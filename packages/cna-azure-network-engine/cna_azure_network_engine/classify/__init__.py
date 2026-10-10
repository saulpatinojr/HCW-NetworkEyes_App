"""Topology classifier: the tenant network pattern (vwan | hub_spoke | mesh | isolated)."""

from cna_azure_network_engine.classify.topology import TopologyClassification, classify_topology

__all__ = ["TopologyClassification", "classify_topology"]
