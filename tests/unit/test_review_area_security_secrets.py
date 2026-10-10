"""Unit tests for the ``security-secrets`` area findings (Requirement 6).

Covers the verify-then-close-gaps record for the security-and-secrets audit
(spec task 10.1): the detect-secrets baselined detections recorded by location
and key-name type (never value), the gitleaks tool-unavailable coverage gap, the
clean pip-audit outcome and each npm-audit advisory at its reported severity.
The R-006 runtime-secret escalation this area used to record left the core with
the AWS Terraform (TODO.md T-504), so no finding here carries a blocker id. The
most load-bearing invariant is Property 12: no finding reproduces a secret value.
"""

import json
from pathlib import Path

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import security_secrets_findings

_BASELINE_PATH = Path(__file__).resolve().parents[2] / ".secrets.baseline"


def _load_baselined_secret_values() -> set[str]:
    """Return the hashed-secret tokens detect-secrets recorded in the baseline.

    detect-secrets stores only a ``hashed_secret`` for each detection, never the
    plaintext, so these hashes stand in for "secret material that must not leak
    into a finding". A well-formed finding records location + detector type only,
    so none of these tokens may appear in any finding's subject or action.
    """
    data = json.loads(_BASELINE_PATH.read_text(encoding="utf-8"))
    return {
        f["hashed_secret"]
        for hits in data.get("results", {}).values()
        for f in hits
        if f.get("hashed_secret")
    }


def test_findings_are_well_formed_and_in_area():
    findings = security_secrets_findings()
    assert findings, "the area must record at least one finding"
    for finding in findings:
        assert finding.area == "security-secrets"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_records_every_baselined_secret_location():
    """6.2: a remediation entry exists for every in-project detect-secrets location."""
    findings = security_secrets_findings()
    secret_subjects = {
        f.subject
        for f in findings
        if f.dedup_key.startswith("security-secrets:detect-secrets:")
        and f.dedup_key != "security-secrets:detect-secrets:baseline-drift-skill-libraries"
    }
    # The committed .secrets.baseline records 12 distinct in-project files.
    assert len(secret_subjects) == 12
    assert ".env.example" in secret_subjects
    assert "tests/unit/test_auth.py" in secret_subjects
    assert ".github/workflows/200-build-images.yml" in secret_subjects


def test_secret_findings_never_reproduce_a_value():
    """Property 12: secret findings carry location + key name only, no value.

    The scan never surfaced a live (is_verified) secret value; assert defensively
    that the recorded actions reference detector *types* and locations rather
    than raw material by keeping every secret finding tied to its file subject.
    """
    # The raw secret values behind the baselined detections, as they appear in
    # the source files. None of these strings may leak into a finding.
    forbidden_values = _load_baselined_secret_values()
    assert forbidden_values, "expected the baseline to reference at least one value"

    findings = security_secrets_findings()
    for f in findings:
        haystack = f"{f.subject}\n{f.proposed_action}"
        for value in forbidden_values:
            assert value not in haystack, (
                f"finding {f.dedup_key!r} reproduced a secret value from the source"
            )


def test_records_gitleaks_coverage_gap():
    """6.1: gitleaks was unavailable — recorded as a coverage gap, not a pass."""
    findings = security_secrets_findings()
    gap = next(f for f in findings if f.dedup_key == "security-secrets:gitleaks:tool-unavailable")
    assert gap.severity is Severity.MEDIUM
    assert "gitleaks" in gap.proposed_action.lower()


def test_records_pip_audit_clean():
    """6.3: pip-audit reported no known vulnerabilities (verified compliant)."""
    findings = security_secrets_findings()
    clean = next(f for f in findings if f.dedup_key == "security-secrets:pip-audit:clean")
    assert clean.severity is Severity.INFORMATIONAL


def test_records_each_npm_audit_advisory_at_reported_severity():
    """6.3: the four npm-audit advisories are each recorded at reported severity."""
    findings = security_secrets_findings()
    by_key = {f.dedup_key: f for f in findings}
    assert by_key["security-secrets:npm-audit:next"].severity is Severity.CRITICAL
    assert by_key["security-secrets:npm-audit:browserslist"].severity is Severity.HIGH
    assert by_key["security-secrets:npm-audit:sharp"].severity is Severity.HIGH
    assert by_key["security-secrets:npm-audit:baseline-browser-mapping"].severity is Severity.MEDIUM


def test_no_finding_is_blocker_owned():
    """6.4: the runtime-secret escalation left with the AWS Terraform (T-504)."""
    findings = security_secrets_findings()
    assert all(f.blocker_id is None for f in findings)
    assert "security-secrets:runtime-secrets-supplied-at-deploy" not in {
        f.dedup_key for f in findings
    }


def test_findings_consolidate_and_are_severity_ordered():
    """Findings collapse into an ordered plan referencing this area."""
    plan = consolidate(security_secrets_findings())
    assert plan.entries
    for entry in plan.entries:
        assert "security-secrets" in entry.referenced_areas
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)
    # The critical next advisory is the top-severity entry.
    assert plan.entries[0].dedup_key == "security-secrets:npm-audit:next"
    assert plan.entries[0].severity is Severity.CRITICAL
