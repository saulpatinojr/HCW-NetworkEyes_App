"""Unit tests for the production-readiness blocker model and scope gate.

Example and edge-case coverage for :mod:`cna.review.blockers` — parsing the
``REVIEW.md`` status table, the CLOSED-vs-not-closed status classification
(Requirement 10.3, where a ``resolved`` label alone is *not* closed), and the
scope gate that turns a not-closed blocker's finding into an ``Escalation_Record``
while a closed blocker's finding stays fixable (Requirements 10.1, 10.2, 10.4).

The universal invariants for gated escalation and scope-gate consistency are
covered separately by the property tests (tasks 2.3/2.4).
"""

from pathlib import Path

import pytest

from cna.review import (
    Blocker,
    BlockerStatus,
    Finding,
    Severity,
    classify_status,
    gate_finding,
    load_blockers,
    parse_blockers,
)

_REVIEW_MD = Path(__file__).resolve().parents[2] / "REVIEW.md"

_SAMPLE_TABLE = """\
# Review

Some prose | with a pipe that is not a table row.

| ID | Blocker | Owner | Status |
|---|---|---|---|
| [R-001](#r-001) | AWS account | AWS account owner | Open |
| [R-007](#r-007) | Azure provider registration | Azure owner | Resolved — no longer required |
| [R-010](#r-010) | A finished thing | Someone | Closed |
| [R-009](#r-009) | Wiki access | Repo owner | Open — not blocking |

## R-001 — AWS account
Prose after the table with a | pipe.
"""


# ---- classify_status -------------------------------------------------------


def test_open_status_is_not_closed():
    assert classify_status("Open") is BlockerStatus.NOT_CLOSED


def test_open_not_blocking_is_not_closed():
    assert classify_status("Open — not blocking") is BlockerStatus.NOT_CLOSED


def test_resolved_label_alone_is_not_closed():
    # Requirement 10.3: a resolved label is NOT sufficient to return to scope.
    assert classify_status("Resolved — no longer required") is BlockerStatus.NOT_CLOSED


def test_closed_status_is_closed():
    assert classify_status("Closed") is BlockerStatus.CLOSED


def test_closed_is_case_insensitive_and_matches_whole_word():
    assert classify_status("CLOSED") is BlockerStatus.CLOSED
    assert classify_status("Resolved and closed") is BlockerStatus.CLOSED


def test_disclosed_is_not_treated_as_closed():
    # 'closed' as a substring of another word must not count.
    assert classify_status("Undisclosed pending review") is BlockerStatus.NOT_CLOSED


def test_empty_status_is_not_closed():
    assert classify_status("") is BlockerStatus.NOT_CLOSED


def test_in_scope_reflects_closed_status():
    assert BlockerStatus.CLOSED.in_scope is True
    assert BlockerStatus.NOT_CLOSED.in_scope is False


# ---- parse_blockers --------------------------------------------------------


def test_parse_extracts_ids_and_statuses_in_order():
    blockers = parse_blockers(_SAMPLE_TABLE)
    assert [b.id for b in blockers] == ["R-001", "R-007", "R-010", "R-009"]


def test_parse_classifies_status_per_row():
    by_id = {b.id: b for b in parse_blockers(_SAMPLE_TABLE)}
    assert by_id["R-001"].status is BlockerStatus.NOT_CLOSED
    assert by_id["R-007"].status is BlockerStatus.NOT_CLOSED  # resolved, not closed
    assert by_id["R-010"].status is BlockerStatus.CLOSED
    assert by_id["R-009"].status is BlockerStatus.NOT_CLOSED


def test_parse_preserves_raw_status_text():
    by_id = {b.id: b for b in parse_blockers(_SAMPLE_TABLE)}
    assert by_id["R-007"].status_text == "Resolved — no longer required"


def test_parse_ignores_prose_pipes_outside_the_table():
    # Only the four table rows are parsed, not the prose lines with pipes.
    assert len(parse_blockers(_SAMPLE_TABLE)) == 4


def test_parse_empty_text_yields_no_blockers():
    assert parse_blockers("") == []


def test_blocker_in_scope_only_when_closed():
    closed = Blocker(id="R-010", status=BlockerStatus.CLOSED, status_text="Closed")
    openb = Blocker(id="R-001", status=BlockerStatus.NOT_CLOSED, status_text="Open")
    assert closed.in_scope is True
    assert openb.in_scope is False


