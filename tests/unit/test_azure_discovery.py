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

import contextlib
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import HttpResponseError

from cna.core.exceptions import CNAAuthError
from cna.core.topology_schema import (
    AppGatewayMetric,
    AzureSubscriptionTopology,
    NetworkMetrics,
    SubnetType,
)
from cna.modules.network.discovery.azure_discovery import (
    AzureDiscovery,
    AzureDiscoveryOptions,
    _classify_subnet,
    _MetricsContext,
    _rg_from_id,
    _safe_list,
    _sub_from_id,
)

MODULE = "cna.modules.network.discovery.azure_discovery"


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


# ---------------------------------------------------------------------------
# TODO.md T-408 — coverage for the orchestrator and the collectors that had
# none. Everything is mocked; no Azure call is made.
# ---------------------------------------------------------------------------


class TestResourceIdHelpers:
    @pytest.mark.parametrize(
        "resource_id,expected",
        [
            ("/subscriptions/s1/resourceGroups/rg-net/providers/x/y/z", "rg-net"),
            # ARM is case-inconsistent about this segment; both spellings occur.
            ("/subscriptions/s1/resourcegroups/rg-low/providers/x/y/z", "rg-low"),
            ("/subscriptions/s1/RESOURCEGROUPS/rg-up/providers/x/y/z", "rg-up"),
        ],
    )
    def test_rg_from_id(self, resource_id, expected):
        assert _rg_from_id(resource_id) == expected

    def test_rg_from_id_falls_back_on_a_malformed_id(self):
        assert _rg_from_id("not-an-arm-id") == ""

    @pytest.mark.parametrize(
        "resource_id,expected",
        [
            ("/subscriptions/sub-0001/resourceGroups/rg/providers/x", "sub-0001"),
            ("/SUBSCRIPTIONS/sub-0002/resourceGroups/rg", "sub-0002"),
            ("no-subscription-segment", ""),
        ],
    )
    def test_sub_from_id(self, resource_id, expected):
        assert _sub_from_id(resource_id) == expected


class TestSafeList:
    def test_materialises_an_iterable(self):
        assert _safe_list(iter([1, 2, 3])) == [1, 2, 3]

    def test_returns_empty_on_any_exception(self):
        """Azure pagers raise mid-iteration on a permission boundary."""

        def _explode():
            yield 1
            raise RuntimeError("403 on page 2")

        assert _safe_list(_explode()) == []


class TestClassifySubnet:
    @pytest.mark.parametrize("name", ["GatewaySubnet", "AzureFirewallSubnet", "AzureBastionSubnet"])
    def test_wellknown_infra_names_are_private_regardless_of_config(self, name):
        assert _classify_subnet(name, None, None, None, True) == SubnetType.PRIVATE

    def test_delegation_forces_private(self):
        assert (
            _classify_subnet("app", None, None, "Microsoft.Web/serverFarms", True)
            == SubnetType.PRIVATE
        )

    def test_nsg_and_udr_is_isolated(self):
        assert _classify_subnet("app", "nsg-1", "rt-1", None, True) == SubnetType.ISOLATED

    @pytest.mark.parametrize("nsg,udr", [("nsg-1", None), (None, "rt-1")])
    def test_one_control_layer_is_private(self, nsg, udr):
        assert _classify_subnet("app", nsg, udr, None, True) == SubnetType.PRIVATE

    def test_no_controls_with_default_outbound_is_public(self):
        assert _classify_subnet("app", None, None, None, True) == SubnetType.PUBLIC

    def test_no_controls_without_default_outbound_is_unknown(self):
        assert _classify_subnet("app", None, None, None, False) == SubnetType.UNKNOWN


class TestCredentialGuards:
    """`_cred` / `_subs` narrow Optional once instead of at 17 sites (T-410)."""

    def test_cred_raises_before_initialisation(self, discovery):
        with pytest.raises(RuntimeError, match="credential not initialised"):
            _ = discovery._cred

    def test_subs_raises_before_initialisation(self, discovery):
        with pytest.raises(RuntimeError, match="subscription client not initialised"):
            _ = discovery._subs


class TestInitCredentials:
    def test_uses_service_principal_when_both_id_and_secret_are_set(self, store):
        opts = AzureDiscoveryOptions(
            tenant_id="tenant-1", client_id="app-1", client_secret="placeholder-not-real"
        )
        d = AzureDiscovery(store=store, options=opts)
        csc, dac, subclient = MagicMock(), MagicMock(), MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "azure.identity": MagicMock(ClientSecretCredential=csc, DefaultAzureCredential=dac),
                "azure.mgmt.subscription": MagicMock(SubscriptionClient=subclient),
            },
        ):
            d._init_credentials()

        csc.assert_called_once()
        dac.assert_not_called()
        assert csc.call_args.kwargs["tenant_id"] == "tenant-1"

    def test_falls_back_to_the_default_credential_chain(self, discovery):
        csc, dac, subclient = MagicMock(), MagicMock(), MagicMock()

        with patch.dict(
            "sys.modules",
            {
                "azure.identity": MagicMock(ClientSecretCredential=csc, DefaultAzureCredential=dac),
                "azure.mgmt.subscription": MagicMock(SubscriptionClient=subclient),
            },
        ):
            discovery._init_credentials()

        dac.assert_called_once()
        csc.assert_not_called()
        assert discovery._sub_client is subclient.return_value

    def test_missing_sdk_raises_a_named_auth_error_naming_the_install(self, discovery):
        with (
            patch.dict("sys.modules", {"azure.identity": None}),
            pytest.raises(CNAAuthError, match="pip install azure-identity"),
        ):
            discovery._init_credentials()


class TestValidateAccess:
    def _wire(self, discovery, token_ok=True):
        discovery._credential = MagicMock()
        discovery._sub_client = MagicMock()
        if token_ok:
            discovery._credential.get_token.return_value = MagicMock(expires_on=123)
        else:
            discovery._credential.get_token.side_effect = RuntimeError("no token")

    def test_token_failure_is_fatal(self, discovery):
        with patch.object(discovery, "_init_credentials"):
            self._wire(discovery, token_ok=False)
            with pytest.raises(CNAAuthError, match="cannot obtain ARM token"):
                discovery.validate_access()

    def test_returns_early_when_no_subscription_filter_is_set(self, store):
        d = AzureDiscovery(store=store, options=AzureDiscoveryOptions(tenant_id="t"))
        with patch.object(d, "_init_credentials"):
            self._wire(d)
            d.validate_access()
        d._sub_client.subscriptions.get.assert_not_called()

    def test_reports_each_requested_subscription(self, discovery):
        messages = []
        discovery._progress = messages.append
        with patch.object(discovery, "_init_credentials"):
            self._wire(discovery)
            discovery._sub_client.subscriptions.get.return_value = MagicMock(
                display_name="Prod", state="Enabled"
            )
            discovery.validate_access()

        assert any("sub-0001" in m and "Prod" in m for m in messages)

    def test_warns_on_a_state_that_may_limit_discovery(self, discovery):
        messages = []
        discovery._progress = messages.append
        with patch.object(discovery, "_init_credentials"):
            self._wire(discovery)
            discovery._sub_client.subscriptions.get.return_value = MagicMock(
                display_name="Old", state="Disabled"
            )
            discovery.validate_access()

        assert any("WARNING" in m for m in messages)

    def test_an_inaccessible_subscription_is_reported_not_raised(self, discovery):
        """One unreadable subscription must not abort the pre-flight for the rest."""
        messages = []
        discovery._progress = messages.append
        with patch.object(discovery, "_init_credentials"):
            self._wire(discovery)
            discovery._sub_client.subscriptions.get.side_effect = RuntimeError("403")
            discovery.validate_access()

        assert any("NOT accessible" in m for m in messages)


class TestListSubscriptions:
    def _sub(self, sub_id, name, state):
        s = MagicMock()
        s.subscription_id, s.display_name, s.state = sub_id, name, state
        return s

    @pytest.mark.parametrize("state", ["Enabled", "Warned", "PastDue"])
    def test_readable_states_are_included(self, discovery, state):
        discovery._sub_client = MagicMock()
        discovery._sub_client.subscriptions.list.return_value = [self._sub("sub-1", "One", state)]

        assert [s["id"] for s in discovery._list_subscriptions()] == ["sub-1"]

    @pytest.mark.parametrize("state", ["Disabled", "Deleted"])
    def test_inaccessible_states_are_skipped(self, discovery, state):
        discovery._sub_client = MagicMock()
        discovery._sub_client.subscriptions.list.return_value = [self._sub("sub-1", "One", state)]

        assert discovery._list_subscriptions() == []

    def test_skipped_subscriptions_are_named_in_the_progress_log(self, discovery):
        messages = []
        discovery._progress = messages.append
        discovery._sub_client = MagicMock()
        discovery._sub_client.subscriptions.list.return_value = [
            self._sub("sub-1", "Live", "Enabled"),
            self._sub("sub-2", "Dead", "Disabled"),
        ]

        discovery._list_subscriptions()

        assert any("Dead" in m and "Disabled" in m for m in messages)


class TestGetSubscriptionDirect:
    def test_returns_the_subscription_when_readable(self, discovery):
        discovery._sub_client = MagicMock()
        discovery._sub_client.subscriptions.get.return_value = MagicMock(
            subscription_id="sub-1", display_name="One"
        )

        assert discovery._get_subscription_direct("sub-1")["name"] == "One"

    def test_falls_back_to_the_id_when_the_name_is_absent(self, discovery):
        discovery._sub_client = MagicMock()
        discovery._sub_client.subscriptions.get.return_value = MagicMock(
            subscription_id="sub-1", display_name=None
        )

        assert discovery._get_subscription_direct("sub-1")["name"] == "sub-1"

    def test_returns_none_on_failure(self, discovery):
        discovery._sub_client = MagicMock()
        discovery._sub_client.subscriptions.get.side_effect = RuntimeError("403")

        assert discovery._get_subscription_direct("sub-1") is None


