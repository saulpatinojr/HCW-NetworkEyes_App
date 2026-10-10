"""Unit tests for Phase B diagram engine.

Tests generate valid draw.io XML and Mermaid from minimal topology fixtures.
No filesystem writes — all tests operate on string output only.
No draw.io CLI required.
"""

import pytest

from cna.core.topology_schema import (
    VPC,
    AWSNetworkFirewall,
    AWSRegionTopology,
    AWSTopology,
    AWSWAFWebACL,
    AzureSubnet,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVHub,
    AzureVWan,
    DirectConnectConnection,
    ManagementGroup,
    Subnet,
    SubnetType,
    TransitGateway,
    VNet,
    VpnGateway,
)
from cna.diagram_engine.drawio_generator import (
    generate_tgw_topology,
    generate_vnet_topology,
    generate_vpc_topology,
    generate_vwan_topology,
)
from cna.diagram_engine.mermaid_generator import (
    generate_aws_account_hierarchy,
    generate_azure_mg_hierarchy,
    generate_landing_zone_diagram,
)

# ── Fixtures ────────────────────────────────────────────────────────────


@pytest.fixture
def minimal_vpc_region():
    return AWSRegionTopology(
        account_id="123456789012",
        region="us-east-1",
        vpcs=[
            VPC(
                id="vpc-abc123",
                name="prod-vpc",
                cidr="10.0.0.0/16",
                subnets=[
                    Subnet(
                        id="subnet-a",
                        name="public-a",
                        cidr="10.0.1.0/24",
                        az="us-east-1a",
                        subnet_type=SubnetType.PUBLIC,
                    ),
                    Subnet(
                        id="subnet-b",
                        name="private-b",
                        cidr="10.0.2.0/24",
                        az="us-east-1b",
                        subnet_type=SubnetType.PRIVATE,
                    ),
                ],
            )
        ],
    )


@pytest.fixture
def empty_vpc_region():
    return AWSRegionTopology(account_id="111111111111", region="eu-west-1", vpcs=[])


@pytest.fixture
def blocked_region():
    return AWSRegionTopology(
        account_id="222222222222",
        region="ap-southeast-1",
        discovery_blocked=True,
        block_reason="SCP denied ec2:DescribeVpcs",
    )


@pytest.fixture
def minimal_vnet_sub():
    return AzureSubscriptionTopology(
        subscription_id="sub-001",
        tenant_id="tenant-001",
        vnets=[
            VNet(
                id="/subscriptions/sub-001/resourceGroups/rg-prod/providers/Microsoft.Network/virtualNetworks/prod-vnet",
                name="prod-vnet",
                location="eastus",
                resource_group="rg-prod",
                subscription_id="sub-001",
                address_space=["10.1.0.0/16"],
                subnets=[
                    AzureSubnet(id="sn-001", name="app-subnet", address_prefix="10.1.1.0/24"),
                    AzureSubnet(
                        id="sn-002",
                        name="db-subnet",
                        address_prefix="10.1.2.0/24",
                        nsg_id="/nsg/db-nsg",
                    ),
                ],
            )
        ],
    )


# ── draw.io generator tests ──────────────────────────────────────────────


