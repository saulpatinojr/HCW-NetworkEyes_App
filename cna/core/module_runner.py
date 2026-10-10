"""Module runner with dependency enforcement.

Closes TODO_PhaseA: Module depends_on not enforced.

Every module invocation goes through ModuleRunner.run().
It checks that all declared depends_on modules have completed
discovery for this engagement before proceeding.
Raises ModuleDependencyError if not satisfied — never silently skips.
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml

from cna.core.exceptions import ModuleDependencyError
from cna.core.persistence import EngagementStore

logger = logging.getLogger("cna.core.module_runner")


class ModuleRunner:
    """Enforces module dependency graph before execution."""

    def __init__(self, store: EngagementStore, modules_dir: Path | None = None):
        self.store = store
        self.modules_dir = modules_dir or Path("cna/modules")

    def _load_module_manifest(self, module_name: str) -> dict:
        manifest_path = self.modules_dir / module_name / "module.yaml"
        if not manifest_path.exists():
            raise FileNotFoundError(f"No module.yaml found for module '{module_name}'")
        with open(manifest_path) as f:
            return yaml.safe_load(f)

    def _get_completed_modules(self, engagement_id: str) -> set[str]:
        """Return set of module names that have completed discovery checkpoints."""
        completed = set()
        for platform in ["aws", "azure"]:
            checkpoints = self.store.list_completed_checkpoints(engagement_id, platform)
            if checkpoints:
                # If any checkpoint exists for a platform, network discovery ran
                # More granular tracking added in Phase C discovery layer
                completed.add("network")
        return completed

    def check_dependencies(self, module_name: str, engagement_id: str) -> None:
        """Raise ModuleDependencyError if depends_on modules not yet complete.

        Args:
            module_name: Module about to be run.
            engagement_id: Current engagement.

        Raises:
            ModuleDependencyError: If a dependency has not completed.
        """
        manifest = self._load_module_manifest(module_name)
        depends_on = manifest.get("depends_on", [])
        if not depends_on:
            return

        completed = self._get_completed_modules(engagement_id)
        for dep in depends_on:
            if dep not in completed:
                raise ModuleDependencyError(module=module_name, missing_dependency=dep)

    def run(self, module_name: str, engagement_id: str, **kwargs) -> None:
        """Run a module after dependency check."""
        logger.info("Checking dependencies for module: %s", module_name)
        self.check_dependencies(module_name, engagement_id)
        logger.info("Dependencies satisfied. Running module: %s", module_name)
        # Phase C: dynamic module loader and executor
