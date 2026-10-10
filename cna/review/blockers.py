"""Human-gated blocker model and the scope gate for the review.

The set of human-gated blockers (``R-0NN``) and their status is recorded in the
repository's ``REVIEW.md``. This module reads that file's status table and
turns it into the **subject → blocker → status** mapping the design's
"Blocker model" and "Consolidation, Deduplication, and Escalation" sections
describe, then exposes the *scope gate* those sections define.

Two behaviours are load-bearing:

  * **Status parsing.** ``REVIEW.md`` records a markdown status table with the
    columns ``ID | Blocker | Owner | Status``. The ``Status`` cell is free text
    (``Open``, ``Open — not blocking``, ``Resolved — no longer required``,
    ``Closed``, ...). Only an explicit *closed* status returns a subject to
    automated scope; every other label — including ``resolved`` — keeps the
    subject out of scope (Requirement 10.3). :class:`BlockerStatus` collapses
    the free text to ``CLOSED`` vs ``NOT_CLOSED`` so the gate is a pure
    function of that classification.

  * **Scope gate (Requirements 10.1–10.4).** A finding whose subject is owned by
    a blocker that is *not closed* is forced to an ``Escalation_Record``
    (:class:`~cna.review.model.PlanEntry` with ``is_escalation=True`` and a
    required ``blocker_id``); a finding whose owning blocker is *closed*, or
    that has no owning blocker, stays fixable and must not carry a
    ``blocker_id``. The gate depends only on blocker status, so re-running it
    after a status flip is consistent (design Property 8).

In the current ``REVIEW.md`` every blocker is ``Open`` except R-007, which is
``Resolved — no longer required`` — resolved but *not* closed — so R-007's
subject (Azure provider registration) stays out of automated scope until its
status becomes ``Closed``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from cna.review.model import Finding, PlanEntry, Severity

__all__ = [
    "BlockerStatus",
    "Blocker",
    "classify_status",
    "parse_blockers",
    "load_blockers",
    "gate_finding",
]


class BlockerStatus(Enum):
    """The scope-relevant classification of a blocker's free-text status.

    ``REVIEW.md`` records rich status text; the scope gate only cares about one
    distinction: is the blocker *closed* (its subject returns to automated
    scope) or *not closed* (its subject stays out of scope, forcing
    escalation)? Only an explicit closed status maps to :attr:`CLOSED`; every
    other label — ``Open``, ``Resolved``, ``Open — not blocking`` — maps to
    :attr:`NOT_CLOSED`.
    """

    CLOSED = "closed"
    NOT_CLOSED = "not_closed"

    @property
    def in_scope(self) -> bool:
        """True iff a subject owned by a blocker in this status is in scope."""
        return self is BlockerStatus.CLOSED


# A blocker id is ``R-`` followed by digits (R-001 … R-009 today).
_BLOCKER_ID = re.compile(r"R-\d{3,}")
# A status is "closed" only when the closed word stands on its own — a leading
# token or a whole word — never as a substring of another word. This matches
# "Closed", "Closed — done", "Resolved and closed" but not "disclosed" and,
# critically, not "Resolved — no longer required".
_CLOSED = re.compile(r"(?:^|\b)closed\b", re.IGNORECASE)


def classify_status(status_text: str) -> BlockerStatus:
    """Classify a blocker's free-text status as CLOSED or NOT_CLOSED.

    Only an explicit *closed* status yields :attr:`BlockerStatus.CLOSED`. A
    ``resolved`` label alone is deliberately *not* sufficient (Requirement
    10.3): R-007 is "Resolved — no longer required" and must classify as
    :attr:`BlockerStatus.NOT_CLOSED`.

    :param status_text: the raw ``Status`` cell text from ``REVIEW.md``.
    :returns: :attr:`BlockerStatus.CLOSED` iff the status names *closed*,
        otherwise :attr:`BlockerStatus.NOT_CLOSED`.
    """
    if _CLOSED.search(status_text or ""):
        return BlockerStatus.CLOSED
    return BlockerStatus.NOT_CLOSED


@dataclass(frozen=True)
class Blocker:
    """A human-gated ``REVIEW.md`` blocker and its scope-relevant status.

    :ivar id: the ``R-0NN`` identifier.
    :ivar status: the classified :class:`BlockerStatus`.
    :ivar status_text: the raw status text as written in ``REVIEW.md``.
    """

    id: str
    status: BlockerStatus
    status_text: str

    @property
    def in_scope(self) -> bool:
        """True iff this blocker's subject is in automated scope (i.e. closed)."""
        return self.status.in_scope


