"""FinOps signals — AZ-COST-* findings derived from discovery checkpoints.

Pure post-processing over an existing AzureTopology (DD-008: data store
only). Cost figures come from the static estimate table in
azure_network_prices.py — every dollar amount is an ESTIMATE and is
flagged [VERIFY] in finding descriptions per CBTS review policy.

Rule IDs:
  AZ-COST-001 — orphaned (unassociated) public IP
  AZ-COST-002 — idle gateway (zero 24h throughput with connections configured)
  AZ-COST-003 — oversized VPN gateway SKU vs observed 24h peak utilization
  AZ-COST-004 — NAT gateway with no associated subnets
  AZ-COST-005 — Azure Firewall processing zero traffic (cost angle of AZ-NET-009)
"""

from __future__ import annotations

from dataclasses import dataclass

from cna.core.finding_taxonomy import classify_traffic_direction
from cna.core.findings_schema import (
    Finding,
    FindingRecommendation,
    FindingSeverity,
    FindingStatus,
    FrameworkMapping,
    ObservedState,
)
from cna.core.topology_schema import AzureSubscriptionTopology, AzureTopology

R_AZ_COST_ORPHANED_PIP = "AZ-COST-001"
R_AZ_COST_IDLE_GATEWAY = "AZ-COST-002"
R_AZ_COST_OVERSIZED_GATEWAY = "AZ-COST-003"
R_AZ_COST_NAT_GW_NO_SUBNETS = "AZ-COST-004"
R_AZ_COST_FIREWALL_ZERO_TRAFFIC = "AZ-COST-005"

# Downsize suggestion threshold: observed peak utilization below this
# percentage on a SKU with a smaller tier available
_OVERSIZE_UTILIZATION_PCT = 10.0

_FINOPS_FRAMEWORK = [
    FrameworkMapping(
        framework="FinOps Framework",
        pillar="Optimize",
        control="Workload optimization — rightsizing and waste elimination",
    ),
    FrameworkMapping(
        framework="Azure Well-Architected Framework",
        pillar="Cost Optimization",
        control="CO-7 — Optimize component costs",
    ),
]


def _verify(amount: float) -> str:
    """Render a monthly estimate string with the mandatory [VERIFY] flag."""
    return f"Estimated monthly cost: ~${amount:,.2f} USD [VERIFY]"


@dataclass
class _FindingParams:
    rule_id: str
    severity: FindingSeverity
    sub_id: str
    region: str
    resource_id: str
    resource_type: str
    title: str
    fact: str
    evidence_ref: str
    recommendation: str
    est_monthly_cost_usd: float | None
    description: str


def _finding(p: _FindingParams) -> Finding:
    return Finding(
        rule_id=p.rule_id,
        severity=p.severity,
        platform="azure",
        category="FinOps",
        account_id=p.sub_id,
        region=p.region or "Global",
        resource_id=p.resource_id,
        resource_type=p.resource_type,
        title=p.title,
        description=p.description,
        observed_state=ObservedState(fact=p.fact, evidence_ref=p.evidence_ref),
        framework_mappings=list(_FINOPS_FRAMEWORK),
        recommendations=[FindingRecommendation(source="CNA Platform", text=p.recommendation)],
        recommendation=p.recommendation,
        traffic_direction=classify_traffic_direction(p.rule_id, "FinOps", p.resource_type),
        est_monthly_cost_usd=p.est_monthly_cost_usd,
        status=FindingStatus.OPEN,
    )


def _check_orphaned_pips(sub_id: str, sub, prices) -> list[Finding]:
    findings: list[Finding] = []
    for pip in sub.public_ips:
        if pip.associated_resource_type:
            continue
        monthly = (
            prices.PUBLIC_IP_BASIC_MONTHLY
            if pip.sku_name == "Basic"
            else prices.PUBLIC_IP_STANDARD_MONTHLY
        )
        findings.append(
            _finding(
                _FindingParams(
                    rule_id=R_AZ_COST_ORPHANED_PIP,
                    severity=FindingSeverity.LOW,
                    sub_id=sub_id,
                    region=pip.location,
                    resource_id=pip.id,
                    resource_type="Microsoft.Network/publicIPAddresses",
                    title=f"Orphaned public IP '{pip.name}' incurs charges with no workload",
                    fact=(
                        f"Public IP {pip.name} ({pip.sku_name} SKU) in {pip.location} "
                        f"has associated_resource_type=None — it is not attached to "
                        f"any resource."
                    ),
                    evidence_ref=(
                        f"discovery:azure_{sub_id}.public_ips[id={pip.id}].associated_resource_type"
                    ),
                    recommendation=(
                        "Delete the unassociated public IP if no longer needed, or "
                        "document the reservation intent in resource tags. Use Azure "
                        "Policy to alert on orphaned public IPs."
                    ),
                    est_monthly_cost_usd=monthly,
                    description=(
                        f"Public IP '{pip.name}' is billed while unattached. {_verify(monthly)}."
                    ),
                )
            )
        )
    return findings


