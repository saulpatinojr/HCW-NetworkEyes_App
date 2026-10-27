"""Azure network rules ``AZ-NET-001..033``.

``AZ-NET-001..019`` are Engine A's rules (facts, evidence references and framework mappings
intact); ``AZ-NET-020..033`` are the checks the API's Engine B alone carried, typed under the
ids and severities of plan table 7.B. Each rule is a pure function over one subscription's
checkpoint and yields ``Observation`` values (or ``NotEvaluable`` when the topology cannot
answer it); the registry turns them into findings.

Rule versions follow the downstream lab edition's table, which is the contract both
editions pin: ``AZ-NET-002/003/006/007/011/012/014`` are at version 2 (merged platform-subnet
skip list; threat intelligence read through the linked firewall policy; flow logs and
Traffic Analytics read from flow-log rows when the topology is an export; subnet IP
exhaustion derived from ``ipConfigurations``; hedge-free facts and titles).

Every ``learn_url`` is a Microsoft Learn path recorded without a retrieval check and stays
``[VERIFY]`` until the owner confirms it; every framework control reference is a claim shown
to customers and is ``[REVIEW REQUIRED]`` (plan section 22, item 5).
"""

from __future__ import annotations

import ipaddress
from collections.abc import Iterator

from network_assessment_azure_engine.findings.schema import FindingSeverity
from network_assessment_azure_engine.model.azure import (
    AzureRouteTable,
    AzureSubscriptionTopology,
    AzureTopology,
    NSGSecurityRule,
    VNet,
)
from network_assessment_azure_engine.rules import frameworks as fw
from network_assessment_azure_engine.rules.registry import NotEvaluable, Observation, rule

# ---------------------------------------------------------------------------
# Rule ids — stable across runs, never reused
# ---------------------------------------------------------------------------

R_AZ_VNET_NO_DDOS = "AZ-NET-001"
R_AZ_SUBNET_NO_NSG = "AZ-NET-002"
R_AZ_FW_THREAT_INTEL_NOT_DENY = "AZ-NET-003"
R_AZ_ER_NO_REDUNDANCY = "AZ-NET-004"
R_AZ_PEERING_ALLOW_GW_TRANSIT = "AZ-NET-005"
R_AZ_VNET_NO_FLOW_LOGS = "AZ-NET-006"
R_AZ_APPGW_WAF_DISABLED = "AZ-NET-007"
R_AZ_GW_SATURATION = "AZ-NET-008"
R_AZ_FW_NO_HITS = "AZ-NET-009"
R_AZ_LB_SNAT_EXHAUSTION = "AZ-NET-010"
R_AZ_VNET_IP_EXHAUSTION = "AZ-NET-011"
R_AZ_PEERING_FW_BYPASS = "AZ-NET-012"
R_AZ_FW_NO_DIAGNOSTICS = "AZ-NET-013"
R_AZ_TRAFFIC_ANALYTICS_MISSING = "AZ-NET-014"
R_AZ_BASTION_NO_DIAGNOSTICS = "AZ-NET-015"
R_AZ_ER_SATURATION = "AZ-NET-016"
R_AZ_DDOS_ATTACK_DETECTED = "AZ-NET-017"
R_AZ_FRONTDOOR_WAF_DETECTION_MODE = "AZ-NET-018"
R_AZ_APPGW_HIGH_LATENCY = "AZ-NET-019"
R_AZ_NSG_REMOTE_ACCESS_FROM_INTERNET = "AZ-NET-020"
R_AZ_NSG_WILDCARD_ALLOW_ALL = "AZ-NET-021"
R_AZ_UDR_DEFAULT_ROUTE_INTERNET = "AZ-NET-022"
R_AZ_UDR_BGP_PROPAGATION_DISABLED = "AZ-NET-023"
R_AZ_VNET_CUSTOM_DNS = "AZ-NET-024"
R_AZ_APPGW_WAF_DETECTION_MODE = "AZ-NET-025"
R_AZ_LB_BASIC_SKU = "AZ-NET-026"
R_AZ_PIP_BASIC_SKU = "AZ-NET-027"
R_AZ_VPN_GW_BASIC_SKU = "AZ-NET-028"
R_AZ_VPN_GW_GENERATION1 = "AZ-NET-029"
R_AZ_GW_CONNECTION_NOT_CONNECTED = "AZ-NET-030"
R_AZ_PE_CONNECTION_PENDING = "AZ-NET-031"
R_AZ_NO_FIREWALL = "AZ-NET-032"
R_AZ_NO_BASTION = "AZ-NET-033"

# ---------------------------------------------------------------------------
# Thresholds and vocabularies
# ---------------------------------------------------------------------------

_HIGH_UTILIZATION_PCT: float = 80.0
_CRITICAL_UTILIZATION_PCT: float = 85.0
_APPGW_LATENCY_THRESHOLD_MS: int = 2000
_APPGW_FAILURE_RATE_THRESHOLD: float = 0.05
_PORT_SSH: int = 22
_PORT_RDP: int = 3389
_REMOTE_ACCESS_PORTS: frozenset[int] = frozenset({_PORT_SSH, _PORT_RDP})
_AZURE_PROVIDED_DNS = "168.63.129.16"
_DEFAULT_ROUTE = "0.0.0.0/0"
_NEXT_HOP_INTERNET = "Internet"
_NEXT_HOP_NVA = "VirtualAppliance"
_WAF_PREVENTION = "prevention"
_SKU_BASIC = "basic"
_GATEWAY_TYPE_VPN = "Vpn"
_CONNECTED_STATES: frozenset[str] = frozenset({"connected", "unknown"})
_PENDING = "pending"
_IP_EXHAUSTION_PCT: float = 80.0
_RESERVED_ADDRESSES_PER_SUBNET = 5  # Azure reserves the first four and the last address
_NO_FLOW_LOG_ROWS = "the export has no networkwatchers/flowlogs rows; flow log state is unknown"

# Service-tagged or wildcard sources that mean "anywhere on the internet" in an NSG rule.
_INTERNET_SOURCES: frozenset[str] = frozenset({"*", "internet", "any", "0.0.0.0/0"})
# Wildcards accepted in an NSG rule's protocol and destination-port fields.
_WILDCARDS: frozenset[str] = frozenset({"*", "any"})

# Platform subnets that cannot carry an NSG or a route table by design. Engine A skipped
# only GatewaySubnet (and its hub-bypass list spelt RouteServerSubnet "routeservicesubnet");
# Engine B skipped all five. Merged and lower-cased here (AZ-NET-002 v2, AZ-NET-012 v2).
PLATFORM_SUBNETS: frozenset[str] = frozenset(
    {
        "gatewaysubnet",
        "azurebastionsubnet",
        "azurefirewallsubnet",
        "azurefirewallmanagementsubnet",
        "routeserversubnet",
    }
)

# ---------------------------------------------------------------------------
# Microsoft Learn references — every entry [VERIFY] until the owner confirms it
# ---------------------------------------------------------------------------

