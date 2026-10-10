"""Azure topology model — re-exported from the engine package (REFACTOR_APP.md change set C).

The classes live in ``cna_azure_network_engine.model.azure``; this module keeps the monorepo's
import path and the ``AZURE_TOPOLOGY_VERSION`` name (an alias of the engine's
``TOPOLOGY_MODEL_VERSION``). This module imports nothing from the AWS model.
"""

from cna_azure_network_engine.model.azure import *  # noqa: F403
from cna_azure_network_engine.model.azure import TOPOLOGY_MODEL_VERSION as AZURE_TOPOLOGY_VERSION
from cna_azure_network_engine.model.azure import __all__ as _engine_all
from cna_azure_network_engine.model.common import SubnetType  # noqa: F401 — kept as an attribute

__all__ = [*_engine_all, "AZURE_TOPOLOGY_VERSION"]
