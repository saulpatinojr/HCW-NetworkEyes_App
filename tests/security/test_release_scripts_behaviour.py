"""The release and cleanup scripts, run against stub data (no registry, no GitHub, no cosign is contacted).

``tests/security/test_publish_workflow_safety.py`` pins the shape of the workflows; this file runs the logic they
call, because a pin cannot show that a jq filter, a path glob or a "not found" test does what it claims:

* ``scripts/ci/paths_touch_build.py``: which changed files make ``200-build-images.yml`` build;
* ``scripts/ci/registry_digest.sh``: "the tag does not exist" and "I could not ask" are different answers;
* ``scripts/ci/find_release_image.sh``: the search for the image to promote, including the head of main being the
  manifest-only commit every successful 200 ends with;
* ``scripts/ci/manifest_tags.sh``: the tags 370 protects, and only those of the configured repository;
* ``scripts/ci/verify_signed_digest.sh``: the signature, subject, builder and revision checks, with a stub
  ``cosign`` that records how it was called.

They need ``bash`` and ``jq``. GitHub's runners have both; a machine without them skips these tests, and
``test_ci_has_the_tools`` fails on CI if either is missing so a skip can never hide there.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CI_DIR = REPO_ROOT / "scripts" / "ci"
BUILD_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "200-build-images.yml"
BASH = shutil.which("bash")
JQ = shutil.which("jq")
needs_tools = pytest.mark.skipif(not (BASH and JQ), reason="bash and jq are required")

NAMESPACE = "hybridcloudworks"
REPOSITORY = "img-ne-appliance-app"
IMAGE = f"docker.io/{NAMESPACE}/{REPOSITORY}"
HEX = "a" * 64
OTHER_HEX = "b" * 64


def test_ci_has_the_tools() -> None:
    if os.environ.get("CI") == "true":
        assert BASH and JQ, (
            "bash and jq must be on the CI runner; these tests would otherwise skip silently"
        )


def _load_paths_module():
    spec = importlib.util.spec_from_file_location(
        "paths_touch_build", CI_DIR / "paths_touch_build.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


paths_touch_build = _load_paths_module()


# --- paths_touch_build.py (pure Python, always runs) ---


class TestPathsTouchBuild:
    def setup_method(self):
        self.patterns = paths_touch_build.push_paths(BUILD_WORKFLOW.read_text(encoding="utf-8"))

    def test_it_reads_the_real_workflows_path_filter(self):
        for expected in (
            "Dockerfile",
            "cna/**",
            "apps/cna-web/**",
            "uv.lock",
            ".github/workflows/200-build-images.yml",
        ):
            assert expected in self.patterns, expected
        assert "main" not in self.patterns, "the branches list is not a path filter"

    @pytest.mark.parametrize(
        "changed",
        [
            "Dockerfile",
            "cna/core/auth.py",
            "apps/cna-web/lib/image-update-rules.ts",
            "apps/cna-api/Dockerfile",
            "scripts/ci/sign_image.sh",
            "pyproject.toml",
            "uv.lock",
            ".github/workflows/200-build-images.yml",
        ],
    )
    def test_a_file_200_builds_from_is_reported(self, changed):
        assert paths_touch_build.touching([changed], self.patterns) == [changed]

    @pytest.mark.parametrize(
        "changed",
        [
            "README.md",
            "CHANGELOG.md",
            "TODO.md",
            ".deployment-catalog/latest-build.json",
            ".github/workflows/310-release-version.yml",
            "scripts/ci/find_release_image.sh",
            "tests/security/test_image_repository_name.py",
            "docs/dockerfile.md",
            "apps/cna-api/main.py",  # apps/cna-api/** is NOT in the filter; only the Dockerfile paths listed are
        ],
    )
    def test_documentation_the_manifest_and_other_workflows_are_not(self, changed):
        patterns = [p for p in self.patterns if not p.startswith("apps/cna-api/")]
        assert paths_touch_build.touching([changed], patterns) == []

    def test_star_stays_within_a_segment_and_double_star_does_not(self):
        assert paths_touch_build.touching(["a/b.txt"], ["a/*"]) == ["a/b.txt"]
        assert paths_touch_build.touching(["a/b/c.txt"], ["a/*"]) == []
        assert paths_touch_build.touching(["a/b/c.txt"], ["a/**"]) == ["a/b/c.txt"]
        assert paths_touch_build.touching(["a/b/c.txt"], ["**/c.txt"]) == ["a/b/c.txt"]
        assert paths_touch_build.touching(["c.txt"], ["**/c.txt"]) == ["c.txt"]

    def test_the_script_exits_1_with_the_offending_files_and_0_without(self):
        run = lambda files: subprocess.run(  # noqa: E731
            [sys.executable, str(CI_DIR / "paths_touch_build.py"), str(BUILD_WORKFLOW)],
            input=files,
            capture_output=True,
            text=True,
        )
        hit = run("README.md\nDockerfile\n.deployment-catalog/latest-build.json\n")
        assert (hit.returncode, hit.stdout.split()) == (1, ["Dockerfile"])
        clean = run("README.md\n.deployment-catalog/latest-build.json\n")
        assert (clean.returncode, clean.stdout) == (0, "")

    def test_a_workflow_without_a_path_filter_is_refused_not_guessed(self, tmp_path):
        workflow = tmp_path / "w.yml"
        workflow.write_text(
            "name: x\non:\n  push:\n    branches:\n      - main\n", encoding="utf-8"
        )
        result = subprocess.run(
            [sys.executable, str(CI_DIR / "paths_touch_build.py"), str(workflow)],
            input="a\n",
            capture_output=True,
            text=True,
        )
        assert result.returncode == 2 and "refusing to guess" in result.stderr


# --- helpers for the shell scripts ---


def _stub(bin_dir: Path, name: str, body: str) -> None:
    path = bin_dir / name
    path.write_text("#!/usr/bin/env bash\n" + body + "\n", encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)


def _env(bin_dir: Path, **extra: str) -> dict[str, str]:
    # The scripts call `python3`; a machine whose `python3` is missing or is a launcher stub gets the test's own.
    _stub(bin_dir, "python3", f'exec "{sys.executable}" "$@"')
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    env.update(extra)
    return env


def _run(script: str, *args: str, env: dict[str, str], cwd: Path, stdin: str | None = None):
    return subprocess.run(
        [BASH, str(CI_DIR / script), *args],
        env=env,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
    )


DOCKER_STUB = r"""
ref="" want_image=""
for a in "$@"; do case "$a" in docker.io/*) ref="$a" ;; "{{json .Image}}") want_image=1 ;; esac; done
if [ -n "${STUB_REGISTRY_ERROR:-}" ]; then echo "ERROR: $STUB_REGISTRY_ERROR" >&2; exit 1; fi
if [ -n "$want_image" ]; then cat "$STUB_IMAGE"; exit 0; fi
line="$(grep -F "$ref " "${STUB_REGISTRY:-/dev/null}" | head -n1 || true)"
if [ -z "$line" ]; then echo "ERROR: $ref: not found" >&2; exit 1; fi
echo "${line##* }"
"""


# --- registry_digest.sh ---


@needs_tools
class TestRegistryDigest:
    def _check(self, tmp_path, registry_lines: str, error: str = "", ref: str = f"{IMAGE}:1.0.0"):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _stub(bin_dir, "docker", DOCKER_STUB)
        registry = tmp_path / "registry.txt"
        registry.write_text(registry_lines, encoding="utf-8")
        env = _env(bin_dir, STUB_REGISTRY=str(registry), STUB_REGISTRY_ERROR=error)
        script = f'source "{(CI_DIR / "registry_digest.sh").as_posix()}"; registry_digest "$1"; echo "rc=$?"'
        return subprocess.run(
            [BASH, "-c", script, "_", ref], env=env, cwd=tmp_path, capture_output=True, text=True
        )

    def test_an_existing_tag_returns_its_digest(self, tmp_path):
        result = self._check(tmp_path, f"{IMAGE}:1.0.0 sha256:{HEX}\n")
        assert result.stdout.split() == [f"sha256:{HEX}", "rc=0"]

    def test_a_missing_tag_is_status_1_and_nothing_on_stdout(self, tmp_path):
        result = self._check(tmp_path, "")
        assert result.stdout.split() == ["rc=1"]

    @pytest.mark.parametrize(
        "message",
        [
            "docker.io/x/y:1: denied: requested access to the resource is denied",
            "Get https://registry-1.docker.io/v2/: dial tcp: lookup registry-1.docker.io: no such host",
            "toomanyrequests: You have reached your pull rate limit",
            "context deadline exceeded",
        ],
    )
    def test_any_other_failure_is_status_2_with_the_message_kept(self, tmp_path, message):
        result = self._check(tmp_path, "", error=message)
        assert result.stdout.split() == ["rc=2"]
        assert message in result.stderr

    @pytest.mark.parametrize(
        "message", ["x: not found", "MANIFEST_UNKNOWN: manifest unknown", "HTTP status 404"]
    )
    def test_the_registrys_not_found_wordings_are_status_1(self, tmp_path, message):
        assert self._check(tmp_path, "", error=message).stdout.split() == ["rc=1"]


# --- find_release_image.sh ---


def _git(repo: Path, *args: str) -> str:
    env = dict(
        os.environ,
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@example.com",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@example.com",
    )
    return subprocess.run(
        ["git", *args], cwd=repo, env=env, capture_output=True, text=True, check=True
    ).stdout.strip()


def _history(repo: Path, commits: list[dict[str, str]]) -> list[str]:
    """Commit each {path: content} in turn; the first one also gets the real 200 workflow. Returns the SHAs."""
    _git(repo, "init", "-q", "-b", "main")
    shas = []
    for index, files in enumerate(commits):
        if index == 0:
            workflow = repo / ".github" / "workflows" / "200-build-images.yml"
            workflow.parent.mkdir(parents=True)
            workflow.write_text(
                BUILD_WORKFLOW.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
            )
        for name, content in files.items():
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        _git(repo, "add", "-A")
        _git(repo, "commit", "-q", "-m", f"commit {index}")
        shas.append(_git(repo, "rev-parse", "HEAD"))
    return shas


@needs_tools
class TestFindReleaseImage:
    def _find(
        self, tmp_path, commits, runs, registry, target_index=-1, registry_error="", wait="0"
    ):
        repo = tmp_path / "repo"
        repo.mkdir()
        shas = _history(repo, commits)
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _stub(bin_dir, "docker", DOCKER_STUB)
        _stub(bin_dir, "gh", 'cat "$STUB_RUNS"')
        runs_file = tmp_path / "runs.json"
        rows = [
            {**{k: v for k, v in r.items() if k != "at"}, "headSha": shas[r["at"]]} for r in runs
        ]
        runs_file.write_text(json.dumps(rows), encoding="utf-8")
        registry_file = tmp_path / "registry.txt"
        registry_file.write_text(
            "".join(f"{IMAGE}:sha-{shas[i][:7]} sha256:{digest}\n" for i, digest in registry),
            encoding="utf-8",
        )
        out = tmp_path / "github_output"
        env = _env(
            bin_dir,
            STUB_RUNS=str(runs_file),
            STUB_REGISTRY=str(registry_file),
            STUB_REGISTRY_ERROR=registry_error,
            GH_TOKEN="x",
            GITHUB_REPOSITORY="o/r",
            TARGET_SHA=shas[target_index],
            DOCKERHUB_NAMESPACE=NAMESPACE,
            IMAGE_REPOSITORY=REPOSITORY,
            FIND_WAIT_SECONDS=wait,
            FIND_POLL_SECONDS="0",
            GITHUB_OUTPUT=str(out),
        )
        result = _run("find_release_image.sh", env=env, cwd=repo)
        outputs = (
            dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())
            if out.exists()
            else {}
        )
        return result, outputs, shas

    @staticmethod
    def _run_row(at, run_id, status="completed", conclusion="success"):
        return {
            "at": at,
            "databaseId": run_id,
            "status": status,
            "conclusion": conclusion,
            "url": f"https://example/{run_id}",
        }

    BUILD = {
        "Dockerfile": "FROM scratch\n",
        "README.md": "one\n",
        ".deployment-catalog/latest-build.json": '{"commit": "RECORDED"}\n',
    }

    def test_the_manifest_only_head_of_main_finds_the_build_before_it(self, tmp_path):
        # The first-release case: 200 built commit 0, and its self-merging manifest pull request added commit 1.
        commits = [self.BUILD, {".deployment-catalog/latest-build.json": '{"commit": "new"}\n'}]
        result, out, shas = self._find(tmp_path, commits, [self._run_row(0, 111)], [(0, HEX)])
        assert result.returncode == 0, result.stderr
        assert (
            out["digest"] == f"sha256:{HEX}"
            and out["build_commit"] == shas[0]
            and out["run_ids"] == "111"
        )
        assert out["tag"] == f"sha-{shas[0][:7]}"
        assert "run of its own" in result.stdout

    def test_a_documentation_only_change_after_the_build_is_accepted(self, tmp_path):
        commits = [self.BUILD, {"README.md": "two\n"}, {"CHANGELOG.md": "x\n"}]
        result, out, shas = self._find(tmp_path, commits, [self._run_row(0, 111)], [(0, HEX)])
        assert result.returncode == 0, result.stderr
        assert out["build_commit"] == shas[0]

    def test_a_change_to_a_file_200_builds_from_is_refused_naming_it_and_the_recorded_commit(
        self, tmp_path
    ):
        commits = [
            self.BUILD,
            {"Dockerfile": "FROM scratch\nLABEL x=y\n"},
            {".deployment-catalog/latest-build.json": '{"commit": "RECORDED", "n": 2}\n'},
        ]
        result, out, _ = self._find(tmp_path, commits, [self._run_row(0, 111)], [(0, HEX)])
        assert result.returncode == 1 and out == {}
        assert "Dockerfile" in result.stderr and "latest-build.json" in result.stderr
        assert "RECORDED" in result.stderr, "it tells the owner which commit to tag"

    def test_no_200_run_anywhere_fails_with_the_exact_message(self, tmp_path):
        result, out, _ = self._find(tmp_path, [self.BUILD, {"README.md": "two\n"}], [], [])
        assert result.returncode == 1 and out == {}
        assert "No run of 200-build-images.yml built an image for commit" in result.stderr
        assert "Tag the commit that 200 built" in result.stderr and "RECORDED" in result.stderr

    def test_a_finished_run_without_the_sha_tag_is_not_a_build(self, tmp_path):
        # The scan failed, publishing was off, or 370 pruned the tag: do not promote anything.
        result, out, _ = self._find(
            tmp_path, [self.BUILD], [self._run_row(0, 111, conclusion="failure")], []
        )
        assert result.returncode == 1 and out == {}
        assert "finished without the sha tag" in result.stderr

    def test_a_run_without_a_tag_is_skipped_for_an_older_build_when_the_path_check_allows_it(
        self, tmp_path
    ):
        # Commit 1 has a (rehearsal) run and no image; commit 0 has the image; nothing 200 builds from changed.
        commits = [self.BUILD, {"README.md": "two\n"}, {"CHANGELOG.md": "x\n"}]
        runs = [self._run_row(0, 111), self._run_row(1, 222)]
        result, out, shas = self._find(tmp_path, commits, runs, [(0, HEX)])
        assert result.returncode == 0, result.stderr
        assert out["build_commit"] == shas[0] and out["run_ids"] == "111"

    def test_the_tagged_commit_itself_built_needs_no_path_check(self, tmp_path):
        commits = [self.BUILD, {"Dockerfile": "FROM scratch\nLABEL x=y\n"}]
        runs = [self._run_row(0, 111), self._run_row(1, 222)]
        result, out, shas = self._find(tmp_path, commits, runs, [(0, HEX), (1, OTHER_HEX)])
        assert result.returncode == 0, result.stderr
        assert out["build_commit"] == shas[1] and out["digest"] == f"sha256:{OTHER_HEX}"

    def test_a_registry_error_is_not_read_as_no_image(self, tmp_path):
        result, out, _ = self._find(
            tmp_path,
            [self.BUILD],
            [self._run_row(0, 111)],
            [(0, HEX)],
            registry_error="denied: requested access",
        )
        assert result.returncode == 1 and out == {}
        assert "refusing to guess" in result.stderr

    def test_a_build_still_running_is_waited_for_then_reported(self, tmp_path):
        row = self._run_row(0, 111, status="in_progress", conclusion="")
        result, out, _ = self._find(tmp_path, [self.BUILD], [row], [])
        assert result.returncode == 1 and out == {}
        assert "Waited 0 s for 200-build-images.yml to tag" in result.stderr

    def test_a_target_that_is_not_a_full_sha_is_refused(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        env = _env(
            bin_dir,
            GITHUB_REPOSITORY="o/r",
            TARGET_SHA="main",
            DOCKERHUB_NAMESPACE=NAMESPACE,
            IMAGE_REPOSITORY=REPOSITORY,
        )
        result = _run("find_release_image.sh", env=env, cwd=repo)
        assert result.returncode == 1 and "40-character" in result.stderr


# --- manifest_tags.sh ---

MANIFEST = {
    "images": {
        "cli": f"{IMAGE}:sha-1234567",
        "api": f"{IMAGE}:api-sha-1234567",
        "worker": f"docker.io/{NAMESPACE}/cna:worker-sha-1111111",
        "web": f"{IMAGE}:web-sha-1234567",
        "migrator": f"docker.io/other/{REPOSITORY}:migrator-sha-1234567",
    }
}


@needs_tools
class TestManifestTags:
    def _run(self, mode, tmp_path, manifest=None, prefix=f"{IMAGE}:"):
        return _run(
            "manifest_tags.sh",
            mode,
            prefix,
            env=dict(os.environ),
            cwd=tmp_path,
            stdin=json.dumps(manifest or MANIFEST),
        )

    def test_only_the_tags_of_the_configured_repository_are_protected(self, tmp_path):
        result = self._run("protected", tmp_path)
        assert result.returncode == 0, result.stderr
        assert result.stdout.split() == ["sha-1234567", "api-sha-1234567", "web-sha-1234567"]

    def test_entries_of_another_repository_or_namespace_are_counted_not_protected(self, tmp_path):
        assert self._run("foreign", tmp_path).stdout.strip() == "2"

    def test_a_manifest_of_the_retired_repository_protects_nothing(self, tmp_path):
        old = {"images": {k: v.replace(REPOSITORY, "cna") for k, v in MANIFEST["images"].items()}}
        assert self._run("protected", tmp_path, old).stdout.strip() == ""
        assert self._run("foreign", tmp_path, old).stdout.strip() == "5"

    def test_a_prefix_without_the_colon_is_refused(self, tmp_path):
        assert self._run("protected", tmp_path, prefix=IMAGE).returncode == 2

    def test_the_committed_manifest_can_be_read(self, tmp_path):
        committed = json.loads(
            (REPO_ROOT / ".deployment-catalog" / "latest-build.json").read_text(encoding="utf-8")
        )
        result = self._run("foreign", tmp_path, committed)
        assert result.returncode == 0 and result.stdout.strip().isdigit()


# --- verify_signed_digest.sh ---

CHECK_COMMIT = "c" * 40
RUN_ID = "111"


def _statement(digest_hex=HEX, builder=f"https://github.com/o/r/actions/runs/{RUN_ID}/attempts/1"):
    return {
        "predicateType": "https://slsa.dev/provenance/v0.2",
        "subject": [{"digest": {"sha256": digest_hex}}],
        "predicate": {"builder": {"id": builder}},
    }


def _envelope(statement) -> str:
    return json.dumps({"payload": base64.b64encode(json.dumps(statement).encode()).decode()})


@needs_tools
class TestVerifySignedDigest:
    REF = f"{IMAGE}@sha256:{HEX}"

    def _verify(
        self,
        tmp_path,
        *,
        sig_digest=HEX,
        statements=None,
        revision=CHECK_COMMIT,
        cosign_fails=False,
        run_ids=RUN_ID,
        expected_revision=CHECK_COMMIT,
        ref=None,
        repository=REPOSITORY,
        image=None,
    ):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        log = tmp_path / "cosign.log"
        _stub(
            bin_dir,
            "cosign",
            'echo "$*" >> "$COSIGN_LOG"\n'
            '[ -z "${STUB_COSIGN_FAIL:-}" ] || { echo "no matching signatures" >&2; exit 1; }\n'
            'case "$1" in verify) cat "$STUB_SIG" ;; verify-attestation) cat "$STUB_ATTEST" ;; esac',
        )
        _stub(bin_dir, "docker", DOCKER_STUB)
        (tmp_path / "sig.json").write_text(
            json.dumps(
                [{"critical": {"image": {"docker-manifest-digest": f"sha256:{sig_digest}"}}}]
            ),
            encoding="utf-8",
        )
        statements = [_statement()] if statements is None else statements
        (tmp_path / "attest.jsonl").write_text(
            "\n".join(_envelope(s) for s in statements) + "\n", encoding="utf-8"
        )
        shape = image or {
            "linux/amd64": {"config": {"Labels": {"org.opencontainers.image.revision": revision}}}
        }
        (tmp_path / "image.json").write_text(json.dumps(shape), encoding="utf-8")
        env = _env(
            bin_dir,
            COSIGN_LOG=str(log),
            STUB_SIG=str(tmp_path / "sig.json"),
            STUB_ATTEST=str(tmp_path / "attest.jsonl"),
            STUB_IMAGE=str(tmp_path / "image.json"),
            STUB_COSIGN_FAIL="1" if cosign_fails else "",
            GITHUB_SERVER_URL="https://github.com",
            GITHUB_REPOSITORY="o/r",
            IMAGE_REPOSITORY=repository,
            EXPECTED_REVISION=expected_revision,
            EXPECTED_RUN_IDS=run_ids,
        )
        result = _run("verify_signed_digest.sh", ref or self.REF, env=env, cwd=tmp_path)
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return result, calls

    def test_a_signed_attested_digest_built_from_the_commit_passes(self, tmp_path):
        result, calls = self._verify(tmp_path)
        assert result.returncode == 0, result.stderr
        assert "Verified" in result.stdout and "Revision label" in result.stdout

    def test_cosign_is_asked_for_exactly_the_200_identity_on_main_and_githubs_issuer(
        self, tmp_path
    ):
        # Mutation guard on behaviour: whatever the file's comments say, this is what cosign was called with.
        _, calls = self._verify(tmp_path)
        assert calls, "cosign was never called"
        for call in calls:
            assert (
                "--certificate-identity https://github.com/o/r/.github/workflows/200-build-images.yml@refs/heads/main"
                in call
            )
            assert "--certificate-oidc-issuer https://token.actions.githubusercontent.com" in call
            assert self.REF in call
        assert any(c.startswith("verify ") for c in calls)
        assert any(c.startswith("verify-attestation --type slsaprovenance02") for c in calls)

    def test_cosign_failing_fails_the_script(self, tmp_path):
        result, _ = self._verify(tmp_path, cosign_fails=True)
        assert result.returncode != 0 and "not signed by" in result.stderr

    def test_a_signature_on_another_digest_fails(self, tmp_path):
        result, _ = self._verify(tmp_path, sig_digest=OTHER_HEX)
        assert result.returncode != 0 and "no signature on exactly" in result.stderr

    def test_a_provenance_statement_for_another_subject_fails(self, tmp_path):
        result, _ = self._verify(tmp_path, statements=[_statement(digest_hex=OTHER_HEX)])
        assert result.returncode != 0 and "No provenance statement names" in result.stderr

    @pytest.mark.parametrize(
        "builder",
        [
            "https://github.com/o/r/actions/runs/999/attempts/1",  # a run of this repository, but not a 200 run of the commit
            "https://github.com/evil/r/actions/runs/111/attempts/1",  # another repository
            "https://github.com/o/r/actions/runs/1111/attempts/1",  # a run id that merely starts with 111
            "",
        ],
    )
    def test_a_builder_that_is_not_one_of_the_commits_runs_fails(self, tmp_path, builder):
        result, _ = self._verify(tmp_path, statements=[_statement(builder=builder)])
        assert result.returncode != 0 and "No provenance statement names" in result.stderr

    def test_any_run_of_the_repository_is_accepted_when_no_run_ids_are_given(self, tmp_path):
        result, _ = self._verify(
            tmp_path,
            run_ids="",
            statements=[_statement(builder="https://github.com/o/r/actions/runs/5/attempts/2")],
        )
        assert result.returncode == 0, result.stderr

    def test_a_revision_label_of_another_commit_fails(self, tmp_path):
        result, _ = self._verify(tmp_path, revision="d" * 40)
        assert result.returncode != 0 and "revision label" in result.stderr

    def test_the_revision_is_not_checked_when_none_is_expected(self, tmp_path):
        result, _ = self._verify(tmp_path, revision="d" * 40, expected_revision="")
        assert result.returncode == 0, result.stderr

    def test_a_single_platform_image_config_is_read_too(self, tmp_path):
        shape = {"config": {"Labels": {"org.opencontainers.image.revision": CHECK_COMMIT}}}
        assert self._verify(tmp_path, image=shape)[0].returncode == 0

    def test_an_image_with_no_revision_label_fails(self, tmp_path):
        result, _ = self._verify(tmp_path, image={"linux/amd64": {"config": {"Labels": {}}}})
        assert result.returncode != 0 and "revision label" in result.stderr

    @pytest.mark.parametrize(
        "ref", [f"docker.io/{NAMESPACE}/cna@sha256:{HEX}", f"{IMAGE}:1.0.0", f"{IMAGE}@sha256:abc"]
    )
    def test_a_reference_that_is_not_a_digest_of_the_configured_repository_is_refused(
        self, tmp_path, ref
    ):
        result, calls = self._verify(tmp_path, ref=ref)
        assert result.returncode == 1 and calls == []
