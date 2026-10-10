"""Module registry — loads installed modules, lists stubs."""

from pathlib import Path

import yaml

MODULES_DIR = Path(__file__).parent


def list_all_modules() -> list:
    """Return all modules (installed + stubs), sorted by name."""
    modules = []
    for manifest in MODULES_DIR.glob("*/module.yaml"):
        with open(manifest) as f:
            modules.append(yaml.safe_load(f))
    return sorted(modules, key=lambda m: m.get("name", ""))


def get_installed_modules() -> list:
    """Return names of installed modules only."""
    return [m["name"] for m in list_all_modules() if m.get("status") == "installed"]


def get_stub_modules() -> list:
    """Return stub modules — available but not installed."""
    return [m for m in list_all_modules() if m.get("status") == "available_not_installed"]