# The status table header row and its separator, so parsing keys off the real
# table and ignores prose that happens to contain a pipe.
_TABLE_HEADER = re.compile(
    r"^\s*\|\s*ID\s*\|\s*Blocker\s*\|\s*Owner\s*\|\s*Status\s*\|\s*$",
    re.IGNORECASE,
)
_TABLE_SEPARATOR = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _split_row(line: str) -> list[str] | None:
    """Split a markdown table row into trimmed cells, or None if not a row."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return None
    # Drop the leading/trailing pipe, then split. A trailing pipe leaves an
    # empty final cell we discard.
    inner = stripped.strip("|")
    return [cell.strip() for cell in inner.split("|")]


def parse_blockers(text: str) -> list[Blocker]:
    """Parse the ``REVIEW.md`` status table into :class:`Blocker` records.

    Reads the ``ID | Blocker | Owner | Status`` table: for each data row the
    ``R-0NN`` id is extracted from the first cell (which may wrap the id in a
    markdown link) and the status is taken from the last cell and classified.

    :param text: the full contents of ``REVIEW.md``.
    :returns: the blockers in the order they appear in the table.
    """
    lines = text.splitlines()
    blockers: list[Blocker] = []
    seen: set[str] = set()
    in_table = False

    for line in lines:
        if _TABLE_HEADER.match(line):
            in_table = True
            continue
        if not in_table:
            continue
        if _TABLE_SEPARATOR.match(line):
            continue
        cells = _split_row(line)
        if cells is None:
            # A non-row line ends the table.
            break
        if len(cells) < 4:
            continue
        id_match = _BLOCKER_ID.search(cells[0])
        if not id_match:
            continue
        blocker_id = id_match.group(0)
        if blocker_id in seen:
            continue
        status_text = cells[-1]
        blockers.append(
            Blocker(
                id=blocker_id,
                status=classify_status(status_text),
                status_text=status_text,
            )
        )
        seen.add(blocker_id)

    return blockers


def _default_review_path() -> Path:
    """Locate the repository ``REVIEW.md`` relative to this package."""
    # cna/review/blockers.py -> repo root is three parents up.
    return Path(__file__).resolve().parents[2] / "REVIEW.md"


def load_blockers(review_path: str | Path | None = None) -> dict[str, Blocker]:
    """Load the blockers from ``REVIEW.md`` keyed by id.

    :param review_path: path to ``REVIEW.md``; defaults to the repository copy
        alongside the ``cna`` package.
    :returns: a mapping of ``R-0NN`` id to :class:`Blocker`.
    :raises FileNotFoundError: if the file does not exist.
    """
    path = Path(review_path) if review_path is not None else _default_review_path()
    text = path.read_text(encoding="utf-8")
    return {b.id: b for b in parse_blockers(text)}


def gate_finding(
    finding: Finding,
    blockers: dict[str, Blocker],
) -> PlanEntry:
    """Apply the scope gate to a single finding, yielding one plan entry.

    The classification is a pure function of the finding's blocker ownership and
    that blocker's status:

      * **No owning blocker** → a fixable :class:`~cna.review.model.PlanEntry`
        (``is_escalation=False``, no ``blocker_id``).
      * **Owning blocker is not closed** (open, or resolved-but-not-closed like
        R-007) → an ``Escalation_Record`` carrying the owning ``blocker_id``
        (Requirements 10.1, 10.2, 10.4). The subject stays out of automated
        scope.
      * **Owning blocker is closed** → the subject has returned to automated
        scope, so the finding is treated as fixable (Requirement 10.3). A
        ``blocker_id`` on a fixable finding is dropped rather than carried, so
        the resulting fixable entry never carries a blocker id.

    :param finding: the raw finding to classify.
    :param blockers: the ``R-0NN`` → :class:`Blocker` mapping (from
        :func:`load_blockers`).
    :returns: a :class:`~cna.review.model.PlanEntry` for this finding.
    :raises KeyError: if the finding names a ``blocker_id`` absent from
        ``blockers`` — an escalation must reference a real ``REVIEW.md`` blocker.
    """
    severity = Severity(finding.severity)
    referenced_areas = {finding.area}
    subjects = {finding.subject}

    blocker_id = finding.blocker_id
    if blocker_id is None:
        return PlanEntry(
            dedup_key=finding.dedup_key,
            severity=severity,
            proposed_action=finding.proposed_action,
            referenced_areas=referenced_areas,
            subjects=subjects,
            is_escalation=False,
            blocker_id=None,
        )

    if blocker_id not in blockers:
        raise KeyError(
            f"finding references unknown blocker {blocker_id!r}; "
            "an escalation must map to a REVIEW.md blocker"
        )

    if blockers[blocker_id].in_scope:
        # The owning blocker is CLOSED: the subject is back in automated scope,
        # so this is a fixable entry and must not carry a blocker id.
        return PlanEntry(
            dedup_key=finding.dedup_key,
            severity=severity,
            proposed_action=finding.proposed_action,
            referenced_areas=referenced_areas,
            subjects=subjects,
            is_escalation=False,
            blocker_id=None,
        )

    # The owning blocker is not closed: force escalation with the blocker id.
    return PlanEntry(
        dedup_key=finding.dedup_key,
        severity=severity,
        proposed_action=finding.proposed_action,
        referenced_areas=referenced_areas,
        subjects=subjects,
        is_escalation=True,
        blocker_id=blocker_id,
    )
