"""Finding taxonomy — deterministic traffic-direction classification.

The Azure tables (rule ids, categories, resource-type hints) live in the engine package
(``cna_azure_network_engine.rules.taxonomy``); this module layers the AWS rule ids of
``network_assessment/ai_engine/analysis_engine.py`` in front of them and delegates the rest. It returns
"east_west", "north_south", "management", or "" when no deterministic mapping exists —
callers treat "" as "unclassified", never guess.
"""

from __future__ import annotations

from cna_azure_network_engine.rules.taxonomy import (
    classify_traffic_direction as _engine_classify,
)

EAST_WEST = "east_west"
NORTH_SOUTH = "north_south"
MANAGEMENT = "management"

# ── Rule-ID mapping tables ─────────────────────────────────────────────────
# AWS rule ids from network_assessment/ai_engine/analysis_engine.py.

_EAST_WEST_RULES: frozenset[str] = frozenset(
    {
        "AWS-NET-001",  # default VPC — unintended lateral paths
        "AWS-NET-006",  # TGW default route table association
        "AWS-NET-007",  # TGW default route table propagation
        "AWS-NET-010",  # subnet without NACL
    }
)

_NORTH_SOUTH_RULES: frozenset[str] = frozenset(
    {
        "AWS-NET-003",  # SG unrestricted SSH from internet
        "AWS-NET-004",  # SG unrestricted RDP from internet
        "AWS-NET-005",  # SG unrestricted all from internet
        "AWS-NET-008",  # single Direct Connect
        "AWS-NET-009",  # NAT single AZ
        "AWS-NET-011",  # IGW missing route
        "AWS-NET-012",  # no Network Firewall with IGW
        "AWS-NET-013",  # WAF Web ACL not associated
    }
)

_MANAGEMENT_RULES: frozenset[str] = frozenset(
    {
        "AWS-NET-002",  # VPC flow logs disabled
    }
)


def _classify_aws_rule_id(rule_id: str) -> str | None:
    if rule_id in _EAST_WEST_RULES:
        return EAST_WEST
    if rule_id in _NORTH_SOUTH_RULES:
        return NORTH_SOUTH
    if rule_id in _MANAGEMENT_RULES:
        return MANAGEMENT
    return None


def classify_traffic_direction(rule_id: str, category: str = "", resource_type: str = "") -> str:
    """Classify a finding into a traffic-direction plane.

    Resolution order: AWS rule_id (exact match) → the engine's Azure tables (rule_id, then
    category case-insensitively, then resource_type substring). Returns "east_west",
    "north_south", "management", or "" when no deterministic mapping exists.
    """
    if rule_id:
        result = _classify_aws_rule_id(rule_id)
        if result is not None:
            return result
    return _engine_classify(rule_id, category, resource_type)
