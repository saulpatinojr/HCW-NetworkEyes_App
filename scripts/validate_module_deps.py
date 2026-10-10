"""CI script: validate all module.yaml depends_on reference installed modules.

Closes TODO_PhaseA: Module depends_on not enforced.
Runs in CI (module-dependency-check job) and can be run locally.

The modules directory is resolved from __file__, not the working directory, so
the script validates the same tree wherever it is invoked from. Finding zero
modules is treated as a broken invocation rather than a pass — it previously
reported success from any other directory (TODO.md T-406).

Exit 0: all dependencies satisfied.
Exit 1: one or more modules depend on an uninstalled module, or the modules
        directory is missing/empty — blocks merge.
"""

import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULES_DIR = REPO_ROOT / "cna" / "modules"


def load_modules() -> dict[str, dict]:
    all_modules = {}
    for module_yaml in MODULES_DIR.rglob("module.yaml"):
        with open(module_yaml) as f:
            data = yaml.safe_load(f)
        if name := data.get("name"):
            all_modules[name] = data
    return all_modules


def validate() -> bool:
    if not MODULES_DIR.is_dir():
        print(f"ERROR: modules directory not found: {MODULES_DIR}", file=sys.stderr)
        return False

    all_modules = load_modules()
    if not all_modules:
        print(
            f"ERROR: no module.yaml files found under {MODULES_DIR}. "
            "Nothing was validated — this is a broken invocation, not a pass.",
            file=sys.stderr,
        )
        return False

    installed = {
        name: data for name, data in all_modules.items() if data.get("status") == "installed"
    }

    errors = []
    for name, data in all_modules.items():
        if data.get("status") != "installed":
            continue
        for dep in data.get("depends_on", []):
            if dep not in installed:
                errors.append(
                    f"ERROR: Module '{name}' depends on '{dep}' but '{dep}' is not installed."
                )

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        print(f"\n{len(errors)} dependency error(s) found. Fix module.yaml files.", file=sys.stderr)
        return False

    print(f"OK: {len(installed)} installed modules, all dependencies satisfied.")
    return True


if __name__ == "__main__":
    sys.exit(0 if validate() else 1)
