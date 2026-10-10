"""Consolidation engine for the production-hardening review.

Every area reviewer emits raw :class:`~cna.review.model.Finding` records; this
module collapses them into the single, ordered
:class:`~cna.review.model.RemediationPlan` described in the spec design
("Consolidation, Deduplication, and Escalation").

Three behaviours are load-bearing:

  * **Deduplication (Requirement 1.5).** Findings sharing a ``dedup_key``
    describe one underlying defect and collapse into exactly one
    :class:`~cna.review.model.PlanEntry`. The entry's ``referenced_areas`` is
    the union of the contributing areas, its ``subjects`` the union of their
    subjects, and its ``severity`` the maximum among them.
  * **Ordering (Requirement 1.4).** Entries are sorted by ``severity``
    descending into the plan.
  * **Escalation classification (Requirement 1.6).** An entry is an
    ``Escalation_Record`` iff a contributing finding is blocker-owned (carries a
    ``blocker_id``). Escalation entries carry that ``blocker_id``; fixable
    entries carry none.

**Recording as the gate (Requirement 1.3).** A finding is only "in the plan"
once it has been consolidated: :func:`consolidate` is the single point at which
recorded findings become plan entries, so a completed audit always implies its
findings reached the plan.

**Idempotence (Requirement 1.5).** Consolidation is idempotent — feeding an
already-consolidated plan back through :func:`consolidate` yields an equivalent
plan. To make that natural, :func:`consolidate` accepts both raw ``Finding``
records and already-merged ``PlanEntry`` records in any mix.
"""

from __future__ import annotations

from collections.abc import Iterable

from cna.review.model import Finding, PlanEntry, RemediationPlan, Severity

__all__ = ["consolidate"]


def _blocker_id_for(findings: list[Finding]) -> str | None:
    """Return the owning ``blocker_id`` for a merged group, if any.

    An entry is an escalation iff a contributing finding is blocker-owned. When
    several contributing findings carry a ``blocker_id`` they describe the same
    underlying defect (same ``dedup_key``); the lowest ``R-0NN`` id is chosen
    for a stable, deterministic result.
    """
    ids = {f.blocker_id for f in findings if f.blocker_id}
    if not ids:
        return None
    return min(ids)


def _entry_from_group(dedup_key: str, findings: list[Finding]) -> PlanEntry:
    """Merge every finding sharing ``dedup_key`` into a single plan entry."""
    severity = Severity(max(f.severity for f in findings))
    referenced_areas = {f.area for f in findings}
    subjects = {f.subject for f in findings}
    blocker_id = _blocker_id_for(findings)
    # The proposed action of the most severe contributor is the most
    # representative; ties resolve on the finding's own ordering (stable).
    proposed_action = max(findings, key=lambda f: f.severity).proposed_action
    return PlanEntry(
        dedup_key=dedup_key,
        severity=severity,
        proposed_action=proposed_action,
        referenced_areas=referenced_areas,
        subjects=subjects,
        is_escalation=blocker_id is not None,
        blocker_id=blocker_id,
    )


def _explode(entry: PlanEntry) -> list[Finding]:
    """Turn an already-merged plan entry back into equivalent raw findings.

    This lets :func:`consolidate` accept a previously consolidated plan and
    re-merge it without changing the result (idempotence). Each referenced area
    is paired with each subject so the union semantics are preserved on the
    round trip.
    """
    findings: list[Finding] = []
    areas = sorted(entry.referenced_areas)
    subjects = sorted(entry.subjects) or [""]
    for area in areas:
        for subject in subjects:
            findings.append(
                Finding(
                    area=area,
                    severity=entry.severity,
                    proposed_action=entry.proposed_action,
                    dedup_key=entry.dedup_key,
                    subject=subject,
                    blocker_id=entry.blocker_id,
                )
            )
    return findings


def consolidate(items: Iterable[Finding | PlanEntry]) -> RemediationPlan:
    """Consolidate findings (and/or plan entries) into one ordered plan.

    Findings sharing a ``dedup_key`` collapse into a single
    :class:`~cna.review.model.PlanEntry` whose ``referenced_areas``/``subjects``
    are the unions of the contributors and whose ``severity`` is their maximum.
    The resulting entries are ordered by ``severity`` descending.

    Passing an already-consolidated plan's entries back in produces an
    equivalent plan (idempotence): ``consolidate(consolidate(fs).entries)``
    equals ``consolidate(fs)``.

    :param items: raw ``Finding`` records, previously merged ``PlanEntry``
        records, or any mix of the two.
    :returns: a :class:`~cna.review.model.RemediationPlan` with entries ordered
        by severity descending.
    """
    findings: list[Finding] = []
    for item in items:
        if isinstance(item, PlanEntry):
            findings.extend(_explode(item))
        else:
            findings.append(item)

    groups: dict[str, list[Finding]] = {}
    for finding in findings:
        groups.setdefault(finding.dedup_key, []).append(finding)

    entries = [_entry_from_group(key, group) for key, group in groups.items()]
    # Order by severity descending; ``dedup_key`` breaks ties for a stable,
    # deterministic plan across runs and re-consolidations.
    entries.sort(key=lambda e: (-int(e.severity), e.dedup_key))
    return RemediationPlan(entries=entries)