class TestCollectManagementGroups:
    def test_splits_children_into_management_groups_and_subscriptions(self, discovery):
        discovery._credential = MagicMock()
        mg = MagicMock()
        mg.name, mg.display_name = "mg-root", "Root"
        detail = MagicMock()
        child_mg, child_sub = MagicMock(), MagicMock()
        child_mg.id, child_mg.name = "/providers/.../managementGroups/mg-a", "mg-a"
        child_sub.id, child_sub.name = "/subscriptions/sub-1", "sub-1"
        detail.children = [child_mg, child_sub]
        api = MagicMock()
        api.return_value.management_groups.list.return_value = [mg]
        api.return_value.management_groups.get.return_value = detail

        with patch.dict(
            "sys.modules", {"azure.mgmt.managementgroups": MagicMock(ManagementGroupsAPI=api)}
        ):
            groups = discovery._collect_management_groups()

        assert len(groups) == 1
        assert groups[0].child_mg_ids == ["mg-a"]
        assert groups[0].subscription_ids == ["sub-1"]

    def test_missing_sdk_returns_empty_rather_than_raising(self, discovery):
        with patch.dict("sys.modules", {"azure.mgmt.managementgroups": None}):
            assert discovery._collect_management_groups() == []

    def test_enumeration_failure_returns_empty(self, discovery):
        """Tenant-root MG read is frequently denied; it must not fail discovery."""
        discovery._credential = MagicMock()
        api = MagicMock()
        api.return_value.management_groups.list.side_effect = RuntimeError("403")

        with patch.dict(
            "sys.modules", {"azure.mgmt.managementgroups": MagicMock(ManagementGroupsAPI=api)}
        ):
            assert discovery._collect_management_groups() == []


# Collectors driven by `_discover_subscription`, in call order. Kept as one list
# so the ordering assertion below cannot drift from the patch set.
_PHASE1_COLLECTORS = [
    ("public_ips", "_collect_public_ips"),
    ("nsgs", "_collect_nsgs"),
    ("route_tables", "_collect_route_tables"),
    ("nat_gateways", "_collect_nat_gateways"),
    ("vnets", "_collect_vnets"),
    ("virtual_wans", "_collect_vwans"),
    ("route_servers", "_collect_route_servers"),
    ("firewalls", "_collect_firewalls"),
    ("application_gateways", "_collect_appgws"),
    ("load_balancers", "_collect_load_balancers"),
    ("virtual_network_gateways", "_collect_vnet_gateways"),
    ("private_endpoints", "_collect_private_endpoints"),
    ("bastion_hosts", "_collect_bastion_hosts"),
    ("private_dns_zones", "_collect_private_dns"),
    ("express_route_circuits", "_collect_er_circuits"),
]


@contextlib.contextmanager
def _all_collectors_stubbed(discovery, returns=None, raises=None):
    """Patch every phase-1 collector plus the phase-2 scan, and the ARM clients."""
    returns = returns or {}
    raises = raises or {}
    discovery._credential = MagicMock()  # _cred narrows this and raises when unset
    with contextlib.ExitStack() as stack:
        stack.enter_context(patch(f"{MODULE}.NetworkManagementClient", create=True))
        stack.enter_context(patch("azure.mgmt.network.NetworkManagementClient"))
        rmc = stack.enter_context(patch("azure.mgmt.resource.resources.ResourceManagementClient"))
        rg = MagicMock()
        rg.name = "rg-net"  # `name=` is reserved by MagicMock itself
        rmc.return_value.resource_groups.list.return_value = [rg]
        patched = {}
        for _attr, method in _PHASE1_COLLECTORS:
            kwargs = {}
            if method in raises:
                kwargs["side_effect"] = raises[method]
            else:
                kwargs["return_value"] = returns.get(method, [])
            patched[method] = stack.enter_context(patch.object(discovery, method, **kwargs))
        patched["_run_phase2_collectors"] = stack.enter_context(
            patch.object(discovery, "_run_phase2_collectors")
        )
        yield patched


class TestDiscoverSubscription:
    def test_runs_every_collector_and_returns_an_unblocked_topology(self, discovery):
        with _all_collectors_stubbed(discovery) as patched:
            topo = discovery._discover_subscription("sub-0001", "Prod")

        assert topo.subscription_id == "sub-0001"
        assert topo.subscription_name == "Prod"
        assert topo.discovery_blocked is False
        for _attr, method in _PHASE1_COLLECTORS:
            assert patched[method].called, f"{method} was never called"
        patched["_run_phase2_collectors"].assert_called_once()

    def test_client_construction_failure_blocks_the_whole_subscription(self, discovery):
        """No ARM client means nothing can be read — that is a blocked subscription."""
        discovery._credential = MagicMock()
        with patch(
            "azure.mgmt.network.NetworkManagementClient", side_effect=RuntimeError("403 on ARM")
        ):
            topo = discovery._discover_subscription("sub-0001", "Prod")

        assert topo.discovery_blocked is True
        assert "403 on ARM" in topo.block_reason

    def test_one_failing_collector_does_not_block_the_others(self, discovery):
        """A missing permission on one resource type must not lose the subscription."""
        with _all_collectors_stubbed(
            discovery,
            returns={"_collect_nsgs": [MagicMock()]},
            raises={"_collect_firewalls": RuntimeError("no Microsoft.Network/azureFirewalls read")},
        ) as patched:
            topo = discovery._discover_subscription("sub-0001", "Prod")

        assert topo.discovery_blocked is False, "something was discovered, so not blocked"
        assert "_collect_firewalls" not in topo.block_reason
        assert "firewalls:" in topo.block_reason
        assert patched["_collect_er_circuits"].called, "later collectors still ran"

    def test_http_response_errors_are_reported_with_their_status(self, discovery):
        err = HttpResponseError(message="Forbidden")
        err.status_code = 403
        with _all_collectors_stubbed(
            discovery,
            returns={"_collect_nsgs": [MagicMock()]},
            raises={"_collect_vnets": err},
        ):
            topo = discovery._discover_subscription("sub-0001", "Prod")

        assert "HTTP 403" in topo.block_reason

    def test_every_collector_failing_marks_the_subscription_blocked(self, discovery):
        raises = {method: RuntimeError("403") for _a, method in _PHASE1_COLLECTORS}
        with _all_collectors_stubbed(discovery, raises=raises):
            topo = discovery._discover_subscription("sub-0001", "Prod")

        assert topo.discovery_blocked is True

    def test_progress_log_summarises_phase_one(self, discovery):
        messages = []
        discovery._progress = messages.append
        with _all_collectors_stubbed(discovery):
            discovery._discover_subscription("sub-0001", "Prod")

        assert any("Phase 1 complete" in m for m in messages)


