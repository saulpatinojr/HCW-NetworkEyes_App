"""Property-based tests for the production-readiness review data model.

Feature: production-readiness
Property 1: Finding records are well-formed

For any ``Finding`` produced by any area reviewer, the record has a valid
severity, an ``area`` drawn only from the nine fixed owner areas, and a
non-empty ``proposed_action``. Well-formedness is enforced at construction
time, so a well-formed input always yields a well-formed record and any
ill-formed input (bad severity, area outside ``AREAS``, empty/whitespace
``proposed_action``) always raises ``ValueError``.

Validates: Requirements 1.2
"""

from __future__ import annotations

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from cna.review import AREAS, Finding, Severity

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(
    max_examples=100,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

_AREA = st.sampled_from(sorted(AREAS))
_SEVERITY = st.sampled_from(list(Severity))
# Non-empty once stripped: rejects "" and pure-whitespace actions.
_NON_EMPTY_ACTION = st.text(min_size=1).filter(lambda s: s.strip())
_TEXT = st.text()


@_PROPERTY_SETTINGS
@given(
    area=_AREA,
    severity=_SEVERITY,
    proposed_action=_NON_EMPTY_ACTION,
    dedup_key=_TEXT,
    subject=_TEXT,
    blocker_id=st.none() | st.text(),
)
def test_property1_valid_inputs_yield_well_formed_finding(
    area: str,
    severity: Severity,
    proposed_action: str,
    dedup_key: str,
    subject: str,
    blocker_id: str | None,
) -> None:
    """Feature: production-readiness, Property 1: Finding records are well-formed.

    Any valid combination of inputs constructs a well-formed ``Finding``: the
    severity is a ``Severity`` member, the area is drawn from ``AREAS``, and the
    ``proposed_action`` is non-empty after stripping.
    """
    finding = Finding(
        area=area,
        severity=severity,
        proposed_action=proposed_action,
        dedup_key=dedup_key,
        subject=subject,
        blocker_id=blocker_id,
    )

    assert isinstance(finding.severity, Severity)
    assert finding.area in AREAS
    assert finding.proposed_action.strip()
    assert finding.blocker_id == blocker_id


@_PROPERTY_SETTINGS
@given(
    # Any severity value that is not a valid Severity member: exclude the ints
    # that map to a member (0..4) and the members themselves.
    bad_severity=(
        st.integers().filter(lambda i: i not in {int(s) for s in Severity})
        | st.text()
        | st.none()
        | st.floats(allow_nan=False, allow_infinity=False).filter(
            lambda f: f not in {float(s) for s in Severity}
        )
    ),
    proposed_action=_NON_EMPTY_ACTION,
)
def test_property1_invalid_severity_always_raises(
    bad_severity: object,
    proposed_action: str,
) -> None:
    """Feature: production-readiness, Property 1: Finding records are well-formed.

    A severity that is not a ``Severity`` member (or a bare int mapping to one)
    always raises ``ValueError``.
    """
    with pytest.raises(ValueError):
        Finding(
            area="python-engine-api",
            severity=bad_severity,  # type: ignore[arg-type]
            proposed_action=proposed_action,
            dedup_key="k",
            subject="s",
        )


@_PROPERTY_SETTINGS
@given(
    bad_area=st.text().filter(lambda s: s not in AREAS),
    severity=_SEVERITY,
    proposed_action=_NON_EMPTY_ACTION,
)
def test_property1_area_outside_closed_set_always_raises(
    bad_area: str,
    severity: Severity,
    proposed_action: str,
) -> None:
    """Feature: production-readiness, Property 1: Finding records are well-formed.

    Any area not drawn from the nine fixed owner areas always raises
    ``ValueError``.
    """
    with pytest.raises(ValueError, match="area must be one of"):
        Finding(
            area=bad_area,
            severity=severity,
            proposed_action=proposed_action,
            dedup_key="k",
            subject="s",
        )


@_PROPERTY_SETTINGS
@given(
    area=_AREA,
    severity=_SEVERITY,
    # Empty or whitespace-only: nothing survives strip().
    empty_action=st.text(alphabet=" \t\r\n\f\v").filter(lambda s: not s.strip()),
)
def test_property1_empty_proposed_action_always_raises(
    area: str,
    severity: Severity,
    empty_action: str,
) -> None:
    """Feature: production-readiness, Property 1: Finding records are well-formed.

    An empty or whitespace-only ``proposed_action`` always raises
    ``ValueError``.
    """
    with pytest.raises(ValueError, match="proposed_action"):
        Finding(
            area=area,
            severity=severity,
            proposed_action=empty_action,
            dedup_key="k",
            subject="s",
        )
