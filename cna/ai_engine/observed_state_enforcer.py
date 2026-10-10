"""Observed-state enforcer — re-exported from the engine package (REFACTOR_APP.md change set C).

The class and its hedge-word list live in ``cna_azure_network_engine.findings.enforcer``; this
module keeps the monorepo's import path.
"""

from cna_azure_network_engine.findings.enforcer import ObservedStateEnforcer, ObservedStateViolation

__all__ = ["ObservedStateEnforcer", "ObservedStateViolation"]
