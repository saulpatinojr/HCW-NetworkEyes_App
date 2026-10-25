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
                "200-build-images.yml:rehearse-docker-login",
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


def _code(text: str) -> str:
    """The text without whole-line comments (a comment can say what the code must not do)."""
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


#: Registry writers other than the one promotion step, and anything that could mint or move a tag by other means.
FORBIDDEN_IN_RELEASE = re.compile(
    r"\b(crane|gcrane|regctl|skopeo|oras|cosign\s+(sign|attest|copy|tag))\b"
    r"|\bdocker\s+(tag|push|build|commit)\b"
    r"|\bbuildx\s+build\b"
    r"|(?<![\w-])latest\b"
)


class TestReleasePromotesTheScannedDigest:
    def setup_method(self):
        self.text = RELEASE.read_text(encoding="utf-8")
        self.doc = _load(RELEASE)
        self.job = self.doc["jobs"]["release"]

    def _step(self, needle: str) -> dict:
        return _steps(self.job)[_index_of(self.job, needle)]

    def test_it_never_builds_or_pushes_layers(self):
        assert "build-push-action" not in self.text
        assert not re.search(r"docker (build|push)\b(?!x)", _code(self.text))

    def test_nothing_in_it_can_tag_or_move_latest_by_another_route(self):
        # Mutation guard: a `crane tag ... latest`, `skopeo copy`, `docker tag` or `oras tag` appended to any
        # step, or the word latest used as a tag, fails here. Only the promotion step may write, and only a version.
        found = FORBIDDEN_IN_RELEASE.search(_code(self.text))
        assert found is None, f"310 must not contain {found.group(0)!r}"
        writers = re.findall(
            r"^\s*docker buildx imagetools create\b[^\n]*", _code(self.text), re.MULTILINE
        )
        assert writers == [
            '          docker buildx imagetools create -t "${IMAGE}:${VERSION}" "${IMAGE}@${DIGEST}"'
        ]

    def test_it_promotes_a_digest_and_only_after_verifying_it(self):
        find = _index_of(self.job, "Find the scanned image")
        verify = _index_of(self.job, "Verify the signature")
        login = _login_index(self.job)
        promote = _index_of(self.job, "Promote the digest")
        assert find < verify < login < promote, (
            "the write credential is minted after the checks, just before use"
        )
        assert login == promote - 1, "the login is the step right before the promotion"
        assert "sigstore/cosign-installer@" in self.text

    def test_the_verification_cannot_be_made_non_gating(self):
        # Mutation guard: `|| true`, continue-on-error, an `if:` or a `set +e` on the verify step all fail here.
        step = self._step("Verify the signature")
        assert set(step) <= {"name", "env", "run"}, (
            f"unexpected keys on the verify step: {sorted(step)}"
        )
        assert "||" not in step["run"] and ";" not in step["run"] and "&" not in step["run"]
        assert "set +e" not in step["run"]
        assert step["run"].startswith("bash scripts/ci/verify_signed_digest.sh ")
        assert step["env"]["EXPECTED_REVISION"] == "${{ steps.scanned.outputs.build_commit }}"
        assert step["env"]["EXPECTED_RUN_IDS"] == "${{ steps.scanned.outputs.run_ids }}"
        assert "continue-on-error" not in yaml.safe_dump(self.job)

    def test_the_search_is_the_script_and_it_is_not_made_optional(self):
        step = self._step("Find the scanned image")
        assert step["run"] == "bash scripts/ci/find_release_image.sh"
        assert set(step) <= {"name", "id", "env", "run"}

    def test_a_release_tag_is_never_moved_and_a_failed_check_is_not_an_absent_tag(self):
        script = self._step("Promote the digest")["run"]
        assert "a release tag is never moved" in script
        assert "registry_digest" in script and 'case "$rc" in' in script
        # The branch that lets the tag be created is the "not found" one only (return status 1).
        assert re.search(r"^\s*1\) ;;\s*$", script, re.MULTILINE)
        assert "refusing to create a release tag blind" in script
        assert (
            "Delete that tag on Docker Hub" in script
        )  # the runbook line for the post-check failure
        assert "2>/dev/null" not in script, "an inspect failure must not be silenced into 'absent'"

    def test_the_login_hint_names_the_second_ruleset_and_the_troubleshooting_page(self):
        hint = self._step("What to check if the Docker Hub login")
        assert (
            "steps.login.outcome == 'failure'" in hint["if"]
            and "steps.promote.outcome == 'failure'" in hint["if"]
        )
        assert hint["if"].startswith("failure()")
        for needle in (
            "https://docs.docker.com/security/authentication/oidc-connections/troubleshoot",
            "SECOND RULESET",
            "refs/tags/v*",
            "Image Push",
            "Failures",
        ):
            assert needle in hint["run"], needle
        assert "Image Pull" not in hint["run"]

    def test_it_may_read_the_workflow_runs_it_waits_for(self):
        assert self.doc["permissions"].get("actions") == "read"

    def test_the_header_states_the_ruleset_and_the_first_release_flow(self):
        header = self.text.split("name:", 1)[0]
        assert "SECOND RULESET" in header and "refs/tags/v*" in header and "Image Push" in header
        assert "Image Pull is not needed" in header
        assert "latest-build.json" in header and "commit" in header
        assert "DRY RUN" in header and "POST-CHECK" in header.upper()


