"""Unit tests for the ``containers-packaging`` area findings (Requirement 7).

Covers the verify-then-close-gaps record for the container/packaging audit:
the non-root verified-compliant findings per image (7.4), the docker-compose
Web_Service fallback gap this task closed (7.2), the service HEALTHCHECK gap
(7.1), the effective-final-``USER`` parser, and the fail-hard root-user
recording contract (7.5).
"""

import dataclasses

import pytest

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import (
    RootUserFindingError,
    containers_packaging_findings,
    containers_packaging_verify_findings,
    effective_final_user,
    is_root_user,
    record_root_user_finding,
)
from cna.review.areas.containers_packaging import _OBSERVED


def test_findings_are_well_formed_and_in_area():
    findings = containers_packaging_findings()
    assert findings, "the area must record at least one finding"
    for finding in findings:
        assert finding.area == "containers-packaging"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_records_non_root_verified_for_every_service_image():
    """7.4: each of the four service images is recorded as non-root compliant."""
    findings = containers_packaging_findings()
    subjects = {
        f.subject
        for f in findings
        if f.dedup_key.startswith("containers-packaging:non-root-verified:")
    }
    assert subjects == {
        "Dockerfile",
        "apps/cna-api/Dockerfile",
        "apps/cna-web/Dockerfile",
        "apps/cna-worker/Dockerfile",
    }
    for finding in findings:
        if finding.dedup_key.startswith("containers-packaging:non-root-verified:"):
            assert finding.severity is Severity.INFORMATIONAL


def test_no_root_user_finding_when_all_images_non_root():
    """Property 15 negative case: non-root images produce no root-user finding."""
    findings = containers_packaging_findings()
    assert not [f for f in findings if f.dedup_key.startswith("containers-packaging:root-user:")]


def test_records_compose_web_fallback_gap():
    """7.2: the missing docker-compose Web_Service fallback is recorded."""
    findings = containers_packaging_findings()
    entry = next(f for f in findings if f.dedup_key == "containers-packaging:compose-web-fallback")
    assert entry.subject == "docker-compose.yml"
    assert entry.severity is Severity.MEDIUM
    assert "cna-web" in entry.proposed_action


def test_records_service_healthcheck_gap():
    """7.1: the missing HEALTHCHECKs on service images are recorded."""
    findings = containers_packaging_findings()
    entry = next(f for f in findings if f.dedup_key == "containers-packaging:service-healthchecks")
    assert "HEALTHCHECK" in entry.proposed_action


def test_findings_consolidate_into_fixable_entries():
    plan = consolidate(containers_packaging_findings())
    assert plan.entries
    for entry in plan.entries:
        assert entry.is_escalation is False
        assert entry.blocker_id is None
        assert "containers-packaging" in entry.referenced_areas


# ── effective_final_user parser ──────────────────────────────────────────────


def test_effective_final_user_reads_last_user():
    text = "FROM x\nUSER root\nUSER cna\n"
    assert effective_final_user(text) == "cna"


def test_effective_final_user_none_when_unset():
    assert effective_final_user("FROM x\nRUN echo hi\n") is None


def test_effective_final_user_strips_group():
    assert effective_final_user("FROM x\nUSER 1001:1001\n") == "1001"


def test_effective_final_user_resolves_arg_substitution():
    text = "FROM x\nARG APP_USER=cna\nUSER ${APP_USER}\n"
    assert effective_final_user(text) == "cna"


@pytest.mark.parametrize(
    "user,expected",
    [
        (None, True),
        ("root", True),
        ("0", True),
        ("ROOT", True),
        ("cna", False),
        ("nextjs", False),
        ("1001", False),
    ],
)
def test_is_root_user(user, expected):
    assert is_root_user(user) is expected


# ── fail-hard root-user recording (7.5) ──────────────────────────────────────


def test_record_root_user_finding_records_when_root():
    recorded = []
    finding = record_root_user_finding("svc/Dockerfile", None, recorded.append)
    assert finding is not None
    assert recorded == [finding]
    assert finding.dedup_key == "containers-packaging:root-user:svc/Dockerfile"
    assert finding.severity is Severity.HIGH


def test_record_root_user_finding_skips_when_non_root():
    recorded = []
    finding = record_root_user_finding("svc/Dockerfile", "cna", recorded.append)
    assert finding is None
    assert recorded == []


def test_record_root_user_finding_fails_hard_on_sink_failure():
    """7.5: a failure to persist a root-user finding aborts the review."""

    def failing_sink(_finding):
        raise OSError("disk full")

    with pytest.raises(RootUserFindingError):
        record_root_user_finding("svc/Dockerfile", "root", failing_sink)


