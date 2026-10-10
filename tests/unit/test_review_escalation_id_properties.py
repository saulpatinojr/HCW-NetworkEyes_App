"""Property-based tests for escalation blocker-id validity.

Feature: production-readiness
Property 5: Escalations carry a valid owning blocker id

For any RemediationPlan, every entry marked as an Escalation_Record carries a
non-empty ``blocker_id`` matching the ``R-0NN`` pattern and present in
``REVIEW.md``, and no fixable entry carries a blocker id.

Validates: Requirements 1.6, 10.4
"""

from __future__ import annotations

import re

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review import (
    AREAS,
    Finding,
    consolidate,
    gate_finding,
    load_blockers,
)

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

# The blockers actually recorded in REVIEW.md. gate_finding rejects a finding
# that names a blocker id absent from this mapping (an escalation must map to a
# real REVIEW.md blocker), so the generator draws blocker ids only from here.
_BLOCKERS = load_blockers()
_BLOCKER_IDS = sorted(_BLOCKERS)

# The R-0NN pattern the design requires an escalation's blocker_id to match.
_R_PATTERN = re.compile(r"R-\d{3,}")

_AREA = st.sampled_from(sorted(AREAS))
_SEVERITY = st.sampled_from([0, 1, 2, 3, 4])
_NON_EMPTY_ACTION = st.text(min_size=1).filter(lambda s: s.strip())
_DEDUP_KEY = st.sampled_from(["defect-a", "defect-b", "defect-c", "defect-d"])
_SUBJECT = st.text()
# Either fixable (no owning blocker) or blocker-owned (an id present in
# REVIEW.md). This keeps both fixable and escalation entries in play, including
# R-007 which is resolved-but-not-closed (still an escalation).
_BLOCKER_ID = st.none() | st.sampled_from(_BLOCKER_IDS)


@st.composite
def _finding(draw: st.DrawFn) -> Finding:
    """Generate a single well-formed ``Finding``, blocker-owned or not."""
    return Finding(
        area=draw(_AREA),
        severity=draw(_SEVERITY),
        proposed_action=draw(_NON_EMPTY_ACTION),
        dedup_key=draw(_DEDUP_KEY),
        subject=draw(_SUBJECT),
        blocker_id=draw(_BLOCKER_ID),
    )


_FINDINGS = st.lists(_finding(), max_size=25)


def _assert_property5(entries: list) -> None:
    """Every escalation carries a valid, known blocker id; no fixable does."""
    for entry in entries:
        if entry.is_escalation:
            # Non-empty, matches R-0NN, and names a real REVIEW.md blocker.
            assert entry.blocker_id
            assert _R_PATTERN.fullmatch(entry.blocker_id)
            assert entry.blocker_id in _BLOCKERS
        else:
            # A fixable entry never carries a blocker id.
            assert entry.blocker_id is None


@_PROPERTY_SETTINGS
@given(findings=_FINDINGS)
def test_property5_gate_finding_escalations_carry_valid_blocker_id(
    findings: list[Finding],
) -> None:
    """Feature: production-readiness, Property 5: Escalations carry a valid owning blocker id.

    Running arbitrary findings (a mix of blocker-owned and not) through the
    scope gate with blockers loaded from ``REVIEW.md`` yields plan entries where
    every escalation carries a non-empty ``R-0NN`` blocker id present in
    ``REVIEW.md`` and no fixable entry carries a blocker id.
    """
    entries = [gate_finding(f, _BLOCKERS) for f in findings]
    _assert_property5(entries)


@_PROPERTY_SETTINGS
@given(findings=_FINDINGS)
def test_property5_consolidated_plan_escalations_carry_valid_blocker_id(
    findings: list[Finding],
) -> None:
    """Feature: production-readiness, Property 5: Escalations carry a valid owning blocker id.

    The same invariant holds after consolidation: every escalation entry in the
    consolidated ``RemediationPlan`` carries a valid owning blocker id present
    in ``REVIEW.md`` and no fixable entry carries a blocker id.
    """
    plan = consolidate(findings)
    _assert_property5(plan.entries)