class TestReleaseDryRun:
    """Run workflow on 310 proves the find / verify path before any tag exists, without writing anything."""

    def setup_method(self):
        self.doc = _load(RELEASE)
        self.job = self.doc["jobs"]["release"]
        self.steps = _steps(self.job)

    def test_there_is_a_dry_run_input_that_defaults_to_true(self):
        trigger = self.doc.get("on", self.doc.get(True))
        assert trigger["workflow_dispatch"]["inputs"]["dry_run"]["default"] is True
        assert trigger["workflow_dispatch"]["inputs"]["dry_run"]["type"] == "boolean"
        assert trigger["push"]["tags"] == ["v*.*.*"]

    def test_a_dispatch_runs_only_as_a_dry_run_from_main_and_needs_no_publishing_switch(self):
        condition = " ".join(str(self.job["if"]).split())
        dispatch = condition.split("||")[1]
        assert (
            "github.event_name == 'workflow_dispatch'" in dispatch and "inputs.dry_run" in dispatch
        )
        assert "default_branch" in dispatch
        assert "DOCKERHUB_ENABLED" not in dispatch
        assert "DOCKERHUB_ENABLED == 'true'" in condition.split("||")[0], (
            "a pushed tag still needs publishing on"
        )

    def test_every_step_that_writes_runs_only_for_a_pushed_tag(self):
        writers = (
            "Extract version",
            "Log in to Docker Hub",
            "Promote the digest",
            "Create GitHub Release",
        )
        for name in writers:
            step = next(s for s in self.steps if name in s.get("name", ""))
            assert step["if"] == "github.event_name == 'push'", name

    def test_the_dry_run_still_finds_and_verifies_and_reports(self):
        by_name = {s.get("name", ""): s for s in self.steps}
        for name in (
            "Find the scanned image built from this commit",
            "Verify the signature and provenance of that digest",
        ):
            assert "if" not in by_name[name], f"{name} must run in the dry run"
        report = by_name["Report what a release would promote (dry run)"]
        assert report["if"] == "github.event_name == 'workflow_dispatch'"
        assert "nothing was logged in, tagged or released" in report["run"]

    def test_the_dry_run_never_has_a_write_credential(self):
        # The only login step is for a pushed tag, and it comes after the verification.
        login = next(s for s in self.steps if str(s.get("uses", "")).startswith(LOGIN_ACTION))
        assert login["if"] == "github.event_name == 'push'"


