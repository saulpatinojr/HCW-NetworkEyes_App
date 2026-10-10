"""Unit tests for the ``python-engine-api`` area findings (Requirement 2).

Assert the verify-then-close-gaps record for the API correctness audit: the
`/intake` honest-501 verified-compliant finding (2.1) and the single
outcome→status mapping gap this task closes (2.2, 2.4). The findings must be
well-formed and drawn from the ``python-engine-api`` owner area so they
consolidate cleanly (spec task 14.1).
"""

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import python_engine_api_findings


def test_findings_are_well_formed_and_in_area():
    findings = python_engine_api_findings()
    assert findings, "the area must record at least one finding"
    for finding in findings:
        assert finding.area == "python-engine-api"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_records_intake_verified_compliant():
    """2.1: the /intake honest-501 outcome is recorded (verified compliant)."""
    findings = python_engine_api_findings()
    intake = next(f for f in findings if f.dedup_key == "python-engine-api:intake-honest-501")
    assert intake.severity is Severity.INFORMATIONAL
    assert "501" in intake.proposed_action
    assert "intake" in intake.subject


def test_records_single_status_mapping_gap():
    """2.2/2.4: the single outcome→status mapping is recorded as the gap closed."""
    findings = python_engine_api_findings()
    mapping = next(
        f for f in findings if f.dedup_key == "python-engine-api:single-outcome-status-mapping"
    )
    assert mapping.severity is Severity.LOW
    assert "outcome→status" in mapping.proposed_action or "2xx" in mapping.proposed_action


def test_records_worker_retirement_decision():
    """2.5: the worker-retirement decision is recorded with a retire action.

    The decision must state the worker is retired (superseded by /publish),
    not retained with a responsibility, and carry the removal action.
    """
    findings = python_engine_api_findings()
    worker = next(f for f in findings if f.dedup_key == "python-engine-api:worker-retirement")
    assert worker.subject == "apps/cna-worker"
    action = worker.proposed_action.lower()
    assert "retire" in action
    # The action must carry the removal/retention decision (retire => remove).
    assert "remove" in action
    # Superseded by the publish endpoint, not retained with a responsibility.
    assert "/publish" in worker.proposed_action
    assert "retained" not in action or "not retained" in action


def test_findings_are_fixable_not_escalations():
    """Requirement 2 gaps are engineering-fixable — no blocker id attached."""
    for finding in python_engine_api_findings():
        assert finding.blocker_id is None


def test_findings_consolidate_into_fixable_entries():
    plan = consolidate(python_engine_api_findings())
    assert plan.entries
    for entry in plan.entries:
        assert entry.is_escalation is False
        assert entry.blocker_id is None
        assert "python-engine-api" in entry.referenced_areas
