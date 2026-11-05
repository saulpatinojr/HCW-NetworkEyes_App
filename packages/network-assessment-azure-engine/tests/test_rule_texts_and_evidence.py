"""What the downstream lab edition needs from every release of this engine (issue 350).

The lab edition (``saulpatinojr/HCW-NetworkEyes_AddOn``) adopts the released wheel unchanged
and gates it with its own tests: every rule text is present and hedge-free (its catalog and
``GET /api/rules`` show them), every finding cites the input it came from, and a WAF policy
linked to an Application Gateway is read. These tests pin the same contract here, so a
release that breaks it fails in this repository before it is tagged.
"""

from __future__ import annotations

import pytest
from engine_fixtures import SUB, export_rows

from network_assessment_azure_engine import (
    AzureSubscriptionTopology,
    AzureTopology,
    evaluate,
    normalize_resource_graph,
)
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
from network_assessment_azure_engine.findings.enforcer import ObservedStateEnforcer
from network_assessment_azure_engine.model.azure import AppGatewayWafPolicy, ApplicationGateway
from network_assessment_azure_engine.normalize.resource_graph import normalize_rows
from network_assessment_azure_engine.rules import evidence_ref_for, rule_metadata

ENFORCER = ObservedStateEnforcer()
RULE_IDS = [m.id for m in rule_metadata()]
TEXT_FIELDS = ("title", "description", "remediation", "evidence")


@pytest.mark.parametrize("rule_id", RULE_IDS)
def test_every_rule_text_is_present_and_hedge_free(rule_id: str) -> None:
    meta = next(m for m in rule_metadata() if m.id == rule_id)
    for field in TEXT_FIELDS:
        text = getattr(meta, field)
        assert text and text.strip(), f"{rule_id}.{field} is empty"
        assert ENFORCER.scan_text(text) == [], f"{rule_id}.{field}: {text!r}"
    assert meta.description != meta.remediation, rule_id


def test_every_finding_over_the_export_is_complete_and_cites_the_export() -> None:
    topology = normalize_resource_graph(export_rows())
    report = evaluate(topology)
    assert report.total_count > 0
    for f in report.findings:
        prefix = f"export:{f.account_id}."
        assert f.observed_state.evidence_ref.startswith(prefix), (
            f.id,
            f.observed_state.evidence_ref,
        )
        for field in ("title", "description", "remediation"):
            text = getattr(f, field)
            assert text and ENFORCER.scan_text(text) == [], (f.id, field, text)
        assert ENFORCER.scan_text(f.observed_state.fact) == [], (f.id, f.observed_state.fact)


def test_evidence_ref_prefix_follows_the_topology_source() -> None:
    """An uploaded export cites ``export:``; live discovery cites ``discovery:``."""
    topology = normalize_resource_graph(export_rows())
    sub = topology.subscriptions[0]
    assert evidence_ref_for(topology, sub, "vnets[id=x].dns_servers") == (
        f"export:{SUB}.vnets[id=x].dns_servers"
    )
    live = topology.model_copy(update={"source": "discovery"})
    assert evidence_ref_for(live, sub, "vnets[id=x].dns_servers") == (
        f"discovery:{SUB}.vnets[id=x].dns_servers"
    )
    refs = {f.observed_state.evidence_ref.split(":", 1)[0] for f in evaluate(live).findings}
    assert refs == {"discovery"}


def _gateway(
    *,
    inline_enabled: bool,
    inline_mode: str | None,
    policy: AppGatewayWafPolicy | None,
) -> ApplicationGateway:
    return ApplicationGateway(
        id=f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/applicationGateways/agw",
        name="hcw-sample-agw",
        location="eastus",
        resource_group="rg",
        sku_name="WAF_v2",
        waf_enabled=inline_enabled,
        waf_mode=inline_mode,
        waf_policy_id=policy.id if policy else None,
        waf_policy=policy,
    )


def _policy(state: str, mode: str) -> AppGatewayWafPolicy:
    return AppGatewayWafPolicy(
        id=f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/applicationGatewayWebApplicationFirewallPolicies/waf",
        name="hcw-sample-wafpolicy",
        resource_group="rg",
        state=state,
        mode=mode,
    )


def _waf_findings(agw: ApplicationGateway) -> dict[str, str]:
    sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", application_gateways=[agw])
    report = evaluate(AzureTopology(source="export", subscriptions=[sub]))
    return {
        f.rule_id: f.observed_state.fact
        for f in report.findings
        if f.rule_id in ("AZ-NET-007", "AZ-NET-025")
    }


