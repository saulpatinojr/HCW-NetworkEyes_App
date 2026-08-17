"""Unit tests for Azure discovery engine — Phase C.

All Azure SDK calls are mocked. No real Azure credentials required.
Tests cover:
  - VNet/subnet/peering collection
  - Firewall collection
  - App Gateway collection
  - ExpressRoute circuit collection
  - Subscription enumeration
  - Permission-denied handling (discovery_blocked)
  - Resume/checkpoint skip logic
  - AzureDiscoveryOptions defaults
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from cna.core.topology_schema import AzureSubscriptionTopology
from cna.modules.network.discovery.azure_discovery import AzureDiscovery, AzureDiscoveryOptions


@pytest.fixture
def store():
    s = MagicMock()
    s.engagement_id = "test-20260305-0002"
    s.list_completed_checkpoints.return_value = []
    return s


@pytest.fixture
def opts():
    return AzureDiscoveryOptions(
        tenant_id="00000000-0000-0000-0000-000000000001",
        subscription_ids=["sub-0001"],
    )


@pytest.fixture
def discovery(store, opts):
    d = AzureDiscovery(store=store, options=opts)
    return d


class TestAzureDiscoveryOptions:
    def test_defaults(self):
        opts = AzureDiscoveryOptions(tenant_id="tenant-001")
        assert opts.subscription_ids == []
        assert opts.resume is False
        assert opts.use_resource_graph is True
        assert opts.client_id is None
        assert opts.client_secret is None


class TestCollectVNets:
    def _make_vnet_mock(self):
        vnet = MagicMock()
        vnet.id = "/subscriptions/sub-0001/resourceGroups/rg-net/providers/Microsoft.Network/virtualNetworks/vnet-prod"
        vnet.name = "vnet-prod"
        vnet.location = "eastus"
        vnet.address_space.address_prefixes = ["10.0.0.0/16"]
        vnet.tags = {"env": "prod"}
        vnet.ddos_protection_plan = None
        vnet.enable_ddos_protection = False
        vnet.virtual_network_peerings = []

        subnet = MagicMock()
        subnet.id = "/subscriptions/sub-0001/resourceGroups/rg-net/.../subnets/snet-app"
        subnet.name = "snet-app"
        subnet.address_prefix = "10.0.1.0/24"
        subnet.network_security_group = None
        subnet.route_table = None
        subnet.service_endpoints = []
        subnet.private_endpoint_network_policies = "Enabled"
        subnet.delegations = []
        subnet.nat_gateway = None
        vnet.subnets = [subnet]
        return vnet

    def test_basic_vnet_collected(self, discovery):
        net = MagicMock()
        net.virtual_networks.list_all.return_value = [self._make_vnet_mock()]
        vnets = discovery._collect_vnets(net, "sub-0001")
        assert len(vnets) == 1
        assert vnets[0].name == "vnet-prod"
        assert vnets[0].location == "eastus"
        assert vnets[0].address_space == ["10.0.0.0/16"]
        assert len(vnets[0].subnets) == 1
        assert vnets[0].subnets[0].name == "snet-app"

    def test_empty_vnet_list(self, discovery):
        net = MagicMock()
        net.virtual_networks.list_all.return_value = []
        vnets = discovery._collect_vnets(net, "sub-0001")
        assert vnets == []


class TestCollectFirewalls:
    def test_firewall_collected(self, discovery):
        net = MagicMock()
        fw = MagicMock()
        fw.id = "/subscriptions/sub-0001/resourceGroups/rg-hub/providers/.../azureFirewalls/fw-hub"
        fw.name = "fw-hub"
        fw.location = "eastus"
        fw.sku.tier = "Premium"
        fw.ip_configurations = []
        fw.firewall_policy = None
        fw.threat_intel_mode = "Deny"
        net.azure_firewalls.list_all.return_value = [fw]
        firewalls = discovery._collect_firewalls(net, "sub-0001")
        assert len(firewalls) == 1
        assert firewalls[0].name == "fw-hub"
        assert firewalls[0].sku_tier == "Premium"
        assert firewalls[0].threat_intel_mode == "Deny"


class TestCollectExpressRoute:
    def test_er_circuit_collected(self, discovery):
        net = MagicMock()
        erc = MagicMock()
        erc.id = "/subscriptions/sub-0001/resourceGroups/rg-conn/providers/.../expressRouteCircuits/er-01"
        erc.name = "er-01"
        erc.location = "eastus"
        erc.sku.tier = "Premium"
        erc.sku.family = "UnlimitedData"
        erc.service_provider_properties.service_provider_name = "Equinix"
        erc.service_provider_properties.peering_location = "New York"
        erc.service_provider_properties.bandwidth_in_mbps = 1000
        erc.circuit_provisioning_state = "Enabled"
        net.express_route_circuits.list_all.return_value = [erc]
        circuits = discovery._collect_er_circuits(net, "sub-0001")
        assert len(circuits) == 1
        assert circuits[0].name == "er-01"
        assert circuits[0].bandwidth_mbps == 1000
        assert circuits[0].service_provider == "Equinix"


class TestDiscoveryBlocked:
    def test_http_403_sets_blocked(self, discovery):
        topo = AzureSubscriptionTopology(
            subscription_id="sub-0001",
            tenant_id="tenant-001",
            discovery_blocked=True,
            block_reason="HTTP 403: Forbidden",
        )
        with patch.object(discovery, "_discover_subscription", return_value=topo):
            result = discovery._discover_subscription("sub-0001", "test-sub")
            assert result.discovery_blocked is True
            assert "403" in result.block_reason


class TestRun:
    """`AzureDiscovery.run()` — the orchestrator entry point (TODO.md T-403).

    Like its AWS counterpart, `run()` is excluded from coverage measurement by
    `[tool.coverage.run] omit`, so the `fail_under = 80` gate never saw it. Every
    Azure SDK collaborator is mocked here; no ARM call is made.
    """

    def _sub_topo(self, sub_id="sub-0001", blocked=False, reason=None):
        return AzureSubscriptionTopology(
            subscription_id=sub_id,
            tenant_id="00000000-0000-0000-0000-000000000001",
            discovery_blocked=blocked,
            block_reason=reason,
        )

    def test_returns_topology_for_the_requested_subscription(self, discovery, store):
        """opts.subscription_ids is set, so run() goes direct and skips list()."""
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=[]),
            patch.object(
                discovery,
                "_get_subscription_direct",
                return_value={"id": "sub-0001", "name": "prod", "tenant_id": "t"},
            ),
            patch.object(
                discovery, "_discover_subscription", return_value=self._sub_topo()
            ) as discover,
            patch.object(discovery, "_list_subscriptions") as list_subs,
        ):
            topology = discovery.run()

        assert topology.engagement_id == store.engagement_id
        assert [s.subscription_id for s in topology.subscriptions] == ["sub-0001"]
        discover.assert_called_once_with("sub-0001", "prod")
        list_subs.assert_not_called()

    def test_validates_access_before_doing_any_work(self, discovery):
        """A permissions failure must surface immediately, not mid-scan."""
        with (
            patch.object(discovery, "validate_access", side_effect=PermissionError("no Reader")),
            patch.object(discovery, "_discover_subscription") as discover,
            pytest.raises(PermissionError),
        ):
            discovery.run()

        assert discover.call_count == 0

    def test_proceeds_when_the_subscription_metadata_lookup_fails(self, discovery):
        """A network-only Reader can't call subscriptions.get() but can still discover.

        The ID is used as the display name and the scan continues — regressing this
        would silently skip subscriptions the SP can actually read.
        """
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=[]),
            patch.object(discovery, "_get_subscription_direct", return_value=None),
            patch.object(
                discovery, "_discover_subscription", return_value=self._sub_topo()
            ) as discover,
        ):
            topology = discovery.run()

        discover.assert_called_once_with("sub-0001", "sub-0001")
        assert len(topology.subscriptions) == 1

    def test_lists_subscriptions_when_no_ids_are_given(self, discovery, opts):
        opts.subscription_ids = []
        subs = [
            {"id": "sub-a", "name": "alpha", "tenant_id": "t"},
            {"id": "sub-b", "name": "beta", "tenant_id": "t"},
        ]
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=[]),
            patch.object(discovery, "_list_subscriptions", return_value=subs) as list_subs,
            patch.object(discovery, "_get_subscription_direct") as direct,
            patch.object(
                discovery,
                "_discover_subscription",
                side_effect=lambda sid, name: self._sub_topo(sid),
            ) as discover,
        ):
            topology = discovery.run()

        list_subs.assert_called_once()
        direct.assert_not_called()
        assert [s.subscription_id for s in topology.subscriptions] == ["sub-a", "sub-b"]
        assert discover.call_count == 2

    def test_records_the_management_group_hierarchy(self, discovery):
        groups = [MagicMock(), MagicMock()]
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=groups),
            patch.object(
                discovery,
                "_get_subscription_direct",
                return_value={"id": "sub-0001", "name": "prod", "tenant_id": "t"},
            ),
            patch.object(discovery, "_discover_subscription", return_value=self._sub_topo()),
        ):
            topology = discovery.run()

        assert len(topology.management_groups) == 2

    def test_writes_a_checkpoint_for_each_subscription(self, discovery, store):
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=[]),
            patch.object(
                discovery,
                "_get_subscription_direct",
                return_value={"id": "sub-0001", "name": "prod", "tenant_id": "t"},
            ),
            patch.object(discovery, "_discover_subscription", return_value=self._sub_topo()),
        ):
            discovery.run()

        store.write_discovery_checkpoint.assert_called_once()
        args = store.write_discovery_checkpoint.call_args.args
        assert args[1] == "azure"
        assert args[2] == "sub-0001"
        assert args[3]["subscription_id"] == "sub-0001"

    def test_resume_skips_subscriptions_that_already_have_a_checkpoint(
        self, discovery, opts, store
    ):
        opts.resume = True
        store.list_completed_checkpoints.return_value = ["azure/sub-0001.json"]
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=[]),
            patch.object(
                discovery,
                "_get_subscription_direct",
                return_value={"id": "sub-0001", "name": "prod", "tenant_id": "t"},
            ),
            patch.object(discovery, "_discover_subscription") as discover,
        ):
            topology = discovery.run()

        discover.assert_not_called()
        assert topology.subscriptions == []

    def test_resume_still_scans_subscriptions_without_a_checkpoint(self, discovery, opts, store):
        opts.resume = True
        store.list_completed_checkpoints.return_value = ["azure/sub-9999.json"]
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=[]),
            patch.object(
                discovery,
                "_get_subscription_direct",
                return_value={"id": "sub-0001", "name": "prod", "tenant_id": "t"},
            ),
            patch.object(
                discovery, "_discover_subscription", return_value=self._sub_topo()
            ) as discover,
        ):
            topology = discovery.run()

        discover.assert_called_once()
        assert len(topology.subscriptions) == 1

    def test_a_blocked_subscription_is_still_recorded_and_checkpointed(self, discovery, store):
        """Blocked is a result, not an error — dropping it would hide the gap in the report."""
        blocked = self._sub_topo(blocked=True, reason="HTTP 403: Forbidden")
        with (
            patch.object(discovery, "validate_access"),
            patch.object(discovery, "_collect_management_groups", return_value=[]),
            patch.object(
                discovery,
                "_get_subscription_direct",
                return_value={"id": "sub-0001", "name": "prod", "tenant_id": "t"},
            ),
            patch.object(discovery, "_discover_subscription", return_value=blocked),
        ):
            topology = discovery.run()

        assert len(topology.subscriptions) == 1
        assert topology.subscriptions[0].discovery_blocked is True
        store.write_discovery_checkpoint.assert_called_once()

    def test_reports_progress_through_the_callback(self, store, opts):
        """The CLI passes a progress_callback; run() must actually drive it."""
        messages: list[str] = []
        d = AzureDiscovery(store=store, options=opts, progress_callback=messages.append)
        with (
            patch.object(d, "validate_access"),
            patch.object(d, "_collect_management_groups", return_value=[]),
            patch.object(
                d,
                "_get_subscription_direct",
                return_value={"id": "sub-0001", "name": "prod", "tenant_id": "t"},
            ),
            patch.object(d, "_discover_subscription", return_value=self._sub_topo()),
        ):
            d.run()

        assert messages, "expected run() to emit progress messages"
        assert any("sub-0001" in m for m in messages)