_LEARN = "https://learn.microsoft.com/azure/"
_LEARN_DDOS = _LEARN + "ddos-protection/ddos-protection-overview"
_LEARN_NSG = _LEARN + "virtual-network/network-security-groups-overview"
_LEARN_FIREWALL_THREAT_INTEL = _LEARN + "firewall/threat-intel"
_LEARN_ER_HA = _LEARN + "expressroute/designing-for-high-availability-with-expressroute"
_LEARN_GATEWAY_TRANSIT = _LEARN + "vpn-gateway/vpn-gateway-peering-gateway-transit"
_LEARN_VNET_FLOW_LOGS = _LEARN + "network-watcher/vnet-flow-logs-overview"
_LEARN_APPGW_WAF = _LEARN + "web-application-firewall/ag/ag-overview"
_LEARN_VPN_GW_MONITOR = _LEARN + "vpn-gateway/monitor-vpn-gateway"
_LEARN_FIREWALL_LOGS = _LEARN + "firewall/firewall-diagnostics"
_LEARN_LB_OUTBOUND = _LEARN + "load-balancer/load-balancer-outbound-connections"
_LEARN_VNET_PLAN = _LEARN + "virtual-network/virtual-network-vnet-plan-design-arm"
_LEARN_UDR = _LEARN + "virtual-network/virtual-networks-udr-overview"
_LEARN_TRAFFIC_ANALYTICS = _LEARN + "network-watcher/traffic-analytics"
_LEARN_BASTION_LOGS = _LEARN + "bastion/diagnostic-logs"
_LEARN_ER_MONITOR = _LEARN + "expressroute/monitor-expressroute"
_LEARN_FRONTDOOR_WAF = _LEARN + "web-application-firewall/afds/afds-overview"
_LEARN_APPGW_METRICS = _LEARN + "application-gateway/application-gateway-metrics"
_LEARN_VNET_DNS = (
    _LEARN + "virtual-network/virtual-networks-name-resolution-for-vms-and-role-instances"
)
_LEARN_LB_SKUS = _LEARN + "load-balancer/skus"
_LEARN_PIP_SKUS = _LEARN + "virtual-network/ip-services/public-ip-addresses"
_LEARN_VPN_GW_SKUS = _LEARN + "vpn-gateway/about-gateway-skus"
_LEARN_VPN_GW_TROUBLESHOOT = (
    _LEARN + "vpn-gateway/vpn-gateway-troubleshoot-site-to-site-cannot-connect"
)
_LEARN_PRIVATE_ENDPOINT = _LEARN + "private-link/private-endpoint-overview"
_LEARN_FIREWALL = _LEARN + "firewall/overview"
_LEARN_BASTION = _LEARN + "bastion/bastion-overview"

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _is_platform_subnet(name: str | None) -> bool:
    return bool(name) and name.lower() in PLATFORM_SUBNETS


def _port_spec_covers(spec: str | None, ports: frozenset[int]) -> set[int]:
    """Which of ``ports`` an NSG destination-port spec (``*``, ``22``, ``3000-4000``) covers."""
    if not spec:
        return set()
    text = spec.strip()
    if text in _WILDCARDS:
        return set(ports)
    low, _, high = text.partition("-")
    if not low.isdigit():
        return set()
    lower = int(low)
    upper = int(high) if high.isdigit() else lower
    return {p for p in ports if lower <= p <= upper}


def _exposed_ports(nsg_rule: NSGSecurityRule) -> set[int]:
    specs = [nsg_rule.destination_port_range, *nsg_rule.destination_port_ranges]
    exposed: set[int] = set()
    for spec in specs:
        exposed |= _port_spec_covers(spec, _REMOTE_ACCESS_PORTS)
    return exposed


def _sources(nsg_rule: NSGSecurityRule) -> list[str]:
    return [s for s in [nsg_rule.source_address_prefix, *nsg_rule.source_address_prefixes] if s]


def _from_internet(nsg_rule: NSGSecurityRule) -> bool:
    return any(s.strip().lower() in _INTERNET_SOURCES for s in _sources(nsg_rule))


def _is_wildcard(value: str | None) -> bool:
    return bool(value) and value.strip().lower() in _WILDCARDS


def _allows_all_ports(nsg_rule: NSGSecurityRule) -> bool:
    return _is_wildcard(nsg_rule.destination_port_range) or any(
        _is_wildcard(p) for p in nsg_rule.destination_port_ranges
    )


def _nsg_rule_id(nsg_id: str, nsg_rule: NSGSecurityRule) -> str:
    return f"{nsg_id}/securityRules/{nsg_rule.name}"


def _route_tables(sub: AzureSubscriptionTopology) -> list[AzureRouteTable]:
    """Route tables as discovered: the subscription list plus any nested under a VNet."""
    seen: dict[str, AzureRouteTable] = {}
    for rt in [*sub.route_tables, *(rt for vnet in sub.vnets for rt in vnet.route_tables)]:
        seen.setdefault(rt.id, rt)
    return list(seen.values())


def _has_nva_default_route(sub: AzureSubscriptionTopology) -> bool:
    return any(
        route.address_prefix == _DEFAULT_ROUTE and route.next_hop_type == _NEXT_HOP_NVA
        for rt in _route_tables(sub)
        for route in rt.routes
    )


def _has_secured_hub(sub: AzureSubscriptionTopology) -> bool:
    return any(hub.azure_firewall_id for vwan in sub.virtual_wans for hub in vwan.hubs)


def _is_spoke(vnet: VNet) -> bool:
    return any(p.allow_forwarded_traffic or p.use_remote_gateways for p in vnet.peerings)


def _subscription_resource_id(sub: AzureSubscriptionTopology) -> str:
    return f"/subscriptions/{sub.subscription_id}"


def _export_without_flow_logs(topology: AzureTopology) -> bool:
    """An export that carries no flow-log rows cannot say whether flow logs exist."""
    return topology.source == "export" and not any(s.flow_logs for s in topology.subscriptions)


def _usable_addresses(prefixes: list[str]) -> int:
    total = 0
    for prefix in prefixes:
        try:
            network = ipaddress.ip_network(prefix, strict=False)
        except ValueError:
            continue
        if network.version == 4:
            total += network.num_addresses
    return total - _RESERVED_ADDRESSES_PER_SUBNET


# ---------------------------------------------------------------------------
# AZ-NET-001..007 — configuration rules from Engine A
# ---------------------------------------------------------------------------


@rule(
    id=R_AZ_VNET_NO_DDOS,
    title="VNet does not have DDoS Protection enabled",
    severity=FindingSeverity.LOW,
    category="Network Protection",
    version=1,
    learn_url=_LEARN_DDOS,
    frameworks=(
        fw.WAF_NS1,
        fw.ISO_8_20,
        fw.hipaa(
            "(e)(2)(ii) — Encryption and decryption (addressable); "
            "integrity controls for ePHI in transit"
        ),
        fw.FEDRAMP_SC5,
        fw.cisa("3.4", fw.CISA_RESILIENCE, "DDoS protection is a network resilience control"),
    ),
    applies_to="export",
    evidence="vnets[].ddos_protection_enabled",
)
def vnet_without_ddos_protection(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for vnet in sub.vnets:
        if not vnet.ddos_protection_enabled:
            yield Observation(
                resource_id=vnet.id,
                resource_type="Microsoft.Network/virtualNetworks",
                region=vnet.location,
                fact=f"VNet {vnet.name} ({vnet.id}) in {vnet.location} has "
                f"DDoS Protection Standard disabled.",
                evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}].ddos_protection_enabled",
            )


@rule(
    id=R_AZ_SUBNET_NO_NSG,
    title="Subnet has no Network Security Group",
    severity=FindingSeverity.HIGH,
    category="Network Segmentation",
    version=2,
    learn_url=_LEARN_NSG,
    frameworks=(
        fw.WAF_NS1,
        fw.cis("6.2"),
        fw.PCI_1_2,
        fw.ISO_8_22,
        fw.hipaa(
            "(a)(1) — Access control: unique user identification "
            "and network access controls for ePHI systems"
        ),
        fw.FEDRAMP_SC7,
        fw.cisa("3.1", fw.CISA_SEGMENTATION, "NSGs enforce micro-segmentation between subnets"),
    ),
    applies_to="export",
    evidence="vnets[].subnets[].nsg_id",
)
def subnet_without_nsg(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for vnet in sub.vnets:
        for subnet in vnet.subnets:
            if subnet.nsg_id or _is_platform_subnet(subnet.name):
                continue
            yield Observation(
                resource_id=subnet.id,
                resource_type="Microsoft.Network/virtualNetworks/subnets",
                region=vnet.location,
                fact=f"Subnet {subnet.name} ({subnet.id}) in VNet {vnet.name} has no NSG attached.",
                evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}]"
                f".subnets[id={subnet.id}].nsg_id",
            )


