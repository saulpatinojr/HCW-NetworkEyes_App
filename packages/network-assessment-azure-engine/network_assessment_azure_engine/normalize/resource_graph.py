"""Resource Graph rows -> ``AzureTopology`` (REFACTOR_APP.md change sets C and D, section 9).

A row is ``{id, name, type, location, resourceGroup, subscriptionId, tags, zones, sku, kind,
properties}`` as ``az graph query`` or Resource Graph Explorer export it: ``type`` is
lower-cased, ``resourceGroup`` and ``subscriptionId`` are derived from ``id`` when absent.
``rows_from_document`` accepts the ``az graph query`` envelope ``{count, data, skip_token,
total_records}`` and records a warning when a ``skip_token`` remained unconsumed or
``total_records`` exceeds the rows received; ``normalize_resource_graph`` maps the rows.

References (``{id}`` objects in ``properties``) are resolved by id within the export; a reference
to a resource that is not in the export is kept as an id and recorded in ``warnings`` (it names the
resource type and the resource that referenced it, never cell content beyond the ids).
``microsoft.network/networkinterfaces`` rows are counted only; other ``microsoft.network/*`` types
are counted under ``unmapped_types``. Rows outside ``microsoft.network/`` are counted and ignored.

Ported from the downstream lab edition's reference implementation
(``HCW-NetworkEyes_AddOn`` ``src/network_assessment/ingestion/{arg_row,parse,normalize}.py``,
plan section 21), which it replaces once the edition adopts this package.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from network_assessment_azure_engine.model.azure import (
    AppGatewayWafPolicy,
    ApplicationGateway,
    AzureBastionHost,
    AzureFirewall,
    AzureFirewallPolicy,
    AzureGatewayConnection,
    AzureLBFrontendIP,
    AzureLBProbe,
    AzureLBRule,
    AzureLoadBalancer,
    AzureNatGateway,
    AzureNSG,
    AzurePrivateEndpoint,
    AzurePrivateEndpointConnection,
    AzurePublicIP,
    AzureRouteEntry,
    AzureRouteServer,
    AzureRouteTable,
    AzureSubnet,
    AzureSubscriptionTopology,
    AzureTopology,
    AzureVHub,
    AzureVirtualNetworkGateway,
    AzureVWan,
    ExpressRouteCircuit,
    FlowLog,
    FrontDoorWAFPolicy,
    NSGSecurityRule,
    PrivateDnsZone,
    VNet,
    VNetPeering,
)

PAGED_WARNING = "export is paged (skip_token present); only the first page was uploaded"
NO_PROPERTIES_WARNING = (
    "no properties column: rules that read properties answer unknown for this file"
)

# ── Rows ───────────────────────────────────────────────────────────────────

_ID_RG = re.compile(r"^/subscriptions/([^/]+)/resourcegroups/([^/]+)/", re.IGNORECASE)
_ID_SUB = re.compile(r"^/subscriptions/([^/]+)", re.IGNORECASE)


class ArgRow(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    type: str
    location: str | None = None
    resource_group: str | None = None
    subscription_id: str | None = None
    kind: str | None = None
    tags: dict[str, str] = Field(default_factory=dict)
    zones: list[str] = Field(default_factory=list)
    sku: dict[str, Any] = Field(default_factory=dict)
    properties: dict[str, Any] = Field(default_factory=dict)
    row: int = 0  # 1-based position in the export, for warnings

    @field_validator("type")
    @classmethod
    def _lower_type(cls, value: str) -> str:
        return value.strip().lower()

    @property
    def short_type(self) -> str:
        return self.type.removeprefix("microsoft.network/")

    @property
    def prop(self) -> dict[str, Any]:
        return self.properties


def _opt_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): ("" if v is None else str(v)) for k, v in value.items()}


def row_from_dict(raw: dict[str, Any], index: int) -> ArgRow | None:
    """Build an ArgRow or return None when the row has no usable type or id/name."""
    rtype = _opt_str(raw.get("type"))
    if not rtype:
        return None
    rid = _opt_str(raw.get("id"))
    name = _opt_str(raw.get("name"))
    rg = _opt_str(raw.get("resourceGroup"))
    sub = _opt_str(raw.get("subscriptionId"))
    if rid:
        m = _ID_RG.match(rid)
        if m:
            sub = sub or m.group(1)
            rg = rg or m.group(2)
        else:
            m2 = _ID_SUB.match(rid)
            if m2:
                sub = sub or m2.group(1)
        if not name:
            name = rid.rstrip("/").rsplit("/", 1)[-1]
    else:
        if not name:
            return None
        rid = f"/subscriptions/{sub or 'unknown'}/resourceGroups/{rg or 'unknown'}/providers/{rtype}/{name}"
    zones_raw = raw.get("zones")
    zones = [str(z) for z in zones_raw] if isinstance(zones_raw, list) else []
    sku = raw.get("sku")
    properties = raw.get("properties")
    return ArgRow(
        id=rid,
        name=name,
        type=rtype,
        location=_opt_str(raw.get("location")),
        resource_group=rg,
        subscription_id=sub,
        kind=_opt_str(raw.get("kind")),
        tags=_str_dict(raw.get("tags")),
        zones=zones,
        sku=sku if isinstance(sku, dict) else {},
        properties=properties if isinstance(properties, dict) else {},
        row=index,
    )


# ── Envelope ───────────────────────────────────────────────────────────────


def rows_from_document(document: Any) -> tuple[list[Any], list[str]]:
    """Accept a bare array or the `az graph query` envelope. Anything else is an invalid export."""
    warnings: list[str] = []
    if isinstance(document, list):
        return document, warnings
    if isinstance(document, dict):
        data = document.get("data")
        if isinstance(data, list):
            if document.get("skip_token") not in (None, ""):
                warnings.append(PAGED_WARNING)
            total = document.get("total_records")
            if isinstance(total, int) and total > len(data):
                warnings.append(f"export reports {total} records; {len(data)} were uploaded")
            return data, warnings
        raise ValueError("JSON object is not an az graph query envelope (no data array)")
    raise ValueError("JSON document is neither an array nor an az graph query envelope")


# ── Normalizer ─────────────────────────────────────────────────────────────

NETWORK_PREFIX = "microsoft.network/"
COUNTED_ONLY = frozenset({"microsoft.network/networkinterfaces"})
MAPPED_TYPES = frozenset(
    {
        "microsoft.network/virtualnetworks",
        "microsoft.network/networksecuritygroups",
        "microsoft.network/routetables",
        "microsoft.network/publicipaddresses",
        "microsoft.network/loadbalancers",
        "microsoft.network/virtualnetworkgateways",
        "microsoft.network/connections",
        "microsoft.network/privateendpoints",
        "microsoft.network/privateendpoints/privatednszonegroups",
        "microsoft.network/privatednszones",
        "microsoft.network/privatednszones/virtualnetworklinks",
        "microsoft.network/natgateways",
        "microsoft.network/bastionhosts",
        "microsoft.network/azurefirewalls",
        "microsoft.network/firewallpolicies",
        "microsoft.network/applicationgateways",
        "microsoft.network/applicationgatewaywebapplicationfirewallpolicies",
        "microsoft.network/expressroutecircuits",
        "microsoft.network/virtualwans",
        "microsoft.network/virtualhubs",
        "microsoft.network/networkwatchers/flowlogs",
        "microsoft.network/frontdoorwebapplicationfirewallpolicies",
    }
)
_PIP_OWNER_TYPES = (
    ("/networkinterfaces/", "NIC"),
    ("/loadbalancers/", "LB"),
    ("/applicationgateways/", "AppGW"),
    ("/azurefirewalls/", "Firewall"),
    ("/bastionhosts/", "Bastion"),
    ("/virtualnetworkgateways/", "Gateway"),
    ("/natgateways/", "NAT"),
)


@dataclass
class NormalizedExport:
    topology: AzureTopology
    rows: list[ArgRow]
    facts: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )  # resource id -> the fields the rules read
    warnings: list[str] = field(default_factory=list)


def _get(obj: Any, *path: str, default: Any = None) -> Any:
    for key in path:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key)
    return default if obj is None else obj


def _ref(obj: Any) -> str | None:
    value = _get(obj, "id")
    return str(value) if value else None


def _refs(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [r for r in (_ref(i) for i in items) if r]


def _strs(items: Any) -> list[str]:
    return [str(i) for i in items] if isinstance(items, list) else []


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "enabled"}
    return default


def _int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except TypeError, ValueError:
        return None


def _sub_from_id(rid: str) -> str:
    parts = rid.split("/")
    return parts[2] if len(parts) > 2 and parts[1].lower() == "subscriptions" else "unknown"


def _parent(rid: str, child_segment: str) -> str:
    marker = f"/{child_segment}/"
    idx = rid.lower().find(marker)
    return rid[:idx] if idx > 0 else rid


class _Normalizer:
    def __init__(self, rows: list[ArgRow], warnings: list[str], has_properties: bool) -> None:
        self.rows = rows
        self.has_properties = has_properties
        self.warnings: list[str] = list(warnings)
        self.index: dict[str, ArgRow] = {r.id.lower(): r for r in self.rows}
        self.by_type: dict[str, list[ArgRow]] = defaultdict(list)
        self.facts: dict[str, dict[str, Any]] = {}
        self._missing: set[tuple[str, str]] = set()
        for r in self.rows:
            self.by_type[r.type].append(r)

    # ── helpers ───────────────────────────────────────────────────────────

    def lookup(self, rid: str | None, what: str, referenced_by: ArgRow) -> ArgRow | None:
        """Resolve a reference within the export; record a warning once per missing id."""
        if not rid:
            return None
        row = self.index.get(rid.lower())
        if row is None:
            key = (what, rid.lower())
            if key not in self._missing:
                self._missing.add(key)
                self.warnings.append(
                    f"{what} {rid.rsplit('/', 1)[-1]} referenced by {referenced_by.short_type} {referenced_by.name} "
                    f"is not in the export: its settings cannot be evaluated"
                )
        return row

    def fact(self, row: ArgRow, **values: Any) -> None:
        self.facts[row.id] = {k: v for k, v in values.items() if v not in (None, [], {})}

    def rows_of(self, short_type: str) -> list[ArgRow]:
        return self.by_type.get(NETWORK_PREFIX + short_type, [])

    def rows_in(self, short_type: str, sub_id: str) -> list[ArgRow]:
        return [r for r in self.rows_of(short_type) if r.subscription_id == sub_id]

    # ── mappers ───────────────────────────────────────────────────────────

    def vnet(self, r: ArgRow) -> VNet:
        p = r.prop
        subnets: list[AzureSubnet] = []
        for s in _get(p, "subnets", default=[]) or []:
            sp = _get(s, "properties", default={}) or {}
            nsg_id = _ref(_get(sp, "networkSecurityGroup"))
            rt_id = _ref(_get(sp, "routeTable"))
            nsg_row = self.lookup(nsg_id, "network security group", r)
            rt_row = self.lookup(rt_id, "route table", r)
            delegations = _get(sp, "delegations", default=[]) or []
            delegation = _get(delegations[0], "properties", "serviceName") if delegations else None
            prefixes = _strs(_get(sp, "addressPrefixes", default=[]))
            prefix = _get(sp, "addressPrefix") or (prefixes[0] if prefixes else "")
            subnets.append(
                AzureSubnet(
                    id=str(_get(s, "id") or f"{r.id}/subnets/{_get(s, 'name')}"),
                    name=str(_get(s, "name") or ""),
                    address_prefix=str(prefix),
                    address_prefixes=prefixes,
                    nsg_id=nsg_id,
                    nsg_name=nsg_row.name if nsg_row else None,
                    route_table_id=rt_id,
                    route_table_name=rt_row.name if rt_row else None,
                    nat_gateway_id=_ref(_get(sp, "natGateway")),
                    service_endpoints=[
                        str(_get(e, "service"))
                        for e in _get(sp, "serviceEndpoints", default=[]) or []
                    ],
                    private_endpoint_network_policies=str(
                        _get(sp, "privateEndpointNetworkPolicies") or "Enabled"
                    ),
                    default_outbound_access=_bool(_get(sp, "defaultOutboundAccess"), True),
                    delegation=str(delegation) if delegation else None,
                    ip_configuration_count=len(_get(sp, "ipConfigurations", default=[]) or []),
                )
            )
        peerings: list[VNetPeering] = []
        for pe in _get(p, "virtualNetworkPeerings", default=[]) or []:
            pp = _get(pe, "properties", default={}) or {}
            remote_id = _ref(_get(pp, "remoteVirtualNetwork")) or ""
            remote_row = self.index.get(remote_id.lower()) if remote_id else None
            peerings.append(
                VNetPeering(
                    id=str(_get(pe, "id") or f"{r.id}/virtualNetworkPeerings/{_get(pe, 'name')}"),
                    name=str(_get(pe, "name") or ""),
                    remote_vnet_id=remote_id,
                    remote_vnet_name=remote_row.name if remote_row else None,
                    remote_subscription_id=_sub_from_id(remote_id) if remote_id else "unknown",
                    peering_state=str(_get(pp, "peeringState") or "Unknown"),
                    allow_forwarded_traffic=_bool(_get(pp, "allowForwardedTraffic")),
                    allow_gateway_transit=_bool(_get(pp, "allowGatewayTransit")),
                    use_remote_gateways=_bool(_get(pp, "useRemoteGateways")),
                    do_not_verify_remote_gateways=_bool(_get(pp, "doNotVerifyRemoteGateways")),
                    peer_complete_vnets=_bool(_get(pp, "peerCompleteVnets"), True),
                )
            )
        dns = _strs(_get(p, "dhcpOptions", "dnsServers", default=[]))
        address_space = _strs(_get(p, "addressSpace", "addressPrefixes", default=[]))
        self.fact(
            r,
            addressSpace=address_space,
            dnsServers=dns,
            subnets=len(subnets),
            peerings=len(peerings),
            enableDdosProtection=_bool(_get(p, "enableDdosProtection")),
        )
        return VNet(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            subscription_id=r.subscription_id or "unknown",
            address_space=address_space,
            dns_servers=dns,
            subnets=subnets,
            peerings=peerings,
            ddos_protection_enabled=_bool(_get(p, "enableDdosProtection")),
            ddos_protection_plan_id=_ref(_get(p, "ddosProtectionPlan")),
            encryption_enabled=_bool(_get(p, "encryption", "enabled")),
            tags=r.tags,
        )

    @staticmethod
    def _nsg_rule(entry: Any, default: bool) -> NSGSecurityRule:
        p = _get(entry, "properties", default={}) or {}
        return NSGSecurityRule(
            name=str(_get(entry, "name") or ""),
            priority=_int(_get(p, "priority")) or 0,
            direction=str(_get(p, "direction") or ""),
            access=str(_get(p, "access") or ""),
            protocol=str(_get(p, "protocol") or "*"),
            source_port_range=_get(p, "sourcePortRange"),
            source_port_ranges=_strs(_get(p, "sourcePortRanges", default=[])),
            destination_port_range=_get(p, "destinationPortRange"),
            destination_port_ranges=_strs(_get(p, "destinationPortRanges", default=[])),
            source_address_prefix=_get(p, "sourceAddressPrefix"),
            source_address_prefixes=_strs(_get(p, "sourceAddressPrefixes", default=[])),
            source_asgs=_refs(_get(p, "sourceApplicationSecurityGroups", default=[])),
            destination_address_prefix=_get(p, "destinationAddressPrefix"),
            destination_address_prefixes=_strs(_get(p, "destinationAddressPrefixes", default=[])),
            destination_asgs=_refs(_get(p, "destinationApplicationSecurityGroups", default=[])),
            description=_get(p, "description"),
            is_default_rule=default,
        )

    def nsg(self, r: ArgRow) -> AzureNSG:
        p = r.prop
        rules = [self._nsg_rule(e, False) for e in _get(p, "securityRules", default=[]) or []]
        self.fact(
            r,
            securityRules=len(rules),
            subnets=len(_refs(_get(p, "subnets"))),
            flowLogs=len(_refs(_get(p, "flowLogs"))),
        )
        return AzureNSG(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            security_rules=rules,
            default_security_rules=[
                self._nsg_rule(e, True) for e in _get(p, "defaultSecurityRules", default=[]) or []
            ],
            associated_subnet_ids=_refs(_get(p, "subnets")),
            associated_nic_ids=_refs(_get(p, "networkInterfaces")),
            flow_log_ids=_refs(_get(p, "flowLogs")),
            tags=r.tags,
        )

    def route_table(self, r: ArgRow) -> AzureRouteTable:
        p = r.prop
        routes = [
            AzureRouteEntry(
                name=str(_get(e, "name") or ""),
                address_prefix=str(_get(e, "properties", "addressPrefix") or ""),
                next_hop_type=str(_get(e, "properties", "nextHopType") or ""),
                next_hop_ip=_get(e, "properties", "nextHopIpAddress"),
                has_bgp_override=_bool(_get(e, "properties", "hasBgpOverride")),
            )
            for e in _get(p, "routes", default=[]) or []
        ]
        self.fact(
            r,
            routes=[f"{x.address_prefix} -> {x.next_hop_type}" for x in routes],
            disableBgpRoutePropagation=_bool(_get(p, "disableBgpRoutePropagation")),
        )
        return AzureRouteTable(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            routes=routes,
            associated_subnet_ids=_refs(_get(p, "subnets")),
            disable_bgp_route_propagation=_bool(_get(p, "disableBgpRoutePropagation")),
            tags=r.tags,
        )

    def public_ip(self, r: ArgRow) -> AzurePublicIP:
        p = r.prop
        owner = _ref(_get(p, "ipConfiguration")) or _ref(_get(p, "natGateway"))
        owner_type = None
        if owner:
            low = owner.lower()
            owner_type = next((t for marker, t in _PIP_OWNER_TYPES if marker in low), "Other")
        self.fact(
            r,
            sku=_get(r.sku, "name"),
            allocationMethod=_get(p, "publicIPAllocationMethod"),
            attachedTo=owner_type,
        )
        return AzurePublicIP(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            sku_name=str(_get(r.sku, "name") or "Basic"),
            allocation_method=str(_get(p, "publicIPAllocationMethod") or "Dynamic"),
            ip_address=_get(p, "ipAddress"),
            ip_version=str(_get(p, "publicIPAddressVersion") or "IPv4"),
            dns_label=_get(p, "dnsSettings", "domainNameLabel"),
            fqdn=_get(p, "dnsSettings", "fqdn"),
            zones=r.zones,
            associated_resource_id=owner,
            associated_resource_type=owner_type,
            ddos_protection_mode=str(
                _get(p, "ddosSettings", "protectionMode") or "VirtualNetworkInherited"
            ),
            tags=r.tags,
        )

    def load_balancer(self, r: ArgRow) -> AzureLoadBalancer:
        p = r.prop
        frontends = [
            AzureLBFrontendIP(
                name=str(_get(f, "name") or ""),
                public_ip_id=_ref(_get(f, "properties", "publicIPAddress")),
                private_ip_address=_get(f, "properties", "privateIPAddress"),
                private_ip_allocation_method=_get(f, "properties", "privateIPAllocationMethod"),
                subnet_id=_ref(_get(f, "properties", "subnet")),
                zones=_strs(_get(f, "zones", default=[])),
            )
            for f in _get(p, "frontendIPConfigurations", default=[]) or []
        ]
        rules = [
            AzureLBRule(
                name=str(_get(e, "name") or ""),
                protocol=str(_get(e, "properties", "protocol") or "Tcp"),
                frontend_port=_int(_get(e, "properties", "frontendPort")) or 0,
                backend_port=_int(_get(e, "properties", "backendPort")) or 0,
                enable_floating_ip=_bool(_get(e, "properties", "enableFloatingIP")),
                enable_tcp_reset=_bool(_get(e, "properties", "enableTcpReset")),
                idle_timeout_minutes=_int(_get(e, "properties", "idleTimeoutInMinutes")) or 4,
                load_distribution=str(_get(e, "properties", "loadDistribution") or "Default"),
                disable_outbound_snat=_bool(_get(e, "properties", "disableOutboundSnat")),
            )
            for e in _get(p, "loadBalancingRules", default=[]) or []
        ]
        probes = [
            AzureLBProbe(
                name=str(_get(e, "name") or ""),
                protocol=str(_get(e, "properties", "protocol") or "Tcp"),
                port=_int(_get(e, "properties", "port")) or 0,
                interval_seconds=_int(_get(e, "properties", "intervalInSeconds")) or 15,
                number_of_probes=_int(_get(e, "properties", "numberOfProbes")) or 2,
                request_path=_get(e, "properties", "requestPath"),
            )
            for e in _get(p, "probes", default=[]) or []
        ]
        lb_type = "Public" if any(f.public_ip_id for f in frontends) else "Internal"
        self.fact(
            r, sku=_get(r.sku, "name"), type=lb_type, frontends=len(frontends), rules=len(rules)
        )
        return AzureLoadBalancer(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            sku_name=str(_get(r.sku, "name") or "Basic"),
            lb_type=lb_type,
            frontend_ip_configs=frontends,
            lb_rules=rules,
            probes=probes,
            backend_pool_ids=_refs(_get(p, "backendAddressPools")),
            inbound_nat_rule_count=len(_get(p, "inboundNatRules", default=[]) or []),
            zones=r.zones,
            tags=r.tags,
        )

    def gateway(self, r: ArgRow, connections: list[ArgRow]) -> AzureVirtualNetworkGateway:
        p = r.prop
        ipconfigs = _get(p, "ipConfigurations", default=[]) or []
        subnet_id = next(
            (
                _ref(_get(c, "properties", "subnet"))
                for c in ipconfigs
                if _ref(_get(c, "properties", "subnet"))
            ),
            None,
        )
        pips = [x for x in (_ref(_get(c, "properties", "publicIPAddress")) for c in ipconfigs) if x]
        conns = []
        for c in connections:
            cp = c.prop
            conns.append(
                AzureGatewayConnection(
                    id=c.id,
                    name=c.name,
                    connection_type=str(_get(cp, "connectionType") or ""),
                    connection_status=str(_get(cp, "connectionStatus") or "Unknown"),
                    remote_vnet_id=_ref(_get(cp, "virtualNetworkGateway2")),
                    local_network_gateway_id=_ref(_get(cp, "localNetworkGateway2")),
                    express_route_circuit_id=_ref(_get(cp, "peer")),
                    routing_weight=_int(_get(cp, "routingWeight")) or 10,
                    enable_bgp=_bool(_get(cp, "enableBgp")),
                    use_policy_based_traffic_selectors=_bool(
                        _get(cp, "usePolicyBasedTrafficSelectors")
                    ),
                    shared_key_set=_get(cp, "sharedKey") is not None,  # the value is never read
                )
            )
        sku_name = str(_get(p, "sku", "name") or _get(r.sku, "name") or "Basic")
        self.fact(
            r,
            gatewayType=_get(p, "gatewayType"),
            sku=sku_name,
            activeActive=_bool(_get(p, "activeActive")),
            generation=_get(p, "vpnGatewayGeneration"),
            connections=[f"{c.name}: {c.connection_status}" for c in conns],
        )
        return AzureVirtualNetworkGateway(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            gateway_type=str(_get(p, "gatewayType") or "Vpn"),
            vpn_type=_get(p, "vpnType"),
            sku_name=sku_name,
            sku_tier=str(_get(p, "sku", "tier") or sku_name),
            active_active=_bool(_get(p, "activeActive")),
            enable_bgp=_bool(_get(p, "enableBgp")),
            bgp_asn=_int(_get(p, "bgpSettings", "asn")),
            public_ip_ids=pips,
            subnet_id=subnet_id,
            connections=conns,
            generation=_get(p, "vpnGatewayGeneration"),
            zones=r.zones,
            tags=r.tags,
        )

    def private_endpoint(self, r: ArgRow, zone_groups: list[ArgRow]) -> AzurePrivateEndpoint:
        p = r.prop
        conns = []
        for c in (_get(p, "privateLinkServiceConnections", default=[]) or []) + (
            _get(p, "manualPrivateLinkServiceConnections", default=[]) or []
        ):
            cp = _get(c, "properties", default={}) or {}
            conns.append(
                AzurePrivateEndpointConnection(
                    connection_name=str(_get(c, "name") or ""),
                    private_link_service_id=str(_get(cp, "privateLinkServiceId") or ""),
                    group_ids=_strs(_get(cp, "groupIds", default=[])),
                    connection_state=str(
                        _get(cp, "privateLinkServiceConnectionState", "status") or "Unknown"
                    ),
                )
            )
        zone_names = [
            str(_get(z, "name"))
            for g in zone_groups
            for z in _get(g.prop, "privateDnsZoneConfigs", default=[]) or []
            if _get(z, "name")
        ]
        self.fact(
            r,
            connections=[f"{c.connection_name}: {c.connection_state}" for c in conns],
            dnsZoneGroups=zone_names,
        )
        return AzurePrivateEndpoint(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            subnet_id=_ref(_get(p, "subnet")),
            service_connections=conns,
            dns_zone_group_names=zone_names,
            custom_dns_configs=[
                str(_get(d, "fqdn"))
                for d in _get(p, "customDnsConfigs", default=[]) or []
                if _get(d, "fqdn")
            ],
            tags=r.tags,
        )

    def private_dns_zone(self, r: ArgRow, links: list[ArgRow]) -> PrivateDnsZone:
        vnet_ids = [x for x in (_ref(_get(link.prop, "virtualNetwork")) for link in links) if x]
        names = []
        for vid in vnet_ids:
            row = self.lookup(vid, "virtual network", r)
            names.append(row.name if row else vid.rsplit("/", 1)[-1])
        self.fact(r, recordSets=_int(_get(r.prop, "numberOfRecordSets")), linkedVnets=names)
        return PrivateDnsZone(
            id=r.id,
            name=r.name,
            resource_group=r.resource_group or "",
            linked_vnet_ids=vnet_ids,
            linked_vnet_names=names,
            auto_registration_enabled=any(
                _bool(_get(link.prop, "registrationEnabled")) for link in links
            ),
            record_count=_int(_get(r.prop, "numberOfRecordSets")) or 0,
        )

    def nat_gateway(self, r: ArgRow) -> AzureNatGateway:
        p = r.prop
        subnets = _refs(_get(p, "subnets"))
        self.fact(
            r,
            sku=_get(r.sku, "name"),
            subnets=len(subnets),
            publicIps=len(_refs(_get(p, "publicIpAddresses"))),
        )
        return AzureNatGateway(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            sku_name=str(_get(r.sku, "name") or "Standard"),
            idle_timeout_minutes=_int(_get(p, "idleTimeoutInMinutes")) or 4,
            public_ip_ids=_refs(_get(p, "publicIpAddresses")),
            public_ip_prefix_ids=_refs(_get(p, "publicIpPrefixes")),
            associated_subnet_ids=subnets,
            zones=r.zones,
            tags=r.tags,
        )

    def bastion(self, r: ArgRow) -> AzureBastionHost:
        p = r.prop
        ipconfigs = _get(p, "ipConfigurations", default=[]) or []
        first = ipconfigs[0] if ipconfigs else {}
        self.fact(
            r,
            sku=_get(r.sku, "name"),
            scaleUnits=_int(_get(p, "scaleUnits")),
            tunneling=_bool(_get(p, "enableTunneling")),
        )
        return AzureBastionHost(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            sku_name=str(_get(r.sku, "name") or "Basic"),
            subnet_id=_ref(_get(first, "properties", "subnet")),
            public_ip_id=_ref(_get(first, "properties", "publicIPAddress")),
            scale_units=_int(_get(p, "scaleUnits")) or 2,
            tunneling_enabled=_bool(_get(p, "enableTunneling")),
            shareable_link_enabled=_bool(_get(p, "enableShareableLink")),
            ip_connect_enabled=_bool(_get(p, "enableIpConnect")),
            file_copy_enabled=_bool(_get(p, "enableFileCopy")),
            kerberos_enabled=_bool(_get(p, "enableKerberos")),
            tags=r.tags,
        )

    def firewall_policy(self, r: ArgRow) -> AzureFirewallPolicy:
        p = r.prop
        self.fact(
            r,
            threatIntelMode=_get(p, "threatIntelMode"),
            tier=_get(p, "sku", "tier"),
            dnsProxy=_bool(_get(p, "dnsSettings", "enableProxy")),
        )
        return AzureFirewallPolicy(
            id=r.id,
            name=r.name,
            resource_group=r.resource_group or "",
            sku_tier=_get(p, "sku", "tier"),
            threat_intel_mode=_get(p, "threatIntelMode"),
            dns_proxy_enabled=_bool(_get(p, "dnsSettings", "enableProxy")),
            intrusion_detection_mode=_get(p, "intrusionDetection", "mode"),
        )

    def firewall(self, r: ArgRow, policies: dict[str, AzureFirewallPolicy]) -> AzureFirewall:
        p = r.prop
        ipconfigs = _get(p, "ipConfigurations", default=[]) or []
        policy_id = _ref(_get(p, "firewallPolicy"))
        policy = policies.get(policy_id.lower()) if policy_id else None
        if policy_id and policy is None:
            self.lookup(policy_id, "firewall policy", r)
        fw = AzureFirewall(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            sku_tier=str(_get(p, "sku", "tier") or "Standard"),
            subnet_id=next(
                (
                    _ref(_get(c, "properties", "subnet"))
                    for c in ipconfigs
                    if _ref(_get(c, "properties", "subnet"))
                ),
                None,
            ),
            public_ip_ids=[
                x for x in (_ref(_get(c, "properties", "publicIPAddress")) for c in ipconfigs) if x
            ],
            policy_id=policy_id,
            firewall_policy=policy,
            threat_intel_mode=str(_get(p, "threatIntelMode") or "Alert"),
            zones=r.zones,
            tags=r.tags,
        )
        self.fact(
            r,
            tier=fw.sku_tier,
            threatIntelMode=fw.effective_threat_intel_mode,
            zones=r.zones,
            policy=policy.name if policy else None,
        )
        return fw

    def waf_policy(self, r: ArgRow) -> AppGatewayWafPolicy:
        p = r.prop
        self.fact(
            r, state=_get(p, "policySettings", "state"), mode=_get(p, "policySettings", "mode")
        )
        return AppGatewayWafPolicy(
            id=r.id,
            name=r.name,
            resource_group=r.resource_group or "",
            state=_get(p, "policySettings", "state"),
            mode=_get(p, "policySettings", "mode"),
        )

    def app_gateway(
        self, r: ArgRow, policies: dict[str, AppGatewayWafPolicy]
    ) -> ApplicationGateway:
        p = r.prop
        gw_configs = _get(p, "gatewayIPConfigurations", default=[]) or []
        waf = _get(p, "webApplicationFirewallConfiguration", default={}) or {}
        policy_id = _ref(_get(p, "firewallPolicy"))
        policy = policies.get(policy_id.lower()) if policy_id else None
        if policy_id and policy is None:
            self.lookup(policy_id, "WAF policy", r)
        agw = ApplicationGateway(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            sku_name=str(_get(p, "sku", "name") or "Standard_v2"),
            sku_tier=_get(p, "sku", "tier"),
            sku_capacity=_int(_get(p, "sku", "capacity")),
            subnet_id=next(
                (
                    _ref(_get(c, "properties", "subnet"))
                    for c in gw_configs
                    if _ref(_get(c, "properties", "subnet"))
                ),
                None,
            ),
            waf_enabled=_bool(_get(waf, "enabled")),
            waf_mode=_get(waf, "firewallMode"),
            waf_rule_set_type=_get(waf, "ruleSetType"),
            waf_rule_set_version=_get(waf, "ruleSetVersion"),
            waf_policy_id=policy_id,
            waf_policy=policy,
            ssl_policy_name=_get(p, "sslPolicy", "policyName"),
            autoscale_min=_int(_get(p, "autoscaleConfiguration", "minCapacity")),
            autoscale_max=_int(_get(p, "autoscaleConfiguration", "maxCapacity")),
            zones=r.zones,
            tags=r.tags,
        )
        self.fact(
            r,
            sku=agw.sku_name,
            wafEnabled=agw.waf_enabled
            or bool(policy and (policy.state or "").lower() == "enabled"),
            wafMode=(policy.mode if policy else agw.waf_mode),
            zones=r.zones,
        )
        return agw

    def er_circuit(self, r: ArgRow) -> ExpressRouteCircuit:
        p = r.prop
        spp = _get(p, "serviceProviderProperties", default={}) or {}
        self.fact(
            r,
            provider=_get(spp, "serviceProviderName"),
            bandwidthMbps=_int(_get(spp, "bandwidthInMbps")),
            tier=_get(r.sku, "tier"),
        )
        return ExpressRouteCircuit(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            service_provider=_get(spp, "serviceProviderName"),
            peering_location=_get(spp, "peeringLocation"),
            bandwidth_mbps=_int(_get(spp, "bandwidthInMbps")),
            sku_tier=str(_get(r.sku, "tier") or _get(p, "sku", "tier") or "Standard"),
            sku_family=str(_get(r.sku, "family") or _get(p, "sku", "family") or "MeteredData"),
            circuit_provisioning_state=str(_get(p, "circuitProvisioningState") or "Enabled"),
            global_reach_enabled=_bool(_get(p, "globalReachEnabled")),
            peering_types=[
                str(_get(x, "properties", "peeringType"))
                for x in _get(p, "peerings", default=[]) or []
                if _get(x, "properties", "peeringType")
            ],
            tags=r.tags,
        )

    def vhub(self, r: ArgRow) -> AzureVHub:
        p = r.prop
        self.fact(
            r,
            addressPrefix=_get(p, "addressPrefix"),
            securedByFirewall=bool(_ref(_get(p, "azureFirewall"))),
            connections=len(_refs(_get(p, "virtualNetworkConnections"))),
        )
        return AzureVHub(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            address_prefix=str(_get(p, "addressPrefix") or ""),
            sku=str(_get(p, "sku") or "Standard"),
            connected_vnet_ids=_refs(_get(p, "virtualNetworkConnections")),
            express_route_gateway_id=_ref(_get(p, "expressRouteGateway")),
            azure_firewall_id=_ref(_get(p, "azureFirewall")),
            routing_state=str(_get(p, "routingState") or "Provisioned"),
            virtual_router_asn=_int(_get(p, "virtualRouterAsn")),
            virtual_router_ips=_strs(_get(p, "virtualRouterIps", default=[])),
        )

    def route_server(self, r: ArgRow) -> AzureRouteServer:
        p = r.prop
        self.fact(
            r,
            asn=_int(_get(p, "virtualRouterAsn")),
            branchToBranch=_bool(_get(p, "allowBranchToBranchTraffic")),
        )
        return AzureRouteServer(
            id=r.id,
            name=r.name,
            location=r.location or "",
            resource_group=r.resource_group or "",
            virtual_router_asn=_int(_get(p, "virtualRouterAsn")),
            virtual_router_ips=_strs(_get(p, "virtualRouterIps", default=[])),
            allow_branch_to_branch_traffic=_bool(_get(p, "allowBranchToBranchTraffic")),
            hub_routing_preference=_get(p, "hubRoutingPreference"),
            tags=r.tags,
        )

    def flow_log(self, r: ArgRow) -> FlowLog:
        p = r.prop
        ta = _bool(
            _get(
                p,
                "flowAnalyticsConfiguration",
                "networkWatcherFlowAnalyticsConfiguration",
                "enabled",
            )
        )
        self.fact(
            r,
            target=str(_get(p, "targetResourceId") or "").rsplit("/", 1)[-1],
            enabled=_bool(_get(p, "enabled"), True),
            trafficAnalytics=ta,
        )
        return FlowLog(
            id=r.id,
            name=r.name,
            target_resource_id=str(_get(p, "targetResourceId") or ""),
            enabled=_bool(_get(p, "enabled"), True),
            traffic_analytics_enabled=ta,
            retention_days=_int(_get(p, "retentionPolicy", "days")),
        )

    def front_door_waf(self, r: ArgRow) -> FrontDoorWAFPolicy:
        p = r.prop
        self.fact(
            r,
            mode=_get(p, "policySettings", "mode"),
            enabledState=_get(p, "policySettings", "enabledState"),
        )
        return FrontDoorWAFPolicy(
            id=r.id,
            name=r.name,
            resource_group=r.resource_group or "",
            location=r.location or "global",
            policy_mode=str(_get(p, "policySettings", "mode") or "Detection"),
            policy_enabled_state=str(_get(p, "policySettings", "enabledState") or "Enabled"),
            custom_rules_count=len(_get(p, "customRules", "rules", default=[]) or []),
            managed_rules_count=len(_get(p, "managedRules", "managedRuleSets", default=[]) or []),
            tags=r.tags,
        )

    # ── assembly ──────────────────────────────────────────────────────────

    def subscription(self, sub_id: str) -> AzureSubscriptionTopology:
        rows = lambda t: self.rows_in(t, sub_id)  # noqa: E731
        fw_policies = {
            x.id.lower(): x for x in (self.firewall_policy(r) for r in rows("firewallpolicies"))
        }
        waf_policies = {
            x.id.lower(): x
            for x in (
                self.waf_policy(r) for r in rows("applicationgatewaywebapplicationfirewallpolicies")
            )
        }
        # policies in other subscriptions still resolve: index them globally
        for r in self.rows_of("firewallpolicies"):
            fw_policies.setdefault(r.id.lower(), self.firewall_policy(r))
        for r in self.rows_of("applicationgatewaywebapplicationfirewallpolicies"):
            waf_policies.setdefault(r.id.lower(), self.waf_policy(r))

        connections_by_gw: dict[str, list[ArgRow]] = defaultdict(list)
        for c in rows("connections"):
            gw_id = _ref(_get(c.prop, "virtualNetworkGateway1"))
            if gw_id and self.lookup(gw_id, "virtual network gateway", c):
                connections_by_gw[gw_id.lower()].append(c)
        zone_groups: dict[str, list[ArgRow]] = defaultdict(list)
        for g in rows("privateendpoints/privatednszonegroups"):
            zone_groups[_parent(g.id, "privatednszonegroups").lower()].append(g)
        links: dict[str, list[ArgRow]] = defaultdict(list)
        for link in rows("privatednszones/virtualnetworklinks"):
            links[_parent(link.id, "virtualnetworklinks").lower()].append(link)

        hubs_by_wan: dict[str, list[AzureVHub]] = defaultdict(list)
        route_servers: list[AzureRouteServer] = []
        for r in rows("virtualhubs"):
            if (r.kind or "").lower() == "routeserver":
                route_servers.append(self.route_server(r))
            else:
                hubs_by_wan[(_ref(_get(r.prop, "virtualWan")) or "").lower()].append(self.vhub(r))
        wans: list[AzureVWan] = []
        for r in rows("virtualwans"):
            self.fact(
                r,
                sku=_get(r.prop, "type") or _get(r.sku, "name"),
                hubs=len(hubs_by_wan.get(r.id.lower(), [])),
            )
            wans.append(
                AzureVWan(
                    id=r.id,
                    name=r.name,
                    resource_group=r.resource_group or "",
                    sku=str(_get(r.prop, "type") or "Standard"),
                    hubs=hubs_by_wan.pop(r.id.lower(), []),
                    allow_vnet_to_vnet_traffic=_bool(_get(r.prop, "allowVnetToVnetTraffic"), True),
                    allow_branch_to_branch_traffic=_bool(
                        _get(r.prop, "allowBranchToBranchTraffic"), True
                    ),
                    tags=r.tags,
                )
            )
        for wan_id, hubs in hubs_by_wan.items():
            if not wan_id or self.index.get(wan_id) is None:
                self.warnings.append(
                    f"virtual WAN {wan_id.rsplit('/', 1)[-1] or '(unknown)'} referenced by {len(hubs)} virtual hub(s) "
                    "is not in the export"
                )
                wans.append(
                    AzureVWan(
                        id=wan_id or "unknown",
                        name=wan_id.rsplit("/", 1)[-1] or "unknown",
                        resource_group="",
                        sku="Standard",
                        hubs=hubs,
                    )
                )

        sub = AzureSubscriptionTopology(
            subscription_id=sub_id,
            vnets=[self.vnet(r) for r in rows("virtualnetworks")],
            nsgs=[self.nsg(r) for r in rows("networksecuritygroups")],
            route_tables=[self.route_table(r) for r in rows("routetables")],
            virtual_network_gateways=[
                self.gateway(r, connections_by_gw.get(r.id.lower(), []))
                for r in rows("virtualnetworkgateways")
            ],
            load_balancers=[self.load_balancer(r) for r in rows("loadbalancers")],
            public_ips=[self.public_ip(r) for r in rows("publicipaddresses")],
            private_endpoints=[
                self.private_endpoint(r, zone_groups.get(r.id.lower(), []))
                for r in rows("privateendpoints")
            ],
            nat_gateways=[self.nat_gateway(r) for r in rows("natgateways")],
            bastion_hosts=[self.bastion(r) for r in rows("bastionhosts")],
            virtual_wans=wans,
            route_servers=route_servers,
            firewalls=[self.firewall(r, fw_policies) for r in rows("azurefirewalls")],
            firewall_policies=[fw_policies[r.id.lower()] for r in rows("firewallpolicies")],
            application_gateways=[
                self.app_gateway(r, waf_policies) for r in rows("applicationgateways")
            ],
            waf_policies=[
                waf_policies[r.id.lower()]
                for r in rows("applicationgatewaywebapplicationfirewallpolicies")
            ],
            private_dns_zones=[
                self.private_dns_zone(r, links.get(r.id.lower(), []))
                for r in rows("privatednszones")
            ],
            express_route_circuits=[self.er_circuit(r) for r in rows("expressroutecircuits")],
            front_door_waf_policies=[
                self.front_door_waf(r) for r in rows("frontdoorwebapplicationfirewallpolicies")
            ],
            flow_logs=[self.flow_log(r) for r in rows("networkwatchers/flowlogs")],
        )
        self._project_flow_logs(sub)
        return sub

    @staticmethod
    def _project_flow_logs(sub: AzureSubscriptionTopology) -> None:
        """An enabled flow log targeting an NSG, a subnet or a VNet marks the NSG and the VNet(s) it covers."""
        enabled_targets = {
            fl.target_resource_id.lower()
            for fl in sub.flow_logs
            if fl.enabled and fl.target_resource_id
        }
        nsg_by_id = {n.id.lower(): n for n in sub.nsgs}
        for nsg in sub.nsgs:
            if nsg.id.lower() in enabled_targets:
                nsg.flow_logs_enabled = True
        for vnet in sub.vnets:
            if vnet.id.lower() in enabled_targets:
                vnet.flow_logs_enabled = True
                continue
            for subnet in vnet.subnets:
                nsg = nsg_by_id.get((subnet.nsg_id or "").lower())
                if subnet.id.lower() in enabled_targets or (nsg and nsg.flow_logs_enabled):
                    vnet.flow_logs_enabled = True
                    break

    def run(self) -> NormalizedExport:
        counts = Counter(r.type for r in self.rows)
        outside = sum(n for t, n in counts.items() if not t.startswith(NETWORK_PREFIX))
        if outside:
            self.warnings.append(f"{outside} row(s) outside microsoft.network/ were ignored")
        unmapped = sorted(
            t
            for t in counts
            if t.startswith(NETWORK_PREFIX) and t not in MAPPED_TYPES and t not in COUNTED_ONLY
        )
        for t in unmapped:
            self.warnings.append(f"{counts[t]} row(s) of type {t} are counted but not evaluated")
        sub_ids = sorted(
            {r.subscription_id or "unknown" for r in self.rows if r.type.startswith(NETWORK_PREFIX)}
        )
        subscriptions = [self.subscription(s) for s in sub_ids]
        if not any(t.startswith(NETWORK_PREFIX) for t in counts):
            raise ValueError("the export has no microsoft.network/* rows")
        topology = AzureTopology(
            source="export",
            subscriptions=subscriptions,
            resource_counts=dict(sorted(counts.items())),
            unmapped_types=unmapped,
            has_properties=self.has_properties,
            warnings=self.warnings,
        )
        return NormalizedExport(
            topology=topology, rows=self.rows, facts=self.facts, warnings=list(self.warnings)
        )


def _as_rows(rows: Iterable[dict[str, Any] | ArgRow], warnings: list[str]) -> list[ArgRow]:
    out: list[ArgRow] = []
    for index, raw in enumerate(rows, start=1):
        if isinstance(raw, ArgRow):
            out.append(raw)
            continue
        if not isinstance(raw, dict):
            warnings.append(f"row {index}: not an object; skipped")
            continue
        row = row_from_dict(raw, index)
        if row is None:
            warnings.append(f"row {index}: missing type or id/name; skipped")
            continue
        out.append(row)
    return out


def normalize_rows(
    rows: Iterable[dict[str, Any] | ArgRow],
    *,
    warnings: list[str] | None = None,
    has_properties: bool | None = None,
) -> NormalizedExport:
    """Map Resource Graph rows (dicts as the export carries them, or ``ArgRow``) onto the model.

    ``warnings`` are the caller's ingestion warnings (``rows_from_document`` produces the paging
    ones); ``has_properties`` is detected when not given. Raises ``ValueError`` when no usable
    ``microsoft.network/*`` row exists. Returns the topology plus the per-resource facts the
    rules read, for callers that show them.
    """
    collected: list[str] = list(warnings or [])
    parsed = _as_rows(rows, collected)
    if not parsed:
        raise ValueError("export contains no usable rows (every row lacks a type or an id/name)")
    if has_properties is None:
        has_properties = any(r.properties for r in parsed)
    if not has_properties:
        collected.insert(0, NO_PROPERTIES_WARNING)
    return _Normalizer(parsed, collected, has_properties).run()


def normalize_resource_graph(
    rows: Iterable[dict[str, Any] | ArgRow],
    *,
    warnings: list[str] | None = None,
    has_properties: bool | None = None,
) -> AzureTopology:
    """Resource Graph rows -> ``AzureTopology`` (``source="export"``); see ``normalize_rows``."""
    return normalize_rows(rows, warnings=warnings, has_properties=has_properties).topology
