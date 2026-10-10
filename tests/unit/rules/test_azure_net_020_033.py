"""One fixture per rule for ``AZ-NET-020..033`` — the checks ported from the API's Engine B.

Each rule gets the topology that fires it and the near-miss that must not, so a port that
drifts in either direction is caught. Fixtures use the sample subscription id and
``hcw-sample-*`` names only.
"""

from __future__ import annotations

import pytest

from cna.ai_engine.azure_rules import RULES, evaluate
from cna.core.findings_schema import FindingSeverity
from cna.core.topology.azure import (
    ApplicationGateway,
    AzureBastionHost,
    AzureFirewall,
    AzureGatewayConnection,
    AzureLoadBalancer,
    AzureNSG,
    AzurePrivateEndpoint,
    AzurePrivateEndpointConnection,
    AzurePublicIP,
    AzureRouteEntry,
    AzureRouteTable,
    AzureSubnet,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVHub,
    AzureVirtualNetworkGateway,
    AzureVWan,
    NSGSecurityRule,
    VNet,
)

SUB = "00000000-0000-0000-0000-000000000001"
RG = "hcw-sample-rg"
LOC = "eastus"
VNET_ID = f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/virtualNetworks/hcw-sample-vnet"


def _vnet(**overrides) -> VNet:
    base = {
        "id": VNET_ID,
        "name": "hcw-sample-vnet",
        "location": LOC,
        "resource_group": RG,
        "subscription_id": SUB,
        "address_space": ["10.0.0.0/16"],
        "ddos_protection_enabled": True,
        "flow_logs_enabled": True,
        "subnets": [
            AzureSubnet(
                id=f"{VNET_ID}/subnets/app", name="app", address_prefix="10.0.1.0/24", nsg_id="/nsg"
            )
        ],
    }
    base.update(overrides)
    return VNet(**base)


def _topology(sub: AzureSubscriptionTopology) -> AzureTopology:
    return AzureTopology(engagement_id="hcw-sample-engagement", tenant_id="t", subscriptions=[sub])


def _sub(**overrides) -> AzureSubscriptionTopology:
    base = {"subscription_id": SUB, "subscription_name": "hcw-sample-sub", "tenant_id": "t"}
    base.update(overrides)
    return AzureSubscriptionTopology(**base)


def _findings(sub: AzureSubscriptionTopology, rule_id: str):
    return [f for f in evaluate(_topology(sub)).findings if f.rule_id == rule_id]


def _nsg_rule(**overrides) -> NSGSecurityRule:
    base = {
        "name": "allow-in",
        "priority": 100,
        "direction": "Inbound",
        "access": "Allow",
        "protocol": "Tcp",
        "source_address_prefix": "Internet",
        "destination_address_prefix": "*",
        "destination_port_range": "443",
    }
    base.update(overrides)
    return NSGSecurityRule(**base)


def _nsg(*rules: NSGSecurityRule) -> AzureNSG:
    return AzureNSG(
        id=f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/networkSecurityGroups/hcw-sample-nsg",
        name="hcw-sample-nsg",
        location=LOC,
        resource_group=RG,
        security_rules=list(rules),
    )


def _gateway(**overrides) -> AzureVirtualNetworkGateway:
    base = {
        "id": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/virtualNetworkGateways/hcw-sample-gw",
        "name": "hcw-sample-gw",
        "location": LOC,
        "resource_group": RG,
        "gateway_type": "Vpn",
        "sku_name": "VpnGw2",
        "sku_tier": "VpnGw2",
        "zones": ["1", "2", "3"],
        "active_active": True,
    }
    base.update(overrides)
    return AzureVirtualNetworkGateway(**base)


def _route_table(*routes: AzureRouteEntry, **overrides) -> AzureRouteTable:
    base = {
        "id": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/routeTables/hcw-sample-rt",
        "name": "hcw-sample-rt",
        "location": LOC,
        "resource_group": RG,
        "routes": list(routes),
        "associated_subnet_ids": [f"{VNET_ID}/subnets/app"],
    }
    base.update(overrides)
    return AzureRouteTable(**base)


