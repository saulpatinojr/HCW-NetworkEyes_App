"""FastAPI ``TestClient`` tests for the ``apps/cna-api`` error paths (Requirement 2).

This is the integration-level companion to the ``cna.api_status`` /
``cna.api_errors`` unit tests. Where those pin the pure mapping and sanitizer in
isolation, these drive the real FastAPI app end to end and assert the behaviour a
caller actually observes:

  * **2.1 — ``/intake`` honesty.** ``POST /intake`` returns an honest ``501``
    (not a fabricated ``200``); the response body carries no fake success flag.
  * **2.2 / 2.4 — outcome→status class.** Error paths return the matching
    4xx/5xx class and never a ``200``; validation failures are 4xx.
  * **2.3 — downstream SDK sanitization.** When a downstream SDK raises, the
    client response excludes the raw exception text and returns only the
    generic, category-level message from :mod:`cna.api_errors`.

**Importing the app.** ``apps/cna-api`` has a hyphen, so ``apps.cna-api.main`` is
not a valid dotted import. The app is loaded from its file path with
``importlib`` (see ``_load_api_module``), mirroring how the container launches it
by file/module path rather than as an installed package.

**Environment.** The API module imports ``fastapi`` and ``psycopg2`` at import
time, and ``TestClient`` needs ``httpx``/``starlette``. When any of those are not
installed in the current interpreter (e.g. a minimal ``cna``-only checkout), the
whole module is skipped with a clear reason — the tests are still collected and
run in the full dev environment / CI (workflow 300), which installs the API
dependencies. Nothing here mocks the framework itself; only the downstream SDKs
(``azure.identity`` / ``boto3``) are replaced so the sanitizer's real catch sites
execute.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_DIR = _REPO_ROOT / "apps" / "cna-api"
_API_MAIN = _API_DIR / "main.py"

# The raw downstream-SDK detail a handler must never leak to the client. Mirrors
# the shape of real boto3 / azure exception text (endpoints, ARNs, secrets).
_RAW_DETAIL = (
    "AuthorizationFailed: client 'sp-1234' does not have permission at scope "
    "/subscriptions/00000000-0000-0000-0000-000000000000; endpoint "
    "https://login.microsoftonline.com/deadbeef arn:aws:iam::123456789012:role/x"
)
_RAW_FRAGMENTS = (
    "AuthorizationFailed",
    "sp-1234",
    "login.microsoftonline.com",
    "arn:aws:iam",
    "00000000-0000-0000-0000-000000000000",
)


def _load_api_module() -> types.ModuleType:
    """Load ``apps/cna-api/main.py`` as a module despite the hyphenated path.

    The hyphen makes ``apps.cna-api.main`` un-importable via ``import``. We load
    the file directly under a synthetic, import-safe name. ``main.py`` itself
    prepends its own directory to ``sys.path`` so its ``routers.*`` imports
    resolve, so no extra path wiring is needed here — but we ensure the repo
    root is importable first so the top-level ``from cna...`` imports resolve
    when the package is not installed.
    """
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    module_name = "cna_api_main_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    spec = importlib.util.spec_from_file_location(module_name, _API_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Skip the whole module cleanly when the API's runtime deps are absent, so the
# suite stays green on a minimal checkout while still running in CI. The reason
# names the missing piece so an environment gap is never mistaken for a bug.
def _import_or_skip_reason() -> str | None:
    for dep in ("fastapi", "httpx", "starlette", "pydantic"):
        if importlib.util.find_spec(dep) is None:
            return f"{dep} not installed in this environment"
    if importlib.util.find_spec("psycopg2") is None:
        return "psycopg2 not installed in this environment"
    if not _API_MAIN.exists():
        return f"{_API_MAIN} not found"
    return None


_SKIP_REASON = _import_or_skip_reason()
pytestmark = pytest.mark.skipif(
    _SKIP_REASON is not None,
    reason=f"cna-api TestClient tests require the API deps: {_SKIP_REASON}",
)


@pytest.fixture(scope="module")
def api_main() -> types.ModuleType:
    """The loaded ``apps/cna-api/main`` module under test."""
    return _load_api_module()


@pytest.fixture
def client(api_main: types.ModuleType):
    """A FastAPI ``TestClient`` bound to the real app.

    ``raise_server_exceptions=False`` lets a handler's 5xx flow back as a
    response (as a real client would see it) instead of re-raising in the test,
    which is what the error-path assertions need to inspect.
    """
    from fastapi.testclient import TestClient

    return TestClient(api_main.app, raise_server_exceptions=False)


# ── 2.1 — /intake returns an honest 501, never a fabricated 200 ───────────────


def test_intake_returns_honest_501_not_200(client):
    """2.1: /intake reports the real result — a 501, not a fake success."""
    resp = client.post("/intake", json={"anything": "here"})
    assert resp.status_code == 501
    assert resp.status_code != 200
    body = resp.json()
    # An honest not-implemented response carries the error detail and no
    # fabricated success signal.
    assert "detail" in body
    assert body.get("ok") is not True
    assert body["detail"]  # non-empty explanation


def test_intake_501_is_server_error_class(client, api_main):
    """2.2/2.4: the /intake status flows through the single outcome mapping."""
    from cna.api_status import Outcome, OutcomeClass, status_class_of, status_for

    resp = client.post("/intake", json={})
    assert resp.status_code == status_for(Outcome.NOT_IMPLEMENTED)
    assert status_class_of(resp.status_code) is OutcomeClass.SERVER_ERROR


# ── 2.2 / 2.4 — error paths map to the correct non-2xx class ──────────────────


def test_health_success_is_2xx(client):
    """2.4: a successful request returns a 2xx status."""
    resp = client.get("/health")
    assert 200 <= resp.status_code < 300
    assert resp.json()["status"] == "ok"


def test_publish_missing_database_url_is_503_not_200(client, api_main, monkeypatch):
    """2.2: an unconfigured dependency is a 5xx (503), never a fake 200."""
    from cna.api_status import Outcome, status_for

    monkeypatch.setattr(api_main, "DATABASE_URL", "", raising=False)
    resp = client.post("/publish", json={"engagement_id": "e-1"})
    assert resp.status_code == status_for(Outcome.NOT_CONFIGURED)
    assert resp.status_code == 503
    assert resp.status_code != 200


def test_discovery_start_invalid_request_is_4xx(client):
    """2.2: a client-fault request (missing tenant_id) maps to a 4xx class."""
    resp = client.post(
        "/discovery/start",
        json={"job_id": "j-1", "engagement_id": "e-1", "platform": "AZURE"},
    )
    assert 400 <= resp.status_code < 500
    assert resp.status_code != 200


def test_discovery_start_aws_missing_role_is_4xx(client):
    """2.2: AWS discovery without a role ARN is a client error, not a 200."""
    resp = client.post(
        "/discovery/start",
        json={"job_id": "j-1", "engagement_id": "e-1", "platform": "AWS"},
    )
    assert 400 <= resp.status_code < 500
    assert resp.status_code != 200


def test_get_job_status_unconfigured_is_503(client, api_main, monkeypatch):
    """2.2: reading a job without a DB configured is a 5xx (503)."""
    monkeypatch.setattr(api_main, "DATABASE_URL", "", raising=False)
    resp = client.get("/discovery/jobs/does-not-exist")
    assert resp.status_code == 503
    assert resp.status_code != 200


# ── 2.3 — downstream SDK errors are sanitized in the client response ──────────


def _install_fake_azure_sdk(monkeypatch, raw_detail: str) -> None:
    """Replace the Azure SDK modules the handler imports so a call raises.

    ``/discovery/test-connection`` lazily imports ``ClientSecretCredential``
    from ``azure.identity`` and ``SubscriptionClient`` from
    ``azure.mgmt.subscription`` *inside* the handler. We fake both so the
    credential constructs cleanly and listing subscriptions raises a real,
    ``azure``-rooted exception through the handler's genuine catch site — which
    is what exercises the sanitizer's Azure classification (not the generic
    fallback).
    """

    class _FakeAzureError(Exception):
        # The sanitizer classifies by the exception type's ``__module__`` root.
        __module__ = "azure.core.exceptions"

    # azure (package) → azure.identity, azure.mgmt → azure.mgmt.subscription
    fake_azure = types.ModuleType("azure")
    fake_azure.__path__ = []  # type: ignore[attr-defined]  # mark as a package

    fake_identity = types.ModuleType("azure.identity")

    class _FakeCredential:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

    fake_identity.ClientSecretCredential = _FakeCredential  # type: ignore[attr-defined]

    fake_mgmt = types.ModuleType("azure.mgmt")
    fake_mgmt.__path__ = []  # type: ignore[attr-defined]
    fake_subscription = types.ModuleType("azure.mgmt.subscription")

    class _FakeSubscriptionClient:
        def __init__(self, *_args, **_kwargs) -> None:
            raise _FakeAzureError(raw_detail)

    fake_subscription.SubscriptionClient = _FakeSubscriptionClient  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "azure", fake_azure)
    monkeypatch.setitem(sys.modules, "azure.identity", fake_identity)
    monkeypatch.setitem(sys.modules, "azure.mgmt", fake_mgmt)
    monkeypatch.setitem(sys.modules, "azure.mgmt.subscription", fake_subscription)


def test_test_connection_sanitizes_downstream_azure_error(client, monkeypatch):
    """2.3: a raw Azure SDK exception never reaches the client response."""
    _install_fake_azure_sdk(monkeypatch, _RAW_DETAIL)
    resp = client.post(
        "/discovery/test-connection",
        json={
            "tenant_id": "tenant-abc",
            "sp_client_id": "sp-1234",
            "sp_client_secret": "shh-secret",
        },
    )
    # A downstream failure is a 5xx, never a fabricated 200.
    assert resp.status_code >= 500
    assert resp.status_code != 200
    detail = resp.json()["detail"]
    # The generic, category-level message is returned — no raw SDK text leaks.
    assert "Azure" in detail
    for fragment in _RAW_FRAGMENTS:
        assert fragment not in detail
    assert _RAW_DETAIL not in detail
    # The server-side context (tenant id) is never surfaced to the client.
    assert "tenant-abc" not in detail


def test_test_connection_aws_sanitizes_downstream_error(client, monkeypatch):
    """2.3: a raw AWS (boto3) SDK exception is sanitized before the client sees it."""
    fake_boto3 = types.ModuleType("boto3")

    class _FakeBotoError(Exception):
        __module__ = "botocore.exceptions"

    def _session(*_args, **_kwargs):
        raise _FakeBotoError(_RAW_DETAIL)

    fake_boto3.Session = _session  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "boto3", fake_boto3)

    resp = client.post(
        "/discovery/test-connection-aws",
        json={
            "role_arn": "arn:aws:iam::123456789012:role/x",
            "access_key_id": "AKIAEXAMPLE",
            "secret_access_key": "shh-secret",
        },
    )
    assert resp.status_code >= 500
    assert resp.status_code != 200
    detail = resp.json()["detail"]
    assert "AWS" in detail
    for fragment in _RAW_FRAGMENTS:
        assert fragment not in detail
    assert _RAW_DETAIL not in detail


def test_sanitized_error_body_has_no_traceback(client, monkeypatch):
    """2.3: the client body carries no traceback/exception-repr leakage."""
    _install_fake_azure_sdk(monkeypatch, _RAW_DETAIL)
    resp = client.post(
        "/discovery/test-connection",
        json={
            "tenant_id": "t",
            "sp_client_id": "c",
            "sp_client_secret": "s",
        },
    )
    text = resp.text
    for leak in ("Traceback", 'File "', "line ", "Error:", _RAW_DETAIL):
        assert leak not in text
