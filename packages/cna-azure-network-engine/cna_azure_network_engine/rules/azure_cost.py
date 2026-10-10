"""Azure FinOps rules ``AZ-COST-001..005``.

The facts are the monorepo's ``finops_signals`` observations; the static price estimates are
not part of the engine (the downstream lab edition makes no price claims, and the monorepo
annotates ``est_monthly_cost_usd`` on its own findings from its price table). ``002``, ``003``
and ``005`` read 24-hour metrics and are live-only; they surface in ``unknowns`` whenever no
collector ran.

Every ``learn_url`` is ``[VERIFY]`` until the owner confirms it; the framework references are
``[REVIEW REQUIRED]`` compliance claims.
"""

from __future__ import annotations

from collections.abc import Iterator

from cna_azure_network_engine.findings.schema import FindingSeverity
from cna_azure_network_engine.model.azure import AzureSubscriptionTopology, AzureTopology
from cna_azure_network_engine.rules.frameworks import FINOPS_FRAMEWORK
from cna_azure_network_engine.rules.registry import Observation, rule

R_AZ_COST_ORPHANED_PIP = "AZ-COST-001"
R_AZ_COST_IDLE_GATEWAY = "AZ-COST-002"
R_AZ_COST_OVERSIZED_GATEWAY = "AZ-COST-003"
R_AZ_COST_NAT_GW_NO_SUBNETS = "AZ-COST-004"
R_AZ_COST_FIREWALL_ZERO_TRAFFIC = "AZ-COST-005"

_CATEGORY = "FinOps"
T_PIP = "Microsoft.Network/publicIPAddresses"
T_GATEWAY = "Microsoft.Network/virtualNetworkGateways"
T_NAT = "Microsoft.Network/natGateways"
T_FIREWALL = "Microsoft.Network/azureFirewalls"
_GATEWAY_TYPE_VPN = "Vpn"
# Downsize suggestion threshold: observed peak utilization below this percentage on a SKU
# with a smaller tier available.
_OVERSIZE_UTILIZATION_PCT = 10.0
# VPN gateway SKU ladder (Generation 2 names); the AZ variants map onto the same rungs.
_VPN_SKU_LADDER: tuple[str, ...] = ("VpnGw1", "VpnGw2", "VpnGw3", "VpnGw4", "VpnGw5")

_LEARN = "https://learn.microsoft.com/azure/"
_LEARN_PIP = _LEARN + "virtual-network/ip-services/public-ip-addresses"
_LEARN_VPN_GW_SKUS = _LEARN + "vpn-gateway/about-gateway-skus"
_LEARN_NAT = _LEARN + "nat-gateway/nat-overview"
_LEARN_FIREWALL = _LEARN + "firewall/overview"

Rows = Iterator[Observation]


def next_smaller_vpn_sku(sku: str) -> str | None:
    """The next rung down the VPN gateway ladder, keeping an ``AZ`` suffix; None at the bottom."""
    suffix = "AZ" if sku.upper().endswith("AZ") else ""
    base = sku[: -len(suffix)] if suffix else sku
    if base not in _VPN_SKU_LADDER:
        return None
    index = _VPN_SKU_LADDER.index(base)
    return f"{_VPN_SKU_LADDER[index - 1]}{suffix}" if index > 0 else None


