"""The lab edition boundary (change set I of REFACTOR_APP.md).

The base distribution of this package reaches no cloud: no Azure SDK, no ``msal``, no
``boto3``. A lab image built from it proves that at build time and at every start, and
refuses to run when an identity endpoint or a credential variable is present. This module
is that proof; the downstream lab edition (``HCW-NetworkEyes_AddOn``) carries the same
checks against its own process, and ``python -m cna_azure_network_engine.edition`` is the
build-only lab image's ``CMD`` in the Core.

Exit codes: 0 when the boundary holds, 1 (with ``lab edition: …`` on stderr) when it does
not. Nothing here imports a cloud SDK; presence is read with ``importlib.util.find_spec``.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from collections.abc import Mapping

EDITION = "lab"
AZURE_CONNECTIVITY = "disabled-by-design"
FORBIDDEN_MODULES: tuple[str, ...] = ("azure", "msal", "boto3")
IDENTITY_ENV_VARS: tuple[str, ...] = (
    "IDENTITY_ENDPOINT",
    "MSI_ENDPOINT",
    "AZURE_CLIENT_SECRET",
    "AZURE_FEDERATED_TOKEN_FILE",
)


def importable_cloud_sdks() -> list[str]:
    """The forbidden module roots that resolve on this interpreter."""
    found: list[str] = []
    for module in FORBIDDEN_MODULES:
        try:
            spec = importlib.util.find_spec(module)
        except ImportError, ValueError:
            spec = None
        if spec is not None:
            found.append(module)
    return found


def identity_env_present(env: Mapping[str, str] | None = None) -> list[str]:
    """The identity endpoint / credential variables set in ``env`` (names, never values)."""
    source = os.environ if env is None else env
    return [name for name in IDENTITY_ENV_VARS if source.get(name, "").strip()]


def boundary_violations(env: Mapping[str, str] | None = None) -> list[str]:
    """Every reason the lab boundary does not hold; empty when it does."""
    problems = [f"{module} is importable" for module in importable_cloud_sdks()]
    present = identity_env_present(env)
    if present:
        problems.append(f"identity environment present ({', '.join(present)})")
    return problems


def assert_lab_boundary(env: Mapping[str, str] | None = None) -> None:
    """Raise ``SystemExit(1)`` with ``lab edition: …`` on stderr when the boundary fails."""
    problems = boundary_violations(env)
    if problems:
        for problem in problems:
            print(f"lab edition: {problem}", file=sys.stderr)
        raise SystemExit(1)


def main(argv: list[str] | None = None) -> int:
    """``python -m cna_azure_network_engine.edition``: 0 when no cloud SDK is importable and
    no identity variable is set, 1 otherwise."""
    del argv
    try:
        assert_lab_boundary()
    except SystemExit as exc:
        return int(exc.code or 0)
    print(f"lab edition: boundary holds (azure connectivity {AZURE_CONNECTIVITY})")
    return 0


if (
    __name__ == "__main__"
):  # pragma: no cover - exercised through the lab image and subprocess tests
    sys.exit(main())