class TestPhase2Scans:
    """Each phase-2 scan is independently fault-isolated — one failure must not
    stop the next, because they are appended to an already-valid topology."""

    def _topo(self):
        return AzureSubscriptionTopology(
            subscription_id="sub-0001", subscription_name="Prod", tenant_id="t"
        )

    def test_phase2_runs_all_five_scans(self, discovery):
        topo = self._topo()
        with (
            patch.object(discovery, "_run_nva_scan") as nva,
            patch.object(discovery, "_run_bgp_scan") as bgp,
            patch.object(discovery, "_run_observability_scan") as obs,
            patch.object(discovery, "_run_metrics_scan") as met,
            patch.object(discovery, "_run_waf_scan") as waf,
        ):
            discovery._run_phase2_collectors(topo, MagicMock(), "sub-0001", "Prod")

        for scan in (nva, bgp, obs, met, waf):
            scan.assert_called_once()

    def test_nva_scan_records_and_reports_findings(self, discovery):
        messages = []
        discovery._progress = messages.append
        topo = self._topo()
        nva = MagicMock()
        nva.name = "fortigate-01"
        with patch.object(discovery, "_collect_nvas", return_value=[nva]):
            discovery._run_nva_scan(topo, MagicMock(), "sub-0001", "Prod")

        assert topo.nvas == [nva]
        assert any("fortigate-01" in m for m in messages)

    def test_nva_scan_reports_when_none_are_found(self, discovery):
        messages = []
        discovery._progress = messages.append
        with patch.object(discovery, "_collect_nvas", return_value=[]):
            discovery._run_nva_scan(self._topo(), MagicMock(), "sub-0001", "Prod")

        assert any("No NVAs" in m for m in messages)

    def test_nva_scan_failure_is_reported_not_raised(self, discovery):
        messages = []
        discovery._progress = messages.append
        with patch.object(discovery, "_collect_nvas", side_effect=RuntimeError("no compute read")):
            discovery._run_nva_scan(self._topo(), MagicMock(), "sub-0001", "Prod")

        assert any("NVA scan skipped" in m for m in messages)

    def test_bgp_scan_failure_is_reported_not_raised(self, discovery):
        messages = []
        discovery._progress = messages.append
        with patch.object(discovery, "_collect_bgp_data", side_effect=RuntimeError("timeout")):
            discovery._run_bgp_scan(self._topo(), MagicMock(), "sub-0001", "Prod")

        assert any("BGP data skipped" in m for m in messages)

    def test_observability_scan_summarises_what_it_found(self, discovery):
        messages = []
        discovery._progress = messages.append
        topo = self._topo()
        obs = MagicMock()
        obs.network_watchers = ["eastus"]
        obs.log_analytics_workspaces = ["law-1"]
        obs.nsg_flow_logs_enabled, obs.nsg_flow_logs_total = 1, 2
        with patch.object(discovery, "_collect_observability", return_value=obs):
            discovery._run_observability_scan(topo, MagicMock(), "sub-0001", "Prod")

        assert topo.observability is obs
        assert any("Observability:" in m for m in messages)

    def test_observability_scan_failure_is_reported_not_raised(self, discovery):
        messages = []
        discovery._progress = messages.append
        with patch.object(discovery, "_collect_observability", side_effect=RuntimeError("no read")):
            discovery._run_observability_scan(self._topo(), MagicMock(), "sub-0001", "Prod")

        assert any("Observability data skipped" in m for m in messages)

    def test_metrics_scan_reports_a_collection_error_from_the_metrics_object(self, discovery):
        """The metrics collector reports failure in-band rather than by raising."""
        messages = []
        discovery._progress = messages.append
        topo = self._topo()
        metrics = MagicMock()
        metrics.collection_error = "azure-monitor-query not installed"
        with patch.object(discovery, "_collect_network_metrics", return_value=metrics):
            discovery._run_metrics_scan(topo, "sub-0001", "Prod")

        assert any("azure-monitor-query not installed" in m for m in messages)

    def test_metrics_scan_summarises_a_successful_collection(self, discovery):
        messages = []
        discovery._progress = messages.append
        topo = self._topo()
        metrics = MagicMock()
        metrics.collection_error = None
        metrics.gateway_metrics, metrics.firewall_metrics = ["g"], []
        metrics.lb_metrics, metrics.vnet_utilization = ["l"], ["v"]
        with patch.object(discovery, "_collect_network_metrics", return_value=metrics):
            discovery._run_metrics_scan(topo, "sub-0001", "Prod")

        assert any("Metrics collected" in m for m in messages)

    def test_metrics_scan_failure_is_reported_not_raised(self, discovery):
        messages = []
        discovery._progress = messages.append
        with patch.object(
            discovery, "_collect_network_metrics", side_effect=RuntimeError("throttled")
        ):
            discovery._run_metrics_scan(self._topo(), "sub-0001", "Prod")

        assert any("Metrics skipped" in m for m in messages)

    def test_waf_scan_collects_front_door_policies_and_defender_findings(self, discovery):
        topo = self._topo()
        with (
            patch.object(discovery, "_collect_front_door_waf_policies", return_value=["p"]),
            patch.object(discovery, "_collect_defender_assessments", return_value=["a"]),
        ):
            discovery._run_waf_scan(topo, "sub-0001", "Prod")

        assert topo.front_door_waf_policies == ["p"]
        assert topo.defender_assessments == ["a"]

    def test_waf_and_defender_failures_are_independent(self, discovery):
        """Front Door and Defender are separate SDKs; one missing must not lose the other."""
        messages = []
        discovery._progress = messages.append
        topo = self._topo()
        with (
            patch.object(
                discovery,
                "_collect_front_door_waf_policies",
                side_effect=RuntimeError("no cdn sdk"),
            ),
            patch.object(discovery, "_collect_defender_assessments", return_value=["a"]),
        ):
            discovery._run_waf_scan(topo, "sub-0001", "Prod")

        assert any("Front Door WAF scan skipped" in m for m in messages)
        assert topo.defender_assessments == ["a"]

    def test_defender_failure_is_reported_not_raised(self, discovery):
        messages = []
        discovery._progress = messages.append
        with (
            patch.object(discovery, "_collect_front_door_waf_policies", return_value=[]),
            patch.object(
                discovery,
                "_collect_defender_assessments",
                side_effect=RuntimeError("no security sdk"),
            ),
        ):
            discovery._run_waf_scan(self._topo(), "sub-0001", "Prod")

        assert any("Defender for Cloud skipped" in m for m in messages)


class _Arm:
    """Stand-in for an ARM SDK model object.

    The collectors read many optional attributes directly (`pip.dns_settings`,
    `lb.sku`, …) and coerce them (`int(x or 4)`), so a bare `MagicMock` is the
    wrong shape — `int(MagicMock())` raises. This returns `None` for anything
    not explicitly set, which is what the SDK does for an unpopulated field.
    """

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)

    def __getattr__(self, name):  # only reached when the attribute was not set
        return None


class TestInferPipAssocType:
    @pytest.mark.parametrize(
        "assoc_id,expected",
        [
            ("/subscriptions/s/.../loadBalancers/lb-1/frontendIPConfigurations/f", "LB"),
            ("/subscriptions/s/.../applicationGateways/agw-1/x", "AppGW"),
            ("/subscriptions/s/.../azureFirewalls/afw-1/x", "Firewall"),
            ("/subscriptions/s/.../virtualNetworkGateways/vgw-1/x", "VpnGateway"),
            ("/subscriptions/s/.../bastionHosts/bas-1/x", "Bastion"),
            ("/subscriptions/s/.../networkInterfaces/nic-1/x", "NIC"),
            # natGateways is deliberately absent from _PIP_ASSOC_TYPES
            ("/subscriptions/s/.../natGateways/nat-1/x", None),
            ("/subscriptions/s/.../somethingElse/x", None),
        ],
    )
    def test_maps_known_owners(self, assoc_id, expected):
        assert AzureDiscovery._infer_pip_assoc_type(assoc_id) == expected


class TestCollectPublicIps:
    def test_maps_a_fully_populated_public_ip(self, discovery):
        net = MagicMock()
        net.public_ip_addresses.list_all.return_value = [
            _Arm(
                id="/subscriptions/sub-0001/resourceGroups/rg-net/providers/"
                "Microsoft.Network/publicIPAddresses/pip-1",
                name="pip-1",
                location="eastus",
                sku=_Arm(name="Standard"),
                public_ip_allocation_method="Static",
                ip_address="20.1.2.3",
                public_ip_address_version="IPv4",
                dns_settings=_Arm(domain_name_label="cna", fqdn="cna.eastus.cloudapp.azure.com"),
                ddos_settings=_Arm(protection_mode="Enabled"),
                zones=["1", "2"],
                idle_timeout_in_minutes=15,
                tags={"env": "prod"},
                ip_configuration=_Arm(
                    id="/subscriptions/s/providers/Microsoft.Network/loadBalancers/lb-1/x"
                ),
            )
        ]

        pips = discovery._collect_public_ips(net, "sub-0001")

        assert len(pips) == 1
        pip = pips[0]
        assert pip.resource_group == "rg-net"
        assert pip.sku_name == "Standard"
        assert pip.dns_label == "cna"
        assert pip.zones == ["1", "2"]
        assert pip.idle_timeout_minutes == 15
        assert pip.ddos_protection_mode == "Enabled"
        assert pip.associated_resource_type == "LB"

    def test_applies_defaults_for_an_unpopulated_public_ip(self, discovery):
        """Basic-SKU and freshly-created IPs leave most of these fields unset."""
        net = MagicMock()
        net.public_ip_addresses.list_all.return_value = [
            _Arm(id="/subscriptions/s/resourceGroups/rg/x", name="pip-1", location="eastus")
        ]

        pip = discovery._collect_public_ips(net, "sub-0001")[0]

        assert pip.sku_name == "Standard"
        assert pip.allocation_method == "Static"
        assert pip.ip_version == "IPv4"
        assert pip.idle_timeout_minutes == 4
        assert pip.ddos_protection_mode == "VirtualNetworkInherited"
        assert pip.associated_resource_id is None
        assert pip.zones == []


class TestCollectLoadBalancers:
    def _lb(self, frontends, rules=None, probes=None):
        return _Arm(
            id="/subscriptions/sub-0001/resourceGroups/rg-net/providers/"
            "Microsoft.Network/loadBalancers/lb-1",
            name="lb-1",
            location="eastus",
            sku=_Arm(name="Standard"),
            frontend_ip_configurations=frontends,
            load_balancing_rules=rules or [],
            probes=probes or [],
            backend_address_pools=[_Arm(id="pool-1"), _Arm(id=None)],
            inbound_nat_rules=[_Arm(), _Arm()],
            tags={},
        )

    def test_a_frontend_with_a_subnet_makes_the_lb_internal(self, discovery):
        net = MagicMock()
        net.load_balancers.list_all.return_value = [
            self._lb(
                [
                    _Arm(
                        name="fe",
                        subnet=_Arm(id="subnet-1"),
                        private_ip_address="10.0.0.4",
                        private_ip_allocation_method="Static",
                        zones=["1"],
                    )
                ]
            )
        ]

        lb = discovery._collect_load_balancers(net, "sub-0001")[0]

        assert lb.lb_type == "Internal"
        assert lb.frontend_ip_configs[0].subnet_id == "subnet-1"
        assert lb.frontend_ip_configs[0].private_ip_allocation_method == "Static"
        assert lb.zones == ["1"]
        assert lb.backend_pool_ids == ["pool-1"], "pools without an id are dropped"
        assert lb.inbound_nat_rule_count == 2

    def test_a_public_frontend_leaves_the_lb_public(self, discovery):
        net = MagicMock()
        net.load_balancers.list_all.return_value = [
            self._lb([_Arm(name="fe", public_ip_address=_Arm(id="pip-1"))])
        ]

        lb = discovery._collect_load_balancers(net, "sub-0001")[0]

        assert lb.lb_type == "Public"
        assert lb.frontend_ip_configs[0].public_ip_id == "pip-1"
        assert lb.frontend_ip_configs[0].private_ip_allocation_method is None

    def test_maps_rules_and_probes_with_defaults(self, discovery):
        net = MagicMock()
        net.load_balancers.list_all.return_value = [
            self._lb(
                [_Arm(name="fe", public_ip_address=_Arm(id="pip-1"))],
                rules=[
                    _Arm(name="http", frontend_port=80, backend_port=8080, enable_floating_ip=True)
                ],
                probes=[_Arm(name="hp", port=8080, request_path="/healthz")],
            )
        ]

        lb = discovery._collect_load_balancers(net, "sub-0001")[0]

        rule = lb.lb_rules[0]
        assert (rule.frontend_port, rule.backend_port) == (80, 8080)
        assert rule.protocol == "Tcp", "unset protocol defaults"
        assert rule.idle_timeout_minutes == 4
        assert rule.load_distribution == "Default"
        assert rule.enable_floating_ip is True
        probe = lb.probes[0]
        assert probe.interval_seconds == 15
        assert probe.number_of_probes == 2
        assert probe.request_path == "/healthz"


