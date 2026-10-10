"""cna-azure-network-engine: the Azure network assessment engine.

One model (``AzureTopology``), one typed rule set (``RULES``, ``evaluate``), the topology
classifier, the Resource Graph normalizer and the Markdown/JSON renderers — installable with
pydantic alone. Live discovery lives behind the ``[azure]`` extra.
"""

from cna_azure_network_engine.classify.topology import TopologyClassification, classify_topology
from cna_azure_network_engine.findings.schema import (
    FINDINGS_SCHEMA_VERSION,
    Finding,
    FindingSeverity,
    FindingsReport,
    FrameworkMapping,
    ObservedState,
    Unknown,
)
from cna_azure_network_engine.model.azure import (
    TOPOLOGY_MODEL_VERSION,
    AzureSubscriptionTopology,
    AzureTopology,
)
from cna_azure_network_engine.normalize.resource_graph import (
    normalize_resource_graph,
    rows_from_document,
)
from cna_azure_network_engine.report.jsonreport import render_json
from cna_azure_network_engine.report.markdown import render_markdown
from cna_azure_network_engine.rules import RULES, RULES_VERSION, evaluate, rules_digest, rules_table

__version__ = "0.1.0"

__all__ = [
    "FINDINGS_SCHEMA_VERSION",
    "RULES",
    "RULES_VERSION",
    "TOPOLOGY_MODEL_VERSION",
    "AzureSubscriptionTopology",
    "AzureTopology",
    "Finding",
    "FindingSeverity",
    "FindingsReport",
    "FrameworkMapping",
    "ObservedState",
    "TopologyClassification",
    "Unknown",
    "__version__",
    "classify_topology",
    "evaluate",
    "normalize_resource_graph",
    "render_json",
    "render_markdown",
    "rows_from_document",
    "rules_digest",
    "rules_table",
]
