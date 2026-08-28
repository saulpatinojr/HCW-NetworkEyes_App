"""CNA — Cloud Network Assessment Platform.

The version is derived from the installed package metadata (pyproject.toml
is the single source of truth). The literal fallback covers running from a
source checkout where the package is not installed.
"""

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("cna")
except PackageNotFoundError:  # running from source without an installed dist
    __version__ = "0.8.0b0"
