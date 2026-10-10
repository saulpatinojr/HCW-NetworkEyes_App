"""Finding taxonomy — deterministic traffic-direction classification.

Maps a finding to one of three traffic planes used by the report engine
and the stat-master aggregations:

  east_west   — lateral traffic between VNets/VPCs/subnets (peering, UDRs,
                segmentation, private endpoints, internal load balancing)
  north_south — traffic crossing the perimeter (public IPs, firewalls,
                WAF/App Gateway, NAT, VPN/ExpressRoute, ingress/egress)
  management  — control-plane and observability concerns (flow logs,
                diagnostics, Bastion, Network Watcher, log retention)

Classification is rule_id-first (stable identifiers from the Azure rule
registry in cna/ai_engine/azure_rules and the AWS rules in analysis_engine.py),
falling back to category, then resource_type. Returns "" when the
direction cannot be determined — callers must treat "" as "unclassified",
never guess.
"""

from __future__ import annotations

EAST_WEST = "east_west"
NORTH_SOUTH = "north_south"
MANAGEMENT = "management"

# ── Rule-ID mapping tables ─────────────────────────────────────────────────
# Rule IDs from the Azure rule registry (cna/ai_engine/azure_rules: AZ-NET-*,
# AZ-BCDR-*, AZ-COST-*) and the AWS rules of cna/ai_engine/analysis_engine.py.

_EAST_WEST_RULES: frozenset[str] = frozenset(
    {
        # Segmentation / lateral movement
        "AWS-NET-001",  # default VPC — unintended lateral paths
        "AWS-NET-006",  # TGW default route table association
        "AWS-NET-007",  # TGW default route table propagation
        "AWS-NET-010",  # subnet without NACL
        "AZ-NET-002",  # subnet without NSG
        "AZ-NET-005",  # peering allows gateway transit without gateway
        "AZ-NET-011",  # VNet IP exhaustion (intra-VNet capacity)
        "AZ-NET-012",  # spoke UDR missing — hub firewall bypass
        "AZ-NET-021",  # NSG wildcard allow-all rule
        "AZ-NET-023",  # BGP route propagation disabled on a route table
        "AZ-NET-031",  # private endpoint connection pending
    }
)

_NORTH_SOUTH_RULES: frozenset[str] = frozenset(
    {
        # Perimeter ingress/egress
        "AWS-NET-003",  # SG unrestricted SSH from internet
        "AWS-NET-004",  # SG unrestricted RDP from internet
        "AWS-NET-005",  # SG unrestricted all from internet
        "AWS-NET-008",  # single Direct Connect
        "AWS-NET-009",  # NAT single AZ
        "AWS-NET-011",  # IGW missing route
        "AWS-NET-012",  # no Network Firewall with IGW
        "AWS-NET-013",  # WAF Web ACL not associated
        "AZ-NET-001",  # VNet without DDoS protection
        "AZ-NET-003",  # firewall threat intel not Deny
        "AZ-NET-004",  # single ExpressRoute circuit
        "AZ-NET-007",  # App Gateway WAF disabled
        "AZ-NET-008",  # gateway saturation
        "AZ-NET-009",  # firewall with zero hits
        "AZ-NET-010",  # LB SNAT exhaustion (outbound internet)
        "AZ-NET-016",  # ER circuit saturation
        "AZ-NET-017",  # DDoS attack detected
        "AZ-NET-018",  # Front Door WAF in Detection mode
        "AZ-NET-019",  # App Gateway high latency / failures
        "AZ-NET-020",  # NSG allows RDP/SSH from the internet
        "AZ-NET-022",  # route table default route straight to the internet
        "AZ-NET-025",  # App Gateway WAF in Detection mode
        "AZ-NET-026",  # load balancer Basic SKU
        "AZ-NET-027",  # public IP Basic SKU
        "AZ-NET-028",  # VPN gateway Basic SKU
        "AZ-NET-029",  # VPN gateway Generation 1
        "AZ-NET-030",  # gateway connection not connected
        "AZ-NET-032",  # no Azure Firewall with VNets present
        # FinOps — perimeter resources (public IPs, gateways, NAT, firewall)
        "AZ-COST-001",
        "AZ-COST-002",
        "AZ-COST-003",
        "AZ-COST-004",
        "AZ-COST-005",
        # BC/DR — perimeter and hybrid-connectivity SPOFs
        "AZ-BCDR-001",
        "AZ-BCDR-002",
        "AZ-BCDR-003",
        "AZ-BCDR-004",
        "AZ-BCDR-005",
        "AZ-BCDR-006",
        "AZ-BCDR-007",
    }
)