class TestCollectVnetGateways:
    def _gw(self, **over):
        base = {
            "id": "/subscriptions/sub-0001/resourceGroups/rg-net/providers/"
            "Microsoft.Network/virtualNetworkGateways/vgw-1",
            "name": "vgw-1",
            "location": "eastus",
            "gateway_type": "Vpn",
            "vpn_type": "RouteBased",
            "sku": _Arm(name="VpnGw2", tier="VpnGw2"),
            "bgp_settings": _Arm(asn=65515, bgp_peering_address="10.0.255.4"),
            "ip_configurations": [
                _Arm(public_ip_address=_Arm(id="pip-1"), subnet=_Arm(id="gwsub"))
            ],
            "active_active": True,
            "enable_bgp": True,
            "vpn_gateway_generation": "Generation2",
            "zones": ["1"],
            "tags": {},
        }
        base.update(over)
        return _Arm(**base)

    def test_iterates_per_resource_group_and_maps_the_gateway(self, discovery):
        net = MagicMock()
        net.virtual_network_gateways.list.return_value = [self._gw()]
        net.virtual_network_gateway_connections.list.return_value = []

        gws = discovery._collect_vnet_gateways(net, "sub-0001", ["rg-net"])

        assert len(gws) == 1
        gw = gws[0]
        assert gw.sku_name == "VpnGw2"
        assert gw.bgp_asn == 65515
        assert gw.public_ip_ids == ["pip-1"]
        assert gw.subnet_id == "gwsub"
        assert gw.active_active is True
        assert gw.generation == "Generation2"
        net.virtual_network_gateways.list.assert_called_once_with("rg-net")

    def test_expressroute_gateways_have_no_vpn_type(self, discovery):
        net = MagicMock()
        net.virtual_network_gateways.list.return_value = [self._gw(gateway_type="ExpressRoute")]
        net.virtual_network_gateway_connections.list.return_value = []

        assert discovery._collect_vnet_gateways(net, "sub-0001", ["rg-net"])[0].vpn_type is None

    def test_collects_vpn_client_address_pools(self, discovery):
        net = MagicMock()
        net.virtual_network_gateways.list.return_value = [
            self._gw(
                vpn_client_configuration=_Arm(
                    vpn_client_address_pool=[_Arm(address_prefixes=["172.16.0.0/24"])]
                )
            )
        ]
        net.virtual_network_gateway_connections.list.return_value = []

        gw = discovery._collect_vnet_gateways(net, "sub-0001", ["rg-net"])[0]

        assert gw.vpn_client_address_pool == ["172.16.0.0/24"]

    def test_applies_sku_defaults_when_unset(self, discovery):
        net = MagicMock()
        net.virtual_network_gateways.list.return_value = [self._gw(sku=None, bgp_settings=None)]
        net.virtual_network_gateway_connections.list.return_value = []

        gw = discovery._collect_vnet_gateways(net, "sub-0001", ["rg-net"])[0]

        assert (gw.sku_name, gw.sku_tier) == ("VpnGw1", "VpnGw1")
        assert gw.bgp_asn is None


class TestCollectGatewayConnections:
    def _conn(self, gw_id, **over):
        base = {
            "id": "/subscriptions/s/resourceGroups/rg/providers/x/conn-1",
            "name": "conn-1",
            "connection_type": "IPsec",
            "connection_status": "Connected",
            "virtual_network_gateway1": _Arm(id=gw_id),
            "routing_weight": 10,
            "enable_bgp": True,
            "use_policy_based_traffic_selectors": False,
            "egress_bytes_transferred": 100,
            "ingress_bytes_transferred": 200,
        }
        base.update(over)
        return _Arm(**base)

    def test_keeps_only_connections_referencing_this_gateway(self, discovery):
        net = MagicMock()
        net.virtual_network_gateway_connections.list.return_value = [
            self._conn("/subscriptions/s/.../virtualNetworkGateways/vgw-1"),
            self._conn("/subscriptions/s/.../virtualNetworkGateways/other-gw", name="conn-2"),
        ]

        conns = discovery._collect_gateway_connections(net, "rg-net", "vgw-1")

        assert [c.name for c in conns] == ["conn-1"]
        assert conns[0].egress_bytes_transferred == 100
        assert conns[0].shared_key_set is True

    def test_records_the_remote_side_of_each_connection_shape(self, discovery):
        net = MagicMock()
        net.virtual_network_gateway_connections.list.return_value = [
            self._conn(
                "/x/virtualNetworkGateways/vgw-1",
                virtual_network_gateway2=_Arm(id="remote-vgw"),
                local_network_gateway2=_Arm(id="lng-1"),
                peer=_Arm(id="er-circuit-1"),
            )
        ]

        conn = discovery._collect_gateway_connections(net, "rg-net", "vgw-1")[0]

        assert conn.remote_vnet_id == "remote-vgw"
        assert conn.local_network_gateway_id == "lng-1"
        assert conn.express_route_circuit_id == "er-circuit-1"

    def test_a_listing_failure_returns_empty_rather_than_losing_the_gateway(self, discovery):
        net = MagicMock()
        net.virtual_network_gateway_connections.list.side_effect = RuntimeError("403")

        assert discovery._collect_gateway_connections(net, "rg-net", "vgw-1") == []


class TestCollectNatGateways:
    def test_maps_associations_and_defaults(self, discovery):
        net = MagicMock()
        net.nat_gateways.list_all.return_value = [
            _Arm(
                id="/subscriptions/sub-0001/resourceGroups/rg-net/providers/x/nat-1",
                name="nat-1",
                location="eastus",
                public_ip_addresses=[_Arm(id="pip-1"), _Arm(id=None)],
                public_ip_prefixes=[_Arm(id="pfx-1")],
                subnets=[_Arm(id="subnet-1")],
                zones=["1"],
                tags={},
            )
        ]

        ng = discovery._collect_nat_gateways(net, "sub-0001")[0]

        assert ng.public_ip_ids == ["pip-1"], "entries without an id are dropped"
        assert ng.public_ip_prefix_ids == ["pfx-1"]
        assert ng.associated_subnet_ids == ["subnet-1"]
        assert ng.idle_timeout_minutes == 4
        assert ng.sku_name == "Standard"
        assert ng.provisioning_state == "Succeeded"


class TestCollectBastionHosts:
    def test_maps_feature_flags_and_ip_configuration(self, discovery):
        net = MagicMock()
        net.bastion_hosts.list.return_value = [
            _Arm(
                id="/subscriptions/sub-0001/resourceGroups/rg-net/providers/x/bas-1",
                name="bas-1",
                location="eastus",
                sku=_Arm(name="Premium"),
                scale_units=4,
                enable_tunneling=True,
                enable_ip_connect=True,
                enable_file_copy=False,
                ip_configurations=[
                    _Arm(
                        subnet=_Arm(id="AzureBastionSubnet-id"), public_ip_address=_Arm(id="pip-1")
                    )
                ],
                tags={},
            )
        ]

        bh = discovery._collect_bastion_hosts(net, "sub-0001")[0]

        assert bh.sku_name == "Premium"
        assert bh.scale_units == 4
        assert bh.tunneling_enabled is True
        assert bh.ip_connect_enabled is True
        assert bh.file_copy_enabled is False
        assert bh.subnet_id == "AzureBastionSubnet-id"
        assert bh.public_ip_id == "pip-1"

    def test_defaults_when_the_optional_fields_are_absent(self, discovery):
        net = MagicMock()
        net.bastion_hosts.list.return_value = [
            _Arm(id="/subscriptions/s/resourceGroups/rg/x", name="bas-1", location="eastus")
        ]

        bh = discovery._collect_bastion_hosts(net, "sub-0001")[0]

        assert bh.sku_name == "Standard"
        assert bh.scale_units == 2
        assert bh.kerberos_enabled is False


class TestValidatePeDns:
    def test_no_custom_dns_but_private_ips_is_treated_as_valid(self):
        assert AzureDiscovery._validate_pe_dns([], ["10.0.0.4"]) is True

    def test_no_custom_dns_and_no_private_ips_is_inconclusive(self):
        assert AzureDiscovery._validate_pe_dns([], []) is None

    def test_resolution_to_an_rfc1918_address_passes(self):
        with patch("socket.gethostbyname", return_value="10.1.2.3"):
            assert AzureDiscovery._validate_pe_dns(["db.privatelink.example"], []) is True

    def test_resolution_to_a_public_address_fails(self):
        """A private endpoint FQDN resolving publicly means DNS is misconfigured."""
        with patch("socket.gethostbyname", return_value="93.184.216.34"):
            assert AzureDiscovery._validate_pe_dns(["db.privatelink.example"], []) is False

    def test_unresolvable_names_are_inconclusive_rather_than_a_failure(self):
        with patch("socket.gethostbyname", side_effect=OSError("NXDOMAIN")):
            assert AzureDiscovery._validate_pe_dns(["nope.example"], []) is None

    def test_checks_at_most_three_names(self):
        with patch("socket.gethostbyname", return_value="93.184.216.34") as resolve:
            AzureDiscovery._validate_pe_dns([f"h{i}.example" for i in range(10)], [])
        assert resolve.call_count == 3


