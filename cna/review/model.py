"""Review data model for the production-hardening review.

These are the plain records every area reviewer emits into and that the
consolidation engine collapses into a single ``Remediation_Plan``. The shapes
match the ``production-readiness`` spec design ("Data Models"):

  * :class:`Severity` — an ``IntEnum`` ordering findings from ``INFORMATIONAL``
    (0) to ``CRITICAL`` (4), so ``severity``-descending ordering is a plain
    numeric sort and merged entries can take the ``max``.
  * :data:`AREAS` — the closed set of the nine fixed owner areas. Every
    ``Finding.area`` is drawn only from this set.
  * :class:`Finding`, :class:`PlanEntry`, :class:`RemediationPlan` — the raw
    finding, a consolidated plan entry, and the ordered plan.

Well-formedness (design Property 1) is enforced at construction time: an
invalid ``severity``, an ``area`` outside :data:`AREAS`, or an empty
``proposed_action`` raises :class:`ValueError` rather than producing a
malformed record that would flow silently into the plan.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum


class Severity(IntEnum):
    """Finding severity, ordered so a larger value is more severe.

    The integer ordering is load-bearing: the plan is sorted by severity
    descending and merged entries take the maximum severity among their
    contributing findings.
    """

    INFORMATIONAL = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# The nine fixed owner areas — the closed set every finding's ``area`` is drawn
# from. Kept in sync with the design's "Components and Interfaces" sections.
AREAS: frozenset[str] = frozenset(
    {
        "app-typescript",  # apps/cna-web (Next.js, incl. AWS-shaped UI views)
        "python-engine-api",  # cna/ core + apps/cna-api + apps/cna-worker decision
        "terraform-azure",  # the Azure appliance's Terraform (reviewed there; T-504)
        "terraform-aws",  # the AWS appliance's Terraform (reviewed there; T-504)
        "cicd",  # .github/workflows (200, 300, 310, 370)
        "security-secrets",  # detect-secrets, gitleaks, pip-audit, npm audit
        "containers-packaging",  # Dockerfiles, docker-compose, cna CLI packaging
        "observability",  # structured logging, AI-path coverage
        "documentation",  # README/CHANGELOG/TODO accuracy, executable paths
    }
)


def _require_severity(value: object) -> Severity:
    """Validate and normalize a severity value to a :class:`Severity` member."""
    if isinstance(value, Severity):
        return value
    # A bare int that maps to a member is acceptable; anything else is not.
    if isinstance(value, int) and not isinstance(value, bool):
        try:
            return Severity(value)
        except ValueError:
            pass
    raise ValueError(f"severity must be a Severity member, got {value!r}")


@dataclass
class Finding:
    """A single raw finding emitted by an area reviewer.

    Findings sharing a ``dedup_key`` describe one underlying defect and are
    later collapsed into a single :class:`PlanEntry`.
    """

    area: str  # ∈ AREAS
    severity: Severity
    proposed_action: str  # non-empty
    dedup_key: str  # findings sharing this describe one defect
    subject: str  # the file/module/workflow the finding is about
    blocker_id: str | None = None  # set iff this maps to a REVIEW.md blocker (R-0NN)

    def __post_init__(self) -> None:
        self.severity = _require_severity(self.severity)
        if self.area not in AREAS:
            raise ValueError(f"area must be one of {sorted(AREAS)}, got {self.area!r}")
        if not isinstance(self.proposed_action, str) or not self.proposed_action.strip():
            raise ValueError("proposed_action must be a non-empty string")


@dataclass
class PlanEntry:
    """A consolidated plan entry: one underlying defect across contributing areas.

    ``severity`` is the maximum among the merged findings and
    ``referenced_areas`` is the union of their areas. An escalation entry
    (``is_escalation``) carries a required ``blocker_id`` and gets no automated
    fix; a fixable entry never carries a ``blocker_id``.
    """

    dedup_key: str
    severity: Severity  # max severity among merged findings
    proposed_action: str
    referenced_areas: set[str]  # union of contributing areas
    subjects: set[str]
    is_escalation: bool  # True ⇒ blocker_id required, no automated fix
    blocker_id: str | None = None  # required iff is_escalation

    def __post_init__(self) -> None:
        self.severity = _require_severity(self.severity)
        if not isinstance(self.proposed_action, str) or not self.proposed_action.strip():
            raise ValueError("proposed_action must be a non-empty string")
        unknown = set(self.referenced_areas) - AREAS
        if unknown:
            raise ValueError(
                f"referenced_areas must be drawn from {sorted(AREAS)}, unknown: {sorted(unknown)}"
            )
        if self.is_escalation:
            if not self.blocker_id:
                raise ValueError("an escalation entry requires a non-empty blocker_id")
        elif self.blocker_id is not None:
            raise ValueError("a fixable entry must not carry a blocker_id")


@dataclass
class RemediationPlan:
    """The single consolidated plan: entries ordered by severity descending."""

    entries: list[PlanEntry] = field(default_factory=list)