class TestAzNet020RemoteAccessFromInternet:
    RULE = "AZ-NET-020"

    @pytest.mark.parametrize("port", ["22", "3389", "20-30", "3000-4000", "*"])
    def test_internet_source_on_remote_access_port_is_critical(self, port):
        sub = _sub(nsgs=[_nsg(_nsg_rule(destination_port_range=port))])
        found = _findings(sub, self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.CRITICAL
        assert found[0].resource_id.endswith("/securityRules/allow-in")

    def test_port_ranges_list_is_honoured(self):
        rule = _nsg_rule(destination_port_range=None, destination_port_ranges=["80", "3389"])
        sub = _sub(nsgs=[_nsg(rule)])
        assert len(_findings(sub, self.RULE)) == 1

    @pytest.mark.parametrize("source", ["*", "Internet", "0.0.0.0/0", "Any"])
    def test_every_internet_spelling_counts(self, source):
        sub = _sub(
            nsgs=[_nsg(_nsg_rule(source_address_prefix=source, destination_port_range="22"))]
        )
        assert len(_findings(sub, self.RULE)) == 1

    def test_corporate_source_does_not_fire(self):
        rule = _nsg_rule(source_address_prefix="203.0.113.0/24", destination_port_range="22")
        assert _findings(_sub(nsgs=[_nsg(rule)]), self.RULE) == []

    def test_deny_outbound_and_other_ports_do_not_fire(self):
        rules = [
            _nsg_rule(name="deny", access="Deny", destination_port_range="22"),
            _nsg_rule(name="out", direction="Outbound", destination_port_range="22"),
            _nsg_rule(name="https", destination_port_range="443"),
            _nsg_rule(name="range-miss", destination_port_range="100-200"),
        ]
        assert _findings(_sub(nsgs=[_nsg(*rules)]), self.RULE) == []


class TestAzNet021WildcardAllowAll:
    RULE = "AZ-NET-021"

    def test_any_source_any_port_any_protocol_is_high(self):
        rule = _nsg_rule(source_address_prefix="*", destination_port_range="*", protocol="*")
        found = _findings(_sub(nsgs=[_nsg(rule)]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.HIGH

    def test_outbound_wildcard_also_fires(self):
        rule = _nsg_rule(
            direction="Outbound",
            source_address_prefix="Any",
            destination_port_range="Any",
            protocol="Any",
        )
        assert len(_findings(_sub(nsgs=[_nsg(rule)]), self.RULE)) == 1

    def test_specific_port_or_protocol_does_not_fire(self):
        rules = [
            _nsg_rule(
                name="tcp-only",
                source_address_prefix="*",
                destination_port_range="*",
                protocol="Tcp",
            ),
            _nsg_rule(
                name="one-port",
                source_address_prefix="*",
                destination_port_range="443",
                protocol="*",
            ),
        ]
        assert _findings(_sub(nsgs=[_nsg(*rules)]), self.RULE) == []


class TestAzNet022DefaultRouteToInternet:
    RULE = "AZ-NET-022"

    def test_default_route_with_internet_next_hop_is_medium(self):
        rt = _route_table(
            AzureRouteEntry(name="egress", address_prefix="0.0.0.0/0", next_hop_type="Internet")
        )
        found = _findings(_sub(route_tables=[rt]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.MEDIUM
        assert found[0].affected_resources == [f"{VNET_ID}/subnets/app"]

    def test_route_table_nested_under_a_vnet_is_read_too(self):
        rt = _route_table(
            AzureRouteEntry(name="egress", address_prefix="0.0.0.0/0", next_hop_type="Internet")
        )
        assert len(_findings(_sub(vnets=[_vnet(route_tables=[rt])]), self.RULE)) == 1

    def test_default_route_to_nva_or_specific_prefix_does_not_fire(self):
        rt = _route_table(
            AzureRouteEntry(
                name="fw",
                address_prefix="0.0.0.0/0",
                next_hop_type="VirtualAppliance",
                next_hop_ip="10.0.3.4",
            ),
            AzureRouteEntry(name="dmz", address_prefix="192.0.2.0/24", next_hop_type="Internet"),
        )
        assert _findings(_sub(route_tables=[rt]), self.RULE) == []


class TestAzNet023BgpPropagationDisabled:
    RULE = "AZ-NET-023"

    def test_disabled_propagation_is_informational(self):
        found = _findings(
            _sub(route_tables=[_route_table(disable_bgp_route_propagation=True)]), self.RULE
        )
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.INFORMATIONAL

    def test_enabled_propagation_does_not_fire(self):
        assert _findings(_sub(route_tables=[_route_table()]), self.RULE) == []


class TestAzNet024CustomDns:
    RULE = "AZ-NET-024"

    def test_custom_servers_are_informational_and_listed(self):
        found = _findings(_sub(vnets=[_vnet(dns_servers=["10.0.0.4", "10.0.0.5"])]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.INFORMATIONAL
        assert "10.0.0.4, 10.0.0.5" in found[0].observed_state.fact

    def test_azure_provided_dns_does_not_fire(self):
        assert _findings(_sub(vnets=[_vnet(dns_servers=["168.63.129.16"])]), self.RULE) == []
        assert _findings(_sub(vnets=[_vnet(dns_servers=[])]), self.RULE) == []


def _appgw(**overrides) -> ApplicationGateway:
    base = {
        "id": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/applicationGateways/hcw-sample-agw",
        "name": "hcw-sample-agw",
        "location": LOC,
        "resource_group": RG,
        "sku_name": "WAF_v2",
        "subnet_id": f"{VNET_ID}/subnets/agw",
        "waf_enabled": True,
        "waf_mode": "Prevention",
        "zones": ["1", "2", "3"],
    }
    base.update(overrides)
    return ApplicationGateway(**base)


class TestAzNet025AppGatewayWafDetection:
    RULE = "AZ-NET-025"

    def test_detection_mode_is_medium(self):
        found = _findings(_sub(application_gateways=[_appgw(waf_mode="Detection")]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.MEDIUM

    def test_prevention_or_waf_disabled_does_not_fire(self):
        assert _findings(_sub(application_gateways=[_appgw()]), self.RULE) == []
        # WAF disabled is AZ-NET-007's finding, not this rule's.
        assert (
            _findings(
                _sub(application_gateways=[_appgw(waf_enabled=False, waf_mode=None)]), self.RULE
            )
            == []
        )


def _lb(**overrides) -> AzureLoadBalancer:
    base = {
        "id": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/loadBalancers/hcw-sample-lb",
        "name": "hcw-sample-lb",
        "location": LOC,
        "resource_group": RG,
        "sku_name": "Standard",
        "zones": ["1", "2", "3"],
    }
    base.update(overrides)
    return AzureLoadBalancer(**base)


class TestAzNet026LoadBalancerBasicSku:
    RULE = "AZ-NET-026"

    def test_basic_sku_is_medium(self):
        found = _findings(_sub(load_balancers=[_lb(sku_name="Basic")]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.MEDIUM

    def test_standard_sku_does_not_fire(self):
        assert _findings(_sub(load_balancers=[_lb()]), self.RULE) == []


def _pip(name: str, **overrides) -> AzurePublicIP:
    base = {
        "id": f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/publicIPAddresses/{name}",
        "name": name,
        "location": LOC,
        "resource_group": RG,
        "sku_name": "Standard",
    }
    base.update(overrides)
    return AzurePublicIP(**base)


class TestAzNet027PublicIpBasicSku:
    RULE = "AZ-NET-027"

    def test_one_finding_per_basic_ip_not_per_subscription(self):
        pips = [
            _pip("hcw-sample-pip-1", sku_name="Basic"),
            _pip("hcw-sample-pip-2", sku_name="Basic"),
            _pip("hcw-sample-pip-3"),
        ]
        found = _findings(_sub(public_ips=pips), self.RULE)
        assert sorted(f.resource_id.rsplit("/", 1)[-1] for f in found) == [
            "hcw-sample-pip-1",
            "hcw-sample-pip-2",
        ]
        assert {f.severity for f in found} == {FindingSeverity.MEDIUM}

    def test_standard_only_does_not_fire(self):
        assert _findings(_sub(public_ips=[_pip("hcw-sample-pip-1")]), self.RULE) == []


class TestAzNet028VpnGatewayBasicSku:
    RULE = "AZ-NET-028"

    def test_basic_vpn_gateway_is_high(self):
        found = _findings(
            _sub(virtual_network_gateways=[_gateway(sku_name="Basic", sku_tier="Basic")]), self.RULE
        )
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.HIGH

    def test_expressroute_gateway_and_standard_vpn_do_not_fire(self):
        gws = [
            _gateway(gateway_type="ExpressRoute", sku_name="Basic", sku_tier="Basic"),
            _gateway(),
        ]
        assert _findings(_sub(virtual_network_gateways=gws), self.RULE) == []


class TestAzNet029VpnGatewayGeneration1:
    RULE = "AZ-NET-029"

    @pytest.mark.parametrize("generation", ["Generation1", "generation 1"])
    def test_generation1_is_low(self, generation):
        found = _findings(
            _sub(virtual_network_gateways=[_gateway(generation=generation)]), self.RULE
        )
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.LOW

    def test_generation2_or_unknown_does_not_fire(self):
        gws = [_gateway(generation="Generation2"), _gateway(id="/gw-2", generation=None)]
        assert _findings(_sub(virtual_network_gateways=gws), self.RULE) == []


def _connection(status: str, name: str = "hcw-sample-conn") -> AzureGatewayConnection:
    return AzureGatewayConnection(
        id=f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/connections/{name}",
        name=name,
        connection_type="IPsec",
        connection_status=status,
    )


class TestAzNet030GatewayConnectionNotConnected:
    RULE = "AZ-NET-030"

    @pytest.mark.parametrize("status", ["NotConnected", "Connecting"])
    def test_non_connected_status_is_high(self, status):
        found = _findings(
            _sub(virtual_network_gateways=[_gateway(connections=[_connection(status)])]), self.RULE
        )
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.HIGH
        assert found[0].resource_id.endswith("/connections/hcw-sample-conn")

    @pytest.mark.parametrize("status", ["Connected", "Unknown"])
    def test_connected_or_unknown_does_not_fire(self, status):
        assert (
            _findings(
                _sub(virtual_network_gateways=[_gateway(connections=[_connection(status)])]),
                self.RULE,
            )
            == []
        )

    def test_expressroute_connections_are_checked_too(self):
        gw = _gateway(gateway_type="ExpressRoute", connections=[_connection("NotConnected")])
        assert len(_findings(_sub(virtual_network_gateways=[gw]), self.RULE)) == 1


def _private_endpoint(state: str) -> AzurePrivateEndpoint:
    return AzurePrivateEndpoint(
        id=f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/privateEndpoints/hcw-sample-pe",
        name="hcw-sample-pe",
        location=LOC,
        resource_group=RG,
        subnet_id=f"{VNET_ID}/subnets/app",
        service_connections=[
            AzurePrivateEndpointConnection(
                connection_name="hcw-sample-link",
                private_link_service_id=f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Storage/storageAccounts/hcwsample",
                connection_state=state,
            )
        ],
    )


class TestAzNet031PrivateEndpointPending:
    RULE = "AZ-NET-031"

    def test_pending_connection_is_medium(self):
        found = _findings(_sub(private_endpoints=[_private_endpoint("Pending")]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.MEDIUM
        assert "hcwsample" in found[0].observed_state.fact

    def test_approved_connection_does_not_fire(self):
        assert _findings(_sub(private_endpoints=[_private_endpoint("Approved")]), self.RULE) == []


def _firewall() -> AzureFirewall:
    return AzureFirewall(
        id=f"/subscriptions/{SUB}/resourceGroups/{RG}/providers/Microsoft.Network/azureFirewalls/hcw-sample-fw",
        name="hcw-sample-fw",
        location=LOC,
        resource_group=RG,
        sku_tier="Standard",
        threat_intel_mode="Deny",
        zones=["1", "2", "3"],
    )


class TestAzNet032NoFirewall:
    RULE = "AZ-NET-032"

    def test_vnets_without_firewall_is_medium(self):
        found = _findings(_sub(vnets=[_vnet()]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.MEDIUM
        assert found[0].affected_resources == [VNET_ID]

    def test_firewall_present_does_not_fire(self):
        assert _findings(_sub(vnets=[_vnet()], firewalls=[_firewall()]), self.RULE) == []

    def test_no_vnets_does_not_fire(self):
        assert _findings(_sub(), self.RULE) == []

    def test_secured_virtual_wan_hub_suppresses(self):
        hub = AzureVHub(
            id="/hub",
            name="hcw-sample-hub",
            location=LOC,
            resource_group=RG,
            address_prefix="10.9.0.0/24",
            routing_state="Provisioned",
            azure_firewall_id="/fw-in-hub",
        )
        vwan = AzureVWan(
            id="/vwan", name="hcw-sample-vwan", resource_group=RG, sku="Standard", hubs=[hub]
        )
        assert _findings(_sub(vnets=[_vnet()], virtual_wans=[vwan]), self.RULE) == []

    def test_nva_default_route_suppresses(self):
        rt = _route_table(
            AzureRouteEntry(
                name="fw",
                address_prefix="0.0.0.0/0",
                next_hop_type="VirtualAppliance",
                next_hop_ip="10.0.3.4",
            )
        )
        assert _findings(_sub(vnets=[_vnet()], route_tables=[rt]), self.RULE) == []


class TestAzNet033NoBastion:
    RULE = "AZ-NET-033"

    def test_vnets_without_bastion_is_low(self):
        found = _findings(_sub(vnets=[_vnet()]), self.RULE)
        assert len(found) == 1
        assert found[0].severity == FindingSeverity.LOW

    def test_bastion_present_or_no_vnets_does_not_fire(self):
        bastion = AzureBastionHost(
            id="/bastion", name="hcw-sample-bastion", location=LOC, resource_group=RG
        )
        assert _findings(_sub(vnets=[_vnet()], bastion_hosts=[bastion]), self.RULE) == []
        assert _findings(_sub(), self.RULE) == []


class TestEngineBSeveritiesMatchThePlan:
    """Plan table 7.B: the Core and the downstream lab edition must agree on these exactly."""

    EXPECTED = {
        "AZ-NET-020": FindingSeverity.CRITICAL,
        "AZ-NET-021": FindingSeverity.HIGH,
        "AZ-NET-022": FindingSeverity.MEDIUM,
        "AZ-NET-023": FindingSeverity.INFORMATIONAL,
        "AZ-NET-024": FindingSeverity.INFORMATIONAL,
        "AZ-NET-025": FindingSeverity.MEDIUM,
        "AZ-NET-026": FindingSeverity.MEDIUM,
        "AZ-NET-027": FindingSeverity.MEDIUM,
        "AZ-NET-028": FindingSeverity.HIGH,
        "AZ-NET-029": FindingSeverity.LOW,
        "AZ-NET-030": FindingSeverity.HIGH,
        "AZ-NET-031": FindingSeverity.MEDIUM,
        "AZ-NET-032": FindingSeverity.MEDIUM,
        "AZ-NET-033": FindingSeverity.LOW,
    }

    def test_every_ported_rule_is_registered_with_the_planned_severity(self):
        assert {rid: RULES[rid][0].severity for rid in self.EXPECTED} == self.EXPECTED

    def test_every_ported_rule_is_evaluable_from_an_export(self):
        assert all(RULES[rid][0].applies_to == "export" for rid in self.EXPECTED)
