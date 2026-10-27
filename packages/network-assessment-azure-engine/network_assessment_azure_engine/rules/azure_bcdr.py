"""Azure BC/DR rules ``AZ-BCDR-001..007``.

``001..005`` carry the facts and remediations of the monorepo's ``bcdr_signals`` generators;
``006`` and ``007`` are the zone-redundancy checks Engine B carried for Application Gateways
and Standard load balancers (plan table 7.B, numbered under BC/DR — plan section 22, item 6).
``AZ-BCDR-004`` is tenant-wide: it reads every unblocked subscription and the registry's
deduplication keeps its one finding once.

Every ``learn_url`` is ``[VERIFY]`` until the owner confirms it; the framework references are
``[REVIEW REQUIRED]`` compliance claims.
"""

from __future__ import annotations

from collections.abc import Iterator

from network_assessment_azure_engine.findings.schema import FindingSeverity
from network_assessment_azure_engine.model.azure import AzureSubscriptionTopology, AzureTopology
from network_assessment_azure_engine.rules.frameworks import BCDR_FRAMEWORK
from network_assessment_azure_engine.rules.registry import Observation, rule

R_AZ_BCDR_FW_NOT_ZONE_REDUNDANT = "AZ-BCDR-001"
R_AZ_BCDR_VPN_ACTIVE_PASSIVE = "AZ-BCDR-002"
R_AZ_BCDR_SINGLE_ER_GATEWAY = "AZ-BCDR-003"
R_AZ_BCDR_SINGLE_FIREWALL_SPOF = "AZ-BCDR-004"
R_AZ_BCDR_GW_NOT_ZONE_REDUNDANT = "AZ-BCDR-005"
R_AZ_BCDR_APPGW_NOT_ZONE_REDUNDANT = "AZ-BCDR-006"
R_AZ_BCDR_LB_NOT_ZONE_REDUNDANT = "AZ-BCDR-007"

_MIN_REDUNDANCY_ZONES = 2
_SINGLE_GATEWAY = 1
_GATEWAY_TYPE_VPN = "Vpn"
_GATEWAY_TYPE_EXPRESSROUTE = "ExpressRoute"
_SKU_BASIC = "basic"
_SKU_STANDARD = "standard"
_V2_SKU_MARKER = "_v2"
_CATEGORY = "BC/DR"
T_FIREWALL = "Microsoft.Network/azureFirewalls"
T_GATEWAY = "Microsoft.Network/virtualNetworkGateways"
T_APPGW = "Microsoft.Network/applicationGateways"
T_LB = "Microsoft.Network/loadBalancers"

_LEARN = "https://learn.microsoft.com/azure/"
_LEARN_FIREWALL_ZONES = _LEARN + "firewall/deploy-availability-zone-powershell"
_LEARN_VPN_HA = _LEARN + "vpn-gateway/vpn-gateway-highlyavailable"
_LEARN_ER_GATEWAYS = _LEARN + "expressroute/expressroute-about-virtual-network-gateways"
_LEARN_FIREWALL_HUB = _LEARN + "architecture/networking/architecture/hub-spoke"
_LEARN_GATEWAY_ZONES = _LEARN + "vpn-gateway/about-zone-redundant-vnet-gateways"
_LEARN_APPGW_ZONES = _LEARN + "application-gateway/application-gateway-autoscaling-zone-redundant"
_LEARN_LB_ZONES = _LEARN + "reliability/reliability-load-balancer"

Rows = Iterator[Observation]