class TestLinkedWafPolicy:
    """AZ-NET-007 and AZ-NET-025 read the WAF policy linked to the gateway (v2 of both rules)."""

    def test_policy_in_prevention_mode_satisfies_both_rules(self) -> None:
        agw = _gateway(
            inline_enabled=False, inline_mode=None, policy=_policy("Enabled", "Prevention")
        )
        assert agw.effective_waf_enabled and agw.effective_waf_mode == "Prevention"
        assert _waf_findings(agw) == {}

    def test_policy_in_detection_mode_fires_025_not_007(self) -> None:
        agw = _gateway(
            inline_enabled=False, inline_mode=None, policy=_policy("Enabled", "Detection")
        )
        facts = _waf_findings(agw)
        assert set(facts) == {"AZ-NET-025"}
        assert "Detection mode (from its WAF policy hcw-sample-wafpolicy)" in facts["AZ-NET-025"]

    def test_disabled_policy_and_no_inline_waf_fires_007(self) -> None:
        agw = _gateway(
            inline_enabled=False, inline_mode=None, policy=_policy("Disabled", "Prevention")
        )
        facts = _waf_findings(agw)
        assert set(facts) == {"AZ-NET-007"}
        assert "linked WAF policy hcw-sample-wafpolicy has state=Disabled" in facts["AZ-NET-007"]

    def test_no_policy_falls_back_to_the_inline_setting(self) -> None:
        assert set(
            _waf_findings(_gateway(inline_enabled=False, inline_mode=None, policy=None))
        ) == {"AZ-NET-007"}
        assert set(
            _waf_findings(_gateway(inline_enabled=True, inline_mode="Detection", policy=None))
        ) == {"AZ-NET-025"}
        assert (
            _waf_findings(_gateway(inline_enabled=True, inline_mode="Prevention", policy=None))
            == {}
        )

    def test_policy_mode_wins_over_the_inline_mode(self) -> None:
        agw = _gateway(
            inline_enabled=True, inline_mode="Detection", policy=_policy("Enabled", "Prevention")
        )
        assert _waf_findings(agw) == {}

    def test_disabled_policy_wins_over_the_inline_enabled_setting(self) -> None:
        """A linked policy decides the state: Disabled over inline enabled is disabled."""
        agw = _gateway(
            inline_enabled=True, inline_mode="Prevention", policy=_policy("Disabled", "Prevention")
        )
        assert agw.effective_waf_enabled is False
        assert set(_waf_findings(agw)) == {"AZ-NET-007"}
        # a policy without a state leaves the inline setting in charge
        agw = _gateway(inline_enabled=True, inline_mode="Prevention", policy=_policy("", ""))
        assert agw.effective_waf_enabled is True and agw.effective_waf_mode == "Prevention"
        assert _waf_findings(agw) == {}

    def test_evidence_cites_the_policy_when_the_policy_supplied_the_value(self) -> None:
        policy = _policy("Enabled", "Detection")

        def refs(agw: ApplicationGateway) -> dict[str, str]:
            sub = AzureSubscriptionTopology(
                subscription_id=SUB, tenant_id="t", application_gateways=[agw]
            )
            report = evaluate(AzureTopology(source="export", subscriptions=[sub]))
            return {f.rule_id: f.observed_state.evidence_ref for f in report.findings}

        from_policy = refs(_gateway(inline_enabled=False, inline_mode=None, policy=policy))
        assert from_policy["AZ-NET-025"] == f"export:{SUB}.waf_policies[id={policy.id}].mode"
        disabled = refs(
            _gateway(inline_enabled=False, inline_mode=None, policy=_policy("Disabled", ""))
        )
        assert disabled["AZ-NET-007"] == f"export:{SUB}.waf_policies[id={policy.id}].state"
        inline = _gateway(inline_enabled=True, inline_mode="Detection", policy=None)
        assert refs(inline)["AZ-NET-025"] == (
            f"export:{SUB}.application_gateways[id={inline.id}].waf_mode"
        )

    def test_normalizer_links_the_policy_row_to_the_gateway(self) -> None:
        """An export whose gateway carries no inline WAF block and links a policy by id."""
        rows = [
            r
            for r in export_rows()
            if r["type"].lower()
            in {
                "microsoft.network/applicationgateways",
                "microsoft.network/applicationgatewaywebapplicationfirewallpolicies",
            }
        ]
        agw_row = next(r for r in rows if r["type"].lower().endswith("/applicationgateways"))
        agw_row["properties"].pop("webApplicationFirewallConfiguration")
        topology = normalize_resource_graph(rows)
        agw = topology.subscriptions[0].application_gateways[0]
        assert agw.waf_policy is not None and agw.waf_policy.name == "hcw-sample-waf"
        assert agw.waf_enabled is False and agw.effective_waf_enabled is True
        report = evaluate(topology)
        by_rule = {f.rule_id for f in report.findings}
        assert "AZ-NET-007" not in by_rule and "AZ-NET-025" in by_rule