@rule(
    id=R_AZ_FW_THREAT_INTEL_NOT_DENY,
    title="Azure Firewall Threat Intelligence mode is not set to Deny",
    severity=FindingSeverity.CRITICAL,
    category="Network Security",
    version=2,
    learn_url=_LEARN_FIREWALL_THREAT_INTEL,
    frameworks=(
        fw.WAF_NS4,
        fw.NIST_PR_PT_4,
        fw.PCI_1_3,
        fw.ISO_8_20,
        fw.hipaa(
            "(e)(1) — Transmission security: guard against unauthorized access to ePHI in transit"
        ),
        fw.FEDRAMP_SC7,
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "Threat intel-based blocking controls traffic flows to known malicious destinations",
        ),
    ),
    applies_to="export",
    evidence="firewalls[].threat_intel_mode (or the linked firewall policy's)",
)
def firewall_threat_intel_not_deny(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for firewall in sub.firewalls:
        mode = firewall.effective_threat_intel_mode
        if mode.lower() == "deny":
            continue
        via = " (from its firewall policy)" if firewall.firewall_policy else ""
        yield Observation(
            resource_id=firewall.id,
            resource_type="Microsoft.Network/azureFirewalls",
            region=firewall.location,
            fact=f"Azure Firewall {firewall.name} has ThreatIntelMode='{mode}'{via}. "
            f"Known malicious IPs and domains are not actively blocked.",
            evidence_ref=f"discovery:azure_{sub_id}.firewalls[id={firewall.id}].threat_intel_mode",
        )


@rule(
    id=R_AZ_ER_NO_REDUNDANCY,
    title="Single ExpressRoute circuit — no redundancy",
    severity=FindingSeverity.LOW,
    category="Connectivity",
    version=1,
    learn_url=_LEARN_ER_HA,
    frameworks=(
        fw.WAF_RE3,
        fw.ISO_8_21,
        fw.hipaa(
            "(a)(2)(ii) — Automatic logoff / contingency operations; availability of ePHI systems"
        ),
        fw.FEDRAMP_CP8_REDUNDANCY,
        fw.cisa(
            "3.4",
            fw.CISA_RESILIENCE,
            "Redundant circuits prevent single points of failure in hybrid connectivity",
        ),
    ),
    applies_to="export",
    evidence="express_route_circuits[]",
    needs_properties=False,
)
def single_expressroute_circuit(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    if len(sub.express_route_circuits) == 1:
        er = sub.express_route_circuits[0]
        yield Observation(
            resource_id=er.id,
            resource_type="Microsoft.Network/expressRouteCircuits",
            region=er.location,
            fact=f"Only one ExpressRoute circuit ({er.name}, {er.bandwidth_mbps}Mbps via "
            f"{er.service_provider or 'unknown provider'}) found in subscription {sub_id}.",
            evidence_ref=f"discovery:azure_{sub_id}.express_route_circuits",
        )


@rule(
    id=R_AZ_PEERING_ALLOW_GW_TRANSIT,
    title="VNet peering allows gateway transit but VNet has no gateway",
    severity=FindingSeverity.LOW,
    category="Routing & Transit",
    version=1,
    learn_url=_LEARN_GATEWAY_TRANSIT,
    frameworks=(
        fw.WAF_NS1,
        fw.FEDRAMP_SC7,
        fw.cisa(
            "3.1", fw.CISA_SEGMENTATION, "Misconfigured peering can create unintended network paths"
        ),
    ),
    applies_to="export",
    evidence="vnets[].peerings[].allow_gateway_transit, virtual_network_gateways[].subnet_id",
)
def peering_gateway_transit_without_gateway(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for vnet in sub.vnets:
        # A gateway has no vnet_id — it lives in a GatewaySubnet, and an ARM subnet id
        # nests under its VNet id as "<vnet_id>/subnets/<name>" (TODO.md T-410).
        has_local_gw = any(
            gw.subnet_id and gw.subnet_id.startswith(f"{vnet.id}/")
            for gw in sub.virtual_network_gateways or []
        )
        if has_local_gw:
            continue
        for peering in vnet.peerings:
            if peering.allow_gateway_transit:
                yield Observation(
                    resource_id=vnet.id,
                    resource_type="Microsoft.Network/virtualNetworks/virtualNetworkPeerings",
                    region=vnet.location,
                    fact=f"Peering {peering.name} on VNet {vnet.name} has "
                    f"allow_gateway_transit=True but no virtual network gateway "
                    f"exists in this VNet. Spoke VNets attempting to use this "
                    f"transit path will have no effective route.",
                    evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}]"
                    f".peerings[name={peering.name}].allow_gateway_transit",
                )


@rule(
    id=R_AZ_VNET_NO_FLOW_LOGS,
    title="VNet has no NSG flow logs enabled",
    severity=FindingSeverity.HIGH,
    category="Monitoring & Visibility",
    version=2,
    learn_url=_LEARN_VNET_FLOW_LOGS,
    frameworks=(
        fw.WAF_NS2,
        fw.nist(
            "Detect", "DE.CM-1 — The network is monitored to detect potential cybersecurity events"
        ),
        fw.hipaa("(b) — Audit controls: hardware/software activity records for ePHI systems"),
        fw.FEDRAMP_AU2,
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "Flow logs enable traffic visibility required for zero trust enforcement",
        ),
    ),
    applies_to="export",
    evidence="vnets[].flow_logs_enabled (an export: networkwatchers/flowlogs rows projected onto the VNet)",
)
def vnet_without_flow_logs(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation | NotEvaluable]:
    sub_id = sub.subscription_id
    if _export_without_flow_logs(topology):
        yield NotEvaluable(_NO_FLOW_LOG_ROWS)
        return
    for vnet in sub.vnets:
        if not vnet.flow_logs_enabled:
            yield Observation(
                resource_id=vnet.id,
                resource_type="Microsoft.Network/virtualNetworks",
                region=vnet.location,
                fact=f"VNet {vnet.name} ({vnet.id}) in {vnet.location} has "
                f"flow_logs_enabled=False. Network traffic to/from this VNet "
                f"produces no telemetry for incident investigation.",
                evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}].flow_logs_enabled",
            )