@rule(
    id=R_AZ_BCDR_FW_NOT_ZONE_REDUNDANT,
    title="Azure Firewall is not zone-redundant",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_FIREWALL_ZONES,
    frameworks=BCDR_FRAMEWORK,
    applies_to="export",
    evidence="firewalls[].zones",
    remediation="Redeploy the firewall with zones=[1,2,3] and zone-redundant public IPs. A zonal "
    "outage would otherwise interrupt all inspected traffic.",
    description="A single-zone firewall has no SLA protection against zonal failure; every flow "
    "routed through it is interrupted by a zone outage.",
)
def firewall_not_zone_redundant(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    for firewall in sub.firewalls:
        if len(firewall.zones) >= _MIN_REDUNDANCY_ZONES:
            continue
        yield Observation(
            resource_id=firewall.id,
            resource_type=T_FIREWALL,
            region=firewall.location,
            title=f"Azure Firewall '{firewall.name}' is not zone-redundant",
            fact=f"Azure Firewall {firewall.name} ({firewall.sku_tier} tier) in {firewall.location} "
            f"is deployed in {len(firewall.zones)} availability zone(s).",
            evidence_ref=f"discovery:azure_{sub_id}.firewalls[id={firewall.id}].zones",
        )


@rule(
    id=R_AZ_BCDR_VPN_ACTIVE_PASSIVE,
    title="VPN gateway runs in active-passive mode",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_VPN_HA,
    frameworks=BCDR_FRAMEWORK,
    applies_to="export",
    evidence="virtual_network_gateways[].active_active (gateway_type Vpn)",
    remediation="Enable active-active mode (requires a second public IP and VpnGw2+ SKU) and BGP "
    "for automatic failover. Active-standby failover interrupts tunnels for up to 90 seconds on "
    "unplanned events.",
    description="Active-passive VPN gateways interrupt hybrid connectivity during failover and "
    "planned maintenance.",
)
def vpn_gateway_active_passive(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    for gw in sub.virtual_network_gateways:
        if gw.gateway_type != _GATEWAY_TYPE_VPN or gw.active_active:
            continue
        yield Observation(
            resource_id=gw.id,
            resource_type=T_GATEWAY,
            region=gw.location,
            title=f"VPN gateway '{gw.name}' runs in active-passive mode",
            fact=f"VPN gateway {gw.name} (SKU: {gw.sku_name}) has active_active=False.",
            evidence_ref=f"discovery:azure_{sub_id}.virtual_network_gateways[id={gw.id}].active_active",
        )


@rule(
    id=R_AZ_BCDR_SINGLE_ER_GATEWAY,
    title="Single ExpressRoute gateway terminates all circuit connectivity",
    severity=FindingSeverity.HIGH,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_ER_GATEWAYS,
    frameworks=BCDR_FRAMEWORK,
    applies_to="export",
    evidence="express_route_circuits[], virtual_network_gateways[gateway_type=ExpressRoute]",
    remediation="Deploy a second ExpressRoute gateway in another region (or a zone-redundant SKU "
    "plus VPN failover) so a gateway failure does not sever all on-premises connectivity.",
    description="All ExpressRoute private connectivity depends on a single gateway — a regional "
    "or gateway-level failure severs hybrid connectivity.",
)
def single_expressroute_gateway(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    er_gateways = [
        gw for gw in sub.virtual_network_gateways if gw.gateway_type == _GATEWAY_TYPE_EXPRESSROUTE
    ]
    if not sub.express_route_circuits or len(er_gateways) != _SINGLE_GATEWAY:
        return
    gw = er_gateways[0]
    circuit_names = ", ".join(c.name for c in sub.express_route_circuits[:5])
    yield Observation(
        resource_id=gw.id,
        resource_type=T_GATEWAY,
        region=gw.location,
        title=f"Single ExpressRoute gateway '{gw.name}' terminates all circuit connectivity",
        fact=f"Subscription {sub_id} has {len(sub.express_route_circuits)} ExpressRoute circuit(s) "
        f"({circuit_names}) but only one ExpressRoute gateway ({gw.name}, SKU: {gw.sku_name}).",
        evidence_ref=f"discovery:azure_{sub_id}.virtual_network_gateways[gateway_type=ExpressRoute]",
        affected_resources=tuple(c.id for c in sub.express_route_circuits),
    )


@rule(
    id=R_AZ_BCDR_SINGLE_FIREWALL_SPOF,
    title="Azure Firewall is a single point of failure for the tenant footprint",
    severity=FindingSeverity.HIGH,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_FIREWALL_HUB,
    frameworks=BCDR_FRAMEWORK,
    applies_to="export",
    evidence="firewalls[] and vnets[] across every unblocked subscription",
    remediation="Deploy the firewall zone-redundant (zones=[1,2,3]) and define a documented "
    "bypass/failover runbook. For multi-region footprints, evaluate a secured-hub-per-region "
    "design (Azure Firewall in each regional hub or vWAN secured hubs).",
    description="If spoke traffic is force-tunneled through one firewall, a firewall outage halts "
    "east-west and internet-bound traffic for the entire footprint.",
)
def single_firewall_spof(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    # Tenant-wide: evaluated from each subscription; the registry keeps the finding once.
    all_firewalls = []
    vnet_count = 0
    for other in topology.subscriptions:
        if other.discovery_blocked:
            continue
        all_firewalls.extend((other.subscription_id, fw) for fw in other.firewalls)
        vnet_count += len(other.vnets)
    if len(all_firewalls) != 1 or vnet_count <= 1:
        return
    sub_id, firewall = all_firewalls[0]
    if sub_id != sub.subscription_id:
        return  # emitted from the subscription that holds the firewall
    yield Observation(
        resource_id=firewall.id,
        resource_type=T_FIREWALL,
        region=firewall.location,
        title=f"Azure Firewall '{firewall.name}' is a single point of failure for {vnet_count} VNets",
        fact=f"One Azure Firewall ({firewall.name}, {firewall.sku_tier} tier, "
        f"{len(firewall.zones)} zone(s)) was discovered across the tenant while {vnet_count} "
        f"VNets were discovered.",
        evidence_ref=f"discovery:azure_{sub_id}.firewalls[id={firewall.id}]",
    )


@rule(
    id=R_AZ_BCDR_GW_NOT_ZONE_REDUNDANT,
    title="Virtual network gateway is not zone-redundant",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_GATEWAY_ZONES,
    frameworks=BCDR_FRAMEWORK,
    applies_to="export",
    evidence="virtual_network_gateways[].zones (non-Basic SKUs)",
    remediation="Migrate to an AZ SKU (e.g. VpnGw2AZ / ErGw2AZ) deployed with zones=[1,2,3] and "
    "zone-redundant public IPs.",
    description="A zonal failure would take down all tunnels/circuit connectivity terminating on "
    "this gateway.",
)
def gateway_not_zone_redundant(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    for gw in sub.virtual_network_gateways:
        if gw.sku_name.lower() == _SKU_BASIC or len(gw.zones) >= _MIN_REDUNDANCY_ZONES:
            continue
        yield Observation(
            resource_id=gw.id,
            resource_type=T_GATEWAY,
            region=gw.location,
            title=f"Gateway '{gw.name}' is not zone-redundant",
            fact=f"{gw.gateway_type} gateway {gw.name} (SKU: {gw.sku_name}) is deployed in "
            f"{len(gw.zones)} availability zone(s).",
            evidence_ref=f"discovery:azure_{sub_id}.virtual_network_gateways[id={gw.id}].zones",
        )


@rule(
    id=R_AZ_BCDR_APPGW_NOT_ZONE_REDUNDANT,
    title="Application Gateway is not zone-redundant",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_APPGW_ZONES,
    frameworks=BCDR_FRAMEWORK,
    applies_to="export",
    evidence="application_gateways[].zones (v2 SKUs)",
    remediation="Redeploy the v2 gateway with zones=[1,2,3] and a zone-redundant Standard public "
    "IP for its frontend.",
    description="A zonal outage interrupts every listener on a gateway that is not spread across "
    "zones.",
)
def application_gateway_not_zone_redundant(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Rows:
    sub_id = sub.subscription_id
    for agw in sub.application_gateways:
        if _V2_SKU_MARKER not in agw.sku_name.lower():
            continue
        if len(agw.zones) >= _MIN_REDUNDANCY_ZONES:
            continue
        yield Observation(
            resource_id=agw.id,
            resource_type=T_APPGW,
            region=agw.location,
            fact=f"Application Gateway {agw.name} ({agw.sku_name}) in {agw.location} is deployed "
            f"in {len(agw.zones)} availability zone(s).",
            evidence_ref=f"discovery:azure_{sub_id}.application_gateways[id={agw.id}].zones",
        )


@rule(
    id=R_AZ_BCDR_LB_NOT_ZONE_REDUNDANT,
    title="Standard load balancer is not zone-redundant",
    severity=FindingSeverity.LOW,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_LB_ZONES,
    frameworks=BCDR_FRAMEWORK,
    applies_to="export",
    evidence="load_balancers[].zones (Standard SKU)",
    remediation="Configure the frontend IP as zone-redundant (zones=[1,2,3]) and spread the backend "
    "pool across zones.",
    description="A zonal outage takes the frontend with it when it is pinned to one zone or to "
    "none.",
)
def load_balancer_not_zone_redundant(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Rows:
    sub_id = sub.subscription_id
    for lb in sub.load_balancers:
        if lb.sku_name.lower() != _SKU_STANDARD:
            continue
        zones = lb.zones or [z for f in lb.frontend_ip_configs for z in f.zones]
        if len(set(zones)) >= _MIN_REDUNDANCY_ZONES:
            continue
        yield Observation(
            resource_id=lb.id,
            resource_type=T_LB,
            region=lb.location,
            fact=f"Load balancer {lb.name} ({lb.lb_type}, Standard SKU) in {lb.location} has "
            f"{len(set(zones))} availability zone(s) on its frontend.",
            evidence_ref=f"discovery:azure_{sub_id}.load_balancers[id={lb.id}].zones",
        )
