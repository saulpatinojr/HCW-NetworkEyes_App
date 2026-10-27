"""``apps/cna-api/main.py`` evaluates Azure findings through the rule registry (change set B).

The API's own Engine B (17 ``_check_*`` helpers, ``_topology_to_findings``) is gone; the
Azure discovery runner hands the discovered topology to ``evaluate()`` and writes every
finding through ``finding_to_record`` with its rule id. These tests drive
``_run_azure_discovery`` with a fake discovery and captured writes, and pin the acceptance
grep of the plan: ``main.py`` defines no ``_check_`` function.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import types
from pathlib import Path

import pytest

from network_assessment.core.topology.azure import AzureSubscriptionTopology, AzureTopology, VNet

_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_DIR = _REPO_ROOT / "apps" / "cna-api"
_API_MAIN = _API_DIR / "main.py"
SUB = "00000000-0000-0000-0000-000000000001"
RULE_ID_RE = re.compile(r"^(AZ-(?:NET|BCDR|COST)-\d{3}): ")


def _import_or_skip_reason() -> str | None:
    for dep in ("fastapi", "httpx", "starlette", "pydantic", "psycopg2"):
        if importlib.util.find_spec(dep) is None:
            return f"{dep} not installed in this environment"
    if not _API_MAIN.exists():
        return f"{_API_MAIN} not found"
    return None


_SKIP_REASON = _import_or_skip_reason()
pytestmark = pytest.mark.skipif(
    _SKIP_REASON is not None,
    reason=f"cna-api tests require the API deps: {_SKIP_REASON}",
)


def _load_api_module() -> types.ModuleType:
    """Load ``apps/cna-api/main.py`` under the import-safe name the other API tests share."""
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


@pytest.fixture(scope="module")
def api_main() -> types.ModuleType:
    return _load_api_module()


def _topology(blocked: bool = False) -> AzureTopology:
    vnet = VNet(
        id=f"/subscriptions/{SUB}/resourceGroups/hcw-sample-rg/providers/Microsoft.Network/virtualNetworks/hcw-sample-vnet",
        name="hcw-sample-vnet",
        location="eastus",
        resource_group="hcw-sample-rg",
        subscription_id=SUB,
        ddos_protection_enabled=False,
        flow_logs_enabled=False,
    )
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        subscription_name="hcw-sample-sub",
        tenant_id="t",
        vnets=[vnet],
        discovery_blocked=blocked,
    )
    return AzureTopology(engagement_id="hcw-sample-engagement", tenant_id="t", subscriptions=[sub])


class _Captured:
    def __init__(self) -> None:
        self.records: list[dict] | None = None
        self.jobs: list[dict] = []
        self.advanced: list[str] = []


def _progress_lines(cap: _Captured) -> list[str]:
    """The runner stores its progress log JSON-encoded; read the last snapshot's lines."""
    logs = [j["progressLog"] for j in cap.jobs if "progressLog" in j]
    return json.loads(logs[-1]) if logs else []


@pytest.fixture
def captured(api_main, monkeypatch) -> _Captured:
    cap = _Captured()

    def _replace(engagement_id, credential_id, findings):
        cap.records = list(findings)

    monkeypatch.setattr(api_main, "_replace_discovery_findings", _replace)
    monkeypatch.setattr(
        api_main, "_update_job", lambda job_id, **kw: cap.jobs.append({"job_id": job_id, **kw})
    )
    monkeypatch.setattr(
        api_main, "_advance_engagement_status", lambda eid: cap.advanced.append(eid)
    )
    monkeypatch.setattr(api_main, "rebuild_metrics", lambda eid: 0)
    return cap


def _fake_discovery(topology: AzureTopology):
    class FakeDiscovery:
        def __init__(self, store, options, progress_callback=None):
            self.progress_callback = progress_callback

        def run(self) -> AzureTopology:
            return topology

    return FakeDiscovery


def _request(api_main):
    return api_main.DiscoveryStartRequest(
        job_id="hcw-sample-job",
        engagement_id="hcw-sample-engagement",
        credential_id="hcw-sample-credential",
        tenant_id="00000000-0000-0000-0000-000000000002",
        subscription_ids=[SUB],
    )


