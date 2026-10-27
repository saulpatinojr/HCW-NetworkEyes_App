"""NetworkEyes stands alone: it builds and publishes its own images and depends on nothing but this repository
and its own Docker Hub repository.

Owner decision (2026-10-25): no workflow, script, Dockerfile, application code, template or live document of this
repository may name, call, dispatch to or take a setting from the sibling appliance repositories (another owner's
repositories) or from a GitHub App installed on them. This guard keeps that from coming back:

* ``TestNoOtherRepositoryIsNamed`` scans the repository for the strings below. The scan skips history
  (``CHANGELOG.md``, ``CNA-0.90-updates.md``), the tests (they may spell a forbidden string out to prove a
  guard), dependency and build directories, and this file. There is no exemption list: a live file that
  names one of the strings fails the test.
* ``TestEveryActionIsFromAnAllowedPublisher`` fails when a workflow or a local action (``*.yml`` and ``*.yaml``)
  uses an action from a publisher outside ``ALLOWED_PUBLISHERS`` or one that is not pinned to a full commit SHA.
* ``TestTheAdminAppIsUsedByTheAdminWorkflowOnly`` keeps the GitHub App token, and the ``admin-ops`` credentials
  behind it, out of every workflow except ``390-repository-admin.yml`` (``ADMIN_WORKFLOWS``).

Both checks are static reads of files; they do not prove what a workflow does when it runs.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve()

#: name -> pattern. ``APPLIANCE_`` alone is not used: it would also match the product's own runtime vocabulary
#: (``NETWORK_ASSESSMENT_APPLIANCE_CLOUD``, ``APPLIANCE_ENV``), which stays. These are the variables that named the siblings.
FORBIDDEN: dict[str, re.Pattern[str]] = {
    "saulpatino-cbts": re.compile(r"saulpatino-cbts"),
    "Work-Cloud_": re.compile(r"Work-Cloud_"),
    "APPLIANCE_REPOS/OWNER/REPO": re.compile(r"APPLIANCE_(?:REPOS|OWNER|REPO)\b"),
    "GH_APP_": re.compile(r"GH_APP_"),
    "repository_dispatch": re.compile(r"repository_dispatch"),
    "cna-image-published": re.compile(r"cna-image-published"),
    "CORE_REPO": re.compile(r"CORE_REPO\b"),
    "IMAGE_SIGNING_IDENTITY": re.compile(r"IMAGE_SIGNING_IDENTITY"),
}

#: History, never scanned.
HISTORY_FILES = frozenset({"CHANGELOG.md", "CNA-0.90-updates.md"})
#: Generated directories, skipped at any depth.
GENERATED_DIRECTORIES = frozenset(
    {"node_modules", ".next", "__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache"}
)
#: Directories skipped ONLY at these repository-root paths (a directory of the same name elsewhere, for example
#: ``apps/x/tests`` or ``packages/y/dist`` that is checked in, is scanned like any other).
SKIPPED_PATHS = frozenset(
    {
        ".git",
        ".venv",
        ".qlty",
        "local",  # vendored agent configuration, gitignored
        "tests",  # tests may spell a string out to prove a guard; the web tier has its own (standalone-boundary.test.ts)
        "dist",
        "coverage",
        "apps/network-assessment-web/coverage",  # test output of the web tier, gitignored
        "apps/network-assessment-web/dist",
    }
)
SKIPPED_FILES = frozenset({"uv.lock", "package-lock.json"})
#: The web tier's own guard spells the strings out on purpose.
GUARD_FILES = frozenset({"apps/network-assessment-web/lib/standalone-boundary.test.ts"})
MAX_BYTES = 2_000_000

#: Publishers whose actions workflows may use. Every other publisher fails the second guard. Add one only with the
#: reason in the pull request: an action is code that runs with this repository's token.
ALLOWED_PUBLISHERS = frozenset(
    {
        "actions",  # checkout, cache, setup-python, artifacts, dependency-review, create-github-app-token (390 only)
        "docker",  # buildx, login, metadata, build-push, scout
        "sigstore",  # cosign-installer
        "softprops",  # 310 creates the GitHub Release
    }
)

#: The only workflows that may mint a GitHub App token or read the `admin-ops` credentials. 390 is the owner-approved
#: repository-admin workflow (branch and tag rules, branch clean-up, the board); it keeps APP_CLIENT_ID,
#: APP_PRIVATE_KEY and PROJECT_TOKEN in the environment `admin-ops`. No build, test, release or cleanup workflow uses them.
ADMIN_WORKFLOWS = frozenset({"390-repository-admin.yml"})
ADMIN_ONLY_TOKENS = (
    "create-github-app-token",
    "APP_CLIENT_ID",
    "APP_PRIVATE_KEY",
    "PROJECT_TOKEN",
    "admin-ops",
)


def _is_text(raw: bytes) -> bool:
    return b"\x00" not in raw


def _scanned_files() -> list[Path]:
    files = []
    for directory, subdirectories, names in os.walk(REPO_ROOT):
        # Prune before descending: node_modules and .venv are large and never scanned.
        here = Path(directory).relative_to(REPO_ROOT).as_posix()
        subdirectories[:] = sorted(
            d
            for d in subdirectories
            if d not in GENERATED_DIRECTORIES
            and (d if here == "." else f"{here}/{d}") not in SKIPPED_PATHS
        )
        for filename in sorted(names):
            path = Path(directory) / filename
            name = path.relative_to(REPO_ROOT).as_posix()
            if (
                path.resolve() == THIS_FILE
                or name in HISTORY_FILES
                or name in GUARD_FILES
                or filename in SKIPPED_FILES
            ):
                continue
            if path.stat().st_size > MAX_BYTES:
                continue
            files.append(path)
    return files


def violations_in(text: str) -> set[str]:
    return {name for name, pattern in FORBIDDEN.items() if pattern.search(text)}


def occurrences_in(text: str) -> dict[str, int]:
    """Token -> number of occurrences, for the tokens that occur."""
    counts = {name: len(pattern.findall(text)) for name, pattern in FORBIDDEN.items()}
    return {name: n for name, n in counts.items() if n}


def _found() -> dict[str, dict[str, int]]:
    found: dict[str, dict[str, int]] = {}
    for path in _scanned_files():
        raw = path.read_bytes()
        if not _is_text(raw):
            continue
        hit = occurrences_in(raw.decode("utf-8", errors="replace"))
        if hit:
            found[path.relative_to(REPO_ROOT).as_posix()] = hit
    return found


class TestNoOtherRepositoryIsNamed:
    def test_the_scan_reads_the_places_it_guards(self):
        # A guard whose walk silently stopped finding files would pass for the wrong reason.
        names = {p.relative_to(REPO_ROOT).as_posix() for p in _scanned_files()}
        for expected in (
            ".github/workflows/200-build-images.yml",
            ".github/workflows/310-release-version.yml",
            ".github/workflows/370-registry-cleanup.yml",
            "scripts/ci/sign_image.sh",
            "Dockerfile",
            "apps/network-assessment-api/Dockerfile",
            "apps/network-assessment-web/lib/image-update.ts",
            "network_assessment/core/auth.py",
            ".env.example",
            "README.md",
            "CLAUDE.md",
        ):
            assert expected in names, expected
        assert len(names) > 200
        assert "CHANGELOG.md" not in names

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("https://github.com/saulpatino-cbts/x", {"saulpatino-cbts"}),
            ("Work-Cloud_Network_Azure_Appliance", {"Work-Cloud_"}),
            ("vars.APPLIANCE_OWNER", {"APPLIANCE_REPOS/OWNER/REPO"}),
            ("vars.APPLIANCE_REPOS != ''", {"APPLIANCE_REPOS/OWNER/REPO"}),
            ("NETWORK_ASSESSMENT_APPLIANCE_REPO", {"APPLIANCE_REPOS/OWNER/REPO"}),
            ("secrets.GH_APP_ID", {"GH_APP_"}),
            ("secrets.GH_APP_PRIVATE_KEY", {"GH_APP_"}),
            ("on: repository_dispatch", {"repository_dispatch"}),
            ("event_type: cna-image-published", {"cna-image-published"}),
            ("vars.CORE_REPO", {"CORE_REPO"}),
            ("vars.IMAGE_SIGNING_IDENTITY", {"IMAGE_SIGNING_IDENTITY"}),
        ],
    )
    def test_the_matchers_catch_each_forbidden_name(self, text, expected):
        assert violations_in(text) == expected

    @pytest.mark.parametrize(
        "text",
        [
            "NETWORK_ASSESSMENT_APPLIANCE_CLOUD=azure",  # the product's own runtime vocabulary stays
            "APPLIANCE_ENV = 'NETWORK_ASSESSMENT_APPLIANCE_CLOUD'",
            "NETWORK_ASSESSMENT_EDITION=appliance",
            "final-appliance",
            "img-ne-appliance-app",
            "CORE_REPOSITORY",
            "workflow_dispatch",  # a manual trigger is not a cross-repository dispatch
            "the engine-v* release",  # downstream editions pull it; this repository does not call them
        ],
    )
    def test_the_matchers_leave_the_products_own_vocabulary_alone(self, text):
        assert violations_in(text) == set()

    def test_nothing_names_a_sibling_repository_or_its_settings(self):
        found = _found()
        assert found == {}, (
            "NetworkEyes stands alone: remove these references (file: token: occurrences): "
            + repr(found)
        )

    def test_occurrences_are_counted_per_token(self):
        text = "Work-Cloud_A and Work-Cloud_B, saulpatino-cbts/x, GH_APP_ID GH_APP_ID GH_APP_ID"
        assert occurrences_in(text) == {"Work-Cloud_": 2, "saulpatino-cbts": 1, "GH_APP_": 3}

    def test_directories_are_pruned_at_the_repository_root_only(self, monkeypatch, tmp_path):
        for relative in (
            "tests/a.txt",  # root tests: skipped
            "apps/x/tests/b.txt",  # a checked-in directory of the same name elsewhere: scanned
            "dist/c.txt",  # root dist: skipped
            "packages/y/dist/d.txt",  # scanned
            "coverage/e.txt",  # root coverage: skipped
            "apps/network-assessment-web/coverage/f.txt",  # known path: skipped
            "apps/z/coverage/g.txt",  # scanned
            "local/h.txt",  # skipped
            "docs/local/i.txt",  # scanned
            "apps/x/node_modules/j.txt",  # generated, skipped at any depth
            "keep.txt",
        ):
            (tmp_path / relative).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / relative).write_text("x", encoding="utf-8")
        monkeypatch.setattr(sys.modules[__name__], "REPO_ROOT", tmp_path)
        scanned = {p.relative_to(tmp_path).as_posix() for p in _scanned_files()}
        assert scanned == {
            "apps/x/tests/b.txt",
            "packages/y/dist/d.txt",
            "apps/z/coverage/g.txt",
            "docs/local/i.txt",
            "keep.txt",
        }

    def test_the_publishing_workflows_name_no_repository_list_and_no_stored_docker_token(self):
        for name in ("200-build-images.yml", "310-release-version.yml", "370-registry-cleanup.yml"):
            text = (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")
            assert "repositories:" not in text, name
            assert "secrets.DOCKERHUB_TOKEN" not in text, name

    def test_docker_hub_is_reached_through_the_oidc_connection_only(self):
        text = (REPO_ROOT / ".github" / "workflows" / "200-build-images.yml").read_text(
            encoding="utf-8"
        )
        assert "secrets.DOCKERHUB_TOKEN" not in text
        assert "DOCKERHUB_OIDC_CONNECTIONID: ${{ vars.DOCKERHUB_CONNECTION }}" in text


_USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(?P<ref>[^\s#]+)", re.MULTILINE)
_PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def action_references(text: str) -> list[str]:
    return [m.group("ref").strip("\"'") for m in _USES.finditer(text)]


def publisher_problems(ref: str) -> list[str]:
    """Why ``ref`` (the value of a ``uses:``) is not acceptable; empty when it is."""
    if ref.startswith("./"):
        return []
    publisher = ref.split("/", 1)[0]
    problems = []
    if publisher not in ALLOWED_PUBLISHERS:
        problems.append(f"publisher '{publisher}' is not in ALLOWED_PUBLISHERS")
    if not _PINNED.match(ref):
        problems.append("not pinned to a full 40-character commit SHA")
    return problems


def _workflow_files(root: Path | None = None) -> list[Path]:
    """Every workflow and local action file: both extensions GitHub accepts."""
    github = (root or REPO_ROOT) / ".github"
    patterns = ("workflows/*.yml", "workflows/*.yaml", "actions/**/*.yml", "actions/**/*.yaml")
    return sorted({path for pattern in patterns for path in github.glob(pattern)})


def admin_problems(name: str, text: str) -> list[str]:
    """Admin-app tokens used by a workflow that is not in ADMIN_WORKFLOWS."""
    if name in ADMIN_WORKFLOWS:
        return []
    return [token for token in ADMIN_ONLY_TOKENS if token in text]


class TestTheAdminAppIsUsedByTheAdminWorkflowOnly:
    @pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
    def test_only_the_admin_workflow_mints_an_app_token_or_reads_the_admin_credentials(self, path):
        assert admin_problems(path.name, path.read_text("utf-8")) == []

    def test_the_admin_workflow_is_the_one_user_and_stays_so(self):
        # If 390 stopped using the App, APP_CLIENT_ID / APP_PRIVATE_KEY / PROJECT_TOKEN (environment admin-ops)
        # would be deletable too; this fails so that the allow-list and the deletion list are revisited together.
        text = (REPO_ROOT / ".github" / "workflows" / "390-repository-admin.yml").read_text("utf-8")
        for token in (
            "create-github-app-token",
            "APP_CLIENT_ID",
            "APP_PRIVATE_KEY",
            "PROJECT_TOKEN",
            "admin-ops",
        ):
            assert token in text, token
        assert ADMIN_WORKFLOWS == {"390-repository-admin.yml"}

    @pytest.mark.parametrize(
        "text",
        [
            "uses: actions/create-github-app-token@" + "a" * 40,
            "client-id: ${{ vars.APP_CLIENT_ID }}",
            "private-key: ${{ secrets.APP_PRIVATE_KEY }}",
            "token: ${{ secrets.PROJECT_TOKEN }}",
            "environment: admin-ops",
        ],
    )
    def test_the_check_flags_each_admin_token_outside_the_admin_workflow(self, text):
        assert admin_problems("200-build-images.yml", text)
        assert admin_problems("390-repository-admin.yml", text) == []

    def test_the_old_app_secrets_are_named_nowhere_outside_history_and_the_pending_docs(self):
        # GH_APP_ID / GH_APP_PRIVATE_KEY are covered by the FORBIDDEN scan above (token `GH_APP_`).
        assert "GH_APP_" in FORBIDDEN


class TestEveryActionIsFromAnAllowedPublisher:
    def test_the_scan_sees_the_workflows_and_their_actions(self):
        refs = [r for path in _workflow_files() for r in action_references(path.read_text("utf-8"))]
        assert len(refs) > 40
        assert {"actions", "docker", "sigstore", "softprops"} <= {r.split("/")[0] for r in refs}

    @pytest.mark.parametrize("path", _workflow_files(), ids=lambda p: p.name)
    def test_every_uses_is_local_or_an_allowed_pinned_action(self, path):
        problems = {
            ref: publisher_problems(ref)
            for ref in action_references(path.read_text("utf-8"))
            if publisher_problems(ref)
        }
        assert problems == {}

    @pytest.mark.parametrize(
        ("ref", "ok"),
        [
            ("./.github/actions/anything", True),
            ("actions/checkout@" + "3" * 40, True),
            ("docker/login-action@" + "d" * 40, True),
            ("sigstore/cosign-installer@" + "6" * 40, True),
            ("softprops/action-gh-release@" + "e" * 40, True),
            ("peter-evans/create-pull-request@" + "a" * 40, False),  # not used any more
            (
                "saulpatino-cbts/x/.github/workflows/y.yml@" + "a" * 40,
                False,
            ),  # a sibling's reusable workflow
            ("evil/action@" + "a" * 40, False),
            ("actions/checkout@v4", False),  # a tag moves
            ("actions/checkout@main", False),
            ("docker/login-action", False),
        ],
    )
    def test_the_check_accepts_only_allowed_pinned_publishers(self, ref, ok):
        assert (publisher_problems(ref) == []) is ok

    def test_both_yaml_extensions_are_scanned_in_workflows_and_actions(self, tmp_path):
        github = tmp_path / ".github"
        files = {
            "workflows/a.yml": "x",
            "workflows/b.yaml": "x",
            "actions/c/action.yml": "x",
            "actions/d/e/action.yaml": "x",
            "workflows/readme.md": "x",
            "other/f.yaml": "x",
        }
        for relative, text in files.items():
            (github / relative).parent.mkdir(parents=True, exist_ok=True)
            (github / relative).write_text(text, encoding="utf-8")
        found = {p.relative_to(github).as_posix() for p in _workflow_files(tmp_path)}
        assert found == {
            "workflows/a.yml",
            "workflows/b.yaml",
            "actions/c/action.yml",
            "actions/d/e/action.yaml",
        }

    def test_a_bad_action_in_a_yaml_file_is_reported(self, tmp_path):
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        bad = tmp_path / ".github" / "workflows" / "evil.yaml"
        bad.write_text(
            "jobs:\n  j:\n    steps:\n      - uses: evil/x@" + "a" * 40 + "\n", encoding="utf-8"
        )
        refs = [
            r for p in _workflow_files(tmp_path) for r in action_references(p.read_text("utf-8"))
        ]
        assert refs == ["evil/x@" + "a" * 40]
        assert publisher_problems(refs[0]) == ["publisher 'evil' is not in ALLOWED_PUBLISHERS"]

    def test_the_matcher_finds_every_form_of_uses(self):
        text = (
            "      - uses: actions/checkout@" + "a" * 40 + "  # v7\n"
            "        uses: docker/login-action@" + "b" * 40 + "\n"
            "      - name: x\n        uses: './.github/actions/y'\n"
            '        uses: "evil/z@' + "c" * 40 + '"\n'
        )
        assert action_references(text) == [
            "actions/checkout@" + "a" * 40,
            "docker/login-action@" + "b" * 40,
            "./.github/actions/y",
            "evil/z@" + "c" * 40,
        ]
