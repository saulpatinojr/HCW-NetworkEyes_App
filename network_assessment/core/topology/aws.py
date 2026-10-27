"""AWS topology data contracts — bridge between discovery and the diagram engine.

Moved verbatim from ``network_assessment.core.topology_schema`` (lines 64 to 309 at the split); the
model version history is in that module's former docstring, now in
``network_assessment.core.topology.azure``. This module imports nothing from the Azure model.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from network_assessment.core.topology.common import AttachmentType, PeeringState, SubnetType

AWS_TOPOLOGY_VERSION = "1.3.0"

__all__ = [
    "AWSAccount",
    "AWSNetworkFirewall",
    "AWSRegionTopology",
    "AWSSecurityFinding",
    "AWSTopology",
    "AWSWAFWebACL",
    "AWS_TOPOLOGY_VERSION",
    "DirectConnectConnection",
    "InternetGateway",
    "NACL",
    "NACLEntry",
    "NatGateway",
    "NetworkFirewallPolicy",
    "RouteEntry",
    "RouteTable",
    "SecurityGroup",
    "SecurityGroupRule",
    "Subnet",
    "TGWAttachment",
    "TransitGateway",
    "VPC",
    "VpcPeeringConnection",
    "VpnGateway",
]


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
    schema_version: str = AWS_TOPOLOGY_VERSION
    engagement_id: str
    accounts: list[AWSAccount] = Field(default_factory=list)
    regions: list[AWSRegionTopology] = Field(default_factory=list)
    management_account_id: str | None = None
    organization_id: str | None = None
