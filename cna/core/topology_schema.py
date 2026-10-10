"""Deprecated: import from cna.core.topology.azure / .aws / .common instead.

Kept for one release so existing imports keep working (TODO.md T-719 removes it).
"""

import warnings

from cna.core.topology.aws import *  # noqa: F403
from cna.core.topology.aws import __all__ as _aws_all
from cna.core.topology.azure import *  # noqa: F403
from cna.core.topology.azure import AZURE_TOPOLOGY_VERSION as TOPOLOGY_SCHEMA_VERSION
from cna.core.topology.azure import __all__ as _azure_all
from cna.core.topology.common import *  # noqa: F403
from cna.core.topology.common import __all__ as _common_all

__all__ = [*_common_all, *_aws_all, *_azure_all, "TOPOLOGY_SCHEMA_VERSION"]

warnings.warn(
    "cna.core.topology_schema is deprecated; import cna.core.topology.azure or .aws",
    DeprecationWarning,
    stacklevel=2,
)
