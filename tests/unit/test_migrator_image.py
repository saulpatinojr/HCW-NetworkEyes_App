"""The migrator image ships what it runs and nothing else (TODO.md T-737).

`apps/cna-web/Dockerfile` has a `migrator` target that receives the database-owner connection string and runs
`prisma/migrate.sh` (`prisma migrate deploy`, then `prisma/seed-local-admin.js`). It used to copy the builder's whole
`node_modules`: every devDependency, among them the Go-compiled TypeScript 7 compiler (19 High findings in a Trivy
scan) and two vulnerable `brace-expansion` versions, none of which `npm audit --omit=dev` can see. These tests keep
that from coming back, statically; the `Image Scan (Trivy)` job of `300-test-codebase.yml` checks the built image.

What is pinned here:

* the Dockerfile text: the migrator copies nothing from the builder and takes `node_modules` from its own
  `migrator-deps` stage, which installs from a lockfile with `npm ci --omit=dev --ignore-scripts`; the runner still
  takes only the generated Prisma client from the builder (so `prisma` moving to `dependencies` cannot enlarge it);
  the numeric user, the exec-form `CMD`/`HEALTHCHECK` and the file ownership stay as they were;
* `package.json`: `prisma` is a production dependency (the migrator runs it) at the same range as `@prisma/client`;
* the lockfile: no `brace-expansion` below the versions that fix GHSA-qhr7-859c-m2p7 and GHSA-6j4f-fj2g-mc7p;
* `scripts/migrator-lockfile.mjs`, run against the real lockfile: the migrator tree contains Prisma and none of the
  build tooling, copies lockfile entries as they are, and is accepted by `npm ci` (an offline dry run).
"""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB = REPO_ROOT / "apps" / "cna-web"
DOCKERFILE = WEB / "Dockerfile"
PACKAGE_JSON = WEB / "package.json"
PACKAGE_LOCK = WEB / "package-lock.json"
LOCKFILE_SCRIPT = WEB / "scripts" / "migrator-lockfile.mjs"

# Packages that must never be in the migrator: the web app's build, lint, test and runtime tooling.
BANNED_IN_MIGRATOR = (
    "typescript",
    "@typescript/native",
    "@typescript/typescript6",
    "eslint",
    "vitest",
    "vite",
    "tailwindcss",
    "@tailwindcss/postcss",
    "next",
    "react",
    "jsdom",
    "postcss",
)
# What prisma/migrate.sh and prisma/seed-local-admin.js load.
REQUIRED_IN_MIGRATOR = ("prisma", "@prisma/client", "@prisma/engines", "@prisma/config")

# First fixed version per major line: GHSA-qhr7-859c-m2p7 (fixed in 1.1.20, 2.1.6, 3.0.8, 5.0.11) and
# GHSA-6j4f-fj2g-mc7p (fixed in 1.1.19, 2.1.5, 3.0.7, 5.0.10); every 4.x is affected, 5.0.11 is the first clean one.
BRACE_EXPANSION_FIXED = {1: (1, 1, 20), 2: (2, 1, 6), 3: (3, 0, 8), 4: (5, 0, 11), 5: (5, 0, 11)}

node = shutil.which("node")
npm = shutil.which("npm")
needs_node = pytest.mark.skipif(node is None, reason="node is not available")


def stages(path: Path) -> dict[str, list[tuple[int, str, str]]]:
    """Dockerfile instructions grouped by stage name; continuations joined, comments dropped."""
    result: dict[str, list[tuple[int, str, str]]] = {}
    current = ""
    pending, start = "", 0
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if pending and line.startswith("#"):
            continue
        if not pending:
            start = number
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        full = (pending + line).strip()
        pending = ""
        keyword, _, arguments = full.partition(" ")
        keyword = keyword.upper()
        if keyword == "FROM":
            match = re.search(r"\s+AS\s+(\S+)\s*$", arguments, re.IGNORECASE)
            current = match.group(1) if match else f"stage-{len(result)}"
            result[current] = []
        result.setdefault(current, []).append((start, keyword, arguments.strip()))
    return result


def copies(stage: str) -> list[tuple[int, str]]:
    return [(n, a) for n, k, a in stages(DOCKERFILE)[stage] if k == "COPY"]


def runs(stage: str) -> list[str]:
    return [a for _, k, a in stages(DOCKERFILE)[stage] if k == "RUN"]


def package_json() -> dict:
    return json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))


def package_lock() -> dict:
    return json.loads(PACKAGE_LOCK.read_text(encoding="utf-8"))


def version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in re.match(r"(\d+)\.(\d+)\.(\d+)", version).groups())


