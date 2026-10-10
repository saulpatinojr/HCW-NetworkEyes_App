"""Property-based tests for the containers-packaging non-root check.

Feature: production-readiness
Property 15: Root-running images are flagged for non-root

For any service Dockerfile whose effective final ``USER`` is root or unset, the
review records a ``Remediation_Plan`` entry to run the process as a non-root
user, and does not record one when the final ``USER`` is a non-root user.

The check is a pure function of the Dockerfile's *effective* final ``USER``:
:func:`effective_final_user` resolves the last ``USER`` instruction (with
``ARG``/``ENV`` substitution and ``name:group`` handling), and
:func:`record_root_user_finding` records a HIGH non-root remediation finding
exactly when that user is root (``root``/``0``) or unset, and records nothing
otherwise.

Validates: Requirements 7.4
"""

from __future__ import annotations

from hypothesis import assume, given, settings
from hypothesis import strategies as st

from cna.review.areas.containers_packaging import (
    effective_final_user,
    is_root_user,
    record_root_user_finding,
)
from cna.review.model import Severity

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=200)

# Tokens that resolve to the root account (case-insensitive for the name).
_ROOT_TOKENS = st.sampled_from(["root", "ROOT", "Root", "0"])

# A non-root user name: an identifier that is not "root" and not purely a
# root-equivalent uid. Constrained to a realistic Dockerfile USER token.
_NON_ROOT_NAME = st.from_regex(r"[a-z][a-z0-9_-]{0,15}", fullmatch=True).filter(
    lambda s: s.lower() != "root"
)

# A non-root uid: any positive integer (uid 0 is root).
_NON_ROOT_UID = st.integers(min_value=1, max_value=65535).map(str)

_NON_ROOT_TOKENS = _NON_ROOT_NAME | _NON_ROOT_UID

# A group token to exercise the ``name:group`` / ``uid:gid`` forms.
_GROUP_TOKEN = st.from_regex(r"[a-z][a-z0-9_-]{0,10}", fullmatch=True) | st.integers(
    min_value=0, max_value=65535
).map(str)

_SUBJECT = st.sampled_from(
    [
        "Dockerfile",
        "apps/cna-api/Dockerfile",
        "apps/cna-web/Dockerfile",
        "apps/cna-worker/Dockerfile",
    ]
)

# Preamble lines that never set a final USER, sprinkled between instructions.
_NOISE_LINE = st.sampled_from(
    [
        "FROM python:3.12-slim AS base",
        "RUN apt-get update && apt-get install -y curl",
        "WORKDIR /app",
        "COPY . .",
        "EXPOSE 8000",
        "# a comment",
        "",
        'HEALTHCHECK CMD ["curl", "-f", "http://localhost/health"]',
    ]
)


class _RecordingSink:
    """A sink that captures the findings handed to it."""

    def __init__(self) -> None:
        self.findings: list = []

    def __call__(self, finding) -> None:
        self.findings.append(finding)


def _assemble(lines: list[str], user_line: str | None) -> str:
    """Build Dockerfile text from noise ``lines`` plus an optional USER line."""
    body = list(lines)
    if user_line is not None:
        body.append(user_line)
    return "\n".join(body)


# --- Root / unset final USER is flagged ------------------------------------


@_PROPERTY_SETTINGS
@given(
    subject=_SUBJECT,
    noise=st.lists(_NOISE_LINE, max_size=6),
    root_token=_ROOT_TOKENS,
    with_group=st.booleans(),
    group=_GROUP_TOKEN,
)
def test_property15_root_final_user_is_flagged(
    subject: str,
    noise: list[str],
    root_token: str,
    with_group: bool,
    group: str,
) -> None:
    """Feature: production-readiness, Property 15: Root-running images are flagged for non-root.

    A Dockerfile whose effective final ``USER`` is root (``root``/``0``, in any
    of the ``name`` / ``name:group`` forms) records exactly one HIGH non-root
    remediation finding.
    """
    spec = f"{root_token}:{group}" if with_group else root_token
    text = _assemble(noise, f"USER {spec}")

    user = effective_final_user(text)
    assert is_root_user(user) is True

    sink = _RecordingSink()
    finding = record_root_user_finding(subject, user, sink)

    assert finding is not None
    assert sink.findings == [finding]
    assert finding.severity is Severity.HIGH
    assert finding.subject == subject
    assert "non-root" in finding.proposed_action.lower()


@_PROPERTY_SETTINGS
@given(subject=_SUBJECT, noise=st.lists(_NOISE_LINE, max_size=6))
def test_property15_unset_final_user_is_flagged(
    subject: str,
    noise: list[str],
) -> None:
    """Feature: production-readiness, Property 15: Root-running images are flagged for non-root.

    A Dockerfile with no ``USER`` instruction runs as root by default and is
    flagged with a HIGH non-root remediation finding.
    """
    text = _assemble(noise, user_line=None)

    user = effective_final_user(text)
    assert user is None
    assert is_root_user(user) is True

    sink = _RecordingSink()
    finding = record_root_user_finding(subject, user, sink)

    assert finding is not None
    assert sink.findings == [finding]
    assert finding.severity is Severity.HIGH
    assert "non-root" in finding.proposed_action.lower()


