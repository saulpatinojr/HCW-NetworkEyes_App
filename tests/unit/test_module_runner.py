"""Unit tests for cna.core.module_runner."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml

from cna.core.exceptions import ModuleDependencyError
from cna.core.module_runner import ModuleRunner


def _make_runner(tmp_path: Path, store=None) -> ModuleRunner:
    modules_dir = tmp_path / "cna" / "modules"
    modules_dir.mkdir(parents=True)
    mock_store = store or MagicMock()
    mock_store.list_completed_checkpoints.return_value = []
    return ModuleRunner(store=mock_store, modules_dir=modules_dir)


def _write_manifest(modules_dir: Path, module_name: str, manifest: dict) -> None:
    module_dir = modules_dir / module_name
    module_dir.mkdir(parents=True, exist_ok=True)
    (module_dir / "module.yaml").write_text(yaml.dump(manifest))


# ── _load_module_manifest ──────────────────────────────────────────────────────


class TestLoadModuleManifest:
    def test_loads_existing_manifest(self, tmp_path):
        runner = _make_runner(tmp_path)
        _write_manifest(
            runner.modules_dir,
            "network",
            {"name": "network", "depends_on": []},
        )
        manifest = runner._load_module_manifest("network")
        assert manifest["name"] == "network"

    def test_raises_if_manifest_missing(self, tmp_path):
        runner = _make_runner(tmp_path)
        with pytest.raises(FileNotFoundError, match="No module.yaml found"):
            runner._load_module_manifest("nonexistent_module")


# ── _get_completed_modules ─────────────────────────────────────────────────────


class TestGetCompletedModules:
    def test_empty_when_no_checkpoints(self, tmp_path):
        store = MagicMock()
        store.list_completed_checkpoints.return_value = []
        runner = _make_runner(tmp_path, store=store)
        result = runner._get_completed_modules("eng-001")
        assert result == set()

    def test_network_added_when_aws_checkpoints_exist(self, tmp_path):
        store = MagicMock()

        def _checkpoints(engagement_id, platform):
            return ["checkpoint-vpc"] if platform == "aws" else []

        store.list_completed_checkpoints.side_effect = _checkpoints
        runner = _make_runner(tmp_path, store=store)
        result = runner._get_completed_modules("eng-001")
        assert "network" in result

    def test_network_added_when_azure_checkpoints_exist(self, tmp_path):
        store = MagicMock()

        def _checkpoints(engagement_id, platform):
            return ["checkpoint-vnet"] if platform == "azure" else []

        store.list_completed_checkpoints.side_effect = _checkpoints
        runner = _make_runner(tmp_path, store=store)
        result = runner._get_completed_modules("eng-001")
        assert "network" in result

    def test_checks_both_platforms(self, tmp_path):
        store = MagicMock()
        store.list_completed_checkpoints.return_value = []
        runner = _make_runner(tmp_path, store=store)
        runner._get_completed_modules("eng-001")
        calls = [c.args[1] for c in store.list_completed_checkpoints.call_args_list]
        assert "aws" in calls
        assert "azure" in calls


# ── check_dependencies ─────────────────────────────────────────────────────────


class TestCheckDependencies:
    def test_no_depends_on_always_passes(self, tmp_path):
        runner = _make_runner(tmp_path)
        _write_manifest(runner.modules_dir, "standalone", {"name": "standalone"})
        runner.check_dependencies("standalone", "eng-001")  # Must not raise

    def test_empty_depends_on_passes(self, tmp_path):
        runner = _make_runner(tmp_path)
        _write_manifest(runner.modules_dir, "zero_deps", {"name": "zero_deps", "depends_on": []})
        runner.check_dependencies("zero_deps", "eng-001")  # Must not raise

    def test_raises_if_dependency_not_completed(self, tmp_path):
        store = MagicMock()
        store.list_completed_checkpoints.return_value = []
        runner = _make_runner(tmp_path, store=store)
        _write_manifest(
            runner.modules_dir,
            "landingzone",
            {"name": "landingzone", "depends_on": ["network"]},
        )
        with pytest.raises(ModuleDependencyError):
            runner.check_dependencies("landingzone", "eng-001")

    def test_passes_when_dependency_completed(self, tmp_path):
        runner = _make_runner(tmp_path)
        runner.store.list_completed_checkpoints.return_value = ["vpc-checkpoint"]
        _write_manifest(
            runner.modules_dir,
            "landingzone",
            {"name": "landingzone", "depends_on": ["network"]},
        )
        runner.check_dependencies("landingzone", "eng-001")  # Must not raise

    def test_raises_for_each_missing_dependency(self, tmp_path):
        store = MagicMock()
        store.list_completed_checkpoints.return_value = []
        runner = _make_runner(tmp_path, store=store)
        _write_manifest(
            runner.modules_dir,
            "security",
            {"name": "security", "depends_on": ["network", "iam"]},
        )
        with pytest.raises(ModuleDependencyError):
            runner.check_dependencies("security", "eng-001")


# ── run ────────────────────────────────────────────────────────────────────────


class TestRun:
    def test_run_calls_check_dependencies(self, tmp_path):
        runner = _make_runner(tmp_path)
        _write_manifest(runner.modules_dir, "mymodule", {"name": "mymodule", "depends_on": []})
        # Should not raise — dependency check passes for empty depends_on
        runner.run("mymodule", "eng-001")

    def test_run_raises_if_dependency_missing(self, tmp_path):
        store = MagicMock()
        store.list_completed_checkpoints.return_value = []
        runner = _make_runner(tmp_path, store=store)
        _write_manifest(
            runner.modules_dir, "blocked", {"name": "blocked", "depends_on": ["network"]}
        )
        with pytest.raises(ModuleDependencyError):
            runner.run("blocked", "eng-001")
