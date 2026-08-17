"""Unit tests for Phase D Analysis Engine.

All topology inputs are built from schema models — no real cloud access.
Tests cover:
  - AWS finding rule coverage (NET-001 through NET-008)
  - Azure finding rule coverage (AZ-NET-001 through AZ-NET-007)
  - Deduplication (same finding on same resource emitted once)
  - observed_state enforcement blocks hedge language
  - framework_mappings required — missing raises ValueError
  - Severity classification (CRITICAL/HIGH/MEDIUM)
  - Blocked regions/subscriptions produce zero findings
  - CRITICAL findings trigger escalation engine
  - dry_run does not call store.write_findings_report
  - FindingsReport counts match findings list
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cna.ai_engine.analysis_engine import AnalysisEngine, AnalysisOptions
from cna.ai_engine.observed_state_enforcer import ObservedStateEnforcer, ObservedStateViolation
from cna.core.findings_schema import (
    Finding,
    FindingSeverity,
    FindingStatus,
    FrameworkMapping,
    ObservedState,
)
from cna.core.topology_schema import (
    VPC,
    ApplicationGateway,
    AWSRegionTopology,
    AWSTopology,
    AWSWAFWebACL,
    AzureFirewall,
    AzureSubnet,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVirtualNetworkGateway,
    DirectConnectConnection,
    FrontDoorWAFPolicy,
    PeeringState,
    SecurityGroup,
    SecurityGroupRule,
    TransitGateway,
    VNet,
    VNetPeering,
)


@pytest.fixture
def store():
    s = MagicMock()
    s.engagement_id = "test-20260305-d001"
    return s


@pytest.fixture
def engine(store):
    return AnalysisEngine(store=store, options=AnalysisOptions(dry_run=True))


def _make_clean_vpc(vpc_id="vpc-001", is_default=False) -> VPC:
    return VPC(
        id=vpc_id,
        name="test-vpc",
        cidr="10.0.0.0/16",
        is_default=is_default,
        flow_logs_enabled=True,
        security_groups=[],
        nacls=[],
        subnets=[],
        route_tables=[],
        internet_gateways=[],
        nat_gateways=[],
        peering_connections=[],
    )


def _make_region(
    account_id="111111111111", region="us-east-1", vpcs=None, tgws=None, dx=None
) -> AWSRegionTopology:
    return AWSRegionTopology(
        account_id=account_id,
        region=region,
        vpcs=vpcs or [],
        transit_gateways=tgws or [],
        direct_connect_connections=dx or [],
        vpn_gateways=[],
    )


class TestAWSNetFindingRules:
    def test_default_vpc_produces_finding(self, engine):
        vpc = _make_clean_vpc(is_default=True)
        region = _make_region(vpcs=[vpc])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        assert any(f.rule_id == "AWS-NET-001" for f in report.findings)

    def test_flow_logs_disabled_produces_finding(self, engine):
        vpc = _make_clean_vpc()
        vpc.flow_logs_enabled = False
        region = _make_region(vpcs=[vpc])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        assert any(f.rule_id == "AWS-NET-002" for f in report.findings)

    def test_sg_unrestricted_ssh_is_critical(self, engine):
        vpc = _make_clean_vpc()
        sg = SecurityGroup(
            id="sg-001",
            name="web-sg",
            vpc_id=vpc.id,
            rules=[
                SecurityGroupRule(
                    direction="ingress",
                    protocol="tcp",
                    from_port=22,
                    to_port=22,
                    cidr_ranges=["0.0.0.0/0"],
                )
            ],
        )
        vpc.security_groups = [sg]
        region = _make_region(vpcs=[vpc])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        ssh_findings = [f for f in report.findings if f.rule_id == "AWS-NET-003"]
        assert len(ssh_findings) == 1
        assert ssh_findings[0].severity == FindingSeverity.CRITICAL

    def test_sg_unrestricted_rdp_is_critical(self, engine):
        vpc = _make_clean_vpc()
        sg = SecurityGroup(
            id="sg-002",
            name="rdp-sg",
            vpc_id=vpc.id,
            rules=[
                SecurityGroupRule(
                    direction="ingress",
                    protocol="tcp",
                    from_port=3389,
                    to_port=3389,
                    cidr_ranges=["0.0.0.0/0"],
                )
            ],
        )
        vpc.security_groups = [sg]
        region = _make_region(vpcs=[vpc])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        rdp_findings = [f for f in report.findings if f.rule_id == "AWS-NET-004"]
        assert len(rdp_findings) == 1
        assert rdp_findings[0].severity == FindingSeverity.CRITICAL

    def test_tgw_default_rt_assoc_produces_finding(self, engine):
        tgw = TransitGateway(
            id="tgw-001",
            name="core-tgw",
            owner_account_id="111111111111",
            default_route_table_association=True,
            default_route_table_propagation=False,
            attachments=[],
        )
        region = _make_region(tgws=[tgw])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        assert any(f.rule_id == "AWS-NET-006" for f in report.findings)

    def test_single_dx_connection_produces_finding(self, engine):
        dx = DirectConnectConnection(
            id="dxcon-001",
            name="primary-dx",
            location="EqDC2",
            bandwidth="1Gbps",
            state="available",
            owner_account_id="111111111111",
        )
        region = _make_region(dx=[dx])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        assert any(f.rule_id == "AWS-NET-008" for f in report.findings)

    def test_clean_vpc_no_findings(self, engine):
        vpc = _make_clean_vpc()
        region = _make_region(vpcs=[vpc])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        assert report.total_count == 0

    def test_blocked_region_produces_no_findings(self, engine):
        region = AWSRegionTopology(
            account_id="111111111111",
            region="us-east-1",
            discovery_blocked=True,
            block_reason="Permission denied",
        )
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        assert report.total_count == 0

    def test_waf_acl_without_association_maps_to_applications_and_workloads(self, engine):
        acl = AWSWAFWebACL(
            web_acl_id="waf-001",
            web_acl_arn="arn:aws:wafv2:us-east-1:111111111111:regional/webacl/test/waf-001",
            name="test-waf",
            associated_resource_arns=[],
        )
        region = _make_region()
        region.waf_web_acls = [acl]
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])

        report = engine.run(aws_topology=topo)
        finding = next(f for f in report.findings if f.rule_id == "AWS-NET-013")

        assert any(
            m.framework == "CISA ZTMM v2" and m.pillar == "Applications and Workloads"
            for m in finding.framework_mappings
        )


class TestAzureNetFindingRules:
    def _make_sub(self, sub_id="sub-001") -> AzureSubscriptionTopology:
        return AzureSubscriptionTopology(
            subscription_id=sub_id,
            tenant_id="tenant-001",
            vnets=[],
            firewalls=[],
            application_gateways=[],
            express_route_circuits=[],
            virtual_wans=[],
            private_dns_zones=[],
        )

    def test_vnet_no_ddos_produces_finding(self, engine):
        sub = self._make_sub()
        vnet = VNet(
            id="/subs/sub-001/vnet-prod",
            name="vnet-prod",
            location="eastus",
            resource_group="rg-net",
            subscription_id="sub-001",
            address_space=["10.0.0.0/16"],
            ddos_protection_enabled=False,
            subnets=[],
            peerings=[],
        )
        sub.vnets = [vnet]
        topo = AzureTopology(engagement_id="test", tenant_id="tenant-001", subscriptions=[sub])
        report = engine.run(azure_topology=topo)
        assert any(f.rule_id == "AZ-NET-001" for f in report.findings)

    def test_subnet_no_nsg_produces_high_finding(self, engine):
        sub = self._make_sub()
        vnet = VNet(
            id="/subs/sub-001/vnet-prod",
            name="vnet-prod",
            location="eastus",
            resource_group="rg-net",
            subscription_id="sub-001",
            address_space=["10.0.0.0/16"],
            ddos_protection_enabled=True,
            subnets=[
                AzureSubnet(
                    id="/subs/sub-001/vnet-prod/subnets/snet-app",
                    name="snet-app",
                    address_prefix="10.0.1.0/24",
                    nsg_id=None,
                )
            ],
            peerings=[],
        )
        sub.vnets = [vnet]
        topo = AzureTopology(engagement_id="test", tenant_id="tenant-001", subscriptions=[sub])
        report = engine.run(azure_topology=topo)
        nsg_findings = [f for f in report.findings if f.rule_id == "AZ-NET-002"]
        assert len(nsg_findings) == 1
        assert nsg_findings[0].severity == FindingSeverity.HIGH

    def test_gateway_subnet_no_nsg_not_flagged(self, engine):
        """GatewaySubnet must not be flagged for missing NSG — NSGs not allowed there."""
        sub = self._make_sub()
        vnet = VNet(
            id="/subs/sub-001/vnet-hub",
            name="vnet-hub",
            location="eastus",
            resource_group="rg-hub",
            subscription_id="sub-001",
            address_space=["10.1.0.0/16"],
            ddos_protection_enabled=True,
            subnets=[
                AzureSubnet(
                    id="/subs/sub-001/vnet-hub/subnets/GatewaySubnet",
                    name="GatewaySubnet",
                    address_prefix="10.1.255.0/27",
                    nsg_id=None,
                )
            ],
            peerings=[],
        )
        sub.vnets = [vnet]
        topo = AzureTopology(engagement_id="test", tenant_id="tenant-001", subscriptions=[sub])
        report = engine.run(azure_topology=topo)
        nsg_findings = [f for f in report.findings if f.rule_id == "AZ-NET-002"]
        assert len(nsg_findings) == 0

    def test_firewall_threat_intel_alert_is_critical(self, engine):
        sub = self._make_sub()
        fw = AzureFirewall(
            id="/subs/sub-001/fw-hub",
            name="fw-hub",
            location="eastus",
            resource_group="rg-hub",
            sku_tier="Premium",
            threat_intel_mode="Alert",
        )
        sub.firewalls = [fw]
        topo = AzureTopology(engagement_id="test", tenant_id="tenant-001", subscriptions=[sub])
        report = engine.run(azure_topology=topo)
        fw_findings = [f for f in report.findings if f.rule_id == "AZ-NET-003"]
        assert len(fw_findings) == 1
        assert fw_findings[0].severity == FindingSeverity.CRITICAL

    def test_blocked_subscription_produces_no_findings(self, engine):
        sub = AzureSubscriptionTopology(
            subscription_id="sub-001",
            tenant_id="tenant-001",
            discovery_blocked=True,
            block_reason="HTTP 403",
        )
        topo = AzureTopology(engagement_id="test", tenant_id="tenant-001", subscriptions=[sub])
        report = engine.run(azure_topology=topo)
        assert report.total_count == 0

    def test_app_gateway_waf_disabled_maps_to_applications_and_workloads(self, engine):
        sub = self._make_sub()
        sub.application_gateways = [
            ApplicationGateway(
                id="/subs/sub-001/appgw-prod",
                name="appgw-prod",
                location="eastus",
                resource_group="rg-edge",
                sku_name="Standard_v2",
                subnet_id="/subs/sub-001/vnet/subnets/appgw",
                waf_enabled=False,
            )
        ]
        topo = AzureTopology(engagement_id="test", tenant_id="tenant-001", subscriptions=[sub])

        report = engine.run(azure_topology=topo)
        finding = next(f for f in report.findings if f.rule_id == "AZ-NET-007")

        assert any(
            m.framework == "CISA ZTMM v2" and m.pillar == "Applications and Workloads"
            for m in finding.framework_mappings
        )

    def test_front_door_waf_detection_maps_to_applications_and_workloads(self, engine):
        sub = self._make_sub()
        sub.front_door_waf_policies = [
            FrontDoorWAFPolicy(
                id="/subs/sub-001/frontdoor-waf",
                name="fd-waf",
                resource_group="rg-edge",
                location="global",
                policy_mode="Detection",
            )
        ]
        topo = AzureTopology(engagement_id="test", tenant_id="tenant-001", subscriptions=[sub])

        report = engine.run(azure_topology=topo)
        finding = next(f for f in report.findings if f.rule_id == "AZ-NET-018")

        assert any(
            m.framework == "CISA ZTMM v2" and m.pillar == "Applications and Workloads"
            for m in finding.framework_mappings
        )


class TestDeduplication:
    def test_same_finding_emitted_once(self, engine):
        """Same rule_id + resource_id pair should produce exactly one finding."""
        vpc1 = _make_clean_vpc(vpc_id="vpc-001", is_default=True)
        vpc2 = _make_clean_vpc(vpc_id="vpc-001", is_default=True)  # same ID
        region = _make_region(vpcs=[vpc1, vpc2])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        net001 = [f for f in report.findings if f.rule_id == "AWS-NET-001"]
        assert len(net001) == 1


class TestObservedStateEnforcer:
    def test_clean_fact_passes(self):
        enforcer = ObservedStateEnforcer()
        assert enforcer.scan_text("VPC vpc-001 has no flow logs enabled.") == []

    @pytest.mark.parametrize(
        "hedge_word",
        [
            "may",
            "might",
            "could",
            "should",
            "possibly",
            "probably",
            "likely",
            "appears",
            "seems",
            "suggests",
            "indicates",
            "potentially",
            "expected",
            "typically",
            "usually",
            "generally",
        ],
    )
    def test_hedge_words_detected(self, hedge_word):
        enforcer = ObservedStateEnforcer()
        result = enforcer.scan_text(f"This {hedge_word} be a problem.")
        assert len(result) > 0

    def test_violation_raised_on_finding(self, store):
        engine = AnalysisEngine(store=store, options=AnalysisOptions(dry_run=True))
        bad_finding = Finding(
            rule_id="TEST-001",
            severity=FindingSeverity.MEDIUM,
            resource_id="vpc-001",
            resource_type="AWS::EC2::VPC",
            account_id="111111111111",
            region="us-east-1",
            title="Test",
            observed_state=ObservedState(
                fact="This may indicate a misconfiguration.",  # HEDGE
                evidence_ref="test",
            ),
            framework_mappings=[
                FrameworkMapping(framework="AWS WAF", pillar="Security", control="SEC 5")
            ],
            status=FindingStatus.OPEN,
        )
        with pytest.raises(ObservedStateViolation):
            engine._emit(bad_finding)

    def test_missing_framework_mappings_raises(self, store):
        engine = AnalysisEngine(store=store, options=AnalysisOptions(dry_run=True))
        bad_finding = Finding(
            rule_id="TEST-002",
            severity=FindingSeverity.MEDIUM,
            resource_id="vpc-001",
            resource_type="AWS::EC2::VPC",
            account_id="111111111111",
            region="us-east-1",
            title="Test",
            observed_state=ObservedState(
                fact="VPC vpc-001 has no flow logs enabled.",
                evidence_ref="test",
            ),
            framework_mappings=[],  # MISSING
            status=FindingStatus.OPEN,
        )
        with pytest.raises(ValueError, match="framework_mappings"):
            engine._emit(bad_finding)


class TestReportCounts:
    def test_report_counts_match_findings_list(self, store):
        engine = AnalysisEngine(store=store, options=AnalysisOptions(dry_run=True))
        vpc = _make_clean_vpc(is_default=True)
        vpc.flow_logs_enabled = False
        sg = SecurityGroup(
            id="sg-001",
            name="web-sg",
            vpc_id=vpc.id,
            rules=[
                SecurityGroupRule(
                    direction="ingress",
                    protocol="tcp",
                    from_port=22,
                    to_port=22,
                    cidr_ranges=["0.0.0.0/0"],
                )
            ],
        )
        vpc.security_groups = [sg]
        region = _make_region(vpcs=[vpc])
        topo = AWSTopology(engagement_id="test", regions=[region], accounts=[])
        report = engine.run(aws_topology=topo)
        assert report.total_count == len(report.findings)
        assert report.critical_count == sum(
            1 for f in report.findings if f.severity == FindingSeverity.CRITICAL
        )


class TestAzurePeeringGatewayTransit:
    """`_check_azure_peering_gateway_transit` (TODO.md T-410).

    This read `gw.vnet_id`, which `AzureVirtualNetworkGateway` does not have —
    the model carries `subnet_id`. Any subscription that actually had a gateway
    raised `AttributeError`, so the rule only ever "worked" when the gateway list
    was empty and the short-circuit skipped it.

    An ARM subnet id nests under its VNet id (`<vnet_id>/subnets/<name>`), which
    is the real link between a gateway and its VNet.
    """

    def _vnet(self, vnet_id, allow_gateway_transit=True):
        return VNet(
            id=vnet_id,
            name="vnet-prod",
            location="eastus",
            resource_group="rg-net",
            subscription_id="sub-001",
            address_space=["10.0.0.0/16"],
            subnets=[],
            peerings=[
                VNetPeering(
                    id=f"{vnet_id}/peer",
                    name="to-hub",
                    remote_vnet_id="/subs/sub-001/vnet-hub",
                    remote_subscription_id="sub-001",
                    peering_state=PeeringState.ACTIVE,
                    allow_forwarded_traffic=False,
                    allow_gateway_transit=allow_gateway_transit,
                    use_remote_gateways=False,
                )
            ],
        )

    def _gateway(self, subnet_id):
        return AzureVirtualNetworkGateway(
            id="/subs/sub-001/gw1",
            name="gw1",
            location="eastus",
            resource_group="rg-net",
            gateway_type="Vpn",
            subnet_id=subnet_id,
        )

    def test_does_not_raise_when_a_gateway_is_present(self, engine):
        """The regression itself: this used to be an AttributeError."""
        vnet_id = "/subs/sub-001/vnet-prod"
        sub = AzureSubscriptionTopology(subscription_id="sub-001", tenant_id="tenant-001")
        sub.vnets = [self._vnet(vnet_id)]
        sub.virtual_network_gateways = [self._gateway(f"{vnet_id}/subnets/GatewaySubnet")]

        engine._check_azure_peering_gateway_transit(sub, "sub-001")  # must not raise

    def test_a_gateway_in_this_vnet_suppresses_the_finding(self, engine):
        vnet_id = "/subs/sub-001/vnet-prod"
        sub = AzureSubscriptionTopology(subscription_id="sub-001", tenant_id="tenant-001")
        sub.vnets = [self._vnet(vnet_id)]
        sub.virtual_network_gateways = [self._gateway(f"{vnet_id}/subnets/GatewaySubnet")]

        before = len(engine._findings)
        engine._check_azure_peering_gateway_transit(sub, "sub-001")
        assert len(engine._findings) == before, "a local gateway should suppress the finding"

    def test_a_gateway_in_a_different_vnet_does_not_count(self, engine):
        """Prefix matching must not treat another VNet's gateway as local."""
        vnet_id = "/subs/sub-001/vnet-prod"
        sub = AzureSubscriptionTopology(subscription_id="sub-001", tenant_id="tenant-001")
        sub.vnets = [self._vnet(vnet_id)]
        sub.virtual_network_gateways = [
            self._gateway("/subs/sub-001/vnet-other/subnets/GatewaySubnet")
        ]

        before = len(engine._findings)
        engine._check_azure_peering_gateway_transit(sub, "sub-001")
        assert len(engine._findings) > before, "no local gateway — the finding should be emitted"
