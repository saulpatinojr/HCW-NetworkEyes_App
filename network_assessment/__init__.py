"""NetworkEyes — Cloud Network Assessment.

The version is derived from the installed package metadata (pyproject.toml
is the single source of truth). The literal fallback covers running from a
source checkout where the package is not installed.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

from network_assessment._legacy_env import adopt_legacy_environment

# Accept the old CNA_<NAME> setting names for a while: runs before any module reads its settings.
adopt_legacy_environment()

try:
    __version__ = _pkg_version("network-assessment")
except PackageNotFoundError:  # running from source without an installed dist
    __version__ = "0.8.0b0"
