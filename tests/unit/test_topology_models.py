"""Unit tests for cna.core.topology_models — Pydantic contracts."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cna.core.topology_models import (
    AWSVPC,
    AWSAccount,
    AWSInternetGateway,
    AWSNatGateway,
    AWSOrganizationTopology,
    AWSRegionTopology,
    AWSRouteTable,
    AWSSubnet,
    AWSTransitGateway,
    AWSTransitGatewayAttachment,
    AWSVPCPeeringConnection,
    AzureSubnet,
    AzureTenantTopology,
    AzureVHub,
    AzureVNet,
    AzureVNetPeering,
    AzureVWan,
    FirewallMode,
    PeeringState,
    RegionGroup,
    SubnetType,
)

# ── Enum round-trips ───────────────────────────────────────────────────────────


class TestEnums:
    def test_subnet_type_values(self):
        assert SubnetType.PUBLIC == "public"
        assert SubnetType.PRIVATE == "private"
        assert SubnetType.ISOLATED == "isolated"
        assert SubnetType.TRANSIT == "transit"

    def test_peering_state_values(self):
        assert PeeringState.ACTIVE == "active"
        assert PeeringState.PENDING == "pending"
        assert PeeringState.REJECTED == "rejected"
        assert PeeringState.EXPIRED == "expired"

    def test_firewall_mode_values(self):
        assert FirewallMode.INLINE == "inline"
        assert FirewallMode.PARALLEL == "parallel"
        assert FirewallMode.NONE == "none"

    def test_region_group_values(self):
        assert RegionGroup.US == "us"
        assert RegionGroup.EMEA == "emea"
        assert RegionGroup.JAPAN == "japan"
        assert RegionGroup.OTHER == "other"

    def test_enums_are_strings(self):
        """StrEnum values must compare equal to plain strings."""
        assert SubnetType.PUBLIC == "public"
        assert f"{SubnetType.PRIVATE}" == "private"


# ── AWS primitive models ───────────────────────────────────────────────────────


class TestAWSSubnet:
    def test_minimal_required_fields(self):
        s = AWSSubnet(id="subnet-abc", cidr="10.0.1.0/24", az="us-east-1a", type=SubnetType.PUBLIC)
        assert s.id == "subnet-abc"
        assert s.name is None
        assert s.route_table_id is None

    def test_optional_fields(self):
        s = AWSSubnet(
            id="subnet-abc",
            cidr="10.0.1.0/24",
            az="us-east-1a",
            type=SubnetType.PRIVATE,
            name="private-a",
            route_table_id="rtb-001",
        )
        assert s.name == "private-a"
        assert s.route_table_id == "rtb-001"

    def test_type_coercion_from_string(self):
        """Pydantic should coerce string 'public' to SubnetType.PUBLIC."""
        s = AWSSubnet(id="s", cidr="10.0.0.0/24", az="us-east-1b", type="public")
        assert s.type == SubnetType.PUBLIC


class TestAWSRouteTable:
    def test_defaults(self):
        rt = AWSRouteTable(id="rtb-001")
        assert rt.routes == []
        assert rt.associated_subnets == []
        assert rt.is_main is False

    def test_with_data(self):
        rt = AWSRouteTable(
            id="rtb-001",
            routes=[{"cidr": "0.0.0.0/0", "target": "igw-001", "type": "internet"}],
            associated_subnets=["subnet-001"],
            is_main=True,
        )
        assert len(rt.routes) == 1
        assert rt.is_main is True


class TestAWSInternetGateway:
    def test_default_state(self):
        igw = AWSInternetGateway(id="igw-001")
        assert igw.state == "attached"

    def test_custom_state(self):
        igw = AWSInternetGateway(id="igw-002", state="detached")
        assert igw.state == "detached"


class TestAWSNatGateway:
    def test_required_fields(self):
        nat = AWSNatGateway(id="nat-001", subnet_id="subnet-001", state="available")
        assert nat.public_ip is None

    def test_with_public_ip(self):
        nat = AWSNatGateway(
            id="nat-001", subnet_id="subnet-001", state="available", public_ip="52.0.0.1"
        )
        assert nat.public_ip == "52.0.0.1"


class TestAWSVPCPeeringConnection:
    def test_full_model(self):
        pc = AWSVPCPeeringConnection(
            id="pcx-001",
            requester_vpc_id="vpc-aaa",
            accepter_vpc_id="vpc-bbb",
            requester_account_id="111111111111",
            accepter_account_id="222222222222",
            state=PeeringState.ACTIVE,
        )
        assert pc.state == "active"


class TestAWSTransitGateway:
    def test_defaults(self):
        tgw = AWSTransitGateway(id="tgw-001", account_id="123456789012", region="us-east-1")
        assert tgw.attachments == []
        assert tgw.route_tables == []
        assert tgw.name is None

    def test_with_attachment(self):
        att = AWSTransitGatewayAttachment(
            id="tgw-attach-001",
            tgw_id="tgw-001",
            resource_type="vpc",
            resource_id="vpc-001",
            account_id="123",
            state="available",
        )
        tgw = AWSTransitGateway(
            id="tgw-001",
            account_id="123",
            region="us-east-1",
            attachments=[att],
        )
        assert len(tgw.attachments) == 1


# ── AWS composite models ───────────────────────────────────────────────────────


class TestAWSVPC:
    def test_defaults(self):
        vpc = AWSVPC(
            id="vpc-001", cidr="10.0.0.0/16", account_id="123456789012", region="us-east-1"
        )
        assert vpc.is_default is False
        assert vpc.subnets == []
        assert vpc.firewall_mode == FirewallMode.NONE
        assert vpc.internet_gateway is None

    def test_with_firewall(self):
        vpc = AWSVPC(
            id="vpc-001",
            cidr="10.0.0.0/16",
            account_id="123456789012",
            region="us-east-1",
            firewall_mode=FirewallMode.INLINE,
            firewall_subnet_ids=["subnet-fw-001"],
        )
        assert vpc.firewall_mode == "inline"
        assert len(vpc.firewall_subnet_ids) == 1


class TestAWSOrganizationTopology:
    def test_minimal(self):
        topo = AWSOrganizationTopology(
            engagement_id="acme-20260409-a1b2",
            management_account_id="123456789012",
        )
        assert topo.accounts == []
        assert topo.region_topologies == []

    def test_with_account(self):
        account = AWSAccount(account_id="111222333444", name="sandbox")
        topo = AWSOrganizationTopology(
            engagement_id="eng-001",
            management_account_id="123456789012",
            accounts=[account],
        )
        assert topo.accounts[0].name == "sandbox"

    def test_account_defaults(self):
        account = AWSAccount(account_id="999888777666")
        assert account.name is None
        assert account.is_management is False
        assert account.organizational_unit is None


class TestAWSRegionTopology:
    def test_defaults(self):
        rt = AWSRegionTopology(
            account_id="123456789012",
            region="us-east-1",
            region_group=RegionGroup.US,
        )
        assert rt.discovery_complete is False
        assert rt.vpcs == []
        assert rt.blocked_services == []


# ── Azure models ───────────────────────────────────────────────────────────────


class TestAzureSubnet:
    def test_required_fields(self):
        subnet = AzureSubnet(
            id="/subscriptions/sub-001/subnets/subnet-web",
            name="subnet-web",
            address_prefix="10.1.0.0/24",
        )
        assert subnet.nsg_id is None
        assert subnet.service_endpoints == []
        assert subnet.delegations == []


class TestAzureVNetPeering:
    def test_defaults(self):
        peering = AzureVNetPeering(
            id="/subscriptions/sub/peerings/peer-001",
            name="peer-001",
            remote_vnet_id="/subscriptions/sub2/vnets/vnet-remote",
            remote_subscription_id="sub2",
            state="Connected",
        )
        assert peering.allow_vnet_access is True
        assert peering.allow_forwarded_traffic is False
        assert peering.use_remote_gateways is False


class TestAzureVNet:
    def test_defaults(self):
        vnet = AzureVNet(
            id="/subscriptions/sub-001/vnets/vnet-001",
            name="vnet-prod",
            subscription_id="sub-001",
            resource_group="rg-network",
            region="eastus",
            region_group=RegionGroup.US,
        )
        assert vnet.connected_to_hub is False
        assert vnet.firewall_present is False
        assert vnet.ddos_protection is False
        assert vnet.firewall_mode == FirewallMode.NONE

    def test_with_firewall(self):
        vnet = AzureVNet(
            id="/subscriptions/sub/vnets/vnet-fw",
            name="vnet-hub",
            subscription_id="sub",
            resource_group="rg-hub",
            region="eastus",
            region_group=RegionGroup.US,
            firewall_present=True,
            firewall_id="/subscriptions/sub/firewalls/fw-001",
            firewall_mode=FirewallMode.INLINE,
            ddos_protection=True,
        )
        assert vnet.firewall_present is True
        assert vnet.ddos_protection is True


class TestAzureTenantTopology:
    def test_minimal(self):
        topo = AzureTenantTopology(
            engagement_id="acme-20260409",
            tenant_id="tenant-abc-123",
        )
        assert topo.subscriptions == []
        assert topo.virtual_wans == []
        assert topo.management_group_tree == {}

    def test_tenant_id_required(self):
        with pytest.raises(ValidationError):
            AzureTenantTopology(engagement_id="eng-001")  # missing tenant_id


class TestAzureVHub:
    def test_model(self):
        hub = AzureVHub(
            id="/subscriptions/sub/hubs/hub-001",
            name="hub-eastus",
            address_prefix="10.100.0.0/23",
            subscription_id="sub",
            region="eastus",
            region_group=RegionGroup.US,
        )
        assert hub.connected_vnets == []
        assert hub.azure_firewall_id is None


class TestAzureVWan:
    def test_model_with_hub(self):
        hub = AzureVHub(
            id="hub-id",
            name="hub1",
            address_prefix="10.0.0.0/23",
            subscription_id="sub",
            region="eastus",
            region_group=RegionGroup.US,
        )
        vwan = AzureVWan(
            id="vwan-001",
            name="vwan-global",
            subscription_id="sub",
            hubs=[hub],
        )
        assert len(vwan.hubs) == 1
