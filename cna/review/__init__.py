"""Production-hardening review tooling.

The review's artifacts are the :class:`RemediationPlan` and its entries. Every
area reviewer emits :class:`Finding` records into the shared consolidation
pipeline defined in this package (see the ``production-readiness`` spec design).

The :mod:`cna.review.blockers` layer adds the human-gated blocker model read
from ``REVIEW.md`` and the *scope gate* that turns a blocker-owned finding into
an ``Escalation_Record`` (Requirement 10) while a not-closed blocker holds its
subject out of automated scope.
"""

from cna.review.blockers import (
    Blocker,
    BlockerStatus,
    classify_status,
    gate_finding,
    load_blockers,
    parse_blockers,
)
from cna.review.consolidate import consolidate
from cna.review.model import (
    AREAS,
    Finding,
    PlanEntry,
    RemediationPlan,
    Severity,
)
from cna.review.plan import (
    AREA_EMITTERS,
    EXPECTED_ESCALATION_BLOCKERS,
    assert_escalations_well_formed,
    build_remediation_plan,
    collect_findings,
    escalation_summary,
)

__all__ = [
    "AREAS",
    "AREA_EMITTERS",
    "EXPECTED_ESCALATION_BLOCKERS",
    "Blocker",
    "BlockerStatus",
    "Finding",
    "PlanEntry",
    "RemediationPlan",
    "Severity",
    "assert_escalations_well_formed",
    "build_remediation_plan",
    "classify_status",
    "collect_findings",
    "consolidate",
    "escalation_summary",
    "gate_finding",
    "load_blockers",
    "parse_blockers",
]
