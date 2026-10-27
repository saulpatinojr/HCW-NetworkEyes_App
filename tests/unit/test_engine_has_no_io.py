"""The engine package does no I/O (change set E of REFACTOR_APP.md).

``network_assessment_azure_engine`` is the pure half of the platform: a topology in, a findings
report out. It must import nothing from the monorepo (``network_assessment.*``), no database driver, no
socket or HTTP client, and no Azure SDK outside its ``discovery`` subpackage, which is the
one place that talks to a cloud and lives behind the ``[azure]`` extra. Two checks, as the
packaging tests do it: the import graph read from the source with ``ast`` (static, every
module, every branch), and the modules actually loaded by ``evaluate()`` in a fresh
interpreter (dynamic, what a process really pulls in).
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE_DIR = REPO_ROOT / "packages" / "network-assessment-azure-engine"
SOURCE = PACKAGE_DIR / "network_assessment_azure_engine"

# Top-level module names the engine must never import. ``azure`` is allowed under
# ``discovery/`` only.
FORBIDDEN_ROOTS = frozenset(
    {
        "network_assessment",
        "psycopg2",
        "psycopg",
        "sqlite3",
        "sqlalchemy",
        "socket",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "boto3",
        "botocore",
    }
)
CLOUD_ROOTS = frozenset({"azure", "msal", "msrest"})


def _modules() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def _imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def test_the_package_has_modules():
    assert len(_modules()) > 10


def test_no_module_imports_the_monorepo_a_database_or_a_network_client():
    offenders = {
        str(path.relative_to(PACKAGE_DIR)): sorted(hits)
        for path in _modules()
        if (hits := _imported_roots(path) & FORBIDDEN_ROOTS)
    }
    assert offenders == {}


def test_cloud_sdks_are_imported_only_under_discovery():
    offenders = {
        str(path.relative_to(PACKAGE_DIR)): sorted(hits)
        for path in _modules()
        if "discovery" not in path.relative_to(SOURCE).parts
        and (hits := _imported_roots(path) & CLOUD_ROOTS)
    }
    assert offenders == {}


def test_the_acceptance_grep_is_empty():
    """``git grep -n "EngagementStore\\|psycopg2" -- packages/network-assessment-azure-engine``."""
    hits = [
        f"{path.relative_to(PACKAGE_DIR)}: {needle}"
        for path in sorted(PACKAGE_DIR.rglob("*"))
        if path.is_file()
        and path.suffix in {".py", ".toml", ".md", ".txt", ".cfg"}
        and "egg-info" not in path.parts
        and "build" not in path.parts
        for needle in ("EngagementStore", "psycopg2")
        if needle in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert hits == []


def test_evaluate_loads_no_io_module_in_a_fresh_interpreter():
    """Walk ``sys.modules`` after importing the engine and evaluating an empty topology."""
    probe = (
        "import json, sys\n"
        "from network_assessment_azure_engine.model.azure import AzureTopology\n"
        "from network_assessment_azure_engine.rules.registry import evaluate\n"
        "report = evaluate(AzureTopology(subscriptions=[]))\n"
        "roots = sorted({m.split('.', 1)[0] for m in sys.modules})\n"
        "print(json.dumps({'roots': roots, 'rules_version': report.rules_version}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", probe],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(PACKAGE_DIR),
    )
    payload = json.loads(result.stdout.strip().splitlines()[-1])
    loaded = set(payload["roots"])
    assert payload["rules_version"]
    assert loaded & (FORBIDDEN_ROOTS | CLOUD_ROOTS) == set()
