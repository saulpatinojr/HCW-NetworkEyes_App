"""Post-discovery network analysis — pure functions over topology checkpoints.

Phase B additions:
  topology_classifier — tenant network pattern (mesh | hub_spoke | vwan | isolated)
  finops_signals      — AZ-COST-* findings with estimated monthly cost
  bcdr_signals        — AZ-BCDR-* resilience findings
"""

from cna.modules.network.analysis.bcdr_signals import generate_bcdr_findings
from cna.modules.network.analysis.finops_signals import generate_finops_findings
from cna.modules.network.analysis.topology_classifier import (
    TopologyClassification,
    classify_topology,
)

__all__ = [
    "TopologyClassification",
    "classify_topology",
    "generate_bcdr_findings",
    "generate_finops_findings",
]
