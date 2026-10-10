"""Unit tests for escalation wiring in the consolidated plan (spec task 14.3).

Covers the escalation-wiring assertion layer over
:func:`cna.review.build_remediation_plan`: :func:`cna.review.escalation_summary`
and :func:`cna.review.assert_escalations_well_formed`.

The invariant under test (Requirements 1.6, 10.4) is that every
``Escalation_Record`` entry carries its owning ``REVIEW.md`` blocker id, no
fixable entry carries a blocker id, and the escalations cover exactly the
R-005 and R-009 consumers this review declares (the AWS and Azure Terraform
consumers left the core with the deployment layer, TODO.md T-504). R-007 is
resolved-but-not-closed, so its subject stays entirely out of scope and it is
*not* an escalation consumer.
"""

from __future__ import annotations

import re

import pytest

from cna.review import (
    EXPECTED_ESCALATION_BLOCKERS,
    assert_escalations_well_formed,
    build_remediation_plan,
    escalation_summary,
    load_blockers,
)

# The R-0NN shape an escalation's owning blocker id must match.
_R_PATTERN = re.compile(r"R-\d{3,}")

# The blockers actually recorded in REVIEW.md, keyed by id.
_BLOCKERS = load_blockers()


def test_expected_escalation_blocker_set_is_the_declared_consumers():
    """The declared consumer set is R-005 and R-009 (not R-007)."""
    assert EXPECTED_ESCALATION_BLOCKERS == {"R-005", "R-009"}
    # The AWS/Azure Terraform consumers moved to the appliances with the
    # deployment layer (TODO.md T-504); they are not this repository's escalations.
    assert not EXPECTED_ESCALATION_BLOCKERS & {"R-001", "R-002", "R-003", "R-004", "R-006", "R-008"}
    # R-007 is resolved-but-not-closed: its subject stays out of scope, so it is
    # never an escalation consumer.
    assert "R-007" not in EXPECTED_ESCALATION_BLOCKERS


def test_built_plan_escalations_cover_exactly_the_expected_blockers():
    """The built plan's escalations own exactly the expected blocker set."""
    plan = build_remediation_plan()
    summary = escalation_summary(plan)
    assert set(summary) == EXPECTED_ESCALATION_BLOCKERS, (
        f"escalation blockers were {sorted(summary)}"
    )
    # Every expected blocker actually gates at least one escalation entry.
    for blocker_id in EXPECTED_ESCALATION_BLOCKERS:
        assert summary[blocker_id], f"{blocker_id} owns no escalation entry"


def test_each_escalation_carries_a_valid_blocker_id_present_in_review_md():
    """Every escalation carries a non-empty R-0NN id present in REVIEW.md."""
    plan = build_remediation_plan()
    escalations = [entry for entry in plan.entries if entry.is_escalation]
    assert escalations, "the plan must contain escalation entries"
    for entry in escalations:
        assert entry.blocker_id, f"escalation {entry.dedup_key!r} has no blocker_id"
        assert _R_PATTERN.fullmatch(entry.blocker_id), (
            f"escalation {entry.dedup_key!r} has a malformed id {entry.blocker_id!r}"
        )
        assert entry.blocker_id in _BLOCKERS, (
            f"escalation {entry.dedup_key!r} references unknown {entry.blocker_id!r}"
        )


def test_no_fixable_entry_carries_a_blocker_id():
    """A fixable (non-escalation) entry never carries a blocker id."""
    plan = build_remediation_plan()
    for entry in plan.entries:
        if not entry.is_escalation:
            assert entry.blocker_id is None, (
                f"fixable entry {entry.dedup_key!r} carries {entry.blocker_id!r}"
            )


def test_escalation_summary_only_buckets_escalations():
    """escalation_summary groups only escalation entries, keyed by blocker id."""
    plan = build_remediation_plan()
    summary = escalation_summary(plan)
    fixable_keys = {e.dedup_key for e in plan.entries if not e.is_escalation}
    summarized_keys = {e.dedup_key for entries in summary.values() for e in entries}
    assert summarized_keys.isdisjoint(fixable_keys)
    # Each bucket's entries all carry the bucket's blocker id.
    for blocker_id, entries in summary.items():
        for entry in entries:
            assert entry.is_escalation
            assert entry.blocker_id == blocker_id


def test_assert_escalations_well_formed_passes_and_returns_summary():
    """The assertion helper passes on the real plan and returns the summary."""
    plan = build_remediation_plan()
    summary = assert_escalations_well_formed(plan)
    assert set(summary) == EXPECTED_ESCALATION_BLOCKERS


def test_assert_escalations_well_formed_rejects_missing_blocker():
    """A missing expected blocker fails the exact-set assertion."""
    plan = build_remediation_plan()
    # Drop every escalation owned by R-009 so the set is no longer exact.
    plan.entries = [
        entry for entry in plan.entries if not (entry.is_escalation and entry.blocker_id == "R-009")
    ]
    with pytest.raises(AssertionError):
        assert_escalations_well_formed(plan)
