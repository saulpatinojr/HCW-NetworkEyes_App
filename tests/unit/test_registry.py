"""The Azure rule registry's contract (plan section 14, change set B).

Ids are unique and never reused, every rule carries a Learn URL and a framework mapping,
every title and every emitted description is hedge-free, live-only rules stay registered,
and ``RULES_VERSION`` moves with the id set: the digest below is pinned, so adding, removing
or re-versioning a rule fails here until both the digest and ``RULES_VERSION`` are updated
together.
"""

from __future__ import annotations

import hashlib

import pytest

from cna_azure_network_engine.rules import (
    RULES,
    RULES_VERSION,
    DuplicateRuleError,
    Observation,
    evaluate,
    rule,
    rule_metadata,
    rules_digest,
)
from cna_azure_network_engine.rules.registry import RULES as _registry_dict
from network_assessment.ai_engine.observed_state_enforcer import (
    ObservedStateEnforcer,
    ObservedStateViolation,
)
from network_assessment.core.findings_schema import FindingSeverity, FrameworkMapping
from network_assessment.core.topology.azure import AzureSubscriptionTopology, AzureTopology, VNet

# Re-pin when a rule is added, removed or re-versioned — and bump RULES_VERSION with it.
# The table is the digest's input, so rules_digest() is checked without a hex literal
# (the secrets scanner's entropy plugin would flag one).
PINNED_RULES_VERSION = "2026.10.0"
# The downstream lab edition (HCW-NetworkEyes_AddOn) pins the same table; both move together.
PINNED_VERSIONS = {
    **{f"AZ-NET-{n:03d}": 1 for n in range(1, 34)},
    **{f"AZ-BCDR-{n:03d}": 1 for n in range(1, 8)},
    **{f"AZ-COST-{n:03d}": 1 for n in range(1, 6)},
    "AZ-NET-002": 2,  # merged platform-subnet skip list
    "AZ-NET-003": 2,  # threat intelligence read through the linked firewall policy
    "AZ-NET-006": 2,  # flow logs read from flow-log rows when the topology is an export
    "AZ-NET-007": 2,  # WAF state read through the linked WAF policy
    "AZ-NET-011": 2,  # subnet exhaustion derived from ipConfigurations
    "AZ-NET-012": 2,  # hedge-free facts and title
    "AZ-NET-014": 2,  # Traffic Analytics read from flow-log rows
}

EXPECTED_IDS = sorted(PINNED_VERSIONS)
SUB = "00000000-0000-0000-0000-000000000001"


@pytest.fixture
def scratch_registry(monkeypatch):
    """An empty registry for registration-contract tests; the real one is restored after."""
    monkeypatch.setattr("cna_azure_network_engine.rules.registry.RULES", {})
    return None


def _meta(**overrides):
    base = {
        "id": "AZ-TEST-001",
        "title": "Test rule",
        "severity": FindingSeverity.LOW,
        "category": "Test",
        "version": 1,
        "learn_url": "https://learn.microsoft.com/azure/virtual-network/",
        "frameworks": (FrameworkMapping(framework="Test", control="T-1"),),
        "applies_to": "export",
        "evidence": "vnets[]",
    }
    base.update(overrides)
    return base


class TestIdSet:
    def test_every_planned_id_is_registered_exactly_once(self):
        assert sorted(RULES) == sorted(EXPECTED_IDS)
        assert len(RULES) == len(EXPECTED_IDS) == 45

    def test_rules_version_and_versions_are_pinned_together(self):
        assert RULES_VERSION == PINNED_RULES_VERSION
        assert {rid: meta.version for rid, (meta, _) in RULES.items()} == PINNED_VERSIONS, (
            "the rule id set or a rule version changed: bump RULES_VERSION and re-pin the table"
        )

    def test_digest_is_the_sha256_of_the_pinned_table(self):
        lines = "\n".join(f"{rid}:{ver}" for rid, ver in sorted(PINNED_VERSIONS.items()))
        assert rules_digest() == hashlib.sha256(lines.encode("utf-8")).hexdigest()
        assert len(rules_digest()) == 64

    def test_rule_metadata_is_ordered_by_id(self):
        assert [m.id for m in rule_metadata()] == sorted(RULES)

    def test_live_only_rules_stay_registered(self):
        """The lab edition's live-only set exactly: these surface in unknowns[] for an export."""
        live_only = {m.id for m in rule_metadata() if m.applies_to == "live-only"}
        assert live_only == {
            "AZ-NET-008", "AZ-NET-009", "AZ-NET-010", "AZ-NET-013", "AZ-NET-015",
            "AZ-NET-016", "AZ-NET-017", "AZ-NET-019",
            "AZ-COST-002", "AZ-COST-003", "AZ-COST-005",
        }  # fmt: skip
        assert all(RULES[r][0].inputs for r in live_only)


