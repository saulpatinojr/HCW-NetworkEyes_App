"""Deliverable dependency graph.

DD-013: When a source deliverable changes, all dependent deliverables
are automatically flagged as STALE and must be regenerated.
"""

DELIVERABLE_DEPENDENCIES: dict = {
    "executive_summary": ["zero_trust_scorecard", "gap_analysis", "risk_register"],
    "technical_recommendations": ["gap_analysis", "platform_findings"],
    "roadmap": ["gap_analysis", "zero_trust_scorecard"],
    "regional_reports": ["platform_findings", "gap_analysis"],
    "japan_report": ["regional_reports"],
    "executive_deck": ["executive_summary", "zero_trust_scorecard"],
    "knowledge_transfer": ["technical_recommendations", "platform_findings"],
}


def get_stale_deliverables(changed: str) -> list[str]:
    """Return all deliverables that depend on the changed source."""
    return [
        deliverable for deliverable, deps in DELIVERABLE_DEPENDENCIES.items() if changed in deps
    ]
