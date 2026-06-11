"""Universal findings schema.

DD-002: observed_state is REQUIRED — only what was discovered, no assumptions.
DD-003: recommendation sourced from MCP servers, not custom prompts.
"""

import enum
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator

FINDINGS_SCHEMA_VERSION = "1.0.0"


class FindingSeverity(enum.StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFORMATIONAL = "informational"


class FindingStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    SUPPRESSED = "suppressed"


class ObservedState(BaseModel):
    fact: str
    evidence_ref: str


class FrameworkMapping(BaseModel):
    framework: str  # e.g. "CIS AWS Foundations Benchmark"
    version: str | None = None
    pillar: str | None = None
    control: str | None = None
    control_id: str | None = None
    control_name: str | None = None
    alignment: str | None = None


class FindingRecommendation(BaseModel):
    """A vendor recommendation sourced from an MCP server or offline library."""

    source: str  # e.g. "AWS MCP Server (awslabs/mcp)" or "CNA Platform"
    text: str
    reference_url: str = ""


class Finding(BaseModel):
    id: str | None = None
    rule_id: str | None = None
    severity: FindingSeverity  # critical | high | medium | low | informational
    platform: str | None = None  # aws | azure | both
    region: str | None = None
    category: str | None = None
    title: str
    description: str | None = None
    resource_id: str | None = None
    resource_type: str | None = None
    account_id: str | None = None
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
    recommendations: list["FindingRecommendation"] = Field(default_factory=list)  # DD-003: from MCP
    status: FindingStatus | None = None
    data_confidence: str = "HIGH"  # HIGH | MEDIUM | LOW
    recommendation_source: str | None = None  # MCP server reference URL (legacy)
    recommendation: str | None = None  # From MCP — not our opinion (legacy flat field)
    # Traffic plane: "east_west" | "north_south" | "management" | "" (unclassified).
    # Populated by cna.core.finding_taxonomy.classify_traffic_direction.
    traffic_direction: str = ""
    # Estimated monthly cost impact in USD (FinOps findings). Static-price
    # estimate — must be marked [VERIFY] wherever it is rendered.
    est_monthly_cost_usd: float | None = None
    human_reviewed: bool = False  # DD-009: must be True before report
    human_notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    version: str = FINDINGS_SCHEMA_VERSION


class FindingsReport(BaseModel):
    engagement_id: str
    schema_version: str = FINDINGS_SCHEMA_VERSION
    findings: list[Finding]
    total_count: int
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    review_complete: bool = False  # DD-009
    generated_at: str