class TestVpcTopology:
    def test_produces_valid_xml(self, minimal_vpc_region):
        xml = generate_vpc_topology(minimal_vpc_region)
        assert xml.startswith("<mxfile")
        assert "</mxfile>" in xml

    def test_contains_vpc_name(self, minimal_vpc_region):
        xml = generate_vpc_topology(minimal_vpc_region)
        assert "prod-vpc" in xml

    def test_contains_subnet_cidr(self, minimal_vpc_region):
        xml = generate_vpc_topology(minimal_vpc_region)
        assert "10.0.1.0/24" in xml
        assert "10.0.2.0/24" in xml

    def test_public_subnet_style(self, minimal_vpc_region):
        xml = generate_vpc_topology(minimal_vpc_region)
        # Public subnets get yellow fill
        assert "fff2cc" in xml

    def test_private_subnet_style(self, minimal_vpc_region):
        xml = generate_vpc_topology(minimal_vpc_region)
        # Private subnets get red fill
        assert "f8cecc" in xml

    def test_empty_region_produces_note(self, empty_vpc_region):
        xml = generate_vpc_topology(empty_vpc_region)
        assert "No VPCs found" in xml
        assert "</mxfile>" in xml

    def test_blocked_region_raises(self, blocked_region):
        with pytest.raises(ValueError, match="Discovery was blocked"):
            generate_vpc_topology(blocked_region)

    def test_xml_safe_characters(self):
        """Resource names with XML-unsafe chars must not break output."""
        region = AWSRegionTopology(
            account_id="123456789012",
            region="us-east-1",
            vpcs=[
                VPC(
                    id="vpc-special",
                    name='VPC <Dev> & "Test" / Env',
                    cidr="10.99.0.0/16",
                )
            ],
        )
        xml = generate_vpc_topology(region)
        # Should not raise and should contain escaped version
        assert "&lt;Dev&gt;" in xml or "VPC" in xml
        assert "</mxfile>" in xml

    def test_large_vpc_many_subnets(self):
        """20 subnets should not crash or produce malformed XML."""
        subnets = [
            Subnet(
                id=f"sn-{i}", cidr=f"10.0.{i}.0/24", az="us-east-1a", subnet_type=SubnetType.PRIVATE
            )
            for i in range(20)
        ]
        region = AWSRegionTopology(
            account_id="123456789012",
            region="us-east-1",
            vpcs=[VPC(id="vpc-big", name="big-vpc", cidr="10.0.0.0/8", subnets=subnets)],
        )
        xml = generate_vpc_topology(region)
        assert xml.count("mxCell") > 20
        assert "</mxfile>" in xml


class TestVnetTopology:
    def test_produces_valid_xml(self, minimal_vnet_sub):
        xml = generate_vnet_topology(minimal_vnet_sub)
        assert xml.startswith("<mxfile")
        assert "</mxfile>" in xml

    def test_contains_vnet_name(self, minimal_vnet_sub):
        xml = generate_vnet_topology(minimal_vnet_sub)
        assert "prod-vnet" in xml

    def test_nsg_indicator(self, minimal_vnet_sub):
        xml = generate_vnet_topology(minimal_vnet_sub)
        # db-subnet has NSG, app-subnet does not
        assert "🔒" in xml  # has NSG
        assert "⚠️" in xml  # missing NSG

    def test_empty_subscription_produces_note(self):
        sub = AzureSubscriptionTopology(subscription_id="sub-empty", tenant_id="t-001", vnets=[])
        xml = generate_vnet_topology(sub)
        assert "No VNets found" in xml

    def test_blocked_subscription_raises(self):
        sub = AzureSubscriptionTopology(
            subscription_id="sub-blocked",
            tenant_id="t-001",
            discovery_blocked=True,
            block_reason="Azure Policy denied",
        )
        with pytest.raises(ValueError, match="Discovery was blocked"):
            generate_vnet_topology(sub)


class TestTgwTopology:
    def test_produces_valid_xml(self, minimal_vpc_region):
        tgw = TransitGateway(
            id="tgw-abc",
            name="prod-tgw",
            owner_account_id="123456789012",
            attachments=[],
        )
        xml = generate_tgw_topology(tgw, minimal_vpc_region)
        assert "</mxfile>" in xml
        assert "prod-tgw" in xml


