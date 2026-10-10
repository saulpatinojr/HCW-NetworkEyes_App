"""Property-based tests for committed-secret finding recording.

Feature: production-readiness
Property 12: Secret findings are recorded without the value

For any detected committed secret, the recorded ``Remediation_Plan`` entry
contains the secret's location and key name and does not contain the raw secret
value. The per-location builder ``secret_location_finding`` takes only the
location and detector key-name type — it has no parameter for the secret value —
so no matter what raw secret material a scanner happened to detect at that
location, the recorded finding names the location and key name but can never
reproduce the value.

Validates: Requirements 6.2
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from cna.review.areas.security_secrets import secret_location_finding

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=200)

# Locations and detector key-name types are drawn from realistic, non-empty
# text; the raw secret value is generated independently and is NEVER passed to
# the builder — the property is that it can never appear in the finding.
_LOCATION = st.text(min_size=1).filter(lambda s: s.strip())
_KEY_NAME = st.text(min_size=1).filter(lambda s: s.strip())
# A secret value that is long/entropic enough to be an unambiguous substring:
# excludes empty/whitespace so a coincidental match cannot be trivial.
_SECRET_VALUE = st.text(min_size=8).filter(lambda s: s.strip())


@_PROPERTY_SETTINGS
@given(location=_LOCATION, key_name=_KEY_NAME, count=st.integers(min_value=1, max_value=99))
def test_property12_finding_records_location_and_key_name(
    location: str,
    key_name: str,
    count: int,
) -> None:
    """Feature: production-readiness, Property 12: Secret findings are recorded without the value.

    A finding built for a detected secret names the secret's location (subject
    and proposed_action) and its key-name type (proposed_action).
    """
    finding = secret_location_finding(location, key_name, count)

    # The location is recorded verbatim as the subject and appears in the action.
    assert finding.subject == location
    assert location in finding.proposed_action
    # The detector key-name type is recorded in the action.
    assert key_name in finding.proposed_action
    # The dedup key is keyed by location, not by any secret material.
    assert location in finding.dedup_key


@_PROPERTY_SETTINGS
@given(
    location=_LOCATION,
    key_name=_KEY_NAME,
    secret_value=_SECRET_VALUE,
    count=st.integers(min_value=1, max_value=99),
)
def test_property12_raw_secret_value_never_appears(
    location: str,
    key_name: str,
    secret_value: str,
    count: int,
) -> None:
    """Feature: production-readiness, Property 12: Secret findings are recorded without the value.

    Given an arbitrary raw secret value detected at a location, the recorded
    finding never contains that value in its subject or proposed_action. The
    builder has no value parameter, so the value cannot flow into any recorded
    field.
    """
    finding = secret_location_finding(location, key_name, count)

    # Everything in the recorded fields that is not the location or key name is
    # the builder's fixed wording. A generated value that is a substring of that
    # wording (hypothesis also draws string constants from the code under test,
    # so it finds ".secrets" and "security") is a coincidence, not the value
    # reaching the finding, and is excluded rather than asserted on.
    template = secret_location_finding("", "", count)
    assume(secret_value not in template.proposed_action)
    assume(secret_value not in template.dedup_key)

    # The raw secret value is never reproduced in any recorded text field,
    # unless it coincidentally equals the location/key name the reviewer chose
    # to record (those are recorded on purpose; the *value* qua value is not).
    if secret_value not in location and secret_value not in key_name:
        assert secret_value not in finding.subject
        assert secret_value not in finding.proposed_action
        assert secret_value not in finding.dedup_key