class TestEveryRuleMeta:
    enforcer = ObservedStateEnforcer()

    @pytest.mark.parametrize("rule_id", EXPECTED_IDS)
    def test_learn_url_framework_version_and_hedge_free_title(self, rule_id):
        meta, fn = RULES[rule_id]
        assert meta.id == rule_id
        assert meta.learn_url.startswith("https://learn.microsoft.com/")
        assert len(meta.frameworks) >= 1
        assert meta.version >= 1
        assert meta.applies_to in ("export", "live-only")
        assert meta.evidence
        assert self.enforcer.scan_text(meta.title) == []
        assert callable(fn)

    def test_versions_match_the_lab_editions_table(self):
        assert {rid for rid, v in PINNED_VERSIONS.items() if v > 1} == {
            "AZ-NET-002",
            "AZ-NET-003",
            "AZ-NET-006",
            "AZ-NET-007",
            "AZ-NET-011",
            "AZ-NET-012",
            "AZ-NET-014",
        }


class TestRegistration:
    def test_duplicate_id_raises(self, scratch_registry):
        rule(**_meta())(lambda sub, topo: [])
        with pytest.raises(DuplicateRuleError):
            rule(**_meta())(lambda sub, topo: [])

    def test_hedged_title_raises_at_registration(self, scratch_registry):
        with pytest.raises(ObservedStateViolation):
            rule(**_meta(title="Subnet may be exposed"))

    def test_missing_framework_raises(self, scratch_registry):
        with pytest.raises(ValueError, match="framework"):
            rule(**_meta(frameworks=()))

    def test_non_learn_url_raises(self, scratch_registry):
        with pytest.raises(ValueError, match="learn_url"):
            rule(**_meta(learn_url="https://example.com/doc"))

    def test_real_registry_untouched_by_scratch_fixture(self):
        assert len(_registry_dict) == 45


def _vnet(ddos: bool) -> VNet:
    return VNet(
        id="/subscriptions/x/vnet",
        name="hcw-sample-vnet",
        location="eastus",
        resource_group="hcw-sample-rg",
        subscription_id=SUB,
        ddos_protection_enabled=ddos,
        flow_logs_enabled=True,
    )


class TestEvaluate:
    def _topology(self, *subs: AzureSubscriptionTopology) -> AzureTopology:
        return AzureTopology(engagement_id="hcw-sample", tenant_id="t", subscriptions=list(subs))

    def test_empty_topology_yields_an_empty_report(self):
        report = evaluate(self._topology())
        assert report.total_count == 0 and report.findings == []
        assert report.engagement_id == "hcw-sample"
        assert report.review_complete is False

    def test_blocked_subscription_is_skipped(self):
        sub = AzureSubscriptionTopology(
            subscription_id=SUB, tenant_id="t", vnets=[_vnet(False)], discovery_blocked=True
        )
        assert evaluate(self._topology(sub)).total_count == 0

    def test_every_finding_carries_rule_metadata(self):
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(False)])
        report = evaluate(self._topology(sub))
        assert report.total_count > 0
        for f in report.findings:
            meta = RULES[f.rule_id][0]
            assert f.platform == "azure"
            assert f.account_id == SUB
            assert f.category == meta.category
            assert f.framework_mappings == list(meta.frameworks)
            assert f.traffic_direction in ("east_west", "north_south", "management")
            assert f.rule_version == meta.version and f.learn_url == meta.learn_url

    def test_emitted_descriptions_and_facts_are_hedge_free(self):
        enforcer = ObservedStateEnforcer()
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(False)])
        for f in evaluate(self._topology(sub)).findings:
            assert enforcer.scan_text(f.title) == []
            assert enforcer.scan_text(f.description or "") == []
            assert enforcer.scan_text(f.observed_state.fact) == []

    def test_dedup_on_rule_and_resource(self):
        sub = AzureSubscriptionTopology(
            subscription_id=SUB, tenant_id="t", vnets=[_vnet(False), _vnet(False)]
        )
        report = evaluate(self._topology(sub))
        assert [f.rule_id for f in report.findings].count("AZ-NET-001") == 1

    def test_counts_match_the_findings(self):
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(False)])
        report = evaluate(self._topology(sub))
        by = {s: sum(1 for f in report.findings if f.severity == s) for s in FindingSeverity}
        assert (
            report.critical_count,
            report.high_count,
            report.medium_count,
            report.low_count,
        ) == (
            by[FindingSeverity.CRITICAL],
            by[FindingSeverity.HIGH],
            by[FindingSeverity.MEDIUM],
            by[FindingSeverity.LOW],
        )
        assert report.total_count == len(report.findings)

    def test_progress_is_called_once_per_subscription(self):
        seen = []
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(False)])
        evaluate(self._topology(sub, sub), progress=lambda i, n, s, f: seen.append((i, n, len(f))))
        assert [(i, n) for i, n, _ in seen] == [(1, 2), (2, 2)]
        assert seen[1][2] == 0, "the second subscription's findings were all deduplicated"

    def test_hedged_observation_from_a_rule_is_rejected_at_evaluation(self, scratch_registry):
        @rule(**_meta())
        def hedged(sub, topo):
            yield Observation(
                resource_id="/r", resource_type="t", fact="This may be a problem.", evidence_ref="e"
            )

        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t")
        with pytest.raises(ObservedStateViolation):
            evaluate(self._topology(sub))

    def test_rule_emitting_a_foreign_rule_id_is_rejected(self, scratch_registry):
        from network_assessment.core.findings_schema import Finding, ObservedState

        @rule(**_meta())
        def foreign(sub, topo):
            yield Finding(
                rule_id="AZ-TEST-999",
                severity=FindingSeverity.LOW,
                title="x",
                observed_state=ObservedState(fact="f", evidence_ref="e"),
            )

        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t")
        with pytest.raises(ValueError, match="AZ-TEST-999"):
            evaluate(self._topology(sub))


