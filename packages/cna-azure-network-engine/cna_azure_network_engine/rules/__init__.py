"""The typed Azure rule registry: importing this package registers every rule module."""

from cna_azure_network_engine.rules import (  # noqa: F401 — registration
    azure_bcdr,
    azure_cost,
    azure_net,
)
from cna_azure_network_engine.rules.registry import (
    NO_PROPERTIES_REASON,
    RULES,
    RULES_VERSION,
    DuplicateRuleError,
    NotEvaluable,
    Observation,
    ProgressFn,
    RuleMeta,
    evaluate,
    evaluate_subscription,
    rule,
    rule_metadata,
    rules_digest,
    rules_table,
)
from cna_azure_network_engine.rules.taxonomy import classify_traffic_direction

__all__ = [
    "NO_PROPERTIES_REASON",
    "RULES",
    "RULES_VERSION",
    "DuplicateRuleError",
    "NotEvaluable",
    "Observation",
    "ProgressFn",
    "RuleMeta",
    "classify_traffic_direction",
    "evaluate",
    "evaluate_subscription",
    "rule",
    "rule_metadata",
    "rules_digest",
    "rules_table",
]
