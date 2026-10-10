"""Unit tests for the ``cicd`` area findings (Requirement 5.1/5.2 CI/CD).

Covers the verify-then-close-gaps record for the core's GitHub Actions workflows
(spec task 9.1): the self-hosted-only SPOF entries (5.2), the one GitHub-hosted
workflow recorded as an informational non-SPOF so every workflow is covered,
and the best-practice gaps this task closed in-tree (per-job timeout-minutes and
concurrency guards) plus the verified-compliant least-privilege permissions
record. Third-party action SHA-pinning is spec task 9.3's job, so no finding
here carries a blocker_id. The deploy and operations workflows left the core
with the deployment layer (TODO.md T-504) and are reviewed in the appliances.
"""

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import cicd_findings, cicd_verify_findings
from cna.review.areas.cicd import (
    GITHUB_HOSTED_WORKFLOWS,
    SELF_HOSTED_ONLY_WORKFLOWS,
)

# The full set of numbered workflows under .github/workflows/.
_ALL_WORKFLOWS = SELF_HOSTED_ONLY_WORKFLOWS + GITHUB_HOSTED_WORKFLOWS


def test_findings_are_well_formed_and_in_area():
    findings = cicd_findings()
    assert findings, "the area must record at least one finding"
    for finding in findings:
        assert finding.area == "cicd"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()
        assert finding.dedup_key.startswith("cicd:")


def test_topology_covers_all_core_workflows():
    """5.1: exactly four workflows, all GitHub-hosted since the runner retired."""
    assert len(SELF_HOSTED_ONLY_WORKFLOWS) == 0
    assert len(GITHUB_HOSTED_WORKFLOWS) == 4
    assert len(_ALL_WORKFLOWS) == 4
    assert GITHUB_HOSTED_WORKFLOWS == (
        "200-build-images.yml",
        "300-test-codebase.yml",
        "310-release-version.yml",
        "370-registry-cleanup.yml",
    )
    # No workflow is both self-hosted-only and GitHub-hosted.
    assert not set(SELF_HOSTED_ONLY_WORKFLOWS) & set(GITHUB_HOSTED_WORKFLOWS)


def test_every_self_hosted_only_workflow_is_flagged_as_a_spof():
    """5.2: each self-hosted-only workflow gets a SPOF entry with a mitigation.

    The set is empty since the runner retired, so no MEDIUM SPOF entry may
    remain; the assertion still pins the invariant for a future regression.
    """
    findings = cicd_findings()
    spof_subjects = {
        f.subject.rsplit("/", 1)[-1]
        for f in findings
        if f.dedup_key.startswith("cicd:self-hosted-spof:") and f.severity is Severity.MEDIUM
    }
    assert spof_subjects == set(SELF_HOSTED_ONLY_WORKFLOWS)
    # Each SPOF finding carries a concrete mitigation, not just a flag.
    for finding in findings:
        if (
            finding.dedup_key.startswith("cicd:self-hosted-spof:")
            and finding.severity is Severity.MEDIUM
        ):
            assert "self-hosted" in finding.proposed_action.lower()
            assert "mitigate" in finding.proposed_action.lower()


def test_github_hosted_workflow_recorded_as_informational_non_spof():
    """5.2 counter-case: every ubuntu-latest workflow is not a self-hosted SPOF."""
    findings = cicd_findings()
    for workflow in GITHUB_HOSTED_WORKFLOWS:
        informational_spof = [
            f for f in findings if f.dedup_key == f"cicd:self-hosted-spof:{workflow}"
        ]
        assert len(informational_spof) == 1, workflow
        assert informational_spof[0].severity is Severity.INFORMATIONAL
        assert informational_spof[0].subject.endswith(workflow)
        assert "ubuntu-latest" in informational_spof[0].proposed_action


def test_all_core_workflows_are_covered():
    """Every core workflow appears as a subject in the findings."""
    findings = cicd_findings()
    covered = {
        f.subject.rsplit("/", 1)[-1]
        for f in findings
        if f.dedup_key.startswith("cicd:self-hosted-spof:")
    }
    assert covered == set(_ALL_WORKFLOWS)
    assert len(covered) == 4