# --- the Dockerfile ---


def test_the_web_dockerfile_has_the_expected_stage_graph() -> None:
    assert list(stages(DOCKERFILE)) == ["deps", "builder", "migrator-deps", "migrator", "runner"]


def test_migrator_copies_nothing_from_the_builder() -> None:
    """The builder's node_modules holds every devDependency; its other output is not the migrator's business."""
    for number, arguments in copies("migrator"):
        assert "--from=builder" not in arguments, (
            f"Dockerfile:{number} the migrator stage copies from the builder: COPY {arguments}"
        )


def test_migrator_takes_node_modules_from_its_own_stage_with_the_same_ownership() -> None:
    node_modules = [(n, a) for n, a in copies("migrator") if "node_modules" in a]
    assert len(node_modules) == 1, node_modules
    number, arguments = node_modules[0]
    assert "--from=migrator-deps" in arguments, f"Dockerfile:{number} {arguments}"
    assert "--chown=nextjs:nodejs" in arguments
    prisma_dir = [a for _, a in copies("migrator") if re.search(r"\bprisma\s+\./prisma\s*$", a)]
    assert prisma_dir and "--chown=nextjs:nodejs" in prisma_dir[0], copies("migrator")
    assert any(
        "--chmod=755 prisma/migrate.sh ./prisma/migrate.sh" in a for _, a in copies("migrator")
    )


def test_migrator_deps_installs_production_only_from_a_lockfile_without_scripts() -> None:
    commands = " && ".join(runs("migrator-deps"))
    assert "node migrator-lockfile.mjs" in commands, "the tree must be cut out of package-lock.json"
    install = re.search(r"npm ci\b[^&|;]*", commands)
    assert install, (
        "the migrator tree must be installed with `npm ci` (lockfile versions and integrity)"
    )
    assert "--omit=dev" in install.group(0)
    assert "--ignore-scripts" in install.group(0)
    assert "npm install" not in commands, (
        "`npm install` would resolve versions the lockfile does not name"
    )
    # Prisma's two install-time jobs, done explicitly instead of by running every dependency's scripts.
    assert "@prisma/engines/scripts/postinstall.js" in commands
    assert "prisma generate" in commands
    copied = [a for _, a in copies("migrator-deps")]
    assert any("migrator-lockfile.mjs" in a for a in copied)
    assert any("package-lock.json" in a and "package.json" in a for a in copied)


def test_migrator_keeps_its_user_command_and_environment() -> None:
    migrator = stages(DOCKERFILE)["migrator"]
    assert [a for _, k, a in migrator if k == "USER"] == ["1001"]
    assert [a for _, k, a in migrator if k == "CMD"] == ['["./prisma/migrate.sh"]']
    assert not [1 for _, k, _ in migrator if k in {"ENTRYPOINT", "HEALTHCHECK"}]
    assert "CHECKPOINT_DISABLE=1" in [a for _, k, a in migrator if k == "ENV"]


def test_runner_takes_only_the_generated_prisma_client_from_the_builder() -> None:
    """`prisma` moving to `dependencies` must not put the Prisma CLI (or any other package) in the runner."""
    modules = [a for _, a in copies("runner") if "/app/node_modules" in a]
    assert sorted(a.split()[-2] for a in modules) == [
        "/app/node_modules/.prisma",
        "/app/node_modules/@prisma",
    ], modules
    runner = stages(DOCKERFILE)["runner"]
    assert [a for _, k, a in runner if k == "USER"] == ["1001"]
    assert [a for _, k, a in runner if k == "CMD"] == ['["node", "app/server.js"]']
    assert any(k == "HEALTHCHECK" and "/api/health" in a for _, k, a in runner)


# --- package.json and the lockfile ---


def test_prisma_is_a_production_dependency_next_to_its_client() -> None:
    manifest = package_json()
    assert "prisma" in manifest["dependencies"], "the migrator runs the Prisma CLI"
    assert "prisma" not in manifest.get("devDependencies", {})
    assert manifest["dependencies"]["prisma"] == manifest["dependencies"]["@prisma/client"], (
        "the CLI that migrates and the client that queries must move together"
    )


def test_brace_expansion_has_no_override_below_the_fixed_versions() -> None:
    for key, value in package_json().get("overrides", {}).items():
        if key.split("@")[0] == "brace-expansion":
            assert isinstance(value, str) and re.fullmatch(r"[\^~>=]*\d+\.\d+\.\d+", value), (
                key,
                value,
            )
            major = version_tuple(value.lstrip("^~>="))[0]
            assert version_tuple(value.lstrip("^~>=")) >= BRACE_EXPANSION_FIXED[major], (
                f"override {key}={value} pins brace-expansion below the fixed version"
            )


