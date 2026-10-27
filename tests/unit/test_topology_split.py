"""The split of ``network_assessment.core.topology_schema`` into ``network_assessment.core.topology.{common,azure,aws}``.

Pins the contract of the split: the old import path resolves to the very same classes,
Azure and AWS carry their own version constants, the Azure module never loads the AWS
one, and no project source imports the deprecated path any more.
"""

from __future__ import annotations

import ast
import subprocess
import sys
import warnings
from pathlib import Path

import pytest

from network_assessment.core import topology
from network_assessment.core.topology import aws, azure, common

REPO_ROOT = Path(__file__).resolve().parents[2]
SHIM = REPO_ROOT / "network_assessment" / "core" / "topology_schema.py"
TOPOLOGY_DIR = REPO_ROOT / "network_assessment" / "core" / "topology"


@pytest.fixture(scope="module")
def shim():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        import network_assessment.core.topology_schema as module
    return module


class TestOldPathResolvesToTheSameObjects:
    def test_every_public_name_is_the_same_object(self, shim):
        for module in (common, aws, azure):
            for name in module.__all__:
                assert getattr(shim, name) is getattr(module, name), name

    def test_shim_exports_exactly_the_three_modules_plus_the_alias(self, shim):
        expected = {*common.__all__, *aws.__all__, *azure.__all__, "TOPOLOGY_SCHEMA_VERSION"}
        assert set(shim.__all__) == expected

    def test_old_version_name_is_the_azure_version(self, shim):
        assert shim.TOPOLOGY_SCHEMA_VERSION is azure.AZURE_TOPOLOGY_VERSION


class TestSeparateVersions:
    def test_each_model_carries_its_own_version(self):
        # The Azure model moved to the engine package and gained the export fields (1.4.0);
        # the AWS model stays in the monorepo at 1.3.0.
        assert azure.AZURE_TOPOLOGY_VERSION == "1.4.0"
        assert aws.AWS_TOPOLOGY_VERSION == "1.3.0"

    def test_each_root_model_defaults_to_its_own_version(self):
        azure_topology = azure.AzureTopology(engagement_id="e", tenant_id="t")
        assert azure_topology.source == "discovery"
        aws_topology = aws.AWSTopology(engagement_id="e")
        assert azure_topology.schema_version == azure.AZURE_TOPOLOGY_VERSION
        assert aws_topology.schema_version == aws.AWS_TOPOLOGY_VERSION


class TestModuleBoundaries:
    @staticmethod
    def _imported_modules(path: Path) -> set[str]:
        tree = ast.parse(path.read_text())
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                found.add(node.module)
            elif isinstance(node, ast.Import):
                found.update(alias.name for alias in node.names)
        return found

    def test_azure_module_imports_nothing_from_aws(self):
        imported = self._imported_modules(TOPOLOGY_DIR / "azure.py")
        assert "network_assessment.core.topology.aws" not in imported
        assert "network_assessment.core.topology_schema" not in imported
        # The Azure model lives in the engine package; this module re-exports it.
        assert "network_assessment_azure_engine.model.azure" in imported

    def test_aws_module_imports_nothing_from_azure(self):
        imported = self._imported_modules(TOPOLOGY_DIR / "aws.py")
        assert "network_assessment.core.topology.azure" not in imported
        assert "network_assessment.core.topology_schema" not in imported
        assert "network_assessment.core.topology.common" in imported
        assert not any(m.startswith("network_assessment_azure_engine") for m in imported)

    def test_importing_azure_does_not_load_aws(self):
        code = (
            "import sys; import network_assessment.core.topology.azure; "
            "assert 'network_assessment.core.topology.aws' not in sys.modules, sorted(sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=False
        )
        assert result.returncode == 0, result.stderr

    def test_package_reexports_common_and_azure_only(self):
        assert set(topology.__all__) == {*common.__all__, *azure.__all__}
        assert not any(name in topology.__all__ for name in aws.__all__)

    def test_azure_uses_only_the_shared_enums_it_needs(self):
        assert azure.SubnetType is common.SubnetType
        assert not hasattr(azure, "AttachmentType")


class TestNoProjectSourceImportsTheDeprecatedPath:
    def test_only_the_shim_mentions_the_old_import(self):
        offenders = []
        for top in ("network_assessment", "apps"):
            for path in (REPO_ROOT / top).rglob("*.py"):
                if path == SHIM:
                    continue
                if "network_assessment.core.topology_schema import" in path.read_text(
                    errors="replace"
                ):
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        assert offenders == []