class TestVwanTopology:
    def test_produces_valid_xml(self):
        vwan = AzureVWan(
            id="/vwan/prod-vwan",
            name="prod-vwan",
            resource_group="rg-conn",
            sku="Standard",
            hubs=[
                AzureVHub(
                    id="/hub/us-hub",
                    name="us-hub",
                    location="eastus",
                    resource_group="rg-conn",
                    address_prefix="10.100.0.0/23",
                    routing_state="Provisioned",
                    connected_vnet_ids=["/vnets/spoke-1", "/vnets/spoke-2"],
                )
            ],
        )
        xml = generate_vwan_topology(vwan)
        assert "</mxfile>" in xml
        assert "us-hub" in xml

    def test_empty_vwan_produces_note(self):
        vwan = AzureVWan(
            id="/vwan/empty", name="empty-vwan", resource_group="rg-conn", sku="Standard", hubs=[]
        )
        xml = generate_vwan_topology(vwan)
        assert "no hubs" in xml.lower()


# ── Mermaid generator tests ──────────────────────────────────────────────


class TestMermaidGenerators:
    def test_aws_hierarchy_starts_with_flowchart(self):
        from cna.core.topology_schema import AWSAccount

        topology = AWSTopology(
            engagement_id="eng-001",
            management_account_id="000000000000",
            accounts=[
                AWSAccount(account_id="000000000000", is_management_account=True),
                AWSAccount(account_id="111111111111", account_name="prod", ou_name="Production"),
                AWSAccount(account_id="222222222222", account_name="dev", ou_name="Development"),
            ],
        )
        mmd = generate_aws_account_hierarchy(topology)
        assert mmd.startswith("flowchart TD")
        assert "000000000000" in mmd
        assert "Production" in mmd
        assert "Development" in mmd

    def test_azure_mg_hierarchy_starts_with_flowchart(self):
        topology = AzureTopology(
            engagement_id="eng-001",
            tenant_id="tenant-001",
            management_groups=[
                ManagementGroup(
                    id="mg-root",
                    name="root",
                    display_name="Root",
                    child_mg_ids=["mg-prod"],
                ),
                ManagementGroup(
                    id="mg-prod",
                    name="prod",
                    display_name="Production",
                    parent_id="mg-root",
                    subscription_ids=["sub-001", "sub-002"],
                ),
            ],
        )
        mmd = generate_azure_mg_hierarchy(topology)
        assert mmd.startswith("flowchart TD")
        assert "Production" in mmd
        assert "sub-001" in mmd

    def test_lz_diagram_flowchart_lr(self):
        mmd = generate_landing_zone_diagram(
            platform="aws",
            design_notes={
                "management_layer": "Management Account",
                "connectivity_layer": "Transit Gateway",
                "workload_layers": ["Prod Workloads", "Dev Workloads"],
                "security_controls": ["Network Firewall", "GuardDuty"],
            },
        )
        assert mmd.startswith("flowchart LR")
        assert "Transit_Gateway" in mmd or "Transit" in mmd
        assert "Network_Firewall" in mmd or "Network" in mmd

    def test_empty_topology_does_not_crash(self):
        topology = AWSTopology(engagement_id="eng-empty", accounts=[])
        mmd = generate_aws_account_hierarchy(topology)
        assert "EMPTY" in mmd or "No accounts" in mmd


# ── Service band, subnet typing, label breaks, multi-page merge ─────────────
#
# Added 2026-08-28 alongside the Diagram-page wiring. Before that the VNet
# diagram drew only VNets/subnets/peerings, painted every subnet with the
# private style, and emitted multi-line labels that html=1 collapsed onto one
# line.


