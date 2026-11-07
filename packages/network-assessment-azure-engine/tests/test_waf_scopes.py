"""WAF policies linked to a single listener or path rule of an Application Gateway (issue #352).

Azure lets ``httpListeners[].properties.firewallPolicy`` and
``urlPathMaps[].properties.pathRules[].properties.firewallPolicy`` name a WAF policy that
overrides the gateway-wide one for that listener or path. AZ-NET-007 (v3) and AZ-NET-025 (v2)
evaluate each of them, and a scoped discovery hands over such a policy when it lives outside
the scope, as it does for the gateway-wide policy since #351.
"""

from __future__ import annotations

from engine_fixtures import SUB, export_rows

from network_assessment_azure_engine import evaluate, normalize_resource_graph
from network_assessment_azure_engine.discovery.resource_graph import (
    CONTAINERS_QUERY,
    DEFENDER_QUERY,
    NETWORK_QUERY,
    NVA_QUERY,
    ResourceGraphDiscovery,
    Scope,
    filter_to_scopes,
    referenced_policy_rows,
)

POLICY_TYPE = "microsoft.network/applicationgatewaywebapplicationfirewallpolicies"


def _policy_id(rg: str, name: str) -> str:
    return (
        f"/subscriptions/{SUB}/resourceGroups/{rg}/providers/Microsoft.Network"
        f"/ApplicationGatewayWebApplicationFirewallPolicies/{name}"
    )


GATEWAY_POLICY = _policy_id("hcw-sample-rg", "hcw-sample-gateway-waf")
LISTENER_POLICY = _policy_id("hcw-sample-rg", "hcw-sample-listener-waf")
PATH_POLICY = _policy_id("hcw-sample-rg", "hcw-sample-path-waf")
OTHER_RG_LISTENER_POLICY = _policy_id("hcw-other-rg", "hcw-other-listener-waf")


def _policy_row(policy_id: str, state: str, mode: str) -> dict:
    rg = policy_id.split("/resourceGroups/")[1].split("/")[0]
    return {
        "id": policy_id,
        "name": policy_id.rsplit("/", 1)[1],
        "type": POLICY_TYPE,
        "location": "eastus",
        "resourceGroup": rg,
        "subscriptionId": SUB,
        "properties": {"policySettings": {"state": state, "mode": mode}},
    }


def _rows(
    *,
    listener_policy: str | None = None,
    path_policy: str | None = None,
    policies: list[dict],
    gateway_state: str = "Enabled",
    extra_listener: bool = False,
) -> tuple[list[dict], str]:
    """The fixture export with one gateway whose gateway-wide policy is Enabled in Prevention.

    The gateway gains one listener and one path rule, each optionally linked to its own policy.
    Returns the rows and the gateway id.
    """
    rows = [r for r in export_rows() if r["type"].lower() != POLICY_TYPE]
    agw = next(r for r in rows if r["type"].lower().endswith("/applicationgateways"))
    props = agw["properties"]
    props.pop("webApplicationFirewallConfiguration", None)
    props["firewallPolicy"] = {"id": GATEWAY_POLICY}
    listener: dict = {
        "id": f"{agw['id']}/httpListeners/hcw-sample-listener",
        "name": "hcw-sample-listener",
        "properties": {},
    }
    if listener_policy:
        listener["properties"]["firewallPolicy"] = {"id": listener_policy}
    path_rule: dict = {
        "id": f"{agw['id']}/urlPathMaps/hcw-sample-map/pathRules/hcw-sample-api",
        "name": "hcw-sample-api",
        "properties": {"paths": ["/api/*"]},
    }
    if path_policy:
        path_rule["properties"]["firewallPolicy"] = {"id": path_policy}
    props["httpListeners"] = [listener]
    if extra_listener:
        props["httpListeners"].append(
            {
                "id": f"{agw['id']}/httpListeners/hcw-sample-plain",
                "name": "hcw-sample-plain",
                "properties": {},
            }
        )
    props["urlPathMaps"] = [
        {
            "id": f"{agw['id']}/urlPathMaps/hcw-sample-map",
            "name": "hcw-sample-map",
            "properties": {"pathRules": [path_rule]},
        }
    ]
    rows += [_policy_row(GATEWAY_POLICY, gateway_state, "Prevention"), *policies]
    return rows, agw["id"]


def _waf_findings(rows: list[dict]) -> dict[tuple[str, str], object]:
    report = evaluate(normalize_resource_graph(rows))
    return {
        (f.rule_id, f.resource_id): f
        for f in report.findings
        if f.rule_id in ("AZ-NET-007", "AZ-NET-025")
    }


