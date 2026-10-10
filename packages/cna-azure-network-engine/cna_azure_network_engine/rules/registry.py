"""Azure rule registry — one typed, versioned rule set for every Azure finding.

Every rule has a stable id, a hedge-free title, a severity, a category, a version, a
Microsoft Learn URL, at least one framework mapping, an ``applies_to`` of ``export`` or
``live-only`` and an evidence path (``RuleMeta``). A rule is a pure function
``(subscription, topology) -> observations`` over the topology checkpoint (DD-008).

``evaluate(topology)`` runs every rule over every unblocked subscription, enforces the
observed-state discipline on every finding (DD-002: ``fact``, ``title`` and ``description``
carry no hedge language), stamps the rule's metadata (``rule_version``, ``learn_url``,
``remediation``, frameworks, traffic plane), deduplicates on ``"{rule_id}:{resource_id}"``
(first occurrence wins) and returns a ``FindingsReport`` whose ``unknowns`` list names every
rule it could not answer: a live-only rule whose collector inputs are absent from every
subscription, a rule that needs resource properties when the export has none, or a rule
that yielded ``NotEvaluable``. It is pure: callers persist around it.

Rule ids are never reused; a changed rule bumps its own ``version``; ``RULES_VERSION`` moves
whenever the id set or any version changes, and ``rules_digest()`` is the sha256 the
downstream lab edition pins over the same ``id:version`` table.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from cna_azure_network_engine.findings.enforcer import ObservedStateEnforcer, ObservedStateViolation
from cna_azure_network_engine.findings.schema import (
    FINDINGS_SCHEMA_VERSION,
    EvidenceState,
    Finding,
    FindingSeverity,
    FindingsReport,
    FrameworkMapping,
    ObservedState,
    Unknown,
)
from cna_azure_network_engine.model.azure import AzureSubscriptionTopology, AzureTopology
from cna_azure_network_engine.rules.taxonomy import classify_traffic_direction

logger = logging.getLogger("cna_azure_network_engine.rules")

# Calendar version of the registry. Bump it, and re-pin the id:version table in the tests,
# whenever a rule id is added or a rule's ``version`` moves.
RULES_VERSION = "2026.10.0"

# ``export``: evaluable from a Resource Graph export of the network resources.
# ``live-only``: needs a live collector (Azure Monitor metrics, diagnostic settings, BGP
# actions, Log Analytics); without those inputs the rule is reported in ``unknowns``.
AppliesTo = Literal["export", "live-only"]

NO_PROPERTIES_REASON = (
    "the export has no properties column, so the fields this rule reads are absent"
)
_LEARN_PREFIX = "https://learn.microsoft.com/"
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
    remediation: str | None = None  # default when an observation carries none
    description: str | None = None  # default when an observation carries none
    needs_properties: bool = True  # False for rules that read resource existence only
    inputs: tuple[str, ...] = ()  # subscription attributes a live-only rule reads


@dataclass(frozen=True)
class Observation:
    """What a rule observed on one resource; the registry turns it into a ``Finding``."""

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
    state: EvidenceState = "observed"


@dataclass(frozen=True)
class NotEvaluable:
    """Yielded by a rule that cannot decide over this topology (one ``unknowns`` entry per rule)."""

    reason: str


Emitted = Observation | Finding | NotEvaluable
RuleFn = Callable[[AzureSubscriptionTopology, AzureTopology], Iterable[Emitted]]
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
    remediation: str | None = None,
    description: str | None = None,
    needs_properties: bool = True,
    inputs: tuple[str, ...] = (),
) -> Callable[[RuleFn], RuleFn]:
    """Register a rule function under ``id``.

    Registration enforces the contract: a duplicate id, a hedged title or description, a
    missing framework mapping, a non-Learn URL or a live-only rule without declared inputs
    raises at import time, so a bad rule never reaches a run.
    """
    for field_name, text in (("title", title), ("description", description or "")):
        hedges = _ENFORCER.scan_text(text)
        if hedges:
            raise ObservedStateViolation(
                f"Rule {id}: {field_name} contains hedge language: {hedges!r}"
            )
    if not frameworks:
        raise ValueError(f"Rule {id}: at least one framework mapping is required")
    if not learn_url.startswith(_LEARN_PREFIX):
        raise ValueError(f"Rule {id}: learn_url must be a Microsoft Learn page, got {learn_url!r}")
    if version < 1:
        raise ValueError(f"Rule {id}: version must be a positive integer, got {version!r}")
    if applies_to == "live-only" and not inputs:
        raise ValueError(f"Rule {id}: a live-only rule names the subscription inputs it reads")
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
        remediation=remediation,
        description=description,
        needs_properties=needs_properties,
        inputs=tuple(inputs),
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


def rules_table() -> list[dict]:
    """The registry serialised (``GET /api/rules``, ``rules.json`` in a bundle)."""
    return [
        {
            "id": m.id,
            "title": m.title,
            "severity": m.severity.value,
            "category": m.category,
            "version": m.version,
            "appliesTo": m.applies_to,
            "evidence": m.evidence,
            "needsProperties": m.needs_properties,
            "description": m.description,
            "remediation": m.remediation,
            "learnUrl": m.learn_url,
            "frameworks": [f.model_dump(by_alias=True, exclude_none=True) for f in m.frameworks],
        }
        for m in rule_metadata()
    ]


def _finding_from_observation(
    meta: RuleMeta, obs: Observation, sub: AzureSubscriptionTopology
) -> Finding:
    return Finding(
        id=f"{meta.id}:{obs.resource_id}",
        rule_id=meta.id,
        rule_version=meta.version,
        severity=obs.severity or meta.severity,
        platform=_PLATFORM,
        region=obs.region or "Global",
        category=meta.category,
        title=obs.title or meta.title,
        description=obs.description or meta.description,
        resource_id=obs.resource_id,
        resource_type=obs.resource_type,
        account_id=sub.subscription_id,
        observed_state=ObservedState(state=obs.state, fact=obs.fact, evidence_ref=obs.evidence_ref),
        affected_resources=list(obs.affected_resources),
        framework_mappings=list(meta.frameworks),
        remediation=obs.recommendation or meta.remediation,
        learn_url=meta.learn_url,
        traffic_direction=classify_traffic_direction(meta.id, meta.category, obs.resource_type),
    )


def _complete_finding(meta: RuleMeta, finding: Finding) -> Finding:
    """A rule that builds its own ``Finding`` still gets the registry's guarantees."""
    if finding.rule_id != meta.id:
        raise ValueError(f"Rule {meta.id} emitted a finding carrying rule_id {finding.rule_id!r}")
    updates: dict[str, object] = {"rule_version": meta.version}
    if not finding.id:
        updates["id"] = f"{meta.id}:{finding.resource_id}"
    if not finding.framework_mappings:
        updates["framework_mappings"] = list(meta.frameworks)
    if not finding.platform:
        updates["platform"] = _PLATFORM
    if not finding.category:
        updates["category"] = meta.category
    if not finding.learn_url:
        updates["learn_url"] = meta.learn_url
    if not finding.remediation:
        updates["remediation"] = meta.remediation
    if not finding.traffic_direction:
        updates["traffic_direction"] = classify_traffic_direction(
            meta.id, finding.category or meta.category, finding.resource_type or ""
        )
    return finding.model_copy(update=updates)


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


