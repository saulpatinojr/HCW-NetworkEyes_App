"""Resource Graph discovery (change set D of REFACTOR_APP.md).

One paged Resource Graph query per scope set populates the model through the normalizer;
ARM is used only where Resource Graph has no data (BGP POST actions, Monitor metrics,
diagnostic settings, Cost Management, Log Analytics), and those live collectors run after
this module has built the topology. Everything here is a read of a ``Resources``,
``ResourceContainers`` or ``SecurityResources`` table with the Reader role; nothing writes.

The module imports the Azure SDK lazily (``[azure]`` extra). ``query_all``,
``filter_to_scopes``, ``attach_containers``, ``attach_defender`` and ``attach_nvas`` take plain
rows, so every path is testable with a fake client and fixture JSON.
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from cna_azure_network_engine.discovery import require_azure_extra
from cna_azure_network_engine.model.azure import (
    AzureNIC,
    AzureNVA,
    AzureSubscriptionTopology,
    AzureTopology,
    DefenderAssessment,
    ManagementGroup,
)
from cna_azure_network_engine.normalize.resource_graph import normalize_resource_graph

logger = logging.getLogger("cna_azure_network_engine.discovery")

NETWORK_QUERY = (
    "Resources | where type startswith 'microsoft.network/' "
    "| project id, name, type, location, resourceGroup, subscriptionId, tags, zones, sku, kind, "
    "properties"
)
CONTAINERS_QUERY = "ResourceContainers | project id, name, type, properties"
DEFENDER_QUERY = (
    "SecurityResources | where type == 'microsoft.security/assessments' "
    "| project id, name, properties"
)
NVA_QUERY = (
    "Resources | where type in~ ('microsoft.compute/virtualmachines',"
    "'microsoft.network/networkinterfaces') "
    "| project id, name, type, location, resourceGroup, subscriptionId, properties, plan"
)

DEFAULT_PAGE = 1000
# Rows kept across all pages of one query. A tenant past this is reported as truncated,
# never silently cut: findings then say which rows they cover.
MAX_ROWS = 50_000
MAX_RETRIES = 5
_MAX_BACKOFF_SECONDS = 30.0
_RETRYABLE_STATUS = frozenset({429, 503})

TRUNCATED_WARNING = "resource graph response was truncated; findings cover the rows received"

# Marketplace / image publishers that identify a network virtual appliance.
NGFW_PUBLISHERS: frozenset[str] = frozenset(
    {
        "paloaltonetworks",
        "fortinet",
        "checkpoint",
        "cisco",
        "barracudanetworks",
        "junipernetworks",
        "sophos",
        "f5-networks",
        "zscaler",
        "stormshield",
        "watchguard-technologies",
        "forcepoint-llc",
        "a10networks",
        "citrix",
        "versa-networks",
        "arista-networks",
    }
)

_ID_SUB_RG = re.compile(
    r"^/subscriptions/(?P<sub>[^/]+)(?:/resourcegroups/(?P<rg>[^/]+))?", re.IGNORECASE
)


# ── Scopes ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Scope:
    subscription_id: str
    resource_group: str | None  # lower-cased; None means the whole subscription


_SCOPE_RE = re.compile(
    r"^/subscriptions/(?P<sub>[0-9a-f-]{36})(?:/resourceGroups/(?P<rg>[^/]+))?/?$",
    re.IGNORECASE,
)


def parse_scopes(value: str) -> list[Scope]:
    """``CNA_SCOPES``, space-separated. Accepts ``/subscriptions/<sub>`` and
    ``/subscriptions/<sub>/resourceGroups/<rg>``; anything else is a ``SystemExit`` at
    start-up, before any query."""
    scopes: list[Scope] = []
    for token in value.split():
        m = _SCOPE_RE.match(token)
        if not m:
            raise SystemExit(
                f"CNA_SCOPES: {token!r} is not /subscriptions/<id> or "
                "/subscriptions/<id>/resourceGroups/<name>"
            )
        rg = m.group("rg")
        scopes.append(Scope(m.group("sub").lower(), rg.lower() if rg else None))
    return list(dict.fromkeys(scopes))


def subscriptions_of(scopes: Iterable[Scope]) -> list[str]:
    """What Resource Graph is asked for: the distinct subscription ids, sorted."""
    return sorted({s.subscription_id for s in scopes})


def _row_scope(row: Mapping[str, Any]) -> tuple[str | None, str | None]:
    sub = row.get("subscriptionId")
    rg = row.get("resourceGroup")
    rid = row.get("id")
    if isinstance(rid, str) and (not sub or not rg):
        m = _ID_SUB_RG.match(rid)
        if m:
            sub = sub or m.group("sub")
            rg = rg or m.group("rg")
    return (
        str(sub).lower() if sub else None,
        str(rg).lower() if rg else None,
    )


def filter_to_scopes(rows: list[dict], scopes: list[Scope]) -> list[dict]:
    """Keep a row when its subscription is in a whole-subscription scope, or when
    ``(subscriptionId, resourceGroup.lower())`` matches a resource-group scope. Rows
    outside every scope are dropped: Resource Graph answers per subscription, so a
    resource-group scope is enforced here and nowhere else."""
    whole = {s.subscription_id for s in scopes if s.resource_group is None}
    groups = {(s.subscription_id, s.resource_group) for s in scopes if s.resource_group}
    kept: list[dict] = []
    for row in rows:
        sub, rg = _row_scope(row)
        if sub is None:
            continue
        if sub in whole or (rg is not None and (sub, rg) in groups):
            kept.append(row)
    return kept


# ── Paged queries ────────────────────────────────────────────────────────────


def _request(query: str, subscriptions: list[str], page: int, skip_token: str | None):
    from azure.mgmt.resourcegraph.models import QueryRequest, QueryRequestOptions

    return QueryRequest(
        subscriptions=subscriptions,
        query=query,
        options=QueryRequestOptions(top=page, skip_token=skip_token, result_format="objectArray"),
    )


def _status_of(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    return status if isinstance(status, int) else None


def _retry_after(exc: BaseException) -> float | None:
    """The ``Retry-After`` the service asked for, in seconds, when it sent one."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        value = headers.get("Retry-After") or headers.get("retry-after")
    except AttributeError:
        return None
    if value is None:
        return None
    try:
        return max(0.0, float(value))
    except TypeError, ValueError:
        return None


