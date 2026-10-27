"""Map a typed ``Finding`` to the flat record ``_replace_discovery_findings`` writes.

The Prisma ``Finding`` table has no ``ruleId`` column, so the rule id is embedded as a title
prefix (``"AZ-NET-020: …"``); the stat-master, encyclopedia and copilot loaders all recover it
with the shared ``_RULE_ID_RE`` extraction. Both discovery runners (Azure through the engine's rule
registry, AWS through ``AnalysisEngine``) write through this one mapper, so every persisted
finding carries its rule id the same way; an engine finding without the monorepo's
web-tier fields maps too.
"""

from __future__ import annotations

from network_assessment.core.findings_schema import Finding

_DEFAULT_CATEGORY = "General"


def finding_to_record(finding: Finding) -> dict:
    """The Prisma-shaped dict for one finding; ``rule_id`` is never empty for a registry rule."""
    rule_id = finding.rule_id or ""
    title = finding.title
    if rule_id and rule_id not in title:
        title = f"{rule_id}: {title}"
    recommendations = getattr(finding, "recommendations", None) or []
    recommendation = (
        getattr(finding, "recommendation", None)
        or finding.remediation
        or (recommendations[0].text if recommendations else "")
    )
    return {
        "rule_id": rule_id,
        "title": title,
        "severity": str(finding.severity.value).upper(),
        "category": finding.category or _DEFAULT_CATEGORY,
        "description": finding.description or finding.observed_state.fact,
        "recommendation": recommendation,
        "traffic_direction": finding.traffic_direction,
        "region": finding.region or "",
        "resource_type": finding.resource_type or "",
        "est_cost_impact": getattr(finding, "est_monthly_cost_usd", None),
    }
