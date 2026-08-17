"""Phase D — AI Analysis Engine.

Consumes AWSTopology and AzureTopology checkpoints from EngagementStore.
Produces a versioned FindingsReport written back to EngagementStore.

Design contracts (all enforced in code, not just docs):
  DD-002: Every finding MUST have observed_state. Hedge language blocks publication.
  DD-003: Finding generation and recommendation injection are STRICTLY separate.
          This module generates findings only. Recommendations are injected by
          recommendation_engine.py AFTER this module completes.
  DD-008: This engine reads from our data store ONLY — never touches client env.
  DD-009: FindingsReport written to store with review_complete=False. Report engine
          refuses to generate output until review_complete=True.
  DD-016: CRITICAL findings trigger EscalationEngine before analysis completes.

Finding deduplication key: f"{finding_id}:{resource_id}"
Any finding with the same key is deduplicated — the first occurrence wins.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from cna.ai_engine.observed_state_enforcer import ObservedStateEnforcer
from cna.core.escalation_engine import CriticalFindingEscalationEngine
from cna.core.findings_schema import (
    FINDINGS_SCHEMA_VERSION,
    Finding,
    FindingSeverity,
    FindingsReport,
    FindingStatus,
    FrameworkMapping,
    ObservedState,
)
from cna.core.persistence import EngagementStore
from cna.core.topology_schema import (
    AWSRegionTopology,
    AWSTopology,
    AzureSubscriptionTopology,
    AzureTopology,
)

logger = logging.getLogger("cna.analysis")

# ---------------------------------------------------------------------------
# Finding rule IDs — stable across runs, used as dedup keys
# ---------------------------------------------------------------------------

# AWS
R_AWS_DEFAULT_VPC_EXISTS = "AWS-NET-001"
R_AWS_VPC_FLOW_LOGS_DISABLED = "AWS-NET-002"
R_AWS_SG_UNRESTRICTED_SSH = "AWS-NET-003"
R_AWS_SG_UNRESTRICTED_RDP = "AWS-NET-004"
R_AWS_SG_UNRESTRICTED_ALL = "AWS-NET-005"
R_AWS_TGW_DEFAULT_RT_ASSOC = "AWS-NET-006"
R_AWS_TGW_DEFAULT_RT_PROP = "AWS-NET-007"
R_AWS_DX_NO_REDUNDANCY = "AWS-NET-008"
R_AWS_NAT_SINGLE_AZ = "AWS-NET-009"
R_AWS_SUBNET_NO_NACL = "AWS-NET-010"
R_AWS_IGW_MISSING_ROUTE = "AWS-NET-011"

# Azure
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
R_AWS_NO_NETWORK_FIREWALL = "AWS-NET-012"
R_AWS_WAF_NO_ASSOCIATION = "AWS-NET-013"

# Severity thresholds
_CRITICAL_IDS = {
    R_AWS_SG_UNRESTRICTED_SSH,
    R_AWS_SG_UNRESTRICTED_RDP,
    R_AWS_SG_UNRESTRICTED_ALL,
    R_AZ_FW_THREAT_INTEL_NOT_DENY,
    R_AZ_DDOS_ATTACK_DETECTED,
}
_HIGH_IDS = {
    R_AWS_VPC_FLOW_LOGS_DISABLED,
    R_AZ_SUBNET_NO_NSG,
    R_AZ_VNET_NO_FLOW_LOGS,
    R_AZ_APPGW_WAF_DISABLED,
    R_AZ_GW_SATURATION,
    R_AZ_FW_NO_HITS,
    R_AZ_LB_SNAT_EXHAUSTION,
    R_AZ_VNET_IP_EXHAUSTION,
    R_AZ_ER_SATURATION,
    R_AZ_APPGW_HIGH_LATENCY,
}

_MEDIUM_IDS = {
    R_AZ_TRAFFIC_ANALYTICS_MISSING,
    R_AZ_FW_NO_DIAGNOSTICS,
    R_AZ_BASTION_NO_DIAGNOSTICS,
    R_AZ_PEERING_FW_BYPASS,
    R_AZ_FRONTDOOR_WAF_DETECTION_MODE,
    R_AWS_WAF_NO_ASSOCIATION,
}


_PORT_SSH: int = 22
_PORT_RDP: int = 3389
_HIGH_UTILIZATION_PCT: float = 80.0
_CRITICAL_UTILIZATION_PCT: float = 85.0
_APPGW_LATENCY_THRESHOLD_MS: int = 2000
_APPGW_FAILURE_RATE_THRESHOLD: float = 0.05


def _severity(rule_id: str) -> FindingSeverity:
    if rule_id in _CRITICAL_IDS:
        return FindingSeverity.CRITICAL
    if rule_id in _HIGH_IDS:
        return FindingSeverity.HIGH
    if rule_id in _MEDIUM_IDS:
        return FindingSeverity.MEDIUM
    return FindingSeverity.LOW


@dataclass
class AnalysisOptions:
    load_aws: bool = True
    load_azure: bool = True
    dry_run: bool = False  # produce findings but do not write to store
    # (cloud, current, total, label) — see cli/analyze.py's `progress`
    progress_callback: Callable[[str, int, int, str], None] | None = None


class AnalysisEngine:
    """Generates findings from topology checkpoints. Writes FindingsReport.

    Strictly does NOT inject recommendations — that is RecommendationEngine's job.
    """

    def __init__(self, store: EngagementStore, options: AnalysisOptions | None = None):
        self.store = store
        self.opts = options or AnalysisOptions()
        self._enforcer = ObservedStateEnforcer()
        self._escalation = CriticalFindingEscalationEngine()
        self._seen: set[str] = set()  # deduplication register
        self._findings: list[Finding] = []

    # ---------------------------------------------------------------- dedup

    def _dedup_key(self, rule_id: str | None, resource_id: str | None) -> str:
        return f"{rule_id}:{resource_id}"

    def _emit(self, finding: Finding) -> None:
        """Validate, deduplicate, and register a finding."""
        # 1. Enforce observed_state — blocks hedge language (DD-002)
        self._enforcer.validate(finding)  # raises ObservedStateViolation on failure

        # 2. Enforce framework_mappings (DD-002)
        if not finding.framework_mappings:
            raise ValueError(
                f"Finding {finding.rule_id} has no framework_mappings. "
                "Every finding must map to at least one framework control."
            )

        # 3. Deduplication
        key = self._dedup_key(finding.rule_id, finding.resource_id)
        if key in self._seen:
            logger.debug("Deduplicated finding %s", key)
            return
        self._seen.add(key)

        # 4. CRITICAL escalation check (DD-016)
        if finding.severity == FindingSeverity.CRITICAL:
            self._escalation.flag(finding)

        self._findings.append(finding)
        logger.debug(
            "Finding emitted: %s on %s [%s]",
            finding.rule_id,
            finding.resource_id,
            finding.severity.value,
        )

    # ---------------------------------------------------------------- AWS rules

    def _check_aws_vpc(self, vpc, account_id: str, region: str) -> None:
        if vpc.is_default:
            self._emit(
                Finding(
                    rule_id=R_AWS_DEFAULT_VPC_EXISTS,
                    severity=_severity(R_AWS_DEFAULT_VPC_EXISTS),
                    resource_id=vpc.id,
                    resource_type="AWS::EC2::VPC",
                    account_id=account_id,
                    region=region,
                    title="Default VPC exists",
                    observed_state=ObservedState(
                        fact=f"Default VPC {vpc.id} exists in {account_id}/{region}.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}.vpcs[id={vpc.id}].is_default",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Security",
                            control="SEC 5 — Network Protection",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.1",
                            control_name="Network Segmentation",
                            alignment="Default VPCs create unintended network paths that undermine segmentation policy",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        if not vpc.flow_logs_enabled:
            self._emit(
                Finding(
                    rule_id=R_AWS_VPC_FLOW_LOGS_DISABLED,
                    severity=_severity(R_AWS_VPC_FLOW_LOGS_DISABLED),
                    resource_id=vpc.id,
                    resource_type="AWS::EC2::VPC",
                    account_id=account_id,
                    region=region,
                    title="VPC flow logs disabled",
                    observed_state=ObservedState(
                        fact=f"VPC {vpc.id} ({vpc.name or 'unnamed'}) has no flow logs enabled.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}.vpcs[id={vpc.id}].flow_logs_enabled",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Security",
                            control="SEC 4 — Detective Controls",
                        ),
                        FrameworkMapping(
                            framework="NIST CSF",
                            pillar="Detect",
                            control="DE.CM-1",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.2",
                            control_name="Traffic Management",
                            alignment="Flow logs enable traffic visibility required for zero trust enforcement",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        for sg in vpc.security_groups:
            self._check_aws_sg(sg, vpc, account_id, region)

    def _check_aws_sg(self, sg, vpc, account_id: str, region: str) -> None:
        for rule in sg.rules:
            if rule.direction != "ingress":
                continue
            for cidr in rule.cidr_ranges or []:
                if cidr not in ("0.0.0.0/0", "::/0"):
                    continue
                self._check_aws_sg_open_cidr(sg, vpc, account_id, region, rule, cidr)

    @staticmethod
    def _tcp_port_exposed(proto: str, fp, tp, port: int) -> bool:
        """Return True if a TCP rule exposes the given port."""
        return proto in ("tcp", "6") and fp is not None and fp <= port <= (tp or fp)

    def _check_aws_sg_open_cidr(
        self, sg, vpc, account_id: str, region: str, rule, cidr: str
    ) -> None:
        fp = rule.from_port
        tp = rule.to_port
        proto = rule.protocol

        if proto == "-1":
            self._emit(
                Finding(
                    rule_id=R_AWS_SG_UNRESTRICTED_ALL,
                    severity=FindingSeverity.CRITICAL,
                    resource_id=sg.id,
                    resource_type="AWS::EC2::SecurityGroup",
                    account_id=account_id,
                    region=region,
                    title="Security group allows all inbound traffic from internet",
                    observed_state=ObservedState(
                        fact=f"Security group {sg.id} ({sg.name}) in VPC {vpc.id} "
                        f"has an ingress rule allowing all protocols from {cidr}.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}.vpcs[id={vpc.id}]"
                        f".security_groups[id={sg.id}].rules",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Security",
                            control="SEC 5 — Network Protection",
                        ),
                        FrameworkMapping(
                            framework="CIS AWS Foundations Benchmark",
                            pillar="Networking",
                            control="4.1",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.1",
                            control_name="Network Segmentation",
                            alignment="NSGs enforce micro-segmentation between subnets",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )
            return

        if self._tcp_port_exposed(proto, fp, tp, _PORT_SSH):
            self._emit(
                Finding(
                    rule_id=R_AWS_SG_UNRESTRICTED_SSH,
                    severity=FindingSeverity.CRITICAL,
                    resource_id=sg.id,
                    resource_type="AWS::EC2::SecurityGroup",
                    account_id=account_id,
                    region=region,
                    title="Security group allows unrestricted SSH (port 22) from internet",
                    observed_state=ObservedState(
                        fact=f"Security group {sg.id} ({sg.name}) in VPC {vpc.id} "
                        f"allows TCP port 22 from {cidr}.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}.vpcs[id={vpc.id}]"
                        f".security_groups[id={sg.id}].rules",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Security",
                            control="SEC 5 — Network Protection",
                        ),
                        FrameworkMapping(
                            framework="CIS AWS Foundations Benchmark",
                            pillar="Networking",
                            control="4.1",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.1",
                            control_name="Network Segmentation",
                            alignment="NSGs enforce micro-segmentation between subnets",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        if self._tcp_port_exposed(proto, fp, tp, _PORT_RDP):
            self._emit(
                Finding(
                    rule_id=R_AWS_SG_UNRESTRICTED_RDP,
                    severity=FindingSeverity.CRITICAL,
                    resource_id=sg.id,
                    resource_type="AWS::EC2::SecurityGroup",
                    account_id=account_id,
                    region=region,
                    title="Security group allows unrestricted RDP (port 3389) from internet",
                    observed_state=ObservedState(
                        fact=f"Security group {sg.id} ({sg.name}) in VPC {vpc.id} "
                        f"allows TCP port 3389 from {cidr}.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}.vpcs[id={vpc.id}]"
                        f".security_groups[id={sg.id}].rules",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Security",
                            control="SEC 5 — Network Protection",
                        ),
                        FrameworkMapping(
                            framework="CIS AWS Foundations Benchmark",
                            pillar="Networking",
                            control="4.2",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.1",
                            control_name="Network Segmentation",
                            alignment="NSGs enforce micro-segmentation between subnets",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_aws_tgw(self, tgw, account_id: str, region: str) -> None:
        if tgw.default_route_table_association:
            self._emit(
                Finding(
                    rule_id=R_AWS_TGW_DEFAULT_RT_ASSOC,
                    severity=_severity(R_AWS_TGW_DEFAULT_RT_ASSOC),
                    resource_id=tgw.id,
                    resource_type="AWS::EC2::TransitGateway",
                    account_id=account_id,
                    region=region,
                    title="TGW default route table association enabled",
                    observed_state=ObservedState(
                        fact=f"Transit Gateway {tgw.id} ({tgw.name or 'unnamed'}) has "
                        f"DefaultRouteTableAssociation=enable. All new attachments "
                        f"associate to the default route table automatically.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}"
                        f".transit_gateways[id={tgw.id}].default_route_table_association",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Security",
                            control="SEC 5 — Network Protection",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.4",
                            control_name="Network Resilience",
                            alignment="Redundant circuits prevent single points of failure in hybrid connectivity",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        if tgw.default_route_table_propagation:
            self._emit(
                Finding(
                    rule_id=R_AWS_TGW_DEFAULT_RT_PROP,
                    severity=_severity(R_AWS_TGW_DEFAULT_RT_PROP),
                    resource_id=tgw.id,
                    resource_type="AWS::EC2::TransitGateway",
                    account_id=account_id,
                    region=region,
                    title="TGW default route table propagation enabled",
                    observed_state=ObservedState(
                        fact=f"Transit Gateway {tgw.id} has DefaultRouteTablePropagation=enable. "
                        f"Routes propagate to shared route table without explicit policy.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}"
                        f".transit_gateways[id={tgw.id}].default_route_table_propagation",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Security",
                            control="SEC 5 — Network Protection",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.4",
                            control_name="Network Resilience",
                            alignment="Redundant circuits prevent single points of failure in hybrid connectivity",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_aws_connectivity(
        self, region_topo: AWSRegionTopology, account_id: str, region: str
    ) -> None:
        dx_connections = region_topo.direct_connect_connections
        if len(dx_connections) == 1:
            self._emit(
                Finding(
                    rule_id=R_AWS_DX_NO_REDUNDANCY,
                    severity=_severity(R_AWS_DX_NO_REDUNDANCY),
                    resource_id=dx_connections[0].id,
                    resource_type="AWS::DirectConnect::Connection",
                    account_id=account_id,
                    region=region,
                    title="Single Direct Connect connection — no redundancy",
                    observed_state=ObservedState(
                        fact=f"Only one Direct Connect connection ({dx_connections[0].id}, "
                        f"{dx_connections[0].bandwidth}) found in {region}. "
                        f"No redundant path exists.",
                        evidence_ref=f"discovery:aws_{account_id}_{region}.direct_connect_connections",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="AWS Well-Architected Framework",
                            pillar="Reliability",
                            control="REL 6 — Design to Withstand Component Failure",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.4",
                            control_name="Network Resilience",
                            alignment="Redundant circuits prevent single points of failure in hybrid connectivity",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        vpcs_with_igw = [vpc for vpc in region_topo.vpcs if vpc.internet_gateways]
        if (
            vpcs_with_igw
            and not region_topo.aws_network_firewalls
            and not region_topo.network_firewalls
        ):
            for vpc in vpcs_with_igw:
                self._emit(
                    Finding(
                        rule_id=R_AWS_NO_NETWORK_FIREWALL,
                        severity=_severity(R_AWS_NO_NETWORK_FIREWALL),
                        resource_id=vpc.id,
                        resource_type="AWS::EC2::VPC",
                        account_id=account_id,
                        region=region,
                        title="VPC with internet gateway has no AWS Network Firewall deployed",
                        observed_state=ObservedState(
                            fact=f"VPC {vpc.id} ({vpc.name or 'unnamed'}) in {account_id}/{region} "
                            f"has an internet gateway but no AWS Network Firewall resource was found in the region.",
                            evidence_ref=f"discovery:aws_{account_id}_{region}.vpcs[id={vpc.id}].internet_gateways",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="AWS Well-Architected Framework",
                                pillar="Security",
                                control="SEC 5 — Network Protection",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.2",
                                control_name="Traffic Management",
                                alignment="Network Firewall enforces stateful traffic inspection at VPC ingress/egress",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

        for acl in region_topo.waf_web_acls:
            if not acl.associated_resource_arns:
                self._emit(
                    Finding(
                        rule_id=R_AWS_WAF_NO_ASSOCIATION,
                        severity=_severity(R_AWS_WAF_NO_ASSOCIATION),
                        resource_id=acl.web_acl_arn,
                        resource_type="AWS::WAFv2::WebACL",
                        account_id=account_id,
                        region=region,
                        title="WAF Web ACL is not associated with any load balancer",
                        observed_state=ObservedState(
                            fact=f"WAF Web ACL {acl.name} ({acl.web_acl_id}) in {account_id}/{region} "
                            f"has no associated Application Load Balancer resources. "
                            f"Managed rule groups: {acl.managed_rule_groups_count}, "
                            f"custom rules: {acl.custom_rules_count}.",
                            evidence_ref=f"discovery:aws_{account_id}_{region}.waf_web_acls[id={acl.web_acl_id}].associated_resource_arns",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="AWS Well-Architected Framework",
                                pillar="Security",
                                control="SEC 5 — Network Protection",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.2",
                                control_name="Traffic Management",
                                alignment="WAF provides application-layer traffic filtering at the perimeter",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Applications and Workloads",
                                control_id="4.0",
                                control_name="Application and Workload Protection",
                                alignment="A detached WAF leaves application endpoints without workload-layer inspection",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

    def _analyze_aws_region(self, region_topo: AWSRegionTopology) -> None:
        if region_topo.discovery_blocked:
            return

        account_id = region_topo.account_id
        region = region_topo.region

        for vpc in region_topo.vpcs:
            self._check_aws_vpc(vpc, account_id, region)

        for tgw in region_topo.transit_gateways:
            self._check_aws_tgw(tgw, account_id, region)

        self._check_aws_connectivity(region_topo, account_id, region)

    # ---------------------------------------------------------------- Azure rules

    # Well-known infrastructure subnet names excluded from workload checks
    _INFRA_SUBNETS = frozenset(
        {
            "gatewaysubnet",
            "azurefirewallsubnet",
            "azurefirewallmanagementsubnet",
            "azurebastionsubnet",
            "routeservicesubnet",
        }
    )

    def _check_azure_vnet(self, vnet, sub_id: str) -> None:
        if not vnet.ddos_protection_enabled:
            self._emit(
                Finding(
                    rule_id=R_AZ_VNET_NO_DDOS,
                    severity=_severity(R_AZ_VNET_NO_DDOS),
                    resource_id=vnet.id,
                    resource_type="Microsoft.Network/virtualNetworks",
                    account_id=sub_id,
                    region=vnet.location,
                    title="VNet does not have DDoS Protection enabled",
                    observed_state=ObservedState(
                        fact=f"VNet {vnet.name} ({vnet.id}) in {vnet.location} has "
                        f"DDoS Protection Standard disabled.",
                        evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}].ddos_protection_enabled",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="NS-1 — Establish network segmentation boundaries",
                        ),
                        FrameworkMapping(
                            framework="ISO 27001:2022",
                            pillar="Network Security",
                            control="A.8.20 — Networks security",
                        ),
                        FrameworkMapping(
                            framework="HIPAA §164.312",
                            pillar="Technical Safeguards",
                            control="(e)(2)(ii) — Encryption and decryption (addressable); "
                            "integrity controls for ePHI in transit",
                        ),
                        FrameworkMapping(
                            framework="FedRAMP Moderate",
                            pillar="System and Communications Protection",
                            control="SC-5 — Denial of Service Protection",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.4",
                            control_name="Network Resilience",
                            alignment="DDoS protection is a network resilience control",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        for subnet in vnet.subnets:
            if not subnet.nsg_id:
                if subnet.name and subnet.name.lower() == "gatewaysubnet":
                    continue
                self._emit(
                    Finding(
                        rule_id=R_AZ_SUBNET_NO_NSG,
                        severity=_severity(R_AZ_SUBNET_NO_NSG),
                        resource_id=subnet.id,
                        resource_type="Microsoft.Network/virtualNetworks/subnets",
                        account_id=sub_id,
                        region=vnet.location,
                        title="Subnet has no Network Security Group",
                        observed_state=ObservedState(
                            fact=f"Subnet {subnet.name} ({subnet.id}) in VNet {vnet.name} "
                            f"has no NSG attached.",
                            evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}]"
                            f".subnets[id={subnet.id}].nsg_id",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Security",
                                control="NS-1 — Establish network segmentation boundaries",
                            ),
                            FrameworkMapping(
                                framework="CIS Microsoft Azure Foundations Benchmark",
                                pillar="Networking",
                                control="6.2",
                            ),
                            FrameworkMapping(
                                framework="PCI-DSS 4.0",
                                pillar="Network Security Controls",
                                control="Req 1.2 — Network security controls configured "
                                "and maintained",
                            ),
                            FrameworkMapping(
                                framework="ISO 27001:2022",
                                pillar="Network Security",
                                control="A.8.22 — Segregation of networks",
                            ),
                            FrameworkMapping(
                                framework="HIPAA §164.312",
                                pillar="Technical Safeguards",
                                control="(a)(1) — Access control: unique user identification "
                                "and network access controls for ePHI systems",
                            ),
                            FrameworkMapping(
                                framework="FedRAMP Moderate",
                                pillar="System and Communications Protection",
                                control="SC-7 — Boundary Protection",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.1",
                                control_name="Network Segmentation",
                                alignment="NSGs enforce micro-segmentation between subnets",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

    def _check_azure_firewall(self, fw, sub_id: str) -> None:
        if fw.threat_intel_mode.lower() != "deny":
            self._emit(
                Finding(
                    rule_id=R_AZ_FW_THREAT_INTEL_NOT_DENY,
                    severity=FindingSeverity.CRITICAL,
                    resource_id=fw.id,
                    resource_type="Microsoft.Network/azureFirewalls",
                    account_id=sub_id,
                    region=fw.location,
                    title="Azure Firewall Threat Intelligence mode is not set to Deny",
                    observed_state=ObservedState(
                        fact=f"Azure Firewall {fw.name} has ThreatIntelMode='{fw.threat_intel_mode}'. "
                        f"Known malicious IPs and domains are not actively blocked.",
                        evidence_ref=f"discovery:azure_{sub_id}.firewalls[id={fw.id}].threat_intel_mode",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="NS-4 — Protect applications from external network attacks",
                        ),
                        FrameworkMapping(
                            framework="NIST CSF",
                            pillar="Protect",
                            control="PR.PT-4",
                        ),
                        FrameworkMapping(
                            framework="PCI-DSS 4.0",
                            pillar="Network Security Controls",
                            control="Req 1.3 — Restrict inbound and outbound traffic",
                        ),
                        FrameworkMapping(
                            framework="ISO 27001:2022",
                            pillar="Network Security",
                            control="A.8.20 — Networks security",
                        ),
                        FrameworkMapping(
                            framework="HIPAA §164.312",
                            pillar="Technical Safeguards",
                            control="(e)(1) — Transmission security: guard against "
                            "unauthorized access to ePHI in transit",
                        ),
                        FrameworkMapping(
                            framework="FedRAMP Moderate",
                            pillar="System and Communications Protection",
                            control="SC-7 — Boundary Protection",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.2",
                            control_name="Traffic Management",
                            alignment="Threat intel-based blocking controls traffic flows to known malicious destinations",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_azure_er_redundancy(self, sub_topo: AzureSubscriptionTopology, sub_id: str) -> None:
        if len(sub_topo.express_route_circuits) == 1:
            er = sub_topo.express_route_circuits[0]
            self._emit(
                Finding(
                    rule_id=R_AZ_ER_NO_REDUNDANCY,
                    severity=_severity(R_AZ_ER_NO_REDUNDANCY),
                    resource_id=er.id,
                    resource_type="Microsoft.Network/expressRouteCircuits",
                    account_id=sub_id,
                    region=er.location,
                    title="Single ExpressRoute circuit — no redundancy",
                    observed_state=ObservedState(
                        fact=f"Only one ExpressRoute circuit ({er.name}, {er.bandwidth_mbps}Mbps via "
                        f"{er.service_provider or 'unknown provider'}) found in subscription {sub_id}.",
                        evidence_ref=f"discovery:azure_{sub_id}.express_route_circuits",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Reliability",
                            control="RE-3 — Use redundant connectivity",
                        ),
                        FrameworkMapping(
                            framework="ISO 27001:2022",
                            pillar="Network Security",
                            control="A.8.21 — Security of network services",
                        ),
                        FrameworkMapping(
                            framework="HIPAA §164.312",
                            pillar="Technical Safeguards",
                            control="(a)(2)(ii) — Automatic logoff / contingency operations; "
                            "availability of ePHI systems",
                        ),
                        FrameworkMapping(
                            framework="FedRAMP Moderate",
                            pillar="Contingency Planning",
                            control="CP-8 — Telecommunications Services (redundancy)",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.4",
                            control_name="Network Resilience",
                            alignment="Redundant circuits prevent single points of failure in hybrid connectivity",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_azure_appgw(self, agw, sub_id: str) -> None:
        if not agw.waf_enabled:
            self._emit(
                Finding(
                    rule_id=R_AZ_APPGW_WAF_DISABLED,
                    severity=_severity(R_AZ_APPGW_WAF_DISABLED),
                    resource_id=agw.id,
                    resource_type="Microsoft.Network/applicationGateways",
                    account_id=sub_id,
                    region=agw.location,
                    title="Application Gateway WAF is disabled",
                    observed_state=ObservedState(
                        fact=f"Application Gateway {agw.name} ({agw.sku_name}) has "
                        f"Web Application Firewall disabled.",
                        evidence_ref=f"discovery:azure_{sub_id}.application_gateways[id={agw.id}].waf_enabled",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="NS-4 — Protect applications from external network attacks",
                        ),
                        FrameworkMapping(
                            framework="PCI-DSS 4.0",
                            pillar="Network Security Controls",
                            control="Req 1.3 — Restrict inbound and outbound traffic",
                        ),
                        FrameworkMapping(
                            framework="ISO 27001:2022",
                            pillar="Network Security",
                            control="A.8.23 — Web filtering",
                        ),
                        FrameworkMapping(
                            framework="HIPAA §164.312",
                            pillar="Technical Safeguards",
                            control="(e)(1) — Transmission security: protect ePHI APIs "
                            "from injection and web-layer attacks",
                        ),
                        FrameworkMapping(
                            framework="FedRAMP Moderate",
                            pillar="System and Communications Protection",
                            control="SC-7 — Boundary Protection",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.2",
                            control_name="Traffic Management",
                            alignment="WAF provides application-layer traffic filtering at the perimeter",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Applications and Workloads",
                            control_id="4.0",
                            control_name="Application and Workload Protection",
                            alignment="Disabled WAF leaves application workloads without HTTP-layer attack inspection",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_azure_gateway_metrics(self, metrics, sub_id: str) -> None:
        for gm in metrics.gateway_metrics:
            if gm.utilization_pct and gm.utilization_pct > _HIGH_UTILIZATION_PCT:
                self._emit(
                    Finding(
                        rule_id=R_AZ_GW_SATURATION,
                        severity=_severity(R_AZ_GW_SATURATION),
                        resource_id=sub_id,
                        resource_type="Microsoft.Network/virtualNetworkGateways",
                        account_id=sub_id,
                        region="Global",
                        title="Virtual Network Gateway utilization exceeds 80%",
                        observed_state=ObservedState(
                            fact=f"Gateway {gm.gateway_name} has {gm.utilization_pct}% utilization.",
                            evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Performance Efficiency",
                                control="PE-3 — Monitor and optimize network performance",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.4",
                                control_name="Network Resilience",
                                alignment="Gateway saturation degrades hybrid connectivity resilience",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

    def _check_azure_firewall_metrics(self, metrics, sub_id: str) -> None:
        for fm in metrics.firewall_metrics:
            no_rule_hits = (
                fm.network_rule_hits_24h == 0
                and fm.app_rule_hits_24h == 0
                and fm.nat_rule_hits_24h == 0
            )
            if no_rule_hits or fm.data_processed_gb_24h == 0.0:
                self._emit(
                    Finding(
                        rule_id=R_AZ_FW_NO_HITS,
                        severity=_severity(R_AZ_FW_NO_HITS),
                        resource_id=sub_id,
                        resource_type="Microsoft.Network/azureFirewalls",
                        account_id=sub_id,
                        region="Global",
                        title="Azure Firewall present but processes 0 traffic",
                        observed_state=ObservedState(
                            fact=f"Firewall {fm.firewall_name} recorded 0 rule hits or 0 data processed in 24 hours. "
                            "It may be misconfigured or bypassed by routing.",
                            evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Security",
                                control="NS-4 — Protect applications from external network attacks",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.2",
                                control_name="Traffic Management",
                                alignment="Zero rule hits suggests traffic bypasses the firewall",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

    def _check_azure_lb_and_vnet_metrics(self, metrics, sub_id: str) -> None:
        for lm in metrics.lb_metrics:
            if (
                lm.snat_port_utilization_pct
                and lm.snat_port_utilization_pct > _HIGH_UTILIZATION_PCT
            ):
                self._emit(
                    Finding(
                        rule_id=R_AZ_LB_SNAT_EXHAUSTION,
                        severity=_severity(R_AZ_LB_SNAT_EXHAUSTION),
                        resource_id=sub_id,
                        resource_type="Microsoft.Network/loadBalancers",
                        account_id=sub_id,
                        region="Global",
                        title="Load Balancer SNAT port utilization exceeds 80%",
                        observed_state=ObservedState(
                            fact=f"Load Balancer {lm.lb_name} used {lm.snat_port_utilization_pct}% of allocated SNAT ports.",
                            evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Reliability",
                                control="RE-4 — Design for scale out",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.4",
                                control_name="Network Resilience",
                                alignment="SNAT exhaustion causes connection failures affecting resilience",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

        for vnet_id, util in metrics.vnet_utilization.items():
            if util > _CRITICAL_UTILIZATION_PCT:
                self._emit(
                    Finding(
                        rule_id=R_AZ_VNET_IP_EXHAUSTION,
                        severity=_severity(R_AZ_VNET_IP_EXHAUSTION),
                        resource_id=vnet_id,
                        resource_type="Microsoft.Network/virtualNetworks",
                        account_id=sub_id,
                        region="Global",
                        title="VNet IP space utilization exceeds 85%",
                        observed_state=ObservedState(
                            fact=f"VNet {vnet_id} has {util}% of its address space allocated to subnets.",
                            evidence_ref=f"discovery:azure_{sub_id}.network_metrics",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Reliability",
                                control="RE-2 — Design for capacity",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.4",
                                control_name="Network Resilience",
                                alignment="IP space exhaustion prevents new workload deployments",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

        self._check_azure_er_and_ddos_metrics(metrics, sub_id)
        self._check_azure_appgw_metrics(metrics, sub_id)

    def _check_azure_metrics(self, sub_topo: AzureSubscriptionTopology, sub_id: str) -> None:
        metrics = sub_topo.network_metrics
        if not metrics:
            return
        self._check_azure_gateway_metrics(metrics, sub_id)
        self._check_azure_firewall_metrics(metrics, sub_id)
        self._check_azure_lb_and_vnet_metrics(metrics, sub_id)

    def _check_azure_er_and_ddos_metrics(self, metrics, sub_id: str) -> None:
        for em in metrics.er_circuit_metrics:
            max_util = max(
                filter(None, [em.primary_utilization_pct, em.secondary_utilization_pct]),
                default=None,
            )
            if max_util and max_util > _HIGH_UTILIZATION_PCT:
                self._emit(
                    Finding(
                        rule_id=R_AZ_ER_SATURATION,
                        severity=_severity(R_AZ_ER_SATURATION),
                        resource_id=sub_id,
                        resource_type="Microsoft.Network/expressRouteCircuits",
                        account_id=sub_id,
                        region="Global",
                        title="ExpressRoute circuit bandwidth utilization exceeds 80%",
                        observed_state=ObservedState(
                            fact=f"ER circuit {em.circuit_name} primary utilization is "
                            f"{em.primary_utilization_pct}% "
                            f"(provisioned {em.bandwidth_mbps_provisioned} Mbps). "
                            f"At this rate the circuit will saturate under load.",
                            evidence_ref=f"discovery:azure_{sub_id}.network_metrics.er_circuit_metrics",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Performance Efficiency",
                                control="PE-3 — Monitor and optimize network performance",
                            ),
                            FrameworkMapping(
                                framework="FedRAMP Moderate",
                                pillar="Contingency Planning",
                                control="CP-8 — Telecommunications Services",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.4",
                                control_name="Network Resilience",
                                alignment="Circuit saturation degrades hybrid connectivity reliability",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

        if metrics.ddos_attack_events_24h > 0:
            ips = ", ".join(metrics.public_ips_under_ddos_attack[:5])
            self._emit(
                Finding(
                    rule_id=R_AZ_DDOS_ATTACK_DETECTED,
                    severity=_severity(R_AZ_DDOS_ATTACK_DETECTED),
                    resource_id=sub_id,
                    resource_type="Microsoft.Network/publicIPAddresses",
                    account_id=sub_id,
                    region="Global",
                    title="Active or recent DDoS attack detected on public IP resources",
                    observed_state=ObservedState(
                        fact=f"Azure Monitor reported IfUnderDDoSAttack > 0 on "
                        f"{metrics.ddos_attack_events_24h} public IP(s) "
                        f"in the last 24 hours. Affected IPs: {ips or 'unknown'}.",
                        evidence_ref=f"discovery:azure_{sub_id}.network_metrics.ddos_attack_events_24h",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="NS-4 — Protect applications from external network attacks",
                        ),
                        FrameworkMapping(
                            framework="FedRAMP Moderate",
                            pillar="System and Communications Protection",
                            control="SC-5 — Denial of Service Protection",
                        ),
                        FrameworkMapping(
                            framework="HIPAA §164.312",
                            pillar="Technical Safeguards",
                            control="(a)(2)(ii) — Contingency operations: protect ePHI "
                            "availability during attack",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.4",
                            control_name="Network Resilience",
                            alignment="Active DDoS attack directly threatens network resilience",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_azure_appgw_metrics(self, metrics, sub_id: str) -> None:
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
                and (agm.failed_requests_24h / agm.total_requests_24h)
                > _APPGW_FAILURE_RATE_THRESHOLD
            )
            if latency_breach or failure_rate_high:
                latency_str = (
                    f"{agm.backend_latency_ms_avg:.0f}ms" if agm.backend_latency_ms_avg else "N/A"
                )
                fail_pct = (
                    f"{(agm.failed_requests_24h / agm.total_requests_24h * 100):.1f}%"
                    if agm.total_requests_24h and agm.failed_requests_24h
                    else "N/A"
                )
                self._emit(
                    Finding(
                        rule_id=R_AZ_APPGW_HIGH_LATENCY,
                        severity=_severity(R_AZ_APPGW_HIGH_LATENCY),
                        resource_id=agm.appgw_name,
                        resource_type="Microsoft.Network/applicationGateways",
                        account_id=sub_id,
                        region="Global",
                        title="Application Gateway reports high backend latency or elevated failure rate",
                        observed_state=ObservedState(
                            fact=f"App Gateway {agm.appgw_name}: avg backend latency "
                            f"{latency_str} (threshold 2000ms), failure rate {fail_pct} "
                            f"(threshold 5%). WAF rule hits (24h): {agm.waf_rule_hits_24h}.",
                            evidence_ref=f"discovery:azure_{sub_id}.network_metrics.appgw_metrics[name={agm.appgw_name}]",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Reliability",
                                control="RE-4 — Design for capacity",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.4",
                                control_name="Network Resilience",
                                alignment="App Gateway capacity degradation indicates resilience gap",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

    def _check_azure_front_door_waf(self, policy, sub_id: str) -> None:
        if str(policy.policy_mode).lower() == "detection":
            self._emit(
                Finding(
                    rule_id=R_AZ_FRONTDOOR_WAF_DETECTION_MODE,
                    severity=_severity(R_AZ_FRONTDOOR_WAF_DETECTION_MODE),
                    resource_id=policy.id,
                    resource_type="Microsoft.Network/frontDoorWebApplicationFirewallPolicies",
                    account_id=sub_id,
                    region=policy.location,
                    title="Front Door WAF policy is in Detection mode, not Prevention",
                    observed_state=ObservedState(
                        fact=f"Front Door WAF policy {policy.name} is in Detection mode. "
                        f"Malicious requests are logged but not blocked. "
                        f"Custom rules: {policy.custom_rules_count}, "
                        f"Managed rule sets: {policy.managed_rules_count}.",
                        evidence_ref=f"discovery:azure_{sub_id}"
                        f".front_door_waf_policies[id={policy.id}].policy_mode",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="NS-4 — Protect applications from external network attacks",
                        ),
                        FrameworkMapping(
                            framework="PCI-DSS 4.0",
                            pillar="Network Security Controls",
                            control="Req 1.3 — Restrict inbound and outbound traffic",
                        ),
                        FrameworkMapping(
                            framework="FedRAMP Moderate",
                            pillar="System and Communications Protection",
                            control="SC-7 — Boundary Protection",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.2",
                            control_name="Traffic Management",
                            alignment="WAF in Detection mode does not block malicious traffic",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Applications and Workloads",
                            control_id="4.0",
                            control_name="Application and Workload Protection",
                            alignment="Detection-only WAF does not enforce blocking for application-layer attacks",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_azure_observability(self, sub_topo: AzureSubscriptionTopology, sub_id: str) -> None:
        obs = sub_topo.observability
        if not obs:
            return

        if obs.nsg_flow_logs_enabled > 0 and obs.traffic_analytics_enabled == 0:
            self._emit(
                Finding(
                    rule_id=R_AZ_TRAFFIC_ANALYTICS_MISSING,
                    severity=_severity(R_AZ_TRAFFIC_ANALYTICS_MISSING),
                    resource_id=sub_id,
                    resource_type="Microsoft.Network/networkSecurityGroups",
                    account_id=sub_id,
                    region="Global",
                    title="NSG Flow Logs are enabled but Traffic Analytics is disabled",
                    observed_state=ObservedState(
                        fact=f"Subscription has {obs.nsg_flow_logs_enabled} active flow "
                        f"logs, but {obs.traffic_analytics_enabled} have Traffic "
                        f"Analytics enabled.",
                        evidence_ref=f"discovery:azure_{sub_id}.observability",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="NS-2 — Monitor network security",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.2",
                            control_name="Traffic Management",
                            alignment="Traffic Analytics provides flow-level visibility for zero trust verification",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        if obs.firewalls_total > 0 and obs.firewalls_with_diagnostics < obs.firewalls_total:
            missing = obs.firewalls_total - obs.firewalls_with_diagnostics
            self._emit(
                Finding(
                    rule_id=R_AZ_FW_NO_DIAGNOSTICS,
                    severity=_severity(R_AZ_FW_NO_DIAGNOSTICS),
                    resource_id=sub_id,
                    resource_type="Microsoft.Network/azureFirewalls",
                    account_id=sub_id,
                    region="Global",
                    title="Azure Firewall lacks Log Analytics diagnostic settings",
                    observed_state=ObservedState(
                        fact=f"{missing} of {obs.firewalls_total} Azure Firewall(s) "
                        f"in subscription {sub_id} have no Log Analytics diagnostic "
                        f"sink. Firewall rule logs and threat intel logs are lost.",
                        evidence_ref=f"discovery:azure_{sub_id}.observability"
                        f".firewalls_with_diagnostics",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="NS-3 — Deploy firewall at the edge of enterprise network",
                        ),
                        FrameworkMapping(
                            framework="NIST CSF",
                            pillar="Detect",
                            control="DE.CM-1 — The network is monitored to detect potential "
                            "cybersecurity events",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.2",
                            control_name="Traffic Management",
                            alignment="Firewall logs are required to audit and verify traffic management policies",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

        if obs.bastion_total > 0 and obs.bastion_with_diagnostics < obs.bastion_total:
            missing = obs.bastion_total - obs.bastion_with_diagnostics
            self._emit(
                Finding(
                    rule_id=R_AZ_BASTION_NO_DIAGNOSTICS,
                    severity=_severity(R_AZ_BASTION_NO_DIAGNOSTICS),
                    resource_id=sub_id,
                    resource_type="Microsoft.Network/bastionHosts",
                    account_id=sub_id,
                    region="Global",
                    title="Azure Bastion lacks session audit logging",
                    observed_state=ObservedState(
                        fact=f"{missing} of {obs.bastion_total} Bastion host(s) "
                        f"in subscription {sub_id} have no Log Analytics diagnostic "
                        f"sink. SSH/RDP session audit trails are unavailable.",
                        evidence_ref=f"discovery:azure_{sub_id}.observability"
                        f".bastion_with_diagnostics",
                    ),
                    framework_mappings=[
                        FrameworkMapping(
                            framework="Azure Well-Architected Framework",
                            pillar="Security",
                            control="PA-2 — Avoid standing access for user accounts and "
                            "permissions",
                        ),
                        FrameworkMapping(
                            framework="NIST CSF",
                            pillar="Detect",
                            control="DE.CM-3 — Personnel activity is monitored",
                        ),
                        FrameworkMapping(
                            framework="CISA ZTMM v2",
                            version="v2",
                            pillar="Networks",
                            control_id="3.2",
                            control_name="Traffic Management",
                            alignment="Session logging provides audit trail for privileged access paths",
                        ),
                    ],
                    status=FindingStatus.OPEN,
                )
            )

    def _check_azure_peering_gateway_transit(
        self, sub_topo: AzureSubscriptionTopology, sub_id: str
    ) -> None:
        for vnet in sub_topo.vnets:
            # A gateway has no vnet_id — it lives in a GatewaySubnet, and an ARM
            # subnet id nests under its VNet id as "<vnet_id>/subnets/<name>".
            # Reading gw.vnet_id raised AttributeError for any subscription that
            # actually had a gateway (TODO.md T-410).
            has_local_gw = any(
                gw.subnet_id and gw.subnet_id.startswith(f"{vnet.id}/")
                for gw in sub_topo.virtual_network_gateways or []
            )
            for peering in vnet.peerings:
                if peering.allow_gateway_transit and not has_local_gw:
                    self._emit(
                        Finding(
                            rule_id=R_AZ_PEERING_ALLOW_GW_TRANSIT,
                            severity=_severity(R_AZ_PEERING_ALLOW_GW_TRANSIT),
                            resource_id=vnet.id,
                            resource_type="Microsoft.Network/virtualNetworks/virtualNetworkPeerings",
                            account_id=sub_id,
                            region=vnet.location,
                            title="VNet peering allows gateway transit but VNet has no gateway",
                            observed_state=ObservedState(
                                fact=f"Peering {peering.name} on VNet {vnet.name} has "
                                f"allow_gateway_transit=True but no virtual network gateway "
                                f"exists in this VNet. Spoke VNets attempting to use this "
                                f"transit path will have no effective route.",
                                evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}]"
                                f".peerings[name={peering.name}].allow_gateway_transit",
                            ),
                            framework_mappings=[
                                FrameworkMapping(
                                    framework="Azure Well-Architected Framework",
                                    pillar="Security",
                                    control="NS-1 — Establish network segmentation boundaries",
                                ),
                                FrameworkMapping(
                                    framework="FedRAMP Moderate",
                                    pillar="System and Communications Protection",
                                    control="SC-7 — Boundary Protection",
                                ),
                                FrameworkMapping(
                                    framework="CISA ZTMM v2",
                                    version="v2",
                                    pillar="Networks",
                                    control_id="3.1",
                                    control_name="Network Segmentation",
                                    alignment="Misconfigured peering can create unintended network paths",
                                ),
                            ],
                            status=FindingStatus.OPEN,
                        )
                    )

    def _check_azure_vnet_flow_logs(self, sub_topo: AzureSubscriptionTopology, sub_id: str) -> None:
        for vnet in sub_topo.vnets:
            if not vnet.flow_logs_enabled:
                self._emit(
                    Finding(
                        rule_id=R_AZ_VNET_NO_FLOW_LOGS,
                        severity=_severity(R_AZ_VNET_NO_FLOW_LOGS),
                        resource_id=vnet.id,
                        resource_type="Microsoft.Network/virtualNetworks",
                        account_id=sub_id,
                        region=vnet.location,
                        title="VNet has no NSG flow logs enabled",
                        observed_state=ObservedState(
                            fact=f"VNet {vnet.name} ({vnet.id}) in {vnet.location} has "
                            f"flow_logs_enabled=False. Network traffic to/from this VNet "
                            f"produces no telemetry for incident investigation.",
                            evidence_ref=f"discovery:azure_{sub_id}.vnets[id={vnet.id}]"
                            f".flow_logs_enabled",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Security",
                                control="NS-2 — Monitor network security",
                            ),
                            FrameworkMapping(
                                framework="NIST CSF",
                                pillar="Detect",
                                control="DE.CM-1 — The network is monitored to detect "
                                "potential cybersecurity events",
                            ),
                            FrameworkMapping(
                                framework="HIPAA §164.312",
                                pillar="Technical Safeguards",
                                control="(b) — Audit controls: hardware/software activity "
                                "records for ePHI systems",
                            ),
                            FrameworkMapping(
                                framework="FedRAMP Moderate",
                                pillar="Audit and Accountability",
                                control="AU-2 — Audit Events",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.2",
                                control_name="Traffic Management",
                                alignment="Flow logs enable traffic visibility required for zero trust enforcement",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

    def _check_azure_peering_and_routing(
        self, sub_topo: AzureSubscriptionTopology, sub_id: str
    ) -> None:
        self._check_azure_peering_gateway_transit(sub_topo, sub_id)
        self._check_azure_vnet_flow_logs(sub_topo, sub_id)
        rt_by_name = {rt.name: rt for rt in sub_topo.route_tables}
        for vnet in sub_topo.vnets:
            self._check_azure_fw_bypass(vnet, rt_by_name, sub_id)

    def _check_azure_fw_bypass(self, vnet, rt_by_name: dict, sub_id: str) -> None:
        is_spoke = any(p.allow_forwarded_traffic or p.use_remote_gateways for p in vnet.peerings)
        if not is_spoke:
            return

        for subnet in vnet.subnets:
            if subnet.name.lower() in self._INFRA_SUBNETS:
                continue
            rt = rt_by_name.get(subnet.route_table_name or "")
            if rt is None:
                self._emit(
                    Finding(
                        rule_id=R_AZ_PEERING_FW_BYPASS,
                        severity=_severity(R_AZ_PEERING_FW_BYPASS),
                        resource_id=subnet.id,
                        resource_type="Microsoft.Network/virtualNetworks/subnets",
                        account_id=sub_id,
                        region=vnet.location,
                        title="Spoke subnet has no UDR — hub firewall may be bypassed",
                        observed_state=ObservedState(
                            fact=f"Subnet {subnet.name} in spoke VNet {vnet.name} "
                            f"has no route table. Internet-bound traffic may egress "
                            f"directly rather than through the hub NVA/firewall.",
                            evidence_ref=f"discovery:azure_{sub_id}"
                            f".vnets[id={vnet.id}].subnets[id={subnet.id}]"
                            f".route_table_name",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Security",
                                control="NS-1 — Establish network segmentation boundaries",
                            ),
                            FrameworkMapping(
                                framework="Azure Security Benchmark",
                                pillar="Network Security",
                                control="NS-4",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.1",
                                control_name="Network Segmentation",
                                alignment="Traffic bypassing the hub firewall violates segmentation policy",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )
                continue

            has_forced_route = any(
                r.address_prefix == "0.0.0.0/0" and r.next_hop_type == "VirtualAppliance"
                for r in rt.routes
            )
            if not has_forced_route:
                self._emit(
                    Finding(
                        rule_id=R_AZ_PEERING_FW_BYPASS,
                        severity=_severity(R_AZ_PEERING_FW_BYPASS),
                        resource_id=subnet.id,
                        resource_type="Microsoft.Network/virtualNetworks/subnets",
                        account_id=sub_id,
                        region=vnet.location,
                        title="Spoke subnet UDR lacks 0.0.0.0/0 → NVA route",
                        observed_state=ObservedState(
                            fact=f"Subnet {subnet.name} in spoke VNet {vnet.name} "
                            f"has route table {rt.name} but no default route "
                            f"(0.0.0.0/0) pointing to a VirtualAppliance. "
                            f"Internet traffic may bypass the hub firewall.",
                            evidence_ref=f"discovery:azure_{sub_id}"
                            f".route_tables[name={rt.name}].routes",
                        ),
                        framework_mappings=[
                            FrameworkMapping(
                                framework="Azure Well-Architected Framework",
                                pillar="Security",
                                control="NS-1 — Establish network segmentation boundaries",
                            ),
                            FrameworkMapping(
                                framework="Azure Security Benchmark",
                                pillar="Network Security",
                                control="NS-4",
                            ),
                            FrameworkMapping(
                                framework="CISA ZTMM v2",
                                version="v2",
                                pillar="Networks",
                                control_id="3.1",
                                control_name="Network Segmentation",
                                alignment="Traffic bypassing the hub firewall violates segmentation policy",
                            ),
                        ],
                        status=FindingStatus.OPEN,
                    )
                )

    def _analyze_azure_subscription(self, sub_topo: AzureSubscriptionTopology) -> None:
        if sub_topo.discovery_blocked:
            return

        sub_id = sub_topo.subscription_id

        for vnet in sub_topo.vnets:
            self._check_azure_vnet(vnet, sub_id)

        for fw in sub_topo.firewalls:
            self._check_azure_firewall(fw, sub_id)

        self._check_azure_er_redundancy(sub_topo, sub_id)

        for agw in sub_topo.application_gateways:
            self._check_azure_appgw(agw, sub_id)

        self._check_azure_metrics(sub_topo, sub_id)

        for policy in sub_topo.front_door_waf_policies:
            self._check_azure_front_door_waf(policy, sub_id)

        self._check_azure_observability(sub_topo, sub_id)
        self._check_azure_peering_and_routing(sub_topo, sub_id)

    # ---------------------------------------------------------------- run

    def run(
        self,
        aws_topology: AWSTopology | None = None,
        azure_topology: AzureTopology | None = None,
    ) -> FindingsReport:
        """Execute analysis. Returns FindingsReport.

        Call sequence:
          1. Analyze AWS regions (if aws_topology provided)
          2. Analyze Azure subscriptions (if azure_topology provided)
          3. Validate escalations (DD-016)
          4. Write FindingsReport to store (unless dry_run)
          5. Return report
        """
        engagement_id = self.store.engagement_id
        if engagement_id is None:
            raise ValueError(
                "AnalysisEngine requires an EngagementStore bound to an engagement_id; "
                "construct it with EngagementStore(engagement_id=...)."
            )
        self._findings = []
        self._seen = set()

        progress = self.opts.progress_callback

        # AWS
        if aws_topology and self.opts.load_aws:
            total = len(aws_topology.regions)
            for i, region_topo in enumerate(aws_topology.regions):
                if progress:
                    progress("aws", i + 1, total, f"{region_topo.account_id}/{region_topo.region}")
                self._analyze_aws_region(region_topo)

        # Azure
        if azure_topology and self.opts.load_azure:
            total = len(azure_topology.subscriptions)
            for i, sub_topo in enumerate(azure_topology.subscriptions):
                if progress:
                    progress("azure", i + 1, total, sub_topo.subscription_id)
                self._analyze_azure_subscription(sub_topo)

        # Escalation check (DD-016)
        critical_findings = [f for f in self._findings if f.severity == FindingSeverity.CRITICAL]
        if critical_findings:
            logger.warning(
                "[%s] %d CRITICAL findings detected — escalation engine triggered",
                engagement_id,
                len(critical_findings),
            )
            self._escalation.process(engagement_id, critical_findings)

        report = FindingsReport(
            engagement_id=engagement_id,
            schema_version=FINDINGS_SCHEMA_VERSION,
            findings=self._findings,
            total_count=len(self._findings),
            critical_count=len(
                [f for f in self._findings if f.severity == FindingSeverity.CRITICAL]
            ),
            high_count=len([f for f in self._findings if f.severity == FindingSeverity.HIGH]),
            medium_count=len([f for f in self._findings if f.severity == FindingSeverity.MEDIUM]),
            low_count=len([f for f in self._findings if f.severity == FindingSeverity.LOW]),
            review_complete=False,  # DD-009: must be set to True manually
            generated_at=datetime.now(UTC).isoformat(),
        )

        if not self.opts.dry_run:
            self.store.write_findings_report(
                engagement_id,
                report.model_dump(),
            )
            logger.info(
                "[%s] FindingsReport written: %d findings (%d CRITICAL, %d HIGH, %d MEDIUM, %d LOW)",
                engagement_id,
                report.total_count,
                report.critical_count,
                report.high_count,
                report.medium_count,
                report.low_count,
            )

        return report
