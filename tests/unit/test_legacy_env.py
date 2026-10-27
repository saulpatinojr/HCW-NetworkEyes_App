"""The old ``CNA_<NAME>`` setting names are still accepted for a while (rename step 3 of 4, owner order 2026-10-27).

Every setting is now ``NETWORK_ASSESSMENT_<NAME>``. A deployment that still sets the old name keeps working because the
package copies it to the new name when it is imported; a new name that has a value wins, and a blank new name does not
hide a non-blank old one. The old prefix appears in no other code or configuration file, which the guard at the end checks.
"""

from __future__ import annotations

import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from network_assessment._legacy_env import LEGACY_PREFIX, PREFIX, adopt_legacy_environment

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_an_old_name_is_copied_to_the_new_name_when_the_new_one_is_not_set() -> None:
    env = {"CNA_API_TOKEN": "a-token"}
    assert adopt_legacy_environment(env) == ["NETWORK_ASSESSMENT_API_TOKEN"]
    assert env["NETWORK_ASSESSMENT_API_TOKEN"] == "a-token"
    assert env["CNA_API_TOKEN"] == "a-token"


def test_a_new_name_that_has_a_value_wins_over_the_old_one() -> None:
    env = {"CNA_AI_MODE": "saas", "NETWORK_ASSESSMENT_AI_MODE": "byo-api"}
    assert adopt_legacy_environment(env) == []
    assert env["NETWORK_ASSESSMENT_AI_MODE"] == "byo-api"


def test_a_blank_new_name_does_not_hide_a_non_blank_old_one() -> None:
    env = {"CNA_APPLIANCE_CLOUD": "azure", "NETWORK_ASSESSMENT_APPLIANCE_CLOUD": ""}
    assert adopt_legacy_environment(env) == ["NETWORK_ASSESSMENT_APPLIANCE_CLOUD"]
    assert env["NETWORK_ASSESSMENT_APPLIANCE_CLOUD"] == "azure"


def test_a_blank_new_name_stays_blank_when_the_old_one_is_blank_too() -> None:
    env = {"CNA_LOG_LEVEL": "", "NETWORK_ASSESSMENT_LOG_LEVEL": ""}
    assert adopt_legacy_environment(env) == []
    assert env["NETWORK_ASSESSMENT_LOG_LEVEL"] == ""


def test_names_without_the_old_prefix_and_the_bare_prefix_are_ignored() -> None:
    env = {"OTHER_CNA_THING": "x", "CNA_": "bare", "XCNA_API_TOKEN": "y", "AZURE_TENANT_ID": "z"}
    assert adopt_legacy_environment(env) == []
    assert not [k for k in env if k.startswith(PREFIX)]


def test_it_returns_sorted_names_and_never_a_value() -> None:
    env = {"CNA_B": "secret-b", "CNA_A": "secret-a"}
    names = adopt_legacy_environment(env)
    assert names == ["NETWORK_ASSESSMENT_A", "NETWORK_ASSESSMENT_B"]
    assert "secret" not in repr(names)


def test_the_prefixes_are_the_documented_ones() -> None:
    assert (LEGACY_PREFIX, PREFIX) == ("CNA_", "NETWORK_ASSESSMENT_")


# --- fresh processes: the shim runs before anything reads a setting --------------------------------------------------


def _fresh(code: str, extra_env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith(("CNA_", "NETWORK_ASSESSMENT_", "AZURE_")) and k != "DATABASE_URL"
    }
    env.update(extra_env)
    # run from the repository root, without -I, so that the working tree's package is the one imported
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )


def test_importing_the_package_adopts_the_old_names_in_a_fresh_process() -> None:
    code = (
        "import os, network_assessment; "
        "print(os.environ.get('NETWORK_ASSESSMENT_STALE_JOB_MINUTES'), os.environ.get('CNA_STALE_JOB_MINUTES'))"
    )
    result = _fresh(code, {"CNA_STALE_JOB_MINUTES": "45"})
    assert result.returncode == 0, result.stderr[-1500:]
    assert result.stdout.split() == ["45", "45"]


