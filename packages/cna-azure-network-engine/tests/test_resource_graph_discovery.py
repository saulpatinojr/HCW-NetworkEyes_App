"""Resource Graph discovery (change set D): scopes, paging, backoff, filtering, the attach
functions and ``ResourceGraphDiscovery.run`` against a fake client and fictional fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from engine_fixtures import SUB, export_rows

pytest.importorskip("azure.mgmt.resourcegraph")

from cna_azure_network_engine.discovery import resource_graph as rg  # noqa: E402
from cna_azure_network_engine.discovery.resource_graph import (  # noqa: E402
    CONTAINERS_QUERY,
    DEFENDER_QUERY,
    NETWORK_QUERY,
    NVA_QUERY,
    TRUNCATED_WARNING,
    ResourceGraphDiscovery,
    Scope,
    attach_containers,
    attach_defender,
    attach_nvas,
    filter_to_scopes,
    identify_nva,
    parse_scopes,
    query_all,
    subscriptions_of,
)
from cna_azure_network_engine.model.azure import (  # noqa: E402
    AzureSubscriptionTopology,
    AzureTopology,
)
from cna_azure_network_engine.report.markdown import render_markdown  # noqa: E402
from cna_azure_network_engine.rules.registry import evaluate  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "resource_graph"
SUB2 = "00000000-0000-0000-0000-000000000002"
RG_HUB = f"/subscriptions/{SUB}/resourceGroups/RG-Hub"


def fixture(name: str) -> list[dict]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


# ── a fake Resource Graph client ──────────────────────────────────────────────


class FakeHttpError(Exception):
    def __init__(self, status: int, retry_after: str | None = None) -> None:
        super().__init__(f"HTTP {status}")
        self.status_code = status
        headers = {"Retry-After": retry_after} if retry_after is not None else {}
        self.response = SimpleNamespace(status_code=status, headers=headers)


class FakeClient:
    """Answers each query with its list of pages; records every request it saw."""

    def __init__(self, pages: dict[str, list[dict]], failures: list[Exception] | None = None):
        self.pages = pages
        self.failures = list(failures or [])
        self.requests: list[SimpleNamespace] = []

    def resources(self, request):
        self.requests.append(
            SimpleNamespace(
                query=request.query,
                subscriptions=list(request.subscriptions),
                top=request.options.top,
                skip_token=request.options.skip_token,
            )
        )
        if self.failures:
            raise self.failures.pop(0)
        pages = self.pages[request.query]
        index = int(request.options.skip_token or 0)
        page = pages[index]
        return SimpleNamespace(
            data=page["data"],
            skip_token=page.get("skip_token"),
            total_records=page.get("total_records", sum(len(p["data"]) for p in pages)),
        )


def single_page(rows: list[dict]) -> list[dict]:
    return [{"data": rows}]


# ── scopes ───────────────────────────────────────────────────────────────────


class TestScopes:
    def test_parses_both_shapes_and_lower_cases_the_group(self):
        scopes = parse_scopes(f"/subscriptions/{SUB} {RG_HUB}")
        assert scopes == [Scope(SUB, None), Scope(SUB, "rg-hub")]
        assert subscriptions_of(scopes) == [SUB]

    def test_tolerates_a_trailing_slash_and_deduplicates(self):
        assert parse_scopes(f"/subscriptions/{SUB}/ /subscriptions/{SUB}") == [Scope(SUB, None)]

    @pytest.mark.parametrize(
        "bad",
        [
            "/resourceGroups/rg-hub",
            "/subscriptions/not-a-guid",
            f"/subscriptions/{SUB}/resourceGroups/rg/providers/x",
            "subscriptions/" + SUB,
        ],
    )
    def test_anything_else_exits_at_startup(self, bad: str):
        with pytest.raises(SystemExit, match="NETWORK_ASSESSMENT_SCOPES"):
            parse_scopes(bad)

    def test_empty_value_is_no_scopes(self):
        assert parse_scopes("") == []


class TestFilterToScopes:
    HUB = {
        "id": f"/subscriptions/{SUB}/resourceGroups/RG-Hub/providers/Microsoft.Network/virtualNetworks/hub"
    }
    SPOKE = {
        "id": f"/subscriptions/{SUB}/resourceGroups/rg-spoke/providers/Microsoft.Network/virtualNetworks/spoke",
        "subscriptionId": SUB,
        "resourceGroup": "rg-spoke",
    }
    FOREIGN = {
        "id": f"/subscriptions/{SUB2}/resourceGroups/rg-hub/providers/Microsoft.Network/virtualNetworks/x"
    }

    def test_a_resource_group_scope_keeps_its_rows_case_insensitively_and_drops_the_rest(self):
        kept = filter_to_scopes([self.HUB, self.SPOKE, self.FOREIGN], [Scope(SUB, "rg-hub")])
        assert kept == [self.HUB]

    def test_a_subscription_scope_keeps_every_group_of_that_subscription(self):
        kept = filter_to_scopes([self.HUB, self.SPOKE, self.FOREIGN], [Scope(SUB, None)])
        assert kept == [self.HUB, self.SPOKE]

    def test_a_foreign_scope_row_never_reaches_the_model(self):
        rows = [*export_rows(), self.FOREIGN]
        topology = ResourceGraphDiscovery(
            None,
            [Scope(SUB, None)],
            client=FakeClient(
                {
                    NETWORK_QUERY: single_page(rows),
                    CONTAINERS_QUERY: single_page([]),
                    DEFENDER_QUERY: single_page([]),
                    NVA_QUERY: single_page([]),
                }
            ),
        ).run()
        assert [s.subscription_id for s in topology.subscriptions] == [SUB]

    def test_rows_without_a_subscription_are_dropped(self):
        assert filter_to_scopes([{"name": "orphan"}], [Scope(SUB, None)]) == []


# ── paging and backoff ───────────────────────────────────────────────────────


class TestQueryAll:
    def test_follows_the_skip_token_silently(self):
        client = FakeClient(
            {
                "q": [
                    {"data": [{"id": "a"}, {"id": "b"}], "skip_token": "1", "total_records": 3},
                    {"data": [{"id": "c"}], "total_records": 3},
                ]
            }
        )
        rows, truncated = query_all(client, "q", [SUB], page=2, sleep=lambda _s: None)
        assert [r["id"] for r in rows] == ["a", "b", "c"]
        assert truncated is False
        assert [(r.top, r.skip_token) for r in client.requests] == [(2, None), (2, "1")]
        assert client.requests[0].subscriptions == [SUB]

    def test_the_row_cap_marks_the_result_truncated(self):
        client = FakeClient(
            {
                "q": [
                    {"data": [{"id": "a"}, {"id": "b"}], "skip_token": "1"},
                    {"data": [{"id": "c"}]},
                ]
            }
        )
        rows, truncated = query_all(client, "q", [SUB], page=2, max_rows=2, sleep=lambda _s: None)
        assert len(rows) == 2 and truncated is True
        assert len(client.requests) == 1

    def test_total_records_above_the_rows_received_is_truncated(self):
        client = FakeClient({"q": [{"data": [{"id": "a"}], "total_records": 5}]})
        _rows, truncated = query_all(client, "q", [SUB], sleep=lambda _s: None)
        assert truncated is True

    def test_a_throttled_page_waits_for_retry_after_then_succeeds(self):
        slept: list[float] = []
        client = FakeClient({"q": single_page([{"id": "a"}])}, failures=[FakeHttpError(429, "2")])
        rows, truncated = query_all(client, "q", [SUB], sleep=slept.append)
        assert [r["id"] for r in rows] == ["a"] and truncated is False
        assert slept == [2.0]

    def test_backoff_is_exponential_without_retry_after(self):
        slept: list[float] = []
        client = FakeClient(
            {"q": single_page([{"id": "a"}])}, failures=[FakeHttpError(429), FakeHttpError(503)]
        )
        rows, _ = query_all(client, "q", [SUB], sleep=slept.append)
        assert len(rows) == 1
        assert slept == [1.0, 2.0]

    def test_backoff_is_bounded_and_a_dead_page_truncates_instead_of_raising(self):
        slept: list[float] = []
        client = FakeClient({"q": single_page([])}, failures=[FakeHttpError(429)] * 10)
        rows, truncated = query_all(client, "q", [SUB], sleep=slept.append, max_retries=3)
        assert rows == [] and truncated is True
        assert len(slept) == 3
        assert len(client.requests) == 4

    def test_a_non_retryable_error_does_not_wait(self):
        slept: list[float] = []
        client = FakeClient({"q": single_page([])}, failures=[FakeHttpError(403)])
        rows, truncated = query_all(client, "q", [SUB], sleep=slept.append)
        assert rows == [] and truncated is True and slept == []

    def test_retry_after_is_capped_below_zero_and_tolerates_garbage(self):
        assert rg._retry_after(FakeHttpError(429, "-5")) == 0.0
        assert rg._retry_after(FakeHttpError(429, "soon")) is None
        assert rg._retry_after(RuntimeError("no response")) is None


# ── attach_* ─────────────────────────────────────────────────────────────────


def _topology(*subs: str) -> AzureTopology:
    return AzureTopology(
        source="discovery",
        subscriptions=[AzureSubscriptionTopology(subscription_id=s, tenant_id="t") for s in subs],
    )


class TestAttachContainers:
    def test_names_subscriptions_and_builds_the_management_group_tree(self):
        topology = _topology(SUB)
        attach_containers(topology, fixture("containers"))
        assert topology.subscriptions[0].subscription_name == "hcw-sample-prod"
        groups = {g.name: g for g in topology.management_groups}
        assert set(groups) == {"hcw-sample-root", "hcw-sample-landing"}
        assert groups["hcw-sample-landing"].parent_id == "hcw-sample-root"
        assert groups["hcw-sample-root"].child_mg_ids == ["hcw-sample-landing"]
        assert groups["hcw-sample-landing"].subscription_ids == [SUB]
        assert groups["hcw-sample-landing"].display_name == "Landing zones"

    def test_no_rows_leaves_the_topology_untouched(self):
        topology = _topology(SUB)
        attach_containers(topology, [])
        assert topology.management_groups == []
        assert topology.subscriptions[0].subscription_name is None


class TestAttachDefender:
    def test_keeps_unhealthy_networking_assessments_of_known_subscriptions_only(self):
        topology = _topology(SUB)
        attach_defender(topology, fixture("defender"))
        found = topology.subscriptions[0].defender_assessments
        assert [a.display_name for a in found] == [
            "Management ports should be closed on your virtual machines"
        ]
        one = found[0]
        assert one.status == "Unhealthy" and one.severity == "High"
        assert one.category == "Networking"
        assert one.resource_type == "microsoft.compute/virtualmachines"
        assert one.resource_id.endswith("/virtualMachines/hcw-sample-vm")
        assert one.remediation_description == "Restrict the inbound rule."
        assert one.implementation_effort == "Low" and one.threats == ["ThreatResistance"]

    def test_the_foreign_subscription_row_is_dropped_by_the_scope_filter_before_attach(self):
        rows = filter_to_scopes(fixture("defender"), [Scope(SUB, None)])
        assert all(r["id"].startswith(f"/subscriptions/{SUB}") for r in rows)
        assert len(rows) == 3

    def test_evaluate_and_the_report_accept_a_topology_with_assessments(self):
        topology = _topology(SUB)
        attach_defender(topology, fixture("defender"))
        report = evaluate(topology)
        assert report.rules_version
        assert "Assessment" in render_markdown(report) or report.total_count >= 0


class TestAttachNvas:
    def test_identifies_marketplace_image_and_ip_forwarding_appliances(self):
        topology = _topology(SUB)
        attach_nvas(topology, fixture("nva"))
        nvas = {n.name: n for n in topology.subscriptions[0].nvas}
        assert set(nvas) == {"hcw-sample-ngfw", "hcw-sample-byol", "hcw-sample-router"}
        assert nvas["hcw-sample-ngfw"].identification_method == "marketplace"
        assert nvas["hcw-sample-ngfw"].publisher == "paloaltonetworks"
        assert nvas["hcw-sample-ngfw"].vm_size == "Standard_D3_v2"
        assert nvas["hcw-sample-ngfw"].os_type == "Linux"
        assert nvas["hcw-sample-byol"].identification_method == "image_reference"
        assert nvas["hcw-sample-byol"].offer == "fortinet_fortigate-vm_v5"
        assert nvas["hcw-sample-router"].identification_method == "ip_forwarding"
        assert nvas["hcw-sample-router"].publisher is None

    def test_nics_carry_forwarding_subnet_ip_nsg_and_public_ip(self):
        topology = _topology(SUB)
        attach_nvas(topology, fixture("nva"))
        ngfw = next(n for n in topology.subscriptions[0].nvas if n.name == "hcw-sample-ngfw")
        assert len(ngfw.nics) == 1
        nic = ngfw.nics[0]
        assert nic.ip_forwarding_enabled is True
        assert nic.private_ips == ["10.0.1.4"]
        assert nic.subnet_ids[0].endswith("/subnets/trust")
        assert nic.nsg_id.endswith("/networkSecurityGroups/hcw-sample-nsg")
        assert nic.public_ip_id.endswith("/publicIPAddresses/hcw-sample-pip")
        assert nic.vm_id == ngfw.id and nic.tags == {"role": "ngfw"}

    def test_a_plain_vm_is_not_an_appliance(self):
        topology = _topology(SUB)
        attach_nvas(topology, fixture("nva"))
        assert "hcw-sample-web" not in {n.name for n in topology.subscriptions[0].nvas}

    def test_identify_nva_reads_the_plan_before_the_image(self):
        row = {
            "plan": {"publisher": "Fortinet", "product": "p", "name": "n"},
            "properties": {"storageProfile": {"imageReference": {"publisher": "Canonical"}}},
        }
        assert identify_nva(row) == ("Fortinet", "p", "n", "marketplace")
        assert identify_nva({"plan": None, "properties": {}}) == (None, None, None, None)


# ── run() ────────────────────────────────────────────────────────────────────


class TestResourceGraphDiscoveryRun:
    def _client(self, network_pages=None, **overrides):
        pages = {
            NETWORK_QUERY: network_pages or single_page(export_rows()),
            CONTAINERS_QUERY: single_page(fixture("containers")),
            DEFENDER_QUERY: single_page(fixture("defender")),
            NVA_QUERY: single_page(fixture("nva")),
        }
        pages.update(overrides)
        return FakeClient(pages)

    def test_runs_the_four_queries_over_the_subscription_set_only(self):
        client = self._client()
        messages: list[str] = []
        scopes = [Scope(SUB, "hcw-sample-rg"), Scope(SUB, None)]
        topology = ResourceGraphDiscovery(
            None, scopes, progress=messages.append, client=client
        ).run()

        assert [r.query for r in client.requests] == [
            NETWORK_QUERY,
            CONTAINERS_QUERY,
            DEFENDER_QUERY,
            NVA_QUERY,
        ]
        assert all(r.subscriptions == [SUB] for r in client.requests)
        assert topology.source == "discovery"
        sub = topology.subscriptions[0]
        assert sub.subscription_name == "hcw-sample-prod"
        assert len(sub.vnets) >= 1
        assert len(sub.defender_assessments) == 1
        assert {n.name for n in sub.nvas} == {
            "hcw-sample-ngfw",
            "hcw-sample-byol",
            "hcw-sample-router",
        }
        assert topology.management_groups
        assert TRUNCATED_WARNING not in topology.warnings
        assert any("in scope" in m for m in messages)

    def test_a_truncated_network_query_is_a_warning_not_a_failure(self):
        rows = export_rows()
        client = self._client(
            network_pages=[{"data": rows[:3], "skip_token": "1"}, {"data": rows[3:]}]
        )
        discovery = ResourceGraphDiscovery(None, [Scope(SUB, None)], client=client, page=3)
        discovery._page = 3
        topology = discovery.run()
        assert TRUNCATED_WARNING not in topology.warnings  # paging consumed silently

        capped = ResourceGraphDiscovery(
            None,
            [Scope(SUB, None)],
            client=self._client(
                network_pages=[
                    {"data": rows, "skip_token": "1", "total_records": 10_000},
                    {"data": [], "total_records": 10_000},
                ]
            ),
        )
        topology = capped.run()
        assert TRUNCATED_WARNING in topology.warnings

    def test_the_live_rules_are_unknown_without_the_live_collectors(self):
        topology = ResourceGraphDiscovery(None, [Scope(SUB, None)], client=self._client()).run()
        report = evaluate(topology)
        assert {u.rule_id for u in report.unknowns} & {"AZ-NET-008", "AZ-COST-002"}

    def test_needs_a_scope(self):
        with pytest.raises(ValueError, match="at least one scope"):
            ResourceGraphDiscovery(None, [])

    def test_the_client_is_built_lazily_from_the_sdk(self, monkeypatch):
        built = {}

        class FakeSdkClient:
            def __init__(self, credential):
                built["credential"] = credential

        import azure.mgmt.resourcegraph as sdk

        monkeypatch.setattr(sdk, "ResourceGraphClient", FakeSdkClient)
        discovery = ResourceGraphDiscovery("cred", [Scope(SUB, None)])
        assert isinstance(discovery.client, FakeSdkClient) and built == {"credential": "cred"}
