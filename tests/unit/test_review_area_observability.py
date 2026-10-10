"""Unit tests for the ``observability`` area findings (Requirement 8).

Covers the verify-then-close-gaps record for the observability audit (spec task
12.1): the structured-logging audit across the API, web, and core engine (8.1 /
8.2 — two verified-compliant surfaces plus the API basicConfig gap this task
closes), and the AI-path coverage requirement (8.3 — a fixable trace/span +
token-usage entry and the R-005 live-Bedrock escalation). The load-bearing
invariants are that only the live-Bedrock finding is blocker-owned (R-005) and
that it gates to an ``Escalation_Record``.
"""

from cna.review import AREAS, Severity, consolidate, gate_finding, load_blockers
from cna.review.areas import observability_findings


def test_findings_are_well_formed_and_in_area():
    findings = observability_findings()
    assert findings, "the area must record at least one finding"
    for finding in findings:
        assert finding.area == "observability"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_covers_all_three_reviewed_surfaces():
    """8.1: the API, web, and core engine are each audited for structured logs."""
    findings = observability_findings()
    keys = {f.dedup_key for f in findings}
    assert "observability:core-engine-structured-json-logging" in keys
    assert "observability:web-onrequesterror-structured-logging" in keys
    assert "observability:api-structured-json-logging" in keys


def test_verified_compliant_surfaces_are_informational():
    """The core-engine and web structured-log surfaces are verified compliant."""
    findings = observability_findings()
    by_key = {f.dedup_key: f for f in findings}
    assert (
        by_key["observability:core-engine-structured-json-logging"].severity
        is Severity.INFORMATIONAL
    )
    assert (
        by_key["observability:web-onrequesterror-structured-logging"].severity
        is Severity.INFORMATIONAL
    )


def test_api_structured_logging_gap_is_a_fixable_low():
    """8.2: the API basicConfig gap is a fixable LOW finding (no blocker)."""
    findings = observability_findings()
    api = next(f for f in findings if f.dedup_key == "observability:api-structured-json-logging")
    assert api.severity is Severity.LOW
    assert api.blocker_id is None
    assert api.subject == "apps/cna-api/main.py"


def test_ai_path_trace_token_coverage_is_fixable():
    """8.3: the non-Bedrock AI-path coverage entry is fixable (no blocker)."""
    findings = observability_findings()
    ai = next(f for f in findings if f.dedup_key == "observability:ai-path-trace-token-coverage")
    assert ai.blocker_id is None
    action = ai.proposed_action.lower()
    assert "token" in action
    assert "trace" in action or "span" in action


def test_ai_path_bedrock_coverage_references_r005():
    """8.3: the live-Bedrock AI-path coverage escalation carries blocker_id R-005."""
    findings = observability_findings()
    esc = next(f for f in findings if f.dedup_key == "observability:ai-path-bedrock-coverage")
    assert esc.blocker_id == "R-005"


def test_only_the_bedrock_finding_is_blocker_owned():
    """Every finding except the R-005 escalation is engineering-fixable."""
    findings = observability_findings()
    blocker_owned = [f for f in findings if f.blocker_id is not None]
    assert len(blocker_owned) == 1
    assert blocker_owned[0].dedup_key == "observability:ai-path-bedrock-coverage"
    assert blocker_owned[0].blocker_id == "R-005"


def test_r005_finding_gates_to_an_escalation_entry():
    """Through the scope gate, the R-005 finding becomes an Escalation_Record."""
    blockers = load_blockers()
    esc = next(
        f
        for f in observability_findings()
        if f.dedup_key == "observability:ai-path-bedrock-coverage"
    )
    entry = gate_finding(esc, blockers)
    assert entry.is_escalation is True
    assert entry.blocker_id == "R-005"


def test_findings_consolidate_and_are_severity_ordered():
    """Findings collapse into an ordered plan referencing this area."""
    plan = consolidate(observability_findings())
    assert plan.entries
    for entry in plan.entries:
        assert "observability" in entry.referenced_areas
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)
    # Exactly one consolidated entry is an escalation — the R-005 Bedrock path.
    escalations = [e for e in plan.entries if e.is_escalation]
    assert len(escalations) == 1
    assert escalations[0].blocker_id == "R-005"
