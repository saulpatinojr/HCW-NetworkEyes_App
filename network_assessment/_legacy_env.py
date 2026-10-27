"""Accept the old ``CNA_<NAME>`` setting names for a while (rename step 3 of 4, owner order 2026-10-27).

Every setting used to be called ``CNA_<NAME>``; it is now ``NETWORK_ASSESSMENT_<NAME>``. A deployment that still sets the old
name keeps working: when the package is imported, each old name whose new name is not set is copied to the new name. When
both are set, the new name wins, even if its value is empty. Nothing is logged, and no value is ever returned or printed.

To end the fallback, delete this module and the call in ``network_assessment/__init__.py`` (and the matching ones in the web
app's ``lib/legacy-env.ts`` and the worker's ``main.py``).
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

LEGACY_PREFIX = "CNA_"
PREFIX = "NETWORK_ASSESSMENT_"


def adopt_legacy_environment(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Copy each ``CNA_<NAME>`` to ``NETWORK_ASSESSMENT_<NAME>`` when the new name is not set.

    Returns the new names it set, sorted. Never returns, logs or prints a value.
    """
    env = os.environ if environ is None else environ
    adopted: list[str] = []
    for key in sorted(env):
        if not key.startswith(LEGACY_PREFIX) or len(key) == len(LEGACY_PREFIX):
            continue
        new_name = PREFIX + key[len(LEGACY_PREFIX) :]
        if new_name not in env:
            env[new_name] = env[key]
            adopted.append(new_name)
    return adopted
