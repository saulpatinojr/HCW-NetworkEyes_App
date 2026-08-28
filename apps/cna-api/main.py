"""CNA API — discovery orchestration layer.

Accepts discovery jobs from cna-web, runs the Azure discovery engine in
background tasks, maps the resulting topology to security findings, and writes
everything back to PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import BackgroundTasks, FastAPI, HTTPException
from pydantic import BaseModel

# Ensure the repo root is on the path so `cna` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cna.core.finding_taxonomy import classify_traffic_direction
from cna.core.persistence import EngagementStore
from cna.modules.network.analysis import (
    generate_bcdr_findings,
    generate_finops_findings,
)
from cna.modules.network.discovery.azure_discovery import (
    AzureDiscovery,
    AzureDiscoveryOptions,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cna-api")

_MIN_ZONE_REDUNDANCY = 2
_MIN_NIC_COUNT = 2
_LOG_RETENTION_MIN_DAYS = 90
_GW_HIGH_UTILIZATION_PCT = 80

# The container starts uvicorn with module path "apps.cna-api.main" from /app,
# so only /app is on sys.path — make the API directory importable so the
# absolute `routers.*` imports resolve in both container and local runs.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from routers.chat import router as chat_router  # noqa: E402, I001
from routers.metrics import rebuild_metrics  # noqa: E402
from routers.metrics import router as metrics_router  # noqa: E402
from routers.reports import router as reports_router  # noqa: E402

DATABASE_URL = os.environ.get("DATABASE_URL", "")

if not DATABASE_URL:
    logger.warning(
        "DATABASE_URL is not set — discovery results will NOT be persisted. "
        "Jobs, findings, and metrics writes will be silently skipped until it is configured."
    )

app = FastAPI(title="CNA API", version="0.2.0")
app.include_router(metrics_router)
app.include_router(chat_router)
app.include_router(reports_router)


# ─── DB helpers ───────────────────────────────────────────────────────────────


def _get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)


def _update_job(job_id: str, **kwargs: Any) -> None:
    if not DATABASE_URL:
        return
    sets = ", ".join(f'"{k}" = %s' for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'UPDATE "DiscoveryJob" SET {sets}, "updatedAt" = NOW() WHERE id = %s',  # noqa: S608
                values,
            )
        conn.commit()


def _replace_discovery_findings(
    engagement_id: str, credential_id: str | None, findings: list[dict]
) -> None:
    """Replace discovery findings for a specific credential (subscription sync group).

    On success: delete old non-AI findings for this credential, then insert fresh ones.
    On failure: this function is never called, so old data is preserved.
    """
    if not DATABASE_URL:
        return
    with _get_db() as conn:
        with conn.cursor() as cur:
            if credential_id:
                # Remove stale findings for this subscription — other subscriptions untouched
                cur.execute(
                    'DELETE FROM "Finding" WHERE "engagementId" = %s AND "credentialId" = %s AND "aiGenerated" = false',
                    (engagement_id, credential_id),
                )
            if findings:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO "Finding"
                         (id, "engagementId", "credentialId", title, severity, category,
                          description, recommendation, "aiGenerated",
                          "trafficDirection", region, "resourceType", "estCostImpact",
                          "createdAt", "updatedAt")
                       VALUES %s""",
                    [
                        (
                            str(uuid.uuid4()),
                            engagement_id,
                            credential_id,
                            f["title"],
                            f["severity"],
                            f["category"],
                            f["description"],
                            f.get("recommendation", ""),
                            False,
                            f.get("traffic_direction") or None,
                            f.get("region") or None,
                            f.get("resource_type") or None,
                            f.get("est_cost_impact"),
                            datetime.now(UTC),
                            datetime.now(UTC),
                        )
                        for f in findings
                    ],
                )
        conn.commit()


