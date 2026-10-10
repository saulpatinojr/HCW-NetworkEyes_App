"""Azure rule registry — one typed, versioned rule set for every Azure finding.

Change set B of the refactoring plan (``REFACTOR_APP.md`` in ``HCW-NetworkEyes_App``):
the rules that lived in ``AnalysisEngine`` (Engine A, ``AZ-NET-001..019``), the
``_check_*`` helpers of ``apps/cna-api/main.py`` (Engine B, now ``AZ-NET-020..033`` and
``AZ-BCDR-006/007``) and the BC/DR and FinOps generators (``AZ-BCDR-001..005``,
``AZ-COST-001..005``) are registered here under one contract:

* every rule has a stable id, a hedge-free title, a severity, a category, a version, a
  Microsoft Learn URL and at least one framework mapping (``RuleMeta``);
* a rule is a pure function ``(subscription, topology) -> observations``; it reads the
  topology checkpoint only (DD-008) and performs no I/O;
* ``evaluate(topology)`` runs every rule over every unblocked subscription, enforces the
  observed-state discipline on every finding (DD-002: ``fact``, ``title`` and
  ``description`` carry no hedge language), stamps the rule's metadata onto each finding,
  deduplicates on ``"{rule_id}:{resource_id}"`` (first occurrence wins) and returns a
  ``FindingsReport``. It is pure: the CLI and the API persist around it.

Rule ids are never reused; a changed rule bumps its own ``version``; ``RULES_VERSION``
moves whenever the id set or any version changes (``tests/unit/test_registry.py`` pins
``rules_digest()``). Live-only rules — those whose inputs come from the metric, diagnostic
and BGP collectors rather than a Resource Graph export — stay registered with
``applies_to="live-only"`` so the downstream lab edition's ``unknowns[]`` list is stable.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from cna.ai_engine.observed_state_enforcer import ObservedStateEnforcer, ObservedStateViolation
from cna.core.finding_taxonomy import classify_traffic_direction
from cna.core.findings_schema import (
    FINDINGS_SCHEMA_VERSION,
    Finding,
    FindingRecommendation,
    FindingSeverity,
    FindingsReport,
    FindingStatus,
    FrameworkMapping,
    ObservedState,
)
from cna.core.topology.azure import AzureSubscriptionTopology, AzureTopology

logger = logging.getLogger("cna.azure_rules")

# Calendar version of the registry. Bump it, and re-pin ``rules_digest()`` in
# tests/unit/test_registry.py, whenever a rule id is added or a rule's ``version`` moves.
RULES_VERSION = "2026.10.0"

# ``export``: evaluable from a Resource Graph export of the network resources.
# ``live-only``: needs a live collector (Azure Monitor metrics, diagnostic settings,
# BGP actions, Log Analytics); the lab edition reports these as ``unknown``.
AppliesTo = Literal["export", "live-only"]

_LEARN_PREFIX = "https://learn.microsoft.com/"
_RECOMMENDATION_SOURCE = "CNA Platform"
_PLATFORM = "azure"


@dataclass(frozen=True)
class RuleMeta:
    """Everything a rule states about itself; stamped onto every finding it emits."""

    id: str
    title: str
    severity: FindingSeverity
    category: str
    version: int
    learn_url: str
    frameworks: tuple[FrameworkMapping, ...]
    applies_to: AppliesTo
    evidence: str


@dataclass(frozen=True)
class Observation:
    """What a rule observed on one resource.

    The registry turns it into a ``Finding`` with the rule's metadata, so a rule states
    only what it saw: the resource, the fact and where in the checkpoint the fact came
    from. ``title``, ``severity`` and ``description`` override the rule's defaults for
    the one finding; ``recommendation`` is advice and is never hedge-checked.
    """

    resource_id: str
    resource_type: str
    fact: str
    evidence_ref: str
    region: str | None = None
    title: str | None = None
    description: str | None = None
    recommendation: str | None = None
    severity: FindingSeverity | None = None
    affected_resources: tuple[str, ...] = ()


RuleFn = Callable[[AzureSubscriptionTopology, AzureTopology], Iterable["Observation | Finding"]]
ProgressFn = Callable[[int, int, AzureSubscriptionTopology, list[Finding]], None]

RULES: dict[str, tuple[RuleMeta, RuleFn]] = {}

_ENFORCER = ObservedStateEnforcer()


class DuplicateRuleError(ValueError):
    """A second rule tried to register an id that is already taken."""


def rule(
    *,
    id: str,  # noqa: A002 — the plan's field name; ``RuleMeta.id`` mirrors it
    title: str,
    severity: FindingSeverity,
    category: str,
    version: int,
    learn_url: str,
    frameworks: tuple[FrameworkMapping, ...],
    applies_to: AppliesTo,
    evidence: str,
) -> Callable[[RuleFn], RuleFn]:
    """Register a rule function under ``id``.

    Registration itself enforces the contract: a duplicate id, a hedged title, a missing
    framework mapping or a non-Learn URL raises at import time, so a bad rule never
    reaches a run.
    """
    hedges = _ENFORCER.scan_text(title)
    if hedges:
        raise ObservedStateViolation(f"Rule {id}: title contains hedge language: {hedges!r}")
    if not frameworks:
        raise ValueError(f"Rule {id}: at least one framework mapping is required")
    if not learn_url.startswith(_LEARN_PREFIX):
        raise ValueError(f"Rule {id}: learn_url must be a Microsoft Learn page, got {learn_url!r}")
    if version < 1:
        raise ValueError(f"Rule {id}: version must be a positive integer, got {version!r}")
    meta = RuleMeta(
        id=id,
        title=title,
        severity=severity,
        category=category,
        version=version,
        learn_url=learn_url,
        frameworks=tuple(frameworks),
        applies_to=applies_to,
        evidence=evidence,
    )

    def register(fn: RuleFn) -> RuleFn:
        if meta.id in RULES:
            raise DuplicateRuleError(f"Rule id {meta.id} is already registered")
        RULES[meta.id] = (meta, fn)
        return fn

    return register


def rules_digest() -> str:
    """SHA-256 over the sorted ``id:version`` pairs — the thing ``RULES_VERSION`` tracks."""
    lines = "\n".join(f"{rule_id}:{meta.version}" for rule_id, (meta, _) in sorted(RULES.items()))
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def rule_metadata() -> list[RuleMeta]:
    """Every registered rule's metadata, ordered by id."""
    return [meta for _, (meta, _) in sorted(RULES.items())]