def _check_gateway_metrics(sub_id: str, gw_by_name: dict, metrics, prices) -> list[Finding]:
    findings: list[Finding] = []
    for gm in metrics.gateway_metrics:
        gw = gw_by_name.get(gm.gateway_name)
        sku = gw.sku_name if gw else ""
        monthly = prices.gateway_monthly(gm.gateway_type, sku) if gw else None

        ingress = gm.ingress_bytes_24h or 0
        egress = gm.egress_bytes_24h or 0
        if gw and ingress == 0 and egress == 0:
            findings.append(
                _finding(
                    _FindingParams(
                        rule_id=R_AZ_COST_IDLE_GATEWAY,
                        severity=FindingSeverity.MEDIUM,
                        sub_id=sub_id,
                        region=gw.location,
                        resource_id=gw.id,
                        resource_type="Microsoft.Network/virtualNetworkGateways",
                        title=(
                            f"Gateway '{gm.gateway_name}' billed but moved zero traffic in 24 hours"
                        ),
                        fact=(
                            f"{gm.gateway_type} gateway {gm.gateway_name} "
                            f"(SKU: {sku or 'unknown'}) recorded 0 ingress and 0 "
                            f"egress bytes over the 24-hour metric window."
                        ),
                        evidence_ref=(
                            f"discovery:azure_{sub_id}.network_metrics"
                            f".gateway_metrics[name={gm.gateway_name}]"
                        ),
                        recommendation=(
                            "Confirm the gateway is still required. If tunnels are "
                            "unused, decommission the gateway and its public IPs. "
                            "If traffic is expected, investigate tunnel and routing "
                            "health."
                        ),
                        est_monthly_cost_usd=monthly,
                        description=(
                            f"Idle gateway continues to accrue hourly charges. "
                            f"{_verify(monthly) if monthly else 'Monthly cost depends on SKU [VERIFY]'}."
                        ),
                    )
                )
            )

        if (
            gw
            and gm.gateway_type == "Vpn"
            and gm.utilization_pct is not None
            and 0 < gm.utilization_pct < _OVERSIZE_UTILIZATION_PCT
        ):
            smaller = prices.next_smaller_vpn_sku(sku)
            if smaller:
                current_cost = prices.vpn_gateway_monthly(sku)
                smaller_cost = prices.vpn_gateway_monthly(smaller)
                saving = current_cost - smaller_cost if current_cost and smaller_cost else None
                findings.append(
                    _finding(
                        _FindingParams(
                            rule_id=R_AZ_COST_OVERSIZED_GATEWAY,
                            severity=FindingSeverity.LOW,
                            sub_id=sub_id,
                            region=gw.location,
                            resource_id=gw.id,
                            resource_type="Microsoft.Network/virtualNetworkGateways",
                            title=(
                                f"VPN gateway '{gm.gateway_name}' SKU appears "
                                f"oversized for observed traffic"
                            ),
                            fact=(
                                f"VPN gateway {gm.gateway_name} (SKU: {sku}) peaked "
                                f"at {gm.utilization_pct:.1f}% of provisioned "
                                f"bandwidth over the 24-hour metric window."
                            ),
                            evidence_ref=(
                                f"discovery:azure_{sub_id}.network_metrics"
                                f".gateway_metrics[name={gm.gateway_name}]"
                                f".utilization_pct"
                            ),
                            recommendation=(
                                f"Evaluate resizing from {sku} to {smaller} after "
                                f"reviewing a longer utilization window (30+ days) "
                                f"and planned growth. Gateway resize causes brief "
                                f"connectivity interruption — schedule a window."
                            ),
                            est_monthly_cost_usd=saving,
                            description=(
                                f"Downsizing {sku} → {smaller} would reduce spend. "
                                f"{f'Estimated monthly saving: ~${saving:.2f} USD [VERIFY]' if saving else 'Saving depends on SKU pricing [VERIFY]'}."
                            ),
                        )
                    )
                )
    return findings


