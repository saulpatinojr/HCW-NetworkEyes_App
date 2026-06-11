"""Unit tests for the topology pattern classifier."""

from cna.core.topology_schema import (
    AzureFirewall,
    AzureSubnet,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVHub,
    AzureVWan,
    VNet,
    VNetPeering,
)
from cna.modules.network.analysis import classify_topology

SUB = "00000000-0000-0000-0000-000000000001"


def _vnet(name: str, peerings: list[VNetPeering] | None = None, subnets=None) -> VNet:
    return VNet(
        id=f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/{name}",
        name=name,
        location="eastus",
        resource_group="rg",
        subscription_id=SUB,
        peerings=peerings or [],
        subnets=subnets or [],
    )


def _peering(name: str, remote_id: str, **flags) -> VNetPeering:
    return VNetPeering(
        id=f"peering-{name}",
        name=name,
        remote_vnet_id=remote_id,
        remote_subscription_id=SUB,
        peering_state="Connected",
        allow_forwarded_traffic=flags.get("allow_forwarded_traffic", False),
        allow_gateway_transit=flags.get("allow_gateway_transit", False),
        use_remote_gateways=flags.get("use_remote_gateways", False),
    )


def _topology(subs: list[AzureSubscriptionTopology]) -> AzureTopology:
    return AzureTopology(engagement_id="ENG-001", tenant_id="tenant", subscriptions=subs)


def test_isolated_when_no_peerings():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB, tenant_id="tenant", vnets=[_vnet("vnet-a"), _vnet("vnet-b")]
    )
    result = classify_topology(_topology([sub]))
    assert result.pattern == "isolated"
    assert result.hub_vnet_ids == []


def test_hub_spoke_from_gateway_transit():
    hub = _vnet("hub")
    spoke = _vnet(
        "spoke",
        peerings=[_peering("spoke-to-hub", hub.id, use_remote_gateways=True)],
    )
    hub.peerings = [_peering("hub-to-spoke", spoke.id, allow_gateway_transit=True)]
    sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="tenant", vnets=[hub, spoke])
    result = classify_topology(_topology([sub]))
    assert result.pattern == "hub_spoke"
    assert hub.id in result.hub_vnet_ids
    assert spoke.id in result.spoke_vnet_ids


def test_hub_identified_by_firewall_subnet():
    fw_subnet = AzureSubnet(
        id=f"/subscriptions/{SUB}/.../virtualNetworks/hub/subnets/AzureFirewallSubnet",
        name="AzureFirewallSubnet",
        address_prefix="10.0.1.0/26",
    )
    hub = _vnet("hub", subnets=[fw_subnet])
    spoke = _vnet("spoke", peerings=[_peering("spoke-to-hub", hub.id)])
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        vnets=[hub, spoke],
        firewalls=[
            AzureFirewall(
                id="fw-1",
                name="fw-1",
                location="eastus",
                resource_group="rg",
                sku_tier="Standard",
                subnet_id=fw_subnet.id,
            )
        ],
    )
    result = classify_topology(_topology([sub]))
    assert result.pattern == "hub_spoke"
    assert result.hub_vnet_ids == [hub.id]


def test_mesh_when_peered_without_hub():
    a = _vnet("vnet-a")
    b = _vnet("vnet-b")
    a.peerings = [_peering("a-to-b", b.id)]
    b.peerings = [_peering("b-to-a", a.id)]
    sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="tenant", vnets=[a, b])
    result = classify_topology(_topology([sub]))
    assert result.pattern == "mesh"


def test_vwan_takes_precedence():
    vhub = AzureVHub(
        id="vhub-1",
        name="vhub-1",
        location="eastus",
        resource_group="rg",
        address_prefix="10.100.0.0/23",
        routing_state="Provisioned",
    )
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        vnets=[_vnet("vnet-a")],
        virtual_wans=[
            AzureVWan(id="vwan-1", name="vwan-1", resource_group="rg", sku="Standard", hubs=[vhub])
        ],
    )
    result = classify_topology(_topology([sub]))
    assert result.pattern == "vwan"
    assert result.hub_vnet_ids == ["vhub-1"]


def test_blocked_subscription_is_skipped():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        discovery_blocked=True,
        vnets=[_vnet("vnet-a")],
    )
    result = classify_topology(_topology([sub]))
    assert result.pattern == "isolated"
