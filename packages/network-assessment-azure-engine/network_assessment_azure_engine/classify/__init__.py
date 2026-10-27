"""Topology classifier: the tenant network pattern (vwan | hub_spoke | mesh | isolated)."""

from network_assessment_azure_engine.classify.topology import (
    TopologyClassification,
    classify_topology,
)

__all__ = ["TopologyClassification", "classify_topology"]
