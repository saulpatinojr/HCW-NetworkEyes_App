"""Topology data contracts — bridge between discovery (Phase C) and diagram engine (Phase B).

Version 1.3.0 — Phase E discovery gap-fill.
  Added Azure: AzureRouteServerBgpConnection, AzureRouteServer
  Expanded: AzureSubscriptionTopology (route_servers),
            ObservabilityData (metric_alert_count, activity_log_alert_count,
            appgw_with_diagnostics/appgw_total, lb_with_diagnostics/lb_total)
  All new fields are Optional with defaults so v1.2.x data remains valid.

Version 1.2.0 — Comprehensive Azure network data expansion.
  Added Azure: NSGSecurityRule, AzureNSG, AzurePublicIP, AzureLBFrontendIP,
               AzureLBRule, AzureLoadBalancer, AzureGatewayConnection,
               AzureVirtualNetworkGateway, AzurePrivateEndpoint,
               AzureNatGateway, AzureBastionHost
  Expanded: AzureSubnet (nsg_name, route_table_name, nat_gateway_id,
            default_outbound_access, private_link_service_network_policies),
            VNet (dns_servers, flow_logs_enabled, ddos_protection_plan_id,
            encryption_enabled),
            AzureSubscriptionTopology (nsgs, route_tables,
            virtual_network_gateways, load_balancers, public_ips,
            private_endpoints, nat_gateways, bastion_hosts)
  Added AWS: SecurityGroup, NACL, VpnGateway, NetworkFirewallPolicy
  All new fields are Optional with default_factory so v1.x data remains valid.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

TOPOLOGY_SCHEMA_VERSION = "1.3.0"


# ── Enums ──────────────────────────────────────────────────────────────────


class SubnetType(StrEnum):
    PUBLIC = "public"
    PRIVATE = "private"
    ISOLATED = "isolated"
    UNKNOWN = "unknown"


class AttachmentType(StrEnum):
    VPC = "vpc"
    VPN = "vpn"
    DIRECT_CONNECT = "direct_connect"
    PEERING = "peering"
    CONNECT = "connect"


class PeeringState(StrEnum):
    ACTIVE = "active"
    PENDING = "pending"
    REJECTED = "rejected"
    EXPIRED = "expired"
    DELETED = "deleted"


# ── AWS primitives ─────────────────────────────────────────────────────────


class RouteEntry(BaseModel):
    destination: str
    target: str
    target_type: str
    state: str = "active"


class RouteTable(BaseModel):
    id: str
    name: str | None = None
    associated_subnet_ids: list[str] = Field(default_factory=list)
    routes: list[RouteEntry] = Field(default_factory=list)
    is_main: bool = False


class SecurityGroupRule(BaseModel):
    rule_id: str | None = None
    direction: str  # "ingress" | "egress"
    protocol: str  # tcp | udp | icmp | -1 (all)
    from_port: int | None = None
    to_port: int | None = None
    cidr_ranges: list[str] = Field(default_factory=list)
    source_sg_id: str | None = None
    description: str | None = None


class SecurityGroup(BaseModel):
    id: str
    name: str | None = None
    description: str | None = None
    vpc_id: str
    rules: list[SecurityGroupRule] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)


class NACLEntry(BaseModel):
    rule_number: int
    protocol: str
    rule_action: str  # "allow" | "deny"
    cidr: str
    from_port: int | None = None
    to_port: int | None = None
    egress: bool


class NACL(BaseModel):
    id: str
    name: str | None = None
    vpc_id: str
    is_default: bool = False
    entries: list[NACLEntry] = Field(default_factory=list)
    associated_subnet_ids: list[str] = Field(default_factory=list)


class VpnGateway(BaseModel):
    id: str
    name: str | None = None
    state: str
    type: str = "ipsec.1"
    amazon_side_asn: int | None = None
    vpc_id: str | None = None


class NetworkFirewallPolicy(BaseModel):
    arn: str
    name: str
    vpc_id: str
    firewall_subnet_ids: list[str] = Field(default_factory=list)
    stateful_rule_group_arns: list[str] = Field(default_factory=list)
    stateless_rule_group_arns: list[str] = Field(default_factory=list)


class Subnet(BaseModel):
    id: str
    name: str | None = None
    cidr: str
    az: str
    subnet_type: SubnetType = SubnetType.UNKNOWN
    route_table_id: str | None = None
    nacl_id: str | None = None
    auto_assign_public_ip: bool = False


class InternetGateway(BaseModel):
    id: str
    name: str | None = None
    state: str = "attached"


class NatGateway(BaseModel):
    id: str
    name: str | None = None
    subnet_id: str
    state: str
    public_ip: str | None = None


class VpcPeeringConnection(BaseModel):
    id: str
    name: str | None = None
    requester_vpc_id: str
    requester_account_id: str
    requester_region: str
    accepter_vpc_id: str
    accepter_account_id: str
    accepter_region: str
    state: PeeringState


class VPC(BaseModel):
    id: str
    name: str | None = None
    cidr: str
    secondary_cidrs: list[str] = Field(default_factory=list)
    is_default: bool = False
    subnets: list[Subnet] = Field(default_factory=list)
    route_tables: list[RouteTable] = Field(default_factory=list)
    internet_gateways: list[InternetGateway] = Field(default_factory=list)
    nat_gateways: list[NatGateway] = Field(default_factory=list)
    peering_connections: list[VpcPeeringConnection] = Field(default_factory=list)
    security_groups: list[SecurityGroup] = Field(default_factory=list)
    nacls: list[NACL] = Field(default_factory=list)
    flow_logs_enabled: bool = False
    tags: dict = Field(default_factory=dict)


class TGWAttachment(BaseModel):
    id: str
    resource_id: str
    resource_type: AttachmentType
    resource_owner_account_id: str
    state: str
    association_route_table_id: str | None = None


class TransitGateway(BaseModel):
    id: str
    name: str | None = None
    owner_account_id: str
    amazon_side_asn: int | None = None
    attachments: list[TGWAttachment] = Field(default_factory=list)
    route_table_ids: list[str] = Field(default_factory=list)
    dns_support: bool = True
    vpn_ecmp_support: bool = True
    default_route_table_association: bool = True
    default_route_table_propagation: bool = True


class DirectConnectConnection(BaseModel):
    id: str
    name: str | None = None
    location: str
    bandwidth: str
    state: str
    owner_account_id: str


class AWSAccount(BaseModel):
    account_id: str
    account_name: str | None = None
    ou_id: str | None = None
    ou_name: str | None = None
    is_management_account: bool = False


class AWSNetworkFirewall(BaseModel):
    """AWS Network Firewall resource — richer than the legacy NetworkFirewallPolicy stub."""

    firewall_arn: str
    firewall_name: str
    vpc_id: str
    firewall_policy_arn: str | None = None
    subnet_mappings: list[str] = Field(default_factory=list)  # subnet IDs
    delete_protection: bool = False
    subnet_change_protection: bool = False
    firewall_policy_change_protection: bool = False
    firewall_status: str = "READY"  # READY | CREATING | DELETING | ...
    logging_s3_enabled: bool = False
    logging_cloudwatch_enabled: bool = False
    logging_kinesis_enabled: bool = False
    tags: dict = Field(default_factory=dict)


class AWSWAFWebACL(BaseModel):
    """AWS WAF v2 Web ACL (regional or CloudFront)."""

    web_acl_id: str
    web_acl_arn: str
    name: str
    scope: str = "REGIONAL"  # "REGIONAL" | "CLOUDFRONT"
    default_action: str = "Allow"  # "Allow" | "Block"
    managed_rule_groups_count: int = 0
    custom_rules_count: int = 0
    associated_resource_arns: list[str] = Field(default_factory=list)
    sampled_requests_enabled: bool = False
    cloudwatch_metrics_enabled: bool = False
    tags: dict = Field(default_factory=dict)


class AWSSecurityFinding(BaseModel):
    """A single AWS security-posture finding.

    Cross-service analog of Azure's DefenderAssessment — normalizes findings from
    Security Hub, GuardDuty, and Config into one actionable shape so the AWS path
    reports security posture the same way the Azure path reports Defender
    assessments. Observed state only (DD-002): no inferred severities.
    """

    finding_id: str
    source: str = "SecurityHub"  # "SecurityHub" | "GuardDuty" | "Config"
    title: str
    description: str | None = None
    remediation: str | None = None
    status: str = "ACTIVE"  # normalized record/workflow state
    severity: str = "MEDIUM"  # "INFORMATIONAL" | "LOW" | "MEDIUM" | "HIGH" | "CRITICAL"
    resource_id: str | None = None
    resource_type: str | None = None
    category: str | None = None  # e.g. "Network Reachability" | "Software and Configuration"
    region: str | None = None
    account_id: str | None = None
    types: list[str] = Field(default_factory=list)
    first_observed_at: str | None = None


class AWSRegionTopology(BaseModel):
    account_id: str
    region: str
    vpcs: list[VPC] = Field(default_factory=list)
    transit_gateways: list[TransitGateway] = Field(default_factory=list)
    direct_connect_connections: list[DirectConnectConnection] = Field(default_factory=list)
    vpn_gateways: list[VpnGateway] = Field(default_factory=list)
    network_firewalls: list[NetworkFirewallPolicy] = Field(default_factory=list)
    aws_network_firewalls: list[AWSNetworkFirewall] = Field(default_factory=list)
    waf_web_acls: list[AWSWAFWebACL] = Field(default_factory=list)
    security_findings: list[AWSSecurityFinding] = Field(default_factory=list)
    discovery_blocked: bool = False
    block_reason: str | None = None


class AWSTopology(BaseModel):
    schema_version: str = TOPOLOGY_SCHEMA_VERSION
    engagement_id: str
    accounts: list[AWSAccount] = Field(default_factory=list)
    regions: list[AWSRegionTopology] = Field(default_factory=list)
    management_account_id: str | None = None
    organization_id: str | None = None


# ── Azure primitives ───────────────────────────────────────────────────────


class AzureSubnet(BaseModel):
    id: str
    name: str
    address_prefix: str
    # Populated by _classify_subnet() in the Azure discovery path. The field was
    # missing while the discovery code already passed it, so Pydantic silently
    # discarded every classification it computed (TODO.md T-410). Defaulted, so
    # checkpoints written before this field existed still deserialise.
    subnet_type: SubnetType = SubnetType.UNKNOWN
    nsg_id: str | None = None
    nsg_name: str | None = None
    route_table_id: str | None = None
    route_table_name: str | None = None
    nat_gateway_id: str | None = None
    service_endpoints: list[str] = Field(default_factory=list)
    private_endpoint_network_policies: str = "Enabled"
    private_link_service_network_policies: str = "Enabled"
    default_outbound_access: bool = True
    delegation: str | None = None
    address_prefixes: list[str] = Field(default_factory=list)  # dual-stack


class AzureRouteEntry(BaseModel):
    name: str
    address_prefix: str
    next_hop_type: str  # VirtualNetworkGateway | VnetLocal | Internet | VirtualAppliance | None
    next_hop_ip: str | None = None
    has_bgp_override: bool = False


class AzureRouteTable(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    routes: list[AzureRouteEntry] = Field(default_factory=list)
    associated_subnet_ids: list[str] = Field(default_factory=list)
    disable_bgp_route_propagation: bool = False
    tags: dict = Field(default_factory=dict)


class VNetPeering(BaseModel):
    id: str
    name: str
    remote_vnet_id: str
    remote_vnet_name: str | None = None
    remote_subscription_id: str
    peering_state: str
    allow_forwarded_traffic: bool
    allow_gateway_transit: bool
    use_remote_gateways: bool
    do_not_verify_remote_gateways: bool = False
    peer_complete_vnets: bool = True


class AzureFirewall(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    sku_tier: str  # "Basic" | "Standard" | "Premium"
    subnet_id: str | None = None  # AzureFirewallSubnet
    public_ip_ids: list[str] = Field(default_factory=list)
    policy_id: str | None = None
    threat_intel_mode: str = "Alert"
    zones: list[str] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)


class ApplicationGateway(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    sku_name: str  # "Standard_v2" | "WAF_v2"
    sku_capacity: int | None = None
    subnet_id: str
    waf_enabled: bool = False
    waf_mode: str | None = None  # "Detection" | "Prevention"
    waf_rule_set_type: str | None = None
    waf_rule_set_version: str | None = None
    frontend_ip_configs: list[str] = Field(default_factory=list)
    ssl_policy_name: str | None = None
    autoscale_min: int | None = None
    autoscale_max: int | None = None
    zones: list[str] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)


class PrivateDnsZone(BaseModel):
    id: str
    name: str  # e.g. "privatelink.blob.core.windows.net"
    resource_group: str
    linked_vnet_ids: list[str] = Field(default_factory=list)
    linked_vnet_names: list[str] = Field(default_factory=list)
    auto_registration_enabled: bool = False
    record_count: int = 0
    soa_record: str | None = None


class ExpressRouteCircuit(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    service_provider: str | None = None
    peering_location: str | None = None
    bandwidth_mbps: int | None = None
    sku_tier: str = "Standard"  # "Standard" | "Premium"
    sku_family: str = "MeteredData"  # "MeteredData" | "UnlimitedData"
    circuit_provisioning_state: str = "Enabled"
    global_reach_enabled: bool = False
    allow_classic_operations: bool = False
    peering_types: list[str] = Field(default_factory=list)  # AzurePrivatePeering, MicrosoftPeering
    tags: dict = Field(default_factory=dict)


# ── NEW: NSG ───────────────────────────────────────────────────────────────


class NSGSecurityRule(BaseModel):
    name: str
    priority: int
    direction: str  # "Inbound" | "Outbound"
    access: str  # "Allow" | "Deny"
    protocol: str  # "Tcp" | "Udp" | "Icmp" | "*"
    source_port_range: str | None = None
    source_port_ranges: list[str] = Field(default_factory=list)
    destination_port_range: str | None = None
    destination_port_ranges: list[str] = Field(default_factory=list)
    source_address_prefix: str | None = None
    source_address_prefixes: list[str] = Field(default_factory=list)
    source_asgs: list[str] = Field(default_factory=list)  # ASG resource IDs
    destination_address_prefix: str | None = None
    destination_address_prefixes: list[str] = Field(default_factory=list)
    destination_asgs: list[str] = Field(default_factory=list)
    description: str | None = None
    is_default_rule: bool = False
    provisioning_state: str = "Succeeded"


class AzureNSG(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    security_rules: list[NSGSecurityRule] = Field(default_factory=list)
    default_security_rules: list[NSGSecurityRule] = Field(default_factory=list)
    associated_subnet_ids: list[str] = Field(default_factory=list)
    associated_nic_ids: list[str] = Field(default_factory=list)
    flow_logs_enabled: bool = False
    flow_logs_workspace_id: str | None = None
    tags: dict = Field(default_factory=dict)


# ── NEW: Public IP ─────────────────────────────────────────────────────────


class AzurePublicIP(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    sku_name: str = "Standard"  # "Basic" | "Standard"
    allocation_method: str = "Static"  # "Static" | "Dynamic"
    ip_address: str | None = None
    ip_version: str = "IPv4"  # "IPv4" | "IPv6"
    dns_label: str | None = None
    fqdn: str | None = None
    zones: list[str] = Field(default_factory=list)
    # What it's attached to
    associated_resource_id: str | None = None
    associated_resource_type: str | None = (
        None  # "NIC" | "LB" | "AppGW" | "Firewall" | "Bastion" | "VpnGateway"
    )
    idle_timeout_minutes: int = 4
    ddos_protection_mode: str = "VirtualNetworkInherited"
    tags: dict = Field(default_factory=dict)


# ── NEW: Load Balancer ─────────────────────────────────────────────────────


class AzureLBFrontendIP(BaseModel):
    name: str
    public_ip_id: str | None = None
    private_ip_address: str | None = None
    private_ip_allocation_method: str | None = None
    subnet_id: str | None = None
    zones: list[str] = Field(default_factory=list)


class AzureLBRule(BaseModel):
    name: str
    protocol: str  # "Tcp" | "Udp" | "All"
    frontend_port: int
    backend_port: int
    enable_floating_ip: bool = False
    enable_tcp_reset: bool = False
    idle_timeout_minutes: int = 4
    load_distribution: str = "Default"
    disable_outbound_snat: bool = False


class AzureLBProbe(BaseModel):
    name: str
    protocol: str  # "Http" | "Https" | "Tcp"
    port: int
    interval_seconds: int = 15
    number_of_probes: int = 2
    request_path: str | None = None


class AzureLoadBalancer(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    sku_name: str = "Standard"  # "Basic" | "Standard" | "Gateway"
    lb_type: str = "Public"  # "Public" | "Internal"
    frontend_ip_configs: list[AzureLBFrontendIP] = Field(default_factory=list)
    lb_rules: list[AzureLBRule] = Field(default_factory=list)
    probes: list[AzureLBProbe] = Field(default_factory=list)
    backend_pool_ids: list[str] = Field(default_factory=list)
    inbound_nat_rule_count: int = 0
    zones: list[str] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)


# ── NEW: VPN / VNet Gateway ────────────────────────────────────────────────


class AzureGatewayConnection(BaseModel):
    id: str
    name: str
    connection_type: str  # "IPsec" | "ExpressRoute" | "VNet2VNet" | "VPNClient"
    connection_status: str
    remote_vnet_id: str | None = None
    local_network_gateway_id: str | None = None
    express_route_circuit_id: str | None = None
    routing_weight: int = 10
    enable_bgp: bool = False
    use_policy_based_traffic_selectors: bool = False
    dpd_timeout_seconds: int | None = None
    egress_bytes_transferred: int = 0
    ingress_bytes_transferred: int = 0
    shared_key_set: bool = False  # never store the actual key


class AzureVirtualNetworkGateway(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    gateway_type: str  # "Vpn" | "ExpressRoute" | "LocalGateway"
    vpn_type: str | None = None  # "RouteBased" | "PolicyBased"
    sku_name: str = "VpnGw1"
    sku_tier: str = "VpnGw1"
    active_active: bool = False
    enable_bgp: bool = False
    bgp_asn: int | None = None
    bgp_peering_address: str | None = None
    public_ip_ids: list[str] = Field(default_factory=list)
    subnet_id: str | None = None  # GatewaySubnet
    vpn_client_address_pool: list[str] = Field(default_factory=list)
    connections: list[AzureGatewayConnection] = Field(default_factory=list)
    generation: str | None = None  # "Generation1" | "Generation2"
    zones: list[str] = Field(default_factory=list)
    tags: dict = Field(default_factory=dict)


# ── NEW: Private Endpoint ──────────────────────────────────────────────────


class AzurePrivateEndpointConnection(BaseModel):
    connection_name: str
    private_link_service_id: str
    group_ids: list[str] = Field(default_factory=list)  # e.g. ["blob", "file"]
    connection_state: str  # "Approved" | "Pending" | "Rejected"


class AzurePrivateEndpoint(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    subnet_id: str
    private_ip_addresses: list[str] = Field(default_factory=list)
    service_connections: list[AzurePrivateEndpointConnection] = Field(default_factory=list)
    dns_zone_group_names: list[str] = Field(default_factory=list)
    custom_dns_configs: list[str] = Field(default_factory=list)  # FQDNs with overrides
    # Set by Network Watcher connectivity check — True if FQDN resolves to RFC 1918
    dns_resolves_to_private_ip: bool | None = None
    tags: dict = Field(default_factory=dict)


# ── NEW: NAT Gateway ───────────────────────────────────────────────────────


class AzureNatGateway(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    sku_name: str = "Standard"
    idle_timeout_minutes: int = 4
    public_ip_ids: list[str] = Field(default_factory=list)
    public_ip_prefix_ids: list[str] = Field(default_factory=list)
    associated_subnet_ids: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    provisioning_state: str = "Succeeded"
    tags: dict = Field(default_factory=dict)


# ── NEW: Bastion Host ──────────────────────────────────────────────────────


class AzureBastionHost(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    sku_name: str = "Standard"  # "Basic" | "Standard" | "Premium"
    subnet_id: str | None = None  # AzureBastionSubnet
    public_ip_id: str | None = None
    scale_units: int = 2
    # Feature flags
    tunneling_enabled: bool = False
    shareable_link_enabled: bool = False
    ip_connect_enabled: bool = False
    file_copy_enabled: bool = False
    kerberos_enabled: bool = False
    tags: dict = Field(default_factory=dict)


# ── NEW (v1.3.0): Azure Route Server ──────────────────────────────────────


class AzureRouteServerBgpConnection(BaseModel):
    """A BGP peering between an Azure Route Server and an NVA."""

    id: str
    name: str
    peer_ip: str | None = None
    peer_asn: int | None = None
    provisioning_state: str = "Succeeded"
    connection_state: str | None = None  # "Connected" | "NotConnected" | None


class AzureRouteServer(BaseModel):
    """Azure Route Server — a virtual hub with kind == 'RouteServer'."""

    id: str
    name: str
    location: str
    resource_group: str
    # RouteServerSubnet that hosts the route server (embeds the VNet id)
    hosted_subnet_id: str | None = None
    vnet_id: str | None = None
    virtual_router_asn: int | None = None
    virtual_router_ips: list[str] = Field(default_factory=list)
    allow_branch_to_branch_traffic: bool = False
    hub_routing_preference: str | None = None  # "ExpressRoute" | "VpnGateway" | "ASPath"
    bgp_connections: list[AzureRouteServerBgpConnection] = Field(default_factory=list)
    provisioning_state: str = "Succeeded"
    tags: dict = Field(default_factory=dict)


# ── Core VNet / VNet models (expanded) ────────────────────────────────────


class VNet(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    subscription_id: str
    address_space: list[str] = Field(default_factory=list)
    dns_servers: list[str] = Field(default_factory=list)
    subnets: list[AzureSubnet] = Field(default_factory=list)
    route_tables: list[AzureRouteTable] = Field(default_factory=list)
    peerings: list[VNetPeering] = Field(default_factory=list)
    ddos_protection_enabled: bool = False
    ddos_protection_plan_id: str | None = None
    flow_logs_enabled: bool = False
    encryption_enabled: bool = False
    vm_protection_enabled: bool = False
    tags: dict = Field(default_factory=dict)


class AzureVHub(BaseModel):
    id: str
    name: str
    location: str
    resource_group: str
    address_prefix: str
    sku: str = "Standard"
    connected_vnet_ids: list[str] = Field(default_factory=list)
    connected_vpn_site_ids: list[str] = Field(default_factory=list)
    express_route_gateway_id: str | None = None
    azure_firewall_id: str | None = None
    routing_state: str
    virtual_router_asn: int | None = None
    virtual_router_ips: list[str] = Field(default_factory=list)


class AzureVWan(BaseModel):
    id: str
    name: str
    resource_group: str
    sku: str
    hubs: list[AzureVHub] = Field(default_factory=list)
    allow_vnet_to_vnet_traffic: bool = True
    allow_branch_to_branch_traffic: bool = True
    tags: dict = Field(default_factory=dict)


class ManagementGroup(BaseModel):
    id: str
    name: str
    display_name: str
    parent_id: str | None = None
    subscription_ids: list[str] = Field(default_factory=list)
    child_mg_ids: list[str] = Field(default_factory=list)


# ── v1.3.0: Extended assessment data ──────────────────────────────────────────


class WorkloadSummary(BaseModel):
    """Kept for backward compatibility with existing topology JSON blobs."""

    vm_count: int = 0
    aca_count: int = 0
    aks_cluster_count: int = 0
    app_service_count: int = 0
    function_app_count: int = 0
    container_registry_count: int = 0
    vm_details: list[dict] = Field(default_factory=list)
    aks_details: list[dict] = Field(default_factory=list)


class AzureNIC(BaseModel):
    """NIC collected when attached to an NVA or has IP forwarding enabled."""

    id: str
    name: str
    location: str
    resource_group: str
    vm_id: str | None = None
    ip_forwarding_enabled: bool = False
    subnet_ids: list[str] = Field(default_factory=list)
    private_ips: list[str] = Field(default_factory=list)
    public_ip_id: str | None = None
    nsg_id: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)


class AzureNVA(BaseModel):
    """Network Virtual Appliance — marketplace NGFW or IP-forwarding VM.

    Identification methods:
      marketplace     — plan.publisher matches a known NGFW vendor
      image_reference — image publisher matches (BYOL, no explicit plan)
      ip_forwarding   — NIC has ip_forwarding_enabled=True, vendor unknown
    """

    id: str
    name: str
    location: str
    resource_group: str
    vm_size: str | None = None
    os_type: str | None = None
    # e.g. paloaltonetworks, fortinet, checkpoint
    publisher: str | None = None
    # e.g. vmseries-flex, fortinet_fortigate-vm_v5
    offer: str | None = None
    # marketplace SKU / plan name
    plan_name: str | None = None
    # marketplace | image_reference | ip_forwarding
    identification_method: str = "marketplace"
    nics: list[AzureNIC] = Field(default_factory=list)
    tags: dict[str, str] = Field(default_factory=dict)


class BgpPeerStatus(BaseModel):
    peer_ip: str
    peer_asn: int | None = None
    state: str = "Unknown"  # Connected | Disconnected | Idle | Unknown
    messages_sent: int = 0
    messages_received: int = 0
    routes_received: int = 0
    connected_duration: str | None = None


class GatewayBgpData(BaseModel):
    gateway_id: str
    gateway_name: str
    bgp_enabled: bool = False
    bgp_asn: int | None = None
    peers: list[BgpPeerStatus] = Field(default_factory=list)
    learned_routes: list[str] = Field(default_factory=list)  # sampled CIDR prefixes
    learned_routes_count: int = 0
    advertised_routes: list[str] = Field(default_factory=list)
    advertised_routes_count: int = 0
    collection_error: str | None = None


class NetworkWatcherInfo(BaseModel):
    location: str
    name: str
    provisioning_state: str = "Succeeded"


class LogAnalyticsWorkspace(BaseModel):
    id: str
    name: str
    resource_group: str
    location: str
    retention_days: int = 30
    sku: str = "PerGB2018"


class ObservabilityData(BaseModel):
    network_watchers: list[NetworkWatcherInfo] = Field(default_factory=list)
    log_analytics_workspaces: list[LogAnalyticsWorkspace] = Field(default_factory=list)
    nsg_flow_logs_enabled: int = 0
    nsg_flow_logs_total: int = 0
    # Traffic Analytics: how many enabled flow logs are feeding Traffic Analytics
    traffic_analytics_enabled: int = 0
    gateways_with_diagnostics: int = 0
    gateways_total: int = 0
    # Bastion: how many bastion hosts have a Log Analytics diagnostic sink
    bastion_with_diagnostics: int = 0
    bastion_total: int = 0
    # Firewalls: how many Azure Firewalls have a Log Analytics diagnostic sink
    firewalls_with_diagnostics: int = 0
    firewalls_total: int = 0
    # v1.3.0 — per-resource-type diagnostic coverage for AppGW and LB
    appgw_with_diagnostics: int = 0
    appgw_total: int = 0
    lb_with_diagnostics: int = 0
    lb_total: int = 0
    # v1.3.0 — Azure Monitor alert-rule coverage (subscription-wide counts)
    metric_alert_count: int = 0
    activity_log_alert_count: int = 0


class GatewayMetric(BaseModel):
    """Azure Monitor bandwidth metrics for a single VPN or ExpressRoute gateway (24-hour window)."""

    gateway_name: str
    gateway_type: str  # Vpn | ExpressRoute
    ingress_bytes_24h: float | None = None
    egress_bytes_24h: float | None = None
    bandwidth_mbps_provisioned: float | None = None
    # populated by AverageBandwidth metric vs provisioned SKU ceiling
    utilization_pct: float | None = None


class FirewallMetric(BaseModel):
    """Azure Monitor metrics for a single Azure Firewall resource (24-hour window)."""

    firewall_name: str
    data_processed_gb_24h: float | None = None
    app_rule_hits_24h: int | None = None
    network_rule_hits_24h: int | None = None
    nat_rule_hits_24h: int | None = None
    collection_error: str | None = None


class LoadBalancerMetric(BaseModel):
    """Azure Monitor SNAT metrics for a single Load Balancer (24-hour window)."""

    lb_name: str
    snat_connections_24h: float | None = None  # SnatConnectionCount (total)
    used_snat_ports: float | None = None  # UsedSnatPorts (avg)
    allocated_snat_ports: float | None = None  # AllocatedSnatPorts (avg)
    snat_port_utilization_pct: float | None = None  # used / allocated * 100
    collection_error: str | None = None


class ERCircuitMetric(BaseModel):
    """Azure Monitor throughput metrics for a single ExpressRoute circuit (24-hour window)."""

    circuit_name: str
    bandwidth_mbps_provisioned: float | None = None
    primary_bits_in_per_second: float | None = None  # avg bps
    secondary_bits_in_per_second: float | None = None  # avg bps
    primary_utilization_pct: float | None = None
    secondary_utilization_pct: float | None = None
    collection_error: str | None = None


class FrontDoorWAFPolicy(BaseModel):
    """Azure Front Door Web Application Firewall policy on the customer tenant."""

    id: str
    name: str
    resource_group: str
    location: str
    policy_mode: str = "Detection"  # "Detection" | "Prevention"
    policy_enabled_state: str = "Enabled"  # "Enabled" | "Disabled"
    custom_rules_count: int = 0
    managed_rules_count: int = 0
    tags: dict = Field(default_factory=dict)


class AppGatewayMetric(BaseModel):
    """Azure Monitor capacity and latency metrics for a single Application Gateway (24h window)."""

    appgw_name: str
    capacity_units_avg: float | None = None  # CapacityUnits (avg) — consumed CUs
    capacity_units_max: float | None = None  # CapacityUnits (max) — peak pressure
    backend_latency_ms_avg: float | None = None  # BackendLastByteResponseTime (ms avg)
    failed_requests_24h: int | None = None  # FailedRequests (total)
    total_requests_24h: int | None = None  # TotalRequests (total)
    waf_rule_hits_24h: int | None = None  # ApplicationGatewayWAFRuleMatches (total)
    collection_error: str | None = None


class DefenderAssessment(BaseModel):
    """A single Defender for Cloud security assessment on a resource."""

    assessment_id: str  # e.g. "/subscriptions/.../assessments/<uuid>"
    display_name: str
    description: str | None = None
    remediation_description: str | None = None
    status: str = "Unhealthy"  # "Healthy" | "Unhealthy" | "NotApplicable" | "NotFound"
    severity: str = "Medium"  # "Low" | "Medium" | "High"
    resource_id: str | None = None
    resource_type: str | None = None
    category: str | None = None  # e.g. "Networking" | "IdentityAndAccess"
    implementation_effort: str | None = None  # "Low" | "Moderate" | "High"
    threats: list[str] = Field(default_factory=list)
    user_impact: str | None = None


class NetworkMetrics(BaseModel):
    gateway_metrics: list[GatewayMetric] = Field(default_factory=list)
    firewall_metrics: list[FirewallMetric] = Field(default_factory=list)
    lb_metrics: list[LoadBalancerMetric] = Field(default_factory=list)
    er_circuit_metrics: list[ERCircuitMetric] = Field(default_factory=list)
    appgw_metrics: list[AppGatewayMetric] = Field(default_factory=list)
    # vnet_id -> utilization % (sum of subnet CIDRs / VNet CIDR * 100)
    vnet_utilization: dict[str, float] = Field(default_factory=dict)
    # Billing-derived: total Microsoft.Network egress spend MTD (USD)
    egress_cost_usd_mtd: float | None = None
    # NTA (Network Traffic Analytics) east-west and north-south byte totals (24h)
    nta_east_west_bytes_24h: float | None = None
    nta_north_south_bytes_24h: float | None = None
    nta_query_workspace_id: str | None = None
    # DDoS attack events detected on Public IPs in the subscription (24h)
    ddos_attack_events_24h: int = 0
    public_ips_under_ddos_attack: list[str] = Field(default_factory=list)
    collection_error: str | None = None


class AzureSubscriptionTopology(BaseModel):
    subscription_id: str
    subscription_name: str | None = None
    tenant_id: str
    vnets: list[VNet] = Field(default_factory=list)
    nsgs: list[AzureNSG] = Field(default_factory=list)
    route_tables: list[AzureRouteTable] = Field(default_factory=list)
    virtual_network_gateways: list[AzureVirtualNetworkGateway] = Field(default_factory=list)
    load_balancers: list[AzureLoadBalancer] = Field(default_factory=list)
    public_ips: list[AzurePublicIP] = Field(default_factory=list)
    private_endpoints: list[AzurePrivateEndpoint] = Field(default_factory=list)
    nat_gateways: list[AzureNatGateway] = Field(default_factory=list)
    bastion_hosts: list[AzureBastionHost] = Field(default_factory=list)
    virtual_wans: list[AzureVWan] = Field(default_factory=list)
    route_servers: list[AzureRouteServer] = Field(default_factory=list)
    firewalls: list[AzureFirewall] = Field(default_factory=list)
    application_gateways: list[ApplicationGateway] = Field(default_factory=list)
    private_dns_zones: list[PrivateDnsZone] = Field(default_factory=list)
    express_route_circuits: list[ExpressRouteCircuit] = Field(default_factory=list)
    # v1.3.0 — extended assessment data
    nvas: list[AzureNVA] = Field(default_factory=list)
    bgp_data: list[GatewayBgpData] = Field(default_factory=list)
    front_door_waf_policies: list[FrontDoorWAFPolicy] = Field(default_factory=list)
    defender_assessments: list[DefenderAssessment] = Field(default_factory=list)
    observability: ObservabilityData | None = None
    network_metrics: NetworkMetrics | None = None
    # kept for backward compat — no longer actively collected
    workload_inventory: WorkloadSummary | None = None
    discovery_blocked: bool = False
    block_reason: str | None = None


class AzureTopology(BaseModel):
    schema_version: str = TOPOLOGY_SCHEMA_VERSION
    engagement_id: str
    tenant_id: str
    management_groups: list[ManagementGroup] = Field(default_factory=list)
    subscriptions: list[AzureSubscriptionTopology] = Field(default_factory=list)