class TestUnknowns:
    """Rules the topology cannot answer are reported, never dropped silently."""

    def _topology(self, *subs, **kwargs) -> AzureTopology:
        return AzureTopology(
            engagement_id="hcw-sample", tenant_id="t", subscriptions=list(subs), **kwargs
        )

    def test_live_only_rules_are_unknown_without_their_inputs(self):
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(False)])
        report = evaluate(self._topology(sub))
        unknown_ids = {u.rule_id for u in report.unknowns}
        assert {m.id for m in rule_metadata() if m.applies_to == "live-only"} <= unknown_ids
        assert all(
            u.reason.startswith("needs a live read")
            for u in report.unknowns
            if u.rule_id == "AZ-NET-008"
        )

    def test_live_only_rule_runs_when_its_input_is_present(self):
        from cna_azure_network_engine.model.azure import GatewayMetric, NetworkMetrics

        metrics = NetworkMetrics(
            gateway_metrics=[
                GatewayMetric(gateway_name="gw", gateway_type="Vpn", utilization_pct=95.0)
            ]
        )
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", network_metrics=metrics)
        report = evaluate(self._topology(sub))
        assert "AZ-NET-008" in {f.rule_id for f in report.findings}
        assert "AZ-NET-008" not in {u.rule_id for u in report.unknowns}

    def test_export_without_flow_logs_marks_006_and_014_unknown(self):
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(True)])
        report = evaluate(self._topology(sub, source="export"))
        unknown = {u.rule_id: u.reason for u in report.unknowns}
        assert "AZ-NET-006" in unknown and "AZ-NET-014" in unknown
        assert "flowlogs" in unknown["AZ-NET-006"]
        # Live discovery fills vnet.flow_logs_enabled itself: no unknown there.
        live = evaluate(self._topology(sub))
        assert "AZ-NET-006" not in {u.rule_id for u in live.unknowns}

    def test_export_without_properties_marks_property_rules_unknown(self):
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(True)])
        report = evaluate(self._topology(sub, source="export", has_properties=False))
        unknown = {u.rule_id for u in report.unknowns}
        assert "AZ-NET-001" in unknown
        # AZ-NET-033 reads resource existence only and still answers.
        assert "AZ-NET-033" not in unknown
        assert "AZ-NET-033" in {f.rule_id for f in report.findings}

    def test_report_carries_versions_and_rule_metadata_on_findings(self):
        sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="t", vnets=[_vnet(False)])
        report = evaluate(self._topology(sub))
        assert report.rules_version == RULES_VERSION
        assert report.model_version == "1.4.0"
        for f in report.findings:
            assert f.rule_version == RULES[f.rule_id][0].version
            assert f.learn_url == RULES[f.rule_id][0].learn_url
            assert f.id == f"{f.rule_id}:{f.resource_id}"
            assert f.observed_state.state == "observed"
