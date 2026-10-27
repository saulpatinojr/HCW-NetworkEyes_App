"""Observed-state enforcer — re-exported from the engine package (REFACTOR_APP.md change set C).

The class and its hedge-word list live in ``network_assessment_azure_engine.findings.enforcer``; this
module keeps the monorepo's import path.
"""

from network_assessment_azure_engine.findings.enforcer import (
    ObservedStateEnforcer,
    ObservedStateViolation,
)

__all__ = ["ObservedStateEnforcer", "ObservedStateViolation"]
