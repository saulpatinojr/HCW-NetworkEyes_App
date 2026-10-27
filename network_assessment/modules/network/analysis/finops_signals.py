"""FinOps signals — AZ-COST-* findings with the monorepo's static cost estimates.

The rules live in the engine package (``network_assessment_azure_engine.rules.azure_cost``,
``AZ-COST-001..005``) and make no price claims. The monorepo keeps the price table
(``azure_network_prices``) and attaches ``est_monthly_cost_usd`` — and the ``[VERIFY]``-flagged
estimate sentence — to its own findings here. ``generate_finops_findings`` evaluates the rules
over a topology and returns the annotated monorepo findings.

Rule IDs:
  AZ-COST-001 — orphaned (unassociated) public IP
  AZ-COST-002 — idle gateway (zero 24h throughput with connections configured)
  AZ-COST-003 — oversized VPN gateway SKU vs observed 24h peak utilization
  AZ-COST-004 — NAT gateway with no associated subnets
  AZ-COST-005 — Azure Firewall processing zero traffic (cost angle of AZ-NET-009)
"""

from __future__ import annotations

from collections.abc import Iterable

from network_assessment.core.findings_schema import Finding
from network_assessment.core.topology.azure import AzureSubscriptionTopology, AzureTopology
from network_assessment.modules.network.analysis import azure_network_prices as prices
from network_assessment_azure_engine.rules import evaluate
from network_assessment_azure_engine.rules.azure_cost import (
    R_AZ_COST_FIREWALL_ZERO_TRAFFIC,
    R_AZ_COST_IDLE_GATEWAY,
    R_AZ_COST_NAT_GW_NO_SUBNETS,
    R_AZ_COST_ORPHANED_PIP,
    R_AZ_COST_OVERSIZED_GATEWAY,
    next_smaller_vpn_sku,
)

__all__ = [
    "R_AZ_COST_FIREWALL_ZERO_TRAFFIC",
    "R_AZ_COST_IDLE_GATEWAY",
    "R_AZ_COST_NAT_GW_NO_SUBNETS",
    "R_AZ_COST_ORPHANED_PIP",
    "R_AZ_COST_OVERSIZED_GATEWAY",
    "attach_cost_estimates",
    "generate_finops_findings",
]

_COST_PREFIX = "AZ-COST-"
_SKU_BASIC = "Basic"


def _verify(amount: float) -> str:
    """Render a monthly estimate string with the mandatory [VERIFY] flag."""
    return f"Estimated monthly cost: ~${amount:,.2f} USD [VERIFY]"


def _subscription(topology: AzureTopology, sub_id: str | None) -> AzureSubscriptionTopology | None:
    return next((s for s in topology.subscriptions if s.subscription_id == sub_id), None)


def _estimate(topology: AzureTopology, finding: Finding) -> tuple[float | None, str | None]:
    """(monthly estimate, sentence) for one AZ-COST finding, from the static price table."""
    sub = _subscription(topology, finding.account_id)
    if sub is None:
        return None, None
    rid = finding.resource_id
    if finding.rule_id == R_AZ_COST_ORPHANED_PIP:
        pip = next((p for p in sub.public_ips if p.id == rid), None)
        if pip is None:
            return None, None
        monthly = (
            prices.PUBLIC_IP_BASIC_MONTHLY
            if pip.sku_name == _SKU_BASIC
            else prices.PUBLIC_IP_STANDARD_MONTHLY
        )
        return monthly, f"Public IP '{pip.name}' is billed while unattached. {_verify(monthly)}."
    if finding.rule_id == R_AZ_COST_NAT_GW_NO_SUBNETS:
        monthly = prices.NAT_GATEWAY_MONTHLY
        return monthly, (
            f"An unattached NAT gateway is billed hourly while providing no egress path. "
            f"{_verify(monthly)}."
        )
    if finding.rule_id == R_AZ_COST_IDLE_GATEWAY:
        gw = next((g for g in sub.virtual_network_gateways if g.id == rid), None)
        monthly = prices.gateway_monthly(gw.gateway_type, gw.sku_name) if gw else None
        return monthly, (
            f"Idle gateway continues to accrue hourly charges. "
            f"{_verify(monthly) if monthly else 'Monthly cost depends on SKU [VERIFY]'}."
        )
    if finding.rule_id == R_AZ_COST_OVERSIZED_GATEWAY:
        gw = next((g for g in sub.virtual_network_gateways if g.id == rid), None)
        if gw is None:
            return None, None
        smaller = next_smaller_vpn_sku(gw.sku_name)
        current_cost = prices.vpn_gateway_monthly(gw.sku_name)
        smaller_cost = prices.vpn_gateway_monthly(smaller) if smaller else None
        saving = current_cost - smaller_cost if current_cost and smaller_cost else None
        return saving, (
            f"Downsizing {gw.sku_name} → {smaller} would reduce spend. "
            f"{f'Estimated monthly saving: ~${saving:.2f} USD [VERIFY]' if saving else 'Saving depends on SKU pricing [VERIFY]'}."
        )
    if finding.rule_id == R_AZ_COST_FIREWALL_ZERO_TRAFFIC:
        fw = next((f for f in sub.firewalls if f.id == rid), None)
        tier = fw.sku_tier if fw else "Standard"
        monthly = prices.FIREWALL_MONTHLY.get(tier)
        return monthly, (
            f"A deployed firewall accrues hourly charges regardless of traffic. "
            f"{_verify(monthly) if monthly else 'Monthly cost depends on tier [VERIFY]'}."
        )
    return None, None


def attach_cost_estimates(topology: AzureTopology, findings: Iterable[Finding]) -> None:
    """Fill ``est_monthly_cost_usd`` and the estimate sentence on every AZ-COST finding, in place."""
    for finding in findings:
        if not (finding.rule_id or "").startswith(_COST_PREFIX):
            continue
        amount, sentence = _estimate(topology, finding)
        if amount is not None:
            finding.est_monthly_cost_usd = amount
        if sentence:
            finding.description = sentence


def generate_finops_findings(topology: AzureTopology) -> list[Finding]:
    """Generate AZ-COST-* findings for every unblocked subscription, with cost estimates (pure)."""
    report = evaluate(topology)
    findings = [
        Finding.from_engine(f)
        for f in report.findings
        if (f.rule_id or "").startswith(_COST_PREFIX)
    ]
    attach_cost_estimates(topology, findings)
    return findings
