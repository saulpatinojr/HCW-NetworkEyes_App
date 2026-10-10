"""Property-based tests for consolidation severity ordering.

Feature: production-readiness
Property 3: The plan is ordered by severity

For any set of findings, consolidating them yields a ``RemediationPlan`` whose
entries are in non-increasing severity order.

Validates: Requirements 1.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review import AREAS, Finding, Severity, consolidate

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

_AREA = st.sampled_from(sorted(AREAS))
_SEVERITY = st.sampled_from(list(Severity))
# Non-empty once stripped: mirrors Finding's well-formedness rule.
_NON_EMPTY_ACTION = st.text(min_size=1).filter(lambda s: s.strip())


@st.composite
def _findings(draw: st.DrawFn) -> Finding:
    """Draw a single well-formed ``Finding``.

    ``dedup_key`` is drawn from a small pool so generated lists exercise both
    distinct entries and merges (findings sharing a key collapse into one
    entry), keeping ordering meaningful across a realistic input space.
    """
    return Finding(
        area=draw(_AREA),
        severity=draw(_SEVERITY),
        proposed_action=draw(_NON_EMPTY_ACTION),
        dedup_key=draw(st.sampled_from(["d0", "d1", "d2", "d3", "d4"])),
        subject=draw(st.text()),
        blocker_id=None,
    )


@_PROPERTY_SETTINGS
@given(findings=st.lists(_findings()))
def test_property3_plan_entries_are_non_increasing_in_severity(
    findings: list[Finding],
) -> None:
    """Feature: production-readiness, Property 3: The plan is ordered by severity.

    Consolidating an arbitrary list of findings yields a plan whose entries are
    ordered by severity descending: each entry's severity is >= the next.
    """
    plan = consolidate(findings)

    severities = [int(entry.severity) for entry in plan.entries]
    assert severities == sorted(severities, reverse=True)
