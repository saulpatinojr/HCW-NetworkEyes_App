"""Topology model: ``common`` (shared enums) and ``azure`` (the Azure classes, ``TOPOLOGY_MODEL_VERSION``)."""

from cna_azure_network_engine.model.azure import *  # noqa: F403
from cna_azure_network_engine.model.azure import __all__ as _azure_all
from cna_azure_network_engine.model.common import *  # noqa: F403
from cna_azure_network_engine.model.common import __all__ as _common_all

__all__ = [*_common_all, *_azure_all]