def _sub_with_services() -> AzureSubscriptionTopology:
    from cna.core.topology_schema import AzureBastionHost, AzureFirewall

    return AzureSubscriptionTopology(
        subscription_id="sub-1",
        subscription_name="Prod",
        tenant_id="tenant-1",
        vnets=[
            VNet(
                id="/v/1",
                name="vnet-hub",
                address_space=["10.0.0.0/16"],
                location="southcentralus",
                resource_group="rg-net",
                subscription_id="sub-1",
                subnets=[
                    AzureSubnet(
                        id="/s/1",
                        name="snet-public",
                        address_prefix="10.0.1.0/24",
                        subnet_type=SubnetType.PUBLIC,
                    ),
                    AzureSubnet(
                        id="/s/2",
                        name="snet-isolated",
                        address_prefix="10.0.2.0/24",
                        subnet_type=SubnetType.ISOLATED,
                    ),
                ],
            )
        ],
        firewalls=[
            AzureFirewall(
                id="/fw/1",
                name="afw-hub",
                location="southcentralus",
                resource_group="rg-net",
                sku_tier="Standard",
            )
        ],
        bastion_hosts=[
            AzureBastionHost(
                id="/b/1",
                name="bas-hub",
                location="southcentralus",
                resource_group="rg-net",
            )
        ],
    )


def test_vnet_topology_renders_discovered_network_services():
    xml = generate_vnet_topology(_sub_with_services())
    assert "Network services" in xml
    assert "afw-hub" in xml
    assert "bas-hub" in xml
    # Real Azure icons, never the stencil form that renders as a blue box.
    assert "img/lib/azure2/networking/Firewalls.svg" in xml
    assert "mxgraph.azure2" not in xml


def test_vnet_topology_colours_subnets_by_type():
    from cna.diagram_engine.drawio_generator import (
        STYLE_SUBNET_ISOLATED,
        STYLE_SUBNET_PUBLIC,
    )

    xml = generate_vnet_topology(_sub_with_services())
    assert STYLE_SUBNET_PUBLIC in xml
    assert STYLE_SUBNET_ISOLATED in xml


def test_labels_use_escaped_line_breaks():
    """A raw "<br>" is malformed inside an XML attribute and drops the cell."""
    import xml.dom.minidom as minidom

    xml = generate_vnet_topology(_sub_with_services())
    assert "&lt;br&gt;" in xml
    assert "<br>" not in xml
    minidom.parseString(xml)  # must stay well-formed


def test_service_band_summarises_overflow_instead_of_drawing_every_icon():
    from cna.core.topology_schema import AzurePrivateEndpoint
    from cna.diagram_engine.drawio_generator import MAX_ICONS_PER_TYPE

    sub = _sub_with_services()
    count = MAX_ICONS_PER_TYPE + 3
    sub.private_endpoints = [
        AzurePrivateEndpoint(
            id=f"/pe/{i}",
            name=f"pe-{i}",
            location="southcentralus",
            resource_group="rg",
            subnet_id="/s/1",
        )
        for i in range(count)
    ]
    xml = generate_vnet_topology(sub)
    assert f"pe-{MAX_ICONS_PER_TYPE - 1}" in xml
    assert f"pe-{MAX_ICONS_PER_TYPE}" not in xml
    assert "+3 more" in xml


def test_subscription_with_no_services_lays_out_unchanged():
    sub = AzureSubscriptionTopology(
        subscription_id="sub-2", tenant_id="t", vnets=_sub_with_services().vnets
    )
    xml = generate_vnet_topology(sub)
    assert "Network services" not in xml
    assert "vnet-hub" in xml


def test_merge_diagrams_makes_one_page_per_input():
    import xml.dom.minidom as minidom

    from cna.diagram_engine.drawio_generator import merge_diagrams

    a = generate_vnet_topology(_sub_with_services())
    merged = merge_diagrams([("Azure sub-1", a), ("Azure sub-2", a)])
    minidom.parseString(merged)
    assert merged.count("<diagram") == 2
    assert 'name="Azure sub-1"' in merged
    assert 'name="Azure sub-2"' in merged


def test_merge_diagrams_skips_unparseable_pages_and_never_returns_empty():
    import xml.dom.minidom as minidom

    from cna.diagram_engine.drawio_generator import merge_diagrams

    good = generate_vnet_topology(_sub_with_services())
    merged = merge_diagrams([("bad", "<not xml"), ("good", good)])
    assert merged.count("<diagram") == 1

    empty = merge_diagrams([])
    minidom.parseString(empty)
    assert "<diagram" in empty


