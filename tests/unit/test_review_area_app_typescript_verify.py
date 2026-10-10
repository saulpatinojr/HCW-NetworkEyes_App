"""Unit tests for the ``app-typescript`` verify step (spec task 5.3).

Covers the executed web-area verification (Requirements 1.1/1.2): the
``tsc --noEmit`` and ``next build`` results are recorded verified-compliant
(confirming the task-5.1/5.2 TypeScript edits are type-correct), the broken
``npm run lint`` step is recorded as a fixable residual gap, and the deprecated
``middleware`` convention is recorded as a fixable LOW gap. Every finding is a
fixable app-area record with no ``blocker_id``, and the set consolidates into
the single Remediation_Plan without escalation.
"""

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import app_typescript_verify_findings


def test_findings_are_well_formed_and_in_area():
    findings = app_typescript_verify_findings()
    assert findings, "the verify step must record at least one finding"
    for finding in findings:
        assert finding.area == "app-typescript"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_every_finding_is_fixable_no_blocker_id():
    """5.3: verification records are fixable app-area entries, never escalations."""
    for finding in app_typescript_verify_findings():
        assert finding.blocker_id is None, finding.dedup_key


def test_records_tsc_and_build_verified_compliant():
    """1.1/1.2: the type-check and build passes are recorded verified-compliant."""
    findings = app_typescript_verify_findings()

    tsc = next(f for f in findings if f.dedup_key == "app-typescript:tsc-noemit-clean")
    assert tsc.severity is Severity.INFORMATIONAL
    assert "tsc --noemit" in tsc.proposed_action.lower()

    build = next(f for f in findings if f.dedup_key == "app-typescript:next-build-succeeds")
    assert build.severity is Severity.INFORMATIONAL
    assert "build" in build.proposed_action.lower()


def test_records_broken_lint_step_as_residual_gap():
    """1.1: the missing/broken lint step is recorded as a fixable finding."""
    lint = next(
        f
        for f in app_typescript_verify_findings()
        if f.dedup_key == "app-typescript:lint-step-not-runnable"
    )
    assert lint.severity is Severity.MEDIUM
    assert lint.blocker_id is None
    action = lint.proposed_action.lower()
    assert "next lint" in action
    assert "eslint.config" in action


def test_records_middleware_deprecation_as_low_gap():
    """1.1: the Next 16 middleware->proxy deprecation is recorded as a LOW gap."""
    mw = next(
        f
        for f in app_typescript_verify_findings()
        if f.dedup_key == "app-typescript:middleware-convention-deprecated"
    )
    assert mw.severity is Severity.LOW
    assert mw.blocker_id is None
    assert "proxy" in mw.proposed_action.lower()


def test_consolidation_yields_only_fixable_entries():
    """The verify findings consolidate into fixable entries (no escalation)."""
    plan = consolidate(app_typescript_verify_findings())

    assert plan.entries
    for entry in plan.entries:
        assert entry.is_escalation is False
        assert entry.blocker_id is None
        assert "app-typescript" in entry.referenced_areas
    # Entries are ordered by severity descending (design Property 3).
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)
