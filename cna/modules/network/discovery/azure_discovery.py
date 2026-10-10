"""Azure Network Discovery — Phase C core.

Discovers all network topology resources across every subscription in an
Azure tenant using DefaultAzureCredential (or service principal).

Design principles:
  - ARM REST API + Azure Resource Graph for efficient cross-subscription queries.
  - Every subscription access failure is logged with reason — never silent.
  - Pagination uses skipToken for ARM list operations.
  - Management Group hierarchy discovered from tenant root.
  - --resume skips subscriptions with existing checkpoints.

API coverage (v1.2.0):
  ARM: VNets, Subnets (expanded), Route Tables (full rules), NSGs (full rules
       + flow log state), VNet Peerings, VPN/VNet Gateways (BGP + connections),
       Azure Firewalls, App Gateways (WAF config), vWANs, vHubs,
       Private DNS Zones, ExpressRoute Circuits,
       Load Balancers (rules + probes), Public IPs (association info),
       Private Endpoints (DNS zone groups), NAT Gateways, Bastion Hosts
  Management API: Management Group tree from tenant root

API coverage additions (v1.3.0):
  ARM: Route Servers (virtual hubs with kind=RouteServer + BGP connections)
  Monitor API: metric alert + activity log alert counts,
       diagnostic-settings coverage for Gateways / AppGWs / Load Balancers
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from azure.core.exceptions import HttpResponseError

from cna.core.exceptions import CNAAuthError
from cna.core.persistence import EngagementStore
from cna.core.throttle import with_retry
from cna.core.topology_schema import (
    AppGatewayMetric,
    ApplicationGateway,
    AzureBastionHost,
    AzureFirewall,
    AzureGatewayConnection,
    AzureLBFrontendIP,
    AzureLBProbe,
    AzureLBRule,
    AzureLoadBalancer,
    AzureNatGateway,
    AzureNIC,
    AzureNSG,
    AzureNVA,
    AzurePrivateEndpoint,
    AzurePrivateEndpointConnection,
    AzurePublicIP,
    AzureRouteEntry,
    AzureRouteServer,
    AzureRouteServerBgpConnection,
    AzureRouteTable,
    AzureSubnet,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVHub,
    AzureVirtualNetworkGateway,
    AzureVWan,
    BgpPeerStatus,
    DefenderAssessment,
    ERCircuitMetric,
    ExpressRouteCircuit,
    FirewallMetric,
    FrontDoorWAFPolicy,
    GatewayBgpData,
    GatewayMetric,
    LoadBalancerMetric,
    LogAnalyticsWorkspace,
    ManagementGroup,
    NetworkMetrics,
    NetworkWatcherInfo,
    NSGSecurityRule,
    ObservabilityData,
    PrivateDnsZone,
    SubnetType,
    VNet,
    VNetPeering,
)

logger = logging.getLogger("cna.discovery.azure")


@dataclass
class AzureDiscoveryOptions:
    tenant_id: str
    subscription_ids: list[str] = field(default_factory=list)  # empty = all
    resume: bool = False
    use_resource_graph: bool = True  # faster cross-sub queries
    client_id: str | None = None  # for service principal auth
    client_secret: str | None = None  # never logged, in-memory only


_RG_PARTS_INDEX = 4  # fallback index for resource group in a split ARM resource ID
_NVA_DISPLAY_LIMIT = 5  # max NVA names shown inline in progress messages


def _rg_from_id(resource_id: str) -> str:
    """Extract resource group name from an Azure resource ID."""
    parts = resource_id.split("/")
    try:
        idx = next(i for i, p in enumerate(parts) if p.lower() == "resourcegroups")
        return parts[idx + 1]
    except (StopIteration, IndexError):
        return parts[_RG_PARTS_INDEX] if len(parts) > _RG_PARTS_INDEX else ""


def _sub_from_id(resource_id: str) -> str:
    """Extract subscription ID from an Azure resource ID."""
    parts = resource_id.split("/")
    try:
        idx = next(i for i, p in enumerate(parts) if p.lower() == "subscriptions")
        return parts[idx + 1]
    except (StopIteration, IndexError):
        return ""


def _safe_list(iterable):
    """Iterate safely — return [] on any exception."""
    try:
        return list(iterable)
    except Exception as exc:
        logger.debug("Safe-list failed: %s", exc)
        return []


# Well-known subnet names that are always infrastructure-owned (never workload PUBLIC)
_INFRA_SUBNET_NAMES = {
    "gatewaysubnet",
    "azurefirewallsubnet",
    "azurefirewallmanagementsubnet",
    "azurebastionsubnet",
    "routeservicesubnet",
}


def _classify_subnet(
    name: str,
    nsg_id: str | None,
    route_table_id: str | None,
    delegation: str | None,
    default_outbound_access: bool,
) -> SubnetType:
    """Classify a subnet based on its control-plane configuration.

    Rules (in priority order):
    - Well-known infra subnet names → PRIVATE (special-purpose, never workload-PUBLIC)
    - Delegated to a PaaS service → PRIVATE
    - Has NSG AND route table → ISOLATED (both segmentation layers present)
    - Has NSG OR route table → PRIVATE
    - No NSG, no route table, default outbound enabled → PUBLIC (uncontrolled)
    - Anything else → UNKNOWN
    """
    if name.lower() in _INFRA_SUBNET_NAMES or delegation:
        return SubnetType.PRIVATE
    has_nsg, has_udr = bool(nsg_id), bool(route_table_id)
    if has_nsg and has_udr:
        return SubnetType.ISOLATED
    if has_nsg or has_udr:
        return SubnetType.PRIVATE
    return SubnetType.PUBLIC if default_outbound_access else SubnetType.UNKNOWN


@dataclass
class _ObservabilityContext:
    net: object
    sub_id: str
    nsg_count: int
    firewalls: list | None = None
    bastion_hosts: list | None = None
    gateways: list | None = None
    appgws: list | None = None
    load_balancers: list | None = None


@dataclass
class _MetricsContext:
    sub_id: str
    gateways: list
    firewalls: list | None = None
    load_balancers: list | None = None
    vnets: list | None = None
    er_circuits: list | None = None
    public_ips: list | None = None
    la_workspaces: list | None = None
    appgws: list | None = None


class AzureDiscovery:
    """Orchestrates Azure network discovery across all subscriptions."""

    def __init__(
        self,
        store: EngagementStore,
        options: AzureDiscoveryOptions,
        progress_callback: Callable[[str], None] | None = None,
    ):
        self.store = store
        self.opts = options
        self._progress = progress_callback or (lambda msg: None)
        self._credential = None
        self._sub_client = None

    @property
    def _cred(self):
        """The ARM credential, established by ``_init_credentials()``.

        Both fields start as ``None`` and are only populated once credentials
        are initialised, so every consumer below was dereferencing a possibly
        ``None`` value. Narrow it in one place and fail with a named error
        rather than ``AttributeError`` on ``NoneType`` (TODO.md T-410).
        """
        if self._credential is None:
            raise RuntimeError(
                "Azure credential not initialised — call validate_access() or "
                "_init_credentials() first."
            )
        return self._credential

    @property
    def _subs(self):
        """The subscription client, established by ``_init_credentials()``."""
        if self._sub_client is None:
            raise RuntimeError(
                "Azure subscription client not initialised — call "
                "validate_access() or _init_credentials() first."
            )
        return self._sub_client

    # ------------------------------------------------------------------ auth

    def _init_credentials(self) -> None:
        """Initialize Azure credentials using DefaultAzureCredential chain."""
        try:
            from azure.identity import ClientSecretCredential, DefaultAzureCredential
            from azure.mgmt.subscription import SubscriptionClient

            if self.opts.client_id and self.opts.client_secret:
                logger.info("Using service principal credentials")
                self._credential = ClientSecretCredential(
                    tenant_id=self.opts.tenant_id,
                    client_id=self.opts.client_id,
                    client_secret=self.opts.client_secret,
                )
            else:
                logger.info("Using DefaultAzureCredential chain")
                self._credential = DefaultAzureCredential()

            self._sub_client = SubscriptionClient(self._credential)
        except ImportError as e:
            raise CNAAuthError(
                "azure-identity and azure-mgmt-subscription are required. "
                "Run: pip install azure-identity azure-mgmt-subscription "
                "azure-mgmt-network azure-mgmt-resource"
            ) from e

    def validate_access(self) -> None:
        """Pre-flight: verify SP credentials and subscription access before discovery.

        Emits results via progress_callback so they appear in the UI progress log.
        Raises on hard auth failures; logs warnings for partial access issues.
        """
        self._init_credentials()

        # 1. Verify the SP can obtain an ARM token.
        self._progress("Pre-check: verifying SP token…")
        try:
            token = self._cred.get_token("https://management.azure.com/.default")
            self._progress(f"Pre-check: token OK (expires ~{token.expires_on})")
        except Exception as e:
            raise CNAAuthError(f"SP authentication failed — cannot obtain ARM token: {e}") from e

        # 2. For each requested subscription, call subscriptions.get() directly.
        #    This tells us: is the sub accessible? What state is it in?
        if not self.opts.subscription_ids:
            self._progress("Pre-check: no subscription filter — will list all accessible.")
            return

        for sub_id in self.opts.subscription_ids:
            try:
                sub = self._subs.subscriptions.get(sub_id)
                self._progress(
                    f"Pre-check: subscription {sub_id} ({sub.display_name}) — state: {sub.state}"
                )
                if sub.state not in self._ACTIVE_SUB_STATES:
                    self._progress(
                        f"  WARNING: state '{sub.state}' may limit discoverability. "
                        f"Expected: Enabled, Warned, or PastDue."
                    )
            except Exception as e:
                self._progress(
                    f"Pre-check: subscription {sub_id} NOT accessible — {e}. "
                    f"Verify SP has Reader role on this subscription."
                )

    # ------------------------------------------------------------------ subscriptions

    # States where a subscription is still readable (not hard-deleted/disabled).
    # "Warned" is common for sandbox/trial subscriptions with a payment warning —
    # the subscription is fully accessible for read operations.
    _ACTIVE_SUB_STATES = {"Enabled", "Warned", "PastDue"}

    def _list_subscriptions(self) -> list[dict]:
        """List all accessible subscriptions in the tenant.

        Includes Enabled, Warned, and PastDue states.  Only Deleted and
        Disabled subscriptions are excluded — they are genuinely inaccessible.
        """
        subs = []
        skipped = []
        for sub in with_retry()(self._subs.subscriptions.list)():
            if sub.state not in self._ACTIVE_SUB_STATES:
                logger.info(
                    "Skipping %s subscription %s (%s)",
                    sub.state,
                    sub.subscription_id,
                    sub.display_name,
                )
                skipped.append(f"{sub.display_name} [{sub.state}]")
                continue
            subs.append(
                {
                    "id": sub.subscription_id,
                    "name": sub.display_name,
                    "tenant_id": self.opts.tenant_id,
                }
            )
        self._progress(
            f"SP list(): {len(subs)} accessible subscription(s)"
            + (f"; skipped {len(skipped)}: {', '.join(skipped)}" if skipped else "")
        )
        return subs

    def _get_subscription_direct(self, subscription_id: str) -> dict | None:
        """Fetch a single subscription by ID — fallback when list() misses it."""
        try:
            sub = with_retry()(self._subs.subscriptions.get)(subscription_id)
            if sub and sub.subscription_id:
                return {
                    "id": sub.subscription_id,
                    "name": sub.display_name or subscription_id,
                    "tenant_id": self.opts.tenant_id,
                }
        except Exception as e:
            logger.warning("Direct get failed for subscription %s: %s", subscription_id, e)
        return None

    # ------------------------------------------------------------------ management groups

    def _collect_management_groups(self) -> list[ManagementGroup]:
        """Discover the full Management Group hierarchy from tenant root."""
        try:
            from azure.mgmt.managementgroups import ManagementGroupsAPI
        except ImportError:
            logger.warning(
                "azure-mgmt-managementgroups not installed. Skipping MG hierarchy discovery."
            )
            return []

        mg_client = ManagementGroupsAPI(self._cred)
        mg_list = []
        try:
            for mg in mg_client.management_groups.list():
                # The SDK types every name as str | None; a nameless group
                # cannot be fetched or modelled, so skip it.
                if not mg.name:
                    continue
                detail = mg_client.management_groups.get(mg.name, expand="children", recurse=False)
                child_mg_ids: list[str] = []
                sub_ids: list[str] = []
                for child in detail.children or []:
                    if not child.name:
                        continue
                    if "/managementGroups/" in (child.id or ""):
                        child_mg_ids.append(child.name)
                    elif "/subscriptions/" in (child.id or ""):
                        sub_ids.append(child.name)

                mg_list.append(
                    ManagementGroup(
                        id=mg.name,
                        name=mg.name,
                        display_name=mg.display_name or mg.name,
                        parent_id=None,
                        subscription_ids=sub_ids,
                        child_mg_ids=child_mg_ids,
                    )
                )
        except Exception as e:
            logger.warning("Management group enumeration failed: %s", e)
        return mg_list

    # ------------------------------------------------------------------ per-subscription

    def _discover_subscription(self, sub_id: str, sub_name: str) -> AzureSubscriptionTopology:
        """Run full network discovery for one Azure subscription.

        Each collector runs independently — a failure in one (e.g. missing
        permission for a specific resource type) is logged but does not block
        the rest of the subscription from being discovered.
        """
        from azure.mgmt.network import NetworkManagementClient

        # azure-mgmt-resource >= 24 split into per-service sub-packages and the
        # top-level re-export was removed; pyproject pins >= 26.
        from azure.mgmt.resource.resources import ResourceManagementClient

        topo = AzureSubscriptionTopology(
            subscription_id=sub_id,
            subscription_name=sub_name,
            tenant_id=self.opts.tenant_id,
        )

        errors: list[str] = []

        def _run(attr: str, collector, *args):
            """Run one collector; on failure log, emit progress, and record the error."""
            try:
                setattr(topo, attr, collector(*args))
            except HttpResponseError as e:
                msg = f"{attr}: HTTP {e.status_code} — {e.message}"
                logger.warning("[%s] %s", sub_id, msg)
                self._progress(f"[{sub_name}] WARNING — {msg}")
                errors.append(msg)
            except Exception as e:
                msg = f"{attr}: {e}"
                logger.warning("[%s] %s", sub_id, msg)
                self._progress(f"[{sub_name}] WARNING — {msg}")
                errors.append(msg)

        try:
            net = NetworkManagementClient(self._cred, sub_id)
            rmc = ResourceManagementClient(self._cred, sub_id)
            rg_names = [rg.name for rg in _safe_list(rmc.resource_groups.list()) if rg.name]
        except Exception as e:
            topo.discovery_blocked = True
            topo.block_reason = str(e)
            return topo

        # Order matters: collect flat resources first so VNets can ref them
        _run("public_ips", self._collect_public_ips, net, sub_id)
        _run("nsgs", self._collect_nsgs, net, sub_id)
        _run("route_tables", self._collect_route_tables, net, sub_id)
        _run("nat_gateways", self._collect_nat_gateways, net, sub_id)
        _run("vnets", self._collect_vnets, net, sub_id)
        _run("virtual_wans", self._collect_vwans, net, sub_id)
        _run("route_servers", self._collect_route_servers, net, sub_id)
        _run("firewalls", self._collect_firewalls, net, sub_id)
        _run("application_gateways", self._collect_appgws, net, sub_id)
        _run("load_balancers", self._collect_load_balancers, net, sub_id)
        _run("virtual_network_gateways", self._collect_vnet_gateways, net, sub_id, rg_names)
        _run("private_endpoints", self._collect_private_endpoints, net, sub_id)
        _run("bastion_hosts", self._collect_bastion_hosts, net, sub_id)
        _run("private_dns_zones", self._collect_private_dns, sub_id)
        _run("express_route_circuits", self._collect_er_circuits, net, sub_id)

        # Diagnostic summary after Phase 1 — makes undercount visible in the progress log
        self._progress(
            f"[{sub_name}] Phase 1 complete: "
            f"{len(topo.vnets)} VNet(s), "
            f"{sum(len(v.subnets) for v in topo.vnets)} subnet(s), "
            f"{len(topo.nsgs)} NSG(s), "
            f"{len(topo.virtual_network_gateways)} gateway(s), "
            f"{len(topo.firewalls)} firewall(s)"
            + (f" | {len(errors)} collector error(s)" if errors else "")
        )

        # ── Phase 2: Extended assessment data ─────────────────────────────────
        self._run_phase2_collectors(topo, net, sub_id, sub_name)

        if errors:
            topo.block_reason = "; ".join(errors)
            # Only mark fully blocked if every collector failed (nothing discovered)
            all_empty = (
                not topo.vnets and not topo.nsgs and not topo.public_ips and not topo.load_balancers
            )
            if all_empty:
                topo.discovery_blocked = True

        return topo

    def _run_phase2_collectors(self, topo, net, sub_id: str, sub_name: str) -> None:
        """Run Phase 2 extended assessment collectors for one subscription."""
        self._run_nva_scan(topo, net, sub_id, sub_name)
        self._run_bgp_scan(topo, net, sub_id, sub_name)
        self._run_observability_scan(topo, net, sub_id, sub_name)
        self._run_metrics_scan(topo, sub_id, sub_name)
        self._run_waf_scan(topo, sub_id, sub_name)

    def _run_nva_scan(self, topo, net, sub_id: str, sub_name: str) -> None:
        self._progress(f"[{sub_name}] Scanning for NVAs / NGFWs…")
        try:
            topo.nvas = self._collect_nvas(net, sub_id)
            if topo.nvas:
                names = ", ".join(n.name for n in topo.nvas[:_NVA_DISPLAY_LIMIT])
                extra = (
                    f" (+{len(topo.nvas) - _NVA_DISPLAY_LIMIT} more)"
                    if len(topo.nvas) > _NVA_DISPLAY_LIMIT
                    else ""
                )
                self._progress(f"[{sub_name}] NVAs found: {len(topo.nvas)} — {names}{extra}")
            else:
                self._progress(f"[{sub_name}] No NVAs / NGFWs detected")
        except Exception as e:
            self._progress(f"[{sub_name}] NVA scan skipped: {e}")

    def _run_bgp_scan(self, topo, net, sub_id: str, sub_name: str) -> None:
        self._progress(f"[{sub_name}] Querying BGP peer status…")
        try:
            topo.bgp_data = self._collect_bgp_data(net, sub_id, topo.virtual_network_gateways)
        except Exception as e:
            self._progress(f"[{sub_name}] BGP data skipped: {e}")

    def _run_observability_scan(self, topo, net, sub_id: str, sub_name: str) -> None:
        self._progress(f"[{sub_name}] Collecting observability data…")
        try:
            obs_ctx = _ObservabilityContext(
                net=net,
                sub_id=sub_id,
                nsg_count=len(topo.nsgs),
                firewalls=topo.firewalls,
                bastion_hosts=topo.bastion_hosts,
                gateways=topo.virtual_network_gateways,
                appgws=topo.application_gateways,
                load_balancers=topo.load_balancers,
            )
            topo.observability = self._collect_observability(obs_ctx)
            obs = topo.observability
            self._progress(
                f"[{sub_name}] Observability: "
                f"{len(obs.network_watchers)} Network Watcher region(s), "
                f"{len(obs.log_analytics_workspaces)} Log Analytics "
                f"workspace(s), {obs.nsg_flow_logs_enabled}/"
                f"{obs.nsg_flow_logs_total} NSG flow logs enabled"
            )
        except Exception as e:
            self._progress(f"[{sub_name}] Observability data skipped: {e}")

    def _run_metrics_scan(self, topo, sub_id: str, sub_name: str) -> None:
        self._progress(f"[{sub_name}] Collecting network metrics (last 24 h)…")
        try:
            metrics_ctx = _MetricsContext(
                sub_id=sub_id,
                gateways=topo.virtual_network_gateways,
                firewalls=topo.firewalls,
                load_balancers=topo.load_balancers,
                vnets=topo.vnets,
                er_circuits=topo.express_route_circuits,
                public_ips=topo.public_ips,
                la_workspaces=(
                    topo.observability.log_analytics_workspaces if topo.observability else None
                ),
                appgws=topo.application_gateways,
            )
            topo.network_metrics = self._collect_network_metrics(metrics_ctx)
            if topo.network_metrics.collection_error:
                self._progress(f"[{sub_name}] Metrics: {topo.network_metrics.collection_error}")
            else:
                gw_ct = len(topo.network_metrics.gateway_metrics)
                fw_ct = len(topo.network_metrics.firewall_metrics)
                lb_ct = len(topo.network_metrics.lb_metrics)
                vnet_ct = len(topo.network_metrics.vnet_utilization)
                self._progress(
                    f"[{sub_name}] Metrics collected: "
                    f"{gw_ct} gateway(s), {fw_ct} firewall(s), "
                    f"{lb_ct} LB(s), {vnet_ct} VNet(s) utilized"
                )
        except Exception as e:
            self._progress(f"[{sub_name}] Metrics skipped: {e}")

    def _run_waf_scan(self, topo, sub_id: str, sub_name: str) -> None:
        self._progress(f"[{sub_name}] Scanning Front Door WAF policies…")
        try:
            topo.front_door_waf_policies = self._collect_front_door_waf_policies(sub_id)
            if topo.front_door_waf_policies:
                self._progress(
                    f"[{sub_name}] Front Door WAF: {len(topo.front_door_waf_policies)} policy(s)"
                )
        except Exception as e:
            self._progress(f"[{sub_name}] Front Door WAF scan skipped: {e}")

        self._progress(f"[{sub_name}] Querying Defender for Cloud network assessments…")
        try:
            topo.defender_assessments = self._collect_defender_assessments(sub_id)
            if topo.defender_assessments:
                self._progress(
                    f"[{sub_name}] Defender: {len(topo.defender_assessments)} network finding(s)"
                )
        except Exception as e:
            self._progress(f"[{sub_name}] Defender for Cloud skipped: {e}")

    # ------------------------------------------------------------------ VNets

    @staticmethod
    def _build_subnet(s) -> AzureSubnet:
        """Convert one ARM subnet object to an AzureSubnet dataclass."""
        nsg_name = None
        if s.network_security_group and s.network_security_group.id:
            nsg_name = s.network_security_group.id.split("/")[-1]

        rt_name = None
        if s.route_table and s.route_table.id:
            rt_name = s.route_table.id.split("/")[-1]

        nat_gw_id = None
        if hasattr(s, "nat_gateway") and s.nat_gateway:
            nat_gw_id = s.nat_gateway.id

        extra_prefixes: list[str] = []
        if hasattr(s, "address_prefixes") and s.address_prefixes:
            extra_prefixes = list(s.address_prefixes)

        default_outbound = True
        if hasattr(s, "default_outbound_access") and s.default_outbound_access is not None:
            default_outbound = bool(s.default_outbound_access)

        pl_svc_policy = "Enabled"
        if hasattr(s, "private_link_service_network_policies"):
            pl_svc_policy = str(s.private_link_service_network_policies or "Enabled")

        _nsg_id = s.network_security_group.id if s.network_security_group else None
        _rt_id = s.route_table.id if s.route_table else None
        _delegation = s.delegations[0].service_name if s.delegations else None
        return AzureSubnet(
            id=s.id,
            name=s.name,
            address_prefix=s.address_prefix or (extra_prefixes[0] if extra_prefixes else ""),
            nsg_id=_nsg_id,
            nsg_name=nsg_name,
            route_table_id=_rt_id,
            route_table_name=rt_name,
            nat_gateway_id=nat_gw_id,
            service_endpoints=[se.service for se in (s.service_endpoints or [])],
            private_endpoint_network_policies=str(s.private_endpoint_network_policies or "Enabled"),
            private_link_service_network_policies=pl_svc_policy,
            default_outbound_access=default_outbound,
            delegation=_delegation,
            address_prefixes=extra_prefixes,
            subnet_type=_classify_subnet(
                s.name or "",
                _nsg_id,
                _rt_id,
                _delegation,
                default_outbound,
            ),
        )

    def _collect_vnets(self, net, sub_id: str) -> list[VNet]:
        vnets = []
        for vnet in net.virtual_networks.list_all():
            subnets = []
            for s in vnet.subnets or []:
                subnets.append(self._build_subnet(s))

            peerings = []
            for p in vnet.virtual_network_peerings or []:
                remote_id = p.remote_virtual_network.id if p.remote_virtual_network else ""
                remote_sub = _sub_from_id(remote_id)
                # Try to get the actual remote VNet name from the resource ID
                remote_name = remote_id.split("/")[-1] if remote_id else None
                peerings.append(
                    VNetPeering(
                        id=p.id,
                        name=p.name,
                        remote_vnet_id=remote_id,
                        remote_vnet_name=remote_name,
                        remote_subscription_id=remote_sub,
                        peering_state=str(p.peering_state or "Unknown"),
                        allow_forwarded_traffic=bool(p.allow_forwarded_traffic),
                        allow_gateway_transit=bool(p.allow_gateway_transit),
                        use_remote_gateways=bool(p.use_remote_gateways),
                        do_not_verify_remote_gateways=bool(
                            getattr(p, "do_not_verify_remote_gateways", False)
                        ),
                        peer_complete_vnets=bool(getattr(p, "peer_complete_vnets", True)),
                    )
                )

            # DNS servers
            dns_servers: list[str] = []
            if vnet.dhcp_options and vnet.dhcp_options.dns_servers:
                dns_servers = list(vnet.dhcp_options.dns_servers)

            # DDoS protection
            ddos_enabled = bool(
                vnet.ddos_protection_plan is not None or vnet.enable_ddos_protection
            )
            ddos_plan_id = vnet.ddos_protection_plan.id if vnet.ddos_protection_plan else None

            # Encryption (VNet encryption — preview feature)
            encryption_enabled = False
            if hasattr(vnet, "encryption") and vnet.encryption:
                encryption_enabled = bool(getattr(vnet.encryption, "enabled", False))

            rg = _rg_from_id(vnet.id)
            vnets.append(
                VNet(
                    id=vnet.id,
                    name=vnet.name,
                    location=vnet.location,
                    resource_group=rg,
                    subscription_id=sub_id,
                    address_space=list(vnet.address_space.address_prefixes or []),
                    dns_servers=dns_servers,
                    subnets=subnets,
                    peerings=peerings,
                    ddos_protection_enabled=ddos_enabled,
                    ddos_protection_plan_id=ddos_plan_id,
                    flow_logs_enabled=False,  # enriched later if Network Watcher API available
                    encryption_enabled=encryption_enabled,
                    vm_protection_enabled=bool(getattr(vnet, "enable_vm_protection", False)),
                    tags=dict(vnet.tags or {}),
                )
            )
        return vnets

    # ------------------------------------------------------------------ NSGs

    def _collect_nsgs(self, net, sub_id: str) -> list[AzureNSG]:
        nsgs = []
        for nsg in net.network_security_groups.list_all():
            rg = _rg_from_id(nsg.id)

            def _map_rule(r, is_default: bool = False) -> NSGSecurityRule:
                return NSGSecurityRule(
                    name=r.name,
                    priority=r.priority,
                    direction=str(r.direction or "Inbound"),
                    access=str(r.access or "Allow"),
                    protocol=str(r.protocol or "*"),
                    source_port_range=r.source_port_range,
                    source_port_ranges=list(r.source_port_ranges or []),
                    destination_port_range=r.destination_port_range,
                    destination_port_ranges=list(r.destination_port_ranges or []),
                    source_address_prefix=r.source_address_prefix,
                    source_address_prefixes=list(r.source_address_prefixes or []),
                    source_asgs=[
                        asg.id for asg in (r.source_application_security_groups or []) if asg.id
                    ],
                    destination_address_prefix=r.destination_address_prefix,
                    destination_address_prefixes=list(r.destination_address_prefixes or []),
                    destination_asgs=[
                        asg.id
                        for asg in (r.destination_application_security_groups or [])
                        if asg.id
                    ],
                    description=r.description,
                    is_default_rule=is_default,
                    provisioning_state=str(r.provisioning_state or "Succeeded"),
                )

            security_rules = [_map_rule(r) for r in (nsg.security_rules or [])]
            default_rules = [
                _map_rule(r, is_default=True) for r in (nsg.default_security_rules or [])
            ]

            subnet_ids = [s.id for s in (nsg.subnets or []) if s.id]
            nic_ids = [ni.id for ni in (nsg.network_interfaces or []) if ni.id]

            nsgs.append(
                AzureNSG(
                    id=nsg.id,
                    name=nsg.name,
                    location=nsg.location,
                    resource_group=rg,
                    security_rules=security_rules,
                    default_security_rules=default_rules,
                    associated_subnet_ids=subnet_ids,
                    associated_nic_ids=nic_ids,
                    flow_logs_enabled=False,  # requires Network Watcher flow log query
                    tags=dict(nsg.tags or {}),
                )
            )
        return nsgs

    # ------------------------------------------------------------------ Route Tables

    def _collect_route_tables(self, net, sub_id: str) -> list[AzureRouteTable]:
        tables = []
        for rt in net.route_tables.list_all():
            rg = _rg_from_id(rt.id)
            routes = []
            for r in rt.routes or []:
                routes.append(
                    AzureRouteEntry(
                        name=r.name,
                        address_prefix=r.address_prefix or "",
                        next_hop_type=str(r.next_hop_type or "None"),
                        next_hop_ip=r.next_hop_ip_address,
                        has_bgp_override=bool(getattr(r, "has_bgp_override", False)),
                    )
                )
            subnet_ids = [s.id for s in (rt.subnets or []) if s.id]
            tables.append(
                AzureRouteTable(
                    id=rt.id,
                    name=rt.name,
                    location=rt.location,
                    resource_group=rg,
                    routes=routes,
                    associated_subnet_ids=subnet_ids,
                    disable_bgp_route_propagation=bool(rt.disable_bgp_route_propagation),
                    tags=dict(rt.tags or {}),
                )
            )
        return tables

    # ------------------------------------------------------------------ Public IPs

    _PIP_ASSOC_TYPES: dict[str, str] = {
        "networkinterfaces": "NIC",
        "loadbalancers": "LB",
        "applicationgateways": "AppGW",
        "azurefirewalls": "Firewall",
        "bastionhosts": "Bastion",
        "virtualnetworkgateways": "VpnGateway",
    }

    @staticmethod
    def _infer_pip_assoc_type(assoc_id: str) -> str | None:
        """Infer the associated resource type from a Public IP ip_configuration ID."""
        id_lower = assoc_id.lower()
        return next(
            (t for k, t in AzureDiscovery._PIP_ASSOC_TYPES.items() if k in id_lower),
            None,
        )

    def _collect_public_ips(self, net, sub_id: str) -> list[AzurePublicIP]:
        pips = []
        for pip in net.public_ip_addresses.list_all():
            rg = _rg_from_id(pip.id)
            sku_name = "Standard"
            if pip.sku:
                sku_name = str(pip.sku.name or "Standard")

            assoc_id = None
            assoc_type = None
            if pip.ip_configuration and pip.ip_configuration.id:
                assoc_id = pip.ip_configuration.id
                assoc_type = self._infer_pip_assoc_type(assoc_id)

            dns_label = None
            fqdn = None
            if pip.dns_settings:
                dns_label = pip.dns_settings.domain_name_label
                fqdn = pip.dns_settings.fqdn

            ddos_mode = "VirtualNetworkInherited"
            if hasattr(pip, "ddos_settings") and pip.ddos_settings:
                ddos_mode = str(getattr(pip.ddos_settings, "protection_mode", ddos_mode))

            pips.append(
                AzurePublicIP(
                    id=pip.id,
                    name=pip.name,
                    location=pip.location,
                    resource_group=rg,
                    sku_name=sku_name,
                    allocation_method=str(pip.public_ip_allocation_method or "Static"),
                    ip_address=pip.ip_address,
                    ip_version=str(pip.public_ip_address_version or "IPv4"),
                    dns_label=dns_label,
                    fqdn=fqdn,
                    zones=list(pip.zones or []),
                    associated_resource_id=assoc_id,
                    associated_resource_type=assoc_type,
                    idle_timeout_minutes=int(pip.idle_timeout_in_minutes or 4),
                    ddos_protection_mode=ddos_mode,
                    tags=dict(pip.tags or {}),
                )
            )
        return pips

    # ------------------------------------------------------------------ Load Balancers

    def _collect_load_balancers(self, net, sub_id: str) -> list[AzureLoadBalancer]:
        lbs = []
        for lb in net.load_balancers.list_all():
            rg = _rg_from_id(lb.id)
            sku_name = "Standard"
            if lb.sku:
                sku_name = str(lb.sku.name or "Standard")

            frontends: list[AzureLBFrontendIP] = []
            lb_type = "Public"
            for fic in lb.frontend_ip_configurations or []:
                is_private = fic.subnet is not None
                if is_private:
                    lb_type = "Internal"
                frontends.append(
                    AzureLBFrontendIP(
                        name=fic.name,
                        public_ip_id=fic.public_ip_address.id if fic.public_ip_address else None,
                        private_ip_address=fic.private_ip_address,
                        private_ip_allocation_method=str(fic.private_ip_allocation_method or "")
                        if is_private
                        else None,
                        subnet_id=fic.subnet.id if fic.subnet else None,
                        zones=list(getattr(fic, "zones", None) or []),
                    )
                )

            rules: list[AzureLBRule] = []
            for r in lb.load_balancing_rules or []:
                rules.append(
                    AzureLBRule(
                        name=r.name,
                        protocol=str(r.protocol or "Tcp"),
                        frontend_port=int(r.frontend_port or 0),
                        backend_port=int(r.backend_port or 0),
                        enable_floating_ip=bool(r.enable_floating_ip),
                        enable_tcp_reset=bool(getattr(r, "enable_tcp_reset", False)),
                        idle_timeout_minutes=int(r.idle_timeout_in_minutes or 4),
                        load_distribution=str(r.load_distribution or "Default"),
                        disable_outbound_snat=bool(getattr(r, "disable_outbound_snat", False)),
                    )
                )

            probes: list[AzureLBProbe] = []
            for p in lb.probes or []:
                probes.append(
                    AzureLBProbe(
                        name=p.name,
                        protocol=str(p.protocol or "Tcp"),
                        port=int(p.port or 0),
                        interval_seconds=int(p.interval_in_seconds or 15),
                        number_of_probes=int(p.number_of_probes or 2),
                        request_path=p.request_path,
                    )
                )

            pool_ids = [pool.id for pool in (lb.backend_address_pools or []) if pool.id]
            nat_rule_count = len(lb.inbound_nat_rules or [])

            # Collect zones from frontend configs
            zones: list[str] = []
            for fic in lb.frontend_ip_configurations or []:
                zones.extend(getattr(fic, "zones", None) or [])
            zones = sorted(set(zones))

            lbs.append(
                AzureLoadBalancer(
                    id=lb.id,
                    name=lb.name,
                    location=lb.location,
                    resource_group=rg,
                    sku_name=sku_name,
                    lb_type=lb_type,
                    frontend_ip_configs=frontends,
                    lb_rules=rules,
                    probes=probes,
                    backend_pool_ids=pool_ids,
                    inbound_nat_rule_count=nat_rule_count,
                    zones=zones,
                    tags=dict(lb.tags or {}),
                )
            )
        return lbs

    # ------------------------------------------------------------------ VNet Gateways

    def _collect_vnet_gateways(
        self, net, sub_id: str, rg_names: list[str]
    ) -> list[AzureVirtualNetworkGateway]:
        # VirtualNetworkGatewaysOperations has no list_all(); iterate per resource group.
        gateways = []
        for rg_name in rg_names:
            for gw in _safe_list(net.virtual_network_gateways.list(rg_name)):
                rg = _rg_from_id(gw.id)

                sku_name = "VpnGw1"
                sku_tier = "VpnGw1"
                if gw.sku:
                    sku_name = str(gw.sku.name or "VpnGw1")
                    sku_tier = str(gw.sku.tier or "VpnGw1")

                bgp_asn = None
                bgp_ip = None
                if gw.bgp_settings:
                    bgp_asn = gw.bgp_settings.asn
                    bgp_ip = gw.bgp_settings.bgp_peering_address

                pip_ids = []
                subnet_id = None
                vpn_client_pools: list[str] = []
                for ipc in gw.ip_configurations or []:
                    if ipc.public_ip_address:
                        pip_ids.append(ipc.public_ip_address.id)
                    if ipc.subnet:
                        subnet_id = ipc.subnet.id

                if gw.vpn_client_configuration:
                    for pool in gw.vpn_client_configuration.vpn_client_address_pool or []:
                        vpn_client_pools.extend(pool.address_prefixes or [])

                connections = self._collect_gateway_connections(net, rg, gw.name)

                gateways.append(
                    AzureVirtualNetworkGateway(
                        id=gw.id,
                        name=gw.name,
                        location=gw.location,
                        resource_group=rg,
                        gateway_type=str(gw.gateway_type or "Vpn"),
                        vpn_type=str(gw.vpn_type or "RouteBased")
                        if gw.gateway_type == "Vpn"
                        else None,
                        sku_name=sku_name,
                        sku_tier=sku_tier,
                        active_active=bool(gw.active_active),
                        enable_bgp=bool(gw.enable_bgp),
                        bgp_asn=bgp_asn,
                        bgp_peering_address=bgp_ip,
                        public_ip_ids=pip_ids,
                        subnet_id=subnet_id,
                        vpn_client_address_pool=vpn_client_pools,
                        connections=connections,
                        generation=str(gw.vpn_gateway_generation or ""),
                        zones=list(gw.zones or []),
                        tags=dict(gw.tags or {}),
                    )
                )
        return gateways

    def _collect_gateway_connections(
        self, net, resource_group: str, gateway_name: str
    ) -> list[AzureGatewayConnection]:
        connections = []
        try:
            for conn in _safe_list(net.virtual_network_gateway_connections.list(resource_group)):
                # Only include connections that reference this gateway
                gw_ref = ""
                if conn.virtual_network_gateway1:
                    gw_ref = conn.virtual_network_gateway1.id or ""
                if gateway_name.lower() not in gw_ref.lower():
                    continue

                connections.append(
                    AzureGatewayConnection(
                        id=conn.id,
                        name=conn.name,
                        connection_type=str(conn.connection_type or "IPsec"),
                        connection_status=str(conn.connection_status or "Unknown"),
                        remote_vnet_id=(
                            conn.virtual_network_gateway2.id
                            if conn.virtual_network_gateway2
                            else None
                        ),
                        local_network_gateway_id=(
                            conn.local_network_gateway2.id if conn.local_network_gateway2 else None
                        ),
                        express_route_circuit_id=(conn.peer.id if conn.peer else None),
                        routing_weight=int(conn.routing_weight or 10),
                        enable_bgp=bool(conn.enable_bgp),
                        use_policy_based_traffic_selectors=bool(
                            conn.use_policy_based_traffic_selectors
                        ),
                        dpd_timeout_seconds=getattr(conn, "dpd_timeout_seconds", None),
                        egress_bytes_transferred=int(conn.egress_bytes_transferred or 0),
                        ingress_bytes_transferred=int(conn.ingress_bytes_transferred or 0),
                        shared_key_set=True,  # key is always set when connection exists
                    )
                )
        except Exception as e:
            logger.debug(
                "Gateway connections for %s/%s failed: %s", resource_group, gateway_name, e
            )
        return connections

    # ------------------------------------------------------------------ Private Endpoints

    @staticmethod
    def _validate_pe_dns(custom_dns: list[str], private_ips: list[str]) -> bool | None:
        """Validate that private endpoint FQDNs resolve to RFC-1918 addresses.

        Returns True if at least one FQDN resolves to a private IP, False if one
        resolves to a public IP, or None when resolution is inconclusive.
        """
        if not custom_dns and private_ips:
            return True
        if not custom_dns:
            return None
        import ipaddress as _ipaddr
        import socket as _socket

        _rfc1918 = (
            _ipaddr.ip_network("10.0.0.0/8"),
            _ipaddr.ip_network("172.16.0.0/12"),
            _ipaddr.ip_network("192.168.0.0/16"),
        )
        result: bool | None = None
        for fqdn in custom_dns[:3]:
            try:
                resolved_ip = _socket.gethostbyname(fqdn)
                addr = _ipaddr.ip_address(resolved_ip)
                if any(addr in net_range for net_range in _rfc1918):
                    return True
                result = False
            except Exception as _e:
                logger.debug("DNS resolution skipped for %s: %s", fqdn, _e)
        return result

    @staticmethod
    def _pe_private_ips(net, pe) -> list[str]:
        """Collect private IPs from a private endpoint's attached NICs."""
        private_ips: list[str] = []
        for nic_ref in pe.network_interfaces or []:
            if not nic_ref.id:
                continue
            try:
                nic_rg = _rg_from_id(nic_ref.id)
                nic_name = nic_ref.id.split("/")[-1]
                nic_obj = net.network_interfaces.get(nic_rg, nic_name)
                for ipc in nic_obj.ip_configurations or []:
                    if ipc.private_ip_address:
                        private_ips.append(ipc.private_ip_address)
            except Exception as _e:
                logger.debug("PE NIC GET failed for %s: %s", nic_ref.id, _e)
        return private_ips

    @staticmethod
    def _pe_service_conns(pe) -> list[AzurePrivateEndpointConnection]:
        """Build service connection list from both auto and manual connections."""
        service_conns: list[AzurePrivateEndpointConnection] = []
        for sc in list(pe.private_link_service_connections or []) + list(
            pe.manual_private_link_service_connections or []
        ):
            state = "Pending"
            if sc.private_link_service_connection_state:
                state = str(sc.private_link_service_connection_state.status or "Pending")
            service_conns.append(
                AzurePrivateEndpointConnection(
                    connection_name=sc.name or "",
                    private_link_service_id=sc.private_link_service_id or "",
                    group_ids=list(sc.group_ids or []),
                    connection_state=state,
                )
            )
        return service_conns

    def _collect_private_endpoints(self, net, sub_id: str) -> list[AzurePrivateEndpoint]:
        endpoints = []
        for pe in net.private_endpoints.list_by_subscription():
            rg = _rg_from_id(pe.id)
            subnet_id = pe.subnet.id or "" if pe.subnet else ""
            private_ips = self._pe_private_ips(net, pe)
            service_conns = self._pe_service_conns(pe)

            dns_group_names: list[str] = []
            custom_dns: list[str] = []
            for dns_cfg in pe.custom_dns_configs or []:
                if dns_cfg.fqdn:
                    custom_dns.append(dns_cfg.fqdn)
            for dng in pe.private_dns_zone_groups or []:
                if dng.name:
                    dns_group_names.append(dng.name)

            endpoints.append(
                AzurePrivateEndpoint(
                    id=pe.id,
                    name=pe.name,
                    location=pe.location,
                    resource_group=rg,
                    subnet_id=subnet_id,
                    private_ip_addresses=private_ips,
                    service_connections=service_conns,
                    dns_zone_group_names=dns_group_names,
                    custom_dns_configs=custom_dns,
                    dns_resolves_to_private_ip=self._validate_pe_dns(custom_dns, private_ips),
                    tags=dict(pe.tags or {}),
                )
            )
        return endpoints

    # ------------------------------------------------------------------ NAT Gateways

    def _collect_nat_gateways(self, net, sub_id: str) -> list[AzureNatGateway]:
        nat_gws = []
        for ng in net.nat_gateways.list_all():
            rg = _rg_from_id(ng.id)
            sku_name = "Standard"
            if ng.sku:
                sku_name = str(ng.sku.name or "Standard")

            pip_ids = [pip.id for pip in (ng.public_ip_addresses or []) if pip.id]
            prefix_ids = [pfx.id for pfx in (ng.public_ip_prefixes or []) if pfx.id]
            subnet_ids = [s.id for s in (ng.subnets or []) if s.id]

            nat_gws.append(
                AzureNatGateway(
                    id=ng.id,
                    name=ng.name,
                    location=ng.location,
                    resource_group=rg,
                    sku_name=sku_name,
                    idle_timeout_minutes=int(ng.idle_timeout_in_minutes or 4),
                    public_ip_ids=pip_ids,
                    public_ip_prefix_ids=prefix_ids,
                    associated_subnet_ids=subnet_ids,
                    zones=list(ng.zones or []),
                    provisioning_state=str(ng.provisioning_state or "Succeeded"),
                    tags=dict(ng.tags or {}),
                )
            )
        return nat_gws

    # ------------------------------------------------------------------ Bastion Hosts

    def _collect_bastion_hosts(self, net, sub_id: str) -> list[AzureBastionHost]:
        bastions = []
        for bh in _safe_list(net.bastion_hosts.list()):
            rg = _rg_from_id(bh.id)
            sku_name = "Standard"
            if hasattr(bh, "sku") and bh.sku:
                sku_name = str(bh.sku.name or "Standard")

            subnet_id = None
            pip_id = None
            for ipc in bh.ip_configurations or []:
                if ipc.subnet:
                    subnet_id = ipc.subnet.id
                if ipc.public_ip_address:
                    pip_id = ipc.public_ip_address.id

            bastions.append(
                AzureBastionHost(
                    id=bh.id,
                    name=bh.name,
                    location=bh.location,
                    resource_group=rg,
                    sku_name=sku_name,
                    subnet_id=subnet_id,
                    public_ip_id=pip_id,
                    scale_units=int(getattr(bh, "scale_units", 2) or 2),
                    tunneling_enabled=bool(getattr(bh, "enable_tunneling", False)),
                    shareable_link_enabled=bool(getattr(bh, "enable_shareable_link", False)),
                    ip_connect_enabled=bool(getattr(bh, "enable_ip_connect", False)),
                    file_copy_enabled=bool(getattr(bh, "enable_file_copy", False)),
                    kerberos_enabled=bool(getattr(bh, "enable_kerberos", False)),
                    tags=dict(bh.tags or {}),
                )
            )
        return bastions

    # ------------------------------------------------------------------ vWANs

    def _collect_vwans(self, net, sub_id: str) -> list[AzureVWan]:
        vwans = []
        for vwan in _safe_list(net.virtual_wans.list()):
            hubs = []
            for hub in _safe_list(net.virtual_hubs.list()):
                if hub.virtual_wan and hub.virtual_wan.id == vwan.id:
                    connected_vnets = [
                        vc.remote_virtual_network.id
                        for vc in (getattr(hub, "virtual_network_connections", None) or [])
                        if vc.remote_virtual_network
                    ]
                    hubs.append(
                        AzureVHub(
                            id=hub.id,
                            name=hub.name,
                            location=hub.location,
                            resource_group=_rg_from_id(hub.id),
                            address_prefix=hub.address_prefix or "",
                            sku=hub.sku or "Standard",
                            connected_vnet_ids=connected_vnets,
                            express_route_gateway_id=(
                                hub.express_route_gateway.id if hub.express_route_gateway else None
                            ),
                            azure_firewall_id=(
                                hub.azure_firewall.id if hub.azure_firewall else None
                            ),
                            routing_state=str(hub.routing_state or "None"),
                            virtual_router_asn=getattr(hub, "virtual_router_asn", None),
                            virtual_router_ips=list(getattr(hub, "virtual_router_ips", None) or []),
                        )
                    )
            vwans.append(
                AzureVWan(
                    id=vwan.id,
                    name=vwan.name,
                    resource_group=_rg_from_id(vwan.id),
                    sku=vwan.type or "Standard",
                    hubs=hubs,
                    allow_vnet_to_vnet_traffic=bool(
                        getattr(vwan, "allow_vnet_to_vnet_traffic", True)
                    ),
                    allow_branch_to_branch_traffic=bool(
                        getattr(vwan, "allow_branch_to_branch_traffic", True)
                    ),
                    tags=dict(vwan.tags or {}),
                )
            )
        return vwans

    # ------------------------------------------------------------------ Route Servers

    def _collect_route_servers(self, net, sub_id: str) -> list[AzureRouteServer]:
        """Azure Route Servers are virtual hubs with kind == 'RouteServer'."""
        route_servers = []
        for hub in _safe_list(net.virtual_hubs.list()):
            if str(getattr(hub, "kind", "") or "").lower() != "routeserver":
                continue
            rg = _rg_from_id(hub.id)
            # The RouteServerSubnet is exposed via the hub's IP configurations
            hosted_subnet_id = None
            for ipc in _safe_list(net.virtual_hub_ip_configuration.list(rg, hub.name)):
                subnet = getattr(ipc, "subnet", None)
                if subnet is not None and getattr(subnet, "id", None):
                    hosted_subnet_id = subnet.id
                    break
            vnet_id = hosted_subnet_id.rsplit("/subnets/", 1)[0] if hosted_subnet_id else None
            bgp_connections = []
            for conn in _safe_list(net.virtual_hub_bgp_connections.list(rg, hub.name)):
                bgp_connections.append(
                    AzureRouteServerBgpConnection(
                        id=conn.id or "",
                        name=conn.name or "unknown",
                        peer_ip=getattr(conn, "peer_ip", None),
                        peer_asn=getattr(conn, "peer_asn", None),
                        provisioning_state=str(
                            getattr(conn, "provisioning_state", None) or "Succeeded"
                        ),
                        connection_state=getattr(conn, "connection_state", None),
                    )
                )
            route_servers.append(
                AzureRouteServer(
                    id=hub.id,
                    name=hub.name,
                    location=hub.location or "",
                    resource_group=rg,
                    hosted_subnet_id=hosted_subnet_id,
                    vnet_id=vnet_id,
                    virtual_router_asn=getattr(hub, "virtual_router_asn", None),
                    virtual_router_ips=list(getattr(hub, "virtual_router_ips", None) or []),
                    allow_branch_to_branch_traffic=bool(
                        getattr(hub, "allow_branch_to_branch_traffic", False)
                    ),
                    hub_routing_preference=getattr(hub, "hub_routing_preference", None),
                    bgp_connections=bgp_connections,
                    provisioning_state=str(getattr(hub, "provisioning_state", None) or "Succeeded"),
                    tags=dict(hub.tags or {}),
                )
            )
        return route_servers

    # ------------------------------------------------------------------ Firewalls

    def _collect_firewalls(self, net, sub_id: str) -> list[AzureFirewall]:
        firewalls = []
        for fw in net.azure_firewalls.list_all():
            rg = _rg_from_id(fw.id)
            sku_tier = "Standard"
            if fw.sku:
                sku_tier = fw.sku.tier or "Standard"
            subnet_id = None
            for ipc in fw.ip_configurations or []:
                if ipc.subnet and ipc.subnet.id:
                    subnet_id = ipc.subnet.id
                    break
            pip_ids = [
                ipc.public_ip_address.id
                for ipc in (fw.ip_configurations or [])
                if ipc.public_ip_address
            ]
            firewalls.append(
                AzureFirewall(
                    id=fw.id or "",
                    name=fw.name or (fw.id.split("/")[-1] if fw.id else "Unknown"),
                    location=fw.location or "",
                    resource_group=rg,
                    sku_tier=sku_tier,
                    subnet_id=subnet_id,
                    public_ip_ids=pip_ids,
                    policy_id=fw.firewall_policy.id if fw.firewall_policy else None,
                    threat_intel_mode=str(fw.threat_intel_mode or "Alert"),
                    zones=list(fw.zones or []),
                    tags=dict(fw.tags or {}),
                )
            )
        return firewalls

    # ------------------------------------------------------------------ App Gateways

    def _collect_appgws(self, net, sub_id: str) -> list[ApplicationGateway]:
        appgws = []
        for agw in net.application_gateways.list_all():
            rg = _rg_from_id(agw.id)
            sku_name = "Standard_v2"
            sku_capacity = None
            waf_enabled = False
            waf_mode = None
            waf_rule_set_type = None
            waf_rule_set_version = None
            if agw.sku:
                sku_name = agw.sku.name or "Standard_v2"
                sku_capacity = agw.sku.capacity
            if agw.web_application_firewall_configuration:
                waf_enabled = bool(agw.web_application_firewall_configuration.enabled)
                waf_mode = str(agw.web_application_firewall_configuration.firewall_mode or "")
                waf_rule_set_type = agw.web_application_firewall_configuration.rule_set_type
                waf_rule_set_version = agw.web_application_firewall_configuration.rule_set_version
            # WAF policy takes precedence over inline WAF config
            if agw.firewall_policy:
                waf_enabled = True

            subnet_id = ""
            for gw_config in agw.gateway_ip_configurations or []:
                if gw_config.subnet and gw_config.subnet.id:
                    subnet_id = gw_config.subnet.id
                    break

            frontend_ips = [fic.name for fic in (agw.frontend_ip_configurations or [])]

            ssl_policy = None
            if agw.ssl_policy and agw.ssl_policy.policy_name:
                ssl_policy = str(agw.ssl_policy.policy_name)

            autoscale_min = None
            autoscale_max = None
            if agw.autoscale_configuration:
                autoscale_min = agw.autoscale_configuration.min_capacity
                autoscale_max = agw.autoscale_configuration.max_capacity

            appgws.append(
                ApplicationGateway(
                    id=agw.id,
                    name=agw.name,
                    location=agw.location,
                    resource_group=rg,
                    sku_name=sku_name,
                    sku_capacity=sku_capacity,
                    subnet_id=subnet_id,
                    waf_enabled=waf_enabled,
                    waf_mode=waf_mode,
                    waf_rule_set_type=waf_rule_set_type,
                    waf_rule_set_version=waf_rule_set_version,
                    frontend_ip_configs=frontend_ips,
                    ssl_policy_name=ssl_policy,
                    autoscale_min=autoscale_min,
                    autoscale_max=autoscale_max,
                    zones=list(agw.zones or []),
                    tags=dict(agw.tags or {}),
                )
            )
        return appgws

    # ------------------------------------------------------------------ Private DNS

    def _collect_private_dns(self, sub_id: str) -> list[PrivateDnsZone]:
        zones = []
        try:
            from azure.mgmt.privatedns import PrivateDnsManagementClient

            dns_client = PrivateDnsManagementClient(self._cred, sub_id)
            for zone in _safe_list(dns_client.private_zones.list()):
                rg = _rg_from_id(zone.id)
                linked_vnets = []
                linked_names = []
                auto_reg = False
                for link in _safe_list(dns_client.virtual_network_links.list(rg, zone.name)):
                    if link.virtual_network:
                        linked_vnets.append(link.virtual_network.id)
                    if link.registration_enabled:
                        auto_reg = True
                    linked_names.append(link.name)
                zones.append(
                    PrivateDnsZone(
                        id=zone.id,
                        name=zone.name,
                        resource_group=rg,
                        linked_vnet_ids=linked_vnets,
                        linked_vnet_names=linked_names,
                        auto_registration_enabled=auto_reg,
                        record_count=zone.number_of_record_sets or 0,
                    )
                )
        except ImportError:
            logger.warning("azure-mgmt-privatedns not installed. Skipping Private DNS discovery.")
        except Exception as e:
            logger.warning("Private DNS discovery failed for %s: %s", sub_id, e)
        return zones

    # ------------------------------------------------------------------ ExpressRoute

    def _collect_er_circuits(self, net, sub_id: str) -> list[ExpressRouteCircuit]:
        circuits = []
        for erc in net.express_route_circuits.list_all():
            rg = _rg_from_id(erc.id)
            sku_tier = "Standard"
            sku_family = "MeteredData"
            if erc.sku:
                sku_tier = erc.sku.tier or "Standard"
                sku_family = erc.sku.family or "MeteredData"
            provider = None
            peering_loc = None
            bw = None
            if erc.service_provider_properties:
                provider = erc.service_provider_properties.service_provider_name
                peering_loc = erc.service_provider_properties.peering_location
                bw = erc.service_provider_properties.bandwidth_in_mbps

            peering_types = [p.peering_type for p in (erc.peerings or []) if p.peering_type]

            circuits.append(
                ExpressRouteCircuit(
                    id=erc.id,
                    name=erc.name,
                    location=erc.location,
                    resource_group=rg,
                    service_provider=provider,
                    peering_location=peering_loc,
                    bandwidth_mbps=bw,
                    sku_tier=sku_tier,
                    sku_family=sku_family,
                    circuit_provisioning_state=str(erc.circuit_provisioning_state or "Enabled"),
                    global_reach_enabled=bool(getattr(erc, "global_reach_enabled", False)),
                    allow_classic_operations=bool(getattr(erc, "allow_classic_operations", False)),
                    peering_types=peering_types,
                    tags=dict(erc.tags or {}),
                )
            )
        return circuits

    # ------------------------------------------------------------------ NVA / NGFW discovery

    # Known marketplace publishers for NGFW and network virtual appliances.
    # Matched against plan.publisher or image_reference.publisher (lower-cased).
    _NGFW_PUBLISHERS: frozenset[str] = frozenset(
        {
            "paloaltonetworks",  # Palo Alto VM-Series
            "fortinet",  # FortiGate
            "checkpoint",  # Check Point CloudGuard
            "cisco",  # Cisco ASAv / FTDv / CSR1000v
            "barracudanetworks",  # Barracuda CloudGen Firewall
            "junipernetworks",  # Juniper vSRX / vMX
            "sophos",  # Sophos XG / UTM
            "f5-networks",  # F5 BIG-IP
            "zscaler",  # Zscaler Private Access
            "stormshield",  # Stormshield Network Security
            "watchguard-technologies",
            "hillstone-networks",
            "viptela",  # Cisco SD-WAN (now Cisco)
        }
    )

    def _collect_nvas(self, net, sub_id: str) -> list[AzureNVA]:
        """Discover Network Virtual Appliances in a subscription.

        Identification strategy (in order):
          1. marketplace plan.publisher matches a known NGFW vendor
          2. image_reference.publisher matches (covers BYOL / custom images)
          3. Any attached NIC has enable_ip_forwarding=True

        Only VMs matching at least one criterion are returned.
        Associated NICs (all, not just forwarding ones) are included
        to show the full multi-homed topology.
        """
        try:
            from azure.mgmt.compute import ComputeManagementClient
        except ImportError:
            logger.warning("azure-mgmt-compute not installed — NVA discovery skipped")
            return []

        cmc = ComputeManagementClient(self._cred, sub_id)
        nvas: list[AzureNVA] = []

        for vm in _safe_list(cmc.virtual_machines.list_all()):
            publisher, offer, plan_name, identification_method = self._identify_nva_publisher(vm)
            vm_nics, has_ip_forwarding = self._collect_vm_nics(net, vm)

            if not identification_method and has_ip_forwarding:
                identification_method = "ip_forwarding"

            if not identification_method:
                continue

            rg = _rg_from_id(vm.id or "")
            os_type: str | None = None
            if vm.storage_profile and vm.storage_profile.os_disk:
                os_type = str(vm.storage_profile.os_disk.os_type or "") or None

            vm_size: str | None = None
            if vm.hardware_profile:
                vm_size = str(vm.hardware_profile.vm_size or "") or None

            nvas.append(
                AzureNVA(
                    id=vm.id,
                    name=vm.name,
                    location=vm.location,
                    resource_group=rg,
                    vm_size=vm_size,
                    os_type=os_type,
                    publisher=publisher,
                    offer=offer,
                    plan_name=plan_name,
                    identification_method=identification_method,
                    nics=vm_nics,
                    tags=dict(vm.tags or {}),
                )
            )

        return nvas

    def _identify_nva_publisher(self, vm) -> tuple[str | None, str | None, str | None, str | None]:
        """Return (publisher, offer, plan_name, identification_method) for a VM.

        Returns all None if the VM does not match any NVA identification strategy.
        """
        publisher: str | None = None
        offer: str | None = None
        plan_name: str | None = None
        identification_method: str | None = None

        if vm.plan and vm.plan.publisher:
            pub_lower = vm.plan.publisher.lower()
            if pub_lower in self._NGFW_PUBLISHERS:
                publisher = vm.plan.publisher
                offer = vm.plan.product
                plan_name = vm.plan.name
                identification_method = "marketplace"

        if not identification_method:
            img = vm.storage_profile.image_reference if vm.storage_profile else None
            if img and img.publisher:
                pub_lower = img.publisher.lower()
                if pub_lower in self._NGFW_PUBLISHERS:
                    publisher = img.publisher
                    offer = img.offer
                    plan_name = img.sku
                    identification_method = "image_reference"

        return publisher, offer, plan_name, identification_method

    def _collect_vm_nics(self, net, vm) -> tuple[list[AzureNIC], bool]:
        """Fetch all NIC objects for a VM and return (nics, has_ip_forwarding)."""
        vm_nics: list[AzureNIC] = []
        has_ip_forwarding = False
        nic_refs = []
        if vm.network_profile:
            nic_refs = vm.network_profile.network_interfaces or []
        for nic_ref in nic_refs:
            if not nic_ref.id:
                continue
            try:
                nic_rg = _rg_from_id(nic_ref.id)
                nic_name = nic_ref.id.split("/")[-1]
                nic = net.network_interfaces.get(nic_rg, nic_name)
                ip_fwd = bool(getattr(nic, "enable_ip_forwarding", False))
                if ip_fwd:
                    has_ip_forwarding = True

                subnet_ids: list[str] = []
                private_ips: list[str] = []
                public_ip_id: str | None = None
                for ipc in nic.ip_configurations or []:
                    if ipc.subnet and ipc.subnet.id:
                        subnet_ids.append(ipc.subnet.id)
                    if ipc.private_ip_address:
                        private_ips.append(ipc.private_ip_address)
                    if ipc.public_ip_address and ipc.public_ip_address.id:
                        public_ip_id = ipc.public_ip_address.id

                vm_nics.append(
                    AzureNIC(
                        id=nic.id,
                        name=nic.name,
                        location=nic.location,
                        resource_group=nic_rg,
                        vm_id=vm.id,
                        ip_forwarding_enabled=ip_fwd,
                        subnet_ids=subnet_ids,
                        private_ips=private_ips,
                        public_ip_id=public_ip_id,
                        nsg_id=(
                            nic.network_security_group.id if nic.network_security_group else None
                        ),
                        tags=dict(vm.tags or {}),
                    )
                )
            except Exception as nic_exc:
                logger.debug("NIC fetch failed %s: %s", nic_ref.id, nic_exc)
        return vm_nics, has_ip_forwarding

    # ------------------------------------------------------------------ BGP data

    def _collect_bgp_data(
        self,
        net,
        sub_id: str,
        gateways: list[AzureVirtualNetworkGateway],
    ) -> list[GatewayBgpData]:
        """Query BGP peer status and routes for each VPN gateway."""
        results: list[GatewayBgpData] = []

        for gw in gateways:
            if gw.gateway_type != "Vpn":
                continue

            item = GatewayBgpData(
                gateway_id=gw.id,
                gateway_name=gw.name,
                bgp_enabled=gw.enable_bgp,
                bgp_asn=gw.bgp_asn,
            )

            if not gw.enable_bgp:
                results.append(item)
                continue

            rg = gw.resource_group
            gw_name = gw.name

            # BGP peer status (long-running operation)
            try:
                self._progress(f"BGP: querying peers for '{gw_name}'…")
                result = net.virtual_network_gateways.begin_get_bgp_peer_status(rg, gw_name).result(
                    timeout=90
                )
                for peer in result.value or []:
                    item.peers.append(
                        BgpPeerStatus(
                            peer_ip=peer.neighbor or "",
                            peer_asn=getattr(peer, "asn", None),
                            state=str(peer.bgp_peer_state or "Unknown"),
                            messages_sent=int(peer.messages_sent or 0),
                            messages_received=int(peer.messages_received or 0),
                            routes_received=int(peer.routes_received or 0),
                            connected_duration=str(peer.connected_duration or "") or None,
                        )
                    )
            except Exception as e:
                item.collection_error = f"BGP peers: {e}"

            # Learned routes
            try:
                result = net.virtual_network_gateways.begin_get_learned_routes(rg, gw_name).result(
                    timeout=90
                )
                all_routes = result.value or []
                item.learned_routes_count = len(all_routes)
                item.learned_routes = [r.network for r in all_routes[:50] if r.network]
            except Exception as e:
                err = f"Learned routes: {e}"
                item.collection_error = (
                    f"{item.collection_error}; {err}" if item.collection_error else err
                )

            # Advertised routes (use first peer)
            try:
                if item.peers:
                    peer_ip = item.peers[0].peer_ip
                    result = net.virtual_network_gateways.begin_get_advertised_routes(
                        rg, gw_name, peer_ip
                    ).result(timeout=90)
                    all_adv = result.value or []
                    item.advertised_routes_count = len(all_adv)
                    item.advertised_routes = [r.network for r in all_adv[:50] if r.network]
            except Exception as exc:  # noqa: BLE001
                logger.debug("advertised routes unavailable: %s", exc)

            results.append(item)

        return results

    # ------------------------------------------------------------------ Observability

    def _collect_observability(self, ctx: _ObservabilityContext) -> ObservabilityData:
        """Collect Network Watcher, Log Analytics, flow log, Traffic Analytics,
        diagnostic-settings coverage (Firewall, Bastion, Gateway, AppGW, LB),
        and Azure Monitor alert-rule counts."""
        net = ctx.net
        sub_id = ctx.sub_id
        obs = ObservabilityData(nsg_flow_logs_total=ctx.nsg_count)
        self._obs_collect_network_watchers(net, sub_id, obs)
        self._obs_collect_flow_logs(net, obs)
        self._obs_collect_la_workspaces(sub_id, obs)
        self._obs_collect_diagnostics(sub_id, ctx, obs)
        self._obs_collect_alert_counts(sub_id, obs)
        return obs

    def _obs_collect_network_watchers(self, net, sub_id, obs) -> None:
        try:
            for nw in _safe_list(net.network_watchers.list_all()):
                obs.network_watchers.append(
                    NetworkWatcherInfo(
                        location=nw.location or "unknown",
                        name=nw.name or "unknown",
                        provisioning_state=str(nw.provisioning_state or "Unknown"),
                    )
                )
        except Exception as e:
            logger.warning("[%s] Network Watcher listing failed: %s", sub_id, e)

    def _obs_collect_flow_logs(self, net, obs) -> None:
        flow_enabled = 0
        ta_enabled = 0
        for nw_info in obs.network_watchers:
            try:
                nw_rg = "NetworkWatcherRG"
                for fl in _safe_list(net.flow_logs.list(nw_rg, nw_info.name)):
                    if getattr(fl, "enabled", False):
                        flow_enabled += 1
                        ta_cfg = getattr(fl, "flow_analytics_configuration", None)
                        if ta_cfg:
                            ta_ws = getattr(
                                ta_cfg, "network_watcher_flow_analytics_configuration", None
                            )
                            if ta_ws and getattr(ta_ws, "enabled", False):
                                ta_enabled += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("flow log enumeration unavailable: %s", exc)
        obs.nsg_flow_logs_enabled = flow_enabled
        obs.traffic_analytics_enabled = ta_enabled

    def _obs_collect_la_workspaces(self, sub_id, obs) -> None:
        try:
            from azure.mgmt.loganalytics import LogAnalyticsManagementClient

            la = LogAnalyticsManagementClient(self._cred, sub_id)
            for ws in _safe_list(la.workspaces.list()):
                obs.log_analytics_workspaces.append(
                    LogAnalyticsWorkspace(
                        id=ws.id or "",
                        name=ws.name or "unknown",
                        resource_group=_rg_from_id(ws.id or ""),
                        location=ws.location or "unknown",
                        retention_days=int(ws.retention_in_days or 30),
                        sku=str(ws.sku.name if ws.sku else "PerGB2018"),
                    )
                )
        except ImportError:
            logger.warning(
                "azure-mgmt-loganalytics not installed — Log Analytics workspace query skipped"
            )
        except Exception as e:
            logger.warning("[%s] Log Analytics listing failed: %s", sub_id, e)

    def _has_la_diagnostic(self, sub_id: str, resource_id: str) -> bool:
        """Return True if the resource has a Log Analytics diagnostic-settings sink."""
        try:
            from azure.mgmt.monitor import MonitorManagementClient

            mon = MonitorManagementClient(self._cred, sub_id)
            for ds in _safe_list(mon.diagnostic_settings.list(resource_id)):
                if getattr(ds, "workspace_id", None):
                    return True
        except Exception as _e:
            logger.debug("Diagnostic settings query failed for %s: %s", resource_id, _e)
        return False

    def _obs_collect_diagnostics(self, sub_id, ctx, obs) -> None:
        resource_groups = [
            (ctx.firewalls, "firewalls_total", "firewalls_with_diagnostics"),
            (ctx.bastion_hosts, "bastion_total", "bastion_with_diagnostics"),
            (ctx.gateways, "gateways_total", "gateways_with_diagnostics"),
            (ctx.appgws, "appgw_total", "appgw_with_diagnostics"),
            (ctx.load_balancers, "lb_total", "lb_with_diagnostics"),
        ]
        for resources, total_attr, diag_attr in resource_groups:
            self._obs_tally_diagnostics(sub_id, resources or [], obs, total_attr, diag_attr)

    def _obs_tally_diagnostics(self, sub_id, resources, obs, total_attr, diag_attr) -> None:
        for resource in resources:
            setattr(obs, total_attr, getattr(obs, total_attr) + 1)
            if self._has_la_diagnostic(sub_id, resource.id):
                setattr(obs, diag_attr, getattr(obs, diag_attr) + 1)

    def _obs_collect_alert_counts(self, sub_id, obs) -> None:
        try:
            from azure.mgmt.monitor import MonitorManagementClient

            mon = MonitorManagementClient(self._cred, sub_id)
            obs.metric_alert_count = len(_safe_list(mon.metric_alerts.list_by_subscription()))
            obs.activity_log_alert_count = len(
                _safe_list(mon.activity_log_alerts.list_by_subscription_id())
            )
        except ImportError:
            logger.warning("azure-mgmt-monitor not installed — alert-rule counts skipped")
        except Exception as e:
            logger.warning("[%s] Alert-rule enumeration failed: %s", sub_id, e)

    # ------------------------------------------------------------------ Network metrics

    # VPN Gateway SKU → provisioned bandwidth ceiling (Mbps)
    # Source: https://learn.microsoft.com/azure/vpn-gateway/vpn-gateway-about-vpngateways
    _GW_SKU_BANDWIDTH: dict[str, float] = {
        "VpnGw1": 650,
        "VpnGw2": 1000,
        "VpnGw3": 1250,
        "VpnGw4": 5000,
        "VpnGw5": 10000,
        "VpnGw1AZ": 650,
        "VpnGw2AZ": 1000,
        "VpnGw3AZ": 1250,
        "VpnGw4AZ": 5000,
        "VpnGw5AZ": 10000,
        "ErGw1AZ": 1000,
        "ErGw2AZ": 2000,
        "ErGw3AZ": 10000,
        "UltraPerformance": 10000,
        "HighPerformance": 2000,
    }

    def _collect_network_metrics(self, ctx: _MetricsContext) -> NetworkMetrics:
        """Collect 24-hour Azure Monitor metrics and compute VNet IP utilization.

        Collectors (each runs independently — failure in one does not abort others):
          1. VPN/ER gateway: TunnelIngress/EgressBytes + AverageBandwidth → utilization_pct
          2. Azure Firewall: DataProcessed + rule hit counts (app/network/NAT)
          3. Load Balancer: SNAT port utilization (used / allocated)
          4. ER circuit: PrimaryBitsInPerSecond / SecondaryBitsInPerSecond → utilization_pct
          5. DDoS: IfUnderDDoSAttack + DdosPacketsDropped on public IPs
          6. VNet IP space: computed from existing CIDR data (no API call)
          7. NTA east-west / north-south bytes: Log Analytics AzureNetworkAnalytics_CL query
          8. Cost Management: Microsoft.Network MTD egress spend (Billing Reader)
          9. App Gateway: CapacityUnits + BackendLastByteResponseTime + request counts
        """
        import datetime as _dt
        from datetime import timedelta

        metrics = NetworkMetrics()

        try:
            from azure.mgmt.monitor import MonitorManagementClient
        except ImportError:
            metrics.collection_error = "azure-mgmt-monitor not installed"
            return metrics

        try:
            monitor = MonitorManagementClient(self._cred, ctx.sub_id)
            end = _dt.datetime.now(_dt.UTC)
            start = end - timedelta(hours=24)
            timespan = (
                f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')}/{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
            )
            self._collect_gateway_metrics(ctx.sub_id, ctx.gateways, monitor, timespan, metrics)
            self._collect_firewall_metrics(ctx.sub_id, ctx.firewalls, monitor, timespan, metrics)
            self._collect_lb_metrics(ctx.sub_id, ctx.load_balancers, monitor, timespan, metrics)
            self._collect_er_metrics(ctx.sub_id, ctx.er_circuits, monitor, timespan, metrics)
            self._collect_ddos_metrics(ctx.sub_id, ctx.public_ips, monitor, timespan, metrics)
        except Exception as e:
            metrics.collection_error = str(e)

        self._compute_vnet_utilization(ctx.vnets, metrics)
        self._collect_nta_metrics(ctx.sub_id, ctx.la_workspaces, metrics)
        self._collect_cost_metrics(ctx.sub_id, metrics)
        self._collect_appgw_metrics(
            ctx.sub_id,
            ctx.appgws,
            monitor if not metrics.collection_error else None,
            timespan if not metrics.collection_error else "",
            metrics,
        )

        return metrics

    @staticmethod
    def _sum_metric_total(metric) -> float:
        """Sum all dp.total values across all timeseries for a Monitor metric result."""
        return sum(
            dp.total or 0 for ts in metric.timeseries for dp in ts.data if dp.total is not None
        )

    @staticmethod
    def _avg_metric_values(metric) -> list[float]:
        """Collect all non-None dp.average values across all timeseries."""
        return [dp.average for ts in metric.timeseries for dp in ts.data if dp.average is not None]

    @staticmethod
    def _max_metric_maximum(metric) -> float:
        """Return the max dp.maximum value across all timeseries (0 if none)."""
        return max(
            (
                dp.maximum or 0
                for ts in metric.timeseries
                for dp in ts.data
                if dp.maximum is not None
            ),
            default=0,
        )

    def _collect_gateway_metrics(self, sub_id, gateways, monitor, timespan, metrics) -> None:
        for gw in (gateways or [])[:5]:
            gm = GatewayMetric(
                gateway_name=gw.name,
                gateway_type=gw.gateway_type,
                bandwidth_mbps_provisioned=self._GW_SKU_BANDWIDTH.get(gw.sku_name),
            )
            try:
                result = monitor.metrics.list(
                    resource_uri=gw.id,
                    timespan=timespan,
                    interval="PT1H",
                    metricnames="TunnelIngressBytes,TunnelEgressBytes,AverageBandwidth",
                    aggregation="Total,Average",
                )
                for metric in result.value or []:
                    mn = metric.name.value if metric.name else ""
                    if mn == "TunnelIngressBytes":
                        gm.ingress_bytes_24h = self._sum_metric_total(metric)
                    elif mn == "TunnelEgressBytes":
                        gm.egress_bytes_24h = self._sum_metric_total(metric)
                    elif mn == "AverageBandwidth":
                        raw_bps_values = self._avg_metric_values(metric)
                        if raw_bps_values and gm.bandwidth_mbps_provisioned:
                            avg_mbps = (sum(raw_bps_values) / len(raw_bps_values)) / 1_000_000
                            gm.utilization_pct = round(
                                (avg_mbps / gm.bandwidth_mbps_provisioned) * 100, 1
                            )
            except Exception as e:
                logger.debug("[%s] Gateway metrics for %s failed: %s", sub_id, gw.name, e)
            metrics.gateway_metrics.append(gm)

    def _collect_firewall_metrics(self, sub_id, firewalls, monitor, timespan, metrics) -> None:
        for fw in (firewalls or [])[:5]:
            fm = FirewallMetric(firewall_name=fw.name)
            try:
                result = monitor.metrics.list(
                    resource_uri=fw.id,
                    timespan=timespan,
                    interval="PT1H",
                    metricnames="DataProcessed,ApplicationRuleHit,NetworkRuleHit,NatRuleHit",
                    aggregation="Total",
                )
                for metric in result.value or []:
                    mn = metric.name.value if metric.name else ""
                    total = self._sum_metric_total(metric)
                    if mn == "DataProcessed":
                        fm.data_processed_gb_24h = round(total / 1_073_741_824, 3)
                    elif mn == "ApplicationRuleHit":
                        fm.app_rule_hits_24h = int(total)
                    elif mn == "NetworkRuleHit":
                        fm.network_rule_hits_24h = int(total)
                    elif mn == "NatRuleHit":
                        fm.nat_rule_hits_24h = int(total)
            except Exception as e:
                fm.collection_error = str(e)
                logger.debug("[%s] Firewall metrics for %s failed: %s", sub_id, fw.name, e)
            metrics.firewall_metrics.append(fm)

    def _collect_lb_metrics(self, sub_id, load_balancers, monitor, timespan, metrics) -> None:
        for lb in (load_balancers or [])[:10]:
            lm = LoadBalancerMetric(lb_name=lb.name)
            try:
                result = monitor.metrics.list(
                    resource_uri=lb.id,
                    timespan=timespan,
                    interval="PT1H",
                    metricnames="SnatConnectionCount,UsedSnatPorts,AllocatedSnatPorts",
                    aggregation="Total,Average",
                )
                for metric in result.value or []:
                    mn = metric.name.value if metric.name else ""
                    if mn == "SnatConnectionCount":
                        lm.snat_connections_24h = self._sum_metric_total(metric)
                    elif mn in ("UsedSnatPorts", "AllocatedSnatPorts"):
                        vals = self._avg_metric_values(metric)
                        if vals:
                            avg = round(sum(vals) / len(vals), 1)
                            if mn == "UsedSnatPorts":
                                lm.used_snat_ports = avg
                            else:
                                lm.allocated_snat_ports = avg
                if lm.used_snat_ports and lm.allocated_snat_ports and lm.allocated_snat_ports > 0:
                    lm.snat_port_utilization_pct = round(
                        (lm.used_snat_ports / lm.allocated_snat_ports) * 100, 1
                    )
            except Exception as e:
                lm.collection_error = str(e)
                logger.debug("[%s] LB SNAT metrics for %s failed: %s", sub_id, lb.name, e)
            metrics.lb_metrics.append(lm)

    def _collect_er_metrics(self, sub_id, er_circuits, monitor, timespan, metrics) -> None:
        for erc in (er_circuits or [])[:5]:
            em = ERCircuitMetric(
                circuit_name=erc.name,
                bandwidth_mbps_provisioned=float(erc.bandwidth_mbps or 0) or None,
            )
            try:
                result = monitor.metrics.list(
                    resource_uri=erc.id,
                    timespan=timespan,
                    interval="PT1H",
                    metricnames="BitsInPerSecond,BitsOutPerSecond",
                    aggregation="Average",
                )
                for metric in result.value or []:
                    mn = metric.name.value if metric.name else ""
                    vals = self._avg_metric_values(metric)
                    if not vals:
                        continue
                    avg_bps = sum(vals) / len(vals)
                    if mn == "BitsInPerSecond":
                        em.primary_bits_in_per_second = round(avg_bps, 1)
                        if em.bandwidth_mbps_provisioned:
                            em.primary_utilization_pct = round(
                                (avg_bps / 1_000_000 / em.bandwidth_mbps_provisioned) * 100, 1
                            )
                    elif mn == "BitsOutPerSecond":
                        em.secondary_bits_in_per_second = round(avg_bps, 1)
                        if em.bandwidth_mbps_provisioned:
                            em.secondary_utilization_pct = round(
                                (avg_bps / 1_000_000 / em.bandwidth_mbps_provisioned) * 100, 1
                            )
            except Exception as e:
                em.collection_error = str(e)
                logger.debug("[%s] ER metrics for %s failed: %s", sub_id, erc.name, e)
            metrics.er_circuit_metrics.append(em)

    def _collect_ddos_metrics(self, sub_id, public_ips, monitor, timespan, metrics) -> None:
        for pip in (public_ips or [])[:20]:
            try:
                result = monitor.metrics.list(
                    resource_uri=pip.id,
                    timespan=timespan,
                    interval="PT1H",
                    metricnames="IfUnderDDoSAttack,DdosPacketsDropped",
                    aggregation="Maximum,Total",
                )
                under_attack = False
                for metric in result.value or []:
                    mn = metric.name.value if metric.name else ""
                    if mn == "IfUnderDDoSAttack":
                        if self._max_metric_maximum(metric) > 0:
                            under_attack = True
                            metrics.ddos_attack_events_24h += 1
                if under_attack and pip.ip_address:
                    metrics.public_ips_under_ddos_attack.append(pip.ip_address)
            except Exception as e:
                logger.debug("[%s] DDoS metrics for %s failed: %s", sub_id, pip.id, e)

    def _compute_vnet_utilization(self, vnets, metrics) -> None:
        import ipaddress

        for vnet in vnets or []:
            try:
                prefixes = vnet.address_space or []
                if not prefixes:
                    continue
                vnet_net = ipaddress.ip_network(prefixes[0], strict=False)
                vnet_size = vnet_net.num_addresses
                if vnet_size <= 0:
                    continue
                allocated = sum(
                    ipaddress.ip_network(s.address_prefix, strict=False).num_addresses
                    for s in (vnet.subnets or [])
                    if s.address_prefix
                )
                metrics.vnet_utilization[vnet.id] = round((allocated / vnet_size) * 100, 1)
            except Exception as e:
                logger.debug("VNet utilization calc failed for %s: %s", vnet.id, e)

    def _collect_nta_metrics(self, sub_id, la_workspaces, metrics) -> None:
        if not la_workspaces:
            return
        try:
            from azure.monitor.query import LogsQueryClient

            logs_client = LogsQueryClient(self._cred)
            nta_query = (
                "AzureNetworkAnalytics_CL"
                "| where TimeGenerated > ago(24h)"
                "| where SubType_s == 'FlowLog'"
                "| summarize Bytes=sum(FlowsByteCount_d) by FlowDirection_s"
            )
            east_west, north_south, queried_ws = self._nta_query_workspaces(
                sub_id, logs_client, nta_query, la_workspaces
            )
            if queried_ws:
                metrics.nta_east_west_bytes_24h = east_west
                metrics.nta_north_south_bytes_24h = north_south
                metrics.nta_query_workspace_id = queried_ws
        except ImportError:
            logger.debug("[%s] azure-monitor-query not installed; NTA query skipped", sub_id)
        except Exception as e:
            logger.debug("[%s] NTA query failed: %s", sub_id, e)

    def _nta_query_workspaces(
        self, sub_id, logs_client, nta_query, la_workspaces
    ) -> tuple[float, float, str | None]:
        """Query up to 3 LA workspaces for NTA flow data; return (east_west, north_south, ws_id)."""
        import datetime as _dt2
        from datetime import timedelta as _td

        from azure.monitor.query import LogsQueryStatus

        east_west: float = 0.0
        north_south: float = 0.0
        queried_ws: str | None = None
        for ws in (la_workspaces or [])[:3]:
            ws_id = ws.get("workspace_id") or ws.get("id", "")
            if not ws_id:
                continue
            try:
                resp = logs_client.query_workspace(
                    workspace_id=ws_id,
                    query=nta_query,
                    timespan=(
                        _dt2.datetime.now(_dt2.UTC) - _td(hours=24),
                        _dt2.datetime.now(_dt2.UTC),
                    ),
                )
                if resp.status == LogsQueryStatus.SUCCESS and resp.tables:
                    for row in resp.tables[0].rows:
                        direction = str(row[0]).strip()
                        byte_val = float(row[1] or 0)
                        if direction in ("E", "IntraVNet"):
                            east_west += byte_val
                        elif direction in ("I", "O", "Inbound", "Outbound"):
                            north_south += byte_val
                    queried_ws = ws_id
                    break
            except Exception as e:
                logger.debug("[%s] NTA query on %s failed: %s", sub_id, ws_id, e)
        return east_west, north_south, queried_ws

    def _collect_cost_metrics(self, sub_id, metrics) -> None:
        try:
            import datetime as _dt3

            from azure.mgmt.costmanagement import CostManagementClient
            from azure.mgmt.costmanagement.models import (
                QueryAggregation,
                QueryComparisonExpression,
                QueryDataset,
                QueryDefinition,
                QueryFilter,
                QueryTimePeriod,
                TimeframeType,
            )

            cost_client = CostManagementClient(self._cred)
            scope = f"/subscriptions/{sub_id}"
            today = _dt3.date.today()
            mtd_start = today.replace(day=1)

            query = QueryDefinition(
                type="ActualCost",
                timeframe=TimeframeType.CUSTOM,
                # QueryTimePeriod, not a dict: the field is declared
                # `QueryTimePeriod | None` and its attribute map serialises
                # from datetimes as iso-8601, so pre-formatted strings in a
                # dict were relying on the serialiser to coerce them
                # (TODO.md T-410).
                time_period=QueryTimePeriod(
                    from_property=_dt3.datetime.combine(mtd_start, _dt3.time.min, tzinfo=_dt3.UTC),
                    to=_dt3.datetime.combine(today, _dt3.time(23, 59, 59), tzinfo=_dt3.UTC),
                ),
                dataset=QueryDataset(
                    granularity="None",
                    aggregation={"TotalCost": QueryAggregation(name="Cost", function="Sum")},
                    filter=QueryFilter(
                        dimensions=QueryComparisonExpression(
                            name="MeterCategory",
                            operator="In",
                            values=["Virtual Network", "Bandwidth"],
                        )
                    ),
                ),
            )
            result = cost_client.query.usage(scope=scope, parameters=query)
            if result and result.rows:
                total_cost = sum(float(row[0] or 0) for row in result.rows)
                metrics.egress_cost_usd_mtd = round(total_cost, 4)
        except ImportError:
            logger.debug("[%s] azure-mgmt-costmanagement not installed; cost query skipped", sub_id)
        except Exception as e:
            logger.debug("[%s] Cost Management query failed: %s", sub_id, e)

    def _collect_appgw_metrics(self, sub_id, appgws, monitor, timespan, metrics) -> None:
        if monitor is None:
            return
        for ag in (appgws or [])[:10]:
            agm = AppGatewayMetric(appgw_name=ag.name)
            try:
                result = monitor.metrics.list(
                    resource_uri=ag.id,
                    timespan=timespan,
                    interval="PT1H",
                    metricnames=(
                        "CapacityUnits,BackendLastByteResponseTime,"
                        "FailedRequests,TotalRequests,ApplicationGatewayWAFRuleMatches"
                    ),
                    aggregation="Average,Total,Maximum",
                )
                for metric in result.value or []:
                    self._apply_appgw_metric(metric, agm)
            except Exception as e:
                agm.collection_error = str(e)
                logger.debug("[%s] App GW metrics for %s failed: %s", sub_id, ag.name, e)
            metrics.appgw_metrics.append(agm)

    @staticmethod
    def _apply_appgw_metric(metric, agm) -> None:
        """Apply one Monitor metric value to an AppGatewayMetric object."""
        mn = metric.name.value if metric.name else ""
        if mn == "CapacityUnits":
            avg_vals = AzureDiscovery._avg_metric_values(metric)
            max_vals = [
                dp.maximum for ts in metric.timeseries for dp in ts.data if dp.maximum is not None
            ]
            if avg_vals:
                agm.capacity_units_avg = round(sum(avg_vals) / len(avg_vals), 2)
            if max_vals:
                agm.capacity_units_max = round(max(max_vals), 2)
        elif mn == "BackendLastByteResponseTime":
            avg_vals = AzureDiscovery._avg_metric_values(metric)
            if avg_vals:
                agm.backend_latency_ms_avg = round(sum(avg_vals) / len(avg_vals), 1)
        elif mn == "FailedRequests":
            agm.failed_requests_24h = int(AzureDiscovery._sum_metric_total(metric))
        elif mn == "TotalRequests":
            agm.total_requests_24h = int(AzureDiscovery._sum_metric_total(metric))
        elif mn == "ApplicationGatewayWAFRuleMatches":
            agm.waf_rule_hits_24h = int(AzureDiscovery._sum_metric_total(metric))

    # ----------------------------------------------- Front Door WAF policies

    def _collect_front_door_waf_policies(self, sub_id: str) -> list[FrontDoorWAFPolicy]:
        """Enumerate Front Door (classic + Standard/Premium) WAF policies."""
        from azure.mgmt.network import NetworkManagementClient

        net = NetworkManagementClient(self._cred, sub_id)
        policies: list[FrontDoorWAFPolicy] = []
        try:
            for p in net.web_application_firewall_policies.list_all():
                # Only return Front Door policies (not App Gateway WAF policies).
                # Front Door WAF policies have kind == "FrontDoor" or no SKU sku name
                # containing "AppGateway".  Filter by resource type tag.
                sku_name = (p.sku.name if p.sku else "") or ""
                if "ApplicationGateway" in sku_name:
                    continue
                rg = (p.id or "").split("/")[4] if p.id else ""
                managed_count = sum(
                    len(rs.rule_sets or [])
                    for rs in (p.managed_rules.managed_rule_sets if p.managed_rules else [])
                )
                policies.append(
                    FrontDoorWAFPolicy(
                        id=p.id or "",
                        name=p.name or "",
                        resource_group=rg,
                        location=p.location or "global",
                        policy_mode=(p.policy_settings.mode if p.policy_settings else "Detection"),
                        policy_enabled_state=(
                            p.policy_settings.enabled_state if p.policy_settings else "Enabled"
                        ),
                        custom_rules_count=len(p.custom_rules.rules if p.custom_rules else []),
                        managed_rules_count=managed_count,
                        tags=dict(p.tags or {}),
                    )
                )
        except Exception as e:
            logger.debug("[%s] Front Door WAF policy enumeration failed: %s", sub_id, e)
        return policies

    # ------------------------------------------------- Defender for Cloud

    @staticmethod
    def _defender_status(item) -> str:
        try:
            return (item.status.code if item.status else "Unknown") or "Unknown"
        except Exception as _e:
            logger.debug("Could not read assessment status: %s", _e)
            return "Unknown"

    @staticmethod
    def _defender_meta(item) -> dict | None:
        """Return parsed metadata dict, or None if item should be skipped."""
        try:
            meta = item.metadata
            category = (meta.categories[0] if meta and meta.categories else None) or ""
            if "network" not in (category or "").lower():
                return None
            return {
                "category": category,
                "severity": (meta.severity if meta else "Medium") or "Medium",
                "description": meta.description if meta else None,
                "remediation": meta.remediation_description if meta else None,
                "effort": meta.implementation_effort if meta else None,
                "threats": list(meta.threats or []) if meta else [],
                "user_impact": meta.user_impact if meta else None,
                "display_name": (meta.display_name if meta else item.name) or item.name or "",
            }
        except Exception as _e:
            logger.debug("Could not read assessment metadata: %s", _e)
            return {
                "category": "Networking",
                "severity": "Medium",
                "description": None,
                "remediation": None,
                "effort": None,
                "threats": [],
                "user_impact": None,
                "display_name": item.name or "",
            }

    @staticmethod
    def _defender_resource(item) -> tuple[str | None, str | None]:
        try:
            if item.resource_details:
                return (
                    getattr(item.resource_details, "id", None),
                    getattr(item.resource_details, "resource_type", None),
                )
        except Exception as _e:
            logger.debug("Could not read assessment resource details: %s", _e)
        return None, None

    def _collect_defender_assessments(self, sub_id: str) -> list[DefenderAssessment]:
        """Collect Defender for Cloud security assessments filtered to Networking category.

        Requires SecurityReader or Security Admin on the subscription.
        Uses azure-mgmt-security (lazy import — optional dependency).
        Only Unhealthy assessments with a Networking category are returned; healthy
        pass-through assessments are skipped to keep the list actionable.
        """
        try:
            from azure.mgmt.security import SecurityCenter
        except ImportError:
            logger.debug("[%s] azure-mgmt-security not installed; Defender skipped", sub_id)
            return []

        assessments: list[DefenderAssessment] = []
        try:
            sc = SecurityCenter(self._cred, sub_id)
            scope = f"/subscriptions/{sub_id}"
            for item in sc.assessments.list(scope):
                status_code = self._defender_status(item)
                if status_code not in ("Unhealthy", "NotApplicable"):
                    continue
                meta = self._defender_meta(item)
                if meta is None:
                    continue
                resource_id, resource_type = self._defender_resource(item)
                effort = meta["effort"]
                user_impact = meta["user_impact"]
                assessments.append(
                    DefenderAssessment(
                        assessment_id=item.id or "",
                        display_name=meta["display_name"],
                        description=meta["description"],
                        remediation_description=meta["remediation"],
                        status=status_code,
                        severity=str(meta["severity"]),
                        resource_id=resource_id,
                        resource_type=resource_type,
                        category=meta["category"],
                        implementation_effort=str(effort) if effort else None,
                        threats=[str(t) for t in meta["threats"]],
                        user_impact=str(user_impact) if user_impact else None,
                    )
                )
        except Exception as e:
            logger.debug("[%s] Defender for Cloud assessments failed: %s", sub_id, e)
        return assessments

    # ----------------------------------------------------------------- run

    def run(self) -> AzureTopology:
        """Execute full Azure discovery. Returns completed AzureTopology."""
        engagement_id = self.store.engagement_id
        if engagement_id is None:
            raise ValueError(
                "EngagementStore is not bound to an engagement_id; "
                "construct it with EngagementStore(engagement_id=...) before discovery."
            )
        logger.info("[%s] Azure discovery starting (v1.2.0)", engagement_id)

        self.validate_access()

        topology = AzureTopology(
            engagement_id=engagement_id,
            tenant_id=self.opts.tenant_id,
        )

        # Management Group hierarchy
        topology.management_groups = self._collect_management_groups()
        logger.info(
            "[%s] %d management groups discovered", engagement_id, len(topology.management_groups)
        )

        # Subscriptions
        # When specific IDs are provided, bypass subscriptions.list() entirely.
        # list() requires Reader on the tenant root or management group — permissions
        # that a subscription-scoped SP won't have.  We already know the IDs; we just
        # need the display names (best-effort via subscriptions.get()).
        if self.opts.subscription_ids:
            self._progress(
                f"Specific subscription IDs provided — skipping list(), "
                f"going direct to {len(self.opts.subscription_ids)} subscription(s)."
            )
            all_subs = []
            for raw_id in self.opts.subscription_ids:
                sub_id = raw_id.strip()
                direct = self._get_subscription_direct(sub_id)
                if direct:
                    all_subs.append(direct)
                    self._progress(
                        f"  Confirmed: {direct['name']} ({direct['id']}) — state accessible"
                    )
                else:
                    # subscriptions.get() failed (insufficient permission on sub metadata),
                    # but the SP may still have network-level Reader and can run discovery.
                    # Use the ID as the name and proceed — ARM network calls will succeed
                    # or fail on their own with informative errors.
                    all_subs.append(
                        {"id": sub_id, "name": sub_id, "tenant_id": self.opts.tenant_id}
                    )
                    self._progress(
                        f"  subscriptions.get({sub_id}) failed — proceeding with "
                        f"discovery anyway (SP may have network-only Reader)."
                    )
        else:
            # No filter — list all accessible subscriptions in the tenant.
            all_subs = self._list_subscriptions()
            logger.info(
                "[%s] SP can see %d subscription(s) via list()", engagement_id, len(all_subs)
            )

        self._progress(f"Discovering {len(all_subs)} subscription(s)…")
        logger.info("[%s] Discovering %d subscription(s)", engagement_id, len(all_subs))

        for sub in all_subs:
            sub_id = sub["id"]
            sub_name = sub["name"]

            if self.opts.resume:
                checkpoints = self.store.list_completed_checkpoints(engagement_id, "azure")
                if any(sub_id in c for c in checkpoints):
                    logger.info(
                        "[%s] Skipping %s — checkpoint exists (--resume)", engagement_id, sub_id
                    )
                    continue

            logger.info("[%s] Subscription: %s (%s)", engagement_id, sub_id, sub_name)
            self._progress(f"Scanning subscription: {sub_name} ({sub_id})…")
            sub_topo = self._discover_subscription(sub_id, sub_name)
            topology.subscriptions.append(sub_topo)

            # Write checkpoint
            self.store.write_discovery_checkpoint(
                engagement_id,
                "azure",
                sub_id,
                json.loads(sub_topo.model_dump_json()),
            )

            vnet_count = len(sub_topo.vnets)
            nsg_count = len(sub_topo.nsgs)
            if sub_topo.discovery_blocked:
                self._progress(
                    f"  {sub_name}: BLOCKED — {sub_topo.block_reason or 'unknown error'}"
                )
            else:
                summary = (
                    f"  {sub_name}: {vnet_count} VNet(s), {nsg_count} NSG(s), "
                    f"{len(sub_topo.load_balancers)} LB(s), "
                    f"{len(sub_topo.virtual_network_gateways)} GW(s), "
                    f"{len(sub_topo.private_endpoints)} PE(s)"
                )
                self._progress(summary)
            logger.info(
                "[%s] %s: %d VNets, %d NSGs, %d LBs, %d GWs, %d PEs%s",
                engagement_id,
                sub_id,
                vnet_count,
                nsg_count,
                len(sub_topo.load_balancers),
                len(sub_topo.virtual_network_gateways),
                len(sub_topo.private_endpoints),
                " [BLOCKED]" if sub_topo.discovery_blocked else "",
            )

        logger.info(
            "[%s] Azure discovery complete. %d subscriptions collected.",
            engagement_id,
            len(topology.subscriptions),
        )
        return topology