def _advance_engagement_status(engagement_id: str) -> None:
    if not DATABASE_URL:
        return
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE "Engagement"
                   SET status = 'DISCOVERY', "updatedAt" = NOW()
                   WHERE id = %s AND status = 'DRAFT'""",
                (engagement_id,),
            )
        conn.commit()


# ─── Topology → Findings mapper ───────────────────────────────────────────────

# Subnets managed by Azure — don't flag missing NSG on these.
_PLATFORM_SUBNETS = {
    "GatewaySubnet",
    "AzureBastionSubnet",
    "AzureFirewallSubnet",
    "AzureFirewallManagementSubnet",
    "RouteServerSubnet",
}


def _check_no_firewall(vnets, firewalls, sub_name):
    if vnets and not firewalls:
        return [
            {
                "title": f"No Azure Firewall deployed in '{sub_name}'",
                "severity": "HIGH",
                "category": "Network Security",
                "description": (
                    f"Subscription '{sub_name}' has {len(vnets)} VNet(s) but no Azure Firewall. "
                    "Without a centralized firewall, east-west and north-south traffic is uninspected."
                ),
                "recommendation": (
                    "Deploy Azure Firewall (Standard or Premium) in a hub VNet. "
                    "Route spoke subnets through the firewall via UDRs. "
                    "Enable Threat Intelligence in Deny mode."
                ),
            }
        ]
    return []


def _check_vnet(vnet):
    findings = []
    vnet_name = vnet.get("name", "unknown")
    location = vnet.get("location", "")
    rg = vnet.get("resource_group", "")
    if not vnet.get("ddos_protection_enabled"):
        findings.append(
            {
                "title": f"VNet '{vnet_name}' has no DDoS Protection Plan",
                "severity": "MEDIUM",
                "category": "Network Protection",
                "description": (
                    f"VNet '{vnet_name}' ({location}, RG: {rg}) has no Azure DDoS Protection Plan. "
                    "Basic DDoS protection lacks adaptive tuning and rapid response SLA."
                ),
                "recommendation": (
                    "Attach a DDoS Protection Plan to VNets hosting public-facing workloads, "
                    "especially those with App Gateways or public IPs."
                ),
            }
        )
    dns_servers = vnet.get("dns_servers", [])
    if dns_servers:
        non_azure = [d for d in dns_servers if d != "168.63.129.16"]
        if non_azure:
            findings.append(
                {
                    "title": f"VNet '{vnet_name}' uses custom DNS servers",
                    "severity": "INFORMATIONAL",
                    "category": "DNS & Name Resolution",
                    "description": (
                        f"VNet '{vnet_name}' ({location}) uses custom DNS servers: "
                        f"{', '.join(non_azure)}. Verify these forward Private DNS zones correctly "
                        "and are highly available. Misconfigured DNS can break private endpoint resolution."
                    ),
                    "recommendation": (
                        "Ensure custom DNS servers forward Azure Private DNS zones "
                        "(168.63.129.16 as forwarder). Consider Azure DNS Private Resolver "
                        "for a managed, HA solution."
                    ),
                }
            )
    for subnet in vnet.get("subnets", []):
        sname = subnet.get("name", "")
        if sname in _PLATFORM_SUBNETS:
            continue
        if not subnet.get("nsg_id"):
            findings.append(
                {
                    "title": f"Subnet '{sname}' in '{vnet_name}' has no NSG",
                    "severity": "MEDIUM",
                    "category": "Network Segmentation",
                    "description": (
                        f"Subnet '{sname}' (VNet: '{vnet_name}', {location}) has no Network Security "
                        "Group. All intra-VNet traffic to this subnet is permitted by default."
                    ),
                    "recommendation": (
                        "Attach an NSG with least-privilege inbound rules. Deny all by default, "
                        "permit only required ports from approved sources. Enable NSG Flow Logs."
                    ),
                }
            )
    for peering in vnet.get("peerings", []):
        if peering.get("allow_gateway_transit") or peering.get("use_remote_gateways"):
            findings.append(
                {
                    "title": f"VNet peering '{peering.get('name', 'unknown')}' allows gateway transit",
                    "severity": "INFORMATIONAL",
                    "category": "Routing & Transit",
                    "description": (
                        f"Peering between '{vnet_name}' and "
                        f"'{peering.get('remote_vnet_name', 'remote VNet')}' has gateway transit "
                        "enabled. Verify this is intentional (hub-spoke) and not a misconfiguration."
                    ),
                    "recommendation": (
                        "Confirm gateway transit is required for hub-spoke architecture. "
                        "Disable on spoke-to-spoke peerings to prevent unintended routing paths."
                    ),
                }
            )
    return findings


def _check_nsg(nsg):
    findings = []
    nsg_name = nsg.get("name", "unknown")
    rules = nsg.get("security_rules", [])
    internet_sources = {"*", "Internet", "0.0.0.0/0"}
    rdp_ssh_ports = {"3389", "22"}
    for rule in rules:
        if rule.get("access") != "Allow":
            continue
        src = rule.get("source_address_prefix", "")
        dst = rule.get("destination_address_prefix", "")
        dport = rule.get("destination_port_range", "")
        proto = rule.get("protocol", "")
        direction = rule.get("direction", "")
        if src in ("*", "Internet", "Any") and dport in ("*", "Any") and proto in ("*", "Any"):
            findings.append(
                {
                    "title": f"NSG '{nsg_name}' has a wildcard allow-all {direction} rule",
                    "severity": "HIGH",
                    "category": "Network Segmentation",
                    "description": (
                        f"NSG '{nsg_name}' rule '{rule.get('name', '?')}' (priority {rule.get('priority', '?')}) "
                        f"allows all {direction} traffic from '{src}' to '{dst}' on all ports. "
                        "This effectively disables network-layer access control."
                    ),
                    "recommendation": (
                        "Remove or narrow the wildcard allow rule. Replace with specific rules "
                        "permitting only required source CIDRs, ports, and protocols. "
                        "Apply least-privilege: deny all by default, allow explicitly."
                    ),
                }
            )
    for rule in rules:
        if rule.get("access") != "Allow" or rule.get("direction") != "Inbound":
            continue
        src = rule.get("source_address_prefix", "")
        ports: set = set()
        if rule.get("destination_port_range"):
            ports.add(rule.get("destination_port_range"))
        ports.update(rule.get("destination_port_ranges", []))
        if src in internet_sources and ports & rdp_ssh_ports:
            exposed = sorted(ports & rdp_ssh_ports)
            findings.append(
                {
                    "title": f"NSG '{nsg_name}' exposes {'RDP' if '3389' in exposed else 'SSH'} to the Internet",
                    "severity": "CRITICAL",
                    "category": "Remote Access",
                    "description": (
                        f"NSG '{nsg_name}' rule '{rule.get('name', '?')}' allows inbound "
                        f"traffic on port(s) {', '.join(exposed)} from the Internet. "
                        "Direct RDP/SSH exposure is a primary attack vector for brute-force and "
                        "ransomware campaigns."
                    ),
                    "recommendation": (
                        "Remove direct RDP/SSH internet exposure immediately. "
                        "Use Azure Bastion for browser-based access, or restrict source to "
                        "specific corporate IP ranges. Consider JIT VM Access via Microsoft Defender."
                    ),
                }
            )
    if not nsg.get("flow_logs_enabled"):
        findings.append(
            {
                "title": f"NSG '{nsg_name}' has no flow logs enabled",
                "severity": "LOW",
                "category": "Monitoring & Visibility",
                "description": (
                    f"NSG '{nsg_name}' does not have Network Watcher flow logs enabled. "
                    "Without flow logs, traffic analysis, threat detection, and forensic "
                    "investigation are severely limited."
                ),
                "recommendation": (
                    "Enable NSG Flow Logs v2 via Azure Network Watcher. "
                    "Configure a 90-day retention policy. Forward logs to a Log Analytics "
                    "workspace and enable Traffic Analytics for visualization."
                ),
            }
        )
    return findings


def _check_route_tables(route_tables):
    findings = []
    for rt in route_tables:
        rt_name = rt.get("name", "unknown")
        for route in rt.get("routes", []):
            if (
                route.get("address_prefix") == "0.0.0.0/0"
                and route.get("next_hop_type") == "Internet"
            ):
                findings.append(
                    {
                        "title": f"Route table '{rt_name}' sends default traffic directly to Internet",
                        "severity": "MEDIUM",
                        "category": "Routing & Transit",
                        "description": (
                            f"Route table '{rt_name}' has a default route (0.0.0.0/0) with next-hop "
                            f"'Internet'. Traffic from associated subnets bypasses centralized firewall "
                            "inspection and flows directly to the Internet."
                        ),
                        "recommendation": (
                            "Change the default route next-hop to the Azure Firewall private IP "
                            "(or NVA) for centralized egress inspection. "
                            "Only use direct Internet next-hop for dedicated egress subnets with explicit "
                            "justification."
                        ),
                    }
                )
        if rt.get("disable_bgp_route_propagation"):
            findings.append(
                {
                    "title": f"Route table '{rt_name}' has BGP route propagation disabled",
                    "severity": "INFORMATIONAL",
                    "category": "Routing & Transit",
                    "description": (
                        f"Route table '{rt_name}' has BGP route propagation disabled. "
                        "On-premises routes learned via VPN/ExpressRoute are not automatically added to "
                        "subnets associated with this table, which may break hybrid connectivity."
                    ),
                    "recommendation": (
                        "Verify this is intentional. If subnets need on-premises connectivity, "
                        "enable BGP route propagation or add explicit static routes for on-premises prefixes."
                    ),
                }
            )
    return findings


def _check_firewalls(firewalls):
    findings = []
    for fw in firewalls:
        fw_name = fw.get("name", "unknown")
        if fw.get("threat_intel_mode", "Alert") != "Deny":
            findings.append(
                {
                    "title": f"Firewall '{fw_name}' threat intelligence not in Deny mode",
                    "severity": "HIGH",
                    "category": "Network Security",
                    "description": (
                        f"Azure Firewall '{fw_name}' threat intelligence mode is "
                        f"'{fw.get('threat_intel_mode', 'Alert')}'. Known-malicious IPs are alerted "
                        "but not blocked, allowing C2 traffic to pass."
                    ),
                    "recommendation": (
                        "Set Threat Intelligence to Deny in the Firewall Policy. "
                        "Review alert logs first to identify legitimate traffic before switching."
                    ),
                }
            )
        zones = fw.get("zones", [])
        if not zones or len(zones) < _MIN_ZONE_REDUNDANCY:
            findings.append(
                {
                    "title": f"Azure Firewall '{fw_name}' is not zone-redundant",
                    "severity": "MEDIUM",
                    "category": "Resilience",
                    "description": (
                        f"Azure Firewall '{fw_name}' is deployed in {len(zones)} availability zone(s). "
                        "A single-zone or no-zone Firewall has no SLA protection against zonal failure."
                    ),
                    "recommendation": (
                        "Redeploy the Firewall with zones=[1,2,3] and a zone-redundant Public IP. "
                        "Use Standard SKU Firewall Policy. This requires a Standard tier Firewall."
                    ),
                }
            )
    return findings


def _check_app_gateways(app_gws):
    findings = []
    for agw in app_gws:
        agw_name = agw.get("name", "unknown")
        if not agw.get("waf_enabled"):
            findings.append(
                {
                    "title": f"Application Gateway '{agw_name}' has WAF disabled",
                    "severity": "HIGH",
                    "category": "Application Security",
                    "description": (
                        f"App Gateway '{agw_name}' is deployed without WAF. "
                        "Without WAF, OWASP Top 10 attacks (SQLi, XSS, request smuggling) are not inspected."
                    ),
                    "recommendation": (
                        "Upgrade to WAF_v2 SKU. Enable WAF in Detection mode first, "
                        "tune false positives, then switch to Prevention with OWASP 3.2 ruleset."
                    ),
                }
            )
        elif agw.get("waf_mode") and agw.get("waf_mode") != "Prevention":
            findings.append(
                {
                    "title": f"Application Gateway '{agw_name}' WAF is in Detection (not Prevention) mode",
                    "severity": "MEDIUM",
                    "category": "Application Security",
                    "description": (
                        f"App Gateway '{agw_name}' has WAF enabled but in Detection mode. "
                        "Attacks are logged but not blocked, providing no actual protection."
                    ),
                    "recommendation": (
                        "After reviewing and tuning Detection mode logs for false positives, "
                        "switch WAF mode to Prevention. Apply OWASP CRS 3.2 or later."
                    ),
                }
            )
        agw_zones = agw.get("zones", [])
        if not agw_zones or len(agw_zones) < _MIN_ZONE_REDUNDANCY:
            findings.append(
                {
                    "title": f"Application Gateway '{agw_name}' is not zone-redundant",
                    "severity": "MEDIUM",
                    "category": "Resilience",
                    "description": (
                        f"App Gateway '{agw_name}' has {len(agw_zones)} availability zone(s). "
                        "A non-zone-redundant App Gateway is a single point of failure for ingress traffic."
                    ),
                    "recommendation": (
                        "Migrate to Application Gateway v2 with zones=[1,2,3] configured. "
                        "Use a zone-redundant frontend public IP (Standard SKU)."
                    ),
                }
            )
    return findings


def _check_load_balancers(load_balancers):
    findings = []
    for lb in load_balancers:
        lb_name = lb.get("name", "unknown")
        lb_zones = lb.get("zones", [])
        if lb.get("sku_name") == "Basic":
            findings.append(
                {
                    "title": f"Load Balancer '{lb_name}' uses Basic SKU",
                    "severity": "MEDIUM",
                    "category": "Resilience",
                    "description": (
                        f"Load Balancer '{lb_name}' uses the Basic SKU which has no SLA, "
                        "no zone redundancy, and does not support HTTPS health probes or "
                        "integration with availability zones."
                    ),
                    "recommendation": (
                        "Upgrade to Standard SKU. Basic LBs are on the retirement path. "
                        "Standard LBs support zone redundancy, secure-by-default (no public access "
                        "without NSG), and HA ports."
                    ),
                }
            )
        elif not lb_zones or len(lb_zones) < _MIN_ZONE_REDUNDANCY:
            findings.append(
                {
                    "title": f"Load Balancer '{lb_name}' is not zone-redundant",
                    "severity": "LOW",
                    "category": "Resilience",
                    "description": (
                        f"Load Balancer '{lb_name}' ({lb.get('lb_type', 'Public')}) "
                        f"has {len(lb_zones)} availability zone(s). "
                        "Frontend IP configurations are not zone-redundant."
                    ),
                    "recommendation": (
                        "Configure the frontend IP as zone-redundant (specify zones=[1,2,3]) "
                        "when using Standard LB. Ensure backend VMs also span multiple zones."
                    ),
                }
            )
    return findings


def _check_vnet_gateway_connections(vnet_gateways):
    findings = []
    for gw in vnet_gateways:
        gw_name = gw.get("name", "unknown")
        if gw.get("gateway_type") != "Vpn":
            continue
        if not gw.get("active_active"):
            findings.append(
                {
                    "title": f"VPN Gateway '{gw_name}' is not in active-active mode",
                    "severity": "MEDIUM",
                    "category": "Resilience",
                    "description": (
                        f"VPN Gateway '{gw_name}' is in active-standby mode. "
                        "Active-standby has a failover time of 10-15 seconds for planned and "
                        "60-90 seconds for unplanned maintenance events."
                    ),
                    "recommendation": (
                        "Enable active-active mode on the VPN Gateway. This requires two public IPs "
                        "and VpnGw2 or higher SKU. Also configure BGP for automatic failover."
                    ),
                }
            )
        for conn in gw.get("connections", []):
            if conn.get("connection_status") not in ("Connected", "Unknown"):
                findings.append(
                    {
                        "title": f"VPN connection '{conn.get('name', '?')}' on gateway '{gw_name}' is not connected",
                        "severity": "HIGH",
                        "category": "Connectivity",
                        "description": (
                            f"Gateway connection '{conn.get('name', '?')}' (type: {conn.get('connection_type', '?')}) "
                            f"has status '{conn.get('connection_status', 'Unknown')}'. "
                            "A disconnected VPN tunnel breaks hybrid connectivity to on-premises."
                        ),
                        "recommendation": (
                            "Investigate the connection status in Azure Portal > VPN Gateways > Connections. "
                            "Check on-premises VPN device logs, verify pre-shared keys and IKE parameters, "
                            "and confirm firewall rules allow UDP 500/4500."
                        ),
                    }
                )
    return findings


def _check_public_ips(public_ips, sub_name):
    findings = []
    unassociated = [p for p in public_ips if not p.get("associated_resource_type")]
    if unassociated:
        findings.append(
            {
                "title": f"{len(unassociated)} unassociated Public IP(s) in '{sub_name}'",
                "severity": "LOW",
                "category": "Cost & Hygiene",
                "description": (
                    f"{len(unassociated)} Public IP(s) are not attached to any resource: "
                    f"{', '.join(p.get('name', '?') for p in unassociated[:5])}. "
                    "Unassociated IPs incur charges and may represent unused or orphaned resources."
                ),
                "recommendation": (
                    "Delete unassociated Public IPs that are no longer needed. "
                    "If reserved for future use, document the intent in resource tags. "
                    "Use Azure Policy to alert on orphaned public IPs."
                ),
            }
        )
    basic_pips = [p for p in public_ips if p.get("sku_name") == "Basic"]
    if basic_pips:
        findings.append(
            {
                "title": f"{len(basic_pips)} Basic SKU Public IP(s) in '{sub_name}'",
                "severity": "MEDIUM",
                "category": "Resilience",
                "description": (
                    f"{len(basic_pips)} Public IP(s) use the Basic SKU: "
                    f"{', '.join(p.get('name', '?') for p in basic_pips[:5])}. "
                    "Basic IPs are open by default, not zone-redundant, and on the retirement path "
                    "(retirement: September 30, 2025)."
                ),
                "recommendation": (
                    "Upgrade all Basic Public IPs to Standard SKU. "
                    "Standard IPs are secure by default (require NSG) and support zone redundancy. "
                    "Follow the migration guide at learn.microsoft.com/azure/virtual-network/ip-services/public-ip-basic-upgrade-guidance."
                ),
            }
        )
    return findings


def _check_bastion(bastion_hosts, vnets, sub_name):
    if not bastion_hosts and vnets:
        return [
            {
                "title": f"No Azure Bastion deployed in '{sub_name}'",
                "severity": "MEDIUM",
                "category": "Remote Access",
                "description": (
                    f"Subscription '{sub_name}' has {len(vnets)} VNet(s) but no Azure Bastion host. "
                    "Without Bastion, secure RDP/SSH access requires either public IPs on VMs or "
                    "complex VPN/JIT configurations."
                ),
                "recommendation": (
                    "Deploy Azure Bastion (Standard SKU) to provide browser-based RDP/SSH "
                    "without exposing VMs to the Internet. Enable tunneling and shareable links "
                    "for additional flexibility."
                ),
            }
        ]
    return []


def _check_private_endpoints(private_endpoints):
    findings = []
    for pe in private_endpoints:
        for sc in pe.get("service_connections", []):
            if sc.get("connection_state") == "Pending":
                findings.append(
                    {
                        "title": f"Private Endpoint '{pe.get('name', '?')}' has a pending connection",
                        "severity": "MEDIUM",
                        "category": "Connectivity",
                        "description": (
                            f"Private Endpoint '{pe.get('name', '?')}' connection to "
                            f"'{sc.get('private_link_service_id', '?').split('/')[-1]}' is in Pending state. "
                            "Traffic to the private service cannot flow until the connection is approved."
                        ),
                        "recommendation": (
                            "Approve the pending private endpoint connection in the target resource's "
                            "Networking > Private endpoint connections blade. "
                            "Verify the request is from an expected subscription and service."
                        ),
                    }
                )
    return findings


def _check_gateway_skus(vnet_gateways):
    findings = []
    for gw in vnet_gateways:
        gw_name = gw.get("name", "unknown")
        sku = gw.get("sku_name", "") or gw.get("sku_tier", "")
        gw_type = gw.get("gateway_type", "Vpn")
        gen = gw.get("generation", "") or ""
        zones = gw.get("zones", [])
        if gw_type == "Vpn" and sku == "Basic":
            findings.append(
                {
                    "title": f"VPN Gateway '{gw_name}' uses Basic SKU — no SLA or zone redundancy",
                    "severity": "HIGH",
                    "category": "Gateway",
                    "description": (
                        f"VPN Gateway '{gw_name}' is deployed with the Basic SKU. "
                        "Basic gateways are limited to 100 Mbps aggregate throughput, "
                        "do not support BGP, active-active configuration, or zone redundancy, "
                        "and carry no Microsoft SLA."
                    ),
                    "recommendation": (
                        "Upgrade to VpnGw2 or higher (Generation 2). "
                        "For zone redundancy, choose a *AZ SKU (e.g., VpnGw2AZ). "
                        "Enable BGP and active-active mode for resilient hybrid connectivity."
                    ),
                }
            )
        if gw_type == "Vpn" and gen and "Generation1" in gen:
            findings.append(
                {
                    "title": f"VPN Gateway '{gw_name}' is Generation 1 — limited throughput ceiling",
                    "severity": "LOW",
                    "category": "Gateway",
                    "description": (
                        f"VPN Gateway '{gw_name}' uses Generation 1 hardware. "
                        "Generation 2 provides up to 100 Gbps aggregate throughput (VpnGw5AZ) "
                        "vs. 1.25 Gbps maximum for Generation 1. "
                        "Throughput caps may become a bottleneck as workloads grow."
                    ),
                    "recommendation": (
                        "Redeploy or resize to a Generation 2 SKU (VpnGw2-VpnGw5 or their AZ variants). "
                        "Generation 2 supports higher throughput at the same or lower cost."
                    ),
                }
            )
        if (
            gw_type == "Vpn"
            and sku not in ("Basic",)
            and (not zones or len(zones) < _MIN_ZONE_REDUNDANCY)
        ):
            findings.append(
                {
                    "title": f"VPN Gateway '{gw_name}' is not zone-redundant",
                    "severity": "MEDIUM",
                    "category": "Gateway",
                    "description": (
                        f"VPN Gateway '{gw_name}' (SKU: {sku}) is not deployed across "
                        "availability zones. A zonal failure would interrupt all "
                        "VPN tunnels and hybrid connectivity."
                    ),
                    "recommendation": (
                        "Migrate to an AZ SKU (e.g., VpnGw2AZ) and deploy with "
                        "zones=[1,2,3]. Also configure a zone-redundant Public IP "
                        "(Standard SKU with zones=[1,2,3])."
                    ),
                }
            )
    return findings


def _check_nva(nva):
    findings = []
    nva_name = nva.get("name", "unknown")
    nics = nva.get("nics", [])
    method = nva.get("identification_method", "")
    if len(nics) < _MIN_NIC_COUNT:
        findings.append(
            {
                "title": f"NVA '{nva_name}' has only {len(nics)} NIC — possible hairpin or misconfiguration",
                "severity": "HIGH",
                "category": "Network Appliances",
                "description": (
                    f"NVA '{nva_name}' was identified as a network virtual appliance but has fewer than 2 NICs. "
                    "Most NGFWs require at least a LAN and a WAN interface to separate inside and outside traffic. "
                    "A single-NIC configuration often indicates a misconfiguration or a hairpin NAT design."
                ),
                "recommendation": (
                    "Verify the intended traffic model. If this NVA should inspect bidirectional traffic, "
                    "add a second NIC on a separate subnet. Review associated UDRs to ensure traffic is "
                    "actually traversing the appliance."
                ),
            }
        )
    mgmt_nics_without_nsg = [n for n in nics if not n.get("nsg_id")]
    if mgmt_nics_without_nsg:
        findings.append(
            {
                "title": f"NVA '{nva_name}': {len(mgmt_nics_without_nsg)} NIC(s) without NSG",
                "severity": "MEDIUM",
                "category": "Network Appliances",
                "description": (
                    f"NVA '{nva_name}' has {len(mgmt_nics_without_nsg)} network interface(s) "
                    "with no Network Security Group attached. Without an NSG, management-plane access "
                    "to the NVA is not filtered at the Azure layer, increasing the blast radius if "
                    "the appliance is compromised."
                ),
                "recommendation": (
                    "Attach an NSG to every NIC of the NVA. The management NIC NSG should restrict "
                    "inbound access to known jump-host IPs and deny all other inbound traffic. "
                    "Never expose the management interface directly to the internet."
                ),
            }
        )
    if method == "ip_forwarding":
        findings.append(
            {
                "title": f"VM '{nva_name}' has IP forwarding enabled — verify intent",
                "severity": "MEDIUM",
                "category": "Network Appliances",
                "description": (
                    f"VM '{nva_name}' has IP forwarding enabled on one or more NICs but does not match "
                    "any known NGFW marketplace publisher. IP forwarding is required for NVAs and routers "
                    "but is a security risk if enabled on general-purpose VMs, as it allows the VM to "
                    "forward traffic it did not originate."
                ),
                "recommendation": (
                    "Confirm this VM is intentionally acting as a router or NVA. If not, disable IP "
                    "forwarding on its NICs in the Azure portal. If it is an NVA, document the vendor, "
                    "version, and licensing and ensure it is under a formal change-management process."
                ),
            }
        )
    return findings


def _check_nvas(nvas, sub_name):
    if not nvas:
        return []
    findings = [
        {
            "title": f"{len(nvas)} Network Virtual Appliance(s) detected in '{sub_name}'",
            "severity": "INFORMATIONAL",
            "category": "Network Appliances",
            "description": (
                f"Subscription '{sub_name}' contains {len(nvas)} NVA(s) "
                f"({', '.join(n.get('name', '?') for n in nvas[:5])}). "
                "NVAs acting as NGFWs are critical chokepoints for East-West and North-South traffic. "
                "Their placement, licensing, and HA configuration must be validated."
            ),
            "recommendation": (
                "Verify each NVA is deployed in an Active/Active or Active/Standby HA pair. "
                "Confirm UDRs route traffic through the NVA in both inbound and outbound directions. "
                "Check that management interfaces are on a dedicated subnet with no default route to the internet."
            ),
        }
    ]
    for nva in nvas:
        findings += _check_nva(nva)
    return findings


def _check_bgp_gateway(bgp, vnet_gateways):
    findings = []
    gw_name = bgp.get("gateway_name", "unknown")
    bgp_enabled = bgp.get("bgp_enabled", False)
    peers = bgp.get("peers", [])
    if not bgp_enabled:
        matching_gw = next((g for g in vnet_gateways if g.get("name") == gw_name), {})
        if bool(matching_gw.get("connections")):
            findings.append(
                {
                    "title": f"VPN Gateway '{gw_name}' has connections but BGP is disabled",
                    "severity": "MEDIUM",
                    "category": "BGP & Routing",
                    "description": (
                        f"VPN Gateway '{gw_name}' has active connections but BGP is not enabled. "
                        "Without BGP, routes must be statically maintained and failover is not automatic. "
                        "This increases operational overhead and risk of routing gaps during maintenance."
                    ),
                    "recommendation": (
                        "Enable BGP on the VPN Gateway and on-premises VPN device. "
                        "Use a private ASN (64512-65534) and configure BGP peer IPs. "
                        "BGP enables dynamic route learning, path selection, and automatic failover "
                        "in active-active configurations."
                    ),
                }
            )
        return findings
    for peer in [p for p in peers if p.get("state") not in ("Connected", "Unknown")]:
        findings.append(
            {
                "title": f"BGP peer {peer.get('peer_ip', '?')} on '{gw_name}' is {peer.get('state', 'Disconnected')}",
                "severity": "HIGH",
                "category": "BGP & Routing",
                "description": (
                    f"BGP peer {peer.get('peer_ip', '?')} (ASN: {peer.get('peer_asn', 'unknown')}) "
                    f"on gateway '{gw_name}' is in state '{peer.get('state', 'Disconnected')}'. "
                    f"Routes received: {peer.get('routes_received', 0)}. "
                    "A disconnected BGP peer means dynamic routes from that peer are withdrawn and "
                    "traffic may black-hole."
                ),
                "recommendation": (
                    "Check BGP session state on the remote peer (on-premises router or remote gateway). "
                    "Verify ASN, peer IP, and BGP timers match. "
                    "Review Azure VPN Gateway diagnostics for IKE and BGP logs."
                ),
            }
        )
    learned_count = bgp.get("learned_routes_count", 0)
    adv_count = bgp.get("advertised_routes_count", 0)
    connected_peers = [p for p in peers if p.get("state") == "Connected"]
    if bgp_enabled and learned_count == 0 and connected_peers:
        findings.append(
            {
                "title": f"VPN Gateway '{gw_name}' has connected BGP peers but no learned routes",
                "severity": "HIGH",
                "category": "BGP & Routing",
                "description": (
                    f"Gateway '{gw_name}' has {len(connected_peers)} connected BGP peer(s) but is not "
                    "learning any routes. This indicates the remote side is not advertising any prefixes, "
                    "which would cause on-premises resources to be unreachable from Azure."
                ),
                "recommendation": (
                    "Verify the on-premises BGP configuration is advertising the correct prefixes to Azure. "
                    "Check for BGP route filters or prefix-lists that may be blocking advertisements. "
                    "Review route policies on the remote device."
                ),
            }
        )
    if bgp_enabled and (learned_count > 0 or adv_count > 0):
        findings.append(
            {
                "title": f"BGP Route Table: '{gw_name}' — {learned_count} learned, {adv_count} advertised",
                "severity": "INFORMATIONAL",
                "category": "BGP & Routing",
                "description": (
                    f"Gateway '{gw_name}' BGP route summary: "
                    f"{learned_count} route(s) learned from peers, {adv_count} route(s) advertised to peers. "
                    + (
                        f"Sample learned prefixes: {', '.join(bgp.get('learned_routes', [])[:5])}."
                        if bgp.get("learned_routes")
                        else ""
                    )
                ),
                "recommendation": (
                    "Review the learned routes to confirm all expected on-premises prefixes are present. "
                    "Verify advertised routes match the intended Azure address spaces. "
                    "Investigate unexpected or missing prefixes."
                ),
            }
        )
    return findings


def _check_observability(obs, vnets, sub_name):
    if not obs:
        return []
    findings = []
    nw_regions = {nw.get("location", "") for nw in obs.get("network_watchers", [])}
    vnet_regions = {v.get("location", "") for v in vnets}
    missing_nw = vnet_regions - nw_regions
    if missing_nw:
        findings.append(
            {
                "title": f"Network Watcher not enabled in {len(missing_nw)} region(s) in '{sub_name}'",
                "severity": "MEDIUM",
                "category": "Observability",
                "description": (
                    f"Azure Network Watcher is not enabled in {len(missing_nw)} region(s) that contain VNets: "
                    f"{', '.join(sorted(missing_nw))}. "
                    "Network Watcher is required for NSG flow logs, Connection Monitor, packet capture, "
                    "and topology visualization."
                ),
                "recommendation": (
                    "Enable Azure Network Watcher in every region where Azure resources are deployed. "
                    "Network Watcher is free and enables critical diagnostics: "
                    "NSG flow logs, Connection Monitor, IP flow verify, and next hop."
                ),
            }
        )
    workspaces = obs.get("log_analytics_workspaces", [])
    if not workspaces and vnets:
        findings.append(
            {
                "title": f"No Log Analytics workspace in '{sub_name}'",
                "severity": "HIGH",
                "category": "Observability",
                "description": (
                    f"Subscription '{sub_name}' has {len(vnets)} VNet(s) but no Log Analytics workspace. "
                    "Without a workspace, NSG flow logs, diagnostic settings, Azure Monitor alerts, "
                    "and Traffic Analytics cannot be centrally collected or queried."
                ),
                "recommendation": (
                    "Create a Log Analytics workspace in this subscription. "
                    "Configure a minimum 90-day retention policy. "
                    "Forward all diagnostic settings (NSGs, firewalls, gateways) to the workspace. "
                    "Enable Traffic Analytics for NSG flow logs."
                ),
            }
        )
    for ws in workspaces:
        ret = ws.get("retention_days", 30)
        if ret < _LOG_RETENTION_MIN_DAYS:
            findings.append(
                {
                    "title": f"Log Analytics workspace '{ws.get('name', 'unknown')}' has short retention ({ret} days)",
                    "severity": "MEDIUM",
                    "category": "Observability",
                    "description": (
                        f"Log Analytics workspace '{ws.get('name', 'unknown')}' retains data for only {ret} days. "
                        "Security investigations, compliance audits, and forensic analysis typically require "
                        "90+ days of log history. NIST 800-53 and CIS recommend at least 90 days online "
                        "retention (1 year for compliance workloads)."
                    ),
                    "recommendation": (
                        "Increase retention to at least 90 days in the workspace "
                        "Settings > Usage and estimated costs > Data Retention. "
                        "For compliance workloads (PCI, HIPAA, SOC 2), set 365 days "
                        "or archive to Azure Storage with immutability policies."
                    ),
                }
            )
    fl_enabled = obs.get("nsg_flow_logs_enabled", 0)
    fl_total = obs.get("nsg_flow_logs_total", 0)
    if fl_total > 0 and fl_enabled < fl_total:
        missing_fl = fl_total - fl_enabled
        findings.append(
            {
                "title": f"{missing_fl} of {fl_total} NSG(s) missing flow logs in '{sub_name}'",
                "severity": "MEDIUM",
                "category": "Observability",
                "description": (
                    f"{missing_fl} NSG(s) in '{sub_name}' do not have Network Watcher flow logs enabled. "
                    "Without flow logs, traffic analysis, threat hunting, and forensic investigation are "
                    "severely limited. Flow logs are required by NIST 800-53 AU-12 and CIS Azure Benchmark."
                ),
                "recommendation": (
                    "Enable NSG Flow Logs v2 for all NSGs via Azure Network Watcher. "
                    "Set a Log Analytics workspace destination and enable Traffic Analytics. "
                    "Configure at least 90-day retention. "
                    "Use Azure Policy to enforce flow logs at scale."
                ),
            }
        )
    return findings


def _check_network_metrics(net_metrics, vnet_gateways, sub_name):
    if not net_metrics or net_metrics.get("collection_error"):
        return []
    findings = []
    gw_metrics_list = net_metrics.get("gateway_metrics", [])
    for gm in gw_metrics_list:
        gm_name = gm.get("gateway_name", "unknown")
        ingress = gm.get("ingress_bytes_24h") or 0
        egress = gm.get("egress_bytes_24h") or 0
        util = gm.get("utilization_pct")
        if util and util > _GW_HIGH_UTILIZATION_PCT:
            findings.append(
                {
                    "title": f"High bandwidth utilization on '{gm_name}' ({util:.0f}%)",
                    "severity": "HIGH",
                    "category": "Performance",
                    "description": (
                        f"Gateway '{gm_name}' is operating at {util:.0f}% of its provisioned bandwidth capacity. "
                        "Sustained utilization above 80% risks congestion, increased latency, and packet drops "
                        "during peak periods."
                    ),
                    "recommendation": (
                        "Upgrade to a higher-throughput SKU. "
                        "Consider enabling ExpressRoute FastPath if applicable. "
                        "Review traffic patterns for optimization opportunities "
                        "(compression, caching, traffic shaping)."
                    ),
                }
            )
        matching_gw = next((g for g in vnet_gateways if g.get("name") == gm_name), {})
        if bool(matching_gw.get("connections")) and ingress == 0 and egress == 0:
            findings.append(
                {
                    "title": f"VPN Gateway '{gm_name}' shows zero traffic in the last 24 hours",
                    "severity": "MEDIUM",
                    "category": "Performance",
                    "description": (
                        f"Gateway '{gm_name}' has active connection(s) configured but recorded zero bytes "
                        "transferred in the last 24 hours. This may indicate a disconnected tunnel, unused "
                        "gateway (wasted cost), or a monitoring gap."
                    ),
                    "recommendation": (
                        "Verify tunnel connectivity via Azure Portal > VPN Gateway > Connections. "
                        "If the gateway is no longer needed, consider decommissioning to reduce costs. "
                        "If traffic is expected, investigate VPN client or on-premises routing configuration."
                    ),
                }
            )
    if gw_metrics_list:
        total_in_gb = (
            sum((gm.get("ingress_bytes_24h") or 0) for gm in gw_metrics_list) / 1_000_000_000
        )
        total_out_gb = (
            sum((gm.get("egress_bytes_24h") or 0) for gm in gw_metrics_list) / 1_000_000_000
        )
        findings.append(
            {
                "title": (
                    f"Gateway Traffic Summary (24 h): "
                    f"{total_in_gb:.2f} GB in / {total_out_gb:.2f} GB out — '{sub_name}'"
                ),
                "severity": "INFORMATIONAL",
                "category": "Performance",
                "description": (
                    f"Combined VPN gateway traffic for '{sub_name}' over the last 24 hours: "
                    f"Ingress {total_in_gb:.2f} GB, Egress {total_out_gb:.2f} GB across "
                    f"{len(gw_metrics_list)} gateway(s). "
                    "No latency metrics are available without Azure Network Watcher Connection Monitor configured."
                ),
                "recommendation": (
                    "Configure Azure Network Watcher Connection Monitor to capture "
                    "round-trip latency and packet loss between endpoints. "
                    "Set alerting thresholds for latency > 150 ms and packet loss > 1%."
                ),
            }
        )
    return findings


def _topology_to_findings(sub_topo: dict) -> list[dict]:
    """Rule-based security checks on a single AzureSubscriptionTopology dict."""
    sub_name = sub_topo.get("subscription_name") or sub_topo.get("subscription_id", "unknown")
    sub_id = sub_topo.get("subscription_id", "unknown")
    if sub_topo.get("discovery_blocked"):
        return [
            {
                "title": f"Discovery blocked for subscription '{sub_name}'",
                "severity": "HIGH",
                "category": "Access Control",
                "description": (
                    f"The service principal lacks permissions to discover subscription {sub_id}. "
                    f"Reason: {sub_topo.get('block_reason', 'insufficient permissions')}. "
                    "Network topology is unknown for this subscription."
                ),
                "recommendation": (
                    "Assign the Reader role at the subscription scope. If NSG / route table details "
                    "are required, also assign Network Contributor."
                ),
            }
        ]
    vnets = sub_topo.get("vnets", [])
    firewalls = sub_topo.get("firewalls", [])
    vnet_gws = sub_topo.get("virtual_network_gateways", [])
    findings: list[dict] = []
    findings += _check_no_firewall(vnets, firewalls, sub_name)
    for vnet in vnets:
        findings += _check_vnet(vnet)
    for nsg in sub_topo.get("nsgs", []):
        findings += _check_nsg(nsg)
    findings += _check_route_tables(sub_topo.get("route_tables", []))
    findings += _check_firewalls(firewalls)
    findings += _check_app_gateways(sub_topo.get("application_gateways", []))
    findings += _check_load_balancers(sub_topo.get("load_balancers", []))
    findings += _check_vnet_gateway_connections(vnet_gws)
    findings += _check_public_ips(sub_topo.get("public_ips", []), sub_name)
    findings += _check_bastion(sub_topo.get("bastion_hosts", []), vnets, sub_name)
    findings += _check_private_endpoints(sub_topo.get("private_endpoints", []))
    findings += _check_gateway_skus(vnet_gws)
    findings += _check_nvas(sub_topo.get("nvas") or [], sub_name)
    for bgp in sub_topo.get("bgp_data") or []:
        findings += _check_bgp_gateway(bgp, vnet_gws)
    findings += _check_observability(sub_topo.get("observability") or {}, vnets, sub_name)
    findings += _check_network_metrics(sub_topo.get("network_metrics") or {}, vnet_gws, sub_name)
    return findings


def _finding_model_to_dict(finding: Any) -> dict:
    """Map a cna.core.findings_schema.Finding to the flat dict shape used by
    _replace_discovery_findings (Prisma Finding columns).

    The Prisma Finding table has no ruleId column, so the rule id is embedded
    as a title prefix; the stat-master / encyclopedia / copilot loaders all
    recover it with the shared _RULE_ID_RE extraction."""
    rule_id = finding.rule_id or ""
    title = finding.title
    if rule_id and rule_id not in title:
        title = f"{rule_id}: {title}"
    return {
        "rule_id": rule_id,
        "title": title,
        "severity": str(finding.severity.value).upper(),
        "category": finding.category or "General",
        "description": finding.description or finding.observed_state.fact,
        "recommendation": finding.recommendation
        or (finding.recommendations[0].text if finding.recommendations else ""),
        "traffic_direction": finding.traffic_direction,
        "region": finding.region or "",
        "resource_type": finding.resource_type or "",
        "est_cost_impact": finding.est_monthly_cost_usd,
    }


# ─── Routes ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "cna-api", "version": "0.2.0"}


# Legacy phase endpoints — honest 501s until the phases are actually wired up.
@app.post("/intake", status_code=501)
def intake(body: dict) -> dict:
    raise HTTPException(
        status_code=501,
        detail="The intake phase is not yet implemented in the API.",
    )


@app.post("/publish", status_code=501)
def publish(body: dict) -> dict:
    raise HTTPException(
        status_code=501,
        detail="The publish phase is not yet implemented in the API.",
    )


class TestConnectionRequest(BaseModel):
    tenant_id: str
    sp_client_id: str
    sp_client_secret: str


@app.post("/discovery/test-connection")
async def test_connection(request: TestConnectionRequest) -> dict:
    """Validate SP credentials against the Azure tenant."""
    try:
        from azure.identity import ClientSecretCredential
        from azure.mgmt.subscription import SubscriptionClient

        cred = ClientSecretCredential(
            request.tenant_id, request.sp_client_id, request.sp_client_secret
        )
        client = SubscriptionClient(cred)
        subs = list(client.subscriptions.list())
        return {
            "ok": True,
            "subscriptions": [{"id": s.subscription_id, "name": s.display_name} for s in subs],
        }
    except Exception:
        # Full details stay server-side; callers get a sanitized message.
        logger.exception("test-connection failed for tenant %s", request.tenant_id)
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not validate the service principal against the Azure tenant. "
                "Check the tenant ID, client ID, and client secret, then try again."
            ),
        ) from None


class AwsTestConnectionRequest(BaseModel):
    role_arn: str
    external_id: str | None = None
    access_key_id: str
    secret_access_key: str  # plaintext — decrypted by web layer


@app.post("/discovery/test-connection-aws")
async def test_connection_aws(request: AwsTestConnectionRequest) -> dict:
    """Validate AWS keys and prove the CNA read-only role can be assumed."""
    try:
        import boto3  # lazy: keeps Azure-only deployments importable without boto3

        session = boto3.Session(
            aws_access_key_id=request.access_key_id,
            aws_secret_access_key=request.secret_access_key,
        )
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        kwargs: dict[str, Any] = {
            "RoleArn": request.role_arn,
            "RoleSessionName": "CNA-TestConnection",
            "DurationSeconds": 900,
        }
        if request.external_id:
            kwargs["ExternalId"] = request.external_id
        assumed = sts.assume_role(**kwargs)
        return {
            "ok": True,
            "caller_account": identity["Account"],
            "assumed_role_arn": assumed["AssumedRoleUser"]["Arn"],
        }
    except Exception:
        # Full details stay server-side; callers get a sanitized message.
        logger.exception("test-connection-aws failed for role %s", request.role_arn)
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not validate the AWS credentials or assume the read-only role. "
                "Check the access key, secret, role ARN, and external ID, then try again."
            ),
        ) from None


class DiscoveryStartRequest(BaseModel):
    job_id: str
    engagement_id: str
    credential_id: str | None = None
    platform: str = "AZURE"  # "AZURE" | "AWS"
    # Azure
    tenant_id: str | None = None
    subscription_ids: list[str] = []
    sp_client_id: str | None = None
    sp_client_secret: str | None = None  # plaintext — decrypted by web layer
    # AWS
    aws_role_arn: str | None = None
    aws_external_id: str | None = None
    aws_regions: list[str] = []
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None  # plaintext — decrypted by web layer


@app.post("/discovery/start")
async def start_discovery(
    request: DiscoveryStartRequest, background_tasks: BackgroundTasks
) -> dict:
    if request.platform.upper() == "AWS":
        if not request.aws_role_arn:
            raise HTTPException(
                status_code=422, detail="aws_role_arn is required for AWS discovery"
            )
        if not request.aws_access_key_id or not request.aws_secret_access_key:
            raise HTTPException(
                status_code=422,
                detail="aws_access_key_id and aws_secret_access_key are required for AWS discovery",
            )
        _update_job(request.job_id, status="RUNNING", startedAt=datetime.now(UTC))
        background_tasks.add_task(_run_aws_discovery, request)
        return {"job_id": request.job_id, "status": "RUNNING"}

    if not request.tenant_id:
        raise HTTPException(status_code=422, detail="tenant_id is required")
    _update_job(request.job_id, status="RUNNING", startedAt=datetime.now(UTC))
    background_tasks.add_task(_run_azure_discovery, request)
    return {"job_id": request.job_id, "status": "RUNNING"}


@app.get("/discovery/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    if not DATABASE_URL:
        raise HTTPException(status_code=503, detail="DATABASE_URL not configured")
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, status, "startedAt", "completedAt",
                          "findingsCount", "errorMessage", "progressLog", "updatedAt"
                   FROM "DiscoveryJob" WHERE id = %s""",
                (job_id,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="job not found")
    return dict(row)


