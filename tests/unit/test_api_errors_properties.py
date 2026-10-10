"""Property-based tests for the downstream-SDK error sanitizer.

Feature: production-readiness
Property 11: Downstream SDK errors are sanitized

For any raw downstream SDK exception text, the client-facing error response
excludes the raw exception text and contains only a generic category message.
Concretely, ``sanitize_downstream_error`` is exercised against stand-in
exception classes whose ``__module__`` mimics ``azure.core.exceptions`` /
``botocore.exceptions`` / ``boto3.exceptions`` / ``psycopg2.errors`` (plus a
generic module), each carrying an arbitrary raw message that embeds
sensitive-looking fragments (hosts, ARNs, connection strings). The returned
``client_message`` must never contain the raw message text (nor any substantial
substring of it), must equal one of the fixed generic category messages, and the
outcome must always be the 5xx ``DOWNSTREAM_ERROR``.

Validates: Requirements 2.3
"""

from __future__ import annotations

import logging

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.api_errors import (
    _CLIENT_MESSAGE,
    DownstreamCategory,
    SanitizedError,
    sanitize_downstream_error,
)
from cna.api_status import Outcome, OutcomeClass, class_for

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=100)

# The only strings a client may ever see for a sanitized downstream failure.
_GENERIC_MESSAGES: frozenset[str] = frozenset(_CLIENT_MESSAGE.values())

# A logger that discards everything: the raw detail is logged server-side, but
# the property under test is about the *returned* client message, so we route
# log output to nowhere to keep the test quiet.
_NULL_LOGGER = logging.getLogger("test_api_errors_properties")
_NULL_LOGGER.addHandler(logging.NullHandler())
_NULL_LOGGER.propagate = False


# Stand-in exception classes whose ``__module__`` mimics each real SDK's
# exception module. The sanitizer classifies by module *path* (never importing
# the SDKs), so a class carrying the right ``__module__`` is indistinguishable
# from the genuine exception for classification purposes.
class _AzureError(Exception):
    __module__ = "azure.core.exceptions"


class _BotocoreError(Exception):
    __module__ = "botocore.exceptions"


class _Boto3Error(Exception):
    __module__ = "boto3.exceptions"


class _Psycopg2Error(Exception):
    __module__ = "psycopg2.errors"


class _GenericError(Exception):
    __module__ = "some.other.service"


# Each stand-in maps to the category the sanitizer must classify it into, so the
# test can assert the exact generic message that should be returned.
_EXC_CLASSES: dict[type[Exception], DownstreamCategory] = {
    _AzureError: DownstreamCategory.AZURE,
    _BotocoreError: DownstreamCategory.AWS,
    _Boto3Error: DownstreamCategory.AWS,
    _Psycopg2Error: DownstreamCategory.DATABASE,
    _GenericError: DownstreamCategory.DOWNSTREAM,
}

_EXC_CLASS = st.sampled_from(list(_EXC_CLASSES))

# Sensitive-looking fragments a raw SDK exception routinely embeds. Including
# these makes the "no raw text leaks" assertion meaningful: if any survived into
# the client message, that would be a real leak of internal detail.
_SENSITIVE_FRAGMENTS = (
    "arn:aws:iam::123456789012:role/cna-deploy",
    "https://cna-prod.privatelink.blob.core.windows.net",
    "postgresql://admin:s3cr3t@db.internal:5432/cna",
    "AccessDeniedException: user is not authorized",
    "x-amz-request-id: 7F3A2B1C9D8E",
    "10.0.4.17:5432 connection refused",
    "AKIAIOSFODNN7EXAMPLE",
    "Traceback (most recent call last):",
)

# An arbitrary raw message: free text optionally interleaved with the sensitive
# fragments above, so the generator covers both benign and leak-prone text.
_RAW_MESSAGE = st.builds(
    lambda parts: " ".join(parts),
    st.lists(
        st.one_of(
            st.text(min_size=0, max_size=40),
            st.sampled_from(_SENSITIVE_FRAGMENTS),
        ),
        min_size=1,
        max_size=6,
    ),
)


def _substantial_substrings(text: str) -> list[str]:
    """Whitespace-delimited tokens of ``text`` long enough to matter.

    A one- or two-character token (e.g. ``"at"``) can appear incidentally in a
    fixed English message, so the leak check ignores those; a token of five or
    more characters that showed up in the client message would indicate real
    raw-text passthrough.
    """
    return [token for token in text.split() if len(token) >= 5]


@_PROPERTY_SETTINGS
@given(exc_class=_EXC_CLASS, raw=_RAW_MESSAGE)
def test_property11_client_message_excludes_raw_text(exc_class: type[Exception], raw: str) -> None:
    """Feature: production-readiness, Property 11: Downstream SDK errors are sanitized.

    The returned ``client_message`` never contains the raw exception text (nor
    any substantial token of it), regardless of the SDK family or how
    sensitive the raw message looks.
    """
    result = sanitize_downstream_error(
        exc_class(raw), logger=_NULL_LOGGER, context="synthetic property check"
    )

    message = result.client_message

    # The whole raw string never appears verbatim — unless it was empty/blank
    # (nothing to leak) or is itself a fragment of one of the fixed generic
    # messages (hypothesis also draws from constants in the code under test, so
    # it produces "." and the like): that is a coincidence, not passthrough.
    if raw.strip() and not any(raw in generic for generic in _GENERIC_MESSAGES):
        assert raw not in message

    # No substantial token of the raw text survives into the client message.
    for token in _substantial_substrings(raw):
        assert token not in message, f"raw token {token!r} leaked into client message {message!r}"


@_PROPERTY_SETTINGS
@given(exc_class=_EXC_CLASS, raw=_RAW_MESSAGE)
def test_property11_client_message_is_a_fixed_generic_message(
    exc_class: type[Exception], raw: str
) -> None:
    """Feature: production-readiness, Property 11: Downstream SDK errors are sanitized.

    The client message is always exactly one of the fixed, category-level
    generic messages, and it is the one matching the classified category.
    """
    result = sanitize_downstream_error(
        exc_class(raw), logger=_NULL_LOGGER, context="synthetic property check"
    )

    assert isinstance(result, SanitizedError)
    # It is one of the known fixed messages...
    assert result.client_message in _GENERIC_MESSAGES
    # ...and specifically the one for the category the exception classified into.
    expected_category = _EXC_CLASSES[exc_class]
    assert result.category is expected_category
    assert result.client_message == _CLIENT_MESSAGE[expected_category]


@_PROPERTY_SETTINGS
@given(exc_class=_EXC_CLASS, raw=_RAW_MESSAGE)
def test_property11_outcome_is_the_5xx_downstream_error(
    exc_class: type[Exception], raw: str
) -> None:
    """Feature: production-readiness, Property 11: Downstream SDK errors are sanitized.

    Every sanitized downstream failure resolves to the ``DOWNSTREAM_ERROR``
    outcome, which is a 5xx-class (server/downstream) outcome.
    """
    result = sanitize_downstream_error(
        exc_class(raw), logger=_NULL_LOGGER, context="synthetic property check"
    )

    assert result.outcome is Outcome.DOWNSTREAM_ERROR
    assert class_for(result.outcome) is OutcomeClass.SERVER_ERROR