class TestDockerLoginRehearsal:
    """The dry run of the OIDC connection: login plus a digest-only push, before publishing is on."""

    def setup_method(self):
        self.doc = _load(BUILD)
        self.job = self.doc["jobs"]["rehearse-docker-login"]
        self.steps = _steps(self.job)

    def test_it_runs_for_the_rehearsal_input_on_the_default_branch_only(self):
        condition = self.job["if"]
        assert "inputs.rehearsal" in condition
        assert (
            "github.event.repository.default_branch" in condition and "refs/heads/{0}" in condition
        )

    def test_it_does_not_depend_on_publishing_being_enabled(self):
        assert "DOCKERHUB_ENABLED" not in self.job["if"]
        assert not any("DOCKERHUB_ENABLED" in str(s.get("if", "")) for s in self.steps)
        # ... while every real publishing job stays off for a rehearsal run.
        for name in ("build-images", "build-web", "tag-images", "publish-build-manifest"):
            assert "!inputs.rehearsal" in self.doc["jobs"][name]["if"], name

    def test_it_holds_only_the_permissions_the_login_needs_and_no_environment(self):
        assert self.job["permissions"] == {"contents": "read", "id-token": "write"}
        assert "environment" not in self.job

    def test_it_checks_the_connection_id_and_the_namespace_before_logging_in(self):
        check = _index_of(self.job, "Validate Docker Hub namespace")
        assert check < _login_index(self.job)
        script = self.steps[check]["run"]
        assert (
            "DOCKERHUB_NAMESPACE" in script and "[0-9a-fA-F]{8}-" in script and "exit 1" in script
        )
        assert self.steps[check]["env"]["CONNECTION"] == "${{ vars.DOCKERHUB_CONNECTION }}"

    def test_it_logs_in_exactly_as_the_real_jobs_do(self):
        mine = self.steps[_login_index(self.job)]
        real = _steps(self.doc["jobs"]["tag-images"])[_login_index(self.doc["jobs"]["tag-images"])]
        assert mine["uses"] == real["uses"]  # the same pinned action
        assert (
            mine["with"]
            == real["with"]
            == {"registry": "docker.io", "username": "${{ vars.DOCKERHUB_NAMESPACE }}"}
        )
        assert mine["env"]["DOCKERHUB_OIDC_CONNECTIONID"] == "${{ vars.DOCKERHUB_CONNECTION }}"
        assert EXPIRE_MIN <= int(mine["env"]["DOCKERHUB_OIDC_EXPIREIN"]) <= EXPIRE_MAX

    def test_it_pushes_by_digest_only_with_no_tag(self):
        push = next(
            s for s in self.steps if str(s.get("uses", "")).startswith("docker/build-push-action@")
        )
        assert (
            "push-by-digest=true" in push["with"]["outputs"]
            and "push=true" in push["with"]["outputs"]
        )
        assert (
            "${{ env.DOCKERHUB_NAMESPACE }}/${{ env.IMAGE_REPOSITORY }}" in push["with"]["outputs"]
        )
        assert "tags" not in push["with"] and "load" not in push["with"]
        assert (
            "tag=" not in push["with"]["outputs"]
            and ",name=" not in push["with"]["outputs"].split("name=", 1)[1]
        )
        # The image has no layers beyond its labels.
        definition = next(s for s in self.steps if "Dockerfile" in str(s.get("run", "")))["run"]
        assert (
            "FROM scratch" in definition
            and "rehearsal=" in definition
            and "GITHUB_RUN_ID" in definition
        )
        # One tiny COPY layer, so a registry that rejects zero-layer images cannot be misread as a scope error.
        assert definition.count("COPY rehearsal.txt /rehearsal.txt") == 1
        assert not re.search(r"\\n(RUN|ADD)\b", definition)

    def test_it_reads_the_digest_back(self):
        script = self.steps[_index_of(self.job, "Read the pushed digest back")]["run"]
        assert "docker buildx imagetools inspect" in script and "@${DIGEST}" in script
        assert 'READ" != "$DIGEST"' in script

    def test_it_never_signs_tags_writes_the_manifest_or_reaches_latest(self):
        text = yaml.safe_dump(
            {**self.job, "runs-on": "runner"}
        )  # ubuntu-latest is a runner label, not a tag
        assert "latest" not in text
        for forbidden in (
            "cosign",
            "sign_image",
            "imagetools create",
            "docker tag",
            "docker push",
            "latest-build.json",
            "self-merging-pr",
            "metadata-action",
            "type=raw",
            "type=sha",
        ):
            assert forbidden not in text, forbidden

    def test_it_explains_a_failure_and_logs_out_at_the_end(self):
        hint = next(
            s for s in self.steps if s.get("if") == "failure() && steps.scout.outcome != 'failure'"
        )
        assert (
            "https://docs.docker.com/security/authentication/oidc-connections/troubleshoot"
            in hint["run"]
        )
        assert (
            "immutable" in hint["run"] and "Failures" in hint["run"] and "Image Push" in hint["run"]
        )
        last = self.steps[-1]
        assert last["if"] == "always()" and "docker logout" in last["run"]

    def test_scout_is_rehearsed_with_the_call_the_real_build_makes(self):
        scout = next(s for s in self.steps if s.get("id") == "scout")
        real = next(
            s
            for s in _steps(self.doc["jobs"]["build-web"])
            if str(s.get("uses", "")).startswith("docker/scout-action@")
        )
        assert scout["uses"] == real["uses"], "the same pinned Scout action as the real jobs"
        for key in ("command", "only-severities", "only-fixed", "exit-code"):
            assert scout["with"][key] == real["with"][key], key
        assert scout["with"]["image"].endswith("@${{ steps.push.outputs.digest }}")
        assert _index_of(self.job, "Docker Scout analyses") > _index_of(
            self.job, "Read the pushed digest back"
        )

    def test_a_scout_failure_gets_its_own_hint_naming_the_token_decision(self):
        hint = next(
            s for s in self.steps if "What to check if Docker Scout failed" in s.get("name", "")
        )
        assert hint["if"] == "failure() && steps.scout.outcome == 'failure'"
        assert (
            "personal access token" in hint["run"]
            and "DOCKERHUB_ENABLED" in hint["run"]
            and "T-728" in hint["run"]
        )
        general = next(s for s in self.steps if s.get("name") == "What to check if this failed")
        assert general["if"] == "failure() && steps.scout.outcome != 'failure'"

    def test_it_claims_nothing_about_docker_hub_deleting_untagged_images(self):
        text = BUILD.read_text(encoding="utf-8")
        assert "garbage-collect" not in text and "garbage collect" not in text