def _check_firewall_metrics(sub_id: str, fw_by_name: dict, metrics) -> list[Finding]:
    from cna.modules.network.analysis.azure_network_prices import FIREWALL_MONTHLY

    findings: list[Finding] = []
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
        monthly = FIREWALL_MONTHLY.get(tier)
        findings.append(
            _finding(
                _FindingParams(
                    rule_id=R_AZ_COST_FIREWALL_ZERO_TRAFFIC,
                    severity=FindingSeverity.MEDIUM,
                    sub_id=sub_id,
                    region=fw.location if fw else "Global",
                    resource_id=fw.id if fw else fm.firewall_name,
                    resource_type="Microsoft.Network/azureFirewalls",
                    title=(
                        f"Azure Firewall '{fm.firewall_name}' billed while processing zero traffic"
                    ),
                    fact=(
                        f"Azure Firewall {fm.firewall_name} ({tier} tier) recorded "
                        f"0 network, application, and NAT rule hits over the "
                        f"24-hour metric window."
                    ),
                    evidence_ref=(
                        f"discovery:azure_{sub_id}.network_metrics"
                        f".firewall_metrics[name={fm.firewall_name}]"
                    ),
                    recommendation=(
                        "Verify routing actually sends traffic through this "
                        "firewall (see AZ-NET-009). If the firewall is genuinely "
                        "unused, decommission it; if it protects intermittent "
                        "workloads, consider Firewall Basic or stop/start "
                        "automation."
                    ),
                    est_monthly_cost_usd=monthly,
                    description=(
                        f"A deployed firewall accrues hourly charges regardless of "
                        f"traffic. {_verify(monthly) if monthly else 'Monthly cost depends on tier [VERIFY]'}."
                    ),
                )
            )
        )
    return findings


def _check_idle_nat_gateways(sub_id: str, sub) -> list[Finding]:
    from cna.modules.network.analysis.azure_network_prices import NAT_GATEWAY_MONTHLY

    findings: list[Finding] = []
    for nat in sub.nat_gateways:
        if nat.associated_subnet_ids:
            continue
        findings.append(
            _finding(
                _FindingParams(
                    rule_id=R_AZ_COST_NAT_GW_NO_SUBNETS,
                    severity=FindingSeverity.LOW,
                    sub_id=sub_id,
                    region=nat.location,
                    resource_id=nat.id,
                    resource_type="Microsoft.Network/natGateways",
                    title=f"NAT gateway '{nat.name}' has no associated subnets",
                    fact=(
                        f"NAT gateway {nat.name} in {nat.location} has "
                        f"associated_subnet_ids=[] — no subnet routes outbound "
                        f"traffic through it."
                    ),
                    evidence_ref=(
                        f"discovery:azure_{sub_id}.nat_gateways[id={nat.id}].associated_subnet_ids"
                    ),
                    recommendation=(
                        "Associate the NAT gateway with the subnets that need "
                        "predictable outbound SNAT, or delete it (and its public "
                        "IPs) if it is no longer required."
                    ),
                    est_monthly_cost_usd=NAT_GATEWAY_MONTHLY,
                    description=(
                        f"An unattached NAT gateway is billed hourly while providing "
                        f"no egress path. {_verify(NAT_GATEWAY_MONTHLY)}."
                    ),
                )
            )
        )
    return findings


def _analyze_subscription(sub: AzureSubscriptionTopology) -> list[Finding]:
    from cna.modules.network.analysis import azure_network_prices as prices

    sub_id = sub.subscription_id
    findings: list[Finding] = []

    findings.extend(_check_orphaned_pips(sub_id, sub, prices))

    if sub.network_metrics:
        gw_by_name = {gw.name: gw for gw in sub.virtual_network_gateways}
        findings.extend(_check_gateway_metrics(sub_id, gw_by_name, sub.network_metrics, prices))
        fw_by_name = {fw.name: fw for fw in sub.firewalls}
        findings.extend(_check_firewall_metrics(sub_id, fw_by_name, sub.network_metrics))

    findings.extend(_check_idle_nat_gateways(sub_id, sub))

    return findings


def generate_finops_findings(topology: AzureTopology) -> list[Finding]:
    """Generate AZ-COST-* findings for every unblocked subscription.

    Pure function — does not write to any store, does not deduplicate
    across runs (rule_id + resource_id remain stable dedup keys).
    """
    findings: list[Finding] = []
    for sub in topology.subscriptions:
        if sub.discovery_blocked:
            continue
        findings.extend(_analyze_subscription(sub))
    return findings
