"""Unit tests for the ``python-engine-api`` verification step (spec task 4.7).

Asserts the recorded result of the design's section-2 verification suite —
``ruff check cna apps`` / ``ruff format --check``, ``ty check cna``, and
``pytest`` under the 80% coverage gate (Requirements 2.1-2.4). The clean/passing
outcomes are recorded verified-compliant, the residual ``ty`` gap is a fixable
finding, and the two observability Property-16 test failures the suite surfaced
are recorded (owned by the observability area) so they reach the consolidated
plan. None of these is an escalation — every gap is engineering-fixable.
"""

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import python_engine_api_verify_findings
from cna.review.areas.python_engine_api_verify import COVERAGE_GATE, COVERAGE_PERCENT


def test_findings_are_well_formed_and_in_known_areas():
    findings = python_engine_api_verify_findings()
    assert findings, "the verify step must record at least one finding"
    for finding in findings:
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_no_finding_is_an_escalation():
    """Every Requirement 2 verification gap is engineering-fixable — no blocker."""
    for finding in python_engine_api_verify_findings():
        assert finding.blocker_id is None


def test_records_ruff_verified_compliant():
    """ruff check + format are recorded clean (verified compliant)."""
    ruff = next(
        f
        for f in python_engine_api_verify_findings()
        if f.dedup_key == "python-engine-api:verify-ruff-clean"
    )
    assert ruff.area == "python-engine-api"
    assert ruff.severity is Severity.INFORMATIONAL
    action = ruff.proposed_action.lower()
    assert "ruff check" in action
    assert "ruff format" in action
    # The formatting fix must not have weakened any gate.
    assert "no lint rule silenced" in action or "no gate weakened" in action


def test_records_ty_residual_gap_not_in_area_files():
    """ty gap is recorded LOW, fixable, and confined to foundry_agent_client."""
    ty = next(
        f
        for f in python_engine_api_verify_findings()
        if f.dedup_key == "python-engine-api:verify-ty-foundry-agents-gap"
    )
    assert ty.area == "python-engine-api"
    assert ty.severity is Severity.LOW
    assert ty.blocker_id is None
    assert "foundry_agent_client" in ty.subject
    # The gap is explicitly outside this area's own files.
    action = ty.proposed_action.lower()
    assert "api_status" in action and "api_errors" in action
    assert "no type error" in action


def test_records_pytest_coverage_gate_pass():
    """The 80% coverage gate is recorded as passed, with the real percentage."""
    cov = next(
        f
        for f in python_engine_api_verify_findings()
        if f.dedup_key == "python-engine-api:verify-pytest-coverage-gate"
    )
    assert cov.area == "python-engine-api"
    assert cov.severity is Severity.INFORMATIONAL
    # The recorded coverage clears the gate.
    assert COVERAGE_PERCENT >= COVERAGE_GATE
    assert f"{COVERAGE_PERCENT:.2f}" in cov.proposed_action
    assert str(COVERAGE_GATE) in cov.proposed_action


def test_records_observability_property16_failures_under_observability_area():
    """The two Property-16 failures are recorded and owned by observability."""
    failure = next(
        f
        for f in python_engine_api_verify_findings()
        if f.dedup_key == "observability:property16-reserved-logrecord-key-collision"
    )
    # Surfaced by the python-engine-api suite, but owned by the observability area.
    assert failure.area == "observability"
    assert failure.severity is Severity.MEDIUM
    assert failure.blocker_id is None
    action = failure.proposed_action.lower()
    assert "levelname" in action and "processname" in action
    assert "test_logging_config_properties" in failure.subject


def test_findings_consolidate_and_stay_fixable():
    """Consolidation yields fixable entries (no escalations) across two areas."""
    plan = consolidate(python_engine_api_verify_findings())
    assert plan.entries
    for entry in plan.entries:
        assert entry.is_escalation is False
        assert entry.blocker_id is None
    # The observability failure carries its area through consolidation.
    obs = next(
        e
        for e in plan.entries
        if e.dedup_key == "observability:property16-reserved-logrecord-key-collision"
    )
    assert "observability" in obs.referenced_areas
    # And the python-engine-api verified-compliant records carry theirs.
    ruff = next(e for e in plan.entries if e.dedup_key == "python-engine-api:verify-ruff-clean")
    assert "python-engine-api" in ruff.referenced_areas


def test_entries_are_ordered_by_severity_descending():
    """The consolidated plan is severity-ordered (design Property 3)."""
    plan = consolidate(python_engine_api_verify_findings())
    severities = [int(e.severity) for e in plan.entries]
    assert severities == sorted(severities, reverse=True)
