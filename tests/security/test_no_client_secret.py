"""No client-secret path exists anywhere in the product (REFACTOR_APP.md change set G).

The plan's acceptance grep, as a test: ``ClientSecretCredential``, ``sp_client_secret``,
``spSecretEnc``, ``spClientId`` and an ``AZURE_CLIENT_SECRET=`` assignment appear nowhere under
``apps/``, ``network_assessment/`` or ``packages/``, and ``DefaultAzureCredential`` is constructed in exactly one
place — the platform factory that excludes the environment and interactive credentials — so no
module can quietly grow a secret-reading chain of its own.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SKIP_DIRS = {"node_modules", ".next", "__pycache__", ".venv", "dist", "migrations"}
TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".prisma",
    ".yaml",
    ".yml",
    ".json",
    ".sh",
    ".toml",
    ".example",
}
FORBIDDEN = (
    "ClientSecretCredential",
    "sp_client_secret",
    "spSecretEnc",
    "spClientId",
    "AZURE_CLIENT_SECRET=",
)
FACTORY = REPO_ROOT / "network_assessment" / "core" / "auth.py"
_CONSTRUCTS_DEFAULT = re.compile(r"DefaultAzureCredential\(")


def _files(*roots: Path):
    for root in roots:
        if root.is_file():
            yield root
            continue
        for path in root.rglob("*"):
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in TEXT_SUFFIXES:
                yield path


def _roots() -> list[Path]:
    return [
        REPO_ROOT / "apps",
        REPO_ROOT / "network_assessment",
        REPO_ROOT / "packages",
        REPO_ROOT / ".env.example",
    ]


def test_no_client_secret_path_in_the_product():
    offenders = []
    for path in _files(*_roots()):
        text = path.read_text(encoding="utf-8", errors="replace")
        for needle in FORBIDDEN:
            if needle in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {needle}")
    assert offenders == []


def test_default_azure_credential_is_built_only_by_the_factory():
    """Every other module calls ``build_azure_credential``; none builds the chain itself."""
    builders = [
        str(path.relative_to(REPO_ROOT))
        for path in _files(
            REPO_ROOT / "apps", REPO_ROOT / "network_assessment", REPO_ROOT / "packages"
        )
        if path.suffix == ".py"
        and _CONSTRUCTS_DEFAULT.search(path.read_text(encoding="utf-8", errors="replace"))
    ]
    assert builders == [str(FACTORY.relative_to(REPO_ROOT))]


def test_the_prisma_schema_carries_no_service_principal_columns():
    schema = (REPO_ROOT / "apps" / "network-assessment-web" / "prisma" / "schema.prisma").read_text(
        encoding="utf-8"
    )
    assert "spSecretEnc" not in schema and "spClientId" not in schema
    migration = (
        REPO_ROOT
        / "apps"
        / "network-assessment-web"
        / "prisma"
        / "migrations"
        / "20261010000016_drop_sp_secret"
    )
    assert 'DROP COLUMN "spSecretEnc"' in (migration / "migration.sql").read_text(encoding="utf-8")
    assert "spSecretEnc" in (migration / "down.sql").read_text(encoding="utf-8")
