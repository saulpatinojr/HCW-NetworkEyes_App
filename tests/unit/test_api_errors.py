"""Unit tests for the downstream-SDK error sanitizer (``cna.api_errors``).

Covers the Requirement 2.3 contract in the one place it is now enforced: a
caught downstream SDK exception is converted to a generic, category-level client
message that carries *no* raw exception text, while the full raw detail is
logged server-side. The exhaustive category checks here complement the
generative Property 11 test (task 4.4).
"""

from __future__ import annotations

import logging

import pytest

from cna.api_errors import (
    DownstreamCategory,
    SanitizedError,
    classify_downstream_error,
    sanitize_downstream_error,
)
from cna.api_status import Outcome, OutcomeClass, class_for

# ── Stand-in SDK exception types ──────────────────────────────────────────────
# The sanitizer detects the SDK family by the exception type's ``__module__``,
# so these stand-ins reproduce the real SDKs' module paths without importing
# boto3 / azure / psycopg2 (which may not be installed in every deployment).


class _FakeAzureError(Exception):
    __module__ = "azure.core.exceptions"


class _FakeBotocoreError(Exception):
    __module__ = "botocore.exceptions"


class _FakeBoto3Error(Exception):
    __module__ = "boto3.exceptions"


class _FakePsycopg2Error(Exception):
    __module__ = "psycopg2.errors"


_RAW = (
    "connection to server at db.internal (10.0.0.5), port 5432 failed: "
    "FATAL password authentication failed for user 'cna_admin' arn:aws:iam::123"
)


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (_FakeAzureError(_RAW), DownstreamCategory.AZURE),
        (_FakeBotocoreError(_RAW), DownstreamCategory.AWS),
        (_FakeBoto3Error(_RAW), DownstreamCategory.AWS),
        (_FakePsycopg2Error(_RAW), DownstreamCategory.DATABASE),
        (ValueError(_RAW), DownstreamCategory.DOWNSTREAM),
        (RuntimeError("boom"), DownstreamCategory.DOWNSTREAM),
    ],
)
def test_classify_maps_sdk_module_to_category(exc: BaseException, expected: DownstreamCategory):
    assert classify_downstream_error(exc) is expected


def test_classify_walks_mro_for_subclasses():
    """A subclass defined in the caller's module still resolves by its SDK root."""

    class WrappedAzureError(_FakeAzureError):
        __module__ = "apps.cna_api.main"  # defined outside the SDK namespace

    assert classify_downstream_error(WrappedAzureError(_RAW)) is DownstreamCategory.AZURE


@pytest.mark.parametrize(
    "exc",
    [
        _FakeAzureError(_RAW),
        _FakeBotocoreError(_RAW),
        _FakeBoto3Error(_RAW),
        _FakePsycopg2Error(_RAW),
        ValueError(_RAW),
    ],
)
def test_client_message_excludes_raw_exception_text(exc: BaseException):
    """Requirement 2.3 core: no fragment of the raw text reaches the client."""
    sanitized = sanitize_downstream_error(
        exc, logger=logging.getLogger("test"), context="unit test"
    )
    message = sanitized.client_message
    assert str(exc) not in message
    # No sensitive raw fragment leaks through the generic message.
    for fragment in ("10.0.0.5", "5432", "cna_admin", "arn:aws:iam", "password"):
        assert fragment not in message


def test_sanitize_returns_downstream_error_outcome():
    """A sanitized downstream failure always maps to a 5xx server outcome."""
    sanitized = sanitize_downstream_error(
        _FakeAzureError(_RAW), logger=logging.getLogger("test"), context="unit test"
    )
    assert isinstance(sanitized, SanitizedError)
    assert sanitized.outcome is Outcome.DOWNSTREAM_ERROR
    assert class_for(sanitized.outcome) is OutcomeClass.SERVER_ERROR


def test_client_message_names_the_category():
    """Each category yields a distinct, dependency-naming generic message."""
    azure = sanitize_downstream_error(
        _FakeAzureError(_RAW), logger=logging.getLogger("t"), context="c"
    )
    aws = sanitize_downstream_error(
        _FakeBotocoreError(_RAW), logger=logging.getLogger("t"), context="c"
    )
    db = sanitize_downstream_error(
        _FakePsycopg2Error(_RAW), logger=logging.getLogger("t"), context="c"
    )
    assert "Azure" in azure.client_message
    assert "AWS" in aws.client_message
    assert "database" in db.client_message
    assert azure.client_message != aws.client_message != db.client_message


def test_full_detail_is_logged_server_side(caplog: pytest.LogCaptureFixture):
    """The raw detail is recorded server-side via ``logger.exception``."""
    logger = logging.getLogger("cna-api.test")
    with caplog.at_level(logging.ERROR, logger="cna-api.test"):
        try:
            raise _FakePsycopg2Error(_RAW)
        except _FakePsycopg2Error as exc:
            sanitized = sanitize_downstream_error(
                exc, logger=logger, context="publish for engagement e-1"
            )
    # Server-side log carries the context and the full traceback/exception.
    assert any(r.levelno == logging.ERROR for r in caplog.records)
    record = next(r for r in caplog.records if r.levelno == logging.ERROR)
    assert "publish for engagement e-1" in record.getMessage()
    assert record.exc_info is not None
    # Client message still leaks nothing.
    assert "cna_admin" not in sanitized.client_message


def test_context_is_never_returned_to_client():
    """The server-side ``context`` string never appears in the client message."""
    sanitized = sanitize_downstream_error(
        _FakeAzureError(_RAW),
        logger=logging.getLogger("t"),
        context="test-connection for tenant super-secret-tenant-id",
    )
    assert "super-secret-tenant-id" not in sanitized.client_message
