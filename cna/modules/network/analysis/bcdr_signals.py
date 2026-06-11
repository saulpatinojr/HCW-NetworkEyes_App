"""BC/DR signals — AZ-BCDR-* resilience findings from discovery checkpoints.

Pure post-processing over an existing AzureTopology (DD-008: data store
only). Kept separate from cna/ai_engine/analysis_engine.py so the rule
engine stays focused on security/network rules; both generators are wired
into the analysis flow where discovery findings are produced.

Rule IDs:
  AZ-BCDR-001 — Azure Firewall not zone-redundant
  AZ-BCDR-002 — VPN gateway in active-passive mode
  AZ-BCDR-003 — single ExpressRoute gateway serving circuit connectivity
  AZ-BCDR-004 — single-firewall SPOF for the whole tenant footprint
  AZ-BCDR-005 — virtual network gateway not zone-redundant
"""

from __future__ import annotations

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

R_AZ_BCDR_FW_NOT_ZONE_REDUNDANT = "AZ-BCDR-001"
R_AZ_BCDR_VPN_ACTIVE_PASSIVE = "AZ-BCDR-002"
R_AZ_BCDR_SINGLE_ER_GATEWAY = "AZ-BCDR-003"
R_AZ_BCDR_SINGLE_FIREWALL_SPOF = "AZ-BCDR-004"
R_AZ_BCDR_GW_NOT_ZONE_REDUNDANT = "AZ-BCDR-005"

_BCDR_FRAMEWORK = [
    FrameworkMapping(
        framework="Azure Well-Architected Framework",
        pillar="Reliability",
        control="RE-5 — Design for redundancy",
    ),
    FrameworkMapping(
        framework="CISA ZTMM v2",
        version="v2",
        pillar="Networks",
        control_id="3.4",
        control_name="Network Resilience",
        alignment="Redundant network components prevent single points of failure",
    ),
]


def _finding(
    *,
    rule_id: str,
    severity: FindingSeverity,
    sub_id: str,
    region: str,
    resource_id: str,
    resource_type: str,
    title: str,
    fact: str,
    evidence_ref: str,
    recommendation: str,
    description: str,
) -> Finding:
    return Finding(
        rule_id=rule_id,
        severity=severity,
        platform="azure",
        category="BC/DR",
        account_id=sub_id,
        region=region or "Global",
        resource_id=resource_id,
        resource_type=resource_type,
        title=title,
        description=description,
        observed_state=ObservedState(fact=fact, evidence_ref=evidence_ref),
        framework_mappings=list(_BCDR_FRAMEWORK),
        recommendations=[FindingRecommendation(source="CNA Platform", text=recommendation)],
        recommendation=recommendation,
        traffic_direction=classify_traffic_direction(rule_id, "BC/DR", resource_type),
        status=FindingStatus.OPEN,
    )