# ── AWS network services band (TODO.md T-418) ───────────────────────────────


def _region_with_services() -> AWSRegionTopology:
    return AWSRegionTopology(
        account_id="123456789012",
        region="us-east-1",
        vpcs=[
            VPC(
                id="vpc-abc123",
                name="prod-vpc",
                cidr="10.0.0.0/16",
                subnets=[
                    Subnet(
                        id="subnet-a",
                        name="public-a",
                        cidr="10.0.1.0/24",
                        az="us-east-1a",
                        subnet_type=SubnetType.PUBLIC,
                    )
                ],
            )
        ],
        transit_gateways=[
            TransitGateway(id="tgw-001", name="hub-tgw", owner_account_id="123456789012")
        ],
        direct_connect_connections=[
            DirectConnectConnection(
                id="dxcon-001",
                name="dc-to-hq",
                location="EqDC2",
                bandwidth="1Gbps",
                state="available",
                owner_account_id="123456789012",
            )
        ],
        vpn_gateways=[VpnGateway(id="vgw-001", name="branch-vpn", state="available")],
        aws_network_firewalls=[
            AWSNetworkFirewall(
                firewall_arn="arn:aws:network-firewall:us-east-1:123456789012:firewall/egress",
                firewall_name="egress-fw",
                vpc_id="vpc-abc123",
            )
        ],
        waf_web_acls=[
            AWSWAFWebACL(
                web_acl_id="acl-001",
                web_acl_arn="arn:aws:wafv2:us-east-1:123456789012:regional/webacl/edge/acl-001",
                name="edge-waf",
            )
        ],
    )


class TestAwsServicesBand:
    def test_band_names_every_discovered_service(self):
        xml = generate_vpc_topology(_region_with_services())
        assert "Network services — 123456789012 / us-east-1" in xml
        for name in ("hub-tgw", "dc-to-hq", "branch-vpn", "egress-fw", "edge-waf"):
            assert name in xml, name
        for label in (
            "Transit Gateway",
            "Direct Connect",
            "VPN Gateway",
            "Network Firewall",
            "WAF Web ACL",
        ):
            assert label in xml, label

    def test_band_uses_aws_icons(self):
        xml = generate_vpc_topology(_region_with_services())
        for icon in ("transit_gateway", "direct_connect", "vpn_gateway", "network_firewall", "waf"):
            assert f"mxgraph.aws4.{icon}" in xml, icon

    def test_region_without_services_has_no_band(self, minimal_vpc_region):
        xml = generate_vpc_topology(minimal_vpc_region)
        assert "Network services" not in xml

    def test_empty_region_still_shows_its_services(self):
        region = AWSRegionTopology(
            account_id="123456789012",
            region="us-east-1",
            transit_gateways=[
                TransitGateway(id="tgw-002", name="lonely-tgw", owner_account_id="123456789012")
            ],
        )
        xml = generate_vpc_topology(region)
        assert "lonely-tgw" in xml
        assert "No VPCs found" in xml

    def test_band_is_valid_xml(self):
        import xml.dom.minidom as minidom

        minidom.parseString(generate_vpc_topology(_region_with_services()))


class TestEngagementBundleLayers:
    def test_bundle_emits_context_and_one_container_per_scope_only(self, minimal_vpc_region):
        from cna.ai_engine.diagram_authoring import author_engagement_bundle
        from cna.diagram_engine.c4_layering import C4Layer

        bundle = author_engagement_bundle(
            "Acme", aws_regions=[minimal_vpc_region], azure_subs=[_sub_with_services()]
        )
        layers = [d.layer for d in bundle]
        assert layers.count(C4Layer.CONTEXT) == 1
        assert layers.count(C4Layer.CONTAINER) == 2
        assert C4Layer.COMPONENT not in layers
        assert len({d.name for d in bundle}) == len(bundle)