def test_best_practice_gaps_are_recorded():
    """The permissions/timeout/concurrency best-practice records are present."""
    findings = cicd_findings()
    keys = {f.dedup_key for f in findings}
    assert "cicd:least-privilege-permissions" in keys
    assert "cicd:job-timeouts" in keys
    assert "cicd:concurrency-guards" in keys


def test_task_9_1_records_no_blocker_ids():
    """9.3 owns the R-003 escalation, so 9.1 records no blocker_id."""
    findings = cicd_findings()
    assert all(f.blocker_id is None for f in findings)


def test_findings_consolidate_into_fixable_entries():
    """Without blocker ids, findings consolidate into fixable plan entries.

    R-003/SHA-pinning is spec task 9.3's job; here the raw findings collapse
    into ordered, fixable entries that reference the cicd area.
    """
    plan = consolidate(cicd_findings())
    assert plan.entries
    for entry in plan.entries:
        assert entry.is_escalation is False
        assert entry.blocker_id is None
        assert "cicd" in entry.referenced_areas
    # Severity ordering (Property 3) holds on the consolidated plan.
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)


# --- Spec task 9.5: actionlint + YAML-parse verification (Requirement 5.1) ---


def test_verify_findings_are_well_formed_and_in_area():
    """5.1 verify records are well-formed cicd-area findings with no blocker."""
    findings = cicd_verify_findings()
    assert findings, "the verify step must record at least one finding"
    for finding in findings:
        assert finding.area == "cicd"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()
        assert finding.dedup_key.startswith("cicd:")
        # 9.5 is a local, non-gated verification: no REVIEW.md blocker is owned.
        assert finding.blocker_id is None


def test_verify_records_actionlint_and_yaml_parse():
    """Both the actionlint sweep and YAML-parse validation are recorded (5.1)."""
    findings = cicd_verify_findings()
    keys = {f.dedup_key for f in findings}
    assert "cicd:actionlint-sweep" in keys
    assert "cicd:yaml-parse-validation" in keys


def test_verify_findings_are_verified_compliant_informational():
    """actionlint reported 0 errors and YAML parsed clean → informational."""
    findings = cicd_verify_findings()
    for finding in findings:
        assert finding.severity is Severity.INFORMATIONAL
        action = finding.proposed_action.lower()
        assert "verified compliant" in action
    # The actionlint record names the tool and the clean result.
    actionlint = next(f for f in findings if f.dedup_key == "cicd:actionlint-sweep")
    assert "actionlint" in actionlint.proposed_action.lower()
    assert "0 errors" in actionlint.proposed_action
    assert "every workflow" in actionlint.proposed_action


def test_verify_findings_consolidate_into_fixable_entries():
    """Verify records carry no blocker id, so they stay fixable/informational."""
    plan = consolidate(cicd_verify_findings())
    assert plan.entries
    for entry in plan.entries:
        assert entry.is_escalation is False
        assert entry.blocker_id is None
        assert "cicd" in entry.referenced_areas


def test_all_workflow_files_parse_as_yaml():
    """9.5 YAML-parse check reproduced: every real workflow file parses.

    Guards against a future 9.1/9.3-style edit reintroducing a YAML break. The
    core keeps only the build/test/release/registry workflows — the deploy and
    operations workflows moved to the appliance repositories (TODO.md T-504).
    """
    import pathlib

    import yaml

    workflows_dir = pathlib.Path(__file__).resolve().parents[2] / ".github" / "workflows"
    files = sorted(workflows_dir.glob("*.yml"))
    assert {path.name for path in files} == {
        "200-build-images.yml",
        "300-test-codebase.yml",
        "310-release-version.yml",
        "370-registry-cleanup.yml",
    }
    for path in files:
        # yaml.safe_load raises on malformed YAML; a clean parse is the assertion.
        yaml.safe_load(path.read_text(encoding="utf-8"))
