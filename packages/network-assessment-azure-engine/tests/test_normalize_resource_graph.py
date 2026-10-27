"""The Resource Graph normalizer: rows -> AzureTopology, references resolved, warnings honest."""

from __future__ import annotations

import pytest
from engine_fixtures import (
    AGW,
    BASE,
    FLOWLOG,
    FW,
    GW,
    NSG,
    PE,
    PIP,
    RT,
    SUB,
    VHUB,
    VNET,
    VWAN,
    export_rows,
)

from network_assessment_azure_engine.normalize import (
    PAGED_WARNING,
    normalize_resource_graph,
    normalize_rows,
    row_from_dict,
    rows_from_document,
)


@pytest.fixture(scope="module")
def topology():
    return normalize_resource_graph(export_rows())


@pytest.fixture(scope="module")
def sub(topology):
    assert len(topology.subscriptions) == 1
    return topology.subscriptions[0]


class TestRows:
    def test_type_is_lower_cased_and_ids_derived(self):
        row = row_from_dict(
            {"id": f"{BASE}/virtualNetworks/x", "type": "Microsoft.Network/VirtualNetworks"}, 1
        )
        assert row is not None
        assert row.type == "microsoft.network/virtualnetworks"
        assert (
            row.subscription_id == SUB and row.resource_group == "hcw-sample-rg" and row.name == "x"
        )

    def test_row_without_type_or_identity_is_dropped(self):
        assert row_from_dict({"name": "x"}, 1) is None
        assert row_from_dict({"type": "microsoft.network/virtualnetworks"}, 1) is None

    def test_envelope_is_accepted_and_paging_recorded(self):
        rows, warnings = rows_from_document(
            {
                "count": 1,
                "data": [{"id": "/x", "type": "t"}],
                "skip_token": "abc",
                "total_records": 5,
            }
        )
        assert len(rows) == 1
        assert PAGED_WARNING in warnings
        assert any("5 records" in w for w in warnings)
        assert rows_from_document([{"id": "/x", "type": "t"}]) == ([{"id": "/x", "type": "t"}], [])

    def test_non_envelope_object_is_rejected(self):
        with pytest.raises(ValueError):
            rows_from_document({"rows": []})
        with pytest.raises(ValueError):
            rows_from_document("text")