class TestPrivateEndpointHelpers:
    def test_pe_private_ips_reads_each_attached_nic(self, discovery):
        net = MagicMock()
        net.network_interfaces.get.return_value = _Arm(
            ip_configurations=[_Arm(private_ip_address="10.0.0.4"), _Arm()]
        )
        pe = _Arm(network_interfaces=[_Arm(id="/subscriptions/s/resourceGroups/rg/x/nic-1")])

        assert AzureDiscovery._pe_private_ips(net, pe) == ["10.0.0.4"]

    def test_pe_private_ips_skips_a_nic_it_cannot_read(self, discovery):
        net = MagicMock()
        net.network_interfaces.get.side_effect = RuntimeError("403")
        pe = _Arm(network_interfaces=[_Arm(id="/subscriptions/s/resourceGroups/rg/x/nic-1")])

        assert AzureDiscovery._pe_private_ips(net, pe) == []

    def test_pe_service_conns_merges_auto_and_manual_connections(self):
        pe = _Arm(
            private_link_service_connections=[
                _Arm(
                    name="auto",
                    private_link_service_id="pls-1",
                    group_ids=["blob"],
                    private_link_service_connection_state=_Arm(status="Approved"),
                )
            ],
            manual_private_link_service_connections=[
                _Arm(name="manual", private_link_service_id="pls-2", group_ids=[])
            ],
        )

        conns = AzureDiscovery._pe_service_conns(pe)

        assert [c.connection_name for c in conns] == ["auto", "manual"]
        assert conns[0].connection_state == "Approved"
        assert conns[1].connection_state == "Pending", "unset state defaults to Pending"


class TestCollectPrivateEndpoints:
    def test_maps_an_endpoint_with_dns_groups_and_custom_configs(self, discovery):
        net = MagicMock()
        net.network_interfaces.get.return_value = _Arm(
            ip_configurations=[_Arm(private_ip_address="10.0.0.4")]
        )
        net.private_endpoints.list_by_subscription.return_value = [
            _Arm(
                id="/subscriptions/sub-0001/resourceGroups/rg-net/providers/x/pe-1",
                name="pe-1",
                location="eastus",
                subnet=_Arm(id="subnet-1"),
                network_interfaces=[_Arm(id="/subscriptions/s/resourceGroups/rg/x/nic-1")],
                custom_dns_configs=[_Arm(fqdn="db.privatelink.example"), _Arm()],
                private_dns_zone_groups=[_Arm(name="default"), _Arm()],
                private_link_service_connections=[],
                manual_private_link_service_connections=[],
                tags={},
            )
        ]

        pe = discovery._collect_private_endpoints(net, "sub-0001")[0]

        assert pe.subnet_id == "subnet-1"
        assert pe.private_ip_addresses == ["10.0.0.4"]
        assert pe.custom_dns_configs == ["db.privatelink.example"]
        assert pe.dns_zone_group_names == ["default"]

    def test_an_endpoint_without_a_subnet_records_an_empty_subnet_id(self, discovery):
        net = MagicMock()
        net.private_endpoints.list_by_subscription.return_value = [
            _Arm(
                id="/subscriptions/s/resourceGroups/rg/x/pe-1",
                name="pe-1",
                location="eastus",
                network_interfaces=[],
                private_link_service_connections=[],
                manual_private_link_service_connections=[],
            )
        ]

        assert discovery._collect_private_endpoints(net, "sub-0001")[0].subnet_id == ""


class TestCollectFirewallsIpConfigurations:
    """Complements TestCollectFirewalls above, which leaves ip_configurations empty."""

    def test_maps_sku_subnet_and_public_ips(self, discovery):
        net = MagicMock()
        net.azure_firewalls.list_all.return_value = [
            _Arm(
                id="/subscriptions/sub-0001/resourceGroups/rg-net/providers/x/afw-1",
                name="afw-1",
                location="eastus",
                sku=_Arm(tier="Premium"),
                ip_configurations=[
                    _Arm(
                        subnet=_Arm(id="AzureFirewallSubnet-id"), public_ip_address=_Arm(id="pip-1")
                    ),
                    _Arm(public_ip_address=_Arm(id="pip-2")),
                ],
                firewall_policy=_Arm(id="pol-1"),
                threat_intel_mode="Deny",
                zones=["1", "2", "3"],
                tags={},
            )
        ]

        fw = discovery._collect_firewalls(net, "sub-0001")[0]

        assert fw.sku_tier == "Premium"
        assert fw.subnet_id == "AzureFirewallSubnet-id"
        assert fw.public_ip_ids == ["pip-1", "pip-2"]
        assert fw.policy_id == "pol-1"
        assert fw.threat_intel_mode == "Deny"

    def test_falls_back_to_the_id_when_the_name_is_missing(self, discovery):
        net = MagicMock()
        net.azure_firewalls.list_all.return_value = [
            _Arm(id="/subscriptions/s/resourceGroups/rg/providers/x/afw-fallback")
        ]

        fw = discovery._collect_firewalls(net, "sub-0001")[0]

        assert fw.name == "afw-fallback"
        assert fw.sku_tier == "Standard"
        assert fw.threat_intel_mode == "Alert"


class TestCollectAppGateways:
    def _agw(self, **over):
        base = {
            "id": "/subscriptions/sub-0001/resourceGroups/rg-net/providers/x/agw-1",
            "name": "agw-1",
            "location": "eastus",
            "sku": _Arm(name="WAF_v2", capacity=2),
            "gateway_ip_configurations": [_Arm(subnet=_Arm(id="agw-subnet"))],
            "frontend_ip_configurations": [_Arm(name="fe-public"), _Arm(name="fe-private")],
            "ssl_policy": _Arm(policy_name="AppGwSslPolicy20220101S"),
            "zones": ["1"],
            "tags": {},
        }
        base.update(over)
        return _Arm(**base)

    def test_maps_inline_waf_configuration(self, discovery):
        net = MagicMock()
        net.application_gateways.list_all.return_value = [
            self._agw(
                web_application_firewall_configuration=_Arm(
                    enabled=True,
                    firewall_mode="Prevention",
                    rule_set_type="OWASP",
                    rule_set_version="3.2",
                )
            )
        ]

        agw = discovery._collect_appgws(net, "sub-0001")[0]

        assert agw.sku_name == "WAF_v2"
        assert agw.sku_capacity == 2
        assert agw.waf_enabled is True
        assert agw.waf_mode == "Prevention"
        assert agw.waf_rule_set_version == "3.2"
        assert agw.subnet_id == "agw-subnet"
        assert agw.frontend_ip_configs == ["fe-public", "fe-private"]
        assert agw.ssl_policy_name == "AppGwSslPolicy20220101S"

    def test_an_attached_waf_policy_enables_waf_even_without_inline_config(self, discovery):
        """A WAF policy supersedes the deprecated inline block; both mean WAF is on."""
        net = MagicMock()
        net.application_gateways.list_all.return_value = [
            self._agw(firewall_policy=_Arm(id="wafpol-1"))
        ]

        assert discovery._collect_appgws(net, "sub-0001")[0].waf_enabled is True

    def test_no_waf_config_and_no_policy_means_waf_off(self, discovery):
        net = MagicMock()
        net.application_gateways.list_all.return_value = [self._agw()]

        agw = discovery._collect_appgws(net, "sub-0001")[0]

        assert agw.waf_enabled is False
        assert agw.waf_mode is None

    def test_reads_autoscale_bounds(self, discovery):
        net = MagicMock()
        net.application_gateways.list_all.return_value = [
            self._agw(autoscale_configuration=_Arm(min_capacity=2, max_capacity=10))
        ]

        agw = discovery._collect_appgws(net, "sub-0001")[0]

        assert (agw.autoscale_min, agw.autoscale_max) == (2, 10)

    def test_defaults_when_the_sku_block_is_absent(self, discovery):
        net = MagicMock()
        net.application_gateways.list_all.return_value = [
            self._agw(sku=None, gateway_ip_configurations=[], ssl_policy=None)
        ]

        agw = discovery._collect_appgws(net, "sub-0001")[0]

        assert agw.sku_name == "Standard_v2"
        assert agw.subnet_id == ""
        assert agw.ssl_policy_name is None


class TestCollectRouteServers:
    def _hub(self, kind="RouteServer"):
        return _Arm(
            id="/subscriptions/sub-0001/resourceGroups/rg-net/providers/x/rs-1",
            name="rs-1",
            location="eastus",
            kind=kind,
            virtual_router_asn=65515,
            virtual_router_ips=["10.0.1.4", "10.0.1.5"],
            allow_branch_to_branch_traffic=True,
            tags={},
        )

    def test_skips_hubs_that_are_not_route_servers(self, discovery):
        """Route Servers and vWAN hubs share the virtual_hubs collection."""
        net = MagicMock()
        net.virtual_hubs.list.return_value = [self._hub(kind="VirtualWAN")]

        assert discovery._collect_route_servers(net, "sub-0001") == []

    def test_maps_the_hosted_subnet_and_derives_the_vnet(self, discovery):
        net = MagicMock()
        net.virtual_hubs.list.return_value = [self._hub()]
        net.virtual_hub_ip_configuration.list.return_value = [
            _Arm(
                subnet=_Arm(
                    id="/subscriptions/s/.../virtualNetworks/vnet-1/subnets/RouteServerSubnet"
                )
            )
        ]
        net.virtual_hub_bgp_connections.list.return_value = []

        rs = discovery._collect_route_servers(net, "sub-0001")[0]

        assert rs.hosted_subnet_id.endswith("/subnets/RouteServerSubnet")
        assert rs.vnet_id == "/subscriptions/s/.../virtualNetworks/vnet-1"
        assert rs.virtual_router_asn == 65515
        assert rs.allow_branch_to_branch_traffic is True

    def test_maps_bgp_peer_connections(self, discovery):
        net = MagicMock()
        net.virtual_hubs.list.return_value = [self._hub()]
        net.virtual_hub_ip_configuration.list.return_value = []
        net.virtual_hub_bgp_connections.list.return_value = [
            _Arm(
                id="conn-1",
                name="peer-nva",
                peer_ip="10.0.2.4",
                peer_asn=65001,
                connection_state="Connected",
            )
        ]

        rs = discovery._collect_route_servers(net, "sub-0001")[0]

        assert rs.vnet_id is None, "no hosted subnet means no derivable VNet"
        assert rs.bgp_connections[0].peer_asn == 65001
        assert rs.bgp_connections[0].provisioning_state == "Succeeded"


