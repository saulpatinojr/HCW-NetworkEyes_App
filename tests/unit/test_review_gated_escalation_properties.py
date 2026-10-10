"""Property-based tests for gated-dependency escalation in the review scope gate.

Feature: production-readiness
Property 6: Gated dependencies become escalations

For any finding whose subject is owned by an open (not-closed) ``REVIEW.md``
blocker, or whose remediation requires a live deploy, secret provisioning, or
account setup, the resulting plan entry is an ``Escalation_Record`` (never an
emitted fix). The converse anchors the boundary: once a blocker's status is
CLOSED its subject returns to automated scope, so a finding owned by a closed
blocker yields a fixable entry that carries no ``blocker_id``.

Validates: Requirements 4.5, 10.1, 10.2
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review import (
    AREAS,
    Blocker,
    BlockerStatus,
    Finding,
    Severity,
    gate_finding,
    load_blockers,
)

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

# The real REVIEW.md blockers. In the current file every blocker is NOT closed
# (R-007 is resolved-but-not-closed), so every id here owns a subject that is
# out of automated scope and must force escalation.
_BLOCKERS = load_blockers()
_NOT_CLOSED_IDS = sorted(
    bid for bid, b in _BLOCKERS.items() if b.status is BlockerStatus.NOT_CLOSED
)

# Sanity: the fixture we build the property on matches the stated state — every
# real blocker is not closed, so the not-closed set is the full set.
assert _NOT_CLOSED_IDS == sorted(_BLOCKERS), "expected every REVIEW.md blocker to be not-closed"

_AREA = st.sampled_from(sorted(AREAS))
_SEVERITY = st.sampled_from(list(Severity))
# Non-empty once stripped, matching the Finding well-formedness constraint.
_NON_EMPTY_ACTION = st.text(min_size=1).filter(lambda s: s.strip())
_SUBJECT = st.text()
# A blocker id drawn from the not-closed blockers in REVIEW.md.
_NOT_CLOSED_BLOCKER_ID = st.sampled_from(_NOT_CLOSED_IDS)

# A synthetic CLOSED blocker id, disjoint from the real R-0NN set, used to
# exercise the converse: a closed owner returns its subject to scope.
_CLOSED_BLOCKER_ID = "R-900"


@_PROPERTY_SETTINGS
@given(
    area=_AREA,
    severity=_SEVERITY,
    proposed_action=_NON_EMPTY_ACTION,
    dedup_key=st.text(),
    subject=_SUBJECT,
    blocker_id=_NOT_CLOSED_BLOCKER_ID,
)
def test_property6_open_blocker_owned_finding_becomes_escalation(
    area: str,
    severity: Severity,
    proposed_action: str,
    dedup_key: str,
    subject: str,
    blocker_id: str,
) -> None:
    """Feature: production-readiness, Property 6: Gated dependencies become escalations.

    Any finding whose subject is owned by an open (not-closed) ``REVIEW.md``
    blocker gates to an ``Escalation_Record``: ``is_escalation`` is True and the
    entry carries the owning ``blocker_id`` (never an emitted fix).
    """
    finding = Finding(
        area=area,
        severity=severity,
        proposed_action=proposed_action,
        dedup_key=dedup_key,
        subject=subject,
        blocker_id=blocker_id,
    )

    entry = gate_finding(finding, _BLOCKERS)

    assert entry.is_escalation is True
    assert entry.blocker_id == blocker_id
    # The owning blocker really is not closed — the escalation is gate-driven.
    assert _BLOCKERS[blocker_id].status is BlockerStatus.NOT_CLOSED


@_PROPERTY_SETTINGS
@given(
    area=_AREA,
    severity=_SEVERITY,
    proposed_action=_NON_EMPTY_ACTION,
    dedup_key=st.text(),
    subject=_SUBJECT,
)
def test_property6_closed_blocker_owned_finding_is_fixable(
    area: str,
    severity: Severity,
    proposed_action: str,
    dedup_key: str,
    subject: str,
) -> None:
    """Feature: production-readiness, Property 6: Gated dependencies become escalations.

    The converse boundary: when the owning blocker's status is CLOSED, the
    subject has returned to automated scope, so the finding yields a fixable
    entry (``is_escalation`` False) that carries no ``blocker_id``.
    """
    blockers = {
        _CLOSED_BLOCKER_ID: Blocker(
            id=_CLOSED_BLOCKER_ID,
            status=BlockerStatus.CLOSED,
            status_text="Closed",
        ),
    }
    finding = Finding(
        area=area,
        severity=severity,
        proposed_action=proposed_action,
        dedup_key=dedup_key,
        subject=subject,
        blocker_id=_CLOSED_BLOCKER_ID,
    )

    entry = gate_finding(finding, blockers)

    assert entry.is_escalation is False
    assert entry.blocker_id is None
