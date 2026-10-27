"""Regression tests for the three repository-guardrail scripts.

Closes TODO.md T-406: the scripts wired into the `repository-guardrails` CI job
had no tests, so their failure modes were unverified. Each script is invoked as
a subprocess against a fixture repository built in tmp_path, which exercises the
real entry point — including the `sys.exit` in `__main__` — rather than an
importable slice of it.

The documentation-model cases also cover T-605 (missing required documents),
T-606 (mixed-case and non-.md documents), and T-608 (untracked build artifacts). Since
2026-10-27 they also cover the docs/ folder (REVIEW.md R-031): which paths are allowed at any
depth, which lookalikes are refused, and that the removed working document cannot come back.
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
        """No docs/ folder is needed: nothing under docs/ is required to exist."""
        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr
        assert "Documentation model OK" in result.stdout
        assert "0 under docs/" in result.stdout

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
            # T-606: every document suffix and any letter case is a document, wherever it sits
            # outside the places the model allows.
            "ROADMAP.md",
            "NOTES.Md",
            "doc/ROADMAP.MD",
            "documentation/NOTES.markdown",
            "Docs/PLAN.rst",
            "src/docs/PLAN.adoc",
            "scripts/GUIDE.md",
            # The working document that was removed on 2026-10-27 may not come back at the root.
            "CNA-0.90-updates.md",
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

    @pytest.mark.parametrize(
        "page",
        [
            "docs/README.md",
            "docs/GUIDE.md",
            # The same document suffixes the validator recognises everywhere else, in any case.
            "docs/ROADMAP.MD",
            "docs/NOTES.markdown",
            "docs/PLAN.rst",
            "docs/PLAN.adoc",
            # Any depth below docs/.
            "docs/adr/0001-record-decisions.md",
            "docs/runbooks/azure/rotate-a-token.md",
            "docs/a/b/c/d/e/deep.md",
            # A folder that happens to be called docs inside docs/ is only a subfolder.
            "docs/docs/inner.md",
            "docs/docs/docs/innermost.md",
            # Names that are only special in .github/ are ordinary pages when deeper in docs/.
            "docs/runbooks/SECURITY.md",
            "docs/guides/ISSUE_TEMPLATE/bug.md",
        ],
    )
    def test_allows_documents_under_the_docs_folder(self, fixture_repo: Path, page: str) -> None:
        """REVIEW.md R-031 (docs-folder, 2026-10-27): long-form documentation lives in docs/."""
        target = fixture_repo / page
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# page\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr
        assert "1 under docs/" in result.stdout

    @pytest.mark.parametrize(
        "lookalike",
        [
            # The folder name is compared exactly: other spellings are other folders.
            "doc/GUIDE.md",
            "Docs/GUIDE.md",
            "DOCS/GUIDE.md",
            "documentation/GUIDE.md",
            "docs-old/GUIDE.md",
            "docs_archive/GUIDE.md",
            # docs/ is the top-level folder only: a second home next to the code is a second
            # source of truth. (A docs folder inside docs/ itself is a subfolder and is allowed.)
            "src/docs/GUIDE.md",
            "apps/network-assessment-web/docs/GUIDE.md",
            "packages/engine/docs/adr/0001.md",
            ".github/docs/GUIDE.md",
            "scripts/docs/GUIDE.md",
            # A root file is judged by the root list, whatever it is called.
            "docs.md",
            "DOCS.md",
            "documentation.md",
        ],
    )
    def test_rejects_lookalikes_of_the_docs_folder(
        self, fixture_repo: Path, lookalike: str
    ) -> None:
        target = fixture_repo / lookalike
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# lookalike\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert lookalike in result.stderr.replace("\\", "/")

    def test_names_in_docs_do_not_hide_a_violation_elsewhere(self, fixture_repo: Path) -> None:
        for path in ("docs/GUIDE.md", "src/docs/GUIDE.md"):
            target = fixture_repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# page\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        report = result.stderr.replace("\\", "/")
        assert "src/docs/GUIDE.md" in report
        assert "  docs/GUIDE.md" not in report

    def test_files_that_are_not_documents_in_docs_are_not_the_validators_business(
        self, fixture_repo: Path
    ) -> None:
        """docs/roles/*.json exists today: only document suffixes are ever scanned."""
        for path in ("docs/roles/role.json", "docs/diagram.drawio", "docs/img/logo.png"):
            target = fixture_repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("not a document\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr
        assert "0 under docs/" in result.stdout

    def test_a_page_in_docs_does_not_stand_in_for_a_required_root_document(
        self, fixture_repo: Path
    ) -> None:
        (fixture_repo / "TODO.md").unlink()
        (fixture_repo / "docs").mkdir()
        (fixture_repo / "docs" / "TODO.md").write_text("# TODO\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "required document(s) missing" in result.stderr

    @pytest.mark.parametrize(
        "reserved",
        [
            # Names GitHub documents as readable from docs/ as well as .github/ (the text of the pages
            # "Creating a default community health file", "Creating a pull request template", "Adding a
            # code of conduct", "Setting guidelines for repository contributors", "Adding support
            # resources" and "Adding an accessibility page", read 2026-10-27): a copy here could be shown
            # as the repository's own policy. Ticket #247 keeps them in .github/.
            "docs/SECURITY.md",
            "docs/CONTRIBUTING.md",
            "docs/CODE_OF_CONDUCT.md",
            "docs/SUPPORT.md",
            "docs/ACCESSIBILITY.md",
            "docs/accessibility.md",
            "docs/PULL_REQUEST_TEMPLATE.md",
            "docs/pull_request_template.md",
            "docs/PULL_REQUEST_TEMPLATE/release.md",
            "docs/security.md",
            # Refused as this repository's choice, not because GitHub reads them from docs/: the same
            # pages document only .github/FUNDING.yml and .github/ISSUE_TEMPLATE/. Kept refused so that
            # docs/ holds no second copy of anything .github/ holds.
            "docs/FUNDING.md",
            "docs/ISSUE_TEMPLATE/bug.md",
            "docs/issue_template/bug.md",
        ],
    )
    def test_rejects_the_community_file_names_directly_in_docs(
        self, fixture_repo: Path, reserved: str
    ) -> None:
        target = fixture_repo / reserved
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# reserved\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert reserved in result.stderr.replace("\\", "/")

    def test_a_community_file_name_in_docs_gets_its_own_hint_not_move_it_into_docs(
        self, fixture_repo: Path
    ) -> None:
        """The file is already in docs/, so 'move long-form content into docs/' would be wrong advice."""
        (fixture_repo / "docs").mkdir()
        (fixture_repo / "docs" / "SECURITY.md").write_text("# policy\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        report = result.stderr.replace("\\", "/")
        assert "  docs/SECURITY.md" in report
        assert "Files inside docs/ named like a GitHub community file" in report
        assert "Rename the page" in report
        assert ".github/" in report
        # The generic hint is for files outside docs/ and would be wrong here.
        assert "Move long-form content into docs/" not in report
        assert "Document files in a place the model does not allow" not in report

    def test_a_file_outside_docs_keeps_the_move_it_into_docs_hint(self, fixture_repo: Path) -> None:
        (fixture_repo / "doc").mkdir()
        (fixture_repo / "doc" / "GUIDE.md").write_text("# guide\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        report = result.stderr.replace("\\", "/")
        assert "  doc/GUIDE.md" in report
        assert "Move long-form content into docs/" in report
        assert "Files inside docs/ named like a GitHub community file" not in report
        assert "Rename the page" not in report

    def test_both_kinds_of_violation_each_get_their_own_hint(self, fixture_repo: Path) -> None:
        for path in ("doc/GUIDE.md", "docs/CONTRIBUTING.md"):
            target = fixture_repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("# page\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        report = result.stderr.replace("\\", "/")
        outside_at = report.index("Document files in a place the model does not allow")
        inside_at = report.index("Files inside docs/ named like a GitHub community file")
        assert outside_at < report.index("  doc/GUIDE.md") < inside_at
        assert inside_at < report.index("  docs/CONTRIBUTING.md")
        assert "Move long-form content into docs/" in report
        assert "Rename the page" in report

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
        """T-604: `.claude/`, `.agents/`, `.codex/`, `.kiro/` are configuration, not documentation."""
        for vendored in (".claude", ".agents", ".codex", ".kiro"):
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

    @pytest.mark.parametrize(
        "community_file",
        [
            ".github/SECURITY.md",
            ".github/CONTRIBUTING.md",
            ".github/CODE_OF_CONDUCT.md",
            ".github/PULL_REQUEST_TEMPLATE.md",
            ".github/pull_request_template.md",
            ".github/SUPPORT.md",
            ".github/FUNDING.md",
            ".github/ISSUE_TEMPLATE/bug.md",
            ".github/PULL_REQUEST_TEMPLATE/release.md",
        ],
    )
    def test_allows_each_community_health_file_where_github_reads_it(
        self, fixture_repo: Path, community_file: str
    ) -> None:
        """Ticket #247: the community files live in `.github/`, not at the root, and the guard allows exactly those."""
        target = fixture_repo / community_file
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# community file\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr

    def test_issue_forms_are_yaml_and_are_not_documents(self, fixture_repo: Path) -> None:
        forms = fixture_repo / ".github" / "ISSUE_TEMPLATE"
        forms.mkdir(parents=True)
        for name in ("bug_report.yml", "feature_request.yml", "config.yml"):
            (forms / name).write_text("name: form\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize(
        "misplaced",
        [
            # The same names are only community files when they sit directly in .github/.
            "SECURITY.md",
            "CONTRIBUTING.md",
            "CODE_OF_CONDUCT.md",
            "PULL_REQUEST_TEMPLATE.md",
            "docs/SECURITY.md",
            ".github/docs/SECURITY.md",
            ".github/workflows/SECURITY.md",
            # Any other markdown under .github/ is still documentation sprawl.
            ".github/copilot-instructions.md",
            ".github/README.md",
            ".github/skills/review/SKILL.md",
            ".github/ISSUE_TEMPLATE/nested/bug.md",
            "ISSUE_TEMPLATE/bug.md",
            "docs/ISSUE_TEMPLATE/bug.md",
        ],
    )
    def test_rejects_community_names_and_github_markdown_in_other_places(
        self, fixture_repo: Path, misplaced: str
    ) -> None:
        target = fixture_repo / misplaced
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# misplaced\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert misplaced in result.stderr.replace("\\", "/")

    def test_failure_message_names_every_place_a_document_is_allowed(
        self, fixture_repo: Path
    ) -> None:
        (fixture_repo / "doc").mkdir()
        (fixture_repo / "doc" / "GUIDE.md").write_text("# guide\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "docs/" in result.stderr
        assert "REFACTOR_APP.md" in result.stderr
        assert ".github/ISSUE_TEMPLATE/" in result.stderr
        assert "CODE_OF_CONDUCT.md" in result.stderr
        # The retired document and the retired destination are no longer offered as options.
        assert "CNA-0.90-updates.md" not in result.stderr
        assert "R-031" not in result.stderr
        assert "no destination" not in result.stderr

    def test_reports_failures_on_stderr(self, fixture_repo: Path) -> None:
        """T-607: failures went to stdout while the sibling shape-catalog guard used stderr."""
        (fixture_repo / "doc").mkdir()
        (fixture_repo / "doc" / "GUIDE.md").write_text("# guide\n")
        commit_all(fixture_repo)

        result = run_script(DOC_MODEL_SCRIPT, fixture_repo)
        assert result.returncode == 1
        assert "violation" in result.stderr
        assert result.stdout.strip() == ""


class TestModuleDependencies:
    def _write_module(self, repo: Path, name: str, **fields: object) -> None:
        directory = repo / "network_assessment" / "modules" / name
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