def _query_page(
    client: Any,
    request: Any,
    sleep: Callable[[float], None],
    max_retries: int,
) -> Any | None:
    """One ``client.resources`` call with bounded backoff on 429/503, honouring Retry-After.

    Returns the response, or ``None`` when the page failed for good: the caller marks the
    result truncated instead of raising, so a throttled tenant still yields a report.
    """
    for attempt in range(max_retries + 1):
        try:
            return client.resources(request)
        except Exception as exc:  # the SDK raises HttpResponseError; keep the module SDK-free
            status = _status_of(exc)
            if status not in _RETRYABLE_STATUS or attempt == max_retries:
                logger.warning(
                    "resource graph page failed: %s%s",
                    type(exc).__name__,
                    f" (HTTP {status})" if status else "",
                )
                return None
            delay = _retry_after(exc)
            if delay is None:
                delay = min(float(2**attempt), _MAX_BACKOFF_SECONDS)
            logger.info("resource graph throttled (HTTP %s); retrying in %.1fs", status, delay)
            sleep(delay)
    return None


def query_all(
    client: Any,
    query: str,
    subscriptions: list[str],
    page: int = DEFAULT_PAGE,
    *,
    max_rows: int = MAX_ROWS,
    sleep: Callable[[float], None] = time.sleep,
    max_retries: int = MAX_RETRIES,
) -> tuple[list[dict], bool]:
    """Run ``query`` over ``subscriptions`` and follow ``skip_token`` until it is gone.

    Returns ``(rows, truncated)``: ``truncated`` is True only when a token remained
    unconsumed (the row cap was reached or a page failed) or ``total_records`` exceeds
    the rows received.
    """
    rows: list[dict] = []
    skip_token: str | None = None
    truncated = False
    total_records: int | None = None
    while True:
        response = _query_page(
            client, _request(query, subscriptions, page, skip_token), sleep, max_retries
        )
        if response is None:
            truncated = True
            break
        data = getattr(response, "data", None) or []
        rows.extend(item for item in data if isinstance(item, dict))
        reported = getattr(response, "total_records", None)
        if isinstance(reported, int):
            total_records = reported
        skip_token = getattr(response, "skip_token", None) or None
        if not skip_token:
            break
        if len(rows) >= max_rows:
            truncated = True
            break
    if total_records is not None and total_records > len(rows):
        truncated = True
    return rows, truncated