def _has_live_inputs(meta: RuleMeta, topology: AzureTopology) -> bool:
    return any(
        getattr(sub, attr, None)
        for sub in topology.subscriptions
        if not sub.discovery_blocked
        for attr in meta.inputs
    )


def _skip_reason(meta: RuleMeta, topology: AzureTopology) -> str | None:
    """Why a rule cannot run at all over this topology, or None when it can."""
    if meta.applies_to == "live-only" and not _has_live_inputs(meta, topology):
        return f"needs a live read: {meta.evidence}"
    if meta.needs_properties and not topology.has_properties:
        return NO_PROPERTIES_REASON
    return None


def evaluate_subscription(
    sub: AzureSubscriptionTopology,
    topology: AzureTopology,
    seen: set[str] | None = None,
    unknowns: dict[str, Unknown] | None = None,
) -> list[Finding]:
    """Run every registered rule over one subscription.

    ``seen`` carries the deduplication register across subscriptions when the caller is
    ``evaluate``, so a tenant-wide rule that fires from each subscription lands once;
    ``unknowns`` collects the rules that answered ``NotEvaluable``.
    """
    if sub.discovery_blocked:
        return []
    register = seen if seen is not None else set()
    not_evaluable = unknowns if unknowns is not None else {}
    findings: list[Finding] = []
    for rule_id, (meta, fn) in sorted(RULES.items()):
        if _skip_reason(meta, topology):
            continue
        for emitted in fn(sub, topology):
            if isinstance(emitted, NotEvaluable):
                not_evaluable.setdefault(rule_id, Unknown(rule_id=rule_id, reason=emitted.reason))
                continue
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
    unknowns: dict[str, Unknown] = {}
    for rule_id, (meta, _) in sorted(RULES.items()):
        reason = _skip_reason(meta, topology)
        if reason:
            unknowns[rule_id] = Unknown(rule_id=rule_id, reason=reason)
    total = len(topology.subscriptions)
    for index, sub in enumerate(topology.subscriptions, start=1):
        sub_findings = evaluate_subscription(sub, topology, seen, unknowns)
        findings.extend(sub_findings)
        if progress:
            progress(index, total, sub, sub_findings)

    def count(severity: FindingSeverity) -> int:
        return sum(1 for f in findings if f.severity == severity)

    return FindingsReport(
        engagement_id=topology.engagement_id,
        schema_version=FINDINGS_SCHEMA_VERSION,
        rules_version=RULES_VERSION,
        model_version=topology.schema_version,
        findings=findings,
        unknowns=[unknowns[k] for k in sorted(unknowns)],
        total_count=len(findings),
        critical_count=count(FindingSeverity.CRITICAL),
        high_count=count(FindingSeverity.HIGH),
        medium_count=count(FindingSeverity.MEDIUM),
        low_count=count(FindingSeverity.LOW),
        review_complete=False,  # DD-009: a human sets this
        generated_at=datetime.now(UTC).isoformat(),
    )
