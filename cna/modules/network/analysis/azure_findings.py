"""Azure findings for the monorepo: the engine's ``evaluate`` plus the monorepo's annotations.

The engine (``cna_azure_network_engine``) evaluates the typed rule registry over a topology and
returns engine findings and the rules it could not answer. The monorepo's callers — the CLI's
``AnalysisEngine``, the API's Azure discovery runner, the FinOps/BC-DR generators — need the
monorepo's ``Finding`` (MCP recommendations, review flags, the static cost estimate), so this
module upcasts every finding, attaches the cost estimates and keeps the ``unknowns`` beside
them. Pure: no store, no I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from cna.core.findings_schema import Finding, Unknown
from cna.core.topology.azure import AzureTopology
from cna.modules.network.analysis.finops_signals import attach_cost_estimates
from cna_azure_network_engine.rules import RULES as ENGINE_RULES
from cna_azure_network_engine.rules import RULES_VERSION as ENGINE_RULES_VERSION
from cna_azure_network_engine.rules import ProgressFn, evaluate

RULES = ENGINE_RULES
RULES_VERSION = ENGINE_RULES_VERSION


@dataclass
class AzureEvaluation:
    findings: list[Finding] = field(default_factory=list)
    unknowns: list[Unknown] = field(default_factory=list)


def evaluate_azure(
    topology: AzureTopology, *, progress: ProgressFn | None = None
) -> AzureEvaluation:
    """Evaluate every registered rule; return the monorepo's findings and the unknowns."""
    report = evaluate(topology, progress=progress)
    findings = [Finding.from_engine(f) for f in report.findings]
    attach_cost_estimates(topology, findings)
    return AzureEvaluation(findings=findings, unknowns=list(report.unknowns))
