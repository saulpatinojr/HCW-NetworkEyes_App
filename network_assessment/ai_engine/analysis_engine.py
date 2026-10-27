"""Phase D — AI Analysis Engine.

Consumes AWSTopology and AzureTopology checkpoints from EngagementStore.
Produces a versioned FindingsReport written back to EngagementStore.

The AWS rules (AWS-NET-*) live here. The Azure rules live in the engine package
(cna_azure_network_engine: AZ-NET-*, AZ-BCDR-*, AZ-COST-*); run() evaluates them through
network_assessment.modules.network.analysis.evaluate_azure and merges the result, so the CLI, the API and
the downstream lab edition produce the same Azure findings from the same rule set.

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

from network_assessment.ai_engine.observed_state_enforcer import ObservedStateEnforcer
from network_assessment.core.escalation_engine import CriticalFindingEscalationEngine
from network_assessment.core.findings_schema import (
    FINDINGS_SCHEMA_VERSION,
    Finding,
    FindingSeverity,
    FindingsReport,
    FindingStatus,
    FrameworkMapping,
    ObservedState,
    Unknown,
)
from network_assessment.core.persistence import EngagementStore
from network_assessment.core.topology.aws import AWSRegionTopology, AWSTopology
from network_assessment.core.topology.azure import AzureTopology
from network_assessment.modules.network.analysis.azure_findings import evaluate_azure

logger = logging.getLogger("network_assessment.analysis")

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

R_AWS_NO_NETWORK_FIREWALL = "AWS-NET-012"
R_AWS_WAF_NO_ASSOCIATION = "AWS-NET-013"

# Severity thresholds (AWS rules; Azure severities live in each rule's RuleMeta)
_CRITICAL_IDS = {
    R_AWS_SG_UNRESTRICTED_SSH,
    R_AWS_SG_UNRESTRICTED_RDP,
    R_AWS_SG_UNRESTRICTED_ALL,
}
_HIGH_IDS = {
    R_AWS_VPC_FLOW_LOGS_DISABLED,
}

_MEDIUM_IDS = {
    R_AWS_WAF_NO_ASSOCIATION,
}


_PORT_SSH: int = 22
_PORT_RDP: int = 3389


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
        self._unknowns: list[Unknown] = []  # Azure rules the topology could not answer

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

    def _analyze_azure(self, azure_topology: AzureTopology) -> None:
        """Evaluate the Azure rule registry and merge its findings into this run.

        The registry already enforced observed state, framework mappings and
        deduplication within the topology; the register here keeps the AWS and
        Azure halves of one run from colliding and records the CRITICAL
        escalations the same way _emit does.
        """
        progress = self.opts.progress_callback

        def _report(index: int, total: int, sub_topo, _findings) -> None:
            if progress:
                progress("azure", index, total, sub_topo.subscription_id)

        evaluation = evaluate_azure(azure_topology, progress=_report)
        self._unknowns = list(evaluation.unknowns)
        for finding in evaluation.findings:
            key = self._dedup_key(finding.rule_id, finding.resource_id)
            if key in self._seen:
                continue
            self._seen.add(key)
            if finding.severity == FindingSeverity.CRITICAL:
                self._escalation.flag(finding)
            self._findings.append(finding)

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
        self._unknowns = []

        progress = self.opts.progress_callback

        # AWS
        if aws_topology and self.opts.load_aws:
            total = len(aws_topology.regions)
            for i, region_topo in enumerate(aws_topology.regions):
                if progress:
                    progress("aws", i + 1, total, f"{region_topo.account_id}/{region_topo.region}")
                self._analyze_aws_region(region_topo)

        # Azure — the engine's typed rule registry (cna_azure_network_engine)
        if azure_topology and self.opts.load_azure:
            self._analyze_azure(azure_topology)

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
            unknowns=self._unknowns,
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
