"""Unit tests for the production-readiness review data model.

Covers well-formedness enforcement on construction (design Property 1) for
``Finding`` and ``PlanEntry``, plus the ``Severity`` ordering and ``AREAS``
closed set that the consolidation engine relies on.
"""

import pytest

from cna.review import AREAS, Finding, PlanEntry, RemediationPlan, Severity


def test_severity_is_ordered_informational_to_critical():
    assert Severity.INFORMATIONAL == 0
    assert Severity.CRITICAL == 4
    assert (
        Severity.INFORMATIONAL < Severity.LOW < Severity.MEDIUM < Severity.HIGH < Severity.CRITICAL
    )
    # max() over a set of findings yields the most severe.
    assert max(Severity.LOW, Severity.CRITICAL, Severity.MEDIUM) is Severity.CRITICAL


def test_areas_is_the_nine_owner_areas():
    assert len(AREAS) == 9
    assert "terraform-aws" in AREAS
    assert "python-engine-api" in AREAS


def test_finding_well_formed_construction():
    f = Finding(
        area="cicd",
        severity=Severity.HIGH,
        proposed_action="Pin the action reference to a commit SHA.",
        dedup_key="cicd:unpinned-action",
        subject=".github/workflows/212-deploy-aws-split.yml",
    )
    assert f.blocker_id is None
    assert f.severity is Severity.HIGH


def test_finding_accepts_bare_int_severity():
    f = Finding(
        area="documentation",
        severity=2,
        proposed_action="Fix the stale version in README.",
        dedup_key="doc:stale-version",
        subject="README.md",
    )
    assert f.severity is Severity.MEDIUM


def test_finding_rejects_area_outside_the_closed_set():
    with pytest.raises(ValueError, match="area must be one of"):
        Finding(
            area="not-an-area",
            severity=Severity.LOW,
            proposed_action="do a thing",
            dedup_key="k",
            subject="s",
        )


def test_finding_rejects_empty_proposed_action():
    with pytest.raises(ValueError, match="proposed_action"):
        Finding(
            area="observability",
            severity=Severity.LOW,
            proposed_action="   ",
            dedup_key="k",
            subject="s",
        )


def test_finding_rejects_invalid_severity():
    with pytest.raises(ValueError, match="severity"):
        Finding(
            area="observability",
            severity=99,
            proposed_action="do a thing",
            dedup_key="k",
            subject="s",
        )


def test_plan_entry_fixable_must_not_carry_blocker_id():
    with pytest.raises(ValueError, match="fixable entry must not carry a blocker_id"):
        PlanEntry(
            dedup_key="k",
            severity=Severity.LOW,
            proposed_action="do a thing",
            referenced_areas={"cicd"},
            subjects={"s"},
            is_escalation=False,
            blocker_id="R-003",
        )


def test_plan_entry_escalation_requires_blocker_id():
    with pytest.raises(ValueError, match="requires a non-empty blocker_id"):
        PlanEntry(
            dedup_key="k",
            severity=Severity.HIGH,
            proposed_action="escalate",
            referenced_areas={"terraform-aws"},
            subjects={"s"},
            is_escalation=True,
        )


def test_plan_entry_rejects_unknown_referenced_area():
    with pytest.raises(ValueError, match="referenced_areas must be drawn from"):
        PlanEntry(
            dedup_key="k",
            severity=Severity.LOW,
            proposed_action="do a thing",
            referenced_areas={"cicd", "bogus"},
            subjects={"s"},
            is_escalation=False,
        )


def test_remediation_plan_defaults_to_empty():
    plan = RemediationPlan()
    assert plan.entries == []