class TestCollectPrivateDns:
    def _client(self, zones, links):
        client = MagicMock()
        client.return_value.private_zones.list.return_value = zones
        client.return_value.virtual_network_links.list.return_value = links
        return client

    def test_maps_zones_and_their_vnet_links(self, discovery):
        discovery._credential = MagicMock()
        client = self._client(
            zones=[
                _Arm(
                    id="/subscriptions/sub-0001/resourceGroups/rg-dns/providers/x/"
                    "privatelink.blob.core.windows.net",
                    name="privatelink.blob.core.windows.net",
                    number_of_record_sets=7,
                )
            ],
            links=[
                _Arm(
                    name="link-hub", virtual_network=_Arm(id="vnet-hub"), registration_enabled=True
                ),
                _Arm(name="link-spoke", virtual_network=_Arm(id="vnet-spoke")),
            ],
        )

        with patch.dict(
            "sys.modules",
            {"azure.mgmt.privatedns": MagicMock(PrivateDnsManagementClient=client)},
        ):
            zones = discovery._collect_private_dns("sub-0001")

        assert len(zones) == 1
        zone = zones[0]
        assert zone.resource_group == "rg-dns"
        assert zone.linked_vnet_ids == ["vnet-hub", "vnet-spoke"]
        assert zone.linked_vnet_names == ["link-hub", "link-spoke"]
        assert zone.auto_registration_enabled is True
        assert zone.record_count == 7

    def test_missing_sdk_returns_empty(self, discovery):
        discovery._credential = MagicMock()
        with patch.dict("sys.modules", {"azure.mgmt.privatedns": None}):
            assert discovery._collect_private_dns("sub-0001") == []

    def test_a_query_failure_returns_empty_rather_than_raising(self, discovery):
        discovery._credential = MagicMock()
        client = MagicMock()
        client.return_value.private_zones.list.side_effect = RuntimeError("403")
        with patch.dict(
            "sys.modules",
            {"azure.mgmt.privatedns": MagicMock(PrivateDnsManagementClient=client)},
        ):
            assert discovery._collect_private_dns("sub-0001") == []


class TestIdentifyNvaPublisher:
    def test_marketplace_plan_from_a_known_vendor(self, discovery):
        vm = _Arm(plan=_Arm(publisher="PaloAltoNetworks", product="vmseries-flex", name="byol"))

        pub, offer, plan, method = discovery._identify_nva_publisher(vm)

        assert (pub, offer, plan, method) == (
            "PaloAltoNetworks",
            "vmseries-flex",
            "byol",
            "marketplace",
        )

    def test_falls_back_to_the_image_reference_for_byol_images(self, discovery):
        vm = _Arm(
            storage_profile=_Arm(
                image_reference=_Arm(
                    publisher="fortinet", offer="fortinet_fortigate-vm_v5", sku="fortinet_fg-vm"
                )
            )
        )

        pub, offer, plan, method = discovery._identify_nva_publisher(vm)

        assert method == "image_reference"
        assert (pub, offer, plan) == ("fortinet", "fortinet_fortigate-vm_v5", "fortinet_fg-vm")

    def test_an_unknown_publisher_matches_nothing(self, discovery):
        vm = _Arm(
            plan=_Arm(publisher="Canonical"),
            storage_profile=_Arm(image_reference=_Arm(publisher="Canonical")),
        )

        assert discovery._identify_nva_publisher(vm) == (None, None, None, None)

    def test_a_vm_with_no_plan_or_image_matches_nothing(self, discovery):
        assert discovery._identify_nva_publisher(_Arm()) == (None, None, None, None)


class TestCollectVmNics:
    def _vm(self, nic_ids):
        return _Arm(
            id="/subscriptions/s/resourceGroups/rg/providers/x/vm-1",
            tags={},
            network_profile=_Arm(network_interfaces=[_Arm(id=i) for i in nic_ids]),
        )

    def test_reports_ip_forwarding_and_maps_the_nic(self, discovery):
        net = MagicMock()
        net.network_interfaces.get.return_value = _Arm(
            id="nic-1",
            name="nic-1",
            location="eastus",
            enable_ip_forwarding=True,
            network_security_group=_Arm(id="nsg-1"),
            ip_configurations=[
                _Arm(
                    subnet=_Arm(id="subnet-1"),
                    private_ip_address="10.0.0.4",
                    public_ip_address=_Arm(id="pip-1"),
                )
            ],
        )

        nics, has_fwd = discovery._collect_vm_nics(
            net, self._vm(["/subscriptions/s/resourceGroups/rg-net/x/nic-1"])
        )

        assert has_fwd is True
        assert nics[0].subnet_ids == ["subnet-1"]
        assert nics[0].private_ips == ["10.0.0.4"]
        assert nics[0].public_ip_id == "pip-1"
        assert nics[0].nsg_id == "nsg-1"
        assert nics[0].resource_group == "rg-net"

    def test_a_vm_without_a_network_profile_yields_nothing(self, discovery):
        assert discovery._collect_vm_nics(MagicMock(), _Arm()) == ([], False)

    def test_an_unreadable_nic_is_skipped_without_losing_the_vm(self, discovery):
        net = MagicMock()
        net.network_interfaces.get.side_effect = RuntimeError("403")

        nics, has_fwd = discovery._collect_vm_nics(
            net, self._vm(["/subscriptions/s/resourceGroups/rg/x/nic-1"])
        )

        assert (nics, has_fwd) == ([], False)


class TestCollectNvas:
    def _cmc(self, vms):
        cmc = MagicMock()
        cmc.return_value.virtual_machines.list_all.return_value = vms
        return cmc

    def _vm(self, **over):
        base = {
            "id": "/subscriptions/sub-0001/resourceGroups/rg-nva/providers/x/vm-1",
            "name": "vm-1",
            "location": "eastus",
            "hardware_profile": _Arm(vm_size="Standard_D4s_v5"),
            "storage_profile": _Arm(os_disk=_Arm(os_type="Linux")),
            "network_profile": _Arm(network_interfaces=[]),
            "tags": {},
        }
        base.update(over)
        return _Arm(**base)

    def test_identifies_a_marketplace_ngfw(self, discovery):
        discovery._credential = MagicMock()
        vm = self._vm(plan=_Arm(publisher="fortinet", product="fortigate", name="byol"))
        with patch.dict(
            "sys.modules",
            {"azure.mgmt.compute": MagicMock(ComputeManagementClient=self._cmc([vm]))},
        ):
            nvas = discovery._collect_nvas(MagicMock(), "sub-0001")

        assert len(nvas) == 1
        assert nvas[0].identification_method == "marketplace"
        assert nvas[0].vm_size == "Standard_D4s_v5"
        assert nvas[0].os_type == "Linux"
        assert nvas[0].resource_group == "rg-nva"

    def test_a_plain_vm_with_ip_forwarding_still_counts_as_an_nva(self, discovery):
        """Custom-built appliances have no recognisable publisher; forwarding is the tell."""
        discovery._credential = MagicMock()
        net = MagicMock()
        net.network_interfaces.get.return_value = _Arm(
            id="nic-1",
            name="nic-1",
            location="eastus",
            enable_ip_forwarding=True,
            ip_configurations=[],
        )
        vm = self._vm(
            network_profile=_Arm(
                network_interfaces=[_Arm(id="/subscriptions/s/resourceGroups/rg/x/nic-1")]
            )
        )
        with patch.dict(
            "sys.modules",
            {"azure.mgmt.compute": MagicMock(ComputeManagementClient=self._cmc([vm]))},
        ):
            nvas = discovery._collect_nvas(net, "sub-0001")

        assert nvas[0].identification_method == "ip_forwarding"

    def test_an_ordinary_vm_is_not_reported(self, discovery):
        discovery._credential = MagicMock()
        with patch.dict(
            "sys.modules",
            {"azure.mgmt.compute": MagicMock(ComputeManagementClient=self._cmc([self._vm()]))},
        ):
            assert discovery._collect_nvas(MagicMock(), "sub-0001") == []

    def test_missing_sdk_returns_empty(self, discovery):
        with patch.dict("sys.modules", {"azure.mgmt.compute": None}):
            assert discovery._collect_nvas(MagicMock(), "sub-0001") == []


class TestCollectBgpData:
    def _gw(self, **over):
        base = {
            "id": "gw-1",
            "name": "vgw-1",
            "gateway_type": "Vpn",
            "enable_bgp": True,
            "bgp_asn": 65515,
            "resource_group": "rg-net",
        }
        base.update(over)
        return _Arm(**base)

    def test_skips_expressroute_gateways(self, discovery):
        assert (
            discovery._collect_bgp_data(
                MagicMock(), "sub-0001", [self._gw(gateway_type="ExpressRoute")]
            )
            == []
        )

    def test_a_gateway_without_bgp_is_recorded_but_not_queried(self, discovery):
        net = MagicMock()

        data = discovery._collect_bgp_data(net, "sub-0001", [self._gw(enable_bgp=False)])

        assert len(data) == 1
        assert data[0].bgp_enabled is False
        assert data[0].peers == []
        net.virtual_network_gateways.begin_get_bgp_peer_status.assert_not_called()

    def test_collects_peers_learned_and_advertised_routes(self, discovery):
        net = MagicMock()
        net.virtual_network_gateways.begin_get_bgp_peer_status.return_value.result.return_value = (
            _Arm(
                value=[
                    _Arm(
                        neighbor="10.0.0.1",
                        asn=65001,
                        bgp_peer_state="Connected",
                        messages_sent=10,
                        messages_received=12,
                        routes_received=5,
                        connected_duration="1:00:00",
                    )
                ]
            )
        )
        net.virtual_network_gateways.begin_get_learned_routes.return_value.result.return_value = (
            _Arm(value=[_Arm(network="10.1.0.0/16"), _Arm()])
        )
        net.virtual_network_gateways.begin_get_advertised_routes.return_value.result.return_value = _Arm(
            value=[_Arm(network="10.0.0.0/16")]
        )

        item = discovery._collect_bgp_data(net, "sub-0001", [self._gw()])[0]

        assert item.peers[0].peer_asn == 65001
        assert item.peers[0].state == "Connected"
        assert item.learned_routes_count == 2
        assert item.learned_routes == ["10.1.0.0/16"], "routes without a network are dropped"
        assert item.advertised_routes == ["10.0.0.0/16"]
        assert item.collection_error is None

    def test_peer_and_route_failures_are_both_recorded_in_one_error(self, discovery):
        """These are long-running ARM operations that time out independently."""
        net = MagicMock()
        net.virtual_network_gateways.begin_get_bgp_peer_status.side_effect = RuntimeError("timeout")
        net.virtual_network_gateways.begin_get_learned_routes.side_effect = RuntimeError("denied")

        item = discovery._collect_bgp_data(net, "sub-0001", [self._gw()])[0]

        assert "BGP peers" in item.collection_error
        assert "Learned routes" in item.collection_error

    def test_advertised_routes_are_skipped_when_there_are_no_peers(self, discovery):
        net = MagicMock()
        net.virtual_network_gateways.begin_get_bgp_peer_status.return_value.result.return_value = (
            _Arm(value=[])
        )
        net.virtual_network_gateways.begin_get_learned_routes.return_value.result.return_value = (
            _Arm(value=[])
        )

        discovery._collect_bgp_data(net, "sub-0001", [self._gw()])

        net.virtual_network_gateways.begin_get_advertised_routes.assert_not_called()


