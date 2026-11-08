"""Observed-state enforcer — re-exported from the engine package (REFACTOR_APP.md change set C).

The class, its hedge-word list and the rule for which customer identifiers can excuse a hedge
word (``is_maskable``) live in ``network_assessment_azure_engine.findings.enforcer``; this module
keeps the monorepo's import path, so the AWS analysis and the Azure engine judge text the same
way. ``HEDGED_WORDING_REASON`` is the engine's fixed, content-free ``unknowns[]`` reason for a
withheld finding, reused by the AWS analysis.
"""

from network_assessment_azure_engine.findings.enforcer import (
    ObservedStateEnforcer,
    ObservedStateViolation,
    is_maskable,
)
from network_assessment_azure_engine.rules import HEDGED_WORDING_REASON

__all__ = [
    "HEDGED_WORDING_REASON",
    "ObservedStateEnforcer",
    "ObservedStateViolation",
    "is_maskable",
]
