"""Property-based tests for the single outcome→HTTP-status mapping.

Feature: production-readiness
Property 10: Request outcomes map to the correct HTTP status class

For any API request outcome, a successful outcome maps to a 2xx status and a
failed outcome maps to a 4xx or 5xx status whose class matches the failure
category (client error → 4xx, server or downstream error → 5xx). The generative
sweep across every ``Outcome`` member complements the exhaustive per-outcome
example checks in ``test_api_status.py``.

Validates: Requirements 2.2, 2.4
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.api_status import (
    Outcome,
    OutcomeClass,
    class_for,
    is_success,
    status_for,
)

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

# Sample across the whole Outcome enum so the mapping is exercised uniformly.
_OUTCOME = st.sampled_from(list(Outcome))

# The hundreds band each OutcomeClass must land in.
_BANDS: dict[OutcomeClass, tuple[int, int]] = {
    OutcomeClass.SUCCESS: (200, 300),
    OutcomeClass.CLIENT_ERROR: (400, 500),
    OutcomeClass.SERVER_ERROR: (500, 600),
}


@_PROPERTY_SETTINGS
@given(outcome=_OUTCOME)
def test_property10_status_falls_in_the_classified_band(outcome: Outcome) -> None:
    """Feature: production-readiness, Property 10: Request outcomes map to the correct HTTP status class.

    The module classifies each outcome via ``class_for``; the actual code from
    ``status_for`` must fall in that class's hundreds band. This ties the
    declared class to the real integer the API would emit.
    """
    expected_class = class_for(outcome)
    code = status_for(outcome)

    low, high = _BANDS[expected_class]
    assert low <= code < high, (
        f"{outcome.name} classified {expected_class.name} but status {code} "
        f"is outside [{low}, {high})"
    )
    # The leading digit is exactly the class's numeric value (2 / 4 / 5).
    assert code // 100 == expected_class.value


@_PROPERTY_SETTINGS
@given(outcome=_OUTCOME)
def test_property10_success_iff_2xx(outcome: Outcome) -> None:
    """Feature: production-readiness, Property 10: Request outcomes map to the correct HTTP status class.

    A successful outcome maps to a 2xx status and, conversely, a 2xx status only
    ever comes from a success outcome — so ``is_success`` and the 2xx band agree.
    """
    code = status_for(outcome)
    in_2xx = 200 <= code < 300
    assert is_success(outcome) == in_2xx
    assert (class_for(outcome) is OutcomeClass.SUCCESS) == in_2xx


@_PROPERTY_SETTINGS
@given(outcome=_OUTCOME)
def test_property10_no_error_outcome_maps_to_2xx(outcome: Outcome) -> None:
    """Feature: production-readiness, Property 10: Request outcomes map to the correct HTTP status class.

    Requirement 2.2/2.4 core: any outcome the module does not classify as a
    success (i.e. every error outcome) resolves to a 4xx or 5xx, never a 2xx.
    """
    code = status_for(outcome)
    if class_for(outcome) is not OutcomeClass.SUCCESS:
        assert not (200 <= code < 300)
        assert 400 <= code < 600