# --- Non-root final USER records nothing -----------------------------------


@_PROPERTY_SETTINGS
@given(
    subject=_SUBJECT,
    noise=st.lists(_NOISE_LINE, max_size=6),
    user_token=_NON_ROOT_TOKENS,
    with_group=st.booleans(),
    group=_GROUP_TOKEN,
)
def test_property15_non_root_final_user_records_nothing(
    subject: str,
    noise: list[str],
    user_token: str,
    with_group: bool,
    group: str,
) -> None:
    """Feature: production-readiness, Property 15: Root-running images are flagged for non-root.

    A Dockerfile ending on a non-root ``USER`` (name or uid, with or without a
    group) records no root-user finding — Property 15's negative case.
    """
    spec = f"{user_token}:{group}" if with_group else user_token
    text = _assemble(noise, f"USER {spec}")

    user = effective_final_user(text)
    assert is_root_user(user) is False

    sink = _RecordingSink()
    finding = record_root_user_finding(subject, user, sink)

    assert finding is None
    assert sink.findings == []


# --- Last USER wins; ARG/ENV substitution ----------------------------------


@_PROPERTY_SETTINGS
@given(
    subject=_SUBJECT,
    noise=st.lists(_NOISE_LINE, max_size=4),
    earlier_root=st.booleans(),
    final_token=_ROOT_TOKENS | _NON_ROOT_TOKENS,
)
def test_property15_last_user_wins(
    subject: str,
    noise: list[str],
    earlier_root: bool,
    final_token: str,
) -> None:
    """Feature: production-readiness, Property 15: Root-running images are flagged for non-root.

    An earlier ``USER`` never decides the outcome: only the final ``USER``
    determines whether the image is flagged, regardless of what came before.
    """
    earlier = "root" if earlier_root else "appuser"
    lines = [f"USER {earlier}", *noise]
    text = _assemble(lines, f"USER {final_token}")

    user = effective_final_user(text)
    sink = _RecordingSink()
    finding = record_root_user_finding(subject, user, sink)

    flagged = is_root_user(user)
    assert (finding is not None) is flagged
    assert (len(sink.findings) == 1) is flagged


@_PROPERTY_SETTINGS
@given(
    subject=_SUBJECT,
    var_name=st.from_regex(r"[A-Z][A-Z0-9_]{0,10}", fullmatch=True),
    source=st.sampled_from(["ARG", "ENV"]),
    is_root=st.booleans(),
    non_root=_NON_ROOT_NAME,
    ref_braces=st.booleans(),
)
def test_property15_arg_env_substitution(
    subject: str,
    var_name: str,
    source: str,
    is_root: bool,
    non_root: str,
    ref_braces: bool,
) -> None:
    """Feature: production-readiness, Property 15: Root-running images are flagged for non-root.

    A parameterised ``USER ${VAR}`` reference is resolved from an ``ARG`` or
    ``ENV`` default so the image is flagged based on the substituted value, not
    mis-flagged as an unresolved reference.
    """
    value = "root" if is_root else non_root
    assume(value.lower() != "root" or is_root)  # keep non-root truly non-root

    if source == "ARG":
        define = f"ARG {var_name}={value}"
    else:
        define = f"ENV {var_name}={value}"

    ref = f"${{{var_name}}}" if ref_braces else f"${var_name}"
    text = _assemble([define, "WORKDIR /app"], f"USER {ref}")

    user = effective_final_user(text)
    # The reference resolved to the defined value (root-ness follows the value).
    assert is_root_user(user) is is_root

    sink = _RecordingSink()
    finding = record_root_user_finding(subject, user, sink)
    assert (finding is not None) is is_root


# --- The invariant, stated directly ----------------------------------------


@_PROPERTY_SETTINGS
@given(
    subject=_SUBJECT,
    noise=st.lists(_NOISE_LINE, max_size=6),
    token=st.none() | _ROOT_TOKENS | _NON_ROOT_TOKENS,
)
def test_property15_records_iff_root_or_unset(
    subject: str,
    noise: list[str],
    token: str | None,
) -> None:
    """Feature: production-readiness, Property 15: Root-running images are flagged for non-root.

    Records a root-user finding exactly when the effective final ``USER`` is
    root or unset, and records nothing otherwise — the biconditional Property 15
    asserts.
    """
    user_line = None if token is None else f"USER {token}"
    text = _assemble(noise, user_line)

    user = effective_final_user(text)
    sink = _RecordingSink()
    finding = record_root_user_finding(subject, user, sink)

    should_flag = is_root_user(user)
    assert (finding is not None) is should_flag
    assert (len(sink.findings) == 1) is should_flag
    if finding is not None:
        assert finding.severity is Severity.HIGH