# ── Attach what the normalizer does not read ─────────────────────────────────


def _by_subscription(topology: AzureTopology) -> dict[str, AzureSubscriptionTopology]:
    return {s.subscription_id.lower(): s for s in topology.subscriptions}


def _props(row: Mapping[str, Any]) -> dict[str, Any]:
    props = row.get("properties")
    return props if isinstance(props, dict) else {}


def _get_ci(obj: Any, *path: str, default: Any = None) -> Any:
    """Case-insensitive ``_get``: Resource Graph preserves each provider's casing."""
    for key in path:
        if not isinstance(obj, dict):
            return default
        lowered = {str(k).lower(): v for k, v in obj.items()}
        obj = lowered.get(key.lower())
        if obj is None:
            return default
    return obj


def _ref(value: Any) -> str | None:
    if isinstance(value, dict):
        rid = _get_ci(value, "id")
        return str(rid) if rid else None
    return None


def attach_containers(topology: AzureTopology, rows: list[dict]) -> None:
    """Subscription display names and the management-group tree from ``ResourceContainers``."""
    subs = _by_subscription(topology)
    groups: list[ManagementGroup] = []
    sub_parent: dict[str, str] = {}
    for row in rows:
        rtype = str(row.get("type") or "").lower()
        rid = str(row.get("id") or "")
        name = str(row.get("name") or "")
        props = _props(row)
        if rtype == "microsoft.resources/subscriptions":
            sub_id = (str(row.get("subscriptionId") or "") or rid.rsplit("/", 1)[-1]).lower()
            if sub_id in subs and name:
                subs[sub_id].subscription_name = name
            chain = _get_ci(props, "managementGroupAncestorsChain", default=None)
            if isinstance(chain, list) and chain:
                first = chain[0]
                if isinstance(first, dict) and first.get("name"):
                    sub_parent[sub_id] = str(first["name"])
        elif rtype == "microsoft.management/managementgroups":
            display = _get_ci(props, "displayName", default=None) or name
            parent_id = _ref(_get_ci(props, "details", "parent", default=None))
            groups.append(
                ManagementGroup(
                    id=name or rid,
                    name=name or rid,
                    display_name=str(display),
                    parent_id=parent_id.rsplit("/", 1)[-1] if parent_id else None,
                )
            )
    by_name = {g.name: g for g in groups}
    for group in groups:
        if group.parent_id and group.parent_id in by_name:
            by_name[group.parent_id].child_mg_ids.append(group.name)
    for sub_id, parent in sub_parent.items():
        if parent in by_name:
            by_name[parent].subscription_ids.append(sub_id)
    if groups:
        topology.management_groups = groups


def _defender_status(props: Mapping[str, Any]) -> str:
    code = _get_ci(props, "status", "code", default=None)
    return str(code) if code else "Unknown"


def attach_defender(topology: AzureTopology, rows: list[dict]) -> None:
    """Fill ``defender_assessments`` from ``SecurityResources`` assessment rows: Networking
    category, Unhealthy or NotApplicable, as the ARM collector selected them."""
    subs = _by_subscription(topology)
    for row in rows:
        sub_id, _rg = _row_scope(row)
        if sub_id is None or sub_id not in subs:
            continue
        props = _props(row)
        status = _defender_status(props)
        if status not in ("Unhealthy", "NotApplicable"):
            continue
        meta = _get_ci(props, "metadata", default=None)
        meta = meta if isinstance(meta, dict) else {}
        categories = _get_ci(meta, "categories", default=None)
        category = (
            str(categories[0]) if isinstance(categories, list) and categories else "Networking"
        )
        if "network" not in category.lower():
            continue
        details = _get_ci(props, "resourceDetails", default=None)
        details = details if isinstance(details, dict) else {}
        effort = _get_ci(meta, "implementationEffort", default=None)
        impact = _get_ci(meta, "userImpact", default=None)
        threats = _get_ci(meta, "threats", default=None)
        display = _get_ci(meta, "displayName", default=None) or _get_ci(
            props, "displayName", default=None
        )
        subs[sub_id].defender_assessments.append(
            DefenderAssessment(
                assessment_id=str(row.get("id") or ""),
                display_name=str(display or row.get("name") or ""),
                description=_opt(_get_ci(meta, "description", default=None)),
                remediation_description=_opt(_get_ci(meta, "remediationDescription", default=None)),
                status=status,
                severity=str(_get_ci(meta, "severity", default=None) or "Medium"),
                resource_id=_opt(_get_ci(details, "id", default=None)),
                resource_type=_opt(_get_ci(details, "resourceType", default=None)),
                category=category,
                implementation_effort=_opt(effort),
                threats=[str(t) for t in threats] if isinstance(threats, list) else [],
                user_impact=_opt(impact),
            )
        )