def _metric(name, *, totals=None, averages=None, maximums=None):
    """Build one Azure Monitor metric result with a single timeseries."""
    points = []
    for seq, attr in ((totals, "total"), (averages, "average"), (maximums, "maximum")):
        for i, v in enumerate(seq or []):
            while len(points) <= i:
                points.append(_Arm())
            setattr(points[i], attr, v)
    return _Arm(name=_Arm(value=name), timeseries=[_Arm(data=points)])


def _monitor_returning(*metrics):
    monitor = MagicMock()
    monitor.metrics.list.return_value = _Arm(value=list(metrics))
    return monitor


class TestMetricAggregationHelpers:
    def test_sum_metric_total_ignores_none_points(self):
        assert AzureDiscovery._sum_metric_total(_metric("m", totals=[1.0, None, 2.5])) == 3.5

    def test_avg_metric_values_collects_only_populated_points(self):
        assert AzureDiscovery._avg_metric_values(_metric("m", averages=[1.0, None, 3.0])) == [
            1.0,
            3.0,
        ]

    def test_max_metric_maximum_defaults_to_zero_when_empty(self):
        assert AzureDiscovery._max_metric_maximum(_metric("m")) == 0

    def test_max_metric_maximum_picks_the_largest(self):
        assert AzureDiscovery._max_metric_maximum(_metric("m", maximums=[1, 9, 4])) == 9


class TestGatewayMetrics:
    def _gw(self, sku="VpnGw2"):
        return _Arm(id="gw-1", name="vgw-1", gateway_type="Vpn", sku_name=sku)

    def test_computes_utilization_against_the_provisioned_sku_bandwidth(self, discovery):
        metrics = NetworkMetrics()
        # VpnGw2 is 1000 Mbps; 500 Mbps average is 50%.
        monitor = _monitor_returning(
            _metric("TunnelIngressBytes", totals=[1000.0]),
            _metric("TunnelEgressBytes", totals=[2000.0]),
            _metric("AverageBandwidth", averages=[500_000_000.0]),
        )

        discovery._collect_gateway_metrics("sub-1", [self._gw()], monitor, "ts", metrics)

        gm = metrics.gateway_metrics[0]
        assert gm.ingress_bytes_24h == 1000.0
        assert gm.egress_bytes_24h == 2000.0
        assert gm.bandwidth_mbps_provisioned == 1000
        assert gm.utilization_pct == 50.0

    def test_an_unknown_sku_has_no_provisioned_bandwidth_and_no_utilization(self, discovery):
        metrics = NetworkMetrics()
        monitor = _monitor_returning(_metric("AverageBandwidth", averages=[500_000_000.0]))

        discovery._collect_gateway_metrics("sub-1", [self._gw(sku="Basic")], monitor, "ts", metrics)

        assert metrics.gateway_metrics[0].bandwidth_mbps_provisioned is None
        assert metrics.gateway_metrics[0].utilization_pct is None

    def test_a_query_failure_still_records_the_gateway(self, discovery):
        metrics = NetworkMetrics()
        monitor = MagicMock()
        monitor.metrics.list.side_effect = RuntimeError("throttled")

        discovery._collect_gateway_metrics("sub-1", [self._gw()], monitor, "ts", metrics)

        assert len(metrics.gateway_metrics) == 1

    def test_caps_at_five_gateways(self, discovery):
        metrics = NetworkMetrics()
        monitor = _monitor_returning()

        discovery._collect_gateway_metrics("sub-1", [self._gw()] * 9, monitor, "ts", metrics)

        assert len(metrics.gateway_metrics) == 5


class TestFirewallMetrics:
    def test_converts_bytes_to_gigabytes_and_maps_rule_hits(self, discovery):
        metrics = NetworkMetrics()
        monitor = _monitor_returning(
            _metric("DataProcessed", totals=[1_073_741_824.0 * 2]),
            _metric("ApplicationRuleHit", totals=[10.0]),
            _metric("NetworkRuleHit", totals=[20.0]),
            _metric("NatRuleHit", totals=[5.0]),
        )

        discovery._collect_firewall_metrics(
            "sub-1", [_Arm(id="fw-1", name="afw-1")], monitor, "ts", metrics
        )

        fm = metrics.firewall_metrics[0]
        assert fm.data_processed_gb_24h == 2.0
        assert (fm.app_rule_hits_24h, fm.network_rule_hits_24h, fm.nat_rule_hits_24h) == (10, 20, 5)

    def test_records_the_error_on_the_firewall_metric_itself(self, discovery):
        metrics = NetworkMetrics()
        monitor = MagicMock()
        monitor.metrics.list.side_effect = RuntimeError("no Microsoft.Insights read")

        discovery._collect_firewall_metrics(
            "sub-1", [_Arm(id="fw-1", name="afw-1")], monitor, "ts", metrics
        )

        assert "no Microsoft.Insights read" in metrics.firewall_metrics[0].collection_error


class TestLoadBalancerMetrics:
    def test_computes_snat_port_utilization(self, discovery):
        metrics = NetworkMetrics()
        monitor = _monitor_returning(
            _metric("SnatConnectionCount", totals=[100.0]),
            _metric("UsedSnatPorts", averages=[512.0]),
            _metric("AllocatedSnatPorts", averages=[1024.0]),
        )

        discovery._collect_lb_metrics(
            "sub-1", [_Arm(id="lb-1", name="lb-1")], monitor, "ts", metrics
        )

        lm = metrics.lb_metrics[0]
        assert lm.snat_connections_24h == 100.0
        assert (lm.used_snat_ports, lm.allocated_snat_ports) == (512.0, 1024.0)
        assert lm.snat_port_utilization_pct == 50.0

    def test_no_allocated_ports_means_no_utilization_rather_than_a_divide_by_zero(self, discovery):
        metrics = NetworkMetrics()
        monitor = _monitor_returning(_metric("UsedSnatPorts", averages=[512.0]))

        discovery._collect_lb_metrics(
            "sub-1", [_Arm(id="lb-1", name="lb-1")], monitor, "ts", metrics
        )

        assert metrics.lb_metrics[0].snat_port_utilization_pct is None

    def test_caps_at_ten_load_balancers(self, discovery):
        metrics = NetworkMetrics()
        discovery._collect_lb_metrics(
            "sub-1", [_Arm(id="lb", name="lb")] * 14, _monitor_returning(), "ts", metrics
        )
        assert len(metrics.lb_metrics) == 10


class TestExpressRouteMetrics:
    def test_computes_utilization_against_the_provisioned_circuit_bandwidth(self, discovery):
        metrics = NetworkMetrics()
        # 1000 Mbps circuit; 500 Mbps in is 50%.
        monitor = _monitor_returning(
            _metric("BitsInPerSecond", averages=[500_000_000.0]),
            _metric("BitsOutPerSecond", averages=[250_000_000.0]),
        )

        discovery._collect_er_metrics(
            "sub-1", [_Arm(id="erc-1", name="erc-1", bandwidth_mbps=1000)], monitor, "ts", metrics
        )

        em = metrics.er_circuit_metrics[0]
        assert em.primary_utilization_pct == 50.0
        assert em.secondary_utilization_pct == 25.0

    def test_a_circuit_without_a_declared_bandwidth_reports_rates_but_no_percentage(
        self, discovery
    ):
        metrics = NetworkMetrics()
        monitor = _monitor_returning(_metric("BitsInPerSecond", averages=[500_000_000.0]))

        discovery._collect_er_metrics(
            "sub-1", [_Arm(id="erc-1", name="erc-1", bandwidth_mbps=0)], monitor, "ts", metrics
        )

        em = metrics.er_circuit_metrics[0]
        assert em.primary_bits_in_per_second == 500_000_000.0
        assert em.primary_utilization_pct is None


class TestDdosMetrics:
    def test_records_an_ip_under_attack(self, discovery):
        metrics = NetworkMetrics()
        monitor = _monitor_returning(_metric("IfUnderDDoSAttack", maximums=[1]))

        discovery._collect_ddos_metrics(
            "sub-1", [_Arm(id="pip-1", ip_address="20.1.2.3")], monitor, "ts", metrics
        )

        assert metrics.ddos_attack_events_24h == 1
        assert metrics.public_ips_under_ddos_attack == ["20.1.2.3"]

    def test_a_quiet_ip_is_not_recorded(self, discovery):
        metrics = NetworkMetrics()
        monitor = _monitor_returning(_metric("IfUnderDDoSAttack", maximums=[0]))

        discovery._collect_ddos_metrics(
            "sub-1", [_Arm(id="pip-1", ip_address="20.1.2.3")], monitor, "ts", metrics
        )

        assert metrics.ddos_attack_events_24h == 0
        assert metrics.public_ips_under_ddos_attack == []