# ─── Background discovery task ────────────────────────────────────────────────


def _run_azure_discovery(request: DiscoveryStartRequest) -> None:
    job_id = request.job_id
    engagement_id = request.engagement_id
    progress: list[str] = []

    def _log(msg: str) -> None:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        entry = f"[{ts} UTC] {msg}"
        progress.append(entry)
        logger.info("[job:%s] %s", job_id, msg)
        _update_job(job_id, progressLog=json.dumps(progress))

    try:
        _log("Initialising discovery engine…")
        tmpdir = Path(mkdtemp(prefix="cna-discovery-"))
        store = EngagementStore(data_dir=tmpdir, engagement_id=engagement_id)

        options = AzureDiscoveryOptions(
            tenant_id=request.tenant_id,  # type: ignore[arg-type]
            subscription_ids=request.subscription_ids,
            client_id=request.sp_client_id,
            client_secret=request.sp_client_secret,
        )

        using_sp = bool(request.sp_client_id and request.sp_client_secret)
        auth_method = "service principal" if using_sp else "managed identity (no SP secret)"
        _log(f"Auth: {auth_method} | tenant {request.tenant_id}")
        if request.subscription_ids:
            sub_list = ", ".join(request.subscription_ids)
            _log(f"Targeting {len(request.subscription_ids)} subscription(s): {sub_list}")
        else:
            _log("No subscription filter — will discover all accessible subscriptions.")

        # Wire the discovery engine's internal progress into the job's progress log.
        discovery = AzureDiscovery(store, options, progress_callback=_log)

        _log("Running discovery — this may take a few minutes…")
        topology = discovery.run()

        _log(f"Scanned {len(topology.subscriptions)} subscription(s).")

        all_findings: list[dict] = []
        for sub_topo in topology.subscriptions:
            sub_dict: dict[str, Any] = json.loads(sub_topo.model_dump_json())
            sub_findings = _topology_to_findings(sub_dict)
            all_findings.extend(sub_findings)
            _log(
                f"  {sub_dict.get('subscription_name') or sub_dict.get('subscription_id')} "
                f"→ {len(sub_findings)} finding(s)"
            )

        # Phase B: FinOps + BC/DR generators from the cna package
        try:
            enriched = generate_finops_findings(topology) + generate_bcdr_findings(topology)
            all_findings.extend(_finding_model_to_dict(f) for f in enriched)
            _log(f"FinOps/BC-DR analysis → {len(enriched)} additional finding(s).")
        except Exception as exc:  # analysis must never fail the discovery run
            logger.exception("[job:%s] finops/bcdr analysis failed", job_id)
            _log(f"FinOps/BC-DR analysis skipped: {exc}")

        # Tag ALL findings (existing + new) with a traffic-direction plane
        for f in all_findings:
            if not f.get("traffic_direction"):
                f["traffic_direction"] = classify_traffic_direction(
                    f.get("rule_id", ""),
                    f.get("category", ""),
                    f.get("resource_type", ""),
                )

        if not DATABASE_URL:
            logger.warning(
                "[job:%s] DATABASE_URL is not set — %d finding(s) will NOT be persisted.",
                job_id,
                len(all_findings),
            )
        _log(f"Writing {len(all_findings)} finding(s) to database…")
        _replace_discovery_findings(engagement_id, request.credential_id, all_findings)
        _advance_engagement_status(engagement_id)

        topology_json = topology.model_dump_json()
        _update_job(
            job_id,
            status="COMPLETED",
            completedAt=datetime.now(UTC),
            findingsCount=len(all_findings),
            topologyJson=topology_json,
            progressLog=json.dumps(progress + ["Done."]),
        )

        # Phase C: materialize stat-master records (best effort — never fail the job)
        try:
            count = rebuild_metrics(engagement_id)
            logger.info("[job:%s] rebuilt %d stat-master record(s)", job_id, count)
        except Exception:
            logger.exception("[job:%s] stat-master rebuild failed", job_id)

    except Exception as exc:
        logger.exception("[job:%s] discovery failed", job_id)
        _update_job(
            job_id,
            status="FAILED",
            errorMessage=str(exc),
            completedAt=datetime.now(UTC),
            progressLog=json.dumps(progress),
        )


