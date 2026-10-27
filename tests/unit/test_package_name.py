"""The old short name is gone from the package, the apps, the engine, the role names and the labels.

Rename steps 1 to 4 (owner order 2026-10-27): the package is `network_assessment`, the apps are
`network-assessment-web|api` (the worker app was retired on 2026-10-27, REVIEW.md R-016), the engine package is `network-assessment-azure-engine`, the role names start with
`NetworkAssessment-`, and the product is shown as NetworkEyes. The old command `cna` still works for now, as an alias.
The old names are built from pieces, so this file does not contain them.
"""

from __future__ import annotations

import importlib
import re
import shutil
import subprocess
import tomllib
from collections.abc import Callable
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

_SHORT = "c" + "na"
_UPPER = "C" + "NA"
OLD_IMPORT = re.compile(r"(?m)^\s*(?:from|import) " + _SHORT + r"\b")
# a dotted module path inside a string, as in a patch target or an import_module call
OLD_DOTTED = re.compile(r"""["']""" + _SHORT + r"[.][a-z_]")
OLD_APP_NAME = re.compile(rf"(?<![A-Za-z0-9_-]){_SHORT}[-_](?:web|api|worker)\b")
OLD_ENGINE = re.compile(rf"{_SHORT}[-_]azure[-_]network[-_]engine")
OLD_ROLE = re.compile(
    rf"(?<![A-Za-z0-9_-]){_UPPER}-(?:ReadOnly|Discovery|Publish|TestConnection|Test)\b"
)
BARE_LABEL = re.compile(rf"(?<![A-Za-z0-9_.-]){_UPPER}(?![A-Za-z0-9_-])")
HISTORY = frozenset(
    {"CHANGELOG.md", "CNA-0.90-updates.md"}
)  # dated records keep the names they were written with
# the first engine release was published under the old name; a line that names that release or its files may keep it
PUBLISHED_ENGINE_RELEASE = re.compile(rf"engine-v0[.]1[.]0|{_SHORT}_azure_network_engine-0[.]1[.]0")


def _hits(
    pattern: re.Pattern[str],
    *,
    suffix: str | None = None,
    skip_line: Callable[[str], bool] | None = None,
) -> list[str]:
    """``file:line`` of every match in a tracked file (and file names) outside the dated records."""
    if shutil.which("git") is None or not (REPO_ROOT / ".git").exists():
        pytest.skip("needs a git checkout and the git program")
    tracked = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-z"], capture_output=True, check=True
    ).stdout.decode("utf-8", errors="replace")
    names = [n for n in tracked.split("\0") if n and n not in HISTORY]
    assert len(names) > 100, "the scan lost its file list"
    found: list[str] = []
    for name in names:
        if pattern.search(name):
            found.append(f"{name} (file name)")
        if suffix is not None and not name.endswith(suffix):
            continue
        try:
            data = (REPO_ROOT / name).read_bytes()
        except FileNotFoundError:  # a tracked file deleted in the working tree
            continue
        if b"\0" in data:
            continue
        text = data.decode("utf-8", errors="replace")
        for match in pattern.finditer(text):
            start = text.rfind("\n", 0, match.start()) + 1
            end = text.find("\n", match.end())
            line = text[start : end if end >= 0 else len(text)]
            if skip_line is None or not skip_line(line):
                found.append(f"{name}:{text.count(chr(10), 0, match.start()) + 1}")
    return found


# --- step 1: the package ---------------------------------------------------------------------------------------------


def test_the_package_imports_under_its_new_name() -> None:
    module = importlib.import_module("network_assessment")
    assert Path(module.__file__).resolve().parent == REPO_ROOT / "network_assessment"


def test_the_old_package_name_does_not_import() -> None:
    # the directory may survive as an untracked __pycache__ on a developer checkout; its package marker may not
    assert not (REPO_ROOT / _SHORT / "__init__.py").exists()


def test_no_tracked_python_file_imports_the_old_package_name() -> None:
    offenders = _hits(OLD_IMPORT, suffix=".py") + _hits(OLD_DOTTED, suffix=".py")
    assert not offenders, f"these files still import the old package name: {offenders}"


