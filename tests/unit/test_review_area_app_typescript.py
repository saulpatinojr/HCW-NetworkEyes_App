"""Unit tests for the ``app-typescript`` AWS-view alignment findings (Req 4.4).

Covers the verify-then-close-gaps record for the AWS-view alignment audit (spec
task 5.2): the credential-capture surface is verified compliant (already
AWS-shaped), and each remaining Azure-shaped AWS-facing view (the discovery
topology summary, the subscription/tenant connection framing, and the inventory
label / connection help) is recorded as its own fixable ``Remediation_Plan``
entry. The load-bearing invariant is that every 4.4 entry is a fixable app-area
finding — none carries a ``blocker_id`` — because aligning the views to the AWS
deployment model needs no AWS account (design section "4. Terraform AWS"
escalation boundary).
"""

from cna.review import AREAS, Severity, consolidate
from cna.review.areas import app_typescript_findings


def test_findings_are_well_formed_and_in_area():
    findings = app_typescript_findings()
    assert findings, "the area must record at least one finding"
    for finding in findings:
        assert finding.area == "app-typescript"
        assert finding.area in AREAS
        assert finding.proposed_action.strip()


def test_records_an_entry_per_azure_shaped_aws_view():
    """4.4: each Azure-shaped AWS-facing view gets its own alignment entry."""
    findings = app_typescript_findings()
    keys = {f.dedup_key for f in findings}
    assert "app-typescript:aws-view-discovery-topology-summary" in keys
    assert "app-typescript:aws-view-subscription-tenant-framing" in keys
    assert "app-typescript:aws-view-inventory-label-and-help" in keys


def test_credential_form_is_verified_compliant():
    """The AWS credential-capture surface is already correctly AWS-shaped."""
    findings = app_typescript_findings()
    aligned = next(
        f for f in findings if f.dedup_key == "app-typescript:aws-view-credential-form-aligned"
    )
    assert aligned.severity is Severity.INFORMATIONAL
    assert aligned.blocker_id is None
    assert "credential-form.tsx" in aligned.subject


def test_every_alignment_entry_is_fixable_not_an_escalation():
    """4.4 is a fixable app-area entry: no finding carries a blocker id."""
    findings = app_typescript_findings()
    assert all(f.blocker_id is None for f in findings)


def test_alignment_actions_reference_the_aws_deployment_model():
    """Each alignment action proposes AWS-shaped naming, not Azure relabelling."""
    findings = app_typescript_findings()
    by_key = {f.dedup_key: f for f in findings}

    topology = by_key["app-typescript:aws-view-discovery-topology-summary"]
    topo_action = topology.proposed_action.lower()
    assert "vpc" in topo_action
    assert "platform-aware" in topo_action

    framing = by_key["app-typescript:aws-view-subscription-tenant-framing"]
    framing_action = framing.proposed_action.lower()
    assert "account" in framing_action
    assert "region" in framing_action


def test_findings_consolidate_and_are_severity_ordered():
    """Findings collapse into an ordered plan referencing this area, no escalation."""
    plan = consolidate(app_typescript_findings())
    assert plan.entries
    for entry in plan.entries:
        assert "app-typescript" in entry.referenced_areas
    severities = [entry.severity for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)
    # 4.4 is fixable-only: the consolidated plan carries no escalation entry.
    assert all(not entry.is_escalation for entry in plan.entries)