@rule(
    id=R_AZ_COST_ORPHANED_PIP,
    title="Orphaned public IP incurs charges with no workload",
    severity=FindingSeverity.LOW,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_PIP,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="export",
    evidence="public_ips[].associated_resource_type",
    remediation="Delete the unassociated public IP if no longer needed, or document the "
    "reservation intent in resource tags. Use Azure Policy to alert on orphaned public IPs.",
    description="A public IP is billed while unattached.",
)
def orphaned_public_ips(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    for pip in sub.public_ips:
        if pip.associated_resource_type or pip.associated_resource_id:
            continue
        yield Observation(
            resource_id=pip.id,
            resource_type=T_PIP,
            region=pip.location,
            title=f"Orphaned public IP '{pip.name}' incurs charges with no workload",
            fact=f"Public IP {pip.name} ({pip.sku_name} SKU) in {pip.location} has "
            f"associated_resource_type=None — it is not attached to any resource.",
            evidence_ref=f"discovery:azure_{sub_id}.public_ips[id={pip.id}].associated_resource_type",
        )


@rule(
    id=R_AZ_COST_IDLE_GATEWAY,
    title="Gateway billed but moved zero traffic in 24 hours",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_VPN_GW_SKUS,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.gateway_metrics[].ingress_bytes_24h / egress_bytes_24h",
    remediation="Confirm the gateway is still required. If tunnels are unused, decommission the "
    "gateway and its public IPs. If traffic is expected, investigate tunnel and routing health.",
    description="An idle gateway continues to accrue hourly charges.",
)
def idle_gateways(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    gw_by_name = {gw.name: gw for gw in sub.virtual_network_gateways}
    for gm in metrics.gateway_metrics:
        gw = gw_by_name.get(gm.gateway_name)
        if gw is None:
            continue
        if (gm.ingress_bytes_24h or 0) != 0 or (gm.egress_bytes_24h or 0) != 0:
            continue
        yield Observation(
            resource_id=gw.id,
            resource_type=T_GATEWAY,
            region=gw.location,
            title=f"Gateway '{gm.gateway_name}' billed but moved zero traffic in 24 hours",
            fact=f"{gm.gateway_type} gateway {gm.gateway_name} (SKU: {gw.sku_name or 'unknown'}) "
            f"recorded 0 ingress and 0 egress bytes over the 24-hour metric window.",
            evidence_ref=f"discovery:azure_{sub_id}.network_metrics"
            f".gateway_metrics[name={gm.gateway_name}]",
        )


@rule(
    id=R_AZ_COST_OVERSIZED_GATEWAY,
    title="VPN gateway SKU is oversized for observed traffic",
    severity=FindingSeverity.LOW,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_VPN_GW_SKUS,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.gateway_metrics[].utilization_pct (gateway_type Vpn)",
    description="A smaller SKU on the same ladder serves the observed peak.",
)
def oversized_vpn_gateways(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    gw_by_name = {gw.name: gw for gw in sub.virtual_network_gateways}
    for gm in metrics.gateway_metrics:
        gw = gw_by_name.get(gm.gateway_name)
        if gw is None or gm.gateway_type != _GATEWAY_TYPE_VPN or gm.utilization_pct is None:
            continue
        if not 0 < gm.utilization_pct < _OVERSIZE_UTILIZATION_PCT:
            continue
        smaller = next_smaller_vpn_sku(gw.sku_name)
        if not smaller:
            continue
        yield Observation(
            resource_id=gw.id,
            resource_type=T_GATEWAY,
            region=gw.location,
            title=f"VPN gateway '{gm.gateway_name}' SKU is oversized for observed traffic",
            fact=f"VPN gateway {gm.gateway_name} (SKU: {gw.sku_name}) peaked at "
            f"{gm.utilization_pct:.1f}% of provisioned bandwidth over the 24-hour metric window.",
            evidence_ref=f"discovery:azure_{sub_id}.network_metrics"
            f".gateway_metrics[name={gm.gateway_name}].utilization_pct",
            recommendation=f"Evaluate resizing from {gw.sku_name} to {smaller} after reviewing a "
            f"longer utilization window (30+ days) and planned growth. Gateway resize causes "
            f"brief connectivity interruption — schedule a window.",
        )


@rule(
    id=R_AZ_COST_NAT_GW_NO_SUBNETS,
    title="NAT gateway has no associated subnets",
    severity=FindingSeverity.LOW,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_NAT,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="export",
    evidence="nat_gateways[].associated_subnet_ids",
    remediation="Associate the NAT gateway with the subnets that need predictable outbound SNAT, "
    "or delete it (and its public IPs) if it is no longer required.",
    description="An unattached NAT gateway is billed hourly while providing no egress path.",
)
def idle_nat_gateways(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    for nat in sub.nat_gateways:
        if nat.associated_subnet_ids:
            continue
        yield Observation(
            resource_id=nat.id,
            resource_type=T_NAT,
            region=nat.location,
            title=f"NAT gateway '{nat.name}' has no associated subnets",
            fact=f"NAT gateway {nat.name} in {nat.location} has associated_subnet_ids=[] — no "
            f"subnet routes outbound traffic through it.",
            evidence_ref=f"discovery:azure_{sub_id}.nat_gateways[id={nat.id}].associated_subnet_ids",
        )


@rule(
    id=R_AZ_COST_FIREWALL_ZERO_TRAFFIC,
    title="Azure Firewall billed while processing zero traffic",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_FIREWALL,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.firewall_metrics[] rule hit counters",
    remediation="Verify routing actually sends traffic through this firewall (see AZ-NET-009). If "
    "the firewall is genuinely unused, decommission it; if it protects intermittent workloads, "
    "consider Firewall Basic or stop/start automation.",
    description="A deployed firewall accrues hourly charges regardless of traffic.",
)
def firewalls_without_traffic(sub: AzureSubscriptionTopology, topology: AzureTopology) -> Rows:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    fw_by_name = {fw.name: fw for fw in sub.firewalls}
    for fm in metrics.firewall_metrics:
        if fm.collection_error:
            continue
        zero_hits = (
            (fm.network_rule_hits_24h or 0) == 0
            and (fm.app_rule_hits_24h or 0) == 0
            and (fm.nat_rule_hits_24h or 0) == 0
        )
        if not zero_hits:
            continue
        fw = fw_by_name.get(fm.firewall_name)
        tier = fw.sku_tier if fw else "Standard"
        yield Observation(
            resource_id=fw.id if fw else fm.firewall_name,
            resource_type=T_FIREWALL,
            region=fw.location if fw else None,
            title=f"Azure Firewall '{fm.firewall_name}' billed while processing zero traffic",
            fact=f"Azure Firewall {fm.firewall_name} ({tier} tier) recorded 0 network, "
            f"application, and NAT rule hits over the 24-hour metric window.",
            evidence_ref=f"discovery:azure_{sub_id}.network_metrics"
            f".firewall_metrics[name={fm.firewall_name}]",
        )
