"""Regression tests for the three repository-guardrail scripts.

Closes TODO.md T-406: the scripts wired into the `repository-guardrails` CI job
had no tests, so their failure modes were unverified. Each script is invoked as
a subprocess against a fixture repository built in tmp_path, which exercises the
real entry point — including the `sys.exit` in `__main__` — rather than an
importable slice of it.

The documentation-model cases also cover T-605 (missing required documents),
T-606 (mixed-case and non-.md documents), and T-608 (untracked build artifacts).
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO_ROOT / "scripts"

DOC_MODEL_SCRIPT = "validate_documentation_model.py"
MODULE_DEPS_SCRIPT = "validate_module_deps.py"
SHAPE_CATALOG_SCRIPT = "validate_shape_catalog.py"

REQUIRED_DOCUMENTS = ("README.md", "CHANGELOG.md", "REVIEW.md", "TODO.md")


def run_script(script_name: str, repo: Path) -> subprocess.CompletedProcess:
    """Run a guardrail script copied into `repo`, from an unrelated cwd.

    The scripts must resolve their own targets from ``__file__``; running from
    ``REPO_ROOT`` would let a script that reads relative paths accidentally pass
    by picking up this repository instead of the fixture.
    """
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / script_name)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT.parent,
    )


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """A minimal git repository with the four documents and the scripts."""
    repo = tmp_path / "fixture-repo"
    (repo / "scripts").mkdir(parents=True)

    for script in (DOC_MODEL_SCRIPT, MODULE_DEPS_SCRIPT, SHAPE_CATALOG_SCRIPT):
        source = SCRIPTS_DIR / script
        if source.exists():
            shutil.copy(source, repo / "scripts" / script)

    for name in REQUIRED_DOCUMENTS:
        (repo / name).write_text(f"# {name}\n")

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def commit_all(repo: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "change"],
        cwd=repo,
        check=True,
    )


class TestDocumentationModel:
    def test_passes_on_a_conforming_repository(self, fixture_repo: Path) -> None:
        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr
        assert "Documentation model OK" in result.stdout

    @pytest.mark.parametrize("missing", REQUIRED_DOCUMENTS)
    def test_fails_when_a_required_document_is_deleted(
        self, fixture_repo: Path, missing: str
    ) -> None:
        """T-605: the guard enforced 'at most four', so deleting all four passed."""
        (fixture_repo / missing).unlink()
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "required document(s) missing" in result.stderr
        assert missing in result.stderr

    def test_fails_when_every_required_document_is_deleted(self, fixture_repo: Path) -> None:
        for name in REQUIRED_DOCUMENTS:
            (fixture_repo / name).unlink()
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        for name in REQUIRED_DOCUMENTS:
            assert name in result.stderr

    @pytest.mark.parametrize(
        "sprawl",
        [
            "docs/GUIDE.md",
            "docs/ROADMAP.MD",
            "NOTES.Md",
            "docs/NOTES.markdown",
            "docs/PLAN.rst",
            "docs/PLAN.adoc",
        ],
    )
    def test_fails_on_documentation_sprawl(self, fixture_repo: Path, sprawl: str) -> None:
        """T-606: only lowercase `.md` was matched, so `.MD`/`.markdown`/`.rst` slipped through."""
        target = fixture_repo / sprawl
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# sprawl\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert sprawl in result.stderr.replace("\\", "/")

    def test_ignores_untracked_build_artifacts(self, fixture_repo: Path) -> None:
        """T-608: a normal `pytest` run wrote .pytest_cache/README.md and broke the guard."""
        cache = fixture_repo / ".pytest_cache"
        cache.mkdir()
        (cache / "README.md").write_text("# pytest cache\n")
        (fixture_repo / ".gitignore").write_text(".pytest_cache/\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr

    def test_ignores_vendored_agent_configuration(self, fixture_repo: Path) -> None:
        """T-604: `.claude/`, `.agents/`, `.codex/` are configuration, not documentation."""
        for vendored in (".claude", ".agents", ".codex"):
            directory = fixture_repo / vendored / "skills"
            directory.mkdir(parents=True)
            (directory / "SKILL.md").write_text("# vendored\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr

    def test_allows_platform_required_github_documents(self, fixture_repo: Path) -> None:
        github = fixture_repo / ".github" / "ISSUE_TEMPLATE"
        github.mkdir(parents=True)
        (github / "bug.md").write_text("# bug\n")
        (fixture_repo / ".github" / "SECURITY.md").write_text("# security\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr

    def test_reports_failures_on_stderr(self, fixture_repo: Path) -> None:
        """T-607: failures went to stdout while the sibling shape-catalog guard used stderr."""
        (fixture_repo / "docs").mkdir()
        (fixture_repo / "docs" / "GUIDE.md").write_text("# guide\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "violation" in result.stderr
        assert result.stdout.strip() == ""


class TestModuleDependencies:
    def _write_module(self, repo: Path, name: str, **fields: object) -> None:
        directory = repo / "cna" / "modules" / name
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "module.yaml").write_text(yaml.safe_dump({"name": name, **fields}))

    def test_passes_when_dependencies_are_installed(self, fixture_repo: Path) -> None:
        self._write_module(fixture_repo, "base", status="installed")
        self._write_module(fixture_repo, "leaf", status="installed", depends_on=["base"])

        result = run_script(MODULE_DEPS_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr
        assert "2 installed modules" in result.stdout

    def test_fails_on_a_missing_dependency(self, fixture_repo: Path) -> None:
        self._write_module(fixture_repo, "leaf", status="installed", depends_on=["absent"])

        result = run_script(MODULE_DEPS_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "depends on 'absent'" in result.stderr

    def test_fails_when_a_dependency_is_present_but_not_installed(self, fixture_repo: Path) -> None:
        self._write_module(fixture_repo, "base", status="available")
        self._write_module(fixture_repo, "leaf", status="installed", depends_on=["base"])

        result = run_script(MODULE_DEPS_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "depends on 'base'" in result.stderr

    def test_fails_instead_of_silently_passing_when_no_modules_exist(
        self, fixture_repo: Path
    ) -> None:
        """T-406: a relative MODULES_DIR made this report 'OK: 0 installed modules'."""
        result = run_script(MODULE_DEPS_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "modules directory not found" in result.stderr

    def test_is_independent_of_the_working_directory(
        self, fixture_repo: Path, tmp_path: Path
    ) -> None:
        """T-406: the script passed from any cwd because it resolved a relative path."""
        self._write_module(fixture_repo, "base", status="installed")
        self._write_module(fixture_repo, "leaf", status="installed", depends_on=["absent"])

        elsewhere = tmp_path / "elsewhere"
        elsewhere.mkdir()
        result = subprocess.run(
            [sys.executable, str(fixture_repo / "scripts" / MODULE_DEPS_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=elsewhere,
        )
        assert result.returncode == 1, "guard passed from an unrelated working directory"
        assert "depends on 'absent'" in result.stderr


class TestShapeCatalog:
    def test_passes_against_this_repository(self) -> None:
        """The catalog guard has no fixture seam yet; assert the real tree stays clean."""
        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / SHAPE_CATALOG_SCRIPT)],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, result.stderr or result.stdout
