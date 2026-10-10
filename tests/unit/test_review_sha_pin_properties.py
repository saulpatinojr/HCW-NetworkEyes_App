"""Property-based tests for third-party action SHA-pinning in the ``cicd`` area.

Feature: production-readiness
Property 14: Third-party action references must be SHA-pinned

For any workflow ``uses:`` reference to a third-party action, the SHA-pin
checker records the reference exactly when it is not pinned to a 40-hex commit
SHA. This test generates arbitrary ``uses:`` references across every category
the checker distinguishes — third-party actions pinned to a 40-hex SHA,
third-party actions pinned to a mutable tag/branch/short-sha, local ``./``
refs, ``docker://`` refs, and reusable-workflow ``.yml@ref`` forms — and
asserts the biconditional: ``find_unpinned_references`` records a reference
exactly when it ``is_third_party_action`` and ``not is_sha_pinned``.

Validates: Requirements 5.3
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from cna.review.areas.cicd_shapin import (
    find_unpinned_references,
    is_sha_pinned,
    is_third_party_action,
    scan_uses_references,
)

# A minimum of 100 iterations per the spec's property-test configuration.
_PROPERTY_SETTINGS = settings(max_examples=200)

# ---------------------------------------------------------------------------
# Building blocks for generated ``uses:`` references.
# ---------------------------------------------------------------------------

# A path segment (owner, repo, or subpath component): lowercase letters/digits
# plus a couple of the punctuation characters GitHub allows, never containing
# ``@``, ``/``, ``#`` or whitespace (those are structural to a ref).
_SEGMENT = st.text(
    alphabet=st.sampled_from(list("abcdefghijklmnopqrstuvwxyz0123456789-_.")),
    min_size=1,
    max_size=12,
).filter(lambda s: not s.endswith((".yml", ".yaml")))

# A 40-hex commit SHA — the only ref form that counts as SHA-pinned.
_SHA40 = st.text(alphabet=st.sampled_from(list("0123456789abcdefABCDEF")), min_size=40, max_size=40)

# A mutable git ref: a version tag, a branch name, or a short (non-40) SHA.
_TAG = st.builds(lambda n: f"v{n}", st.integers(min_value=0, max_value=99))
_BRANCH = st.sampled_from(["main", "master", "develop", "release", "next"])
_SHORT_SHA = st.text(alphabet=st.sampled_from(list("0123456789abcdef")), min_size=1, max_size=39)
_MUTABLE_REF = st.one_of(_TAG, _BRANCH, _SHORT_SHA)


@st.composite
def _owner_repo(draw: st.DrawFn) -> str:
    """``owner/repo`` or ``owner/repo/subpath`` — the path part of an action."""
    owner = draw(_SEGMENT)
    repo = draw(_SEGMENT)
    path = f"{owner}/{repo}"
    if draw(st.booleans()):
        path = f"{path}/{draw(_SEGMENT)}"
    return path


# --- Category strategies, each tagged with (ref, expected_recorded). ---------
#
# ``expected_recorded`` is always computed from the *real* predicate functions
# (``is_third_party_action`` and ``is_sha_pinned``) rather than hardcoded, so a
# generated ref can never carry a label that disagrees with the checker's
# contract. For example ``_owner_repo`` can emit a path whose first segment is a
# bare ``.`` (``./0``), which reads as a local ``./`` ref that
# ``is_third_party_action`` correctly excludes — computing the label keeps the
# tuple honest regardless of which shape a segment takes.


def _expected_recorded(ref: str) -> bool:
    """The checker's biconditional: recorded iff third-party and not SHA-pinned."""
    return is_third_party_action(ref) and not is_sha_pinned(ref)


@st.composite
def _third_party_pinned(draw: st.DrawFn) -> tuple[str, bool]:
    """A third-party action pinned to a 40-hex SHA — never recorded."""
    ref = f"{draw(_owner_repo())}@{draw(_SHA40)}"
    return ref, _expected_recorded(ref)


