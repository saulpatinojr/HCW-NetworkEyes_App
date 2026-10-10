"""Live discovery (change set D of REFACTOR_APP.md) — needs the ``[azure]`` extra.

The base distribution carries no Azure SDK by design; importing this package without the
extra fails with the install hint instead of an opaque ``ModuleNotFoundError``. The
Resource Graph and live collectors land here under change set D.
"""

from __future__ import annotations

import importlib.util

_INSTALL_HINT = 'live discovery needs the Azure SDKs: pip install "cna-azure-network-engine[azure]"'


def require_azure_extra() -> None:
    """Raise ``ImportError`` with the install hint when the ``[azure]`` extra is absent."""
    if importlib.util.find_spec("azure") is None:
        raise ImportError(_INSTALL_HINT)


__all__ = ["require_azure_extra"]
