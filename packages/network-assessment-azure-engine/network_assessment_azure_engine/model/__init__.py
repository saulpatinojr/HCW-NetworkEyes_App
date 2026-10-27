"""Topology model: ``common`` (shared enums) and ``azure`` (the Azure classes, ``TOPOLOGY_MODEL_VERSION``)."""

from network_assessment_azure_engine.model.azure import *  # noqa: F403
from network_assessment_azure_engine.model.azure import __all__ as _azure_all
from network_assessment_azure_engine.model.common import *  # noqa: F403
from network_assessment_azure_engine.model.common import __all__ as _common_all

__all__ = [*_common_all, *_azure_all]