def test_the_lockfile_has_no_vulnerable_brace_expansion() -> None:
    found = {
        path: entry["version"]
        for path, entry in package_lock()["packages"].items()
        if path.endswith("node_modules/brace-expansion")
    }
    assert found, (
        "brace-expansion is no longer in the lockfile; delete this test and BRACE_EXPANSION_FIXED"
    )
    for path, version in found.items():
        major = version_tuple(version)[0]
        assert major in BRACE_EXPANSION_FIXED, (path, version)
        assert version_tuple(version) >= BRACE_EXPANSION_FIXED[major], (
            f"{path} is {version}: below {'.'.join(map(str, BRACE_EXPANSION_FIXED[major]))}, "
            "which fixes GHSA-qhr7-859c-m2p7 and GHSA-6j4f-fj2g-mc7p"
        )


# --- scripts/migrator-lockfile.mjs, against the real lockfile ---


def run_script(source: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(node), str(LOCKFILE_SCRIPT), str(source), str(output)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


@pytest.fixture(scope="module")
def migrator_tree(tmp_path_factory: pytest.TempPathFactory) -> Path:
    if node is None:
        pytest.skip("node is not available")
    output = tmp_path_factory.mktemp("migrator-tree")
    result = run_script(WEB, output)
    assert result.returncode == 0, result.stderr
    return output


def locations(tree: Path) -> dict[str, dict]:
    packages = json.loads((tree / "package-lock.json").read_text(encoding="utf-8"))["packages"]
    return {path: entry for path, entry in packages.items() if path}


def names(tree: Path) -> set[str]:
    return {path.rsplit("node_modules/", 1)[1] for path in locations(tree)}


@needs_node
def test_the_migrator_tree_contains_prisma(migrator_tree: Path) -> None:
    present = names(migrator_tree)
    for required in REQUIRED_IN_MIGRATOR:
        assert required in present, f"{required} is missing from the migrator tree"
    manifest = json.loads((migrator_tree / "package.json").read_text(encoding="utf-8"))
    assert sorted(manifest["dependencies"]) == ["@prisma/client", "prisma"]


@needs_node
def test_the_migrator_tree_contains_none_of_the_build_tooling(migrator_tree: Path) -> None:
    present = names(migrator_tree)
    assert not present & set(BANNED_IN_MIGRATOR), sorted(present & set(BANNED_IN_MIGRATOR))
    assert not {n for n in present if n.startswith("@typescript/") or n.startswith("@types/")}
    assert len(present) < 60, f"{len(present)} packages: the migrator tree should stay small"


@needs_node
def test_the_migrator_tree_copies_lockfile_entries_as_they_are(migrator_tree: Path) -> None:
    full = package_lock()["packages"]
    for path, entry in locations(migrator_tree).items():
        assert path in full, path
        assert entry["version"] == full[path]["version"], path
        assert entry["integrity"] == full[path]["integrity"], path
        assert entry["resolved"] == full[path]["resolved"], path
        assert "dev" not in entry and "devOptional" not in entry, path


@needs_node
@pytest.mark.skipif(npm is None, reason="npm is not available")
def test_npm_ci_accepts_the_migrator_manifest_and_lockfile(migrator_tree: Path) -> None:
    """`npm ci` refuses a lockfile that does not match its package.json; offline, nothing is downloaded."""
    result = subprocess.run(
        [
            str(npm),
            "ci",
            "--dry-run",
            "--offline",
            "--omit=dev",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ],
        cwd=migrator_tree,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@needs_node
def test_the_script_refuses_when_prisma_is_only_a_dev_dependency(tmp_path: Path) -> None:
    manifest = package_json()
    manifest["devDependencies"]["prisma"] = manifest["dependencies"].pop("prisma")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    shutil.copy(PACKAGE_LOCK, tmp_path / "src" / "package-lock.json")
    result = run_script(tmp_path / "src", tmp_path / "out")
    assert result.returncode != 0
    assert "production dependency" in result.stderr


@needs_node
def test_the_script_refuses_an_override_it_cannot_copy_verbatim(tmp_path: Path) -> None:
    manifest = package_json()
    manifest["overrides"]["deepmerge-ts"] = "$prisma"
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "package.json").write_text(json.dumps(manifest), encoding="utf-8")
    shutil.copy(PACKAGE_LOCK, tmp_path / "src" / "package-lock.json")
    result = run_script(tmp_path / "src", tmp_path / "out")
    assert result.returncode != 0
    assert "deepmerge-ts" in result.stderr
