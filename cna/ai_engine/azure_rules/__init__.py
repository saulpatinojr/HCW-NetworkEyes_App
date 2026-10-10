"""Azure rule registry: one typed, versioned rule set evaluated by ``evaluate(topology)``.

Importing this package registers every rule module; ``RULES`` is complete once the import
returns. See ``registry.py`` for the contract.
"""

from cna.ai_engine.azure_rules import azure_bcdr, azure_cost, azure_net  # noqa: F401 — registration
from cna.ai_engine.azure_rules.registry import (
    RULES,
    RULES_VERSION,
    DuplicateRuleError,
    Observation,
    RuleMeta,
    evaluate,
    evaluate_subscription,
    rule,
    rule_metadata,
    rules_digest,
)

__all__ = [
    "RULES",
    "RULES_VERSION",
    "DuplicateRuleError",
    "Observation",
    "RuleMeta",
    "evaluate",
    "evaluate_subscription",
    "rule",
    "rule_metadata",
    "rules_digest",
]
