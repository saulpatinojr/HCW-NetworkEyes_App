"""Azure FinOps rules ``AZ-COST-001..005``.

Registers the generators of ``cna.modules.network.analysis.finops_signals``; their findings,
including the ``[VERIFY]``-flagged static price estimates, pass through unchanged.
``AZ-COST-003`` is at version 2: its title read "appears oversized", which the hedge gate
rejects, and now reads "is oversized" over the same observation.

Every ``learn_url`` is ``[VERIFY]`` until the owner confirms it; the framework references are
``[REVIEW REQUIRED]`` compliance claims.
"""

from __future__ import annotations

from cna.ai_engine.azure_rules.registry import rule
from cna.core.findings_schema import Finding, FindingSeverity
from cna.core.topology.azure import AzureSubscriptionTopology, AzureTopology
from cna.modules.network.analysis.finops_signals import (
    FINOPS_FRAMEWORK,
    R_AZ_COST_FIREWALL_ZERO_TRAFFIC,
    R_AZ_COST_IDLE_GATEWAY,
    R_AZ_COST_NAT_GW_NO_SUBNETS,
    R_AZ_COST_ORPHANED_PIP,
    R_AZ_COST_OVERSIZED_GATEWAY,
    firewalls_without_traffic,
    idle_gateways,
    idle_nat_gateways,
    orphaned_public_ips,
    oversized_vpn_gateways,
)

_CATEGORY = "FinOps"

_LEARN = "https://learn.microsoft.com/azure/"
_LEARN_PIP = _LEARN + "virtual-network/ip-services/public-ip-addresses"
_LEARN_VPN_GW_SKUS = _LEARN + "vpn-gateway/about-gateway-skus"
_LEARN_NAT = _LEARN + "nat-gateway/nat-overview"
_LEARN_FIREWALL = _LEARN + "firewall/overview"


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
)
def cost_orphaned_public_ips(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return orphaned_public_ips(sub)


@rule(
    id=R_AZ_COST_IDLE_GATEWAY,
    title="Gateway billed but moved zero traffic in 24 hours",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_VPN_GW_SKUS,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="live-only",
    evidence="network_metrics.gateway_metrics[].ingress_bytes_24h / egress_bytes_24h",
)
def cost_idle_gateways(sub: AzureSubscriptionTopology, topology: AzureTopology) -> list[Finding]:
    return idle_gateways(sub)


@rule(
    id=R_AZ_COST_OVERSIZED_GATEWAY,
    title="VPN gateway SKU is oversized for observed traffic",
    severity=FindingSeverity.LOW,
    category=_CATEGORY,
    version=2,
    learn_url=_LEARN_VPN_GW_SKUS,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="live-only",
    evidence="network_metrics.gateway_metrics[].utilization_pct (gateway_type Vpn)",
)
def cost_oversized_vpn_gateways(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return oversized_vpn_gateways(sub)


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
)
def cost_idle_nat_gateways(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return idle_nat_gateways(sub)


@rule(
    id=R_AZ_COST_FIREWALL_ZERO_TRAFFIC,
    title="Azure Firewall billed while processing zero traffic",
    severity=FindingSeverity.MEDIUM,
    category=_CATEGORY,
    version=1,
    learn_url=_LEARN_FIREWALL,
    frameworks=FINOPS_FRAMEWORK,
    applies_to="live-only",
    evidence="network_metrics.firewall_metrics[] rule hit counters",
)
def cost_firewalls_without_traffic(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> list[Finding]:
    return firewalls_without_traffic(sub)
