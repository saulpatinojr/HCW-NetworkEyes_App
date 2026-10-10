"""TestClient tests for the cna-api auth, readiness, and reliability paths.

These cover the remediations layered onto ``apps/cna-api`` for the
production-readiness review:

  * **SEC-001 — bearer auth.** When ``CNA_API_TOKEN`` is configured the API
    rejects any request without ``Authorization: Bearer <token>`` (401), except
    the ``/health`` and ``/ready`` probes. With no token *and* no appliance
    cloud (local dev) it serves unauthenticated.
  * **PY-001 — fail-fast config.** In appliance mode
    (``CNA_APPLIANCE_CLOUD`` set) a missing token or database is a ``SystemExit``
    at startup, never a silent no-op.
  * **PY-008 — readiness.** ``/ready`` is 200 only when ``SELECT 1`` succeeds and
    503 when the database is unreachable/unconfigured; ``/health`` stays liveness.
  * **PY-011 — no secret echo.** A validation error never echoes the request
    body (which for discovery carries plaintext cloud secrets).
  * **REL-001 — stale-job reaping.** A RUNNING job with a stale heartbeat is
    marked FAILED.
  * **C2 — version.** ``/health`` reports the package version, not a literal.

The module is loaded from its file path (the ``apps/cna-api`` package has a
hyphen); the whole module skips cleanly when the API runtime deps are absent,
matching ``test_cna_api_error_paths.py``. In CI the ``[api]`` extra is installed,
so these run rather than skip.
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

_TOKEN = "test-bearer-token-abcdef0123456789"
# A value that must never reach a client response through an error path.
_LEAK_CANARY = "CANARY-SP-VALUE-should-not-leak"


def _load_api_module() -> types.ModuleType:
    """Load ``apps/cna-api/main.py`` under a shared, import-safe name."""
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
    return _load_api_module()


@pytest.fixture
def plain_client(api_main: types.ModuleType):
    """A client against the real app as loaded (no token → no auth middleware)."""
    from fastapi.testclient import TestClient

    return TestClient(api_main.app, raise_server_exceptions=False)


@pytest.fixture
def authed_client(api_main: types.ModuleType):
    """The real app fronted by the bearer middleware with a known token.

    The module-level app carries no auth middleware in the test environment
    (``CNA_API_TOKEN`` unset at import), so we wrap the real ASGI app with the
    middleware directly — this exercises the real routes, the real exempt-path
    list, and the real middleware together without mutating shared app state.
    """
    from fastapi.testclient import TestClient

    wrapped = api_main.BearerTokenMiddleware(api_main.app, token=_TOKEN)
    return TestClient(wrapped, raise_server_exceptions=False)


# ── SEC-001 — bearer token enforcement ───────────────────────────────────────


def test_missing_authorization_header_is_401(authed_client):
    resp = authed_client.post("/intake", json={"x": 1})
    assert resp.status_code == 401
    assert resp.json() == {"detail": "unauthorized"}


def test_wrong_token_is_401(authed_client):
    resp = authed_client.post(
        "/intake", json={"x": 1}, headers={"Authorization": "Bearer not-the-token"}
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "unauthorized"}


def test_non_ascii_bearer_value_is_401_not_500(authed_client):
    # hmac.compare_digest on str raises TypeError for non-ASCII input; the
    # middleware compares bytes so a hostile header cannot force a 500.
    resp = authed_client.post(
        "/intake", json={"x": 1}, headers={b"authorization": b"Bearer \xc3\xa9"}
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "unauthorized"}


def test_correct_token_reaches_the_route(authed_client):
    """A valid bearer token passes auth; /intake then returns its honest 501."""
    resp = authed_client.post(
        "/intake", json={"x": 1}, headers={"Authorization": f"Bearer {_TOKEN}"}
    )
    assert resp.status_code != 401
    assert resp.status_code == 501  # reached the real handler


def test_health_is_exempt_from_auth(authed_client):
    resp = authed_client.get("/health")  # no Authorization header
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_is_exempt_from_auth(authed_client, api_main, monkeypatch):
    """/ready is reachable without a token (503 for no DB, but never 401)."""
    monkeypatch.setattr(api_main, "DATABASE_URL", "", raising=False)
    resp = authed_client.get("/ready")  # no Authorization header
    assert resp.status_code != 401


def test_unauthenticated_allowed_when_token_and_cloud_unset(plain_client, api_main):
    """Local dev: no CNA_API_TOKEN and no appliance cloud → no auth middleware."""
    assert api_main.CNA_API_TOKEN == ""
    resp = plain_client.post("/intake", json={"x": 1})  # no header
    assert resp.status_code != 401
    assert resp.status_code == 501


# ── PY-001 — fail-fast startup validation ─────────────────────────────────────


def test_appliance_mode_without_token_exits(api_main):
    with pytest.raises(SystemExit) as exc:
        api_main._validate_startup_config(
            {"CNA_APPLIANCE_CLOUD": "azure", "DATABASE_URL": "postgresql://x"}
        )
    assert "CNA_API_TOKEN" in str(exc.value)


def test_appliance_mode_without_database_exits(api_main):
    with pytest.raises(SystemExit) as exc:
        api_main._validate_startup_config({"CNA_APPLIANCE_CLOUD": "azure", "CNA_API_TOKEN": "t"})
    assert "DATABASE_URL" in str(exc.value)


def test_appliance_mode_fully_configured_does_not_exit(api_main):
    api_main._validate_startup_config(
        {
            "CNA_APPLIANCE_CLOUD": "azure",
            "CNA_API_TOKEN": "t",
            "DATABASE_URL": "postgresql://x",
        }
    )


def test_local_dev_no_cloud_no_token_does_not_exit(api_main):
    api_main._validate_startup_config({})  # no exception


# ── PY-008 — readiness probe ──────────────────────────────────────────────────


def test_ready_503_when_database_unreachable(plain_client, api_main, monkeypatch):
    monkeypatch.setattr(api_main, "DATABASE_URL", "postgresql://x", raising=False)

    def _boom(*_args, **_kwargs):
        raise api_main.psycopg2.OperationalError("connection refused to db-host")

    monkeypatch.setattr(api_main.psycopg2, "connect", _boom)
    resp = plain_client.get("/ready")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["database"] == "unreachable"
    # The raw driver text (host) must not leak into the probe body.
    assert "db-host" not in resp.text


def test_ready_503_when_database_unconfigured(plain_client, api_main, monkeypatch):
    monkeypatch.setattr(api_main, "DATABASE_URL", "", raising=False)
    resp = plain_client.get("/ready")
    assert resp.status_code == 503
    assert resp.json()["checks"]["database"] == "not_configured"


def test_ready_200_when_select_1_succeeds(plain_client, api_main, monkeypatch):
    monkeypatch.setattr(api_main, "DATABASE_URL", "postgresql://x", raising=False)
    monkeypatch.setattr(api_main, "_get_db", lambda: _FakeConn())
    resp = plain_client.get("/ready")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ready", "checks": {"database": "ok"}}


# ── PY-011 — validation errors never echo the request body ────────────────────


def test_validation_error_does_not_echo_request_body(plain_client):
    """A body missing a required field must not have its values echoed back.

    The discovery start request omits the required ``job_id`` and carries a fake
    secret; the 422 must not contain the secret nor an ``input`` key.
    """
    resp = plain_client.post(
        "/discovery/start",
        json={
            "engagement_id": "e-1",
            "platform": "AZURE",
            "sp_client_secret": _LEAK_CANARY,
        },
    )
    assert resp.status_code == 422
    assert _LEAK_CANARY not in resp.text
    for err in resp.json()["detail"]:
        assert "input" not in err
        assert "ctx" not in err
        assert "loc" in err and "msg" in err


# ── REL-001 — stale-job reaping ───────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rowcount: int) -> None:
        self.executed: list[tuple[str, object]] = []
        self.rowcount = rowcount
        self._fetch: object = (1,)

    def __enter__(self) -> _FakeCursor:
        return self

    def __exit__(self, *_a: object) -> None:
        return None

    def execute(self, sql: str, params: object = None) -> None:
        self.executed.append((sql, params))

    def fetchone(self) -> object:
        return self._fetch


class _FakeConn:
    def __init__(self, rowcount: int = 1) -> None:
        self.cursor_obj = _FakeCursor(rowcount)
        self.committed = False
        self.closed = False

    # Call sites use ``with _get_db() as conn:`` — the pooled context manager
    # (T-704) yields the connection; the fake stands in for both.
    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def cursor(self) -> _FakeCursor:
        return self.cursor_obj

    def commit(self) -> None:
        self.committed = True

    def close(self) -> None:
        self.closed = True


def test_reap_stale_jobs_issues_failed_update(api_main, monkeypatch):
    monkeypatch.setattr(api_main, "DATABASE_URL", "postgresql://x", raising=False)
    fake = _FakeConn(rowcount=1)
    monkeypatch.setattr(api_main, "_get_db", lambda: fake)

    reaped = api_main._reap_stale_jobs()

    assert reaped == 1
    # The connection is pooled (T-704): committed here, returned by db.connection.
    assert fake.committed
    sql, params = fake.cursor_obj.executed[0]
    assert "UPDATE" in sql and "'FAILED'" in sql
    assert "'RUNNING'" in sql
    assert "INTERVAL '1 minute'" in sql
    # The heartbeat threshold and the stale message are bound as parameters.
    assert api_main._STALE_JOB_ERROR in params
    assert api_main._STALE_JOB_MINUTES in params
    # No job_id → the reap is not scoped to a single row.
    assert "AND id = %s" not in sql


def test_reap_stale_jobs_scopes_to_one_job_when_id_given(api_main, monkeypatch):
    monkeypatch.setattr(api_main, "DATABASE_URL", "postgresql://x", raising=False)
    fake = _FakeConn(rowcount=1)
    monkeypatch.setattr(api_main, "_get_db", lambda: fake)

    api_main._reap_stale_jobs("job-42")

    sql, params = fake.cursor_obj.executed[0]
    assert "AND id = %s" in sql
    assert "job-42" in params


def test_reap_stale_jobs_no_db_is_noop(api_main, monkeypatch):
    monkeypatch.setattr(api_main, "DATABASE_URL", "", raising=False)
    assert api_main._reap_stale_jobs() == 0


# ── C2 — /health version comes from package metadata, not a literal ───────────


def test_health_version_is_not_a_literal(plain_client, api_main):
    resp = plain_client.get("/health")
    version = resp.json()["version"]
    assert version != "0.2.0"  # the old hardcoded literal
    assert version == api_main._api_version()


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "1.5"])
def test_stale_job_minutes_rejects_invalid_values(api_main, raw):
    with pytest.raises(SystemExit) as excinfo:
        api_main._parse_stale_job_minutes(raw)
    assert "CNA_STALE_JOB_MINUTES" in str(excinfo.value)


@pytest.mark.parametrize(("raw", "expected"), [(None, 30), ("", 30), (" 45 ", 45), ("1", 1)])
def test_stale_job_minutes_accepts_positive_integers(api_main, raw, expected):
    assert api_main._parse_stale_job_minutes(raw) == expected
