"""Unit tests for the ``documentation`` area findings (Requirement 9).

Covers the verify-then-close-gaps record for the documentation audit (spec
task 13.1): the accuracy cross-checks recorded verified-compliant (9.1), the
executable-status entries for the documented CLI/AWS deploy paths (9.2), one
plan entry per still-open doc task (T-304 only; T-401 is Done and recorded
compliant, T-103 is withdrawn) (9.3), and, since 2026-10-27, no escalation: the
R-009 wiki-publication finding was removed with the wiki (REVIEW.md R-031).
"""

from network_assessment.review import AREAS, Severity, consolidate, gate_finding, load_blockers
from network_assessment.review.areas import documentation_findings, documentation_verify_findings


def test_findings_are_well_formed_and_in_area():
    findings = documentation_findings()
    assert findings, "the area must record at least one finding"
    for finding in findings:
        assert finding.area == "documentation"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_records_version_and_cli_accuracy_verified_compliant():
    """9.1: version and CLI-entry-point cross-checks are recorded compliant."""
    by_key = {f.dedup_key: f for f in documentation_findings()}
    version = by_key["documentation:version-accurate"]
    cli = by_key["documentation:cli-entry-point-accurate"]
    assert version.severity is Severity.INFORMATIONAL
    assert "0.8.0b0" in version.proposed_action
    assert cli.severity is Severity.INFORMATIONAL
    assert "network_assessment.cli.main:cli" in cli.proposed_action


def test_records_four_document_model_and_workflow_accuracy():
    """9.1: the four-doc model and workflow references are recorded compliant."""
    by_key = {f.dedup_key: f for f in documentation_findings()}
    assert by_key["documentation:four-document-model-accurate"].severity is Severity.INFORMATIONAL
    assert by_key["documentation:workflow-references-accurate"].severity is Severity.INFORMATIONAL


def test_records_executable_status_of_documented_paths():
    """9.2: the CLI and AWS deploy paths carry an executable-status entry."""
    by_key = {f.dedup_key: f for f in documentation_findings()}
    cli_path = by_key["documentation:cli-path-requires-install"]
    aws_path = by_key["documentation:aws-deploy-path-not-executable"]
    assert cli_path.severity is Severity.LOW
    assert "install" in cli_path.proposed_action.lower()
    assert aws_path.severity is Severity.LOW
    assert "not executable" in aws_path.proposed_action.lower()


def test_records_t304_as_the_only_open_doc_task():
    """9.3: T-304 is open and recorded; T-401 is Done and T-103 is withdrawn, so neither is."""
    by_key = {f.dedup_key: f for f in documentation_findings()}
    assert "documentation:open-task:T-304" in by_key
    # T-304 names the Log Analytics migration.
    assert "T-304" in by_key["documentation:open-task:T-304"].proposed_action
    # T-401 is Done -> no open-task entry, only a verified-compliant record.
    assert "documentation:open-task:T-401" not in by_key
    assert by_key["documentation:t-401-closed"].severity is Severity.INFORMATIONAL
    # T-103 (confirm the ADR pages on the wiki) was withdrawn on 2026-10-27 with the wiki.
    assert "documentation:open-task:T-103" not in by_key
    open_tasks = [key for key in by_key if key.startswith("documentation:open-task:")]
    assert open_tasks == ["documentation:open-task:T-304"]


def test_open_doc_tasks_are_fixable_not_escalations():
    """The open doc task is engineering-tracked, not blocker-owned."""
    by_key = {f.dedup_key: f for f in documentation_findings()}
    assert by_key["documentation:open-task:T-304"].blocker_id is None


def test_the_wiki_publication_escalation_is_gone():
    """The wiki is deleted and R-009 is superseded (REVIEW.md R-031): nothing is left to escalate."""
    keys = {f.dedup_key for f in documentation_findings()}
    assert "documentation:wiki-publication-r009" not in keys


def test_no_documentation_finding_is_blocker_owned():
    """Every finding of this area is engineering-fixable; none carries a blocker id."""
    assert all(f.blocker_id is None for f in documentation_findings())


