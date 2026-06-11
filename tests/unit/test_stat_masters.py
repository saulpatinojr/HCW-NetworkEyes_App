"""Unit tests for the stat-master aggregation builder (Phase C)."""

from cna.core.findings_schema import Finding, FrameworkMapping, ObservedState
from cna.core.stat_masters import StatMasterRecord, build_stat_masters
from cna.core.topology_schema import AzureSubscriptionTopology, AzureTopology

SUB = "00000000-0000-0000-0000-000000000001"


def _model_finding(**overrides) -> Finding:
    base = {
        "rule_id": "AZ-COST-001",
        "severity": "low",
        "platform": "azure",
        "region": "eastus",
        "category": "FinOps",
        "title": "Orphaned Public IP",
        "resource_id": "pip-1",
        "resource_type": "Microsoft.Network/publicIPAddresses",
        "account_id": SUB,
        "observed_state": ObservedState(fact="observed", evidence_ref="ref"),
        "traffic_direction": "north_south",
        "est_monthly_cost_usd": 3.65,
        "framework_mappings": [FrameworkMapping(framework="FinOps Framework")],
    }
    base.update(overrides)
    return Finding(**base)


def _dict_finding(**overrides) -> dict:
    base = {
        "title": "Subnet 'app' in 'vnet-1' has no NSG",
        "severity": "MEDIUM",
        "category": "Network Segmentation",
        "description": "…",
        "traffic_direction": "east_west",
    }
    base.update(overrides)
    return base


def test_empty_findings_yields_empty_bundle():
    bundle = build_stat_masters(None, [])
    assert bundle.records == []
    assert bundle.topology_pattern is None


def test_identical_dimension_tuples_aggregate_into_one_record():
    findings = [
        _model_finding(resource_id="pip-1"),
        _model_finding(resource_id="pip-2"),
        _model_finding(resource_id="pip-2"),  # duplicate resource
    ]
    bundle = build_stat_masters(None, findings)
    assert len(bundle.records) == 1
    rec = bundle.records[0]
    assert rec.finding_count == 3
    assert rec.resource_count == 2  # distinct resource ids
    assert rec.est_monthly_cost_impact == round(3.65 * 3, 2)
    assert rec.rule_id == "AZ-COST-001"
    assert rec.severity == "LOW"
    assert rec.traffic_direction == "north_south"
    assert rec.subscription_id == SUB
    assert rec.framework == "FinOps Framework"


def test_different_dimensions_produce_separate_records():
    findings = [
        _model_finding(region="eastus"),
        _model_finding(region="westus2"),
    ]
    bundle = build_stat_masters(None, findings)
    assert len(bundle.records) == 2
    assert {r.region for r in bundle.records} == {"eastus", "westus2"}


def test_dict_findings_without_rule_id_bucket_with_fallbacks():
    findings = [_dict_finding(), _dict_finding()]
    bundle = build_stat_masters(None, findings)
    assert len(bundle.records) == 1
    rec = bundle.records[0]
    assert rec.finding_count == 2
    assert rec.resource_count == 2  # no resource ids — one per finding
    assert rec.rule_id == "—"
    assert rec.framework == "Unmapped"
    assert rec.region == "Unknown"
    assert rec.subscription_id == "default"
    assert rec.resource_type == "Other"
    assert rec.est_monthly_cost_impact == 0.0


def test_dict_findings_extract_rule_id_from_title():
    findings = [_dict_finding(title="AZ-BCDR-002 Single ExpressRoute circuit")]
    bundle = build_stat_masters(None, findings)
    assert bundle.records[0].rule_id == "AZ-BCDR-002"


def test_dict_findings_accept_prisma_camel_case_keys():
    findings = [
        {
            "title": "Orphaned Public IP",
            "severity": "LOW",
            "category": "FinOps",
            "trafficDirection": "north_south",
            "region": "eastus",
            "resourceType": "Microsoft.Network/publicIPAddresses",
            "estCostImpact": 3.65,
            "credentialId": "cred-1",
        }
    ]
    bundle = build_stat_masters(None, findings)
    rec = bundle.records[0]
    assert rec.traffic_direction == "north_south"
    assert rec.resource_type == "Microsoft.Network/publicIPAddresses"
    assert rec.subscription_id == "cred-1"
    assert rec.est_monthly_cost_impact == 3.65


def test_mixed_model_and_dict_findings_with_same_dimensions_merge():
    model = _model_finding(
        rule_id=None,
        title="Orphaned Public IP",
        severity="low",
        category="FinOps",
        region="eastus",
        account_id="cred-1",
        resource_type="Microsoft.Network/publicIPAddresses",
        framework_mappings=[],
        est_monthly_cost_usd=1.0,
        resource_id="pip-9",
    )
    as_dict = {
        "title": "Orphaned Public IP",
        "severity": "LOW",
        "category": "FinOps",
        "trafficDirection": "north_south",
        "region": "eastus",
        "resourceType": "Microsoft.Network/publicIPAddresses",
        "estCostImpact": 2.5,
        "credentialId": "cred-1",
    }
    bundle = build_stat_masters(None, [model, as_dict])
    assert len(bundle.records) == 1
    rec = bundle.records[0]
    assert rec.finding_count == 2
    assert rec.est_monthly_cost_impact == 3.5
    assert rec.resource_count == 2  # one id ("pip-9") + one anonymous


def test_cost_summing_ignores_unparseable_values():
    findings = [
        _dict_finding(est_cost_impact="not-a-number"),
        _dict_finding(est_cost_impact=10),
    ]
    bundle = build_stat_masters(None, findings)
    assert bundle.records[0].est_monthly_cost_impact == 10.0


def test_topology_metadata_is_populated():
    topology = AzureTopology(
        engagement_id="ENG-001",
        tenant_id="tenant",
        subscriptions=[AzureSubscriptionTopology(subscription_id=SUB, tenant_id="tenant")],
    )
    bundle = build_stat_masters(topology, [_model_finding()], engagement_id="ENG-001")
    assert bundle.generated_for_engagement == "ENG-001"
    assert bundle.subscription_count == 1
    assert bundle.topology_pattern == "isolated"


def test_record_shape_matches_frontend_contract():
    """Field names must mirror apps/cna-web/lib/types/stat-master.ts."""
    expected = {
        "traffic_direction",
        "severity",
        "framework",
        "region",
        "subscription_id",
        "resource_type",
        "category",
        "rule_id",
        "finding_count",
        "resource_count",
        "est_monthly_cost_impact",
    }
    assert set(StatMasterRecord.model_fields) == expected