OTHER_RG_POLICY = (
    f"/subscriptions/{SUB}/resourceGroups/hcw-other-rg/providers/Microsoft.Network"
    "/ApplicationGatewayWebApplicationFirewallPolicies/hcw-other-waf"
)


def _rows_with_policy_in_another_resource_group(state: str) -> list[dict]:
    """The fixture export, its gateway now linked to a policy that lives in another resource group."""
    rows = export_rows()
    agw = next(r for r in rows if r["type"].lower().endswith("/applicationgateways"))
    agw["properties"]["firewallPolicy"] = {"id": OTHER_RG_POLICY}
    agw["properties"]["webApplicationFirewallConfiguration"]["enabled"] = True
    rows = [r for r in rows if not r["type"].lower().endswith("firewallpolicies")]
    rows.append(
        {
            "id": OTHER_RG_POLICY,
            "name": "hcw-other-waf",
            "type": "microsoft.network/applicationgatewaywebapplicationfirewallpolicies",
            "location": "eastus",
            "resourceGroup": "hcw-other-rg",
            "subscriptionId": SUB,
            "properties": {"policySettings": {"state": state, "mode": "Prevention"}},
        }
    )
    return rows


class TestPolicyOutsideTheDiscoveryScope:
    """A resource-group scope keeps the gateway and would drop its policy; the policy is handed
    over for the lookup only, so a Disabled policy in another resource group is still read."""

    def test_referenced_policy_rows_hands_over_only_the_policies_in_scope_rows_name(self):
        rows = _rows_with_policy_in_another_resource_group("Disabled")
        in_scope = filter_to_scopes(rows, [Scope(SUB, "hcw-sample-rg")])
        assert not any(r["id"] == OTHER_RG_POLICY for r in in_scope)
        referenced = referenced_policy_rows(rows, in_scope)
        assert [r["id"] for r in referenced] == [OTHER_RG_POLICY]
        # a policy already in scope is not handed over twice
        assert referenced_policy_rows(rows, rows) == []

    def test_scoped_discovery_reads_the_disabled_policy_and_az_net_007_fires(self):
        from test_resource_graph_discovery import FakeClient, fixture, single_page

        rows = _rows_with_policy_in_another_resource_group("Disabled")
        client = FakeClient(
            {
                NETWORK_QUERY: single_page(rows),
                CONTAINERS_QUERY: single_page(fixture("containers")),
                DEFENDER_QUERY: single_page(fixture("defender")),
                NVA_QUERY: single_page(fixture("nva")),
            }
        )
        messages: list[str] = []
        topology = ResourceGraphDiscovery(
            None, [Scope(SUB, "hcw-sample-rg")], progress=messages.append, client=client
        ).run()
        sub = topology.subscriptions[0]
        agw = sub.application_gateways[0]
        assert agw.waf_policy is not None and agw.waf_policy.state == "Disabled"
        assert agw.waf_enabled is True and agw.effective_waf_enabled is False
        # the policy resolves the reference and is not part of the scoped resource set
        assert sub.waf_policies == []
        assert "microsoft.network/applicationgatewaywebapplicationfirewallpolicies" not in (
            topology.resource_counts
        )
        assert not any("WAF policy" in w and "not in the export" in w for w in topology.warnings)
        assert any("1 referenced policy row(s) outside it" in m for m in messages)
        findings = {f.rule_id: f for f in evaluate(topology).findings}
        assert "AZ-NET-007" in findings
        assert findings["AZ-NET-007"].observed_state.evidence_ref == (
            f"discovery:{SUB}.waf_policies[id={OTHER_RG_POLICY}].state"
        )

    def test_facts_carry_the_effective_waf_state(self):
        """``NormalizedExport.facts`` and AZ-NET-007 cannot contradict each other."""
        rows = _rows_with_policy_in_another_resource_group("Disabled")
        export = normalize_rows(rows)
        agw = export.topology.subscriptions[0].application_gateways[0]
        assert export.facts[agw.id]["wafEnabled"] is False
        assert export.facts[agw.id]["wafMode"] == "Prevention"
        in_scope = filter_to_scopes(rows, [Scope(SUB, "hcw-sample-rg")])
        scoped = normalize_rows(in_scope, referenced=referenced_policy_rows(rows, in_scope))
        assert scoped.facts[agw.id]["wafEnabled"] is False
        assert OTHER_RG_POLICY not in scoped.facts  # no facts for a referenced row
