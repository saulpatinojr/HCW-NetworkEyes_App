"""The publishing workflows are safe to switch on (DOCKERHUB_ENABLED), checked before the first real run.

Defects an independent review of ``200-build-images.yml`` found by reading it, kept from coming back:

* every job that logs in to Docker Hub through OIDC may mint a GitHub OIDC token (``id-token: write``);
* the Docker token outlives the job that uses it (the long jobs ask for the 3600 s maximum);
* the namespace is validated before the login that depends on it;
* ``tag-images`` verifies that every digest is signed before it moves a tag and records one row per component
  (tags, digest, signed) in the run's step summary: nothing is written back to the repository;
* ``310-release-version.yml`` promotes the digest ``200`` scanned and signed for the tagged commit, after
  verifying its signature, lists the digests of all five images in the release notes, and never builds, never
  pushes layers and never moves ``latest``.

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
        self.job = self.doc["jobs"]["verify"]  # find and verify: read-only
        self.release = self.doc["jobs"]["release"]  # login, promote, Release: the only writer

    def _step(self, needle: str) -> dict:
        for job in (self.job, self.release):
            for step in _steps(job):
                if needle in step.get("name", "") or needle in str(step.get("run", "")):
                    return step
        raise AssertionError(f"no step mentions {needle!r}")

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
            '            docker buildx imagetools create -t "${IMAGE}:${TAGS[$c]}" "${IMAGE}@${DIGESTS[$c]}"'
        ]

    def test_it_promotes_a_digest_and_only_after_verifying_it(self):
        find = _index_of(self.job, "Find the scanned image")
        verify = _index_of(self.job, "Verify the signature")
        others = _index_of(self.job, "Find and verify the other images")
        assert find < verify < others
        assert _login_index(self.job) is None, "the verify job has no registry credential"
        # The write credential is minted in a later job, after the checks, just before use.
        assert self.release["needs"] == "verify"
        login = _login_index(self.release)
        promote = _index_of(self.release, "Promote the digests")
        assert login == promote - 1, "the login is the step right before the promotion"
        assert "sigstore/cosign-installer@" in self.text

    def test_the_verification_cannot_be_made_non_gating(self):
        # Mutation guard: `|| true`, continue-on-error, an `if:` or a `set +e` on the verify step all fail here.
        step = self._step("Verify the signature")
        assert set(step) <= {"name", "id", "env", "run"}, (
            f"unexpected keys on the verify step: {sorted(step)}"
        )
        assert step["id"] == "cli" and step["env"]["EMIT_BUILDER_RUN_ID"] == "true"
        assert "||" not in step["run"] and ";" not in step["run"] and "&" not in step["run"]
        assert "set +e" not in step["run"]
        assert step["run"].startswith("bash scripts/ci/verify_signed_digest.sh ")
        assert step["env"]["EXPECTED_REVISION"] == "${{ steps.scanned.outputs.build_commit }}"
        assert step["env"]["EXPECTED_RUN_IDS"] == "${{ steps.scanned.outputs.run_ids }}"
        assert "continue-on-error" not in yaml.safe_dump(self.job)
        assert "continue-on-error" not in yaml.safe_dump(self.release)

    def test_the_search_is_the_script_and_it_is_not_made_optional(self):
        step = self._step("Find the scanned image")
        assert step["run"] == "bash scripts/ci/find_release_image.sh"
        assert set(step) <= {"name", "id", "env", "run"}

    def test_a_release_tag_is_never_moved_and_a_failed_check_is_not_an_absent_tag(self):
        script = self._step("Promote the digests")["run"]
        assert "a release tag is never moved" in script
        assert "registry_digest" in script and 'case "$rc" in' in script
        # The branch that lets the tag be created is the "not found" one only (return status 1).
        assert re.search(r"^\s*1\) MISSING\[\$c\]=yes ;;\s*$", script, re.MULTILINE)
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

    def test_permissions_are_split_between_a_read_only_job_and_the_one_writer(self):
        assert self.doc["permissions"] == {}, "nothing is granted workflow-wide"
        # verify: reads the workflow runs it waits for (actions: read) and checks out; no write, no OIDC token.
        assert self.job["permissions"] == {"contents": "read", "actions": "read"}
        assert self.release["permissions"] == {"contents": "write", "id-token": "write"}

    def test_both_jobs_check_out_without_persisting_a_credential(self):
        for job in (self.job, self.release):
            checkout = next(
                s for s in _steps(job) if str(s.get("uses", "")).startswith("actions/checkout@")
            )
            assert checkout["with"]["persist-credentials"] is False

    def test_the_digests_pass_between_jobs_as_outputs_and_reach_scripts_through_env(self):
        outputs = self.job["outputs"]
        assert sorted(outputs) == [
            "build_commit",
            "digest",
            "digest_api",
            "digest_migrator",
            "digest_web",
            "digest_worker",
            "run_ids",
            "tag",
        ]
        for key, value in outputs.items():
            assert re.fullmatch(r"\$\{\{ steps\.(scanned|others)\.outputs\.\w+ \}\}", value), key
        promote = self._step("Promote the digests")
        assert promote["env"] == {
            "VERSION": "${{ steps.version.outputs.VERSION }}",
            "DIGEST_CLI": "${{ needs.verify.outputs.digest }}",
            "DIGEST_API": "${{ needs.verify.outputs.digest_api }}",
            "DIGEST_WORKER": "${{ needs.verify.outputs.digest_worker }}",
            "DIGEST_WEB": "${{ needs.verify.outputs.digest_web }}",
            "DIGEST_MIGRATOR": "${{ needs.verify.outputs.digest_migrator }}",
        }
        # No script in the release job interpolates an expression: they are all env-fed.
        for step in _steps(self.release):
            assert "${{" not in str(step.get("run", "")), step.get("name")

    def test_the_release_job_holds_no_registry_credential_but_the_one_oidc_login(self):
        # Image Push comes from the single OIDC login of the tag-ref ruleset; no stored token, no other login.
        logins = [
            s for s in _steps(self.release) if str(s.get("uses", "")).startswith(LOGIN_ACTION)
        ]
        assert len(logins) == 1
        text = yaml.safe_dump(self.release)
        for needle in (
            "secrets.",
            "DOCKERHUB_PERSONAL",
            "DOCKERHUB_TOKEN",
            "docker login",
            "--password",
        ):
            assert needle not in text, needle
        assert "refs/tags/v*" in self.text.split("name:", 1)[0]

    def test_the_header_names_the_gap_between_the_check_and_the_creation(self):
        header = " ".join(self.text.split("name:", 1)[0].split())
        assert "between that check and the creation another writer" in header
        assert "immutable tags" in header and "was not checked" in header

    def test_the_header_states_the_ruleset_and_the_first_release_flow(self):
        header = self.text.split("name:", 1)[0]
        assert "SECOND RULESET" in header and "refs/tags/v*" in header and "Image Push" in header
        assert "Image Pull is not needed" in header
        assert "WHICH COMMIT TO TAG" in header and "THE FIVE DIGESTS" in header
        for tag in ("`api-X.Y.Z`", "`worker-X.Y.Z`", "`web-X.Y.Z`", "`migrator-X.Y.Z`"):
            assert tag in header, tag
        assert "Only the CLI image gets" not in self.text
        assert "DRY RUN" in header and "POST-CHECK" in header.upper()


class TestReleaseDryRun:
    """Run workflow on 310 proves the find / verify path before any tag exists, without writing anything."""

    def setup_method(self):
        self.doc = _load(RELEASE)
        self.job = self.doc["jobs"]["verify"]
        self.release = self.doc["jobs"]["release"]
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

    def test_everything_that_writes_is_in_a_job_that_only_a_pushed_tag_reaches(self):
        assert " ".join(str(self.release["if"]).split()) == (
            "github.event_name == 'push' && vars.DOCKERHUB_ENABLED == 'true'"
        )
        assert self.release["needs"] == "verify"
        writers = (
            "Extract version",
            "Log in to Docker Hub",
            "Promote the digest",
            "Create GitHub Release",
        )
        names = [s.get("name", "") for s in _steps(self.release)]
        for name in writers:
            assert any(name in n for n in names), name
        # ... and none of them is in the job a dry run does reach.
        for name in writers:
            assert not any(name in s.get("name", "") for s in self.steps), name
        assert "imagetools create" not in yaml.safe_dump(self.job)

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

    def test_the_dry_run_needs_neither_a_write_scope_nor_an_oidc_token(self):
        assert _login_index(self.job) is None
        assert self.doc["permissions"] == {}
        assert set(self.job["permissions"]) == {"contents", "actions"}
        assert set(self.job["permissions"].values()) == {"read"}


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
        for name in ("build-images", "build-web", "tag-images"):
            assert "!inputs.rehearsal" in self.doc["jobs"][name]["if"], name

    def test_it_holds_only_the_permissions_the_login_needs_and_no_environment(self):
        assert self.job["permissions"] == {"contents": "read", "id-token": "write"}
        assert "environment" not in self.job

    def test_it_proves_the_live_wording_of_a_missing_tag_before_creating_it(self):
        retag = next(s for s in self.steps if s.get("id") == "retag")["run"]
        absent = retag.index('registry_digest "${IMAGE}:${TAG}" > /dev/null || rc=$?')
        assert absent < retag.index("imagetools create")
        assert '[ "$rc" -ne 1 ]' in retag

    def test_it_never_prints_the_connection_id(self):
        check = self.steps[_index_of(self.job, "Validate Docker Hub namespace")]["run"]
        errors = [line for line in check.splitlines() if "::error::" in line]
        assert errors and not any("${CONNECTION}" in line for line in errors)
        assert any("${#CONNECTION}" in line for line in errors), "it says how long the value is"

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

    def test_it_never_reaches_latest_a_sha_tag_or_the_repository_and_creates_one_rehearsal_tag(
        self,
    ):
        text = yaml.safe_dump(
            {**self.job, "runs-on": "runner"}
        )  # ubuntu-latest is a runner label, not a tag
        assert "latest" not in text
        for forbidden in (
            "docker tag",
            "docker push",
            "latest-build.json",
            "self-merging-pr",
            "metadata-action",
            "type=raw",
            "type=sha",
            "sha-",
        ):
            assert forbidden not in text, forbidden
        retag = next(s for s in self.steps if s.get("id") == "retag")["run"]
        assert retag.count("imagetools create") == 1
        assert 'imagetools create -t "${IMAGE}:${TAG}" "${IMAGE}@${DIGEST}"' in retag
        assert 'TAG="rehearsal-${GITHUB_RUN_ID}"' in retag
        assert (
            sum(s.get("run", "").count("docker buildx imagetools create") for s in self.steps) == 1
        )

    def test_it_deletes_nothing(self):
        text = yaml.safe_dump(self.job)
        for needle in (
            "DELETE",
            " rm ",
            "docker rmi",
            "delete",
            "cosign clean",
            "imagetools rm",
        ):
            assert needle not in text, needle

    def test_it_signs_attests_and_verifies_with_the_scripts_the_real_jobs_use(self):
        names = [s.get("name", "") for s in self.steps]
        order = [
            _index_of(self.job, "Push the rehearsal image by digest"),
            _index_of(self.job, "Docker Scout analyses"),
            _index_of(self.job, "Sign and attest the rehearsal digest"),
            _index_of(self.job, "Verify the rehearsal digest"),
            _index_of(self.job, "Give the digest one rehearsal tag"),
        ]
        assert order == sorted(order), names
        sign = self.steps[order[2]]
        assert sign["run"] == (
            'scripts/ci/sign_image.sh "docker.io/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}@${DIGEST}"'
        )
        verify = self.steps[order[3]]
        assert verify["run"] == (
            'bash scripts/ci/verify_signed_digest.sh "docker.io/${DOCKERHUB_NAMESPACE}/${IMAGE_REPOSITORY}@${DIGEST}"'
        )
        assert verify["env"]["EXPECTED_REVISION"] == "${{ github.sha }}"
        assert verify["env"]["EXPECTED_RUN_IDS"] == "${{ github.run_id }}"
        assert (
            sign["env"]["DIGEST"] == verify["env"]["DIGEST"] == "${{ steps.push.outputs.digest }}"
        )
        assert "||" not in sign["run"] and "||" not in verify["run"]
        assert "continue-on-error" not in yaml.safe_dump(self.job)

    def test_it_has_what_those_scripts_need(self):
        uses = [str(s.get("uses", "")) for s in self.steps]
        assert any(u.startswith("actions/checkout@") for u in uses)
        cosign = next(s for s in self.steps if str(s.get("uses", "")).startswith("sigstore/"))
        real = next(
            s
            for s in _steps(self.doc["jobs"]["tag-images"])
            if str(s.get("uses", "")).startswith("sigstore/")
        )
        assert cosign["uses"] == real["uses"]
        assert cosign["with"] == real["with"] == {"cosign-release": "${{ env.COSIGN_VERSION }}"}
        checkout = next(
            s for s in self.steps if str(s.get("uses", "")).startswith("actions/checkout@")
        )
        assert checkout["with"] == {"persist-credentials": False}

    def test_the_image_has_the_provenance_the_sbom_and_the_revision_label_the_real_build_has(self):
        push = next(s for s in self.steps if s.get("id") == "push")
        assert push["with"]["provenance"] is True and push["with"]["sbom"] is True
        assert "org.opencontainers.image.revision=${{ github.sha }}" in push["with"]["labels"]

    def test_it_explains_a_failure_and_logs_out_at_the_end(self):
        hint = next(s for s in self.steps if s.get("name") == "What to check if this failed")
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
        assert general["if"] == (
            "failure() && steps.scout.outcome != 'failure' && steps.sign.outcome != 'failure'"
            " && steps.verify.outcome != 'failure' && steps.retag.outcome != 'failure'"
        )
        crypto = next(
            s for s in self.steps if "signing, verifying or tagging failed" in s.get("name", "")
        )
        assert crypto["if"] == (
            "failure() && (steps.sign.outcome == 'failure' || steps.verify.outcome == 'failure'"
            " || steps.retag.outcome == 'failure')"
        )
        assert "DOCKERHUB_ENABLED" in crypto["run"] and "Referrers" in crypto["run"]

    def test_it_claims_nothing_about_docker_hub_deleting_untagged_images(self):
        text = BUILD.read_text(encoding="utf-8")
        assert "garbage-collect" not in text and "garbage collect" not in text


class TestBuildWorkflowStandsAlone:
    """200 builds, scans, signs, tags and records. It dispatches nothing, opens no pull request, writes no file back."""

    def setup_method(self):
        self.text = BUILD.read_text(encoding="utf-8")
        self.doc = _load(BUILD)

    def test_the_jobs_are_exactly_the_build_the_tagging_and_the_login_rehearsal(self):
        assert sorted(self.doc["jobs"]) == [
            "build-images",
            "build-web",
            "rehearse-docker-login",
            "tag-images",
        ]

    def test_the_only_input_is_the_rehearsal_switch(self):
        trigger = self.doc.get("on", self.doc.get(True))
        assert sorted(trigger["workflow_dispatch"]["inputs"]) == ["rehearsal"]

    def test_no_job_can_write_to_the_repository_or_uses_an_environment(self):
        assert self.doc["permissions"] == {}
        for name, job in self.doc["jobs"].items():
            permissions = job.get("permissions", {})
            assert permissions.get("contents") == "read", name
            assert set(permissions) <= {"contents", "id-token"}, (name, permissions)
            assert "environment" not in job, name
            assert "outputs" not in job or all(
                key.startswith(("digest_", "tags_")) for key in job["outputs"]
            ), name

    def test_every_job_that_publishes_or_rehearses_runs_on_the_default_branch_only(self):
        guard = "github.ref == format('refs/heads/{0}', github.event.repository.default_branch)"
        for name in ("build-images", "build-web", "tag-images", "rehearse-docker-login"):
            assert guard in str(self.doc["jobs"][name]["if"]), name

    def test_a_rehearsal_has_a_concurrency_group_of_its_own(self):
        group = self.doc["concurrency"]["group"]
        assert group == (
            "${{ github.workflow }}-${{ github.ref }}-${{ inputs.rehearsal && 'rehearsal' || 'build' }}"
        )
        assert self.doc["concurrency"]["cancel-in-progress"] is False

    def test_the_rehearsal_input_describes_what_the_job_really_does(self):
        trigger = self.doc.get("on", self.doc.get(True))
        text = " ".join(trigger["workflow_dispatch"]["inputs"]["rehearsal"]["description"].split())
        for needle in (
            "SIGNED and ATTESTED and VERIFIED",
            "rehearsal-<run id>",
            "transparency logs",
            "cannot be removed",
            "nothing is deleted",
        ):
            assert needle in text, needle
        assert "nothing is tagged or signed" not in text.lower()

    def test_the_rehearsal_comment_states_the_residual_facts(self):
        text = self.text
        for needle in (
            "indistinguishable from a real one by identity alone",
            "rehearsal=true",
            "cannot be removed",
            "EXPECTED_RUN_IDS",
            "its own concurrency group",
        ):
            assert needle in " ".join(text.split()), needle
        finder = (REPO_ROOT / "scripts" / "ci" / "find_release_image.sh").read_text(
            encoding="utf-8"
        )
        assert "rehearsal run" in finder and "revision label" in finder

    def test_tag_images_may_move_latest_only_from_the_tip_of_the_default_branch(self):
        job = self.doc["jobs"]["tag-images"]
        step = _steps(job)[_index_of(job, "Verify, tag and record")]
        assert step["env"]["GH_TOKEN"] == "${{ github.token }}"
        assert step["env"]["DEFAULT_BRANCH"] == "${{ github.event.repository.default_branch }}"
        script = step["run"]
        tip = script.index(
            'gh api "repos/${GITHUB_REPOSITORY}/commits/${DEFAULT_BRANCH}" --jq .sha'
        )
        assert tip < script.index('write_table "Verified') < script.index("imagetools create")
        assert job["permissions"] == {"contents": "read", "id-token": "write"}
        header = self.text.split("\non:\n", 1)[0]
        flat = " ".join(header.split())
        assert "move only while the built commit is still current" in flat
        assert "scripts/ci/paths_touch_build.py" in flat and "there is one list and no copy" in flat
        assert "does not strand the tags" in flat
        # The by-design case and the transition are written down.
        assert "build A running, B replaced by C, C fails its scan" in flat
        assert "*-latest stays at the build before A" in flat
        assert "Transition" in " ".join(
            self.text.split()
        ) and "the tip guard covers `*-latest`" in " ".join(self.text.split())
        assert "the run of the tip owns" not in self.text and "only the tip" not in flat

    def test_tag_images_asks_for_the_longest_token_too(self):
        job = self.doc["jobs"]["tag-images"]
        assert int(_steps(job)[_login_index(job)]["env"]["DOCKERHUB_OIDC_EXPIREIN"]) == EXPIRE_MAX

    def test_the_header_documents_that_tagging_is_not_atomic_and_how_to_recover(self):
        header = self.text.split("\non:\n", 1)[0]
        assert "Tagging is NOT atomic" in header and "Re-run failed jobs" in header
        assert "imagetools create" in header and "idempotent" not in header.replace(
            "gives a tag the digest it already has", ""
        )
        concurrency = self.text.split("concurrency:", 1)[0].rsplit("# Never cancel", 1)[1]
        assert "not\n# atomic" in concurrency or "is not\n# atomic" in concurrency
        assert "all-or-nothing" not in self.text

    def test_it_reads_no_secret_and_only_the_docker_hub_variables(self):
        assert "secrets." not in self.text.replace("secrets.GITHUB_TOKEN", "")
        used = set(re.findall(r"vars\.([A-Z_]+)", self.text))
        assert used == {"DOCKERHUB_CONNECTION", "DOCKERHUB_ENABLED", "DOCKERHUB_NAMESPACE"}


class TestTagImagesVerifiesAndRecords:
    def setup_method(self):
        self.doc = _load(BUILD)
        self.job = self.doc["jobs"]["tag-images"]
        self.step = _steps(self.job)[_index_of(self.job, "Verify, tag and record")]
        self.script = self.step["run"]

    def test_the_script_and_cosign_are_available_before_the_step(self):
        step = _index_of(self.job, "Verify, tag and record")
        checkout = next(
            i
            for i, s in enumerate(_steps(self.job))
            if str(s.get("uses", "")).startswith("actions/checkout@")
        )
        cosign = next(
            i
            for i, s in enumerate(_steps(self.job))
            if str(s.get("uses", "")).startswith("sigstore/cosign-installer@")
        )
        assert checkout < step and cosign < step
        assert _steps(self.job)[cosign]["with"]["cosign-release"] == "${{ env.COSIGN_VERSION }}"
        assert _steps(self.job)[checkout]["with"] == {"persist-credentials": False}

    def test_every_digest_is_verified_for_this_commit_and_run_before_any_tag_moves(self):
        env = self.step["env"]
        assert env["EXPECTED_REVISION"] == "${{ github.sha }}"
        assert env["EXPECTED_RUN_IDS"] == "${{ github.run_id }}"
        verify = self.script.index("scripts/ci/verify_signed_digest.sh")
        assert verify < self.script.index("imagetools create")
        assert re.search(
            r'for c in \$COMPONENTS; do\s+if bash scripts/ci/verify_signed_digest\.sh "\$\{IMAGE\}@\$\{DIGESTS\[\$c\]\}"',
            self.script,
        )
        refuse = self.script.index('if [ "$UNSIGNED" -gt 0 ]; then')
        assert verify < refuse < self.script.index("imagetools create")
        assert re.search(r'refusing to tag anything\."\s+exit 1\s+fi', self.script[refuse:])

    def test_a_failed_verification_is_not_made_optional(self):
        assert "|| true" not in self.script and "|| :" not in self.script
        assert "continue-on-error" not in yaml.safe_dump(self.job)
        assert "set +e" not in self.script

    def test_the_digest_table_has_one_row_per_component_with_tags_digest_and_signed(self):
        assert "$GITHUB_STEP_SUMMARY" in self.script
        assert "| Component | Tags | Digest | Signed |" in self.script
        assert 'COMPONENTS="cli api worker web migrator"' in self.script
        assert "${SIGNED[$c]}" in self.script and "${DIGESTS[$c]}" in self.script
        # The table is written on both paths: when something did not verify (before the refusal) and at the end.
        assert self.script.count("write_table ") == 2

    def test_the_job_cannot_write_to_the_repository(self):
        assert self.job["permissions"] == {"contents": "read", "id-token": "write"}


class TestReleaseListsTheFiveDigests:
    def setup_method(self):
        self.text = RELEASE.read_text(encoding="utf-8")
        self.doc = _load(RELEASE)
        self.job = self.doc["jobs"]["verify"]
        self.release = self.doc["jobs"]["release"]

    def _step(self, needle: str) -> dict:
        for job in (self.job, self.release):
            for step in _steps(job):
                if needle in step.get("name", ""):
                    return step
        raise AssertionError(f"no step named like {needle!r}")

    def test_the_other_four_images_are_found_and_verified_before_any_write(self):
        find = _index_of(self.job, "Find the scanned image")
        verify = _index_of(self.job, "Verify the signature")
        others = _index_of(self.job, "Find and verify the other images")
        report = _index_of(self.job, "Report what a release would promote")
        assert find < verify < others < report
        assert _login_index(self.job) is None and _login_index(self.release) is not None
        assert self.release["needs"] == "verify"

    def test_that_step_is_the_script_and_cannot_be_made_optional(self):
        step = self._step("Find and verify the other images")
        assert step["run"] == "bash scripts/ci/release_digests.sh"
        assert set(step) <= {"name", "id", "env", "run"}
        assert step["id"] == "others"
        # One run, the one that built the CLI image: not every run of the commit.
        assert step["env"] == {
            "BUILD_COMMIT": "${{ steps.scanned.outputs.build_commit }}",
            "RUN_IDS": "${{ steps.cli.outputs.builder_run_id }}",
        }

    def test_the_release_notes_carry_all_five_digests_and_the_verification_command(self):
        body = self._step("Create GitHub Release")["with"]["body"]
        for expression in (
            "needs.verify.outputs.digest",
            "needs.verify.outputs.digest_api",
            "needs.verify.outputs.digest_worker",
            "needs.verify.outputs.digest_web",
            "needs.verify.outputs.digest_migrator",
            "needs.verify.outputs.build_commit",
        ):
            assert "${{ " + expression + " }}" in body, expression
        for tag in (
            "`${{ steps.version.outputs.VERSION }}`",
            "`api-${{ steps.version.outputs.VERSION }}`",
            "`worker-${{ steps.version.outputs.VERSION }}`",
            "`web-${{ steps.version.outputs.VERSION }}`",
            "`migrator-${{ steps.version.outputs.VERSION }}`",
        ):
            assert tag in body, tag
        assert "Only the CLI image" not in body
        assert "cosign verify " in body and "cosign verify-attestation" in body
        assert ".predicate.builder.id" in body, (
            "the release notes check the builder, not only the attestation type"
        )
        assert "--certificate-identity" in body and "--certificate-oidc-issuer" in body
        assert "/.github/workflows/200-build-images.yml@refs/heads/main" in body

    def test_the_dry_run_report_lists_all_five_digests_too(self):
        step = self._step("Report what a release would promote")
        assert {k: v for k, v in step["env"].items() if k.startswith("DIGEST")} == {
            "DIGEST": "${{ steps.scanned.outputs.digest }}",
            "DIGEST_API": "${{ steps.others.outputs.digest_api }}",
            "DIGEST_WORKER": "${{ steps.others.outputs.digest_worker }}",
            "DIGEST_WEB": "${{ steps.others.outputs.digest_web }}",
            "DIGEST_MIGRATOR": "${{ steps.others.outputs.digest_migrator }}",
        }
        assert "| Component | Tag | Digest |" in step["run"]
        for component in ("cli", "api", "worker", "web", "migrator"):
            assert f"| {component} |" in step["run"], component

    def test_the_release_stays_independent_of_any_file_a_build_commits(self):
        assert "latest-build" not in self.text and ".deployment-catalog" not in self.text


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