def test_the_distribution_and_both_commands_point_at_the_same_function() -> None:
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "network-assessment"
    scripts = project["scripts"]
    assert scripts["network-assessment"] == "network_assessment.cli.main:cli"
    assert scripts[_SHORT] == scripts["network-assessment"], (
        "the old command is an alias of the new one"
    )
    module_name, _, attribute = scripts["network-assessment"].partition(":")
    assert callable(getattr(importlib.import_module(module_name), attribute))


# --- step 2: the apps ------------------------------------------------------------------------------------------------


def test_the_apps_use_their_new_names() -> None:
    # `worker` stays in this loop only for the old name: the old directory must not come back. The worker app itself
    # is retired (REVIEW.md R-016, owner decision 2026-10-27), so its new name is not expected to exist.
    for app in ("web", "api", "worker"):
        assert not (REPO_ROOT / "apps" / f"{_SHORT}-{app}").exists()
    for app in ("web", "api"):
        assert (REPO_ROOT / "apps" / f"network-assessment-{app}").is_dir()


def test_no_tracked_file_or_file_name_uses_an_old_app_name() -> None:
    hits = _hits(OLD_APP_NAME)
    assert not hits, f"an old app name is back: {hits}"


# --- step 4: the engine package, the role names and the labels -------------------------------------------------------


def test_the_engine_package_and_the_role_document_use_their_new_names() -> None:
    engine = REPO_ROOT / "packages" / "network-assessment-azure-engine"
    assert (engine / "network_assessment_azure_engine" / "__init__.py").is_file()
    assert not (REPO_ROOT / "packages" / f"{_SHORT}-azure-network-engine").exists()
    assert (REPO_ROOT / "docs" / "roles" / "network-assessment-bgp-reader.json").is_file()
    project = tomllib.loads((engine / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert project["name"] == "network-assessment-azure-engine"


def test_no_tracked_file_uses_an_old_engine_name_except_where_it_records_the_published_release() -> (
    None
):
    hits = _hits(OLD_ENGINE, skip_line=lambda line: bool(PUBLISHED_ENGINE_RELEASE.search(line)))
    assert not hits, f"an old engine name is back: {hits}"


def test_no_tracked_file_uses_an_old_role_name() -> None:
    hits = _hits(OLD_ROLE)
    assert not hits, f"an old role name is back: {hits}"


def test_no_tracked_file_shows_the_old_short_name_as_a_label() -> None:
    hits = _hits(BARE_LABEL)
    assert not hits, f"show the product as NetworkEyes, not by its old short name: {hits}"


def test_the_patterns_catch_what_they_are_for_and_spare_what_stays() -> None:
    for text in (f"{_SHORT}-web", f"apps/{_SHORT}_api", f"{_SHORT}-worker"):
        assert OLD_APP_NAME.search(text), text
    for text in (f"{_SHORT}-azure-network-engine", f"{_SHORT}_azure_network_engine"):
        assert OLD_ENGINE.search(text), text
    # only a line that names the published release is spared, not any line that mentions a version
    for text in (
        "engine-v0.1.0",
        f"{_SHORT}_azure_network_engine-0.1.0-py3-none-any.whl",
    ):
        assert PUBLISHED_ENGINE_RELEASE.search(text), text
    for text in (f"{_SHORT}-azure-network-engine>=0.1.0", f"{_SHORT}_azure_network_engine 0.1.0"):
        assert not PUBLISHED_ENGINE_RELEASE.search(text), text
    for text in (f"{_UPPER}-ReadOnly", f"role/{_UPPER}-Discovery", f"{_UPPER}-Test"):
        assert OLD_ROLE.search(text), text
    for text in (f"the {_UPPER} API", f"({_UPPER})", f"{_UPPER} VNet"):
        assert BARE_LABEL.search(text), text
    # the setting prefix, the deployed database name and the alias are not labels
    for text in (
        f"{_UPPER}_API_TOKEN",
        f"{_SHORT}admin",
        f"{_UPPER}-0.90-updates.md",
        f"x{_UPPER}y",
    ):
        assert not BARE_LABEL.search(text), text