# ---- load_blockers against the real REVIEW.md ------------------------------


def test_load_blockers_reads_all_review_md_blockers():
    # REVIEW.md grows over time; assert the parser reads the known blockers
    # rather than pinning an exact count. R-001..R-009 are the original set and
    # R-010 was added later — the loaded set must be a superset of all of them.
    blockers = load_blockers()
    known = {f"R-00{n}" for n in range(1, 10)} | {"R-010"}
    assert known <= set(blockers)


def test_load_blockers_r007_resolved_but_not_closed():
    # The load-bearing case: R-007 is resolved but NOT closed, so out of scope.
    blockers = load_blockers()
    assert blockers["R-007"].status is BlockerStatus.NOT_CLOSED
    assert blockers["R-007"].in_scope is False


def test_load_blockers_all_others_open():
    blockers = load_blockers()
    # Every known blocker except R-007 (resolved-but-not-closed) is Open;
    # R-010 (dev-environment out-of-band deletion protection) is Open too.
    for bid in (
        "R-001",
        "R-002",
        "R-003",
        "R-004",
        "R-005",
        "R-006",
        "R-008",
        "R-009",
        "R-010",
    ):
        assert blockers[bid].status is BlockerStatus.NOT_CLOSED, bid


def test_load_blockers_accepts_explicit_path():
    blockers = load_blockers(_REVIEW_MD)
    assert "R-001" in blockers


def test_load_blockers_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        load_blockers(Path("does-not-exist-REVIEW.md"))


# ---- gate_finding ----------------------------------------------------------


def _finding(*, blocker_id: str | None, area: str = "terraform-aws") -> Finding:
    return Finding(
        area=area,
        severity=Severity.HIGH,
        proposed_action="do a thing",
        dedup_key="k",
        subject="environments/aws/prod",
        blocker_id=blocker_id,
    )


def test_gate_no_blocker_is_fixable():
    blockers = load_blockers()
    entry = gate_finding(_finding(blocker_id=None), blockers)
    assert entry.is_escalation is False
    assert entry.blocker_id is None


def test_gate_open_blocker_forces_escalation_with_blocker_id():
    blockers = load_blockers()
    entry = gate_finding(_finding(blocker_id="R-001"), blockers)
    assert entry.is_escalation is True
    assert entry.blocker_id == "R-001"


def test_gate_resolved_but_not_closed_blocker_still_escalates():
    # R-007 is resolved, not closed → its subject stays out of scope.
    blockers = load_blockers()
    entry = gate_finding(_finding(blocker_id="R-007"), blockers)
    assert entry.is_escalation is True
    assert entry.blocker_id == "R-007"


def test_gate_closed_blocker_returns_subject_to_scope():
    # A closed blocker returns its subject to automated scope: fixable, no id.
    blockers = {
        "R-010": Blocker(id="R-010", status=BlockerStatus.CLOSED, status_text="Closed"),
    }
    entry = gate_finding(_finding(blocker_id="R-010"), blockers)
    assert entry.is_escalation is False
    assert entry.blocker_id is None


def test_gate_preserves_area_subject_and_severity():
    blockers = load_blockers()
    entry = gate_finding(_finding(blocker_id="R-001"), blockers)
    assert entry.referenced_areas == {"terraform-aws"}
    assert entry.subjects == {"environments/aws/prod"}
    assert entry.severity is Severity.HIGH
    assert entry.dedup_key == "k"


def test_gate_unknown_blocker_raises():
    blockers = load_blockers()
    with pytest.raises(KeyError, match="unknown blocker"):
        gate_finding(_finding(blocker_id="R-999"), blockers)


def test_gate_output_is_a_wellformed_plan_entry():
    # A fixable finding never carries a blocker id, an escalation always does —
    # the PlanEntry invariants hold on the gate's output.
    blockers = load_blockers()
    fixable = gate_finding(_finding(blocker_id=None), blockers)
    escalation = gate_finding(_finding(blocker_id="R-002"), blockers)
    assert fixable.blocker_id is None and fixable.is_escalation is False
    assert escalation.blocker_id == "R-002" and escalation.is_escalation is True