class TestTopology:
    def test_source_and_counts(self, topology):
        assert topology.source == "export"
        assert topology.engagement_id is None and topology.tenant_id is None
        assert topology.resource_counts["microsoft.network/virtualnetworks"] == 1
        assert topology.resource_counts["microsoft.compute/virtualmachines"] == 1
        assert "microsoft.network/localnetworkgateways" in topology.unmapped_types
        assert any("outside microsoft.network/" in w for w in topology.warnings)
        assert any("localnetworkgateways" in w for w in topology.warnings)
        assert topology.has_properties is True

    def test_vnet_subnets_peerings_and_references(self, sub):
        vnet = sub.vnets[0]
        assert (
            vnet.id == VNET
            and vnet.dns_servers == ["10.0.0.4"]
            and vnet.ddos_protection_enabled is False
        )
        app = next(s for s in vnet.subnets if s.name == "app")
        assert app.nsg_id == NSG and app.nsg_name == "hcw-sample-nsg"
        assert app.route_table_id == RT and app.route_table_name == "hcw-sample-rt"
        assert app.ip_configuration_count == 1 and app.delegation == "Microsoft.Web/serverFarms"
        peering = vnet.peerings[0]
        assert peering.allow_gateway_transit is True and peering.remote_subscription_id == SUB
        # the remote VNet is not in the export: kept as an id, no crash
        assert peering.remote_vnet_name is None

    def test_nsg_route_table_and_flow_log_projection(self, sub):
        nsg = sub.nsgs[0]
        assert nsg.security_rules[0].destination_port_range == "22"
        assert nsg.default_security_rules[0].is_default_rule is True
        assert nsg.flow_log_ids == [FLOWLOG]
        assert nsg.flow_logs_enabled is True  # projected from the enabled flow log
        assert sub.vnets[0].flow_logs_enabled is True  # the NSG covers subnet app
        rt = sub.route_tables[0]
        assert rt.routes[0].next_hop_type == "Internet" and rt.disable_bgp_route_propagation is True
        flow_log = sub.flow_logs[0]
        assert flow_log.traffic_analytics_enabled is False and flow_log.retention_days == 30

    def test_public_ip_owner_and_load_balancer(self, sub):
        pip = sub.public_ips[0]
        assert pip.sku_name == "Basic" and pip.associated_resource_type is None
        lb = sub.load_balancers[0]
        assert lb.lb_type == "Public" and lb.frontend_ip_configs[0].zones == ["1"]
        assert lb.frontend_ip_configs[0].public_ip_id == PIP

    def test_gateway_connections_and_shared_key_never_stored(self, sub):
        gw = sub.virtual_network_gateways[0]
        assert gw.id == GW and gw.sku_name == "Basic" and gw.generation == "Generation1"
        assert gw.subnet_id == f"{VNET}/subnets/GatewaySubnet"
        conn = gw.connections[0]
        assert conn.connection_status == "NotConnected" and conn.shared_key_set is True
        assert "not-a-real-key" not in gw.model_dump_json()

    def test_private_endpoint_zone_groups_and_private_dns(self, sub):
        pe = sub.private_endpoints[0]
        assert pe.id == PE and pe.service_connections[0].connection_state == "Pending"
        assert pe.dns_zone_group_names == ["privatelink-blob-core-windows-net"]
        zone = sub.private_dns_zones[0]
        assert zone.linked_vnet_ids == [VNET] and zone.linked_vnet_names == ["hcw-sample-vnet"]
        assert zone.record_count == 3

    def test_firewall_policy_is_resolved(self, sub):
        fw = sub.firewalls[0]
        assert fw.id == FW and fw.threat_intel_mode == "Alert"
        assert fw.firewall_policy is not None and fw.firewall_policy.threat_intel_mode == "Deny"
        assert fw.effective_threat_intel_mode == "Deny"
        assert sub.firewall_policies[0].dns_proxy_enabled is True

    def test_application_gateway_and_waf_policy(self, sub):
        agw = sub.application_gateways[0]
        assert (
            agw.id == AGW
            and agw.sku_name == "WAF_v2"
            and agw.waf_mode == "Detection"
            and agw.zones == ["1"]
        )
        assert agw.waf_policy is not None and agw.waf_policy.mode == "Detection"
        assert len(sub.waf_policies) == 1

    def test_expressroute_vwan_hub_route_server_and_front_door(self, sub):
        er = sub.express_route_circuits[0]
        assert er.bandwidth_mbps == 1000 and er.peering_types == ["AzurePrivatePeering"]
        wan = sub.virtual_wans[0]
        assert wan.id == VWAN and wan.hubs[0].id == VHUB and wan.hubs[0].virtual_router_asn == 65515
        assert sub.route_servers[0].virtual_router_ips == ["10.0.254.4"]
        assert sub.front_door_waf_policies[0].custom_rules_count == 1
        assert sub.front_door_waf_policies[0].managed_rules_count == 2
        assert sub.nat_gateways[0].associated_subnet_ids == []
        assert sub.bastion_hosts[0].tunneling_enabled is True


class TestWarnings:
    def test_missing_reference_is_named_without_cell_content(self):
        rows = [
            r
            for r in export_rows()
            if r["type"].lower() != "microsoft.network/networksecuritygroups"
        ]
        topology = normalize_resource_graph(rows)
        assert any(
            "network security group hcw-sample-nsg referenced by virtualnetworks hcw-sample-vnet"
            in w
            for w in topology.warnings
        )

    def test_export_without_network_rows_is_rejected(self):
        with pytest.raises(ValueError):
            normalize_resource_graph(
                [{"id": "/x", "name": "x", "type": "microsoft.compute/virtualmachines"}]
            )

    def test_rows_without_properties_are_flagged(self):
        rows = [
            {
                "id": VNET,
                "name": "hcw-sample-vnet",
                "type": "microsoft.network/virtualnetworks",
                "location": "eastus",
            }
        ]
        export = normalize_rows(rows)
        assert export.topology.has_properties is False
        assert export.topology.warnings[0].startswith("no properties column")
        assert export.facts[VNET]["subnets"] == 0

    def test_facts_name_the_fields_the_rules_read(self):
        export = normalize_rows(export_rows())
        assert export.facts[FW]["threatIntelMode"] == "Deny"
        assert export.facts[VNET]["enableDdosProtection"] is False
        assert export.warnings == export.topology.warnings
