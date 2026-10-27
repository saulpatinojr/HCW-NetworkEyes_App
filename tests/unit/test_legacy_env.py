"""The old ``CNA_<NAME>`` setting names are still accepted for a while (rename step 3 of 4, owner order 2026-10-27).

Every setting is now ``NETWORK_ASSESSMENT_<NAME>``. A deployment that still sets the old name keeps working because the
package copies it to the new name when it is imported; the new name wins when both are set. The old prefix appears in no
other code or configuration file, which the guard at the end checks.
"""

from __future__ import annotations

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


def test_the_new_name_wins_when_both_are_set() -> None:
    env = {"CNA_AI_MODE": "saas", "NETWORK_ASSESSMENT_AI_MODE": "byo-api"}
    assert adopt_legacy_environment(env) == []
    assert env["NETWORK_ASSESSMENT_AI_MODE"] == "byo-api"


def test_an_empty_new_value_counts_as_set() -> None:
    env = {"CNA_LOG_LEVEL": "DEBUG", "NETWORK_ASSESSMENT_LOG_LEVEL": ""}
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


def test_importing_the_package_adopts_the_old_names_in_a_fresh_process() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith(("CNA_", "NETWORK_ASSESSMENT_"))}
    env["CNA_STALE_JOB_MINUTES"] = "45"
    code = (
        "import os, network_assessment; "
        "print(os.environ.get('NETWORK_ASSESSMENT_STALE_JOB_MINUTES'), os.environ.get('CNA_STALE_JOB_MINUTES'))"
    )
    # run from the repository root, without -I, so that the working tree's package is the one imported
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr[-1500:]
    assert result.stdout.split() == ["45", "45"]


# --- the guard: the old prefix lives only in the shims, their tests and the prose -----------------------------------

OLD_PREFIX = re.compile(r"\bCNA_[A-Z]")
ALLOWED = frozenset(
    {
        "network_assessment/_legacy_env.py",
        "tests/unit/test_legacy_env.py",
        "apps/network-assessment-web/lib/legacy-env.ts",
        "apps/network-assessment-web/lib/legacy-env.test.ts",
        "apps/network-assessment-web/instrumentation.ts",
        ".env.example",
        "apps/network-assessment-web/.env.example",
        "CHANGELOG.md",
        "CNA-0.90-updates.md",
    }
)


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
        if name in ALLOWED or name.endswith(".md") or name.endswith("package-lock.json"):
            continue
        try:
            data = (REPO_ROOT / name).read_bytes()
        except FileNotFoundError:  # a tracked file deleted in the working tree
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        hits.extend(
            f"{name}:{text.count(chr(10), 0, m.start()) + 1}" for m in OLD_PREFIX.finditer(text)
        )
    assert not hits, f"the old CNA_ setting prefix is back outside the shims: {hits}"