def _opt(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _nic_from_row(row: Mapping[str, Any], vm_id: str | None, vm_tags: dict) -> AzureNIC:
    props = _props(row)
    _sub, rg = _row_scope(row)
    subnet_ids: list[str] = []
    private_ips: list[str] = []
    public_ip_id: str | None = None
    for ipc in _get_ci(props, "ipConfigurations", default=None) or []:
        ipc_props = _get_ci(ipc, "properties", default=None) or {}
        subnet = _ref(_get_ci(ipc_props, "subnet", default=None))
        if subnet:
            subnet_ids.append(subnet)
        private_ip = _get_ci(ipc_props, "privateIPAddress", default=None)
        if private_ip:
            private_ips.append(str(private_ip))
        pip = _ref(_get_ci(ipc_props, "publicIPAddress", default=None))
        if pip:
            public_ip_id = pip
    return AzureNIC(
        id=str(row.get("id") or ""),
        name=str(row.get("name") or ""),
        location=str(row.get("location") or ""),
        resource_group=str(row.get("resourceGroup") or rg or ""),
        vm_id=vm_id,
        ip_forwarding_enabled=bool(_get_ci(props, "enableIPForwarding", default=False)),
        subnet_ids=subnet_ids,
        private_ips=private_ips,
        public_ip_id=public_ip_id,
        nsg_id=_ref(_get_ci(props, "networkSecurityGroup", default=None)),
        tags={str(k): str(v) for k, v in vm_tags.items()},
    )


def identify_nva(row: Mapping[str, Any]) -> tuple[str | None, str | None, str | None, str | None]:
    """``(publisher, offer, plan_name, identification_method)`` from a VM row's marketplace
    ``plan`` column or its image reference; all ``None`` when neither names an NGFW vendor."""
    plan = row.get("plan")
    if isinstance(plan, dict):
        publisher = _get_ci(plan, "publisher", default=None)
        if publisher and str(publisher).lower() in NGFW_PUBLISHERS:
            return (
                str(publisher),
                _opt(_get_ci(plan, "product", default=None)),
                _opt(_get_ci(plan, "name", default=None)),
                "marketplace",
            )
    image = _get_ci(_props(row), "storageProfile", "imageReference", default=None)
    if isinstance(image, dict):
        publisher = _get_ci(image, "publisher", default=None)
        if publisher and str(publisher).lower() in NGFW_PUBLISHERS:
            return (
                str(publisher),
                _opt(_get_ci(image, "offer", default=None)),
                _opt(_get_ci(image, "sku", default=None)),
                "image_reference",
            )
    return None, None, None, None


def attach_nvas(topology: AzureTopology, rows: list[dict]) -> None:
    """Fill ``nvas`` from VM and NIC rows: a VM whose marketplace plan or image publisher is a
    known NGFW vendor, or that has a NIC with IP forwarding enabled."""
    subs = _by_subscription(topology)
    nics_by_id: dict[str, dict] = {}
    vms: list[dict] = []
    for row in rows:
        rtype = str(row.get("type") or "").lower()
        if rtype == "microsoft.network/networkinterfaces":
            nics_by_id[str(row.get("id") or "").lower()] = row
        elif rtype == "microsoft.compute/virtualmachines":
            vms.append(row)
    for vm in vms:
        sub_id, rg = _row_scope(vm)
        if sub_id is None or sub_id not in subs:
            continue
        props = _props(vm)
        vm_id = str(vm.get("id") or "")
        tags = vm.get("tags") if isinstance(vm.get("tags"), dict) else {}
        publisher, offer, plan_name, method = identify_nva(vm)
        nics: list[AzureNIC] = []
        has_forwarding = False
        for ref in _get_ci(props, "networkProfile", "networkInterfaces", default=None) or []:
            nic_id = _ref(ref)
            nic_row = nics_by_id.get(nic_id.lower()) if nic_id else None
            if nic_row is None:
                continue
            nic = _nic_from_row(nic_row, vm_id, tags)
            has_forwarding = has_forwarding or nic.ip_forwarding_enabled
            nics.append(nic)
        if not method and has_forwarding:
            method = "ip_forwarding"
        if not method:
            continue
        subs[sub_id].nvas.append(
            AzureNVA(
                id=vm_id,
                name=str(vm.get("name") or ""),
                location=str(vm.get("location") or ""),
                resource_group=str(vm.get("resourceGroup") or rg or ""),
                vm_size=_opt(_get_ci(props, "hardwareProfile", "vmSize", default=None)),
                os_type=_opt(_get_ci(props, "storageProfile", "osDisk", "osType", default=None)),
                publisher=publisher,
                offer=offer,
                plan_name=plan_name,
                identification_method=method,
                nics=nics,
                tags={str(k): str(v) for k, v in tags.items()},
            )
        )


# ── Orchestration ────────────────────────────────────────────────────────────


class ResourceGraphDiscovery:
    """Four Resource Graph queries over the scopes' subscriptions, filtered to the scopes,
    normalized into an ``AzureTopology`` with ``source="discovery"``."""

    def __init__(
        self,
        credential: Any,
        scopes: list[Scope],
        progress: Callable[[str], None] | None = None,
        *,
        client: Any = None,
        page: int = DEFAULT_PAGE,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not scopes:
            raise ValueError("ResourceGraphDiscovery needs at least one scope")
        self.scopes = list(scopes)
        self._credential = credential
        self._progress = progress or (lambda _msg: None)
        self._client = client
        self._page = page
        self._sleep = sleep

    @property
    def client(self) -> Any:
        if self._client is None:
            require_azure_extra()
            from azure.mgmt.resourcegraph import ResourceGraphClient

            self._client = ResourceGraphClient(self._credential)
        return self._client

    def _query(self, query: str, subs: list[str]) -> tuple[list[dict], bool]:
        return query_all(self.client, query, subs, self._page, sleep=self._sleep)

    def run(self) -> AzureTopology:
        subs = subscriptions_of(self.scopes)  # what Resource Graph is asked for
        self._progress(
            f"Resource Graph: querying {len(subs)} subscription(s) for microsoft.network/* rows…"
        )
        rows, truncated = self._query(NETWORK_QUERY, subs)
        in_scope = filter_to_scopes(rows, self.scopes)
        self._progress(f"Resource Graph: {len(rows)} row(s) received, {len(in_scope)} in scope")
        topology = normalize_resource_graph(in_scope)
        topology.source = "discovery"
        self._progress("Resource Graph: resource containers…")
        attach_containers(topology, self._query(CONTAINERS_QUERY, subs)[0])
        self._progress("Resource Graph: Defender for Cloud assessments…")
        attach_defender(
            topology, filter_to_scopes(self._query(DEFENDER_QUERY, subs)[0], self.scopes)
        )
        self._progress("Resource Graph: virtual machines and NICs (NVA detection)…")
        attach_nvas(topology, filter_to_scopes(self._query(NVA_QUERY, subs)[0], self.scopes))
        if truncated:
            topology.warnings.append(TRUNCATED_WARNING)
            self._progress(f"WARNING — {TRUNCATED_WARNING}")
        return topology


__all__ = [
    "CONTAINERS_QUERY",
    "DEFENDER_QUERY",
    "MAX_ROWS",
    "NETWORK_QUERY",
    "NGFW_PUBLISHERS",
    "NVA_QUERY",
    "TRUNCATED_WARNING",
    "ResourceGraphDiscovery",
    "Scope",
    "attach_containers",
    "attach_defender",
    "attach_nvas",
    "filter_to_scopes",
    "identify_nva",
    "parse_scopes",
    "query_all",
    "subscriptions_of",
]
