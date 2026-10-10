"""Property-based tests for the production-readiness consolidation engine.

Feature: production-readiness
Property 4: Deduplication is a union and is idempotent

For any set of findings, all findings sharing a ``dedup_key`` collapse into
exactly one ``PlanEntry`` whose ``referenced_areas`` equals the union of the
contributing areas (and whose ``subjects`` likewise equal the union of the
contributing subjects); and consolidating an already-consolidated plan produces
the same plan.

Validates: Requirements 1.5
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review import (
    AREAS,
    Finding,
    RemediationPlan,
    Severity,
    consolidate,
)

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

_AREA = st.sampled_from(sorted(AREAS))
_SEVERITY = st.sampled_from(list(Severity))
# Non-empty once stripped, matching the Finding well-formedness constraint.
_NON_EMPTY_ACTION = st.text(min_size=1).filter(lambda s: s.strip())
# A small, shared alphabet of dedup keys so distinct findings frequently share
# a key and actually exercise the merge/union behaviour.
_DEDUP_KEY = st.sampled_from(["defect-a", "defect-b", "defect-c", "defect-d"])
_SUBJECT = st.text()
# Either fixable (no blocker) or blocker-owned (an R-0NN id). A group is an
# escalation iff any contributing finding is blocker-owned, so leaving this to
# the generator keeps both fixable and escalation groups in play.
_BLOCKER_ID = st.none() | st.sampled_from(
    ["R-001", "R-002", "R-003", "R-004", "R-005", "R-006", "R-008", "R-009"]
)


@st.composite
def _finding(draw: st.DrawFn) -> Finding:
    """Generate a single well-formed ``Finding``."""
    return Finding(
        area=draw(_AREA),
        severity=draw(_SEVERITY),
        proposed_action=draw(_NON_EMPTY_ACTION),
        dedup_key=draw(_DEDUP_KEY),
        subject=draw(_SUBJECT),
        blocker_id=draw(_BLOCKER_ID),
    )


_FINDINGS = st.lists(_finding(), max_size=25)


def _plan_shape(plan: RemediationPlan) -> list[tuple[object, ...]]:
    """A stable, order-sensitive snapshot of a plan's entries for equality.

    ``set`` fields are frozen so tuples compare by value, and the list preserves
    entry order so ordering differences would also surface.
    """
    return [
        (
            e.dedup_key,
            e.severity,
            e.proposed_action,
            frozenset(e.referenced_areas),
            frozenset(e.subjects),
            e.is_escalation,
            e.blocker_id,
        )
        for e in plan.entries
    ]


@_PROPERTY_SETTINGS
@given(findings=_FINDINGS)
def test_property4_dedup_key_collapses_to_one_entry_with_union_areas(
    findings: list[Finding],
) -> None:
    """Feature: production-readiness, Property 4: Deduplication is a union and is idempotent.

    Each ``dedup_key`` present in the input appears in exactly one ``PlanEntry``
    whose ``referenced_areas`` equals the union of the areas of all findings
    sharing that key, and whose ``subjects`` equals the union of their subjects.
    """
    plan = consolidate(findings)

    # Exactly one entry per distinct input dedup_key.
    input_keys = {f.dedup_key for f in findings}
    entry_keys = [e.dedup_key for e in plan.entries]
    assert set(entry_keys) == input_keys
    assert len(entry_keys) == len(input_keys)  # no key appears twice

    entries_by_key = {e.dedup_key: e for e in plan.entries}
    for key in input_keys:
        contributors = [f for f in findings if f.dedup_key == key]
        entry = entries_by_key[key]
        assert entry.referenced_areas == {f.area for f in contributors}
        assert entry.subjects == {f.subject for f in contributors}
        assert entry.severity == max(f.severity for f in contributors)


@_PROPERTY_SETTINGS
@given(findings=_FINDINGS)
def test_property4_consolidation_is_idempotent(
    findings: list[Finding],
) -> None:
    """Feature: production-readiness, Property 4: Deduplication is a union and is idempotent.

    Consolidating an already-consolidated plan produces the same plan:
    ``consolidate(consolidate(findings).entries)`` equals
    ``consolidate(findings)`` by a stable comparable shape.
    """
    once = consolidate(findings)
    twice = consolidate(once.entries)

    assert _plan_shape(twice) == _plan_shape(once)
