"""Consolidation entry point: build the single ``Remediation_Plan`` (task 14.1).

This module is the top of the review pipeline's CONSOLIDATE stage (design
"Consolidation, Deduplication, and Escalation"). Where each per-area emitter in
:mod:`cna.review.areas` produces that area's raw :class:`~cna.review.model.Finding`
records, :func:`build_remediation_plan` gathers *every* area's findings, routes
each one through the scope gate (:func:`~cna.review.blockers.gate_finding`) so
blocker-owned findings are classified as ``Escalation_Record`` entries, and folds
the whole set into one severity-ordered :class:`~cna.review.model.RemediationPlan`.

The flow is deliberately two-stage so both load-bearing behaviours are honoured:

  * **Scope gate first (Requirement 10).** Each raw finding is passed through
    :func:`~cna.review.blockers.gate_finding` against the ``REVIEW.md`` blockers.
    A finding whose owning blocker is not closed becomes an escalation carrying
    its ``blocker_id``; a finding with no owning blocker (or a closed one) becomes
    a fixable entry. This classifies escalations *before* consolidation, so the
    R-003/R-005/R-006/R-008/R-009 consumers are marked as escalations.
  * **Consolidate second (Requirements 1.4, 1.5).** The gated entries are fed
    into :func:`~cna.review.consolidate.consolidate`, which merges entries sharing
    a ``dedup_key`` (``referenced_areas``/``subjects`` unions, ``severity`` max)
    and orders the plan by severity descending. Because ``consolidate`` accepts
    :class:`~cna.review.model.PlanEntry` records as well as raw findings, feeding
    it the gated entries preserves the escalation classification through the merge.

Every area emitter listed in :data:`AREA_EMITTERS` contributes, so the plan
reflects the full audit — every area's audit findings, verification records,
and escalations. The two Terraform areas are represented by the relocation
records in :mod:`cna.review.areas.terraform_relocated`: the deployment layer
left the core (``TODO.md`` T-504) and its findings and gated escalations live in
the appliance repositories.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from pathlib import Path

from cna.review.areas import (
    app_typescript_findings,
    app_typescript_verify_findings,
    cicd_findings,
    cicd_sha_and_escalation_findings,
    cicd_verify_findings,
    containers_packaging_findings,
    containers_packaging_verify_findings,
    documentation_findings,
    documentation_verify_findings,
    observability_findings,
    python_engine_api_findings,
    python_engine_api_verify_findings,
    security_secrets_findings,
    terraform_relocated_findings,
)
from cna.review.blockers import Blocker, gate_finding, load_blockers
from cna.review.consolidate import consolidate
from cna.review.model import Finding, PlanEntry, RemediationPlan

__all__ = [
    "AREA_EMITTERS",
    "EXPECTED_ESCALATION_BLOCKERS",
    "assert_escalations_well_formed",
    "build_remediation_plan",
    "collect_findings",
    "escalation_summary",
]

# The owning ``REVIEW.md`` blockers this review's escalations consume (design
# "Blocker model" table, "Consumers in this review" column). R-005 is the
# Bedrock model-access opt-in the observability area's live-Bedrock coverage
# depends on, and R-009 is the Wiki-publication gate. R-001 – R-004, R-006 and
# R-008 left the core with the deployment layer (TODO.md T-504): the Terraform
# and workflow subjects they gated are reviewed in the appliance repositories,
# whose REVIEW.md files own those escalations now. R-007 is deliberately
# absent: it is resolved-but-not-closed, so its subject stays out of automated
# scope rather than becoming an escalation consumer.
EXPECTED_ESCALATION_BLOCKERS: frozenset[str] = frozenset(
    {
        "R-005",  # Bedrock model access opt-in — Observability (live AI-path coverage)
        "R-009",  # GitHub Wiki write access — Documentation
    }
)

# The ``R-0NN`` shape an escalation's owning blocker id must match (design
# "Escalation classification"): ``R-`` followed by at least three digits.
_BLOCKER_ID_PATTERN = re.compile(r"R-\d{3,}")

# Every area finding emitter that feeds the consolidated plan. Ordered by owner
# area for readability; ordering does not affect the consolidated result (the
# consolidation engine sorts by severity and dedup key). The AWS gated
# escalations (R-001 – R-006) and the R-003 CI escalation left with the
# deployment layer (TODO.md T-504) and are owned by the appliances' REVIEW.md
# files; the escalations that remain are R-005 (observability, live Bedrock) and
# R-009 (documentation, Wiki publication).
AREA_EMITTERS: tuple[Callable[[], list[Finding]], ...] = (
    # python-engine-api
    python_engine_api_findings,
    python_engine_api_verify_findings,
    # app-typescript
    app_typescript_findings,
    app_typescript_verify_findings,
    # terraform-azure + terraform-aws (relocated to the appliances; T-504)
    terraform_relocated_findings,
    # cicd (audit + verify + the SHA-pin findings)
    cicd_findings,
    cicd_verify_findings,
    cicd_sha_and_escalation_findings,
    # security-secrets
    security_secrets_findings,
    # containers-packaging
    containers_packaging_findings,
    containers_packaging_verify_findings,
    # observability (includes the R-005 live-Bedrock escalation)
    observability_findings,
    # documentation (includes the R-009 Wiki-publication escalation)
    documentation_findings,
    documentation_verify_findings,
)


def collect_findings() -> list[Finding]:
    """Gather every area emitter's ``Finding`` records into one flat list.

    Calls each emitter in :data:`AREA_EMITTERS` and concatenates the results.
    No deduplication or classification happens here — that is the job of
    :func:`build_remediation_plan`.

    :returns: every raw finding from every area, in emitter order.
    """
    findings: list[Finding] = []
    for emitter in AREA_EMITTERS:
        findings.extend(emitter())
    return findings


def build_remediation_plan(
    review_path: str | Path | None = None,
    *,
    findings: Iterable[Finding] | None = None,
) -> RemediationPlan:
    """Consolidate every area's findings into the single ``Remediation_Plan``.

    The consolidation entry point for spec task 14.1. Gathers each area's
    :class:`~cna.review.model.Finding` records (from :func:`collect_findings`
    unless an explicit ``findings`` iterable is supplied), routes every finding
    through the scope gate (:func:`~cna.review.blockers.gate_finding`) so a
    blocker-owned finding is classified as an ``Escalation_Record`` carrying its
    ``blocker_id`` while a non-gated finding stays fixable, and folds the gated
    entries into one severity-ordered :class:`~cna.review.model.RemediationPlan`
    via :func:`~cna.review.consolidate.consolidate`.

    :param review_path: path to ``REVIEW.md`` for the blocker model; defaults to
        the repository copy alongside the ``cna`` package.
    :param findings: an explicit iterable of findings to consolidate; defaults to
        every area emitter's output (:func:`collect_findings`). Supplied mainly
        so tests can drive a controlled finding set.
    :returns: the single consolidated, severity-ordered ``Remediation_Plan``.
    :raises KeyError: if a finding references a ``blocker_id`` absent from
        ``REVIEW.md`` (an escalation must map to a real blocker).
    """
    blockers: dict[str, Blocker] = load_blockers(review_path)
    raw = list(findings) if findings is not None else collect_findings()
    gated_entries = [gate_finding(finding, blockers) for finding in raw]
    return consolidate(gated_entries)


def escalation_summary(
    plan: RemediationPlan,
) -> dict[str, list[PlanEntry]]:
    """Group a plan's escalation entries by their owning ``blocker_id``.

    The wiring view for spec task 14.3: every :class:`~cna.review.model.PlanEntry`
    marked ``is_escalation`` is bucketed under the ``R-0NN`` id it carries, so a
    caller can see exactly which blockers own escalations and which entries each
    blocker gates. Fixable entries are excluded — by construction they never
    carry a ``blocker_id``.

    :param plan: the consolidated ``Remediation_Plan`` to summarize.
    :returns: a mapping of owning ``blocker_id`` to the escalation entries that
        carry it, in the plan's (severity-descending) order.
    """
    summary: dict[str, list[PlanEntry]] = {}
    for entry in plan.entries:
        if not entry.is_escalation:
            continue
        # An escalation entry always carries a non-empty blocker_id (enforced by
        # PlanEntry construction); the guard keeps the type checker honest.
        if entry.blocker_id is None:  # pragma: no cover - defended by PlanEntry
            continue
        summary.setdefault(entry.blocker_id, []).append(entry)
    return summary


def assert_escalations_well_formed(
    plan: RemediationPlan,
    review_path: str | Path | None = None,
    *,
    expected_blockers: frozenset[str] = EXPECTED_ESCALATION_BLOCKERS,
) -> dict[str, list[PlanEntry]]:
    """Assert every escalation is wired to a real owning blocker (task 14.3).

    Verifies the escalation-wiring invariant on a built ``Remediation_Plan``
    (Requirements 1.6, 10.4):

      * **Every escalation carries an owning blocker id.** Each entry marked
        ``is_escalation`` carries a non-empty ``blocker_id`` matching the
        ``R-0NN`` pattern that is present in ``REVIEW.md``.
      * **No fixable entry carries a blocker id.** An entry that is not an
        escalation must have ``blocker_id is None``.
      * **The escalation blocker set is exactly the expected consumers.** The
        set of owning blockers across all escalations equals
        ``expected_blockers`` (by default :data:`EXPECTED_ESCALATION_BLOCKERS`,
        the R-005 and R-009 consumers that remain in the core).

    :param plan: the consolidated ``Remediation_Plan`` to verify.
    :param review_path: path to ``REVIEW.md`` for the blocker model; defaults to
        the repository copy alongside the ``cna`` package.
    :param expected_blockers: the owning blocker set the escalations must cover
        exactly; defaults to :data:`EXPECTED_ESCALATION_BLOCKERS`.
    :returns: the :func:`escalation_summary` mapping of ``blocker_id`` to its
        escalation entries, so callers can inspect the wiring after the assert.
    :raises AssertionError: if any escalation lacks a valid known blocker id, if
        any fixable entry carries a blocker id, or if the escalation blocker set
        is not exactly ``expected_blockers``.
    """
    blockers = load_blockers(review_path)

    for entry in plan.entries:
        if entry.is_escalation:
            assert entry.blocker_id, f"escalation entry {entry.dedup_key!r} carries no blocker_id"
            assert _BLOCKER_ID_PATTERN.fullmatch(entry.blocker_id), (
                f"escalation entry {entry.dedup_key!r} has a malformed "
                f"blocker_id {entry.blocker_id!r}"
            )
            assert entry.blocker_id in blockers, (
                f"escalation entry {entry.dedup_key!r} references "
                f"{entry.blocker_id!r} which is absent from REVIEW.md"
            )
        else:
            assert entry.blocker_id is None, (
                f"fixable entry {entry.dedup_key!r} carries a blocker_id {entry.blocker_id!r}"
            )

    summary = escalation_summary(plan)
    escalation_blockers = frozenset(summary)
    assert escalation_blockers == expected_blockers, (
        "escalation blocker set mismatch: "
        f"missing {sorted(expected_blockers - escalation_blockers)}, "
        f"unexpected {sorted(escalation_blockers - expected_blockers)}"
    )
    return summary
