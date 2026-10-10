"""Topology models: ``common`` (shared enums), ``azure`` and ``aws``.

This package re-exports the shared enums and the Azure model. The AWS model is imported
explicitly from ``cna.core.topology.aws`` so an Azure-only consumer never loads it.
"""

from cna.core.topology.azure import *  # noqa: F403
from cna.core.topology.azure import __all__ as _azure_all
from cna.core.topology.common import *  # noqa: F403
from cna.core.topology.common import __all__ as _common_all

__all__ = [*_common_all, *_azure_all]
