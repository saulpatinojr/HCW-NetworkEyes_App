"""Stat Masters — flat aggregated fact records powering pivots, report tables
and the chat copilot.

Mirrors the frontend type in apps/cna-web/lib/types/stat-master.ts:
8 dimensions (traffic_direction, severity, framework, region,
subscription_id, resource_type, category, rule_id) + 3 measures
(finding_count, resource_count, est_monthly_cost_impact).

`build_stat_masters` is a pure function: it accepts both
cna.core.findings_schema.Finding models and plain dict findings (the shape
produced by apps/cna-api/main.py::_topology_to_findings and by Prisma
Finding rows), and an optional AzureTopology for classification metadata.
Unknown dimension values fall back to the same labels the frontend
derive-stat-masters.ts uses ("Unmapped", "Unknown", "default", "Other",
"Uncategorized", "—", "unclassified") so API records and client-derived
records stay interchangeable.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from cna.core.findings_schema import Finding

STAT_MASTERS_VERSION = "1.0.0"

# Same rule-id extraction pattern as apps/cna-web/lib/derive-stat-masters.ts
_RULE_ID_RE = re.compile(r"\b([A-Z]{2,5}-[A-Z]{2,10}-\d{1,4})\b")

# Fallback labels — keep in sync with derive-stat-masters.ts
_UNCLASSIFIED = "unclassified"
_NO_FRAMEWORK = "Unmapped"
_NO_REGION = "Unknown"
_NO_SUBSCRIPTION = "default"
_NO_RESOURCE_TYPE = "Other"
_NO_CATEGORY = "Uncategorized"
_NO_RULE = "—"


class StatMasterRecord(BaseModel):
    """One aggregated fact row per unique dimension tuple."""

    # Dimensions
    traffic_direction: str = _UNCLASSIFIED
    severity: str = ""
    framework: str = _NO_FRAMEWORK
    region: str = _NO_REGION
    subscription_id: str = _NO_SUBSCRIPTION
    resource_type: str = _NO_RESOURCE_TYPE
    category: str = _NO_CATEGORY
    rule_id: str = _NO_RULE
    # Measures
    finding_count: int = 0
    resource_count: int = 0
    est_monthly_cost_impact: float = 0.0


class StatMasterBundle(BaseModel):
    """Stat-master records plus the topology metadata they were built from."""

    records: list[StatMasterRecord] = Field(default_factory=list)
    generated_for_engagement: str | None = None
    topology_pattern: str | None = None  # mesh | hub_spoke | vwan | isolated
    topology_rationale: str | None = None
    subscription_count: int = 0
    version: str = STAT_MASTERS_VERSION


def _extract_rule_id(title: str) -> str:
    match = _RULE_ID_RE.search(title or "")
    return match.group(1) if match else _NO_RULE


def _first_framework(finding: Finding) -> str:
    for fm in finding.framework_mappings:
        if fm.framework:
            return fm.framework
    return _NO_FRAMEWORK


def _dimensions_from_model(finding: Finding) -> tuple[str, ...]:
    return (
        finding.traffic_direction or _UNCLASSIFIED,
        str(finding.severity.value).upper(),
        _first_framework(finding),
        finding.region or _NO_REGION,
        finding.account_id or _NO_SUBSCRIPTION,
        finding.resource_type or _NO_RESOURCE_TYPE,
        finding.category or _NO_CATEGORY,
        finding.rule_id or _extract_rule_id(finding.title),
    )


def _dict_get(finding: dict, *keys: str) -> Any:
    """Return the first present, non-empty value among snake_case and
    camelCase key aliases (dict findings come from both the API mapper and
    Prisma rows)."""
    for key in keys:
        value = finding.get(key)
        if value not in (None, ""):
            return value
    return None


def _dimensions_from_dict(finding: dict) -> tuple[str, ...]:
    title = str(_dict_get(finding, "title") or "")
    rule_id = _dict_get(finding, "rule_id", "ruleId") or _extract_rule_id(title)
    return (
        str(_dict_get(finding, "traffic_direction", "trafficDirection") or _UNCLASSIFIED),
        str(_dict_get(finding, "severity") or "").upper(),
        str(_dict_get(finding, "framework") or _NO_FRAMEWORK),
        str(_dict_get(finding, "region") or _NO_REGION),
        str(
            _dict_get(finding, "subscription_id", "subscriptionId", "account_id", "credentialId")
            or _NO_SUBSCRIPTION
        ),
        str(_dict_get(finding, "resource_type", "resourceType") or _NO_RESOURCE_TYPE),
        str(_dict_get(finding, "category") or _NO_CATEGORY),
        str(rule_id),
    )


def _cost_of(finding: Finding | dict) -> float:
    if isinstance(finding, dict):
        value = _dict_get(finding, "est_monthly_cost_usd", "est_cost_impact", "estCostImpact")
    else:
        value = finding.est_monthly_cost_usd
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _resource_id_of(finding: Finding | dict) -> str:
    if isinstance(finding, dict):
        return str(_dict_get(finding, "resource_id", "resourceId") or "")
    return finding.resource_id or ""


def build_stat_masters(
    topology: Any | None,
    findings: list[Finding | dict],
    engagement_id: str | None = None,
) -> StatMasterBundle:
    """Aggregate findings into one StatMasterRecord per unique dimension tuple.

    Pure and deterministic. `topology` is an optional AzureTopology
    (cna/core/topology_schema.py) used only for bundle metadata — pass
    None when no topology checkpoint is available.

    Measures per group:
      finding_count           — number of findings in the group
      resource_count          — distinct non-empty resource_ids; findings
                                without a resource_id each count as one
                                (parity with the client-side derivation)
      est_monthly_cost_impact — sum of est_monthly_cost_usd (model) or
                                est_cost_impact / estCostImpact (dict)
    """
    groups: dict[tuple[str, ...], dict[str, Any]] = {}

    for finding in findings:
        if isinstance(finding, dict):
            dims = _dimensions_from_dict(finding)
        else:
            dims = _dimensions_from_model(finding)

        group = groups.setdefault(
            dims, {"finding_count": 0, "resource_ids": set(), "anonymous": 0, "cost": 0.0}
        )
        group["finding_count"] += 1
        resource_id = _resource_id_of(finding)
        if resource_id:
            group["resource_ids"].add(resource_id)
        else:
            group["anonymous"] += 1
        group["cost"] += _cost_of(finding)

    records = [
        StatMasterRecord(
            traffic_direction=dims[0],
            severity=dims[1],
            framework=dims[2],
            region=dims[3],
            subscription_id=dims[4],
            resource_type=dims[5],
            category=dims[6],
            rule_id=dims[7],
            finding_count=group["finding_count"],
            resource_count=len(group["resource_ids"]) + group["anonymous"],
            est_monthly_cost_impact=round(group["cost"], 2),
        )
        for dims, group in sorted(groups.items())
    ]

    bundle = StatMasterBundle(records=records, generated_for_engagement=engagement_id)

    if topology is not None:
        bundle.subscription_count = len(getattr(topology, "subscriptions", []) or [])
        try:
            from cna.modules.network.analysis.topology_classifier import classify_topology

            classification = classify_topology(topology)
            bundle.topology_pattern = classification.pattern
            bundle.topology_rationale = classification.rationale
        except Exception:  # noqa: BLE001 — metadata is best-effort, never fatal
            bundle.topology_pattern = None

    return bundle
