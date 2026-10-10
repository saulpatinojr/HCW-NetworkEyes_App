"""Topology classifier — derive the tenant network pattern from discovery data.

Pure post-processing over an existing AzureTopology checkpoint
(cna/core/topology_schema.py). No client environment access (DD-008),
no assumptions beyond what the peering flags and resource placement state.

Patterns:
  vwan      — at least one Virtual WAN hub exists
  hub_spoke — one or more hub VNets identified (gateway transit, firewall
              or gateway placement) with peered spokes
  mesh      — peerings exist but no hub could be identified
  isolated  — VNets exist with no peerings (or no VNets at all)
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from cna.core.topology_schema import AzureTopology, VNet

# Subnets whose presence marks a VNet as a connectivity hub
_HUB_SUBNET_NAMES = frozenset({"gatewaysubnet", "azurefirewallsubnet"})


class TopologyClassification(BaseModel):
    """Result of classifying a tenant's Azure network topology."""

    pattern: str  # "mesh" | "hub_spoke" | "vwan" | "isolated"
    hub_vnet_ids: list[str] = Field(default_factory=list)
    spoke_vnet_ids: list[str] = Field(default_factory=list)
    rationale: str = ""


def _is_hub(vnet: VNet, gateway_vnet_ids: set[str], firewall_subnet_ids: set[str]) -> bool:
    """A VNet is a hub if it offers gateway transit, hosts a gateway or
    firewall, or contains a well-known hub infrastructure subnet."""
    if any(p.allow_gateway_transit for p in vnet.peerings):
        return True
    if vnet.id in gateway_vnet_ids:
        return True
    for subnet in vnet.subnets:
        if subnet.name.lower() in _HUB_SUBNET_NAMES:
            return True
        if subnet.id in firewall_subnet_ids:
            return True
    return False


def _collect_topology_indices(
    topology: AzureTopology,
) -> tuple[list[VNet], list[str], set[str], set[str]]:
    """Collect VNets, vhub IDs, gateway VNet IDs and firewall subnet IDs
    from all unblocked subscriptions."""
    vnets: list[VNet] = []
    vhub_ids: list[str] = []
    gateway_vnet_ids: set[str] = set()
    firewall_subnet_ids: set[str] = set()

    for sub in topology.subscriptions:
        if sub.discovery_blocked:
            continue
        vnets.extend(sub.vnets)
        for vwan in sub.virtual_wans:
            vhub_ids.extend(hub.id for hub in vwan.hubs)
        for gw in sub.virtual_network_gateways:
            if gw.subnet_id:
                gateway_vnet_ids.add(gw.subnet_id.rsplit("/subnets/", 1)[0])
        for fw in sub.firewalls:
            if fw.subnet_id:
                firewall_subnet_ids.add(fw.subnet_id)

    return vnets, vhub_ids, gateway_vnet_ids, firewall_subnet_ids


def classify_topology(topology: AzureTopology) -> TopologyClassification:
    """Classify the tenant network pattern from peering flags and placement.

    Deterministic and side-effect free — safe to call repeatedly on the
    same checkpoint.
    """
    vnets, vhub_ids, gateway_vnet_ids, firewall_subnet_ids = _collect_topology_indices(topology)

    # vWAN takes precedence — vhubs are managed hubs by definition
    if vhub_ids:
        spoke_ids = [v.id for v in vnets if v.peerings]
        return TopologyClassification(
            pattern="vwan",
            hub_vnet_ids=vhub_ids,
            spoke_vnet_ids=spoke_ids,
            rationale=(
                f"{len(vhub_ids)} Virtual WAN hub(s) discovered — managed "
                f"hub-and-spoke via vWAN with {len(spoke_ids)} peered VNet(s)."
            ),
        )

    hub_ids = [v.id for v in vnets if _is_hub(v, gateway_vnet_ids, firewall_subnet_ids)]
    hub_id_set = set(hub_ids)
    spoke_ids = [
        v.id
        for v in vnets
        if v.id not in hub_id_set
        and any(p.use_remote_gateways or p.remote_vnet_id in hub_id_set for p in v.peerings)
    ]

    if hub_ids and spoke_ids:
        return TopologyClassification(
            pattern="hub_spoke",
            hub_vnet_ids=hub_ids,
            spoke_vnet_ids=spoke_ids,
            rationale=(
                f"{len(hub_ids)} hub VNet(s) identified by gateway transit, "
                f"gateway/firewall placement, or hub infrastructure subnets; "
                f"{len(spoke_ids)} spoke VNet(s) peer to them."
            ),
        )

    any_peerings = any(v.peerings for v in vnets)
    if any_peerings:
        return TopologyClassification(
            pattern="mesh",
            hub_vnet_ids=hub_ids,
            spoke_vnet_ids=[],
            rationale=(
                "VNet peerings exist but no hub/spoke relationship could be "
                "established from gateway-transit flags or hub resource placement."
            ),
        )

    return TopologyClassification(
        pattern="isolated",
        hub_vnet_ids=[],
        spoke_vnet_ids=[],
        rationale=f"{len(vnets)} VNet(s) discovered with no peerings between them.",
    )
