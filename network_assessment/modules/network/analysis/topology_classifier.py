"""Topology classifier — re-exported from the engine package (REFACTOR_APP.md change set C).

``classify_topology`` and ``TopologyClassification`` live in
``network_assessment_azure_engine.classify.topology``; this module keeps the monorepo's import path.
"""

from network_assessment_azure_engine.classify.topology import (
    TopologyClassification,
    classify_topology,
)

__all__ = ["TopologyClassification", "classify_topology"]
