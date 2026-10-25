"""The release and cleanup scripts, run against stub data (no registry, no GitHub, no cosign is contacted).

``tests/security/test_publish_workflow_safety.py`` pins the shape of the workflows; this file runs the logic they
call, because a pin cannot show that a jq filter, a path glob or a "not found" test does what it claims:

* ``scripts/ci/paths_touch_build.py``: which changed files make ``200-build-images.yml`` build;
* ``scripts/ci/registry_digest.sh``: "the tag does not exist" and "I could not ask" are different answers;
* ``scripts/ci/find_release_image.sh``: the search for the image to promote, including a tagged commit that changed
  nothing 200 builds from;
* ``scripts/ci/verify_signed_digest.sh``: the signature, subject, builder and revision checks, with a stub
  ``cosign`` that records how it was called;
* ``scripts/ci/release_digests.sh``: the other four images of the build, which the release notes list.

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
            ".github/workflows/370-registry-cleanup.yml",
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
        hit = run("README.md\nDockerfile\nscripts/ci/release_digests.sh\n")
        assert (hit.returncode, hit.stdout.split()) == (1, ["Dockerfile"])
        clean = run("README.md\nscripts/ci/release_digests.sh\n")
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
            # Look like absence but do not name the queried reference as missing: they are errors, never "free".
            "ERROR: failed to authorize: failed to fetch anonymous token: unexpected status: 404 Not Found",
            "bash: line 1: cosign: command not found",
            "HTTP status 404",
            "MANIFEST_UNKNOWN: manifest unknown",
            f'failed to resolve reference "{IMAGE}:1.0.0": failed to authorize: failed to fetch anonymous '
            "token: unexpected status from GET request to https://auth.docker.io/token: 404 Not Found",
            f"{IMAGE}:other: not found",
            "docker.io/x/y:1: not found",
        ],
    )
    def test_any_other_failure_is_status_2_with_the_message_kept(self, tmp_path, message):
        result = self._check(tmp_path, "", error=message)
        assert result.stdout.split() == ["rc=2"]
        assert message in result.stderr

    @pytest.mark.parametrize(
        "template",
        [
            "{ref}: not found",
            "ERROR: {ref}: not found",
            "ERROR: {ref}: NOT FOUND",
            "{ref}: manifest unknown",
            "ERROR: {ref}: name unknown",
        ],
    )
    def test_the_registry_naming_the_queried_reference_as_missing_is_status_1(
        self, tmp_path, template
    ):
        ref = f"{IMAGE}:1.0.0"
        result = self._check(tmp_path, "", error=template.format(ref=ref), ref=ref)
        assert result.stdout.split() == ["rc=1"]


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
    }

    def test_a_head_of_main_that_changed_no_file_200_builds_from_finds_the_build_before_it(
        self, tmp_path
    ):
        # The first-release case: 200 built commit 0; commit 1 only touched another workflow and a test.
        commits = [
            self.BUILD,
            {".github/workflows/310-release-version.yml": "x\n", "tests/test_x.py": "y\n"},
        ]
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

    def test_a_change_to_a_file_200_builds_from_is_refused_naming_it_and_the_commit_to_tag(
        self, tmp_path
    ):
        commits = [
            self.BUILD,
            {"Dockerfile": "FROM scratch\nLABEL x=y\n"},
            {"README.md": "three\n"},
        ]
        result, out, shas = self._find(tmp_path, commits, [self._run_row(0, 111)], [(0, HEX)])
        assert result.returncode == 1 and out == {}
        assert "Dockerfile" in result.stderr
        assert shas[0] in result.stderr, "it tells the owner which commit to tag"
        assert "latest-build" not in result.stderr and "manifest" not in result.stderr

    def test_no_200_run_anywhere_fails_with_the_exact_message(self, tmp_path):
        result, out, _ = self._find(tmp_path, [self.BUILD, {"README.md": "two\n"}], [], [])
        assert result.returncode == 1 and out == {}
        assert "No run of 200-build-images.yml built an image for commit" in result.stderr
        assert "Tag a commit that 200 built" in result.stderr
        assert "latest-build" not in result.stderr and "manifest" not in result.stderr

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
        signatures=None,
        emit=None,
        emit_flag="true",
    ):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        log = tmp_path / "cosign.log"
        _stub(
            bin_dir,
            "cosign",
            'echo "$*" >> "$COSIGN_LOG"\n'
            # cosign 3 warns on stderr when --output is used; the script keeps stdout and stderr apart.
            'echo "WARNING: --output is deprecated with the new bundle format" >&2\n'
            '[ -z "${STUB_COSIGN_FAIL:-}" ] || { echo "no matching signatures" >&2; exit 1; }\n'
            'case "$1" in verify) cat "$STUB_SIG" ;; verify-attestation) cat "$STUB_ATTEST" ;; esac',
        )
        _stub(bin_dir, "docker", DOCKER_STUB)
        (tmp_path / "sig.json").write_text(
            json.dumps(
                signatures
                if signatures is not None
                else [{"critical": {"image": {"docker-manifest-digest": f"sha256:{sig_digest}"}}}]
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
            **({"EMIT_BUILDER_RUN_ID": emit_flag, "GITHUB_OUTPUT": str(emit)} if emit else {}),
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

    def test_the_cosign_3_new_bundle_output_shape_is_accepted(self, tmp_path):
        # cosign 3.1.3, cmd/cosign/cli/verify/verify.go transformOutput: with the new bundle format `verify
        # --output json` prints one SimpleContainerImage per bundle found on the image (the signature bundle and
        # the attestation bundle), whose docker-manifest-digest is "<alg>:<hex>" taken from the in-toto subject and
        # whose critical.type is the predicate type.
        entry = {
            "critical": {
                "identity": {"docker-reference": f"index.docker.io/{NAMESPACE}/{REPOSITORY}"},
                "image": {"docker-manifest-digest": f"sha256:{HEX}"},
                "type": "https://sigstore.dev/cosign/sign/v1",
            },
            "optional": None,
        }
        attestation = {
            **entry,
            "critical": {**entry["critical"], "type": "https://slsa.dev/provenance/v0.2"},
        }
        result, _ = self._verify(tmp_path, signatures=[entry, attestation])
        assert result.returncode == 0, result.stderr

    def test_output_that_is_not_an_array_of_entries_is_refused(self, tmp_path):
        # cosign prints an array (one entry per signature or bundle); a lone object, or an empty array, proves nothing.
        lone = {"critical": {"image": {"docker-manifest-digest": f"sha256:{HEX}"}}}
        for shape in (lone, []):
            sub = tmp_path / type(shape).__name__
            sub.mkdir()
            result, _ = self._verify(sub, signatures=shape)
            assert result.returncode != 0 and "no signature on exactly" in result.stderr

    def test_one_bundle_naming_another_digest_fails_even_when_the_others_match(self, tmp_path):
        good = {"critical": {"image": {"docker-manifest-digest": f"sha256:{HEX}"}}}
        other = {"critical": {"image": {"docker-manifest-digest": f"sha256:{OTHER_HEX}"}}}
        result, _ = self._verify(tmp_path, signatures=[good, other])
        assert result.returncode != 0 and "no signature on exactly" in result.stderr

    def test_an_untransformed_dsse_envelope_in_the_output_is_refused(self, tmp_path):
        # If cosign could not transform a bundle it prints the raw envelope: that is not proof of a signature.
        result, _ = self._verify(
            tmp_path,
            signatures=[{"payloadType": "application/vnd.in-toto+json", "payload": "e30="}],
        )
        assert result.returncode != 0 and "no signature on exactly" in result.stderr

    def test_the_builder_run_id_is_reported_only_when_asked_for(self, tmp_path):
        out = tmp_path / "github_output"
        result, _ = self._verify(tmp_path, emit=out)
        assert result.returncode == 0, result.stderr
        assert out.read_text(encoding="utf-8").splitlines() == [f"builder_run_id={RUN_ID}"]
        quiet = tmp_path / "quiet"
        quiet.mkdir()
        out2 = quiet / "github_output"
        result, _ = self._verify(quiet, emit=out2, emit_flag="")
        assert result.returncode == 0 and not out2.exists()

    def test_nothing_is_reported_when_the_verification_fails(self, tmp_path):
        out = tmp_path / "github_output"
        result, _ = self._verify(tmp_path, emit=out, revision="d" * 40)
        assert result.returncode != 0 and not out.exists()

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


# --- release_digests.sh ---

#: component -> the prefix of its `<prefix><7 hex>` tag, as 200-build-images.yml writes them (the CLI has none).
OTHER_IMAGES = {
    "api": "api-sha-",
    "worker": "worker-sha-",
    "web": "web-sha-",
    "migrator": "migrator-sha-",
}

#: A `cosign` that signs whatever digest it is asked about, as 200 would have: the signature, and a provenance
#: statement built by run 111 of o/r naming that digest. Each call is logged.
COSIGN_FOR_ANY_DIGEST = r"""
echo "$*" >> "$COSIGN_LOG"
[ -z "${STUB_COSIGN_FAIL:-}" ] || { echo "no matching signatures" >&2; exit 1; }
ref=""; for a in "$@"; do case "$a" in docker.io/*) ref="$a" ;; esac; done; hex="${ref##*sha256:}"
case "$1" in
  verify)
    printf '[{"critical":{"image":{"docker-manifest-digest":"sha256:%s"}}}]\n' "$hex" ;;
  verify-attestation)
    stmt="$(printf '{"predicateType":"https://slsa.dev/provenance/v0.2","subject":[{"digest":{"sha256":"%s"}}],"predicate":{"builder":{"id":"https://github.com/o/r/actions/runs/111/attempts/1"}}}' "$hex")"
    printf '{"payload":"%s"}\n' "$(printf '%s' "$stmt" | base64 | tr -d '\n')" ;;
esac
"""


def _digest_of(component: str) -> str:
    return "sha256:" + {"api": "1", "worker": "2", "web": "3", "migrator": "4"}[component] * 64


@needs_tools
class TestReleaseDigests:
    COMMIT = "c" * 40

    def _run(
        self,
        tmp_path,
        *,
        missing=(),
        registry_error="",
        cosign_fails=False,
        run_ids="111",
        revision=None,
        build_commit=None,
    ):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _stub(bin_dir, "docker", DOCKER_STUB)
        _stub(bin_dir, "cosign", COSIGN_FOR_ANY_DIGEST)
        short = self.COMMIT[:7]
        registry = tmp_path / "registry.txt"
        registry.write_text(
            "".join(
                f"{IMAGE}:{prefix}{short} {_digest_of(component)}\n"
                for component, prefix in OTHER_IMAGES.items()
                if component not in missing
            ),
            encoding="utf-8",
        )
        image = tmp_path / "image.json"
        label = revision or self.COMMIT
        image.write_text(
            json.dumps(
                {
                    "linux/amd64": {
                        "config": {"Labels": {"org.opencontainers.image.revision": label}}
                    }
                }
            ),
            encoding="utf-8",
        )
        out = tmp_path / "github_output"
        log = tmp_path / "cosign.log"
        env = _env(
            bin_dir,
            COSIGN_LOG=str(log),
            STUB_REGISTRY=str(registry),
            STUB_REGISTRY_ERROR=registry_error,
            STUB_IMAGE=str(image),
            STUB_COSIGN_FAIL="1" if cosign_fails else "",
            GITHUB_SERVER_URL="https://github.com",
            GITHUB_REPOSITORY="o/r",
            GITHUB_OUTPUT=str(out),
            DOCKERHUB_NAMESPACE=NAMESPACE,
            IMAGE_REPOSITORY=REPOSITORY,
            BUILD_COMMIT=build_commit or self.COMMIT,
            RUN_IDS=run_ids,
        )
        result = _run("release_digests.sh", env=env, cwd=tmp_path)
        outputs = (
            dict(line.split("=", 1) for line in out.read_text(encoding="utf-8").splitlines())
            if out.exists()
            else {}
        )
        calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return result, outputs, calls

    def test_the_four_other_images_are_resolved_by_their_own_sha_tag_and_verified(self, tmp_path):
        result, out, calls = self._run(tmp_path)
        assert result.returncode == 0, result.stderr
        assert out == {f"digest_{c}": _digest_of(c) for c in OTHER_IMAGES}
        # Two cosign calls (signature, provenance) per image, each on exactly that digest and the 200 identity.
        assert len(calls) == 2 * len(OTHER_IMAGES)
        for component in OTHER_IMAGES:
            ref = f"{IMAGE}@{_digest_of(component)}"
            mine = [c for c in calls if f" {ref}" in c]
            assert len(mine) == 2, component
            for call in mine:
                assert (
                    "--certificate-identity https://github.com/o/r/.github/workflows/200-build-images.yml@refs/heads/main"
                    in call
                )

    def test_a_missing_tag_means_an_incomplete_build_and_stops_the_release(self, tmp_path):
        result, out, _ = self._run(tmp_path, missing=("web",))
        assert result.returncode == 1
        assert f"{IMAGE}:web-sha-{self.COMMIT[:7]} does not exist" in result.stderr
        assert "complete set" in result.stderr
        assert "digest_web" not in out and "digest_migrator" not in out

    def test_a_registry_error_is_not_read_as_a_missing_tag(self, tmp_path):
        result, out, _ = self._run(tmp_path, registry_error="denied: requested access")
        assert result.returncode == 1 and out == {}
        assert "refusing to guess" in result.stderr and "does not exist" not in result.stderr

    def test_an_image_that_does_not_verify_is_not_listed(self, tmp_path):
        result, out, _ = self._run(tmp_path, cosign_fails=True)
        assert result.returncode != 0 and out == {}
        assert "not signed by" in result.stderr

    def test_a_digest_built_by_a_run_other_than_the_commits_is_refused(self, tmp_path):
        result, out, _ = self._run(tmp_path, run_ids="999")
        assert result.returncode != 0 and out == {}
        assert "No provenance statement names" in result.stderr

    def test_an_image_built_from_another_commit_is_refused(self, tmp_path):
        result, out, _ = self._run(tmp_path, revision="d" * 40)
        assert result.returncode != 0 and out == {}
        assert "revision label" in result.stderr

    @pytest.mark.parametrize("run_ids", ["111 222", "", "abc", "111,222"])
    def test_anything_but_one_run_id_is_refused(self, tmp_path, run_ids):
        # The five images of a release must come from one workflow run (the CLI image's), not from any run of the commit.
        result, out, calls = self._run(tmp_path, run_ids=run_ids)
        assert result.returncode == 1 and out == {} and calls == []
        assert "single run id" in result.stderr

    def test_a_build_commit_that_is_not_a_full_sha_is_refused(self, tmp_path):
        result, out, calls = self._run(tmp_path, build_commit="main")
        assert result.returncode == 1 and out == {} and calls == []
        assert "40-character" in result.stderr

    def test_the_tag_prefixes_are_the_ones_200_attaches(self):
        # The script resolves `<prefix><sha7>`; 200 must create exactly those tags. A prefix changed on one side
        # only would make every release fail with "does not exist" (or, worse, verify some other image).
        import yaml

        doc = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
        matrix = {
            item["key"]: item["sha_prefix"]
            for item in doc["jobs"]["build-images"]["strategy"]["matrix"]["include"]
        }
        web_text = "\n".join(
            str(step.get("with", {}).get("tags", "")) for step in doc["jobs"]["build-web"]["steps"]
        )
        for role in ("web", "migrator"):
            assert f"type=sha,prefix={role}-sha-" in web_text, role
            matrix[role] = f"{role}-sha-"
        assert matrix["cli"] == "sha-"
        assert {k: v for k, v in matrix.items() if k != "cli"} == OTHER_IMAGES


# --- the "Verify, tag and record" step of tag-images in 200-build-images.yml ---


def _tag_images_script() -> str:
    import yaml

    doc = yaml.safe_load(BUILD_WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["tag-images"]["steps"]
    return next(s for s in steps if "Verify, tag and record" in s.get("name", ""))["run"]


COMPONENT_TAGS = {
    "cli": ["latest", "sha-abc1234"],
    "api": ["api-latest", "api-sha-abc1234"],
    "worker": ["worker-latest", "worker-sha-abc1234"],
    "web": ["web-latest", "web-sha-abc1234"],
    "migrator": ["migrator-latest", "migrator-sha-abc1234"],
}


@needs_tools
class TestTagImagesStep:
    """The step is run as bash with stubs for docker and for the verification script it calls."""

    def _run(
        self,
        tmp_path,
        *,
        bad=None,
        digests=None,
        fail_tag_call=0,
        tip="f" * 40,
        compare=None,
        compare_fail=False,
        compare_raw=None,
    ):
        digests = digests or {c: f"sha256:{str(i) * 64}" for i, c in enumerate(COMPONENT_TAGS, 1)}
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        # `docker` records each call; the Nth call (fail_tag_call) fails, as a Docker Hub error part-way would.
        _stub(
            bin_dir,
            "docker",
            'echo "$*" >> "$DOCKER_LOG"\n'
            '[ "$(wc -l < "$DOCKER_LOG")" -ne "${STUB_FAIL_CALL:-0}" ] || { echo "toomanyrequests" >&2; exit 1; }',
        )
        # `gh api repos/<repo>/commits/<branch> --jq .sha` answers STUB_TIP (empty: a failed call); `gh api
        # repos/<repo>/compare/<sha>...<tip>` answers the file STUB_COMPARE (STUB_COMPARE_FAIL: a failed call).
        _stub(
            bin_dir,
            "gh",
            'echo "$*" >> "$GH_LOG"\n'
            'case "$2" in\n'
            '  */commits/*) [ -n "${STUB_TIP:-}" ] || { echo "HTTP 502" >&2; exit 1; }; echo "$STUB_TIP" ;;\n'
            '  */compare/*) [ -z "${STUB_COMPARE_FAIL:-}" ] || { echo "HTTP 502" >&2; exit 1; }; cat "$STUB_COMPARE" ;;\n'
            "esac",
        )
        # The step reads 200's own on.push.paths through the real helper: both are copied from the repository.
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        (tmp_path / ".github" / "workflows" / "200-build-images.yml").write_text(
            BUILD_WORKFLOW.read_text(encoding="utf-8"), encoding="utf-8", newline="\n"
        )
        (tmp_path / "scripts" / "ci").mkdir(parents=True, exist_ok=True)
        (tmp_path / "scripts" / "ci" / "paths_touch_build.py").write_text(
            (CI_DIR / "paths_touch_build.py").read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\n",
        )
        compare_file = tmp_path / "compare.json"
        compare_file.write_text(json.dumps(compare or {}), encoding="utf-8")
        verify = tmp_path / "scripts" / "ci" / "verify_signed_digest.sh"
        verify.parent.mkdir(parents=True, exist_ok=True)
        if compare_raw is not None:
            compare_file.write_text(compare_raw, encoding="utf-8")
        verify.write_text(
            "#!/usr/bin/env bash\n"
            'echo "$1 revision=$EXPECTED_REVISION runs=$EXPECTED_RUN_IDS" >> "$VERIFY_LOG"\n'
            '[ -z "${STUB_BAD:-}" ] || case "$1" in *"$STUB_BAD") exit 1 ;; esac\n',
            encoding="utf-8",
            newline="\n",
        )
        summary = tmp_path / "summary.md"
        env = _env(
            bin_dir,
            DOCKER_LOG=str(tmp_path / "docker.log"),
            VERIFY_LOG=str(tmp_path / "verify.log"),
            STUB_BAD=digests[bad] if bad else "",
            STUB_FAIL_CALL=str(fail_tag_call),
            STUB_TIP=tip,
            STUB_COMPARE=str(compare_file),
            STUB_COMPARE_FAIL="1" if compare_fail else "",
            GH_LOG=str(tmp_path / "gh.log"),
            GH_TOKEN="x",
            GITHUB_REPOSITORY="o/r",
            DEFAULT_BRANCH="main",
            GITHUB_STEP_SUMMARY=str(summary),
            GITHUB_SHA="f" * 40,
            GITHUB_RUN_ID="4242",
            DOCKERHUB_NAMESPACE=NAMESPACE,
            IMAGE_REPOSITORY=REPOSITORY,
            EXPECTED_REVISION="f" * 40,
            EXPECTED_RUN_IDS="4242",
            **{f"DIGEST_{c.upper()}": d for c, d in digests.items()},
            **{
                f"TAGS_{c.upper()}": json.dumps([f"{IMAGE}:{t}" for t in COMPONENT_TAGS[c]])
                for c in COMPONENT_TAGS
            },
        )
        result = subprocess.run(
            [BASH, "-c", _tag_images_script()],
            env=env,
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

        def read(name):
            path = tmp_path / name
            return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

        return result, read("docker.log"), read("verify.log"), read("summary.md"), digests

    def test_every_digest_is_verified_then_tagged_and_the_table_lists_all_five(self, tmp_path):
        result, docker_log, verify_log, summary, digests = self._run(tmp_path)
        assert result.returncode == 0, result.stderr
        assert len(verify_log) == 5 and len(docker_log) == 5
        assert all("revision=" + "f" * 40 + " runs=4242" in line for line in verify_log)
        assert [line.split()[-1] for line in docker_log] == [
            f"{IMAGE}@{digests[c]}" for c in COMPONENT_TAGS
        ]
        assert summary[0].startswith("### Verified; tagging in progress")
        assert summary[-1] == "### All five components tagged"
        rows = [line for line in summary if line.startswith("| ") and "Component" not in line]
        rows = [line for line in rows if not line.startswith("| ---")]
        assert len(rows) == 5
        for row, component in zip(rows, COMPONENT_TAGS, strict=True):
            tags = ", ".join(f"`{t}`" for t in COMPONENT_TAGS[component])
            assert row == f"| {component} | {tags} | `{digests[component]}` | yes |"

    def test_no_tag_moves_when_one_digest_does_not_verify_and_the_table_says_no(self, tmp_path):
        result, docker_log, verify_log, summary, _ = self._run(tmp_path, bad="web")
        assert result.returncode == 1
        assert docker_log == [], "a tag was created although a digest did not verify"
        assert len(verify_log) == 5, "every digest is checked so the table names all that fail"
        assert "### NOT TAGGED: 1 of 5 digests did not verify" in summary
        assert [line for line in summary if line.startswith("| web ")][0].endswith("| no |")
        assert sum(line.endswith("| yes |") for line in summary) == 4
        assert "refusing to tag anything" in result.stdout + result.stderr

    def test_a_failure_part_way_through_tagging_still_leaves_the_record_and_no_closing_line(
        self, tmp_path
    ):
        result, docker_log, verify_log, summary, digests = self._run(tmp_path, fail_tag_call=3)
        assert result.returncode != 0
        assert len(docker_log) == 3, "two components were tagged and the third failed"
        assert summary[0].startswith("### Verified; tagging in progress")
        assert "### All five components tagged" not in summary
        rows = [line for line in summary if line.startswith("| ") and line.endswith("| yes |")]
        assert len(rows) == 5, "the table was written before the first tag moved"

    @staticmethod
    def _ahead(*files, ahead_by=1, status="ahead"):
        return {
            "status": status,
            "ahead_by": ahead_by,
            "files": [f if isinstance(f, dict) else {"filename": f} for f in files],
        }

    def _latest_moved(self, docker_log):
        return sum("-latest" in line or f"{IMAGE}:latest" in line for line in docker_log)

    def test_a_tip_that_changes_nothing_200_builds_from_still_lets_latest_move(self, tmp_path):
        # A documentation / test / other-workflow commit landed after the built commit: no newer 200 run exists,
        # so this run must move *-latest or nobody will.
        compare = self._ahead(
            "README.md", "tests/unit/test_x.py", ".github/workflows/310-release-version.yml"
        )
        result, docker_log, _, summary, _ = self._run(tmp_path, tip="a" * 40, compare=compare)
        assert result.returncode == 0, result.stderr + result.stdout
        assert len(docker_log) == 5 and self._latest_moved(docker_log) == 5
        assert summary[-1] == "### All five components tagged"
        assert any("changes nothing this workflow builds from" in line for line in summary)

    @pytest.mark.parametrize(
        "changed",
        [
            "apps/cna-web/lib/image-update.ts",
            "Dockerfile",
            "uv.lock",
            ".github/workflows/200-build-images.yml",
            {
                "filename": "docs/moved.md",
                "previous_filename": "Dockerfile",
            },  # renamed out of a build path
        ],
    )
    def test_a_tip_that_changed_a_build_path_gets_its_sha_tags_and_no_latest_tag(
        self, tmp_path, changed
    ):
        compare = self._ahead("README.md", changed)
        result, docker_log, _, summary, _ = self._run(tmp_path, tip="a" * 40, compare=compare)
        assert result.returncode == 0, result.stderr + result.stdout
        assert len(docker_log) == 5, "every component still gets its immutable sha tag"
        assert self._latest_moved(docker_log) == 0
        for line in docker_log:
            assert "sha-abc1234" in line
        assert any(
            line.startswith("The *-latest tags will NOT be moved: later commits change files")
            for line in summary
        )
        assert summary[-1].startswith("### Sha tags attached; the *-latest tags were not moved")
        assert "### All five components tagged" not in summary
        assert "NOT moved" in result.stdout + result.stderr

    @pytest.mark.parametrize("status", ["diverged", "behind", "identical"])
    def test_a_tip_that_is_not_ahead_never_moves_latest(self, tmp_path, status):
        compare = self._ahead("README.md", status=status)
        result, docker_log, *_ = self._run(tmp_path, tip="a" * 40, compare=compare)
        assert (
            result.returncode == 0 and len(docker_log) == 5 and self._latest_moved(docker_log) == 0
        )
        assert f"compare status '{status}'" in result.stdout + result.stderr

    def test_a_truncated_comparison_never_moves_latest(self, tmp_path):
        many = [f"docs/{n}.md" for n in range(300)]  # GitHub lists at most 300 files
        result, docker_log, *_ = self._run(tmp_path, tip="a" * 40, compare=self._ahead(*many))
        assert result.returncode == 0 and self._latest_moved(docker_log) == 0
        assert "too large to list completely" in result.stdout + result.stderr
        (tmp_path / "b").mkdir()
        result, docker_log, *_ = self._run(
            tmp_path / "b", tip="a" * 40, compare=self._ahead("README.md", ahead_by=251)
        )
        assert result.returncode == 0 and self._latest_moved(docker_log) == 0

    def test_just_under_the_limits_is_read_as_complete(self, tmp_path):
        files = [f"docs/{n}.md" for n in range(299)]
        result, docker_log, *_ = self._run(
            tmp_path, tip="a" * 40, compare=self._ahead(*files, ahead_by=250)
        )
        assert result.returncode == 0 and self._latest_moved(docker_log) == 5

    def test_a_failed_compare_tags_nothing(self, tmp_path):
        result, docker_log, verify_log, summary, _ = self._run(
            tmp_path, tip="a" * 40, compare_fail=True
        )
        assert result.returncode == 1 and docker_log == []
        assert "refusing to tag anything" in result.stdout + result.stderr
        assert not any("All five components tagged" in line for line in summary)

    @pytest.mark.parametrize("body", ["", "not json", "[]", '{"message": "Not Found"}'])
    def test_an_answer_without_a_status_tags_nothing(self, tmp_path, body):
        result, docker_log, *_ = self._run(tmp_path, tip="a" * 40, compare_raw=body)
        assert result.returncode == 1 and docker_log == []

    def test_every_path_of_the_workflow_is_a_build_path_for_the_guard(self, tmp_path):
        # One list, no copy: each pattern of 200's own on.push.paths, turned into a file name, must block latest.
        import importlib.util as _u

        spec = _u.spec_from_file_location("paths_touch_build_live", CI_DIR / "paths_touch_build.py")
        module = _u.module_from_spec(spec)
        spec.loader.exec_module(module)
        patterns = module.push_paths(BUILD_WORKFLOW.read_text(encoding="utf-8"))
        assert len(patterns) >= 10
        for index, pattern in enumerate(patterns):
            name = pattern.replace("**", "a/b").replace("*", "z")
            assert module.touching([name], [pattern]) == [name], pattern
            sub = tmp_path / f"p{index}"
            sub.mkdir()
            _, docker_log, *_ = self._run(sub, tip="a" * 40, compare=self._ahead(name))
            assert self._latest_moved(docker_log) == 0, pattern

    def test_the_step_holds_no_copy_of_the_build_paths(self):
        script = _tag_images_script()
        assert "paths_touch_build.py .github/workflows/200-build-images.yml" in script
        for fragment in ("apps/cna-web", "apps/cna-api", "uv.lock", "pyproject.toml", "Dockerfile"):
            assert fragment not in script, fragment

    def test_the_tip_commit_moves_the_latest_tags_too(self, tmp_path):
        result, docker_log, *_ = self._run(tmp_path)
        assert result.returncode == 0
        assert sum("-latest" in line or f"{IMAGE}:latest" in line for line in docker_log) == 5

    def test_an_unreadable_tip_tags_nothing(self, tmp_path):
        result, docker_log, verify_log, summary, _ = self._run(tmp_path, tip="")
        assert result.returncode == 1 and docker_log == []
        assert "refusing to tag anything" in result.stdout + result.stderr
        assert not any("All five components tagged" in line for line in summary)

    def test_the_tip_is_asked_of_the_default_branch_of_this_repository(self, tmp_path):
        self._run(tmp_path)
        assert (tmp_path / "gh.log").read_text(encoding="utf-8").split() == [
            "api",
            "repos/o/r/commits/main",
            "--jq",
            ".sha",
        ]

    def test_a_rerun_after_that_failure_tags_everything_again_without_error(self, tmp_path):
        # imagetools create is idempotent: the second run repeats the verification and all five creates.
        (tmp_path / "first").mkdir()
        (tmp_path / "second").mkdir()
        first = self._run(tmp_path / "first", fail_tag_call=3)
        second = self._run(tmp_path / "second")
        assert first[0].returncode != 0
        assert second[0].returncode == 0 and len(second[1]) == 5 and len(second[2]) == 5
        assert second[3][-1] == "### All five components tagged"

    def test_a_missing_digest_fails_before_anything_is_verified_or_tagged(self, tmp_path):
        digests = {c: f"sha256:{str(i) * 64}" for i, c in enumerate(COMPONENT_TAGS, 1)}
        digests["worker"] = ""
        result, docker_log, verify_log, summary, _ = self._run(tmp_path, digests=digests)
        assert result.returncode == 1 and docker_log == [] and verify_log == [] and summary == []
        assert "No valid digest for 'worker'" in result.stdout + result.stderr


# --- the "Prune stale SHA-tagged images" step of 370-registry-cleanup.yml ---

CLEANUP_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "370-registry-cleanup.yml"


def _prune_script() -> str:
    import yaml

    doc = yaml.safe_load(CLEANUP_WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["cleanup"]["steps"]
    return next(s for s in steps if "Prune stale SHA-tagged images" in s.get("name", ""))["run"]


CURL_FOR_HUB = r"""
method=GET; url=""
while [ "$#" -gt 0 ]; do
  case "$1" in
    -X) method="$2"; shift ;;
    -s|-o|-w|-H|-d) case "$1" in -o|-w|-H|-d) shift ;; esac ;;
    *) url="$1" ;;
  esac
  shift
done
if [ "$method" = DELETE ]; then
  echo "$url" >> "$DELETE_LOG"
  printf '%s' "${STUB_DELETE_STATUS:-204}"
elif [ "$method" = POST ]; then
  printf '{"access_token":"t"}\n200'
else
  cat "$STUB_TAGS"; printf '\n200'
fi
"""


def _hub_tag(name, minute, digest=None, images=()):
    return {
        "name": name,
        "last_updated": f"2026-10-25T10:{59 - minute:02d}:00Z",
        "digest": digest,
        "images": [{"digest": d} for d in images],
    }


@needs_tools
class TestPruneStep:
    """The step is run as bash with a stub `curl` that serves a Docker Hub tag list and records DELETE calls."""

    D = {n: "sha256:" + str(n) * 64 for n in range(1, 10)}

    def _tags(self):
        d = self.D
        return [
            # cli: newest first. KEEP_COUNT=2 keeps sha-a1 and sha-b2.
            _hub_tag("sha-a1", 0, d[1]),
            _hub_tag("sha-b2", 1, d[2]),
            _hub_tag("sha-c3", 2, d[3], images=[d[7]]),  # own: pruned
            _hub_tag(
                "sha-d4", 3, d[4], images=[d[8]]
            ),  # shares its index with the release tag: kept
            _hub_tag("sha-e5", 4, d[5], images=[d[9]]),  # own: pruned
            _hub_tag(
                "sha-f6", 5, d[6], images=[d[3] + "x"]
            ),  # shares only a platform image digest: kept
            _hub_tag("web-sha-1111111", 0, d[1]),
            _hub_tag("web-sha-2222222", 1, d[2]),
            _hub_tag("web-sha-3333333", 2, None),  # Hub lists no digest at all: kept
            _hub_tag("latest", 0, d[1]),
            _hub_tag("1.0.0", 9, d[4], images=[d[8], d[3] + "x"]),  # the release tag
            _hub_tag(
                "sha256-" + "a" * 64 + ".sig", 9, "sha256:" + "f" * 64
            ),  # a signature artifact, not a SHA tag
        ]

    def _run(self, tmp_path, *, dry_run="false", delete_status="204", tags=None):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _stub(bin_dir, "curl", CURL_FOR_HUB)
        page = tmp_path / "tags.json"
        page.write_text(
            json.dumps({"results": tags or self._tags(), "next": None}), encoding="utf-8"
        )
        env = _env(
            bin_dir,
            STUB_TAGS=str(page),
            DELETE_LOG=str(tmp_path / "delete.log"),
            STUB_DELETE_STATUS=delete_status,
            DOCKERHUB_NAMESPACE=NAMESPACE,
            IMAGE_REPOSITORY=REPOSITORY,
            KEEP_COUNT="2",
            DOCKERHUB_PERSONAL_USERNAME="u",
            DOCKERHUB_PERSONAL_TOKEN="t",
            DRY_RUN=dry_run,
        )
        result = subprocess.run(
            [BASH, "-c", _prune_script()], env=env, cwd=tmp_path, capture_output=True, text=True
        )
        log = tmp_path / "delete.log"
        deleted = [
            line.rstrip("/").rsplit("/", 1)[-1]
            for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else [])
        ]
        return result, deleted

    def test_only_old_unshared_sha_tags_are_deleted(self, tmp_path):
        result, deleted = self._run(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout
        assert sorted(deleted) == ["sha-c3", "sha-e5"]

    def test_a_sha_tag_sharing_the_release_tags_index_or_an_image_is_kept_and_said_so(
        self, tmp_path
    ):
        result, deleted = self._run(tmp_path)
        for kept in ("sha-d4", "sha-f6", "web-sha-3333333"):
            assert kept not in deleted
            assert f"keeping: {kept} (" in result.stdout, kept
        assert "keeping: sha-d4 (shared:" in result.stdout
        assert "keeping: web-sha-3333333 (unknown:" in result.stdout
        assert "kept 7 (3 of them because" in result.stdout

    def test_release_and_latest_tags_and_signature_artifacts_are_never_candidates(self, tmp_path):
        _, deleted = self._run(tmp_path)
        assert not {"latest", "1.0.0"} & set(deleted)
        assert not any(name.startswith("sha256-") for name in deleted)

    def test_a_component_version_tag_protects_the_sha_tag_of_its_release(self, tmp_path):
        # 310 tags api-X.Y.Z on the digest of the released api image. Its old api-sha tag must survive 370.
        tags = [
            *self._tags(),
            _hub_tag("api-sha-aaaaaaa", 0, "sha256:" + "a1" * 32),
            _hub_tag("api-sha-bbbbbbb", 1, "sha256:" + "b2" * 32),
            _hub_tag(
                "api-sha-ccccccc", 2, "sha256:" + "c3" * 32, images=["sha256:" + "c4" * 32]
            ),  # released
            _hub_tag(
                "api-sha-ddddddd", 3, "sha256:" + "d5" * 32, images=["sha256:" + "d6" * 32]
            ),  # not released
            _hub_tag("api-1.0.0", 9, "sha256:" + "c3" * 32, images=["sha256:" + "c4" * 32]),
        ]
        result, deleted = self._run(tmp_path, tags=tags)
        assert result.returncode == 0, result.stderr + result.stdout
        assert (
            "api-sha-ccccccc" not in deleted
            and "keeping: api-sha-ccccccc (shared:" in result.stdout
        )
        assert "api-sha-ddddddd" in deleted
        assert "api-1.0.0" not in deleted

    def test_thousands_of_tags_do_not_hit_the_argument_limit(self, tmp_path):
        # cosign's referrer tags (sha256-<hex>) are never pruned and pile up; the permanent set also grows with every
        # release. Passed as one jq argument, the set passes 128 KiB (Linux) or 32 KiB (Windows) and the job ends with
        # "Argument list too long". It is read from a file, and referrer tags are not in it.
        referrers = [
            _hub_tag("sha256-" + f"{n:064x}", 9, "sha256:" + f"{n + 10**6:064x}")
            for n in range(6000)
        ]
        releases = [
            _hub_tag(f"1.{n}.0", 9, "sha256:" + f"{n + 2 * 10**6:064x}") for n in range(3000)
        ]
        result, deleted = self._run(tmp_path, tags=[*self._tags(), *referrers, *releases])
        assert result.returncode == 0, result.stderr + result.stdout
        assert "Argument list too long" not in result.stdout + result.stderr
        assert sorted(deleted) == ["sha-c3", "sha-e5"]
        assert "Fetched 9012 total tags" in result.stdout

    def test_a_referrer_tag_never_shields_a_sha_tag(self, tmp_path):
        # A referrer tag that (impossibly) listed an image digest of a SHA tag must not keep it: they are excluded.
        d = self.D
        tags = [*self._tags(), _hub_tag("sha256-" + "c" * 64, 9, d[3])]
        _, deleted = self._run(tmp_path, tags=tags)
        assert "sha-c3" in deleted

    def test_a_dry_run_deletes_nothing_and_names_the_same_tags(self, tmp_path):
        result, deleted = self._run(tmp_path, dry_run="true")
        assert result.returncode == 0 and deleted == []
        assert "would delete: sha-c3" in result.stdout and "would delete: sha-e5" in result.stdout
        assert "would delete: sha-d4" not in result.stdout

    def test_a_version_tag_without_any_digest_stops_the_prune_before_anything_is_deleted(
        self, tmp_path
    ):
        tags = [*self._tags(), _hub_tag("api-1.0.0", 9, None)]
        for dry_run in ("false", "true"):
            sub = tmp_path / dry_run
            sub.mkdir()
            result, deleted = self._run(sub, dry_run=dry_run, tags=tags)
            assert result.returncode == 1 and deleted == []
            assert "lists no digest for the tag(s) api-1.0.0" in result.stdout + result.stderr
            assert "would delete" not in result.stdout

    def test_a_referrer_tag_without_a_digest_does_not_stop_the_prune(self, tmp_path):
        tags = [*self._tags(), _hub_tag("sha256-" + "a" * 64, 9, None)]
        result, deleted = self._run(tmp_path, tags=tags)
        assert result.returncode == 0 and sorted(deleted) == ["sha-c3", "sha-e5"]

    def test_a_refused_delete_fails_the_job(self, tmp_path):
        result, deleted = self._run(tmp_path, delete_status="403")
        assert result.returncode == 1 and sorted(deleted) == ["sha-c3", "sha-e5"]
        assert "Could not delete sha-c3" in result.stdout + result.stderr


# --- the "Promote the digests to the release tags" step of 310-release-version.yml ---

RELEASE_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "310-release-version.yml"

#: `docker buildx imagetools inspect REF --format ...` answers from a registry file ("<ref> <digest>" lines);
#: `docker buildx imagetools create -t TAG SRC@DIGEST` appends TAG with that digest (or STUB_CREATE_AS) and logs it.
DOCKER_REGISTRY_STUB = r"""
if [ "$3" = create ]; then
  echo "$*" >> "$CREATE_LOG"
  src="${6}"; digest="${STUB_CREATE_AS:-${src##*@}}"
  echo "$5 $digest" >> "$STUB_REGISTRY"
  exit 0
fi
ref="$4"
if [ -n "${STUB_REGISTRY_ERROR:-}" ]; then echo "ERROR: $STUB_REGISTRY_ERROR" >&2; exit 1; fi
line="$(grep -F "$ref " "$STUB_REGISTRY" | tail -n1 || true)"
if [ -z "$line" ]; then echo "ERROR: $ref: not found" >&2; exit 1; fi
echo "${line##* }"
"""

RELEASE_DIGESTS = {
    "cli": "sha256:" + "1" * 64,
    "api": "sha256:" + "2" * 64,
    "worker": "sha256:" + "3" * 64,
    "web": "sha256:" + "4" * 64,
    "migrator": "sha256:" + "5" * 64,
}
RELEASE_TAGS = {
    "cli": "1.2.3",
    "api": "api-1.2.3",
    "worker": "worker-1.2.3",
    "web": "web-1.2.3",
    "migrator": "migrator-1.2.3",
}


def _promote_script() -> str:
    import yaml

    doc = yaml.safe_load(RELEASE_WORKFLOW.read_text(encoding="utf-8"))
    steps = doc["jobs"]["release"]["steps"]
    return next(s for s in steps if "Promote the digests" in s.get("name", ""))["run"]


@needs_tools
class TestPromoteStep:
    """The step is run as bash against a stub registry (docker) and the real registry_digest.sh."""

    def _run(self, tmp_path, *, existing=None, registry_error="", create_as="", digests=None):
        digests = digests or RELEASE_DIGESTS
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        _stub(bin_dir, "docker", DOCKER_REGISTRY_STUB)
        helper = tmp_path / "scripts" / "ci" / "registry_digest.sh"
        helper.parent.mkdir(parents=True)
        helper.write_text(
            (CI_DIR / "registry_digest.sh").read_text(encoding="utf-8"),
            encoding="utf-8",
            newline="\n",
        )
        registry = tmp_path / "registry.txt"
        registry.write_text(
            "".join(f"{IMAGE}:{tag} {digest}\n" for tag, digest in (existing or {}).items()),
            encoding="utf-8",
        )
        env = _env(
            bin_dir,
            STUB_REGISTRY=str(registry),
            STUB_REGISTRY_ERROR=registry_error,
            STUB_CREATE_AS=create_as,
            CREATE_LOG=str(tmp_path / "create.log"),
            REGISTRY="docker.io",
            DOCKERHUB_NAMESPACE=NAMESPACE,
            IMAGE_REPOSITORY=REPOSITORY,
            VERSION="1.2.3",
            DIGEST_CLI=digests["cli"],
            DIGEST_API=digests["api"],
            DIGEST_WORKER=digests["worker"],
            DIGEST_WEB=digests["web"],
            DIGEST_MIGRATOR=digests["migrator"],
        )
        result = subprocess.run(
            [BASH, "-c", _promote_script()], env=env, cwd=tmp_path, capture_output=True, text=True
        )
        log = tmp_path / "create.log"
        creates = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
        return result, creates, registry.read_text(encoding="utf-8").splitlines()

    def test_all_five_release_tags_are_created_on_the_verified_digests(self, tmp_path):
        result, creates, registry = self._run(tmp_path)
        assert result.returncode == 0, result.stderr + result.stdout
        assert len(creates) == 5
        for component, tag in RELEASE_TAGS.items():
            assert f"{IMAGE}:{tag} {RELEASE_DIGESTS[component]}" in registry, tag
        assert creates[0].endswith(f"-t {IMAGE}:1.2.3 {IMAGE}@{RELEASE_DIGESTS['cli']}")

    def test_a_rerun_after_a_partial_failure_creates_only_what_is_missing(self, tmp_path):
        done = {RELEASE_TAGS[c]: RELEASE_DIGESTS[c] for c in ("cli", "api")}
        result, creates, _ = self._run(tmp_path, existing=done)
        assert result.returncode == 0, result.stderr + result.stdout
        assert len(creates) == 3 and not any(
            f"{IMAGE}:1.2.3 " in c or "api-1.2.3" in c for c in creates
        )
        assert "already points at" in result.stdout

    def test_everything_already_tagged_is_a_no_op(self, tmp_path):
        done = {RELEASE_TAGS[c]: RELEASE_DIGESTS[c] for c in RELEASE_TAGS}
        result, creates, _ = self._run(tmp_path, existing=done)
        assert result.returncode == 0 and creates == []

    def test_an_existing_tag_with_another_digest_stops_the_release_before_any_tag_is_created(
        self, tmp_path
    ):
        clash = {RELEASE_TAGS["worker"]: "sha256:" + "9" * 64}
        result, creates, _ = self._run(tmp_path, existing=clash)
        assert result.returncode == 1
        assert creates == [], "phase 1 checks every tag before phase 2 writes any"
        assert "worker-1.2.3 already exists" in result.stderr + result.stdout
        assert "a release tag is never moved" in result.stderr + result.stdout

    def test_a_registry_error_is_not_read_as_an_absent_tag(self, tmp_path):
        result, creates, _ = self._run(tmp_path, registry_error="denied: requested access")
        assert result.returncode == 1 and creates == []
        assert "refusing to create a release tag blind" in result.stderr + result.stdout

    def test_a_tag_that_resolves_to_another_digest_after_creation_fails(self, tmp_path):
        result, creates, _ = self._run(tmp_path, create_as="sha256:" + "8" * 64)
        assert result.returncode == 1 and len(creates) == 1, "it stops at the first bad read-back"
        assert "expected" in result.stderr + result.stdout
        assert "Delete that tag on Docker Hub" in result.stderr + result.stdout

    def test_a_missing_or_malformed_digest_creates_nothing(self, tmp_path):
        digests = {**RELEASE_DIGESTS, "web": ""}
        result, creates, _ = self._run(tmp_path, digests=digests)
        assert result.returncode == 1 and creates == []
        assert "No valid digest for 'web'" in result.stderr + result.stdout
