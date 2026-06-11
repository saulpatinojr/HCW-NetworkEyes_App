"""Future-state topology model builder — Phase E.

Derives a recommended target topology (hub-spoke or vWAN refinements) from
an existing AzureTopology checkpoint plus its TopologyClassification
(cna/modules/network/analysis/topology_classifier.py). Pure post-processing
over discovered data — no client environment access (DD-008).

Outputs:
  - FutureStateModel    : diagrammable node graph (hubs, hub components,
                          spokes) where net-new resources carry is_new=True
  - FutureStateChange   : human-readable change items with prerequisites,
                          embedded in the model and rendered in chapter 6
                          of the encyclopedia report.

Recommendation logic by classified pattern:
  mesh | isolated — adopt hub-spoke: synthesize a hub VNet hosting an Azure
                    Firewall, GatewaySubnet (VPN/ER gateway) and Route
                    Server; all existing VNets become spokes peered to it.
  hub_spoke       — add Azure Route Server if absent; convert active-passive
                    gateways to active-active; recommend vWAN migration when
                    the estate spans 2+ regions.
  vwan            — refinements only: secured hub (Azure Firewall in hub)
                    and routing intent for private traffic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cna.core.topology_schema import (
    AzureFirewall,
    AzureRouteServer,
    AzureTopology,
    AzureVHub,
    AzureVirtualNetworkGateway,
    VNet,
)
from cna.modules.network.analysis.topology_classifier import TopologyClassification

_MIN_MULTI_REGION_COUNT = 2

# ── Models ─────────────────────────────────────────────────────────────────


class FutureStateChange(BaseModel):
    """One recommended change between current and future state."""

    change_type: str  # e.g. "adopt_hub_spoke" | "add_route_server" | ...
    title: str
    description: str
    prerequisites: list[str] = Field(default_factory=list)
    affected_resources: list[str] = Field(default_factory=list)


class FutureStateNode(BaseModel):
    """A diagrammable node in the future-state topology graph."""

    id: str
    name: str
    # "hub_vnet" | "vhub" | "spoke_vnet" | "firewall" | "route_server" | "gateway"
    kind: str
    location: str | None = None
    is_new: bool = False  # True = recommended (net-new) resource


class FutureStateModel(BaseModel):
    """Recommended target topology derived from the current state."""

    target_pattern: str  # "hub_spoke" | "vwan"
    hubs: list[FutureStateNode] = Field(default_factory=list)
    # Components hosted inside hubs (firewall, gateways, route server)
    hub_components: list[FutureStateNode] = Field(default_factory=list)
    spokes: list[FutureStateNode] = Field(default_factory=list)
    changes: list[FutureStateChange] = Field(default_factory=list)


# ── Helpers ────────────────────────────────────────────────────────────────


def _gather(
    topology: AzureTopology,
) -> tuple[
    list[VNet],
    list[AzureVirtualNetworkGateway],
    list[AzureFirewall],
    list[AzureRouteServer],
    list[AzureVHub],
]:
    """Flatten resources across all non-blocked subscriptions."""
    vnets: list[VNet] = []
    gateways: list[AzureVirtualNetworkGateway] = []
    firewalls: list[AzureFirewall] = []
    route_servers: list[AzureRouteServer] = []
    vhubs: list[AzureVHub] = []
    for sub in topology.subscriptions:
        if sub.discovery_blocked:
            continue
        vnets.extend(sub.vnets)
        gateways.extend(sub.virtual_network_gateways)
        firewalls.extend(sub.firewalls)
        route_servers.extend(sub.route_servers)
        for vwan in sub.virtual_wans:
            vhubs.extend(vwan.hubs)
    return vnets, gateways, firewalls, route_servers, vhubs


def _vnet_node(vnet: VNet, kind: str) -> FutureStateNode:
    return FutureStateNode(id=vnet.id, name=vnet.name, kind=kind, location=vnet.location)


def _regions(vnets: list[VNet]) -> list[str]:
    return sorted({v.location for v in vnets if v.location})


# ── Pattern builders ───────────────────────────────────────────────────────


def _build_hub_spoke_adoption(
    vnets: list[VNet], classification: TopologyClassification
) -> FutureStateModel:
    """mesh / isolated → recommend a synthesized hub-spoke topology."""
    if not vnets:
        # Nothing discovered — no meaningful recommendation to draw.
        return FutureStateModel(target_pattern="hub_spoke")
    regions = _regions(vnets)
    region = regions[0] if regions else None
    hub = FutureStateNode(
        id="future:hub-vnet",
        name="hub-vnet",
        kind="hub_vnet",
        location=region,
        is_new=True,
    )
    components = [
        FutureStateNode(
            id="future:hub-azfw",
            name="Azure Firewall",
            kind="firewall",
            location=region,
            is_new=True,
        ),
        FutureStateNode(
            id="future:hub-gateway",
            name="VPN/ER Gateway (GatewaySubnet)",
            kind="gateway",
            location=region,
            is_new=True,
        ),
        FutureStateNode(
            id="future:hub-route-server",
            name="Azure Route Server",
            kind="route_server",
            location=region,
            is_new=True,
        ),
    ]
    spokes = [_vnet_node(v, "spoke_vnet") for v in vnets]
    changes = [
        FutureStateChange(
            change_type="adopt_hub_spoke",
            title="Adopt a hub-spoke network topology",
            description=(
                f"Current pattern is '{classification.pattern}'. Deploy a dedicated "
                "hub VNet hosting shared connectivity services (Azure Firewall, "
                "GatewaySubnet, Azure Route Server) and re-peer all "
                f"{len(spokes)} existing VNet(s) to the hub as spokes. East-west "
                "traffic is then inspected centrally and direct mesh peerings "
                "can be retired."
            ),
            prerequisites=[
                "Allocate a non-overlapping address space for the hub VNet",
                "Plan UDRs on spoke subnets pointing 0.0.0.0/0 at the hub firewall",
                "Schedule a peering cut-over window per spoke",
            ],
            affected_resources=[v.id for v in vnets],
        ),
        FutureStateChange(
            change_type="add_hub_firewall",
            title="Deploy Azure Firewall in the hub",
            description=(
                "Centralize north-south and east-west inspection in an Azure "
                "Firewall hosted in the hub's AzureFirewallSubnet."
            ),
            prerequisites=["Hub VNet deployed", "Firewall policy authored and reviewed"],
            affected_resources=["future:hub-azfw"],
        ),
        FutureStateChange(
            change_type="add_route_server",
            title="Deploy Azure Route Server in the hub",
            description=(
                "Azure Route Server exchanges BGP routes between the hub gateway, "
                "NVAs, and spokes, removing static UDR maintenance for dynamic "
                "prefixes."
            ),
            prerequisites=["Hub VNet deployed with a dedicated RouteServerSubnet (/27)"],
            affected_resources=["future:hub-route-server"],
        ),
    ]
    return FutureStateModel(
        target_pattern="hub_spoke",
        hubs=[hub],
        hub_components=components,
        spokes=spokes,
        changes=changes,
    )


def _build_hub_spoke_refinements(
    vnets: list[VNet],
    gateways: list[AzureVirtualNetworkGateway],
    route_servers: list[AzureRouteServer],
    classification: TopologyClassification,
) -> FutureStateModel:
    """hub_spoke → keep topology, refine hub services."""
    hub_id_set = set(classification.hub_vnet_ids)
    spoke_id_set = set(classification.spoke_vnet_ids)
    hubs = [_vnet_node(v, "hub_vnet") for v in vnets if v.id in hub_id_set]
    spokes = [_vnet_node(v, "spoke_vnet") for v in vnets if v.id in spoke_id_set]
    components: list[FutureStateNode] = []
    changes: list[FutureStateChange] = []

    for gw in gateways:
        components.append(
            FutureStateNode(id=gw.id, name=gw.name, kind="gateway", location=gw.location)
        )

    if not route_servers:
        region = hubs[0].location if hubs else None
        components.append(
            FutureStateNode(
                id="future:hub-route-server",
                name="Azure Route Server",
                kind="route_server",
                location=region,
                is_new=True,
            )
        )
        changes.append(
            FutureStateChange(
                change_type="add_route_server",
                title="Deploy Azure Route Server in the hub",
                description=(
                    "No Azure Route Server was discovered. Adding one to the hub "
                    "VNet enables dynamic BGP route exchange between gateways, "
                    "NVAs, and spokes, eliminating static UDR maintenance."
                ),
                prerequisites=["Dedicated RouteServerSubnet (/27) available in the hub VNet"],
                affected_resources=list(classification.hub_vnet_ids),
            )
        )

    passive_gws = [gw for gw in gateways if gw.gateway_type == "Vpn" and not gw.active_active]
    if passive_gws:
        changes.append(
            FutureStateChange(
                change_type="enable_active_active_gateways",
                title="Convert VPN gateways to active-active",
                description=(
                    f"{len(passive_gws)} VPN gateway(s) run active-passive — a "
                    "failover event drops tunnels while the standby instance "
                    "activates. Converting to an active-active pair provides "
                    "two simultaneously active tunnel endpoints."
                ),
                prerequisites=[
                    "Second public IP per gateway",
                    "BGP enabled on the gateway and on-premises devices",
                    "On-premises devices configured for two tunnels",
                ],
                affected_resources=[gw.id for gw in passive_gws],
            )
        )

    regions = _regions(vnets)
    if len(regions) >= _MIN_MULTI_REGION_COUNT:
        changes.append(
            FutureStateChange(
                change_type="consider_vwan_migration",
                title="Evaluate migration to Azure Virtual WAN",
                description=(
                    f"The estate spans {len(regions)} regions ({', '.join(regions)}). "
                    "Azure Virtual WAN provides managed hub-to-hub transit, "
                    "any-to-any routing, and simplified branch connectivity "
                    "compared to self-managed multi-region hub-spoke."
                ),
                prerequisites=[
                    "Address-space planning for vWAN hubs (/23 per hub recommended)",
                    "Cost comparison of vWAN hub fees vs. current gateway/firewall spend",
                ],
                affected_resources=list(classification.hub_vnet_ids),
            )
        )

    return FutureStateModel(
        target_pattern="hub_spoke",
        hubs=hubs,
        hub_components=components,
        spokes=spokes,
        changes=changes,
    )


def _build_vwan_refinements(
    vnets: list[VNet],
    vhubs: list[AzureVHub],
    classification: TopologyClassification,
) -> FutureStateModel:
    """vwan → secured-hub and routing-intent refinements."""
    hubs = [FutureStateNode(id=h.id, name=h.name, kind="vhub", location=h.location) for h in vhubs]
    spoke_id_set = set(classification.spoke_vnet_ids)
    spokes = [_vnet_node(v, "spoke_vnet") for v in vnets if v.id in spoke_id_set]
    components: list[FutureStateNode] = []
    changes: list[FutureStateChange] = []

    unsecured = [h for h in vhubs if not h.azure_firewall_id]
    for h in unsecured:
        components.append(
            FutureStateNode(
                id=f"future:{h.name}-azfw",
                name=f"Azure Firewall ({h.name})",
                kind="firewall",
                location=h.location,
                is_new=True,
            )
        )
    if unsecured:
        changes.append(
            FutureStateChange(
                change_type="secure_vwan_hub",
                title="Convert vWAN hub(s) to Secured Virtual Hubs",
                description=(
                    f"{len(unsecured)} of {len(vhubs)} vWAN hub(s) have no Azure "
                    "Firewall. Converting them to Secured Virtual Hubs adds "
                    "managed inspection for traffic transiting the hub."
                ),
                prerequisites=[
                    "Firewall Manager policy authored and assigned",
                    "Firewall SKU sized from observed hub throughput",
                ],
                affected_resources=[h.id for h in unsecured],
            )
        )

    changes.append(
        FutureStateChange(
            change_type="adopt_routing_intent",
            title="Adopt routing intent for private traffic",
            description=(
                "Enable vWAN routing intent so private (VNet-to-VNet and "
                "branch-to-VNet) traffic is steered through the hub firewall "
                "without per-connection static routes."
            ),
            prerequisites=["All hubs secured (Azure Firewall or supported NVA deployed)"],
            affected_resources=[h.id for h in vhubs],
        )
    )

    return FutureStateModel(
        target_pattern="vwan",
        hubs=hubs,
        hub_components=components,
        spokes=spokes,
        changes=changes,
    )


# ── Public API ─────────────────────────────────────────────────────────────


def build_future_state(
    topology: AzureTopology, classification: TopologyClassification
) -> FutureStateModel:
    """Build the recommended future-state model for a classified topology.

    Deterministic and side-effect free — safe to call repeatedly on the
    same checkpoint.
    """
    vnets, gateways, firewalls, route_servers, vhubs = _gather(topology)

    if classification.pattern == "vwan":
        return _build_vwan_refinements(vnets, vhubs, classification)
    if classification.pattern == "hub_spoke":
        return _build_hub_spoke_refinements(vnets, gateways, route_servers, classification)
    # mesh / isolated
    return _build_hub_spoke_adoption(vnets, classification)
