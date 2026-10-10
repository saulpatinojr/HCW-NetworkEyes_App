"""Property-based tests for the production-readiness blocker scope gate.

Feature: production-readiness
Property 8: Blocker scope gate is consistent with closed status

For any blocker, while its status is not CLOSED no fixable action targets a
subject it owns (even when the blocker is labeled resolved), and only once its
status is CLOSED is its subject no longer forced to escalation. The gate is a
pure function of blocker status, so its classification is fully determined by
whether the owning blocker is CLOSED: a NOT_CLOSED blocker forces the finding
to an ``Escalation_Record`` (``is_escalation=True`` carrying the owning
``blocker_id``); a CLOSED blocker returns the subject to automated scope,
yielding a fixable entry (``is_escalation=False``, ``blocker_id=None``).

A ``resolved`` label alone is deliberately *not* closed (Requirement 10.3):
R-007-style "Resolved — no longer required" text classifies as NOT_CLOSED and
its subject stays forced to escalation.

Validates: Requirements 10.1, 10.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review import (
    Blocker,
    BlockerStatus,
    Finding,
    Severity,
    classify_status,
    gate_finding,
)

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

# A blocker id in the R-0NN shape.
_BLOCKER_ID = st.builds(lambda n: f"R-{n:03d}", st.integers(min_value=1, max_value=999))

_AREA = st.just("terraform-aws")
_SEVERITY = st.sampled_from(list(Severity))
_NON_EMPTY = st.text(min_size=1).filter(lambda s: s.strip())

# --- Status text strategies -------------------------------------------------
# 'resolved'-style status text: resolved but NOT closed. Every one of these
# must classify as NOT_CLOSED (Requirement 10.3).
_RESOLVED_STATUS = st.sampled_from(
    [
        "Resolved",
        "Resolved — no longer required",
        "Resolved - no longer required",
        "resolved",
        "RESOLVED",
        "Resolved (superseded)",
        "Resolved, will not fix",
        "Done — resolved",
    ]
)

# Other not-closed labels (open / not-blocking / substrings of 'closed').
_OTHER_NOT_CLOSED_STATUS = st.sampled_from(
    [
        "Open",
        "Open — not blocking",
        "OPEN",
        "In progress",
        "Pending",
        "Undisclosed pending review",  # 'closed' only as a substring
        "",
    ]
)

_NOT_CLOSED_STATUS = _RESOLVED_STATUS | _OTHER_NOT_CLOSED_STATUS

# Explicitly-closed labels: 'closed' as a standalone word.
_CLOSED_STATUS = st.sampled_from(
    [
        "Closed",
        "CLOSED",
        "Closed — done",
        "Resolved and closed",
        "closed",
    ]
)


def _finding(blocker_id: str, *, severity: Severity, subject: str) -> Finding:
    return Finding(
        area="terraform-aws",
        severity=severity,
        proposed_action="align the module with best practices",
        dedup_key=f"key::{subject}",
        subject=subject,
        blocker_id=blocker_id,
    )


@_PROPERTY_SETTINGS
@given(
    blocker_id=_BLOCKER_ID,
    status_text=_NOT_CLOSED_STATUS,
    severity=_SEVERITY,
    subject=_NON_EMPTY,
)
def test_property8_not_closed_blocker_forces_escalation(
    blocker_id: str,
    status_text: str,
    severity: Severity,
    subject: str,
) -> None:
    """Feature: production-readiness, Property 8: Blocker scope gate is consistent with closed status.

    While a blocker's status is NOT CLOSED, a finding owning that blocker is
    forced to an escalation carrying the owning blocker id — never a fixable
    action. This holds for every not-closed label, including 'resolved'.
    """
    # The status text classifies as NOT_CLOSED (Requirement 10.3).
    assert classify_status(status_text) is BlockerStatus.NOT_CLOSED

    blocker = Blocker(
        id=blocker_id,
        status=classify_status(status_text),
        status_text=status_text,
    )
    entry = gate_finding(
        _finding(blocker_id, severity=severity, subject=subject),
        {blocker_id: blocker},
    )

    # Not closed ⇒ escalation, carrying the owning blocker id. No fixable
    # action targets a subject the blocker owns.
    assert entry.is_escalation is True
    assert entry.blocker_id == blocker_id


@_PROPERTY_SETTINGS
@given(
    blocker_id=_BLOCKER_ID,
    status_text=_RESOLVED_STATUS,
    severity=_SEVERITY,
    subject=_NON_EMPTY,
)
def test_property8_resolved_label_stays_escalation(
    blocker_id: str,
    status_text: str,
    severity: Severity,
    subject: str,
) -> None:
    """Feature: production-readiness, Property 8: Blocker scope gate is consistent with closed status.

    A 'resolved'-style label alone is not closed: its subject stays out of
    automated scope and the finding remains an escalation (Requirement 10.3).
    """
    assert classify_status(status_text) is BlockerStatus.NOT_CLOSED

    blocker = Blocker(
        id=blocker_id,
        status=BlockerStatus.NOT_CLOSED,
        status_text=status_text,
    )
    entry = gate_finding(
        _finding(blocker_id, severity=severity, subject=subject),
        {blocker_id: blocker},
    )

    assert entry.is_escalation is True
    assert entry.blocker_id == blocker_id


@_PROPERTY_SETTINGS
@given(
    blocker_id=_BLOCKER_ID,
    status_text=_CLOSED_STATUS,
    severity=_SEVERITY,
    subject=_NON_EMPTY,
)
def test_property8_closed_blocker_returns_subject_to_scope(
    blocker_id: str,
    status_text: str,
    severity: Severity,
    subject: str,
) -> None:
    """Feature: production-readiness, Property 8: Blocker scope gate is consistent with closed status.

    Only once a blocker's status is CLOSED is its subject no longer forced to
    escalation: the finding becomes a fixable entry that carries no blocker id.
    """
    assert classify_status(status_text) is BlockerStatus.CLOSED

    blocker = Blocker(
        id=blocker_id,
        status=classify_status(status_text),
        status_text=status_text,
    )
    entry = gate_finding(
        _finding(blocker_id, severity=severity, subject=subject),
        {blocker_id: blocker},
    )

    # Closed ⇒ fixable, and a fixable entry never carries a blocker id.
    assert entry.is_escalation is False
    assert entry.blocker_id is None


@_PROPERTY_SETTINGS
@given(
    blocker_id=_BLOCKER_ID,
    status_text=_NOT_CLOSED_STATUS | _CLOSED_STATUS,
    severity=_SEVERITY,
    subject=_NON_EMPTY,
)
def test_property8_escalation_iff_not_closed(
    blocker_id: str,
    status_text: str,
    severity: Severity,
    subject: str,
) -> None:
    """Feature: production-readiness, Property 8: Blocker scope gate is consistent with closed status.

    The gate yields an escalation exactly when the owning blocker is NOT CLOSED
    and a fixable entry exactly when it is CLOSED — a pure function of status,
    so a status flip from not-closed to closed flips the outcome and nothing
    else does.
    """
    status = classify_status(status_text)
    blocker = Blocker(id=blocker_id, status=status, status_text=status_text)
    entry = gate_finding(
        _finding(blocker_id, severity=severity, subject=subject),
        {blocker_id: blocker},
    )

    is_closed = status is BlockerStatus.CLOSED
    assert entry.is_escalation is (not is_closed)
    assert (entry.blocker_id is None) is is_closed