class TestVerifyScript:
    """Static pins. scripts/ci tests in test_release_scripts_behaviour.py run the script against stubs."""

    def setup_method(self):
        self.text = VERIFY_SCRIPT.read_text(encoding="utf-8")
        self.code = _code(self.text)

    def test_the_identity_is_assigned_to_the_200_workflow_and_main(self):
        # Mutation guard: changing the identity while the old string stays in a comment fails here, because
        # the assertion is on the code of the IDENTITY= assignment, not on the file text.
        assignments = re.findall(r"^IDENTITY=(.*)$", self.code, re.MULTILINE)
        assert assignments == [
            '"${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}/.github/workflows/200-build-images.yml@refs/heads/main"'
        ]
        assert re.findall(r"^ISSUER=(.*)$", self.code, re.MULTILINE) == [
            '"https://token.actions.githubusercontent.com"'
        ]

    def test_every_cosign_call_is_pinned_to_that_identity_and_issuer(self):
        calls = re.findall(
            r"cosign_with_either_timestamp \"[^\"]+\" (verify(?:-attestation)?)\b(.*?)(?:\n\n|\Z)",
            self.code,
            re.S,
        )
        assert [name for name, _ in calls] == ["verify", "verify-attestation"]
        for name, rest in calls:
            assert '--certificate-identity "$IDENTITY"' in rest, name
            assert '--certificate-oidc-issuer "$ISSUER"' in rest, name
        assert "--type slsaprovenance02" in self.code
        assert "--insecure" not in self.code and "--allow-insecure" not in self.code
        assert "--certificate-identity-regexp" not in self.code, "an exact identity, not a pattern"

    def test_no_check_can_be_turned_into_a_pass(self):
        assert "|| true" not in self.code and "set +e" not in self.code
        for line in self.code.splitlines():
            assert not re.search(r"\|\|\s*(true|:)\b", line), line
        # Each failure branch ends the script.
        for match in re.finditer(r"echo \"::error::[^\n]*\n(\s*)(\w+)", self.code):
            assert match.group(2) in {"exit", "return", "echo", "cat"}, match.group(0)

    def test_it_checks_the_subject_the_builder_and_the_revision_like_the_appliances_do(self):
        assert 'predicateType == "https://slsa.dev/provenance/v0.2"' in self.code
        assert ".digest.sha256" in self.code and "predicate.builder.id" in self.code
        assert "startswith($p)" in self.code
        assert "org.opencontainers.image.revision" in self.code
        assert '"docker-manifest-digest"' in self.code

    def test_it_demands_the_exact_digest_and_the_configured_repository(self):
        assert "/${IMAGE_REPOSITORY}@sha256:" in self.text
        assert "${IMAGE_REPOSITORY:-}" in self.text