class TestListenerPolicy:
    def test_disabled_listener_policy_over_an_enabled_gateway_policy_fires_007(self) -> None:
        rows, agw_id = _rows(
            listener_policy=LISTENER_POLICY,
            policies=[_policy_row(LISTENER_POLICY, "Disabled", "Prevention")],
        )
        topology = normalize_resource_graph(rows)
        agw = topology.subscriptions[0].application_gateways[0]
        assert agw.effective_waf_enabled is True
        [scope] = agw.waf_scopes
        assert scope.kind == "listener" and scope.policy is not None
        assert scope.policy.state == "Disabled"

        findings = _waf_findings(rows)
        listener_id = f"{agw_id}/httpListeners/hcw-sample-listener"
        assert set(findings) == {("AZ-NET-007", listener_id)}
        finding = findings[("AZ-NET-007", listener_id)]
        assert "listener hcw-sample-listener has Web Application Firewall disabled" in (
            finding.observed_state.fact
        )
        assert "hcw-sample-listener-waf has state=Disabled" in finding.observed_state.fact
        assert finding.observed_state.evidence_ref == (
            f"export:{SUB}.waf_policies[id={LISTENER_POLICY}].state"
        )

    def test_enabled_listener_policy_in_detection_mode_fires_025(self) -> None:
        rows, agw_id = _rows(
            listener_policy=LISTENER_POLICY,
            policies=[_policy_row(LISTENER_POLICY, "Enabled", "Detection")],
        )
        findings = _waf_findings(rows)
        listener_id = f"{agw_id}/httpListeners/hcw-sample-listener"
        assert set(findings) == {("AZ-NET-025", listener_id)}
        fact = findings[("AZ-NET-025", listener_id)].observed_state.fact
        assert "Detection mode (from its own WAF policy hcw-sample-listener-waf)" in fact

    def test_listener_without_its_own_policy_follows_the_gateway(self) -> None:
        rows, _ = _rows(policies=[])
        assert (
            normalize_resource_graph(rows).subscriptions[0].application_gateways[0].waf_scopes == []
        )
        assert _waf_findings(rows) == {}

    def test_enabled_prevention_listener_policy_is_clean(self) -> None:
        rows, _ = _rows(
            listener_policy=LISTENER_POLICY,
            policies=[_policy_row(LISTENER_POLICY, "Enabled", "Prevention")],
        )
        assert _waf_findings(rows) == {}


class TestPathRulePolicy:
    def test_disabled_path_rule_policy_fires_007_on_the_path_rule(self) -> None:
        rows, agw_id = _rows(
            path_policy=PATH_POLICY,
            policies=[_policy_row(PATH_POLICY, "Disabled", "Prevention")],
        )
        topology = normalize_resource_graph(rows)
        [scope] = topology.subscriptions[0].application_gateways[0].waf_scopes
        assert scope.kind == "path_rule" and scope.name == "hcw-sample-api"
        path_id = f"{agw_id}/urlPathMaps/hcw-sample-map/pathRules/hcw-sample-api"
        findings = _waf_findings(rows)
        assert set(findings) == {("AZ-NET-007", path_id)}
        assert "path rule hcw-sample-api has Web Application Firewall disabled" in (
            findings[("AZ-NET-007", path_id)].observed_state.fact
        )

    def test_listener_and_path_rule_are_reported_separately(self) -> None:
        rows, agw_id = _rows(
            listener_policy=LISTENER_POLICY,
            path_policy=PATH_POLICY,
            policies=[
                _policy_row(LISTENER_POLICY, "Disabled", "Prevention"),
                _policy_row(PATH_POLICY, "Enabled", "Detection"),
            ],
        )
        assert set(_waf_findings(rows)) == {
            ("AZ-NET-007", f"{agw_id}/httpListeners/hcw-sample-listener"),
            ("AZ-NET-025", f"{agw_id}/urlPathMaps/hcw-sample-map/pathRules/hcw-sample-api"),
        }


class TestUnresolvedPolicy:
    def test_a_policy_missing_from_the_input_is_warned_and_not_judged(self) -> None:
        rows, _ = _rows(listener_policy=LISTENER_POLICY, policies=[])
        topology = normalize_resource_graph(rows)
        [scope] = topology.subscriptions[0].application_gateways[0].waf_scopes
        assert scope.policy is None and scope.policy_id == LISTENER_POLICY
        assert any(
            "WAF policy hcw-sample-listener-waf" in w and "not in the export" in w
            for w in topology.warnings
        )
        assert _waf_findings(rows) == {}


