"""The publishing workflows are safe to switch on (DOCKERHUB_ENABLED), checked before the first real run.

Defects an independent review of ``200-build-images.yml`` found by reading it, kept from coming back:

* every job that logs in to Docker Hub through OIDC may mint a GitHub OIDC token (``id-token: write``);
* the Docker token outlives the job that uses it (the long jobs ask for the 3600 s maximum);
* the namespace is validated before the login that depends on it;
* the appliances' owner is its own variable, not this repository's owner, and a dispatch never follows a
  redirect;
* ``310-release-version.yml`` promotes the digest ``200`` scanned and signed for the tagged commit, after
  verifying its signature, and never builds, never pushes layers and never moves ``latest``.

These are static checks of the workflow files; they do not prove a Docker Hub exchange or a registry
push, which only a real run does.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
BUILD = WORKFLOWS / "200-build-images.yml"
RELEASE = WORKFLOWS / "310-release-version.yml"
VERIFY_SCRIPT = REPO_ROOT / "scripts" / "ci" / "verify_signed_digest.sh"
LOGIN_ACTION = "docker/login-action@"
#: Docker Hub's limits for ``DOCKERHUB_OIDC_EXPIREIN`` (seconds), per docker/login-action.
EXPIRE_MIN, EXPIRE_MAX = 300, 3600


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _steps(job: dict) -> list[dict]:
    return job.get("steps", [])


def _login_index(job: dict) -> int | None:
    for i, step in enumerate(_steps(job)):
        if str(step.get("uses", "")).startswith(LOGIN_ACTION):
            return i
    return None


def _index_of(job: dict, needle: str) -> int:
    for i, step in enumerate(_steps(job)):
        if needle in step.get("name", "") or needle in str(step.get("run", "")):
            return i
    raise AssertionError(f"no step mentions {needle!r}")


def _logins() -> list[tuple[str, str, dict, dict]]:
    out = []
    for path in (BUILD, RELEASE):
        doc = _load(path)
        for name, job in doc["jobs"].items():
            if _login_index(job) is not None:
                out.append((path.name, name, doc, job))
    return out


LOGINS = _logins()
IDS = [f"{w}:{j}" for w, j, _, _ in LOGINS]


class TestDockerHubLogin:
    def test_the_logging_in_jobs_are_the_ones_expected(self):
        assert sorted(IDS) == sorted(
            [
                "200-build-images.yml:build-images",
                "200-build-images.yml:build-web",
                "200-build-images.yml:tag-images",
                "310-release-version.yml:release",
            ]
        )

    @pytest.mark.parametrize(("workflow", "name", "doc", "job"), LOGINS, ids=IDS)
    def test_every_job_that_logs_in_may_mint_an_oidc_token(self, workflow, name, doc, job):
        permissions = job.get("permissions", doc.get("permissions", {}))
        assert permissions.get("id-token") == "write", (
            f"{workflow}:{name} logs in to Docker Hub by OIDC"
        )

    @pytest.mark.parametrize(("workflow", "name", "doc", "job"), LOGINS, ids=IDS)
    def test_the_token_lifetime_is_within_the_documented_range(self, workflow, name, doc, job):
        env = _steps(job)[_login_index(job)]["env"]
        assert EXPIRE_MIN <= int(env["DOCKERHUB_OIDC_EXPIREIN"]) <= EXPIRE_MAX

    @pytest.mark.parametrize("name", ["build-images", "build-web"])
    def test_the_long_build_jobs_ask_for_the_longest_token(self, name):
        job = _load(BUILD)["jobs"][name]
        assert job["timeout-minutes"] > 15
        assert int(_steps(job)[_login_index(job)]["env"]["DOCKERHUB_OIDC_EXPIREIN"]) == EXPIRE_MAX

    @pytest.mark.parametrize(("workflow", "name", "doc", "job"), LOGINS, ids=IDS)
    def test_the_namespace_is_validated_before_the_login(self, workflow, name, doc, job):
        assert _index_of(job, "Validate Docker Hub namespace") < _login_index(job)


class TestNotifyAppliances:
    def setup_method(self):
        self.text = BUILD.read_text(encoding="utf-8")
        self.job = _load(BUILD)["jobs"]["notify-appliances"]

    def test_the_owner_is_the_appliance_owner_variable_not_this_repositorys(self):
        assert "github.repository_owner" not in self.text
        token = next(s for s in _steps(self.job) if s.get("id") == "app-token")
        assert token["with"]["owner"] == "${{ vars.APPLIANCE_OWNER }}"
        dispatch = next(
            s for s in _steps(self.job) if "Send cna-image-published" in s.get("name", "")
        )
        assert dispatch["env"]["OWNER"] == "${{ vars.APPLIANCE_OWNER }}"

    def test_a_missing_owner_fails_before_any_token_is_minted(self):
        check = _index_of(self.job, "Require APPLIANCE_OWNER")
        assert check < _index_of(self.job, "Generate GitHub App token")
        script = _steps(self.job)[check]["run"]
        assert "exit 1" in script and "APPLIANCE_OWNER" in script

    def test_the_dispatch_follows_no_redirect_and_checks_the_status(self):
        script = next(
            s for s in _steps(self.job) if "Send cna-image-published" in s.get("name", "")
        )["run"]
        assert "--max-redirs 0" in script
        assert not re.search(r"curl\b[^\n]*\s-[a-zA-Z]*L\b", script) and "--location" not in script
        assert "%{http_code}" in script and "::warning::" in script


class TestReleasePromotesTheScannedDigest:
    def setup_method(self):
        self.text = RELEASE.read_text(encoding="utf-8")
        self.job = _load(RELEASE)["jobs"]["release"]

    def test_it_never_builds_or_pushes_layers(self):
        assert "build-push-action" not in self.text
        assert not re.search(r"docker (build|push)\b(?!x)", self.text)

    def test_it_never_moves_latest(self):
        # `latest` is the CLI tag; 200 moves it, and only after the scan.
        assert ":latest" not in self.text
        tags = re.findall(r"^\s*docker buildx imagetools create\b[^\n]*", self.text, re.MULTILINE)
        assert len(tags) == 1 and re.search(r'-t "\$\{IMAGE\}:\$\{VERSION\}"', tags[0])
        assert "latest" not in tags[0]

    def test_it_promotes_a_digest_and_only_after_verifying_it(self):
        find = _index_of(self.job, "Find the scanned image")
        verify = _index_of(self.job, "Verify the signature")
        promote = _index_of(self.job, "Promote the digest")
        assert _login_index(self.job) < find < verify < promote
        assert 'imagetools create -t "${IMAGE}:${VERSION}" "${IMAGE}@${DIGEST}"' in self.text
        assert "scripts/ci/verify_signed_digest.sh" in _steps(self.job)[verify]["run"]
        assert "sigstore/cosign-installer@" in self.text

    def test_it_finds_the_image_by_the_commit_and_fails_clearly_without_one(self):
        script = _steps(self.job)[_index_of(self.job, "Find the scanned image")]["run"]
        assert 'SHA_TAG="sha-${GITHUB_SHA:0:7}"' in script
        assert "--workflow 200-build-images.yml" in script and '--commit "$GITHUB_SHA"' in script
        assert script.count("::error::") >= 3 and "exit 1" in script

    def test_a_release_tag_is_never_moved(self):
        script = _steps(self.job)[_index_of(self.job, "Promote the digest")]["run"]
        assert "a release tag is never moved" in script

    def test_it_may_read_the_workflow_runs_it_waits_for(self):
        assert _load(RELEASE)["permissions"].get("actions") == "read"


class TestVerifyScript:
    def setup_method(self):
        self.text = VERIFY_SCRIPT.read_text(encoding="utf-8")

    def test_it_checks_signature_and_provenance_under_the_200_identity(self):
        assert "200-build-images.yml@refs/heads/main" in self.text
        assert "https://token.actions.githubusercontent.com" in self.text
        assert re.search(r"\bverify\b", self.text) and "verify-attestation" in self.text
        assert "--type slsaprovenance02" in self.text

    def test_it_demands_the_exact_digest_and_the_configured_repository(self):
        assert '"docker-manifest-digest"' in self.text
        assert "/${IMAGE_REPOSITORY}@sha256:" in self.text
        assert "${IMAGE_REPOSITORY:-}" in self.text
