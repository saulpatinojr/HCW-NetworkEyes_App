"""Single outcome→HTTP-status mapping for the CNA API.

Requirement 2 (production-readiness) requires that every API response reflect
the *actual* result of the operation: a successful outcome returns a 2xx
status, and a failed outcome returns the 4xx or 5xx status whose class matches
the failure category (client error → 4xx, server or downstream error → 5xx).
No handler may return a 200 on an error path.

Historically each handler hard-coded its own status literals, so the guarantee
lived only in reviewers' heads. This module makes it a single, testable
function: an :class:`Outcome` names a domain outcome category, and
:func:`status_for` maps it to the one HTTP status code that carries the
matching class. Property 10 (design) pins the invariant — the mapping is a pure
function whose class placement (2xx / 4xx / 5xx) matches the outcome category.

FastAPI handlers select an :class:`Outcome` and pass :func:`status_for` to the
response (or ``HTTPException``) rather than repeating raw integers, so the
success→2xx / failure→matching-4xx-or-5xx contract cannot silently drift.
"""

from __future__ import annotations

from enum import Enum


class OutcomeClass(Enum):
    """The HTTP status *class* an outcome belongs to.

    The value is the leading digit of the status code (2, 4, or 5), which keeps
    the "class matches category" check a plain integer comparison.
    """

    SUCCESS = 2  # 2xx — the operation completed successfully
    CLIENT_ERROR = 4  # 4xx — the caller's request was at fault
    SERVER_ERROR = 5  # 5xx — the server or a downstream dependency failed


class Outcome(Enum):
    """A domain outcome category, independent of any single handler.

    Each member names *why* a request ended the way it did; :data:`_STATUS`
    maps each to the one HTTP status code that expresses it. Members are grouped
    by class so the mapping is auditable at a glance.
    """

    # ── Success (2xx) ─────────────────────────────────────────────────────────
    SUCCESS = "success"  # 200 — completed, body returned
    ACCEPTED = "accepted"  # 202 — accepted for background processing

    # ── Client error (4xx) ────────────────────────────────────────────────────
    INVALID_REQUEST = "invalid_request"  # 422 — request failed validation
    NOT_FOUND = "not_found"  # 404 — the addressed resource does not exist
    CONFLICT = "conflict"  # 409 — state precondition not met
    GONE = "gone"  # 410 — the resource existed but has expired

    # ── Server / downstream error (5xx) ───────────────────────────────────────
    NOT_IMPLEMENTED = "not_implemented"  # 501 — the phase is not wired up yet
    DOWNSTREAM_ERROR = "downstream_error"  # 502 — a downstream SDK/service failed
    NOT_CONFIGURED = "not_configured"  # 503 — a required dependency is unconfigured
    UNAVAILABLE = "unavailable"  # 503 — a dependency is configured but momentarily saturated
    INTERNAL_ERROR = "internal_error"  # 500 — an unexpected server-side failure


_STATUS: dict[Outcome, int] = {
    Outcome.SUCCESS: 200,
    Outcome.ACCEPTED: 202,
    Outcome.INVALID_REQUEST: 422,
    Outcome.NOT_FOUND: 404,
    Outcome.CONFLICT: 409,
    Outcome.GONE: 410,
    Outcome.NOT_IMPLEMENTED: 501,
    Outcome.DOWNSTREAM_ERROR: 502,
    Outcome.NOT_CONFIGURED: 503,
    Outcome.UNAVAILABLE: 503,
    Outcome.INTERNAL_ERROR: 500,
}


def status_for(outcome: Outcome) -> int:
    """Return the single HTTP status code for a domain ``outcome``.

    The returned code always falls in the class implied by the outcome:
    successes yield a 2xx, client errors a 4xx, and server/downstream errors a
    5xx. This is the one place a status code is chosen for an outcome, so the
    Requirement 2 contract is enforced in exactly one function.
    """
    return _STATUS[outcome]


def status_class_of(status_code: int) -> OutcomeClass:
    """Classify a raw HTTP ``status_code`` into its :class:`OutcomeClass`.

    Raises :class:`ValueError` for a code outside the 2xx/4xx/5xx classes this
    API produces, so an accidental 1xx/3xx (which would not reflect a real
    success or failure outcome) is caught rather than silently accepted.
    """
    leading = status_code // 100
    try:
        return OutcomeClass(leading)
    except ValueError:
        raise ValueError(f"status code {status_code} is outside the 2xx/4xx/5xx classes") from None


def class_for(outcome: Outcome) -> OutcomeClass:
    """Return the :class:`OutcomeClass` an ``outcome`` maps to."""
    return status_class_of(status_for(outcome))


def is_success(outcome: Outcome) -> bool:
    """True iff ``outcome`` maps to a 2xx status."""
    return class_for(outcome) is OutcomeClass.SUCCESS
