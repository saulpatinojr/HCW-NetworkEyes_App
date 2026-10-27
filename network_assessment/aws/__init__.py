"""The AWS extra (change set K of REFACTOR_APP.md).

``pip install network-assessment`` installs no ``boto3``; ``pip install "network-assessment[aws]"`` enables every AWS path
(discovery, Security Hub, the S3 delivery portal, Bedrock chat, the ``/discovery/*-aws``
routes). Every module that imports ``boto3`` at import time wraps it in ``try`` / ``except
ImportError`` and re-raises :data:`INSTALL_HINT`; the lazy call sites call
:func:`require_aws_extra` first. A deployment without the extra therefore fails with the
install hint instead of a bare ``ModuleNotFoundError`` — the same pattern as the engine's
``[azure]`` extra.
"""

from __future__ import annotations

import importlib.util
import sys

INSTALL_HINT = 'the AWS paths need boto3: pip install "network-assessment[aws]"'
AWS_NOT_INSTALLED = "aws_not_installed"


def aws_extra_installed() -> bool:
    """True when ``boto3`` is loaded or resolves on this interpreter (no import is performed)."""
    if "boto3" in sys.modules:
        return True
    try:
        return importlib.util.find_spec("boto3") is not None
    except ImportError, ValueError:
        return False


def require_aws_extra() -> None:
    """Raise ``ImportError`` with the install hint when the ``[aws]`` extra is absent."""
    if not aws_extra_installed():
        raise ImportError(INSTALL_HINT)


__all__ = ["AWS_NOT_INSTALLED", "INSTALL_HINT", "aws_extra_installed", "require_aws_extra"]
