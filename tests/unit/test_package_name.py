"""The Python package is `network_assessment` (rename step A1, owner order 2026-10-27).

The package, the distribution and the command used to be called `cna`. The old command still works for now, as an
alias; nothing else keeps the old name, and no Python file may import it.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
OLD_IMPORT = re.compile(r"(?m)^\s*(?:from|import) cna\b")
# a dotted module path inside a string, as in a patch target or an import_module call
OLD_DOTTED = re.compile(r"""["']cna[.][a-z_]""")


def test_the_package_imports_under_its_new_name() -> None:
    module = importlib.import_module("network_assessment")
    assert Path(module.__file__).resolve().parent == REPO_ROOT / "network_assessment"


def test_the_old_package_name_does_not_import() -> None:
    # the directory may survive as an untracked __pycache__ on a developer checkout; its package marker may not
    assert not (REPO_ROOT / "cna" / "__init__.py").exists()


def test_no_tracked_python_file_imports_the_old_package_name() -> None:
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("needs a git checkout and the git program")
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z", "*.py"],
        capture_output=True,
        check=True,
    ).stdout.decode("utf-8")
    names = [n for n in tracked.split("\0") if n]
    assert len(names) > 100, "the scan lost its file list"
    offenders = [
        n
        for n in names
        if (REPO_ROOT / n).exists()
        and (
            (text := (REPO_ROOT / n).read_text(encoding="utf-8", errors="replace"))
            and (OLD_IMPORT.search(text) or OLD_DOTTED.search(text))
        )
    ]
    assert not offenders, f"these files still import the old package name: {offenders}"


def test_the_distribution_and_both_commands_point_at_the_same_function() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "network-assessment"
    scripts = project["scripts"]
    assert scripts["network-assessment"] == "network_assessment.cli.main:cli"
    assert scripts["cna"] == scripts["network-assessment"], (
        "the old command is an alias of the new one"
    )
    module_name, _, attribute = scripts["network-assessment"].partition(":")
    assert callable(getattr(importlib.import_module(module_name), attribute))


# Rename step 2 (owner order 2026-10-27): the apps are `network-assessment-web|api|worker`. The old names are built
# from pieces so this file does not contain them.
_SHORT = "c" + "na"
OLD_APP_NAME = re.compile(rf"(?<![A-Za-z0-9_-]){_SHORT}[-_](?:web|api|worker)\b")
HISTORY = frozenset(
    {"CHANGELOG.md", "CNA-0.90-updates.md"}
)  # dated records keep the names they were written with


def test_the_apps_use_their_new_names() -> None:
    for app in ("web", "api", "worker"):
        assert (REPO_ROOT / "apps" / f"network-assessment-{app}").is_dir()
        assert not (REPO_ROOT / "apps" / f"{_SHORT}-{app}").exists()


def test_no_tracked_file_or_file_name_uses_an_old_app_name() -> None:
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("needs a git checkout and the git program")
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode("utf-8", errors="replace")
    names = [n for n in tracked.split("\0") if n and n not in HISTORY]
    assert len(names) > 100, "the scan lost its file list"
    hits: list[str] = []
    for name in names:
        if OLD_APP_NAME.search(name):
            hits.append(f"{name} (file name)")
        try:
            data = (REPO_ROOT / name).read_bytes()
        except FileNotFoundError:  # a tracked file deleted in the working tree
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        hits.extend(
            f"{name}:{text.count(chr(10), 0, m.start()) + 1}" for m in OLD_APP_NAME.finditer(text)
        )
    assert not hits, f"an old app name is back: {hits}"