@rule(
    id=R_AZ_APPGW_WAF_DISABLED,
    title="Application Gateway WAF is disabled",
    severity=FindingSeverity.HIGH,
    category="Application Security",
    version=2,
    learn_url=_LEARN_APPGW_WAF,
    frameworks=(
        fw.WAF_NS4,
        fw.PCI_1_3,
        fw.ISO_8_23,
        fw.hipaa(
            "(e)(1) — Transmission security: protect ePHI APIs from injection and web-layer attacks"
        ),
        fw.FEDRAMP_SC7,
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "WAF provides application-layer traffic filtering at the perimeter",
        ),
        fw.cisa(
            "4.0",
            "Application and Workload Protection",
            "Disabled WAF leaves application workloads without HTTP-layer attack inspection",
            pillar="Applications and Workloads",
        ),
    ),
    applies_to="export",
    evidence="application_gateways[].waf_enabled",
)
def application_gateway_waf_disabled(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for agw in sub.application_gateways:
        if not agw.waf_enabled:
            yield Observation(
                resource_id=agw.id,
                resource_type="Microsoft.Network/applicationGateways",
                region=agw.location,
                fact=f"Application Gateway {agw.name} ({agw.sku_name}) has "
                f"Web Application Firewall disabled.",
                evidence_ref=f"discovery:azure_{sub_id}.application_gateways[id={agw.id}].waf_enabled",
            )


# ---------------------------------------------------------------------------
# AZ-NET-008..011, 013..017, 019 — live-only rules from Engine A (metric and
# diagnostic collectors). They keep Engine A's resource keys: the metric rules
# key on the subscription id, as they always did.
# ---------------------------------------------------------------------------


@rule(
    id=R_AZ_GW_SATURATION,
    title="Virtual Network Gateway utilization exceeds 80%",
    severity=FindingSeverity.HIGH,
    category="Performance",
    version=1,
    learn_url=_LEARN_VPN_GW_MONITOR,
    frameworks=(
        fw.WAF_PE3,
        fw.cisa(
            "3.4", fw.CISA_RESILIENCE, "Gateway saturation degrades hybrid connectivity resilience"
        ),
    ),
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.gateway_metrics[].utilization_pct",
)
def gateway_saturation(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    for gm in metrics.gateway_metrics:
        if gm.utilization_pct and gm.utilization_pct > _HIGH_UTILIZATION_PCT:
            yield Observation(
                resource_id=sub_id,
                resource_type="Microsoft.Network/virtualNetworkGateways",
                fact=f"Gateway {gm.gateway_name} has {gm.utilization_pct}% utilization.",
                evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
            )


@rule(
    id=R_AZ_FW_NO_HITS,
    title="Azure Firewall present but processes 0 traffic",
    severity=FindingSeverity.HIGH,
    category="Network Security",
    version=1,
    learn_url=_LEARN_FIREWALL_LOGS,
    frameworks=(
        fw.WAF_NS4,
        fw.cisa("3.2", fw.CISA_TRAFFIC, "Zero rule hits suggests traffic bypasses the firewall"),
    ),
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.firewall_metrics[]",
)
def firewall_without_traffic(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    for fm in metrics.firewall_metrics:
        no_rule_hits = (
            fm.network_rule_hits_24h == 0
            and fm.app_rule_hits_24h == 0
            and fm.nat_rule_hits_24h == 0
        )
        if no_rule_hits or fm.data_processed_gb_24h == 0.0:
            yield Observation(
                resource_id=sub_id,
                resource_type="Microsoft.Network/azureFirewalls",
                fact=f"Firewall {fm.firewall_name} recorded 0 rule hits or 0 data processed "
                f"in 24 hours.",
                evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
                description="No traffic reached the firewall's rules in the metric window: "
                "the routing in place does not send flows through it.",
            )


@rule(
    id=R_AZ_LB_SNAT_EXHAUSTION,
    title="Load Balancer SNAT port utilization exceeds 80%",
    severity=FindingSeverity.HIGH,
    category="Performance",
    version=1,
    learn_url=_LEARN_LB_OUTBOUND,
    frameworks=(
        fw.WAF_RE4_SCALE,
        fw.cisa(
            "3.4",
            fw.CISA_RESILIENCE,
            "SNAT exhaustion causes connection failures affecting resilience",
        ),
    ),
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.lb_metrics[].snat_port_utilization_pct",
)
def load_balancer_snat_exhaustion(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    for lm in metrics.lb_metrics:
        if lm.snat_port_utilization_pct and lm.snat_port_utilization_pct > _HIGH_UTILIZATION_PCT:
            yield Observation(
                resource_id=sub_id,
                resource_type="Microsoft.Network/loadBalancers",
                fact=f"Load Balancer {lm.lb_name} used {lm.snat_port_utilization_pct}% "
                f"of allocated SNAT ports.",
                evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
            )


@rule(
    id=R_AZ_VNET_IP_EXHAUSTION,
    title="Subnet address space is close to exhaustion",
    severity=FindingSeverity.HIGH,
    category="Network Segmentation",
    version=2,
    learn_url=_LEARN_VNET_PLAN,
    frameworks=(
        fw.WAF_RE2,
        fw.cisa("3.4", fw.CISA_RESILIENCE, "IP space exhaustion prevents new workload deployments"),
    ),
    applies_to="export",
    evidence="vnets[].subnets[].ip_configuration_count against the prefix size minus the 5 reserved "
    "addresses (80 percent); network_metrics.vnet_utilization when a live collector ran",
)
def vnet_ip_exhaustion(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for vnet in sub.vnets:
        for subnet in vnet.subnets:
            if not subnet.ip_configuration_count:
                continue
            prefixes = subnet.address_prefixes or (
                [subnet.address_prefix] if subnet.address_prefix else []
            )
            usable = _usable_addresses(prefixes)
            if usable <= 0:
                continue
            pct = subnet.ip_configuration_count / usable * 100
            if pct < _IP_EXHAUSTION_PCT:
                continue
            yield Observation(
                resource_id=subnet.id,
                resource_type="Microsoft.Network/virtualNetworks/subnets",
                region=vnet.location,
                fact=f"Subnet {subnet.name} ({', '.join(prefixes)}) in VNet {vnet.name} lists "
                f"{subnet.ip_configuration_count} ipConfigurations against {usable} usable "
                f"addresses ({pct:.0f} percent).",
                evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}]"
                f".subnets[id={subnet.id}].ip_configuration_count",
            )
    metrics = sub.network_metrics
    if not metrics:
        return
    for vnet_id, util in metrics.vnet_utilization.items():
        if util > _CRITICAL_UTILIZATION_PCT:
            yield Observation(
                resource_id=vnet_id,
                resource_type="Microsoft.Network/virtualNetworks",
                title="VNet IP space utilization exceeds 85%",
                fact=f"VNet {vnet_id} has {util}% of its address space allocated to subnets.",
                evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
            )


@rule(
    id=R_AZ_PEERING_FW_BYPASS,
    title="Spoke subnet has no default route through the hub firewall",
    severity=FindingSeverity.MEDIUM,
    category="Routing & Transit",
    version=2,
    learn_url=_LEARN_UDR,
    frameworks=(
        fw.WAF_NS1,
        fw.asb("NS-4"),
        fw.cisa(
            "3.1",
            fw.CISA_SEGMENTATION,
            "Traffic bypassing the hub firewall violates segmentation policy",
        ),
    ),
    applies_to="export",
    evidence="vnets[].subnets[].route_table_name, route_tables[].routes[]",
)
def spoke_subnet_bypasses_hub_firewall(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    rt_by_name = {rt.name: rt for rt in sub.route_tables}
    for vnet in sub.vnets:
        if not _is_spoke(vnet):
            continue
        for subnet in vnet.subnets:
            if _is_platform_subnet(subnet.name):
                continue
            rt = rt_by_name.get(subnet.route_table_name or "")
            if rt is None:
                yield Observation(
                    resource_id=subnet.id,
                    resource_type="Microsoft.Network/virtualNetworks/subnets",
                    region=vnet.location,
                    title="Spoke subnet has no UDR; hub firewall is not on its default path",
                    fact=f"Subnet {subnet.name} in spoke VNet {vnet.name} has no route table. "
                    f"Internet-bound traffic egresses directly rather than through the "
                    f"hub NVA/firewall.",
                    evidence_ref=f"discovery:azure_{sub_id}"
                    f".vnets[id={vnet.id}].subnets[id={subnet.id}].route_table_name",
                )
                continue
            has_forced_route = any(
                r.address_prefix == _DEFAULT_ROUTE and r.next_hop_type == _NEXT_HOP_NVA
                for r in rt.routes
            )
            if not has_forced_route:
                yield Observation(
                    resource_id=subnet.id,
                    resource_type="Microsoft.Network/virtualNetworks/subnets",
                    region=vnet.location,
                    title="Spoke subnet UDR lacks 0.0.0.0/0 → NVA route",
                    fact=f"Subnet {subnet.name} in spoke VNet {vnet.name} has route table "
                    f"{rt.name} but no default route (0.0.0.0/0) pointing to a "
                    f"VirtualAppliance. Internet traffic does not traverse the hub firewall.",
                    evidence_ref=f"discovery:azure_{sub_id}.route_tables[name={rt.name}].routes",
                )


@rule(
    id=R_AZ_FW_NO_DIAGNOSTICS,
    title="Azure Firewall lacks Log Analytics diagnostic settings",
    severity=FindingSeverity.MEDIUM,
    category="Observability",
    version=1,
    learn_url=_LEARN_FIREWALL_LOGS,
    frameworks=(
        fw.WAF_NS3,
        fw.nist(
            "Detect", "DE.CM-1 — The network is monitored to detect potential cybersecurity events"
        ),
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "Firewall logs are required to audit and verify traffic management policies",
        ),
    ),
    applies_to="live-only",
    inputs=("observability",),
    evidence="observability.firewalls_with_diagnostics",
)
def firewall_without_diagnostics(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    obs = sub.observability
    if not obs:
        return
    if obs.firewalls_total > 0 and obs.firewalls_with_diagnostics < obs.firewalls_total:
        missing = obs.firewalls_total - obs.firewalls_with_diagnostics
        yield Observation(
            resource_id=sub_id,
            resource_type="Microsoft.Network/azureFirewalls",
            fact=f"{missing} of {obs.firewalls_total} Azure Firewall(s) in subscription {sub_id} "
            f"have no Log Analytics diagnostic sink. Firewall rule logs and threat intel "
            f"logs are lost.",
            evidence_ref=f"discovery:azure_{sub_id}.observability.firewalls_with_diagnostics",
        )


@rule(
    id=R_AZ_TRAFFIC_ANALYTICS_MISSING,
    title="Flow log is enabled but Traffic Analytics is disabled",
    severity=FindingSeverity.MEDIUM,
    category="Monitoring & Visibility",
    version=2,
    learn_url=_LEARN_TRAFFIC_ANALYTICS,
    frameworks=(
        fw.WAF_NS2,
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "Traffic Analytics provides flow-level visibility for zero trust verification",
        ),
    ),
    applies_to="export",
    evidence="flow_logs[].traffic_analytics_enabled (networkwatchers/flowlogs rows; unknown when an export "
    "has none); observability.traffic_analytics_enabled when a live collector ran",
)
def traffic_analytics_missing(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation | NotEvaluable]:
    sub_id = sub.subscription_id
    if _export_without_flow_logs(topology):
        yield NotEvaluable(_NO_FLOW_LOG_ROWS)
        return
    for flow_log in sub.flow_logs:
        if flow_log.enabled and not flow_log.traffic_analytics_enabled:
            yield Observation(
                resource_id=flow_log.id,
                resource_type="Microsoft.Network/networkWatchers/flowLogs",
                fact=f"Flow log {flow_log.name} targeting {flow_log.target_resource_id} is enabled "
                f"with Traffic Analytics disabled.",
                evidence_ref=f"discovery:azure_{sub_id}.flow_logs[id={flow_log.id}]"
                f".traffic_analytics_enabled",
            )
    obs = sub.observability
    if obs and obs.nsg_flow_logs_enabled > 0 and obs.traffic_analytics_enabled == 0:
        yield Observation(
            resource_id=sub_id,
            resource_type="Microsoft.Network/networkSecurityGroups",
            title="NSG Flow Logs are enabled but Traffic Analytics is disabled",
            fact=f"Subscription has {obs.nsg_flow_logs_enabled} active flow logs, but "
            f"{obs.traffic_analytics_enabled} have Traffic Analytics enabled.",
            evidence_ref=f"discovery:azure_{sub_id}.observability",
        )


@rule(
    id=R_AZ_BASTION_NO_DIAGNOSTICS,
    title="Azure Bastion lacks session audit logging",
    severity=FindingSeverity.MEDIUM,
    category="Observability",
    version=1,
    learn_url=_LEARN_BASTION_LOGS,
    frameworks=(
        fw.WAF_PA2,
        fw.NIST_DE_CM_3,
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "Session logging provides audit trail for privileged access paths",
        ),
    ),
    applies_to="live-only",
    inputs=("observability",),
    evidence="observability.bastion_with_diagnostics",
)
def bastion_without_diagnostics(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    obs = sub.observability
    if not obs:
        return
    if obs.bastion_total > 0 and obs.bastion_with_diagnostics < obs.bastion_total:
        missing = obs.bastion_total - obs.bastion_with_diagnostics
        yield Observation(
            resource_id=sub_id,
            resource_type="Microsoft.Network/bastionHosts",
            fact=f"{missing} of {obs.bastion_total} Bastion host(s) in subscription {sub_id} "
            f"have no Log Analytics diagnostic sink. SSH/RDP session audit trails are "
            f"unavailable.",
            evidence_ref=f"discovery:azure_{sub_id}.observability.bastion_with_diagnostics",
        )


@rule(
    id=R_AZ_ER_SATURATION,
    title="ExpressRoute circuit bandwidth utilization exceeds 80%",
    severity=FindingSeverity.HIGH,
    category="Performance",
    version=1,
    learn_url=_LEARN_ER_MONITOR,
    frameworks=(
        fw.WAF_PE3,
        fw.FEDRAMP_CP8,
        fw.cisa(
            "3.4", fw.CISA_RESILIENCE, "Circuit saturation degrades hybrid connectivity reliability"
        ),
    ),
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.er_circuit_metrics[]",
)
def expressroute_saturation(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    for em in metrics.er_circuit_metrics:
        max_util = max(
            filter(None, [em.primary_utilization_pct, em.secondary_utilization_pct]),
            default=None,
        )
        if max_util and max_util > _HIGH_UTILIZATION_PCT:
            yield Observation(
                resource_id=sub_id,
                resource_type="Microsoft.Network/expressRouteCircuits",
                fact=f"ER circuit {em.circuit_name} primary utilization is "
                f"{em.primary_utilization_pct}% "
                f"(provisioned {em.bandwidth_mbps_provisioned} Mbps). "
                f"At this rate the circuit will saturate under load.",
                evidence_ref=f"discovery:azure_{sub_id}.network_metrics.er_circuit_metrics",
            )


@rule(
    id=R_AZ_DDOS_ATTACK_DETECTED,
    title="Active or recent DDoS attack detected on public IP resources",
    severity=FindingSeverity.CRITICAL,
    category="Network Protection",
    version=1,
    learn_url=_LEARN_DDOS,
    frameworks=(
        fw.WAF_NS4,
        fw.FEDRAMP_SC5,
        fw.hipaa("(a)(2)(ii) — Contingency operations: protect ePHI availability during attack"),
        fw.cisa(
            "3.4", fw.CISA_RESILIENCE, "Active DDoS attack directly threatens network resilience"
        ),
    ),
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.ddos_attack_events_24h",
)
def ddos_attack_detected(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    if metrics.ddos_attack_events_24h > 0:
        ips = ", ".join(metrics.public_ips_under_ddos_attack[:5])
        yield Observation(
            resource_id=sub_id,
            resource_type="Microsoft.Network/publicIPAddresses",
            fact=f"Azure Monitor reported IfUnderDDoSAttack > 0 on "
            f"{metrics.ddos_attack_events_24h} public IP(s) "
            f"in the last 24 hours. Affected IPs: {ips or 'unknown'}.",
            evidence_ref=f"discovery:azure_{sub_id}.network_metrics.ddos_attack_events_24h",
        )


@rule(
    id=R_AZ_FRONTDOOR_WAF_DETECTION_MODE,
    title="Front Door WAF policy is in Detection mode, not Prevention",
    severity=FindingSeverity.MEDIUM,
    category="Application Security",
    version=1,
    learn_url=_LEARN_FRONTDOOR_WAF,
    frameworks=(
        fw.WAF_NS4,
        fw.PCI_1_3,
        fw.FEDRAMP_SC7,
        fw.cisa("3.2", fw.CISA_TRAFFIC, "WAF in Detection mode does not block malicious traffic"),
        fw.cisa(
            "4.0",
            "Application and Workload Protection",
            "Detection-only WAF does not enforce blocking for application-layer attacks",
            pillar="Applications and Workloads",
        ),
    ),
    applies_to="export",
    evidence="front_door_waf_policies[].policy_mode",
)
def front_door_waf_detection_mode(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for policy in sub.front_door_waf_policies:
        if str(policy.policy_mode).lower() == "detection":
            yield Observation(
                resource_id=policy.id,
                resource_type="Microsoft.Network/frontDoorWebApplicationFirewallPolicies",
                region=policy.location,
                fact=f"Front Door WAF policy {policy.name} is in Detection mode. "
                f"Malicious requests are logged but not blocked. "
                f"Custom rules: {policy.custom_rules_count}, "
                f"Managed rule sets: {policy.managed_rules_count}.",
                evidence_ref=f"discovery:azure_{sub_id}"
                f".front_door_waf_policies[id={policy.id}].policy_mode",
            )


@rule(
    id=R_AZ_APPGW_HIGH_LATENCY,
    title="Application Gateway reports high backend latency or elevated failure rate",
    severity=FindingSeverity.HIGH,
    category="Performance",
    version=1,
    learn_url=_LEARN_APPGW_METRICS,
    frameworks=(
        fw.WAF_RE4_CAPACITY,
        fw.cisa(
            "3.4", fw.CISA_RESILIENCE, "App Gateway capacity degradation indicates resilience gap"
        ),
    ),
    applies_to="live-only",
    inputs=("network_metrics",),
    evidence="network_metrics.appgw_metrics[]",
)
def application_gateway_high_latency(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    metrics = sub.network_metrics
    if not metrics:
        return
    for agm in metrics.appgw_metrics:
        if agm.collection_error:
            continue
        latency_breach = (
            agm.backend_latency_ms_avg is not None
            and agm.backend_latency_ms_avg > _APPGW_LATENCY_THRESHOLD_MS
        )
        has_requests = bool(agm.total_requests_24h) and agm.total_requests_24h > 0
        failure_rate_high = (
            has_requests
            and bool(agm.failed_requests_24h)
            and (agm.failed_requests_24h / agm.total_requests_24h) > _APPGW_FAILURE_RATE_THRESHOLD
        )
        if not (latency_breach or failure_rate_high):
            continue
        latency_str = f"{agm.backend_latency_ms_avg:.0f}ms" if agm.backend_latency_ms_avg else "N/A"
        fail_pct = (
            f"{(agm.failed_requests_24h / agm.total_requests_24h * 100):.1f}%"
            if agm.total_requests_24h and agm.failed_requests_24h
            else "N/A"
        )
        yield Observation(
            resource_id=agm.appgw_name,
            resource_type="Microsoft.Network/applicationGateways",
            fact=f"App Gateway {agm.appgw_name}: avg backend latency "
            f"{latency_str} (threshold 2000ms), failure rate {fail_pct} "
            f"(threshold 5%). WAF rule hits (24h): {agm.waf_rule_hits_24h}.",
            evidence_ref=f"discovery:azure_{sub_id}.network_metrics"
            f".appgw_metrics[name={agm.appgw_name}]",
        )


# ---------------------------------------------------------------------------
# AZ-NET-020..033 — the checks Engine B alone carried (plan table 7.B)
# ---------------------------------------------------------------------------


@rule(
    id=R_AZ_NSG_REMOTE_ACCESS_FROM_INTERNET,
    title="NSG allows RDP/SSH inbound from Internet",
    severity=FindingSeverity.CRITICAL,
    category="Remote Access",
    version=1,
    learn_url=_LEARN_NSG,
    frameworks=(
        fw.WAF_NS1,
        fw.cis("6.1 / 6.2 — RDP and SSH access restricted from the internet"),
        fw.PCI_1_3,
        fw.FEDRAMP_SC7,
        fw.cisa(
            "3.2", fw.CISA_TRAFFIC, "Management ports open to the internet bypass traffic control"
        ),
    ),
    applies_to="export",
    evidence="nsgs[].security_rules[] (Allow, Inbound, internet source, port 22 or 3389)",
)
def nsg_allows_remote_access_from_internet(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for nsg in sub.nsgs:
        for nsg_rule in nsg.security_rules:
            if nsg_rule.access.lower() != "allow" or nsg_rule.direction.lower() != "inbound":
                continue
            if not _from_internet(nsg_rule):
                continue
            exposed = sorted(_exposed_ports(nsg_rule))
            if not exposed:
                continue
            ports = ", ".join(str(p) for p in exposed)
            yield Observation(
                resource_id=_nsg_rule_id(nsg.id, nsg_rule),
                resource_type="Microsoft.Network/networkSecurityGroups/securityRules",
                region=nsg.location,
                fact=f"NSG {nsg.name} rule {nsg_rule.name} (priority {nsg_rule.priority}) allows "
                f"inbound traffic on port(s) {ports} from {', '.join(_sources(nsg_rule))}.",
                evidence_ref=f"discovery:azure_{sub_id}.nsgs[id={nsg.id}]"
                f".security_rules[name={nsg_rule.name}]",
                description="Direct RDP/SSH exposure to the internet is a primary vector for "
                "brute-force and ransomware campaigns.",
                recommendation="Remove the internet source from the rule. Use Azure Bastion for "
                "browser-based access, or restrict the source to corporate IP ranges, and use "
                "just-in-time VM access where Microsoft Defender for Cloud is enabled.",
                affected_resources=(nsg.id,),
            )


@rule(
    id=R_AZ_NSG_WILDCARD_ALLOW_ALL,
    title="NSG wildcard allow-all rule",
    severity=FindingSeverity.HIGH,
    category="Network Segmentation",
    version=1,
    learn_url=_LEARN_NSG,
    frameworks=(
        fw.WAF_NS1,
        fw.PCI_1_2,
        fw.ISO_8_22,
        fw.FEDRAMP_SC7,
        fw.cisa(
            "3.1",
            fw.CISA_SEGMENTATION,
            "An allow-all rule removes the segmentation an NSG exists for",
        ),
    ),
    applies_to="export",
    evidence="nsgs[].security_rules[] (Allow, any source, any port, any protocol)",
)
def nsg_wildcard_allow_all(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for nsg in sub.nsgs:
        for nsg_rule in nsg.security_rules:
            if nsg_rule.access.lower() != "allow":
                continue
            if not (
                _from_internet(nsg_rule)
                and _allows_all_ports(nsg_rule)
                and _is_wildcard(nsg_rule.protocol)
            ):
                continue
            yield Observation(
                resource_id=_nsg_rule_id(nsg.id, nsg_rule),
                resource_type="Microsoft.Network/networkSecurityGroups/securityRules",
                region=nsg.location,
                fact=f"NSG {nsg.name} rule {nsg_rule.name} (priority {nsg_rule.priority}) allows "
                f"all {nsg_rule.direction.lower()} traffic from "
                f"{', '.join(_sources(nsg_rule))} to "
                f"{nsg_rule.destination_address_prefix or 'any destination'} on all ports "
                f"and protocols.",
                evidence_ref=f"discovery:azure_{sub_id}.nsgs[id={nsg.id}]"
                f".security_rules[name={nsg_rule.name}]",
                description="The rule disables network-layer access control for every flow it "
                "matches.",
                recommendation="Replace the wildcard rule with rules that permit only the required "
                "source ranges, ports and protocols; deny by default and allow explicitly.",
                affected_resources=(nsg.id,),
            )


@rule(
    id=R_AZ_UDR_DEFAULT_ROUTE_INTERNET,
    title="Route table default route to Internet",
    severity=FindingSeverity.MEDIUM,
    category="Routing & Transit",
    version=1,
    learn_url=_LEARN_UDR,
    frameworks=(
        fw.WAF_NS1,
        fw.asb("NS-4"),
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "A direct default route sends egress around the inspection point",
        ),
    ),
    applies_to="export",
    evidence="route_tables[].routes[] (0.0.0.0/0 → Internet)",
)
def route_table_default_route_to_internet(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for rt in _route_tables(sub):
        direct = [
            r
            for r in rt.routes
            if r.address_prefix == _DEFAULT_ROUTE and r.next_hop_type == _NEXT_HOP_INTERNET
        ]
        if not direct:
            continue
        names = ", ".join(r.name for r in direct)
        yield Observation(
            resource_id=rt.id,
            resource_type="Microsoft.Network/routeTables",
            region=rt.location,
            fact=f"Route table {rt.name} has a default route (0.0.0.0/0) with next hop "
            f"Internet ({names}); it is associated with "
            f"{len(rt.associated_subnet_ids)} subnet(s).",
            evidence_ref=f"discovery:azure_{sub_id}.route_tables[id={rt.id}].routes",
            description="Traffic from the associated subnets leaves directly to the Internet "
            "without passing a firewall or NVA.",
            recommendation="Point the default route at the Azure Firewall or NVA private IP for "
            "centralised egress inspection; keep a direct Internet next hop only on dedicated "
            "egress subnets with a documented reason.",
            affected_resources=tuple(rt.associated_subnet_ids),
        )


@rule(
    id=R_AZ_UDR_BGP_PROPAGATION_DISABLED,
    title="BGP route propagation disabled on route table",
    severity=FindingSeverity.INFORMATIONAL,
    category="Routing & Transit",
    version=1,
    learn_url=_LEARN_UDR,
    frameworks=(
        fw.WAF_RE3,
        fw.cisa(
            "3.4", fw.CISA_RESILIENCE, "Static-only routing loses learned on-premises prefixes"
        ),
    ),
    applies_to="export",
    evidence="route_tables[].disable_bgp_route_propagation",
)
def route_table_bgp_propagation_disabled(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for rt in _route_tables(sub):
        if not rt.disable_bgp_route_propagation:
            continue
        yield Observation(
            resource_id=rt.id,
            resource_type="Microsoft.Network/routeTables",
            region=rt.location,
            fact=f"Route table {rt.name} has disable_bgp_route_propagation=True; it is "
            f"associated with {len(rt.associated_subnet_ids)} subnet(s).",
            evidence_ref=f"discovery:azure_{sub_id}.route_tables[id={rt.id}]"
            f".disable_bgp_route_propagation",
            description="Routes learned over VPN or ExpressRoute are not added to the associated "
            "subnets; on-premises prefixes reach them only through static routes.",
            recommendation="Confirm the setting is intentional. Where the subnets need on-premises "
            "connectivity, enable BGP route propagation or add static routes for every "
            "on-premises prefix.",
            affected_resources=tuple(rt.associated_subnet_ids),
        )


@rule(
    id=R_AZ_VNET_CUSTOM_DNS,
    title="VNet uses custom DNS servers",
    severity=FindingSeverity.INFORMATIONAL,
    category="DNS & Name Resolution",
    version=1,
    learn_url=_LEARN_VNET_DNS,
    frameworks=(
        fw.WAF_RE3,
        fw.cisa(
            "3.2", fw.CISA_TRAFFIC, "Name resolution is on the path of every private-endpoint flow"
        ),
    ),
    applies_to="export",
    evidence="vnets[].dns_servers",
)
def vnet_custom_dns_servers(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for vnet in sub.vnets:
        custom = [d for d in vnet.dns_servers if d != _AZURE_PROVIDED_DNS]
        if not custom:
            continue
        yield Observation(
            resource_id=vnet.id,
            resource_type="Microsoft.Network/virtualNetworks",
            region=vnet.location,
            fact=f"VNet {vnet.name} ({vnet.location}) uses custom DNS servers: {', '.join(custom)}.",
            evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}].dns_servers",
            description="Private DNS zone resolution for private endpoints depends on these "
            "servers forwarding to Azure DNS.",
            recommendation="Confirm the custom DNS servers forward Azure Private DNS zones through "
            "168.63.129.16 and are highly available; Azure DNS Private Resolver is the managed "
            "alternative.",
        )


@rule(
    id=R_AZ_APPGW_WAF_DETECTION_MODE,
    title="Application Gateway WAF in Detection mode",
    severity=FindingSeverity.MEDIUM,
    category="Application Security",
    version=1,
    learn_url=_LEARN_APPGW_WAF,
    frameworks=(
        fw.WAF_NS4,
        fw.PCI_1_3,
        fw.cisa("3.2", fw.CISA_TRAFFIC, "WAF in Detection mode does not block malicious traffic"),
        fw.cisa(
            "4.0",
            "Application and Workload Protection",
            "Detection-only WAF does not enforce blocking for application-layer attacks",
            pillar="Applications and Workloads",
        ),
    ),
    applies_to="export",
    evidence="application_gateways[].waf_mode",
)
def application_gateway_waf_detection_mode(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for agw in sub.application_gateways:
        if not agw.waf_enabled or not agw.waf_mode:
            continue
        if agw.waf_mode.lower() == _WAF_PREVENTION:
            continue
        yield Observation(
            resource_id=agw.id,
            resource_type="Microsoft.Network/applicationGateways",
            region=agw.location,
            fact=f"Application Gateway {agw.name} ({agw.sku_name}) has WAF enabled in "
            f"{agw.waf_mode} mode.",
            evidence_ref=f"discovery:azure_{sub_id}.application_gateways[id={agw.id}].waf_mode",
            description="Matching requests are logged and not blocked, so the WAF inspects "
            "without protecting.",
            recommendation="After tuning the Detection-mode log for false positives, switch the WAF "
            "policy to Prevention with a current OWASP core rule set.",
        )


@rule(
    id=R_AZ_LB_BASIC_SKU,
    title="Load balancer uses the Basic SKU",
    severity=FindingSeverity.MEDIUM,
    category="Resilience",
    version=1,
    learn_url=_LEARN_LB_SKUS,
    frameworks=(
        fw.WAF_RE3,
        fw.cisa(
            "3.4", fw.CISA_RESILIENCE, "Basic load balancers carry no SLA and no zone redundancy"
        ),
    ),
    applies_to="export",
    evidence="load_balancers[].sku_name",
)
def load_balancer_basic_sku(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for lb in sub.load_balancers:
        if lb.sku_name.lower() != _SKU_BASIC:
            continue
        yield Observation(
            resource_id=lb.id,
            resource_type="Microsoft.Network/loadBalancers",
            region=lb.location,
            fact=f"Load balancer {lb.name} ({lb.lb_type}) in {lb.location} has sku_name=Basic.",
            evidence_ref=f"discovery:azure_{sub_id}.load_balancers[id={lb.id}].sku_name",
            description="The Basic SKU has no SLA, no zone redundancy and no HTTPS health probes, "
            "and Microsoft retired it on 30 September 2025 (Microsoft Learn, read 2026-10-25).",
            recommendation="Upgrade to the Standard SKU, which is secure by default (closed without "
            "an NSG), supports zone redundancy and HA ports.",
        )


@rule(
    id=R_AZ_PIP_BASIC_SKU,
    title="Public IP uses the Basic SKU",
    severity=FindingSeverity.MEDIUM,
    category="Resilience",
    version=1,
    learn_url=_LEARN_PIP_SKUS,
    frameworks=(
        fw.WAF_RE3,
        fw.WAF_NS1,
        fw.cisa(
            "3.4", fw.CISA_RESILIENCE, "Basic public IPs are open by default and not zone-redundant"
        ),
    ),
    applies_to="export",
    evidence="public_ips[].sku_name",
)
def public_ip_basic_sku(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for pip in sub.public_ips:
        if pip.sku_name.lower() != _SKU_BASIC:
            continue
        attached = pip.associated_resource_type or "no resource"
        yield Observation(
            resource_id=pip.id,
            resource_type="Microsoft.Network/publicIPAddresses",
            region=pip.location,
            fact=f"Public IP {pip.name} in {pip.location} has sku_name=Basic and is attached "
            f"to {attached}.",
            evidence_ref=f"discovery:azure_{sub_id}.public_ips[id={pip.id}].sku_name",
            description="Basic public IPs are open by default, not zone-redundant, and Microsoft "
            "retired them on 30 September 2025 (Microsoft Learn, read 2026-10-25).",
            recommendation="Upgrade the public IP to the Standard SKU, which requires an NSG for "
            "inbound traffic and supports availability zones.",
        )


@rule(
    id=R_AZ_VPN_GW_BASIC_SKU,
    title="VPN gateway uses the Basic SKU",
    severity=FindingSeverity.HIGH,
    category="Gateway",
    version=1,
    learn_url=_LEARN_VPN_GW_SKUS,
    frameworks=(
        fw.WAF_RE3,
        fw.FEDRAMP_CP8_REDUNDANCY,
        fw.cisa(
            "3.4",
            fw.CISA_RESILIENCE,
            "A Basic VPN gateway has no SLA, no BGP and no zone redundancy",
        ),
    ),
    applies_to="export",
    evidence="virtual_network_gateways[].sku_name (gateway_type Vpn)",
)
def vpn_gateway_basic_sku(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for gw in sub.virtual_network_gateways:
        if gw.gateway_type != _GATEWAY_TYPE_VPN:
            continue
        sku = gw.sku_name or gw.sku_tier
        if sku.lower() != _SKU_BASIC:
            continue
        yield Observation(
            resource_id=gw.id,
            resource_type="Microsoft.Network/virtualNetworkGateways",
            region=gw.location,
            fact=f"VPN gateway {gw.name} in {gw.location} has sku_name=Basic.",
            evidence_ref=f"discovery:azure_{sub_id}.virtual_network_gateways[id={gw.id}].sku_name",
            description="The Basic SKU is limited to 100 Mbps aggregate throughput and supports "
            "neither BGP, active-active mode nor availability zones, and carries no SLA.",
            recommendation="Resize to VpnGw2 or higher (Generation 2); choose an AZ SKU such as "
            "VpnGw2AZ for zone redundancy, then enable BGP and active-active mode.",
        )


@rule(
    id=R_AZ_VPN_GW_GENERATION1,
    title="VPN gateway is Generation 1",
    severity=FindingSeverity.LOW,
    category="Gateway",
    version=1,
    learn_url=_LEARN_VPN_GW_SKUS,
    frameworks=(
        fw.WAF_PE3,
        fw.cisa("3.4", fw.CISA_RESILIENCE, "Generation 1 gateways cap hybrid throughput"),
    ),
    applies_to="export",
    evidence="virtual_network_gateways[].generation (gateway_type Vpn)",
)
def vpn_gateway_generation1(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for gw in sub.virtual_network_gateways:
        if gw.gateway_type != _GATEWAY_TYPE_VPN or not gw.generation:
            continue
        if "generation1" not in gw.generation.replace(" ", "").lower():
            continue
        yield Observation(
            resource_id=gw.id,
            resource_type="Microsoft.Network/virtualNetworkGateways",
            region=gw.location,
            fact=f"VPN gateway {gw.name} (SKU: {gw.sku_name}) reports generation={gw.generation}.",
            evidence_ref=f"discovery:azure_{sub_id}.virtual_network_gateways[id={gw.id}].generation",
            description="Generation 1 SKUs top out at 1.25 Gbps aggregate throughput; Generation 2 "
            "SKUs reach 10 Gbps (VpnGw5; Microsoft Learn SKU table, read 2026-10-25).",
            recommendation="Resize to a Generation 2 SKU (VpnGw2 to VpnGw5, or their AZ variants) "
            "in a maintenance window.",
        )


@rule(
    id=R_AZ_GW_CONNECTION_NOT_CONNECTED,
    title="Gateway connection is not Connected",
    severity=FindingSeverity.HIGH,
    category="Connectivity",
    version=1,
    learn_url=_LEARN_VPN_GW_TROUBLESHOOT,
    frameworks=(
        fw.WAF_RE3,
        fw.FEDRAMP_CP8,
        fw.cisa("3.4", fw.CISA_RESILIENCE, "A down tunnel removes a hybrid connectivity path"),
    ),
    applies_to="export",
    evidence="virtual_network_gateways[].connections[].connection_status",
)
def gateway_connection_not_connected(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for gw in sub.virtual_network_gateways:
        for conn in gw.connections:
            if conn.connection_status.lower() in _CONNECTED_STATES:
                continue
            yield Observation(
                resource_id=conn.id,
                resource_type="Microsoft.Network/connections",
                region=gw.location,
                fact=f"Connection {conn.name} ({conn.connection_type}) on gateway {gw.name} "
                f"has connection_status={conn.connection_status}.",
                evidence_ref=f"discovery:azure_{sub_id}.virtual_network_gateways[id={gw.id}]"
                f".connections[name={conn.name}].connection_status",
                description="Traffic for this connection's remote prefixes has no tunnel to use.",
                recommendation="Check the connection in the portal and the on-premises device logs; "
                "confirm the pre-shared key, IKE parameters and that UDP 500/4500 are allowed.",
                affected_resources=(gw.id,),
            )


@rule(
    id=R_AZ_PE_CONNECTION_PENDING,
    title="Private endpoint connection is Pending",
    severity=FindingSeverity.MEDIUM,
    category="Connectivity",
    version=1,
    learn_url=_LEARN_PRIVATE_ENDPOINT,
    frameworks=(
        fw.WAF_NS1,
        fw.cisa(
            "3.1", fw.CISA_SEGMENTATION, "An unapproved private link leaves the private path unused"
        ),
    ),
    applies_to="export",
    evidence="private_endpoints[].service_connections[].connection_state",
)
def private_endpoint_connection_pending(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    for pe in sub.private_endpoints:
        for sc in pe.service_connections:
            if sc.connection_state.lower() != _PENDING:
                continue
            target = sc.private_link_service_id.rsplit("/", 1)[-1] or sc.private_link_service_id
            yield Observation(
                resource_id=f"{pe.id}/privateLinkServiceConnections/{sc.connection_name}",
                resource_type="Microsoft.Network/privateEndpoints",
                region=pe.location,
                fact=f"Private endpoint {pe.name} connection {sc.connection_name} to {target} "
                f"has connection_state=Pending.",
                evidence_ref=f"discovery:azure_{sub_id}.private_endpoints[id={pe.id}]"
                f".service_connections[name={sc.connection_name}].connection_state",
                description="Traffic to the private service does not flow until the connection "
                "is approved.",
                recommendation="Approve the pending connection on the target resource's private "
                "endpoint connections blade after confirming the request comes from the "
                "expected subscription.",
                affected_resources=(pe.id,),
            )


@rule(
    id=R_AZ_NO_FIREWALL,
    title="No Azure Firewall with VNets present",
    severity=FindingSeverity.MEDIUM,
    category="Network Security",
    version=1,
    learn_url=_LEARN_FIREWALL,
    frameworks=(
        fw.WAF_NS4,
        fw.WAF_NS3,
        fw.PCI_1_3,
        fw.cisa(
            "3.2",
            fw.CISA_TRAFFIC,
            "Without a central inspection point, traffic management is per NSG",
        ),
    ),
    applies_to="export",
    evidence="firewalls[], virtual_wans[].hubs[].azure_firewall_id, route_tables[].routes[]",
)
def no_firewall_with_vnets(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    if not sub.vnets or sub.firewalls:
        return
    if _has_secured_hub(sub) or _has_nva_default_route(sub):
        return
    label = sub.subscription_name or sub_id
    yield Observation(
        resource_id=_subscription_resource_id(sub),
        resource_type="Microsoft.Network/azureFirewalls",
        fact=f"Subscription {label} has {len(sub.vnets)} VNet(s), no Azure Firewall, no secured "
        f"Virtual WAN hub and no 0.0.0.0/0 route to a VirtualAppliance.",
        evidence_ref=f"discovery:azure_{sub_id}.firewalls",
        description="East-west and north-south traffic in this subscription passes no central "
        "inspection point.",
        recommendation="Deploy Azure Firewall (Standard or Premium) in a hub VNet or a secured "
        "Virtual WAN hub, route spoke subnets through it with UDRs, and set Threat "
        "Intelligence to Deny.",
        affected_resources=tuple(v.id for v in sub.vnets),
    )


@rule(
    id=R_AZ_NO_BASTION,
    title="No Azure Bastion with VNets present",
    severity=FindingSeverity.LOW,
    category="Remote Access",
    version=1,
    learn_url=_LEARN_BASTION,
    frameworks=(
        fw.WAF_PA2,
        fw.cisa("3.2", fw.CISA_TRAFFIC, "Bastion keeps management traffic off public endpoints"),
    ),
    applies_to="export",
    evidence="bastion_hosts[]",
    needs_properties=False,
)
def no_bastion_with_vnets(
    sub: AzureSubscriptionTopology, topology: AzureTopology
) -> Iterator[Observation]:
    sub_id = sub.subscription_id
    if not sub.vnets or sub.bastion_hosts:
        return
    label = sub.subscription_name or sub_id
    yield Observation(
        resource_id=_subscription_resource_id(sub),
        resource_type="Microsoft.Network/bastionHosts",
        fact=f"Subscription {label} has {len(sub.vnets)} VNet(s) and no Azure Bastion host.",
        evidence_ref=f"discovery:azure_{sub_id}.bastion_hosts",
        description="RDP/SSH access to VMs in this subscription needs a public IP, a VPN or a "
        "just-in-time path instead of a browser-based bastion.",
        recommendation="Deploy Azure Bastion (Standard SKU) for RDP/SSH without exposing VMs to the "
        "Internet.",
        affected_resources=tuple(v.id for v in sub.vnets),
    )
