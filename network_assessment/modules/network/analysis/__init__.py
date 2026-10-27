"""Post-discovery network analysis — pure functions over topology checkpoints.

The Azure rules, the classifier and the taxonomy live in the engine package
(``network_assessment_azure_engine``); these modules evaluate them and add the monorepo's own
annotations:
  azure_findings      — evaluate_azure: every rule, monorepo findings plus unknowns
  topology_classifier — tenant network pattern (mesh | hub_spoke | vwan | isolated)
  finops_signals      — AZ-COST-* findings with the static monthly cost estimate
  bcdr_signals        — AZ-BCDR-* resilience findings
"""

from network_assessment.modules.network.analysis.azure_findings import (
    AzureEvaluation,
    evaluate_azure,
)
from network_assessment.modules.network.analysis.bcdr_signals import generate_bcdr_findings
from network_assessment.modules.network.analysis.finops_signals import generate_finops_findings
from network_assessment.modules.network.analysis.topology_classifier import (
    TopologyClassification,
    classify_topology,
)

__all__ = [
    "AzureEvaluation",
    "TopologyClassification",
    "classify_topology",
    "evaluate_azure",
    "generate_bcdr_findings",
    "generate_finops_findings",
]
