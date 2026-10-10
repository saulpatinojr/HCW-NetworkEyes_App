"""Azure BC/DR rules ``AZ-BCDR-001..007``.

``001..005`` register the generators of ``cna.modules.network.analysis.bcdr_signals`` (their
findings pass through unchanged); ``006`` and ``007`` are the zone-redundancy checks Engine B
carried for Application Gateways and Standard load balancers (plan table 7.B, numbered under
BC/DR rather than ``AZ-NET`` — plan section 22, item 6).

Every ``learn_url`` is ``[VERIFY]`` until the owner confirms it; the framework references are
``[REVIEW REQUIRED]`` compliance claims.
"""

from __future__ import annotations

from collections.abc import Iterator

from cna.ai_engine.azure_rules.registry import Observation, rule
from cna.core.findings_schema import Finding, FindingSeverity
from cna.core.topology.azure import AzureSubscriptionTopology, AzureTopology
from cna.modules.network.analysis.bcdr_signals import (
    BCDR_FRAMEWORK,
    R_AZ_BCDR_FW_NOT_ZONE_REDUNDANT,
    R_AZ_BCDR_GW_NOT_ZONE_REDUNDANT,
    R_AZ_BCDR_SINGLE_ER_GATEWAY,
    R_AZ_BCDR_SINGLE_FIREWALL_SPOF,
    R_AZ_BCDR_VPN_ACTIVE_PASSIVE,
    firewall_not_zone_redundant,
    gateway_not_zone_redundant,
    single_expressroute_gateway,
    single_firewall_spof,
    vpn_gateway_active_passive,
)

R_AZ_BCDR_APPGW_NOT_ZONE_REDUNDANT = "AZ-BCDR-006"
R_AZ_BCDR_LB_NOT_ZONE_REDUNDANT = "AZ-BCDR-007"

_MIN_REDUNDANCY_ZONES = 2
_V2_SKU_MARKER = "_v2"
_SKU_STANDARD = "standard"
_CATEGORY = "BC/DR"

_LEARN = "https://learn.microsoft.com/azure/"
_LEARN_FIREWALL_ZONES = _LEARN + "firewall/deploy-availability-zone-powershell"
_LEARN_VPN_HA = _LEARN + "vpn-gateway/vpn-gateway-highlyavailable"
_LEARN_ER_GATEWAYS = _LEARN + "expressroute/expressroute-about-virtual-network-gateways"
_LEARN_FIREWALL_HUB = _LEARN + "architecture/networking/architecture/hub-spoke"
_LEARN_GATEWAY_ZONES = _LEARN + "vpn-gateway/about-zone-redundant-vnet-gateways"
_LEARN_APPGW_ZONES = _LEARN + "application-gateway/application-gateway-autoscaling-zone-redundant"
_LEARN_LB_ZONES = _LEARN + "reliability/reliability-load-balancer"


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
)
def bcdr_firewall_not_zone_redundant(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return firewall_not_zone_redundant(sub)


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
)
def bcdr_vpn_gateway_active_passive(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return vpn_gateway_active_passive(sub)


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
)
def bcdr_single_expressroute_gateway(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return single_expressroute_gateway(sub)


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
)
def bcdr_single_firewall_spof(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    # Tenant-wide: the registry's deduplication keeps the one finding once.
    return single_firewall_spof(topology)


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
)
def bcdr_gateway_not_zone_redundant(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return gateway_not_zone_redundant(sub)


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
)
def application_gateway_not_zone_redundant(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for agw in sub.application_gateways:
        if _V2_SKU_MARKER not in agw.sku_name.lower():
            continue
        if len(agw.zones) >= _MIN_REDUNDANCY_ZONES:
            continue
        yield Observation(
            resource_id=agw.id,
            resource_type="Microsoft.Network/applicationGateways",
            region=agw.location,
            fact=f"Application Gateway {agw.name} ({agw.sku_name}) in {agw.location} is deployed "
            f"in {len(agw.zones)} availability zone(s).",
            evidence_ref=f"discovery:azure_{sub_id}.application_gateways[id={agw.id}].zones",
            description="A zonal outage interrupts every listener on a gateway that is not spread "
            "across zones.",
            recommendation="Redeploy the v2 gateway with zones=[1,2,3] and a zone-redundant Standard "
            "public IP for its frontend.",
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
)
def load_balancer_not_zone_redundant(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for lb in sub.load_balancers:
        if lb.sku_name.lower() != _SKU_STANDARD:
            continue
        if len(lb.zones) >= _MIN_REDUNDANCY_ZONES:
            continue
        yield Observation(
            resource_id=lb.id,
            resource_type="Microsoft.Network/loadBalancers",
            region=lb.location,
            fact=f"Load balancer {lb.name} ({lb.lb_type}, Standard SKU) in {lb.location} has "
            f"{len(lb.zones)} availability zone(s) on its frontend.",
            evidence_ref=f"discovery:azure_{sub_id}.load_balancers[id={lb.id}].zones",
            description="A zonal outage takes the frontend with it when it is pinned to one zone "
            "or to none.",
            recommendation="Configure the frontend IP as zone-redundant (zones=[1,2,3]) and spread "
            "the backend pool across zones.",
        )
