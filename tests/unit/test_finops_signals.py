"""Unit tests for FinOps AZ-COST-* finding generation."""

from cna.core.topology_schema import (
    AzureNatGateway,
    AzurePublicIP,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVirtualNetworkGateway,
    GatewayMetric,
    NetworkMetrics,
)
from cna.modules.network.analysis import generate_finops_findings

SUB = "00000000-0000-0000-0000-000000000001"


def _topology(sub: AzureSubscriptionTopology) -> AzureTopology:
    return AzureTopology(engagement_id="ENG-001", tenant_id="tenant", subscriptions=[sub])


def _rule_ids(findings):
    return {f.rule_id for f in findings}


def test_orphaned_public_ip_emits_cost_001():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        public_ips=[
            AzurePublicIP(
                id="pip-1",
                name="pip-orphan",
                location="eastus",
                resource_group="rg",
                associated_resource_type=None,
            ),
            AzurePublicIP(
                id="pip-2",
                name="pip-used",
                location="eastus",
                resource_group="rg",
                associated_resource_type="Firewall",
            ),
        ],
    )
    findings = generate_finops_findings(_topology(sub))
    cost_findings = [f for f in findings if f.rule_id == "AZ-COST-001"]
    assert len(cost_findings) == 1
    f = cost_findings[0]
    assert f.resource_id == "pip-1"
    assert f.est_monthly_cost_usd is not None and f.est_monthly_cost_usd > 0
    assert "[VERIFY]" in (f.description or "")
    assert f.traffic_direction == "north_south"
    assert f.observed_state.fact
    assert f.recommendations


def test_idle_gateway_emits_cost_002():
    gw = AzureVirtualNetworkGateway(
        id="gw-1",
        name="vpn-gw",
        location="eastus",
        resource_group="rg",
        gateway_type="Vpn",
        sku_name="VpnGw2",
    )
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        virtual_network_gateways=[gw],
        network_metrics=NetworkMetrics(
            gateway_metrics=[
                GatewayMetric(
                    gateway_name="vpn-gw",
                    gateway_type="Vpn",
                    ingress_bytes_24h=0,
                    egress_bytes_24h=0,
                )
            ]
        ),
    )
    findings = generate_finops_findings(_topology(sub))
    assert "AZ-COST-002" in _rule_ids(findings)
    f = next(f for f in findings if f.rule_id == "AZ-COST-002")
    assert f.est_monthly_cost_usd == 357.70


def test_oversized_gateway_emits_cost_003_with_saving():
    gw = AzureVirtualNetworkGateway(
        id="gw-1",
        name="vpn-gw",
        location="eastus",
        resource_group="rg",
        gateway_type="Vpn",
        sku_name="VpnGw3",
    )
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        virtual_network_gateways=[gw],
        network_metrics=NetworkMetrics(
            gateway_metrics=[
                GatewayMetric(
                    gateway_name="vpn-gw",
                    gateway_type="Vpn",
                    ingress_bytes_24h=1000,
                    egress_bytes_24h=1000,
                    utilization_pct=3.0,
                )
            ]
        ),
    )
    findings = generate_finops_findings(_topology(sub))
    f = next(f for f in findings if f.rule_id == "AZ-COST-003")
    assert "VpnGw2" in f.recommendation
    # saving = VpnGw3 (912.50) - VpnGw2 (357.70)
    assert f.est_monthly_cost_usd is not None
    assert abs(f.est_monthly_cost_usd - 554.80) < 0.01


def test_nat_gateway_without_subnets_emits_cost_004():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        nat_gateways=[
            AzureNatGateway(
                id="nat-1",
                name="nat-unused",
                location="eastus",
                resource_group="rg",
                associated_subnet_ids=[],
            )
        ],
    )
    findings = generate_finops_findings(_topology(sub))
    assert "AZ-COST-004" in _rule_ids(findings)


def test_blocked_subscription_produces_no_findings():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        discovery_blocked=True,
        public_ips=[AzurePublicIP(id="pip-1", name="pip", location="eastus", resource_group="rg")],
    )
    assert generate_finops_findings(_topology(sub)) == []