def _run_aws_discovery(request: DiscoveryStartRequest) -> None:
    """AWS counterpart of _run_azure_discovery (CNA-0.90 §3: AWS end-to-end).

    Findings come from the cna package's AnalysisEngine AWS rules rather than
    a second bespoke rule set here — the ~1,000 lines of _check_* helpers
    above are Azure-shaped, and the engine's AWS rules are already tested.
    The FinOps/BC-DR generators are typed AzureTopology-only and are skipped.
    """
    job_id = request.job_id
    engagement_id = request.engagement_id
    progress: list[str] = []

    def _log(msg: str) -> None:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        entry = f"[{ts} UTC] {msg}"
        progress.append(entry)
        logger.info("[job:%s] %s", job_id, msg)
        _update_job(job_id, progressLog=json.dumps(progress))

    try:
        # Lazy: keeps Azure-only deployments importable without boto3.
        from cna.ai_engine.analysis_engine import AnalysisEngine, AnalysisOptions
        from cna.modules.network.discovery.aws_discovery import (
            AWSDiscovery,
        )
        from cna.modules.network.discovery.aws_discovery import (
            DiscoveryOptions as AwsDiscoveryOptions,
        )

        _log("Initialising AWS discovery engine…")
        tmpdir = Path(mkdtemp(prefix="cna-discovery-"))
        store = EngagementStore(data_dir=tmpdir, engagement_id=engagement_id)

        options = AwsDiscoveryOptions(
            org_role_arn=request.aws_role_arn,  # type: ignore[arg-type]  # validated at the endpoint
            external_id=request.aws_external_id,
            regions=request.aws_regions,
            access_key_id=request.aws_access_key_id,
            secret_access_key=request.aws_secret_access_key,
        )

        _log(f"Role: {request.aws_role_arn}")
        if request.aws_regions:
            _log(
                f"Targeting {len(request.aws_regions)} region(s): {', '.join(request.aws_regions)}"
            )
        else:
            _log("No region filter — will discover all enabled regions.")

        discovery = AWSDiscovery(store, options)

        _log("Running discovery — this may take a few minutes…")
        topology = discovery.run()

        blocked = sum(1 for r in topology.regions if r.discovery_blocked)
        _log(
            f"Scanned {len(topology.regions)} region(s) across "
            f"{len(topology.accounts)} account(s)" + (f" — {blocked} blocked." if blocked else ".")
        )

        _log("Running analysis rules…")
        engine = AnalysisEngine(
            store=store,
            options=AnalysisOptions(load_aws=True, load_azure=False, dry_run=True),
        )
        report = engine.run(aws_topology=topology)
        all_findings = [_finding_model_to_dict(f) for f in report.findings]
        _log(f"Analysis → {len(all_findings)} finding(s).")

        # Tag findings with a traffic-direction plane (same as the Azure path)
        for f in all_findings:
            if not f.get("traffic_direction"):
                f["traffic_direction"] = classify_traffic_direction(
                    f.get("rule_id", ""),
                    f.get("category", ""),
                    f.get("resource_type", ""),
                )

        if not DATABASE_URL:
            logger.warning(
                "[job:%s] DATABASE_URL is not set — %d finding(s) will NOT be persisted.",
                job_id,
                len(all_findings),
            )
        _log(f"Writing {len(all_findings)} finding(s) to database…")
        _replace_discovery_findings(engagement_id, request.credential_id, all_findings)
        _advance_engagement_status(engagement_id)

        _update_job(
            job_id,
            status="COMPLETED",
            completedAt=datetime.now(UTC),
            findingsCount=len(all_findings),
            topologyJson=topology.model_dump_json(),
            progressLog=json.dumps(progress + ["Done."]),
        )

    except Exception as exc:
        logger.exception("[job:%s] AWS discovery failed", job_id)
        _update_job(
            job_id,
            status="FAILED",
            errorMessage=str(exc),
            completedAt=datetime.now(UTC),
            progressLog=json.dumps(progress),
        )