def test_the_audit_findings_gate_without_escalation():
    """Through the scope gate every audit finding stays a fixable entry."""
    blockers = load_blockers()
    for finding in documentation_findings():
        entry = gate_finding(finding, blockers)
        assert entry.is_escalation is False
        assert entry.blocker_id is None


def test_the_finding_keys_that_still_make_sense_are_unchanged():
    """The dedup keys are identifiers other records may cite; only the two meaningless ones went."""
    keys = {f.dedup_key for f in documentation_findings()}
    assert keys == {
        "documentation:version-accurate",
        "documentation:cli-entry-point-accurate",
        "documentation:four-document-model-accurate",
        "documentation:workflow-references-accurate",
        "documentation:t-401-closed",
        "documentation:cli-path-requires-install",
        "documentation:aws-deploy-path-not-executable",
        "documentation:open-task:T-304",
    }


def test_the_findings_describe_the_current_document_model():
    """The removed working document and the deleted wiki are not offered as the current state."""
    findings = documentation_findings() + documentation_verify_findings()
    for finding in findings:
        text = f"{finding.proposed_action} {finding.subject}"
        assert "CNA-0.90-updates.md" not in text, finding.dedup_key
        assert "Wiki" not in text, finding.dedup_key
    by_key = {f.dedup_key: f for f in findings}
    model = by_key["documentation:four-document-model-accurate"].proposed_action
    assert "REFACTOR_APP.md" in model and "CLAUDE.md" in model and "docs/" in model
    validator = by_key["documentation:model-validator-passes"].proposed_action
    assert "docs/" in validator and "REFACTOR_APP.md" in validator


def test_findings_consolidate_and_are_severity_ordered():
    """Findings collapse into an ordered plan referencing this area."""
    plan = consolidate(documentation_findings())
    assert plan.entries
    for entry in plan.entries:
        assert "documentation" in entry.referenced_areas
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)


# --- Documentation-model verification (spec task 13.2, Requirement 9.1/9.2) ---


def test_verify_findings_are_well_formed_and_in_area():
    """The verification findings are well-formed documentation findings."""
    findings = documentation_verify_findings()
    assert findings, "the verification must record at least one finding"
    for finding in findings:
        assert finding.area == "documentation"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_verify_findings_are_all_verified_compliant():
    """13.2: the validator and link/command checks all pass -> INFORMATIONAL."""
    findings = documentation_verify_findings()
    for finding in findings:
        assert finding.severity is Severity.INFORMATIONAL
        # Verified-compliant findings are engineering-recorded, never blocker-owned.
        assert finding.blocker_id is None


def test_verify_records_validator_link_and_command_checks():
    """13.2: the three verification checks are each recorded."""
    by_key = {f.dedup_key: f for f in documentation_verify_findings()}
    assert "documentation:model-validator-passes" in by_key
    assert "documentation:links-resolve" in by_key
    assert "documentation:commands-and-workflows-resolve" in by_key
    # The validator entry names the script that was run.
    assert (
        "validate_documentation_model.py" in by_key["documentation:model-validator-passes"].subject
    )
    # The command/workflow entry names a referenced workflow and the CLI entry point.
    commands = by_key["documentation:commands-and-workflows-resolve"].proposed_action
    assert "300-test-codebase.yml" in commands
    assert "network_assessment.cli.main:cli" in commands


def test_verify_findings_consolidate_into_ordered_plan():
    """The verification findings collapse into an ordered plan for this area."""
    plan = consolidate(documentation_verify_findings())
    assert plan.entries
    for entry in plan.entries:
        assert "documentation" in entry.referenced_areas
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)


def test_verify_findings_are_disjoint_from_audit_findings():
    """13.2 verification uses its own dedup keys, distinct from the 13.1 audit."""
    audit_keys = {f.dedup_key for f in documentation_findings()}
    verify_keys = {f.dedup_key for f in documentation_verify_findings()}
    assert audit_keys.isdisjoint(verify_keys)


def test_verify_findings_gate_without_escalation():
    """Verified-compliant findings pass the scope gate as fixable, not escalations."""
    blockers = load_blockers()
    for finding in documentation_verify_findings():
        entry = gate_finding(finding, blockers)
        assert entry.is_escalation is False
        assert entry.blocker_id is None
