"""Accept the old ``CNA_<NAME>`` setting names for a while (rename step 3 of 4, owner order 2026-10-27).

Every setting used to be called ``CNA_<NAME>``; it is now ``NETWORK_ASSESSMENT_<NAME>``. A deployment that still sets the old
name keeps working: when the package is imported, each old name whose new name has no value is copied to the new name. A new
name that has a value always wins. A blank new name does not hide a non-blank old one, so a template that leaves the new name
empty cannot switch off a protection that the old name still asks for. Nothing is logged, and no value is ever returned or
printed.

This works in one direction only. An image built before this change reads only the old names, so while old and new images run
side by side, and when rolling back, set both names to the same value.

To end the fallback, delete this module and the call in ``network_assessment/__init__.py`` and the matching ones in the web
app's ``lib/legacy-env.ts`` and ``instrumentation.ts``. The worker needs nothing: it imports this package.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping

LEGACY_PREFIX = "CNA_"
PREFIX = "NETWORK_ASSESSMENT_"


def adopt_legacy_environment(environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Copy each ``CNA_<NAME>`` to ``NETWORK_ASSESSMENT_<NAME>`` unless the new name already has a value.

    Returns the new names it set, sorted. Never returns, logs or prints a value.
    """
    env = os.environ if environ is None else environ
    adopted: list[str] = []
    for key in sorted(env):
        if not key.startswith(LEGACY_PREFIX) or len(key) == len(LEGACY_PREFIX):
            continue
        new_name = PREFIX + key[len(LEGACY_PREFIX) :]
        current = env.get(new_name)
        if current:  # a new name that has a value always wins
            continue
        # unset: copy the old value; blank: replace it only with a non-blank old value
        if current is None or env[key]:
            env[new_name] = env[key]
            adopted.append(new_name)
    return adopted