class TestRunnerUsesTheRegistry:
    def test_every_persisted_finding_carries_a_rule_id(self, api_main, captured, monkeypatch):
        monkeypatch.setattr(api_main, "AzureDiscovery", _fake_discovery(_topology()))
        api_main._run_azure_discovery(_request(api_main))

        assert captured.records, "the runner wrote nothing"
        for record in captured.records:
            assert record["rule_id"], record
            assert RULE_ID_RE.match(record["title"]), record["title"]
            assert record["rule_id"] in api_main.RULES
            assert record["traffic_direction"] in ("east_west", "north_south", "management")
        ids = {r["rule_id"] for r in captured.records}
        assert {"AZ-NET-001", "AZ-NET-006", "AZ-NET-032", "AZ-NET-033"} <= ids

    def test_job_completes_with_the_persisted_count(self, api_main, captured, monkeypatch):
        monkeypatch.setattr(api_main, "AzureDiscovery", _fake_discovery(_topology()))
        api_main._run_azure_discovery(_request(api_main))

        completed = [j for j in captured.jobs if j.get("status") == "COMPLETED"]
        assert len(completed) == 1
        assert completed[0]["findingsCount"] == len(captured.records)
        assert captured.advanced == ["hcw-sample-engagement"]
        progress = "\n".join(_progress_lines(captured))
        assert (
            f"Evaluating {len(api_main.RULES)} Azure rules (rules {api_main.RULES_VERSION})"
            in progress
        )
        assert "hcw-sample-sub → " in progress

    def test_blocked_subscription_writes_no_findings_and_says_so(
        self, api_main, captured, monkeypatch
    ):
        monkeypatch.setattr(api_main, "AzureDiscovery", _fake_discovery(_topology(blocked=True)))
        api_main._run_azure_discovery(_request(api_main))

        assert captured.records == []
        progress = "\n".join(_progress_lines(captured))
        assert "discovery blocked; no rules evaluated" in progress
        assert [j for j in captured.jobs if j.get("status") == "COMPLETED"]

    def test_discovery_failure_is_sanitized_not_raised(self, api_main, captured, monkeypatch):
        class Boom:
            def __init__(self, *a, **k): ...

            def run(self):
                raise RuntimeError(
                    "AuthorizationFailed at https://login.microsoftonline.com/deadbeef"
                )

        monkeypatch.setattr(api_main, "AzureDiscovery", Boom)
        api_main._run_azure_discovery(_request(api_main))

        failed = [j for j in captured.jobs if j.get("status") == "FAILED"]
        assert len(failed) == 1
        assert "microsoftonline" not in failed[0]["errorMessage"]
        assert captured.records is None


class TestEngineBIsGone:
    def test_main_defines_no_check_functions(self):
        source = _API_MAIN.read_text(encoding="utf-8")
        assert re.findall(r"^def _check_\w+", source, re.M) == []
        assert "_topology_to_findings" not in source
        assert "_finding_model_to_dict" not in source
        assert "_PLATFORM_SUBNETS" not in source

    def test_finding_to_record_prefixes_the_rule_id_once(self):
        if str(_API_DIR) not in sys.path:
            sys.path.insert(0, str(_API_DIR))
        from finding_records import finding_to_record

        from network_assessment.core.findings_schema import Finding, FindingSeverity, ObservedState

        finding = Finding(
            rule_id="AZ-NET-020",
            severity=FindingSeverity.CRITICAL,
            title="NSG allows RDP/SSH inbound from Internet",
            category="Remote Access",
            observed_state=ObservedState(fact="f", evidence_ref="e"),
            traffic_direction="north_south",
        )
        record = finding_to_record(finding)
        assert record["title"] == "AZ-NET-020: NSG allows RDP/SSH inbound from Internet"
        assert record["severity"] == "CRITICAL"
        assert record["description"] == "f"
        assert (
            finding_to_record(finding.model_copy(update={"title": record["title"]}))["title"]
            == record["title"]
        )
