"""Unit tests for deliverable dependency graph (DD-013)."""

from cna.core.deliverable_dependency import get_stale_deliverables


def test_gap_analysis_staleness():
    stale = get_stale_deliverables("gap_analysis")
    assert "roadmap" in stale
    assert "executive_summary" in stale
    assert "technical_recommendations" in stale


def test_platform_findings_staleness():
    stale = get_stale_deliverables("platform_findings")
    assert "technical_recommendations" in stale
    assert "regional_reports" in stale


def test_regional_reports_staleness():
    stale = get_stale_deliverables("regional_reports")
    assert "japan_report" in stale


def test_unrelated_change_no_false_staleness():
    stale = get_stale_deliverables("nonexistent_source")
    assert stale == []