_MANAGEMENT_RULES: frozenset[str] = frozenset(
    {
        # Observability / control plane
        "AWS-NET-002",  # VPC flow logs disabled
        "AZ-NET-006",  # VNet without NSG flow logs
        "AZ-NET-013",  # firewall without diagnostics
        "AZ-NET-014",  # Traffic Analytics missing
        "AZ-NET-015",  # Bastion without session audit logging
        "AZ-NET-024",  # VNet custom DNS servers
        "AZ-NET-033",  # no Azure Bastion with VNets present
    }
)

# ── Category fallback ──────────────────────────────────────────────────────
# Categories carried by rule metadata (RuleMeta.category) and by findings that
# arrive without a rule id; the rule-id tables above take precedence.

_EAST_WEST_CATEGORIES: frozenset[str] = frozenset(
    {
        "network segmentation",
        "routing & transit",
        "network appliances",
    }
)

_NORTH_SOUTH_CATEGORIES: frozenset[str] = frozenset(
    {
        "network security",
        "network protection",
        "application security",
        "remote access",
        "connectivity",
        "gateway",
        "bgp & routing",
        "performance",
        "cost & hygiene",
        "resilience",
        "finops",
        "bc/dr",
    }
)

_MANAGEMENT_CATEGORIES: frozenset[str] = frozenset(
    {
        "observability",
        "monitoring & visibility",
        "access control",
        "dns & name resolution",
    }
)

# ── Resource-type fallback ─────────────────────────────────────────────────
# Substring match on lowercase resource_type (ARM types or AWS:: types).

_EAST_WEST_RESOURCE_HINTS: tuple[str, ...] = (
    "virtualnetworkpeerings",
    "routetables",
    "privateendpoints",
    "virtualnetworks/subnets",
    "networksecuritygroups",
    "transitgateway",
)

_NORTH_SOUTH_RESOURCE_HINTS: tuple[str, ...] = (
    "publicipaddresses",
    "azurefirewalls",
    "applicationgateways",
    "natgateways",
    "virtualnetworkgateways",
    "expressroutecircuits",
    "frontdoor",
    "loadbalancers",
    "internetgateway",
    "securitygroup",
    "wafv2",
    "network-firewall",
)

_MANAGEMENT_RESOURCE_HINTS: tuple[str, ...] = (
    "bastionhosts",
    "networkwatchers",
    "flowlogs",
    "diagnosticsettings",
    "workspaces",
)


def _classify_by_rule_id(rule_id: str) -> str | None:
    if rule_id in _EAST_WEST_RULES:
        return EAST_WEST
    if rule_id in _NORTH_SOUTH_RULES:
        return NORTH_SOUTH
    if rule_id in _MANAGEMENT_RULES:
        return MANAGEMENT
    if rule_id.startswith(("AZ-COST-", "AZ-BCDR-")):
        return NORTH_SOUTH
    return None


def _classify_by_category(category: str) -> str | None:
    cat = (category or "").strip().lower()
    if not cat:
        return None
    if cat in _EAST_WEST_CATEGORIES:
        return EAST_WEST
    if cat in _NORTH_SOUTH_CATEGORIES:
        return NORTH_SOUTH
    if cat in _MANAGEMENT_CATEGORIES:
        return MANAGEMENT
    return None


def _classify_by_resource_type(resource_type: str) -> str | None:
    rt = (resource_type or "").strip().lower()
    if not rt:
        return None
    if any(hint in rt for hint in _MANAGEMENT_RESOURCE_HINTS):
        return MANAGEMENT
    if any(hint in rt for hint in _EAST_WEST_RESOURCE_HINTS):
        return EAST_WEST
    if any(hint in rt for hint in _NORTH_SOUTH_RESOURCE_HINTS):
        return NORTH_SOUTH
    return None


def classify_traffic_direction(rule_id: str, category: str = "", resource_type: str = "") -> str:
    """Classify a finding into a traffic-direction plane.

    Resolution order: rule_id (exact match) → category (case-insensitive)
    → resource_type (substring hint). Returns "east_west", "north_south",
    "management", or "" when no deterministic mapping exists.
    """
    if rule_id:
        result = _classify_by_rule_id(rule_id)
        if result is not None:
            return result

    result = _classify_by_category(category)
    if result is not None:
        return result

    result = _classify_by_resource_type(resource_type)
    if result is not None:
        return result

    return ""
