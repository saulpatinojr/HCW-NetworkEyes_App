"""Unit tests for the single outcome→HTTP-status mapping (``cna.api_status``).

Covers the Requirement 2 contract in the one place it is now enforced: a
success outcome maps to a 2xx status, a client-error outcome to a 4xx, and a
server/downstream-error outcome to a 5xx — so no handler can return a 200 on an
error path. The exhaustive per-outcome check here complements the generative
Property 10 test (task 4.2).
"""

import pytest

from cna.api_status import (
    Outcome,
    OutcomeClass,
    class_for,
    is_success,
    status_class_of,
    status_for,
)

# The expected class for each outcome, kept independent of the module's own
# table so the test genuinely pins the contract rather than echoing it.
_SUCCESS_OUTCOMES = {Outcome.SUCCESS, Outcome.ACCEPTED}
_CLIENT_ERROR_OUTCOMES = {
    Outcome.INVALID_REQUEST,
    Outcome.NOT_FOUND,
    Outcome.CONFLICT,
    Outcome.GONE,
}
_SERVER_ERROR_OUTCOMES = {
    Outcome.NOT_IMPLEMENTED,
    Outcome.DOWNSTREAM_ERROR,
    Outcome.NOT_CONFIGURED,
    Outcome.UNAVAILABLE,
    Outcome.INTERNAL_ERROR,
}


def test_every_outcome_has_a_status():
    """The mapping is total: every ``Outcome`` member resolves to a code."""
    for outcome in Outcome:
        assert isinstance(status_for(outcome), int)


def test_success_outcomes_map_to_2xx():
    for outcome in _SUCCESS_OUTCOMES:
        code = status_for(outcome)
        assert 200 <= code < 300
        assert class_for(outcome) is OutcomeClass.SUCCESS
        assert is_success(outcome)


def test_client_error_outcomes_map_to_4xx():
    for outcome in _CLIENT_ERROR_OUTCOMES:
        code = status_for(outcome)
        assert 400 <= code < 500
        assert class_for(outcome) is OutcomeClass.CLIENT_ERROR
        assert not is_success(outcome)


def test_server_error_outcomes_map_to_5xx():
    for outcome in _SERVER_ERROR_OUTCOMES:
        code = status_for(outcome)
        assert 500 <= code < 600
        assert class_for(outcome) is OutcomeClass.SERVER_ERROR
        assert not is_success(outcome)


def test_partition_is_exhaustive():
    """Success ∪ client-error ∪ server-error covers every outcome exactly once."""
    partition = _SUCCESS_OUTCOMES | _CLIENT_ERROR_OUTCOMES | _SERVER_ERROR_OUTCOMES
    assert partition == set(Outcome)
    assert len(_SUCCESS_OUTCOMES) + len(_CLIENT_ERROR_OUTCOMES) + len(
        _SERVER_ERROR_OUTCOMES
    ) == len(Outcome)


def test_no_error_outcome_maps_to_2xx():
    """Requirement 2.2/2.4 core: no failure outcome resolves to a 2xx status."""
    for outcome in _CLIENT_ERROR_OUTCOMES | _SERVER_ERROR_OUTCOMES:
        assert not (200 <= status_for(outcome) < 300)


def test_intake_not_implemented_is_an_honest_5xx():
    """`/intake` uses NOT_IMPLEMENTED — an honest 501, never a fake 2xx."""
    assert status_for(Outcome.NOT_IMPLEMENTED) == 501
    assert class_for(Outcome.NOT_IMPLEMENTED) is OutcomeClass.SERVER_ERROR


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (200, OutcomeClass.SUCCESS),
        (202, OutcomeClass.SUCCESS),
        (404, OutcomeClass.CLIENT_ERROR),
        (422, OutcomeClass.CLIENT_ERROR),
        (500, OutcomeClass.SERVER_ERROR),
        (503, OutcomeClass.SERVER_ERROR),
    ],
)
def test_status_class_of_classifies_known_codes(code: int, expected: OutcomeClass):
    assert status_class_of(code) is expected


@pytest.mark.parametrize("code", [100, 101, 301, 302])
def test_status_class_of_rejects_non_outcome_classes(code: int):
    """A 1xx/3xx code does not reflect a real success or failure outcome."""
    with pytest.raises(ValueError, match="outside the 2xx/4xx/5xx classes"):
        status_class_of(code)