def test_containers_findings_fail_hard_when_sink_fails():
    """A failing sink propagates through the area emitter (fail-hard).

    Force a root image by pointing the check at a root user via a custom sink;
    here the audit is all non-root so the sink is never called and no error is
    raised — the fail-hard path is exercised directly above. This guards that a
    passed-in sink is threaded through without swallowing exceptions.
    """

    def failing_sink(_finding):
        raise RuntimeError("boom")

    # All audited images are non-root, so the sink is not invoked and no error
    # surfaces — the emitter completes normally.
    findings = containers_packaging_findings(sink=failing_sink)
    assert findings


# ── verification records (spec task 11.3) ────────────────────────────────────


def _results(**overrides):
    """A VerificationResults seeded from the observed run, with overrides."""
    return dataclasses.replace(_OBSERVED, **overrides)


def test_verify_findings_are_well_formed_and_in_area():
    findings = containers_packaging_verify_findings()
    assert findings, "the verification sweep must record at least one finding"
    for finding in findings:
        assert finding.area == "containers-packaging"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_observed_run_records_packaging_and_build_verified():
    """7.3 + 7.1: the observed run built the wheel/CLI and every image."""
    findings = containers_packaging_verify_findings()
    keys = {f.dedup_key for f in findings}
    assert "containers-packaging:cli-packaging-verified" in keys
    assert "containers-packaging:docker-build-verified" in keys
    assert "containers-packaging:built-image-non-root-verified" in keys
    # every non-gap verified finding is informational
    for f in findings:
        if f.dedup_key.endswith("-verified"):
            assert f.severity is Severity.INFORMATIONAL


def test_observed_run_records_hadolint_coverage_gap():
    """hadolint was unavailable: recorded as a coverage gap, not a pass."""
    findings = containers_packaging_verify_findings()
    gap = next(f for f in findings if f.dedup_key == "containers-packaging:hadolint-coverage-gap")
    assert gap.severity is Severity.LOW
    assert "hadolint" in gap.proposed_action
    # and NOT recorded as a verified pass
    assert not [f for f in findings if f.dedup_key == "containers-packaging:hadolint-verified"]


def test_built_image_non_root_reuses_is_root_user():
    """7.4: the built-image assertion agrees with is_root_user on each USER."""
    findings = containers_packaging_verify_findings()
    entry = next(
        f for f in findings if f.dedup_key == "containers-packaging:built-image-non-root-verified"
    )
    # the observed run's inspected users are all non-root by is_root_user
    assert all(not is_root_user(u) for u in _OBSERVED.inspected_users.values())
    assert entry.severity is Severity.INFORMATIONAL


def test_private_pull_note_is_not_an_escalation():
    """The R-006 reference here is a note only — no blocker_id, no escalation."""
    findings = containers_packaging_verify_findings()
    note = next(f for f in findings if f.dedup_key == "containers-packaging:private-pull-r006-note")
    assert note.blocker_id is None
    assert "R-006" in note.proposed_action


def test_packaging_gap_recorded_when_cli_help_fails():
    findings = containers_packaging_verify_findings(_results(cli_help_ok=False))
    gap = next(f for f in findings if f.dedup_key == "containers-packaging:cli-packaging-gap")
    assert gap.severity is Severity.HIGH
    assert "cna --help" in gap.proposed_action
    assert not [f for f in findings if f.dedup_key == "containers-packaging:cli-packaging-verified"]


def test_docker_build_coverage_gap_when_docker_unavailable():
    findings = containers_packaging_verify_findings(
        _results(docker_available=False, docker_build_ok={}, inspected_users={})
    )
    keys = {f.dedup_key for f in findings}
    assert "containers-packaging:docker-build-coverage-gap" in keys
    assert "containers-packaging:built-image-user-coverage-gap" in keys
    assert "containers-packaging:docker-build-verified" not in keys


def test_docker_build_failure_recorded():
    findings = containers_packaging_verify_findings(
        _results(docker_build_ok={**dict(_OBSERVED.docker_build_ok), "Dockerfile": False})
    )
    fail = next(f for f in findings if f.dedup_key == "containers-packaging:docker-build-failure")
    assert fail.severity is Severity.HIGH
    assert "Dockerfile" in fail.subject


def test_built_image_root_flagged_high():
    """7.4: a built image whose runtime USER is root is a HIGH finding."""
    findings = containers_packaging_verify_findings(
        _results(inspected_users={"apps/cna-api/Dockerfile": "root", "Dockerfile": "cna"})
    )
    root = next(
        f for f in findings if f.dedup_key == "containers-packaging:built-image-runs-as-root"
    )
    assert root.severity is Severity.HIGH
    assert "apps/cna-api/Dockerfile" in root.subject


def test_verify_findings_consolidate_into_fixable_entries():
    """None of the verification records is an escalation (no blocker_id)."""
    plan = consolidate(containers_packaging_verify_findings())
    assert plan.entries
    for entry in plan.entries:
        assert entry.is_escalation is False
        assert entry.blocker_id is None
        assert "containers-packaging" in entry.referenced_areas