def _analyze_subscription(sub: AzureSubscriptionTopology) -> list[Finding]:
    findings: list[Finding] = []
    sub_id = sub.subscription_id

    # AZ-BCDR-001: firewall not zone-redundant
    for fw in sub.firewalls:
        if len(fw.zones) >= 2:
            continue
        findings.append(
            _finding(
                rule_id=R_AZ_BCDR_FW_NOT_ZONE_REDUNDANT,
                severity=FindingSeverity.MEDIUM,
                sub_id=sub_id,
                region=fw.location,
                resource_id=fw.id,
                resource_type="Microsoft.Network/azureFirewalls",
                title=f"Azure Firewall '{fw.name}' is not zone-redundant",
                fact=(
                    f"Azure Firewall {fw.name} ({fw.sku_tier} tier) in "
                    f"{fw.location} is deployed in {len(fw.zones)} availability "
                    f"zone(s)."
                ),
                evidence_ref=f"discovery:azure_{sub_id}.firewalls[id={fw.id}].zones",
                recommendation=(
                    "Redeploy the firewall with zones=[1,2,3] and zone-redundant "
                    "public IPs. A zonal outage would otherwise interrupt all "
                    "inspected traffic."
                ),
                description=(
                    "A single-zone firewall has no SLA protection against zonal "
                    "failure; every flow routed through it is interrupted by a "
                    "zone outage."
                ),
            )
        )

    er_gateways = [gw for gw in sub.virtual_network_gateways if gw.gateway_type == "ExpressRoute"]

    for gw in sub.virtual_network_gateways:
        # AZ-BCDR-002: VPN gateway active-passive
        if gw.gateway_type == "Vpn" and not gw.active_active:
            findings.append(
                _finding(
                    rule_id=R_AZ_BCDR_VPN_ACTIVE_PASSIVE,
                    severity=FindingSeverity.MEDIUM,
                    sub_id=sub_id,
                    region=gw.location,
                    resource_id=gw.id,
                    resource_type="Microsoft.Network/virtualNetworkGateways",
                    title=f"VPN gateway '{gw.name}' runs in active-passive mode",
                    fact=(f"VPN gateway {gw.name} (SKU: {gw.sku_name}) has active_active=False."),
                    evidence_ref=(
                        f"discovery:azure_{sub_id}"
                        f".virtual_network_gateways[id={gw.id}].active_active"
                    ),
                    recommendation=(
                        "Enable active-active mode (requires a second public IP and "
                        "VpnGw2+ SKU) and BGP for automatic failover. Active-standby "
                        "failover interrupts tunnels for up to 90 seconds on "
                        "unplanned events."
                    ),
                    description=(
                        "Active-passive VPN gateways interrupt hybrid connectivity "
                        "during failover and planned maintenance."
                    ),
                )
            )

        # AZ-BCDR-005: gateway not zone-redundant (non-Basic SKUs)
        if gw.sku_name != "Basic" and len(gw.zones) < 2:
            findings.append(
                _finding(
                    rule_id=R_AZ_BCDR_GW_NOT_ZONE_REDUNDANT,
                    severity=FindingSeverity.MEDIUM,
                    sub_id=sub_id,
                    region=gw.location,
                    resource_id=gw.id,
                    resource_type="Microsoft.Network/virtualNetworkGateways",
                    title=f"Gateway '{gw.name}' is not zone-redundant",
                    fact=(
                        f"{gw.gateway_type} gateway {gw.name} (SKU: {gw.sku_name}) "
                        f"is deployed in {len(gw.zones)} availability zone(s)."
                    ),
                    evidence_ref=(
                        f"discovery:azure_{sub_id}.virtual_network_gateways[id={gw.id}].zones"
                    ),
                    recommendation=(
                        "Migrate to an AZ SKU (e.g. VpnGw2AZ / ErGw2AZ) deployed "
                        "with zones=[1,2,3] and zone-redundant public IPs."
                    ),
                    description=(
                        "A zonal failure would take down all tunnels/circuit "
                        "connectivity terminating on this gateway."
                    ),
                )
            )

    # AZ-BCDR-003: ER circuits present but only one ER gateway terminates them
    if sub.express_route_circuits and len(er_gateways) == 1:
        gw = er_gateways[0]
        circuit_names = ", ".join(c.name for c in sub.express_route_circuits[:5])
        findings.append(
            _finding(
                rule_id=R_AZ_BCDR_SINGLE_ER_GATEWAY,
                severity=FindingSeverity.HIGH,
                sub_id=sub_id,
                region=gw.location,
                resource_id=gw.id,
                resource_type="Microsoft.Network/virtualNetworkGateways",
                title=(
                    f"Single ExpressRoute gateway '{gw.name}' terminates all circuit connectivity"
                ),
                fact=(
                    f"Subscription {sub_id} has "
                    f"{len(sub.express_route_circuits)} ExpressRoute circuit(s) "
                    f"({circuit_names}) but only one ExpressRoute gateway "
                    f"({gw.name}, SKU: {gw.sku_name})."
                ),
                evidence_ref=(
                    f"discovery:azure_{sub_id}.virtual_network_gateways[gateway_type=ExpressRoute]"
                ),
                recommendation=(
                    "Deploy a second ExpressRoute gateway in another region (or a "
                    "zone-redundant SKU plus VPN failover) so a gateway failure "
                    "does not sever all on-premises connectivity."
                ),
                description=(
                    "All ExpressRoute private connectivity depends on a single "
                    "gateway — a regional or gateway-level failure severs hybrid "
                    "connectivity."
                ),
            )
        )

    return findings


def generate_bcdr_findings(topology: AzureTopology) -> list[Finding]:
    """Generate AZ-BCDR-* findings for every unblocked subscription.

    Pure function over the topology checkpoint. Also emits the tenant-wide
    single-firewall SPOF check (AZ-BCDR-004) across subscriptions.
    """
    findings: list[Finding] = []
    all_firewalls = []
    vnet_count = 0
    for sub in topology.subscriptions:
        if sub.discovery_blocked:
            continue
        findings.extend(_analyze_subscription(sub))
        all_firewalls.extend((sub.subscription_id, fw) for fw in sub.firewalls)
        vnet_count += len(sub.vnets)

    # AZ-BCDR-004: a single firewall protecting a multi-VNet footprint
    if len(all_firewalls) == 1 and vnet_count > 1:
        sub_id, fw = all_firewalls[0]
        findings.append(
            _finding(
                rule_id=R_AZ_BCDR_SINGLE_FIREWALL_SPOF,
                severity=FindingSeverity.HIGH,
                sub_id=sub_id,
                region=fw.location,
                resource_id=fw.id,
                resource_type="Microsoft.Network/azureFirewalls",
                title=(
                    f"Azure Firewall '{fw.name}' is a single point of failure "
                    f"for {vnet_count} VNets"
                ),
                fact=(
                    f"One Azure Firewall ({fw.name}, {fw.sku_tier} tier, "
                    f"{len(fw.zones)} zone(s)) was discovered across the tenant "
                    f"while {vnet_count} VNets were discovered."
                ),
                evidence_ref=f"discovery:azure_{sub_id}.firewalls[id={fw.id}]",
                recommendation=(
                    "Deploy the firewall zone-redundant (zones=[1,2,3]) and "
                    "define a documented bypass/failover runbook. For "
                    "multi-region footprints, evaluate a secured-hub-per-region "
                    "design (Azure Firewall in each regional hub or vWAN secured "
                    "hubs)."
                ),
                description=(
                    "If spoke traffic is force-tunneled through one firewall, a "
                    "firewall outage halts east-west and internet-bound traffic "
                    "for the entire footprint."
                ),
            )
        )

    return findings
