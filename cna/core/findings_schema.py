"""Universal findings schema — the monorepo's view of the engine's contract.

The contract (``ObservedState`` with its ``state``, ``Finding`` with ``rule_version``,
``remediation`` and ``learn_url``, ``Unknown``, ``FindingsReport`` with ``rules_version``,
``model_version`` and ``unknowns``) lives in ``cna_azure_network_engine.findings.schema``
(REFACTOR_APP.md section 9). This module subclasses it with the fields only the monorepo's web
tier, report engine and review flow read: MCP recommendations (DD-003), the review flags
(DD-009), the legacy flat recommendation and the static cost estimate the FinOps annotation
attaches. ``Finding.from_engine`` upcasts an engine finding into this shape.

DD-002: observed_state is REQUIRED — only what was discovered, no assumptions.
DD-003: recommendation sourced from MCP servers, not custom prompts.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, Field

from cna_azure_network_engine.findings.schema import (
    FINDINGS_SCHEMA_VERSION,
    EvidenceState,
    FindingSeverity,
    FrameworkMapping,
    ObservedState,
    Unknown,
)
from cna_azure_network_engine.findings.schema import Finding as EngineFinding
from cna_azure_network_engine.findings.schema import FindingsReport as EngineFindingsReport
from cna_azure_network_engine.model.azure import TOPOLOGY_MODEL_VERSION
from cna_azure_network_engine.rules.registry import RULES_VERSION

__all__ = [
    "FINDINGS_SCHEMA_VERSION",
    "EngineFinding",
    "EngineFindingsReport",
    "EvidenceState",
    "Finding",
    "FindingRecommendation",
    "FindingSeverity",
    "FindingStatus",
    "FindingsReport",
    "FrameworkMapping",
    "ObservedState",
    "Unknown",
]

_PLATFORM_SOURCE = "NetworkEyes"


class FindingStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    SUPPRESSED = "suppressed"


class FindingRecommendation(BaseModel):
    """A vendor recommendation sourced from an MCP server or offline library."""

    source: str  # e.g. "AWS MCP Server (awslabs/mcp)" or "NetworkEyes"
    text: str
    reference_url: str = ""


class Finding(EngineFinding):
    """The engine's finding plus the monorepo's web-tier and review fields."""

    recommendations: list[FindingRecommendation] = Field(default_factory=list)  # DD-003: from MCP
    status: FindingStatus | None = None
    data_confidence: str = "HIGH"  # HIGH | MEDIUM | LOW
    recommendation_source: str | None = None  # MCP server reference URL (legacy)
    recommendation: str | None = None  # legacy flat field; the engine's remediation lands here
    # Estimated monthly cost impact in USD (FinOps findings). Static-price estimate attached
    # by cna.modules.network.analysis.finops_signals — marked [VERIFY] wherever it is rendered.
    est_monthly_cost_usd: float | None = None
    human_reviewed: bool = False  # DD-009: must be True before report
    human_notes: str | None = None

    @classmethod
    def from_engine(cls, finding: EngineFinding) -> Finding:
        """Upcast an engine finding: status OPEN, the remediation as the flat recommendation."""
        if isinstance(finding, cls):
            return finding
        recommendations = (
            [
                FindingRecommendation(
                    source=_PLATFORM_SOURCE,
                    text=finding.remediation,
                    reference_url=finding.learn_url or "",
                )
            ]
            if finding.remediation
            else []
        )
        return cls.model_validate(
            {
                **finding.model_dump(),
                "status": FindingStatus.OPEN,
                "recommendation": finding.remediation,
                "recommendations": recommendations,
            }
        )


class FindingsReport(EngineFindingsReport):
    """The engine's report over the monorepo's findings; versions default to the registry's."""

    rules_version: str = RULES_VERSION
    model_version: str = TOPOLOGY_MODEL_VERSION
    findings: list[Finding]
