"""Findings contract of the engine (REFACTOR_APP.md section 9).

DD-002: ``observed_state`` is required — only what was discovered, no assumptions — and now
says how it was established (``state``: observed, unknown, not-applicable). A ``Finding``
carries its rule's ``rule_version``, ``remediation`` and ``learn_url``; a ``FindingsReport``
carries the ``rules_version`` and ``model_version`` it was produced with and the rules it
could not answer (``unknowns``).

The web-tier fields of the monorepo's finding (MCP recommendations, review flags, the static
cost estimate) are not part of this contract; the monorepo subclasses ``Finding`` and
``FindingsReport`` to add them (``cna.core.findings_schema``). Field names serialise in
snake_case by default and in camelCase with ``by_alias=True``, which is what the downstream
lab edition's API emits.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

FINDINGS_SCHEMA_VERSION = "1.1.0"

EvidenceState = Literal["observed", "unknown", "not-applicable"]


class FindingSeverity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class ObservedState(_Camel):
    state: EvidenceState = "observed"
    fact: str
    evidence_ref: str


class FrameworkMapping(_Camel):
    framework: str  # e.g. "CIS Microsoft Azure Foundations Benchmark"
    version: str | None = None
    pillar: str | None = None
    control: str | None = None
    control_id: str | None = None
    control_name: str | None = None
    alignment: str | None = None


class Finding(_Camel):
    id: str | None = None
    rule_id: str | None = None
    rule_version: int = 1
    severity: FindingSeverity  # critical | high | medium | low | informational
    platform: str | None = "azure"
    region: str | None = None
    category: str | None = None
    title: str
    description: str | None = None
    resource_id: str | None = None
    resource_type: str | None = None
    account_id: str | None = Field(default=None, alias="subscriptionId")
    observed_state: ObservedState  # DD-002: ONLY what was discovered — no assumptions

    @field_validator("observed_state", mode="before")
    @classmethod
    def _coerce_observed_state(cls, v: Any) -> Any:
        """Accept a plain string for observed_state by wrapping it in ObservedState."""
        if isinstance(v, str):
            return ObservedState(fact=v, evidence_ref="")
        return v

    affected_resources: list[str] = Field(default_factory=list)
    framework_mappings: list[FrameworkMapping] = Field(default_factory=list)
    remediation: str | None = None
    learn_url: str | None = None
    # Traffic plane: "east_west" | "north_south" | "management" | "" (unclassified).
    traffic_direction: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: str = FINDINGS_SCHEMA_VERSION


class Unknown(_Camel):
    """A rule that could not be evaluated over this input, and why."""

    rule_id: str
    reason: str


class FindingsReport(_Camel):
    engagement_id: str | None = None
    schema_version: str = FINDINGS_SCHEMA_VERSION
    rules_version: str
    model_version: str
    findings: list[Finding]
    unknowns: list[Unknown] = Field(default_factory=list)
    total_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    review_complete: bool = False  # DD-009
    generated_at: str