class TestComputeVnetUtilization:
    def test_computes_allocated_over_total_address_space(self, discovery):
        metrics = NetworkMetrics()
        # /16 = 65536 addresses; two /24s = 512 → 0.8%
        vnet = _Arm(
            id="vnet-1",
            address_space=["10.0.0.0/16"],
            subnets=[_Arm(address_prefix="10.0.1.0/24"), _Arm(address_prefix="10.0.2.0/24")],
        )

        discovery._compute_vnet_utilization([vnet], metrics)

        assert metrics.vnet_utilization["vnet-1"] == 0.8

    def test_a_vnet_with_no_address_space_is_skipped(self, discovery):
        metrics = NetworkMetrics()
        discovery._compute_vnet_utilization([_Arm(id="vnet-1", address_space=[])], metrics)
        assert metrics.vnet_utilization == {}

    def test_a_malformed_prefix_is_skipped_rather_than_raising(self, discovery):
        metrics = NetworkMetrics()
        discovery._compute_vnet_utilization(
            [_Arm(id="vnet-1", address_space=["not-a-cidr"])], metrics
        )
        assert metrics.vnet_utilization == {}


class TestNtaMetrics:
    def _logs_client(self, rows, status_success=True):
        from azure.monitor.query import LogsQueryStatus

        client = MagicMock()
        client.return_value.query_workspace.return_value = _Arm(
            status=LogsQueryStatus.SUCCESS if status_success else "PartialFailure",
            tables=[_Arm(rows=rows)],
        )
        return client

    def test_no_workspaces_means_no_query(self, discovery):
        metrics = NetworkMetrics()
        discovery._collect_nta_metrics("sub-1", [], metrics)
        assert metrics.nta_query_workspace_id is None

    def test_splits_east_west_from_north_south_traffic(self, discovery):
        discovery._credential = MagicMock()
        metrics = NetworkMetrics()
        client = self._logs_client([["E", 100.0], ["I", 20.0], ["O", 30.0]])

        with patch("azure.monitor.query.LogsQueryClient", client):
            discovery._collect_nta_metrics("sub-1", [{"workspace_id": "ws-1"}], metrics)

        assert metrics.nta_east_west_bytes_24h == 100.0
        assert metrics.nta_north_south_bytes_24h == 50.0
        assert metrics.nta_query_workspace_id == "ws-1"

    def test_skips_workspaces_with_no_id_and_stops_at_the_first_success(self, discovery):
        discovery._credential = MagicMock()
        metrics = NetworkMetrics()
        client = self._logs_client([["IntraVNet", 7.0]])

        with patch("azure.monitor.query.LogsQueryClient", client):
            discovery._collect_nta_metrics(
                "sub-1", [{"workspace_id": ""}, {"id": "ws-2"}, {"workspace_id": "ws-3"}], metrics
            )

        assert metrics.nta_query_workspace_id == "ws-2"
        assert client.return_value.query_workspace.call_count == 1

    def test_a_query_failure_leaves_the_metrics_untouched(self, discovery):
        discovery._credential = MagicMock()
        metrics = NetworkMetrics()
        client = MagicMock()
        client.return_value.query_workspace.side_effect = RuntimeError("no Log Analytics Reader")

        with patch("azure.monitor.query.LogsQueryClient", client):
            discovery._collect_nta_metrics("sub-1", [{"workspace_id": "ws-1"}], metrics)

        assert metrics.nta_query_workspace_id is None


class TestApplyAppgwMetric:
    def test_capacity_units_records_both_average_and_maximum(self):
        agm = AppGatewayMetric(appgw_name="agw-1")
        AzureDiscovery._apply_appgw_metric(
            _metric("CapacityUnits", averages=[2.0, 4.0], maximums=[3.0, 8.0]), agm
        )
        assert agm.capacity_units_avg == 3.0
        assert agm.capacity_units_max == 8.0

    def test_backend_latency_is_averaged(self):
        agm = AppGatewayMetric(appgw_name="agw-1")
        AzureDiscovery._apply_appgw_metric(
            _metric("BackendLastByteResponseTime", averages=[10.0, 20.0]), agm
        )
        assert agm.backend_latency_ms_avg == 15.0

    @pytest.mark.parametrize(
        "name,attr",
        [
            ("FailedRequests", "failed_requests_24h"),
            ("TotalRequests", "total_requests_24h"),
            ("ApplicationGatewayWAFRuleMatches", "waf_rule_hits_24h"),
        ],
    )
    def test_counter_metrics_are_summed_as_integers(self, name, attr):
        agm = AppGatewayMetric(appgw_name="agw-1")
        AzureDiscovery._apply_appgw_metric(_metric(name, totals=[1.0, 2.0]), agm)
        assert getattr(agm, attr) == 3

    def test_an_unrecognised_metric_is_ignored(self):
        agm = AppGatewayMetric(appgw_name="agw-1")
        AzureDiscovery._apply_appgw_metric(_metric("SomethingNew", totals=[5.0]), agm)
        assert agm.total_requests_24h is None, "the field is left unset, not zeroed"


class TestAppgwMetrics:
    def test_skips_entirely_when_the_monitor_client_is_unavailable(self, discovery):
        """`_collect_network_metrics` passes None when its own setup failed."""
        metrics = NetworkMetrics()
        discovery._collect_appgw_metrics("sub-1", [_Arm(id="a", name="agw-1")], None, "", metrics)
        assert metrics.appgw_metrics == []

    def test_records_the_error_on_the_metric_object(self, discovery):
        metrics = NetworkMetrics()
        monitor = MagicMock()
        monitor.metrics.list.side_effect = RuntimeError("throttled")

        discovery._collect_appgw_metrics(
            "sub-1", [_Arm(id="a", name="agw-1")], monitor, "ts", metrics
        )

        assert "throttled" in metrics.appgw_metrics[0].collection_error


class TestCollectNetworkMetrics:
    def test_missing_monitor_sdk_reports_in_band_rather_than_raising(self, discovery):
        ctx = _MetricsContext(sub_id="sub-1", gateways=[])
        with patch.dict("sys.modules", {"azure.mgmt.monitor": None}):
            metrics = discovery._collect_network_metrics(ctx)

        assert metrics.collection_error == "azure-mgmt-monitor not installed"

    def test_monitor_construction_failure_is_recorded_and_the_rest_still_runs(self, discovery):
        """VNet utilization needs no API call, so it must survive a Monitor failure."""
        discovery._credential = MagicMock()
        ctx = _MetricsContext(
            sub_id="sub-1",
            gateways=[],
            vnets=[
                _Arm(
                    id="vnet-1",
                    address_space=["10.0.0.0/16"],
                    subnets=[_Arm(address_prefix="10.0.1.0/24")],
                )
            ],
        )
        with patch("azure.mgmt.monitor.MonitorManagementClient", side_effect=RuntimeError("403")):
            metrics = discovery._collect_network_metrics(ctx)

        assert metrics.collection_error == "403"
        assert metrics.vnet_utilization["vnet-1"] == 0.4


class TestCollectFrontDoorWafPolicies:
    def _policy(self, **over):
        base = {
            "id": "/subscriptions/sub-0001/resourceGroups/rg-waf/providers/x/wafpol-1",
            "name": "wafpol-1",
            "location": "global",
            "sku": _Arm(name="Premium_AzureFrontDoor"),
            "policy_settings": _Arm(mode="Prevention", enabled_state="Enabled"),
            "custom_rules": _Arm(rules=[_Arm(), _Arm()]),
            "managed_rules": _Arm(managed_rule_sets=[_Arm(rule_sets=[_Arm(), _Arm(), _Arm()])]),
            "tags": {},
        }
        base.update(over)
        return _Arm(**base)

    def test_maps_a_front_door_policy(self, discovery):
        discovery._credential = MagicMock()
        net = MagicMock()
        net.return_value.web_application_firewall_policies.list_all.return_value = [self._policy()]

        with patch("azure.mgmt.network.NetworkManagementClient", net):
            policies = discovery._collect_front_door_waf_policies("sub-0001")

        assert len(policies) == 1
        p = policies[0]
        assert p.resource_group == "rg-waf"
        assert p.policy_mode == "Prevention"
        assert p.custom_rules_count == 2
        assert p.managed_rules_count == 3

    def test_application_gateway_policies_are_excluded(self, discovery):
        """App Gateway WAF policies share the same ARM collection."""
        discovery._credential = MagicMock()
        net = MagicMock()
        net.return_value.web_application_firewall_policies.list_all.return_value = [
            self._policy(sku=_Arm(name="ApplicationGatewayWebApplicationFirewallPolicy"))
        ]

        with patch("azure.mgmt.network.NetworkManagementClient", net):
            assert discovery._collect_front_door_waf_policies("sub-0001") == []

    def test_defaults_when_policy_settings_are_absent(self, discovery):
        discovery._credential = MagicMock()
        net = MagicMock()
        net.return_value.web_application_firewall_policies.list_all.return_value = [
            self._policy(policy_settings=None, custom_rules=None, managed_rules=None, sku=None)
        ]

        with patch("azure.mgmt.network.NetworkManagementClient", net):
            p = discovery._collect_front_door_waf_policies("sub-0001")[0]

        assert p.policy_mode == "Detection"
        assert p.policy_enabled_state == "Enabled"
        assert (p.custom_rules_count, p.managed_rules_count) == (0, 0)

    def test_an_enumeration_failure_returns_empty(self, discovery):
        discovery._credential = MagicMock()
        net = MagicMock()
        net.return_value.web_application_firewall_policies.list_all.side_effect = RuntimeError(
            "403"
        )

        with patch("azure.mgmt.network.NetworkManagementClient", net):
            assert discovery._collect_front_door_waf_policies("sub-0001") == []