class TestListenerPolicyOutsideTheDiscoveryScope:
    def test_referenced_policy_rows_hands_over_a_listener_policy(self) -> None:
        rows, _ = _rows(
            listener_policy=OTHER_RG_LISTENER_POLICY,
            policies=[_policy_row(OTHER_RG_LISTENER_POLICY, "Disabled", "Prevention")],
        )
        in_scope = filter_to_scopes(rows, [Scope(SUB, "hcw-sample-rg")])
        assert not any(r["id"] == OTHER_RG_LISTENER_POLICY for r in in_scope)
        assert [r["id"] for r in referenced_policy_rows(rows, in_scope)] == [
            OTHER_RG_LISTENER_POLICY
        ]

    def test_scoped_discovery_reads_the_listener_policy_and_007_fires(self) -> None:
        from test_resource_graph_discovery import FakeClient, fixture, single_page

        rows, agw_id = _rows(
            listener_policy=OTHER_RG_LISTENER_POLICY,
            policies=[_policy_row(OTHER_RG_LISTENER_POLICY, "Disabled", "Prevention")],
        )
        client = FakeClient(
            {
                NETWORK_QUERY: single_page(rows),
                CONTAINERS_QUERY: single_page(fixture("containers")),
                DEFENDER_QUERY: single_page(fixture("defender")),
                NVA_QUERY: single_page(fixture("nva")),
            }
        )
        topology = ResourceGraphDiscovery(
            None, [Scope(SUB, "hcw-sample-rg")], progress=lambda _m: None, client=client
        ).run()
        [scope] = topology.subscriptions[0].application_gateways[0].waf_scopes
        assert scope.policy is not None and scope.policy.state == "Disabled"
        listener_id = f"{agw_id}/httpListeners/hcw-sample-listener"
        findings = {(f.rule_id, f.resource_id): f for f in evaluate(topology).findings}
        assert findings[("AZ-NET-007", listener_id)].observed_state.evidence_ref == (
            f"discovery:{SUB}.waf_policies[id={OTHER_RG_LISTENER_POLICY}].state"
        )


class TestGatewayAndScopeTogether:
    """Review of the first push: no duplicate for the gateway's own policy, no gateway finding
    when the gateway-wide setting applies to no listener."""

    def test_a_listener_linked_to_the_gateway_policy_adds_no_second_finding(self) -> None:
        rows, agw_id = _rows(listener_policy=GATEWAY_POLICY, policies=[], gateway_state="Disabled")
        assert set(_waf_findings(rows)) == {("AZ-NET-007", agw_id)}

    def test_every_listener_with_its_own_enabled_policy_silences_the_gateway(self) -> None:
        rows, _ = _rows(
            listener_policy=LISTENER_POLICY,
            policies=[_policy_row(LISTENER_POLICY, "Enabled", "Prevention")],
            gateway_state="Disabled",
        )
        agw = normalize_resource_graph(rows).subscriptions[0].application_gateways[0]
        assert agw.listener_count == 1 and agw.gateway_policy_unused is True
        assert _waf_findings(rows) == {}

    def test_a_listener_without_its_own_policy_keeps_the_gateway_finding(self) -> None:
        rows, agw_id = _rows(
            listener_policy=LISTENER_POLICY,
            policies=[_policy_row(LISTENER_POLICY, "Enabled", "Prevention")],
            gateway_state="Disabled",
            extra_listener=True,
        )
        agw = normalize_resource_graph(rows).subscriptions[0].application_gateways[0]
        assert agw.listener_count == 2 and agw.gateway_policy_unused is False
        assert set(_waf_findings(rows)) == {("AZ-NET-007", agw_id)}

    def test_a_scope_finding_carries_its_own_recommendation(self) -> None:
        rows, agw_id = _rows(
            listener_policy=LISTENER_POLICY,
            policies=[_policy_row(LISTENER_POLICY, "Disabled", "Prevention")],
        )
        finding = _waf_findings(rows)[("AZ-NET-007", f"{agw_id}/httpListeners/hcw-sample-listener")]
        assert "linked to this listener" in finding.remediation

    def test_a_row_without_sub_resource_ids_gets_azure_shaped_unique_ids(self) -> None:
        rows, agw_id = _rows(
            listener_policy=LISTENER_POLICY,
            path_policy=PATH_POLICY,
            policies=[
                _policy_row(LISTENER_POLICY, "Disabled", "Prevention"),
                _policy_row(PATH_POLICY, "Disabled", "Prevention"),
            ],
        )
        agw = next(r for r in rows if r["type"].lower().endswith("/applicationgateways"))
        for listener in agw["properties"]["httpListeners"]:
            listener.pop("id")
        for path_map in agw["properties"]["urlPathMaps"]:
            path_map.pop("id")
            for path_rule in path_map["properties"]["pathRules"]:
                path_rule.pop("id")
        ids = {
            s.id
            for s in normalize_resource_graph(rows)
            .subscriptions[0]
            .application_gateways[0]
            .waf_scopes
        }
        assert ids == {
            f"{agw_id}/httpListeners/hcw-sample-listener",
            f"{agw_id}/urlPathMaps/hcw-sample-map/pathRules/hcw-sample-api",
        }