API_MAIN = (REPO_ROOT / "apps" / "network-assessment-api" / "main.py").as_posix()
START_THE_API = (
    "import importlib.util as u; "
    f"s = u.spec_from_file_location('api_main_probe', {API_MAIN!r}); "
    "m = u.module_from_spec(s); s.loader.exec_module(m); print('started')"
)
needs_the_api_extra = pytest.mark.skipif(
    any(importlib.util.find_spec(m) is None for m in ("fastapi", "psycopg2", "jwt")),
    reason="the API extra (fastapi, psycopg2, pyjwt) is not installed",
)
_ANY_VALUE = "placeholder"
_APPLIANCE = {
    "CNA_APPLIANCE_CLOUD": "azure",
    "DATABASE_URL": "postgresql://user@db.internal/db",
    "CNA_API_TOKEN": "x" * 32,
}


@needs_the_api_extra
def test_an_appliance_set_up_with_the_old_names_still_starts() -> None:
    result = _fresh(START_THE_API, _APPLIANCE)
    assert result.returncode == 0, result.stderr[-1500:]
    assert "started" in result.stdout


@needs_the_api_extra
def test_an_appliance_set_up_with_the_old_names_still_refuses_a_profile() -> None:
    result = _fresh(START_THE_API, {**_APPLIANCE, "CNA_PROFILE": "test"})
    assert result.returncode != 0
    assert "NETWORK_ASSESSMENT_PROFILE is not accepted" in result.stderr


@needs_the_api_extra
def test_an_appliance_set_up_with_the_old_names_still_refuses_to_start_without_a_token() -> None:
    settings = {k: v for k, v in _APPLIANCE.items() if k != "CNA_API_TOKEN"}
    result = _fresh(START_THE_API, settings)
    assert result.returncode != 0
    assert "refusing to start" in result.stderr


@needs_the_api_extra
def test_an_appliance_set_up_with_the_old_names_still_refuses_a_client_secret() -> None:
    # the variable is refused by its name, whatever its value
    result = _fresh(START_THE_API, {**_APPLIANCE, "AZURE_CLIENT_SECRET": _ANY_VALUE})
    assert result.returncode != 0
    assert "AZURE_CLIENT_SECRET" in result.stderr


# --- the guard: the old prefix lives only in the shims, their tests and the prose -----------------------------------

# the old prefix after anything that is not a letter or digit, so a name inside a longer one (`OTHER_CNA_X`) counts, and a
# name that is built by joining strings
OLD_PREFIX = re.compile(r"(?<![A-Za-z0-9])CNA_")
# the old short name, built from pieces so that the label guard in test_package_name.py can scan this file
_OLD = "C" + "NA"
OLD_PREFIX_JOINED = re.compile(r"""["']""" + _OLD + r"""["']\s*\+\s*["']_""")
ALLOWED = frozenset(
    {
        "network_assessment/__init__.py",
        "network_assessment/_legacy_env.py",
        "tests/unit/test_legacy_env.py",
        "apps/network-assessment-web/lib/legacy-env.ts",
        "apps/network-assessment-web/lib/legacy-env.test.ts",
        "apps/network-assessment-web/instrumentation.ts",
        ".env.example",
        "apps/network-assessment-web/.env.example",
    }
)
HISTORY = frozenset({"CHANGELOG.md"})


def test_the_old_setting_prefix_is_only_in_the_shims_and_the_dated_prose() -> None:
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("needs a git checkout and the git program")
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode("utf-8", errors="replace")
    names = [n for n in tracked.split("\0") if n]
    assert len(names) > 100, "the scan lost its file list"
    hits: list[str] = []
    for name in names:
        if (
            name in ALLOWED
            or name in HISTORY
            or name.endswith(".md")
            or name.endswith("package-lock.json")
        ):
            continue
        try:
            data = (REPO_ROOT / name).read_bytes()
        except FileNotFoundError:  # a tracked file deleted in the working tree
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for pattern in (OLD_PREFIX, OLD_PREFIX_JOINED):
            hits.extend(
                f"{name}:{text.count(chr(10), 0, m.start()) + 1}" for m in pattern.finditer(text)
            )
    assert not hits, f"the old CNA_ setting prefix is back outside the shims: {hits}"


def test_the_guard_catches_the_forms_a_plain_name_search_misses() -> None:
    for text in (
        "CNA_API_TOKEN",
        "process.env.CNA_(?!BUILD_SHA)",  # a regular expression that names the prefix
        'f"CNA_{name}"',
        "`CNA_${name}`",
        "NEXT_PUBLIC_CNA_X",
        "CNA_1",
    ):
        assert OLD_PREFIX.search(text), text
    assert OLD_PREFIX_JOINED.search(f'"{_OLD}" + "_API"')
    assert not OLD_PREFIX.search("XCNA_API_TOKEN")