def _finding_from_observation(
    meta: RuleMeta, obs: Observation, sub: AzureSubscriptionTopology
) -> Finding:
    recommendations = (
        [
            FindingRecommendation(
                source=_RECOMMENDATION_SOURCE,
                text=obs.recommendation,
                reference_url=meta.learn_url,
            )
        ]
        if obs.recommendation
        else []
    )
    return Finding(
        rule_id=meta.id,
        severity=obs.severity or meta.severity,
        platform=_PLATFORM,
        region=obs.region or "Global",
        category=meta.category,
        title=obs.title or meta.title,
        description=obs.description,
        resource_id=obs.resource_id,
        resource_type=obs.resource_type,
        account_id=sub.subscription_id,
        observed_state=ObservedState(fact=obs.fact, evidence_ref=obs.evidence_ref),
        affected_resources=list(obs.affected_resources),
        framework_mappings=list(meta.frameworks),
        recommendations=recommendations,
        recommendation=obs.recommendation,
        traffic_direction=classify_traffic_direction(meta.id, meta.category, obs.resource_type),
        status=FindingStatus.OPEN,
    )


def _complete_finding(meta: RuleMeta, finding: Finding) -> Finding:
    """A rule that builds its own ``Finding`` still gets the registry's guarantees."""
    if finding.rule_id != meta.id:
        raise ValueError(f"Rule {meta.id} emitted a finding carrying rule_id {finding.rule_id!r}")
    updates: dict[str, object] = {}
    if not finding.framework_mappings:
        updates["framework_mappings"] = list(meta.frameworks)
    if not finding.platform:
        updates["platform"] = _PLATFORM
    if not finding.category:
        updates["category"] = meta.category
    if not finding.traffic_direction:
        updates["traffic_direction"] = classify_traffic_direction(
            meta.id, finding.category or meta.category, finding.resource_type or ""
        )
    if finding.status is None:
        updates["status"] = FindingStatus.OPEN
    return finding.model_copy(update=updates) if updates else finding


def _validate(finding: Finding) -> None:
    """DD-002 on every field a reader treats as a statement of fact."""
    _ENFORCER.validate(finding)  # observed_state.fact → ObservedStateViolation
    for field_name in ("title", "description"):
        text = getattr(finding, field_name) or ""
        hedges = _ENFORCER.scan_text(text)
        if hedges:
            raise ObservedStateViolation(
                f"Finding {finding.rule_id} on {finding.resource_id}: {field_name} contains "
                f"hedge language: {hedges!r}. Rewrite without: {hedges}"
            )
    if not finding.framework_mappings:
        raise ValueError(
            f"Finding {finding.rule_id} has no framework_mappings. "
            "Every finding must map to at least one framework control."
        )


def evaluate_subscription(
    sub: AzureSubscriptionTopology, topology: AzureTopology, seen: set[str] | None = None
) -> list[Finding]:
    """Run every registered rule over one subscription.

    ``seen`` carries the deduplication register across subscriptions when the caller is
    ``evaluate``; a tenant-wide rule that fires from each subscription lands once.
    """
    if sub.discovery_blocked:
        return []
    register = seen if seen is not None else set()
    findings: list[Finding] = []
    for rule_id, (meta, fn) in sorted(RULES.items()):
        for emitted in fn(sub, topology):
            finding = (
                _complete_finding(meta, emitted)
                if isinstance(emitted, Finding)
                else _finding_from_observation(meta, emitted, sub)
            )
            _validate(finding)
            key = f"{rule_id}:{finding.resource_id}"
            if key in register:
                logger.debug("Deduplicated finding %s", key)
                continue
            register.add(key)
            findings.append(finding)
    return findings


def evaluate(topology: AzureTopology, *, progress: ProgressFn | None = None) -> FindingsReport:
    """Evaluate every rule over every unblocked subscription of ``topology``.

    Pure: reads the topology, returns a report, touches no store. ``progress`` is called
    after each subscription with ``(index, total, subscription, its findings)``.
    """
    findings: list[Finding] = []
    seen: set[str] = set()
    total = len(topology.subscriptions)
    for index, sub in enumerate(topology.subscriptions, start=1):
        sub_findings = evaluate_subscription(sub, topology, seen)
        findings.extend(sub_findings)
        if progress:
            progress(index, total, sub, sub_findings)

    def count(severity: FindingSeverity) -> int:
        return sum(1 for f in findings if f.severity == severity)

    return FindingsReport(
        engagement_id=topology.engagement_id,
        schema_version=FINDINGS_SCHEMA_VERSION,
        findings=findings,
        total_count=len(findings),
        critical_count=count(FindingSeverity.CRITICAL),
        high_count=count(FindingSeverity.HIGH),
        medium_count=count(FindingSeverity.MEDIUM),
        low_count=count(FindingSeverity.LOW),
        review_complete=False,  # DD-009: a human sets this
        generated_at=datetime.now(UTC).isoformat(),
    )
