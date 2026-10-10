"""Unit tests for the future-state model builder and diagram generator (Phase E)."""

import xml.etree.ElementTree as ET

from cna.core.topology_schema import (
    AzureRouteServer,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVHub,
    AzureVirtualNetworkGateway,
    AzureVWan,
    VNet,
    VNetPeering,
)
from cna.diagram_engine.drawio_generator import (
    RECOMMENDED_SUFFIX,
    generate_future_state_topology,
)
from cna.diagram_engine.future_state import build_future_state
from cna.modules.network.analysis import classify_topology

SUB = "00000000-0000-0000-0000-000000000001"


def _vnet(
    name: str, peerings: list[VNetPeering] | None = None, subnets=None, location="eastus"
) -> VNet:
    return VNet(
        id=f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/virtualNetworks/{name}",
        name=name,
        location=location,
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


def _gateway(name: str, active_active: bool = False) -> AzureVirtualNetworkGateway:
    return AzureVirtualNetworkGateway(
        id=f"/subscriptions/{SUB}/resourceGroups/rg/providers/Microsoft.Network/virtualNetworkGateways/{name}",
        name=name,
        location="eastus",
        resource_group="rg",
        gateway_type="Vpn",
        active_active=active_active,
    )


def _topology(subs: list[AzureSubscriptionTopology]) -> AzureTopology:
    return AzureTopology(engagement_id="ENG-001", tenant_id="tenant", subscriptions=subs)


def _mesh_topology() -> AzureTopology:
    a = _vnet("vnet-a")
    b = _vnet("vnet-b")
    a.peerings = [_peering("a-to-b", b.id)]
    b.peerings = [_peering("b-to-a", a.id)]
    sub = AzureSubscriptionTopology(subscription_id=SUB, tenant_id="tenant", vnets=[a, b])
    return _topology([sub])


def _hub_spoke_topology(with_route_server: bool = False) -> AzureTopology:
    hub = _vnet("hub")
    spoke = _vnet("spoke", peerings=[_peering("spoke-to-hub", hub.id, use_remote_gateways=True)])
    hub.peerings = [_peering("hub-to-spoke", spoke.id, allow_gateway_transit=True)]
    route_servers = []
    if with_route_server:
        route_servers = [
            AzureRouteServer(
                id="rs-1",
                name="rs-1",
                location="eastus",
                resource_group="rg",
                vnet_id=hub.id,
            )
        ]
    sub = AzureSubscriptionTopology(
        subscription_id=SUB,
        tenant_id="tenant",
        vnets=[hub, spoke],
        virtual_network_gateways=[_gateway("gw-1", active_active=False)],
        route_servers=route_servers,
    )
    return _topology([sub])


# ── Builder tests ──────────────────────────────────────────────────────────


def test_mesh_recommends_hub_spoke_adoption():
    topology = _mesh_topology()
    classification = classify_topology(topology)
    assert classification.pattern == "mesh"

    future = build_future_state(topology, classification)
    assert future.target_pattern == "hub_spoke"
    assert len(future.hubs) == 1
    assert future.hubs[0].is_new is True
    # Synthesized hub hosts firewall + gateway + route server
    kinds = {c.kind for c in future.hub_components}
    assert kinds == {"firewall", "gateway", "route_server"}
    assert all(c.is_new for c in future.hub_components)
    # All existing VNets become spokes
    assert len(future.spokes) == 2
    change_types = {c.change_type for c in future.changes}
    assert "adopt_hub_spoke" in change_types
    assert "add_route_server" in change_types
    adopt = next(c for c in future.changes if c.change_type == "adopt_hub_spoke")
    assert adopt.prerequisites
    assert len(adopt.affected_resources) == 2


def test_isolated_recommends_hub_spoke_adoption():
    sub = AzureSubscriptionTopology(
        subscription_id=SUB, tenant_id="tenant", vnets=[_vnet("vnet-a")]
    )
    topology = _topology([sub])
    classification = classify_topology(topology)
    assert classification.pattern == "isolated"

    future = build_future_state(topology, classification)
    assert future.target_pattern == "hub_spoke"
    assert future.hubs[0].is_new is True


def test_hub_spoke_without_route_server_recommends_one():
    topology = _hub_spoke_topology(with_route_server=False)
    classification = classify_topology(topology)
    assert classification.pattern == "hub_spoke"

    future = build_future_state(topology, classification)
    assert future.target_pattern == "hub_spoke"
    # Existing hub is kept, not net-new
    assert future.hubs and future.hubs[0].is_new is False
    rs_nodes = [c for c in future.hub_components if c.kind == "route_server"]
    assert len(rs_nodes) == 1 and rs_nodes[0].is_new is True
    change_types = {c.change_type for c in future.changes}
    assert "add_route_server" in change_types
    # Active-passive VPN gateway triggers active-active recommendation
    assert "enable_active_active_gateways" in change_types


def test_hub_spoke_with_route_server_skips_recommendation():
    topology = _hub_spoke_topology(with_route_server=True)
    classification = classify_topology(topology)
    future = build_future_state(topology, classification)
    change_types = {c.change_type for c in future.changes}
    assert "add_route_server" not in change_types


def test_multi_region_hub_spoke_recommends_vwan_evaluation():
    topology = _hub_spoke_topology()
    topology.subscriptions[0].vnets.append(_vnet("vnet-west", location="westus2"))
    classification = classify_topology(topology)
    future = build_future_state(topology, classification)
    change_types = {c.change_type for c in future.changes}
    assert "consider_vwan_migration" in change_types


def test_vwan_refinements_secure_hub_and_routing_intent():
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
    topology = _topology([sub])
    classification = classify_topology(topology)
    assert classification.pattern == "vwan"

    future = build_future_state(topology, classification)
    assert future.target_pattern == "vwan"
    change_types = {c.change_type for c in future.changes}
    assert "secure_vwan_hub" in change_types
    assert "adopt_routing_intent" in change_types
    fw_nodes = [c for c in future.hub_components if c.kind == "firewall"]
    assert fw_nodes and fw_nodes[0].is_new is True


# ── Diagram XML tests ──────────────────────────────────────────────────────


def test_future_state_xml_is_well_formed_for_mesh():
    topology = _mesh_topology()
    classification = classify_topology(topology)
    xml = generate_future_state_topology(topology, classification)
    root = ET.fromstring(xml)  # noqa: S314 — internal XML
    assert root.tag == "mxfile"
    assert "Future State Topology" in xml


def test_future_state_xml_marks_recommended_resources():
    topology = _hub_spoke_topology(with_route_server=False)
    classification = classify_topology(topology)
    xml = generate_future_state_topology(topology, classification)
    ET.fromstring(xml)  # noqa: S314 — well-formedness gate
    # Net-new route server carries the dashed bright-teal treatment + suffix
    assert "strokeColor=#00E9BB" in xml
    assert "dashed=1" in xml
    assert RECOMMENDED_SUFFIX in xml


def test_future_state_xml_handles_empty_topology():
    topology = _topology([AzureSubscriptionTopology(subscription_id=SUB, tenant_id="tenant")])
    classification = classify_topology(topology)
    xml = generate_future_state_topology(topology, classification)
    ET.fromstring(xml)  # noqa: S314
    assert "(empty)" in xml
