"""Downstream-SDK error sanitizer for the CNA API.

Requirement 2.3 (production-readiness): when a downstream SDK returns an error
to the API, the client-facing response must exclude the *raw* SDK exception
detail. Raw ``boto3`` / ``botocore`` / ``azure-*`` / ``psycopg2`` exception text
routinely embeds internal endpoints, ARNs, connection strings, tracebacks, and
provider request IDs — none of which a caller should see, and some of which are
sensitive.

Historically each handler open-coded this: catch ``Exception``, call
``logger.exception(...)``, and ``raise HTTPException`` with a hand-written
generic string. That works but the guarantee is duplicated across handlers and
drifts silently — a new handler can forget to sanitize, or accidentally pass
``str(exc)`` through. This module makes the guarantee a single, testable
function.

:func:`sanitize_downstream_error` takes a caught downstream exception and
returns a :class:`SanitizedError`: a generic, category-level client message
(carrying no raw exception text) plus the :class:`~cna.api_status.Outcome` the
handler should map to. It logs the full raw detail server-side (with traceback)
so nothing is lost operationally. Property 11 (design) pins the invariant — for
any raw SDK exception text, the client-facing message never contains it.

The SDK family is detected by the exception type's *module path* rather than by
importing the SDKs, so the sanitizer stays importable in an Azure-only (no
``boto3``) or AWS-only deployment where the other SDK is not installed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum

from cna.api_status import Outcome

__all__ = [
    "DownstreamCategory",
    "SanitizedError",
    "sanitize_downstream_error",
]


class DownstreamCategory(Enum):
    """The downstream dependency family a caught exception belongs to.

    The category drives the generic client message: it names *which* dependency
    failed (Azure, AWS, database) without leaking *why* at the SDK-detail level.
    ``DOWNSTREAM`` is the catch-all for anything that reached a downstream call
    site but does not match a known SDK module.
    """

    AZURE = "azure"  # azure.* — Azure SDK (identity, mgmt, storage, ...)
    AWS = "aws"  # boto3 / botocore — AWS SDK
    DATABASE = "database"  # psycopg2 — PostgreSQL driver
    DOWNSTREAM = "downstream"  # any other downstream/service failure


# Generic, category-level client messages. Each is deliberately free of any raw
# exception text: it names the dependency and a next action, nothing more. These
# are the only strings a client ever sees for a sanitized downstream failure.
_CLIENT_MESSAGE: dict[DownstreamCategory, str] = {
    DownstreamCategory.AZURE: (
        "A downstream Azure service request failed. See the API logs for details."
    ),
    DownstreamCategory.AWS: (
        "A downstream AWS service request failed. See the API logs for details."
    ),
    DownstreamCategory.DATABASE: (
        "A downstream database request failed. See the API logs for details."
    ),
    DownstreamCategory.DOWNSTREAM: (
        "A downstream service request failed. See the API logs for details."
    ),
}

# Root module prefixes that identify an SDK family. Matched against the
# exception type's ``__module__`` so the SDKs need not be importable here.
_MODULE_PREFIXES: tuple[tuple[str, DownstreamCategory], ...] = (
    ("azure", DownstreamCategory.AZURE),
    ("botocore", DownstreamCategory.AWS),
    ("boto3", DownstreamCategory.AWS),
    ("psycopg2", DownstreamCategory.DATABASE),
    ("psycopg", DownstreamCategory.DATABASE),
)


@dataclass(frozen=True)
class SanitizedError:
    """The sanitized, client-safe view of a caught downstream exception.

    Attributes:
        category: The downstream family the exception was classified into.
        client_message: The generic message safe to return to the caller — it
            carries no raw SDK exception text.
        outcome: The :class:`~cna.api_status.Outcome` the handler should map to
            (always a 5xx-class server/downstream outcome).
    """

    category: DownstreamCategory
    client_message: str
    outcome: Outcome


def classify_downstream_error(exc: BaseException) -> DownstreamCategory:
    """Classify a caught ``exc`` into its :class:`DownstreamCategory`.

    Detection walks the exception type's MRO and matches each type's
    ``__module__`` against the known SDK root prefixes, so a subclass defined in
    a submodule (e.g. ``azure.core.exceptions.HttpResponseError``) is caught by
    its ``azure`` root. Anything unrecognized falls back to
    :attr:`DownstreamCategory.DOWNSTREAM`.
    """
    for klass in type(exc).__mro__:
        module = getattr(klass, "__module__", "") or ""
        root = module.split(".", 1)[0]
        for prefix, category in _MODULE_PREFIXES:
            if root == prefix:
                return category
    return DownstreamCategory.DOWNSTREAM


def sanitize_downstream_error(
    exc: BaseException,
    *,
    logger: logging.Logger,
    context: str,
) -> SanitizedError:
    """Sanitize a caught downstream SDK ``exc`` for a client-facing response.

    The full raw detail (including traceback) is logged server-side via
    ``logger.exception`` under ``context``, so operators lose nothing. The
    returned :class:`SanitizedError` carries only a generic, category-level
    message — never the raw exception text — which the caller maps into an
    :class:`~fastapi.HTTPException` using
    :func:`cna.api_status.status_for` on :attr:`SanitizedError.outcome`.

    Args:
        exc: The downstream exception that was caught.
        logger: The handler's logger; the raw detail is recorded here.
        context: A short server-side description of what was being attempted
            (e.g. ``"publish for engagement %s" % engagement_id``). It is logged
            server-side only and never returned to the client.

    Returns:
        A :class:`SanitizedError` with a client-safe message and the outcome to
        map to (always :attr:`~cna.api_status.Outcome.DOWNSTREAM_ERROR`).
    """
    category = classify_downstream_error(exc)
    # Full raw detail (message + traceback) stays server-side only.
    logger.exception("downstream %s error during %s", category.value, context)
    return SanitizedError(
        category=category,
        client_message=_CLIENT_MESSAGE[category],
        outcome=Outcome.DOWNSTREAM_ERROR,
    )
