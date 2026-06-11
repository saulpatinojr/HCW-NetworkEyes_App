"""Unit tests for BC/DR AZ-BCDR-* finding generation."""

from cna.core.topology_schema import (
    AzureFirewall,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVirtualNetworkGateway,
    ExpressRouteCircuit,
    VNet,
)
from cna.modules.network.analysis import generate_bcdr_findings

SUB = "00000000-0000-0000-0000-000000000001"


def _topology(*subs: AzureSubscriptionTopology) -> AzureTopology:
    return AzureTopology(engagement_id="ENG-001", tenant_id="tenant", subscriptions=list(subs))


def _vnet(name: str) -> VNet:
    return VNet(
        id=f"vnet-{name}",
        name=name,
        location="eastus",
        resource_group="rg",
        subscription_id=SUB,
    )


def _firewall(name: str, zones: list[str] | None = None) -> AzureFirewall:
    return AzureFirewall(
        id=f"fw-{name}",
        name=name,
        location="eastus",
        resource_group="rg",
        sku_tier="Standard",
        zones=zones or [],
    )


def _rule_ids(findings):
    return {f.rule_id for f in findings}


def test_single_zone_firewall_emits_bcdr_001():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB, tenant_id="tenant", firewalls=[_firewall("fw", zones=["1"])]
    )
    findings = generate_bcdr_findings(_topology(sub))
    assert "AZ-BCDR-001" in _rule_ids(findings)


def test_zone_redundant_firewall_passes_bcdr_001():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        firewalls=[_firewall("fw", zones=["1", "2", "3"])],
    )
    findings = generate_bcdr_findings(_topology(sub))
    assert "AZ-BCDR-001" not in _rule_ids(findings)


def test_active_passive_vpn_gateway_emits_bcdr_002():
    gw = AzureVirtualNetworkGateway(
        id="gw-1",
        name="vpn-gw",
        location="eastus",
        resource_group="rg",
        gateway_type="Vpn",
        active_active=False,
        zones=["1", "2", "3"],
    )
    sub = AzureSubscriptionTopology(
        subscription_id=SUB, tenant_id="tenant", virtual_network_gateways=[gw]
    )
    findings = generate_bcdr_findings(_topology(sub))
    assert "AZ-BCDR-002" in _rule_ids(findings)
    assert "AZ-BCDR-005" not in _rule_ids(findings)  # zone-redundant gateway passes
    f = next(f for f in findings if f.rule_id == "AZ-BCDR-002")
    assert f.traffic_direction == "north_south"
    assert f.framework_mappings


def test_single_er_gateway_with_circuit_emits_bcdr_003():
    er_gw = AzureVirtualNetworkGateway(
        id="ergw-1",
        name="er-gw",
        location="eastus",
        resource_group="rg",
        gateway_type="ExpressRoute",
        sku_name="Standard",
        zones=["1", "2", "3"],
    )
    circuit = ExpressRouteCircuit(
        id="er-1", name="circuit-1", location="eastus", resource_group="rg"
    )
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        virtual_network_gateways=[er_gw],
        express_route_circuits=[circuit],
    )
    findings = generate_bcdr_findings(_topology(sub))
    assert "AZ-BCDR-003" in _rule_ids(findings)
    f = next(f for f in findings if f.rule_id == "AZ-BCDR-003")
    assert f.severity == "high"


def test_single_firewall_spof_emits_bcdr_004():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        vnets=[_vnet("hub"), _vnet("spoke-1"), _vnet("spoke-2")],
        firewalls=[_firewall("fw", zones=["1", "2", "3"])],
    )
    findings = generate_bcdr_findings(_topology(sub))
    assert "AZ-BCDR-004" in _rule_ids(findings)


def test_non_zone_redundant_gateway_emits_bcdr_005():
    gw = AzureVirtualNetworkGateway(
        id="gw-1",
        name="vpn-gw",
        location="eastus",
        resource_group="rg",
        gateway_type="Vpn",
        sku_name="VpnGw2",
        active_active=True,
        zones=[],
    )
    sub = AzureSubscriptionTopology(
        subscription_id=SUB, tenant_id="tenant", virtual_network_gateways=[gw]
    )
    findings = generate_bcdr_findings(_topology(sub))
    assert "AZ-BCDR-005" in _rule_ids(findings)


def test_blocked_subscription_is_skipped():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        discovery_blocked=True,
        firewalls=[_firewall("fw")],
    )
    assert generate_bcdr_findings(_topology(sub)) == []