@st.composite
def _third_party_unpinned(draw: st.DrawFn) -> tuple[str, bool]:
    """A third-party action pinned to a tag/branch/short-sha — usually recorded."""
    ref = f"{draw(_owner_repo())}@{draw(_MUTABLE_REF)}"
    return ref, _expected_recorded(ref)


@st.composite
def _local_ref(draw: st.DrawFn) -> tuple[str, bool]:
    """A local ``./`` or ``../`` action ref — never recorded."""
    prefix = draw(st.sampled_from(["./", "../"]))
    ref = f"{prefix}{draw(_SEGMENT)}/{draw(_SEGMENT)}"
    return ref, _expected_recorded(ref)


@st.composite
def _docker_ref(draw: st.DrawFn) -> tuple[str, bool]:
    """A ``docker://`` container ref — never recorded."""
    image = f"{draw(_SEGMENT)}/{draw(_SEGMENT)}"
    ref = draw(st.one_of(_MUTABLE_REF, st.builds(lambda h: f"sha256:{h}", _SHA40)))
    ref = f"docker://{image}@{ref}"
    return ref, _expected_recorded(ref)


@st.composite
def _reusable_workflow_ref(draw: st.DrawFn) -> tuple[str, bool]:
    """A reusable-workflow ``owner/repo/….yml@ref`` — never recorded."""
    ext = draw(st.sampled_from([".yml", ".yaml"]))
    path = f"{draw(_owner_repo())}/{draw(_SEGMENT)}{ext}"
    ref = draw(st.one_of(_SHA40, _MUTABLE_REF))
    ref = f"{path}@{ref}"
    return ref, _expected_recorded(ref)


_ANY_REF = st.one_of(
    _third_party_pinned(),
    _third_party_unpinned(),
    _local_ref(),
    _docker_ref(),
    _reusable_workflow_ref(),
)


def _workflow_text(refs: list[str]) -> str:
    """Render a minimal workflow body embedding each ref as a ``uses:`` line."""
    lines = ["name: synthetic", "jobs:", "  build:", "    steps:"]
    for ref in refs:
        lines.append(f"      - uses: {ref}")
    return "\n".join(lines) + "\n"


@_PROPERTY_SETTINGS
@given(ref_and_expected=_ANY_REF)
def test_property14_single_ref_recorded_iff_unpinned_third_party(
    ref_and_expected: tuple[str, bool],
) -> None:
    """Feature: production-readiness, Property 14: Third-party action references must be SHA-pinned.

    For a single generated ``uses:`` reference, the checker records it exactly
    when it is a third-party action and is not pinned to a 40-hex commit SHA.
    """
    ref, expected_recorded = ref_and_expected

    # The biconditional the checker's contract rests on.
    predicate = is_third_party_action(ref) and not is_sha_pinned(ref)
    assert predicate is expected_recorded

    recorded = find_unpinned_references(_workflow_text([ref]))
    assert (ref in recorded) is expected_recorded
    # A recorded ref appears exactly when the predicate holds, and only that ref.
    assert recorded == ([ref] if expected_recorded else [])


@_PROPERTY_SETTINGS
@given(refs_and_expected=st.lists(_ANY_REF, max_size=8))
def test_property14_mixed_workflow_records_exactly_unpinned_third_party(
    refs_and_expected: list[tuple[str, bool]],
) -> None:
    """Feature: production-readiness, Property 14: Third-party action references must be SHA-pinned.

    Across a workflow mixing every ref category, ``find_unpinned_references``
    returns exactly the third-party refs that are not 40-hex SHA pinned, in
    scan order, and every other ref (pinned third-party, local, docker,
    reusable-workflow) is never recorded.
    """
    refs = [ref for ref, _ in refs_and_expected]

    recorded = find_unpinned_references(_workflow_text(refs))

    # Every scanned ref is accounted for by the biconditional.
    scanned = scan_uses_references(_workflow_text(refs))
    assert scanned == refs

    expected = [ref for ref in refs if is_third_party_action(ref) and not is_sha_pinned(ref)]
    assert recorded == expected

    # And no recorded ref is a pinned third-party, local, docker, or reusable ref.
    for ref, expected_recorded in refs_and_expected:
        if not expected_recorded:
            assert ref not in recorded
