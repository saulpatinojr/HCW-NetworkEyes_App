"""CI hygiene: hadolint, actionlint and dependency review stay wired in, pinned, and justified (tickets #247, #252, #253).

What is pinned here and why:

* The job names in `300-test-codebase.yml` are required checks of the "Protect main" ruleset. Renaming one
  leaves a check that never reports, which blocks every pull request; the existing names are listed below and
  the new ones are asserted to exist so nobody removes them quietly.
* The tool images (hadolint, actionlint, Trivy) are pinned by digest. A tag can be moved to different content
  (Trivy's was, on 2026-03-19, GHSA-69fq-xp46-6x23); a digest cannot.
* `.hadolint.yaml` may ignore only the rules approved below, each with a written reason beside it.
* The `image-scan` job (TODO.md T-737) builds the migrator and web runner images in every pull request and scans
  them with the same Trivy digest as the local script; `.trivyignore.yaml` suppresses only what it names, by rule
  id and path, with the reason written beside it.
* The four Dockerfiles keep the properties the lint fixes gave them, so a later edit cannot undo them without a
  test failing: digests on every base image, numeric `USER`, exec-form `CMD`/`ENTRYPOINT`/`HEALTHCHECK`, and
  `pipefail` wherever a `RUN` has a pipe.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_300 = REPO_ROOT / ".github" / "workflows" / "300-test-codebase.yml"
LOCAL_CHECKS = REPO_ROOT / "scripts" / "ci" / "local-container-checks.sh"
HARDEN_FLAGS = REPO_ROOT / "scripts" / "ci" / "harden-flags.sh"
HADOLINT_CONFIG = REPO_ROOT / ".hadolint.yaml"
TRIVY_IGNORE = REPO_ROOT / ".trivyignore.yaml"

# Job names that exist today and are required checks of the "Protect main" ruleset (read 2026-10-25).
# `Unit Tests (Python ...)` is a template in the workflow; the ruleset holds the rendered 3.14 form.
REQUIRED_CHECK_JOB_NAMES = {
    "Lint & Format",
    "Unit Tests (Python ${{ matrix.python-version }})",
    "Web lint, typecheck & tests",
    "Python Lockfile Consistency",
    "Python Dependency Audit (pip-audit)",
    "Secret Scanning (detect-secrets, gating)",
    "Repository Guardrails",
}
# Jobs this change added. They are required checks of the ruleset now; `test_repository_admin_required_checks.py`
# pins the full list against `390-repository-admin.yml`.
NEW_JOB_NAMES = {
    "dockerfile-lint": "Dockerfile Lint (hadolint)",
    "workflow-lint": "Workflow Lint (actionlint)",
    "dependency-review": "Dependency Review",
    "image-scan": "Image Scan (Trivy)",
}

# The only rules `.hadolint.yaml` may ignore; adding to this set is a reviewed decision.
APPROVED_HADOLINT_IGNORES = {"DL3008", "DL3018"}
# Inline pragmas allowed in Dockerfiles: (file, rule).
APPROVED_INLINE_PRAGMAS = {("Dockerfile", "DL3006")}

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}\b")


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW_300.read_text(encoding="utf-8"))


def workflow_text() -> str:
    return WORKFLOW_300.read_text(encoding="utf-8")


def script_text() -> str:
    return LOCAL_CHECKS.read_text(encoding="utf-8")


def script_pin(variable: str) -> str:
    match = re.search(rf'^{variable}="([^"]+)"', script_text(), re.MULTILINE)
    assert match, f"{variable} is not set in local-container-checks.sh"
    return match.group(1)


def tracked_dockerfiles() -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--", "Dockerfile", "*/Dockerfile"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [REPO_ROOT / line for line in result.stdout.splitlines() if line]


def instructions(path: Path) -> list[tuple[int, str, str]]:
    """(line number, KEYWORD, arguments) for each Dockerfile instruction, continuations joined, comments dropped."""
    result: list[tuple[int, str, str]] = []
    pending, start = "", 0
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not pending and (not line or line.startswith("#")):
            continue
        if not pending:
            start = number
        if pending and line.startswith("#"):
            continue  # a comment line inside a continued instruction
        if line.endswith("\\"):
            pending += line[:-1].strip() + " "
            continue
        full = (pending + line).strip()
        pending = ""
        keyword, _, arguments = full.partition(" ")
        result.append((start, keyword.upper(), arguments.strip()))
    return result


# --- workflow 300: job names ---


def test_existing_required_check_job_names_are_unchanged() -> None:
    names = {job["name"] for job in workflow()["jobs"].values()}
    missing = REQUIRED_CHECK_JOB_NAMES - names
    assert not missing, f"required-check job name(s) renamed or removed: {sorted(missing)}"


def test_new_jobs_exist_with_their_documented_names() -> None:
    jobs = workflow()["jobs"]
    for job_id, name in NEW_JOB_NAMES.items():
        assert job_id in jobs, job_id
        assert jobs[job_id]["name"] == name


def test_job_names_are_unique() -> None:
    names = [job["name"] for job in workflow()["jobs"].values()]
    assert len(names) == len(set(names))


def test_every_job_in_300_has_a_timeout() -> None:
    for job_id, job in workflow()["jobs"].items():
        assert "timeout-minutes" in job, job_id


# --- workflow 300: the new jobs ---


def test_dependency_review_is_pull_request_only_least_privilege_and_sha_pinned() -> None:
    job = workflow()["jobs"]["dependency-review"]
    assert job["if"] == "github.event_name == 'pull_request'"
    assert job["permissions"] == {"contents": "read"}
    steps = [s for s in job["steps"] if "dependency-review-action" in s.get("uses", "")]
    assert len(steps) == 1
    assert re.fullmatch(r"actions/dependency-review-action@[0-9a-f]{40}", steps[0]["uses"])
    assert steps[0]["with"]["fail-on-severity"] in {"moderate", "high", "critical"}
    # persist-credentials: false on the checkout, the repo's other new jobs do the same.
    checkout = job["steps"][0]
    assert checkout["with"]["persist-credentials"] is False


def test_hadolint_job_uses_the_digest_pinned_image_and_the_reviewed_config() -> None:
    run = "\n".join(s.get("run", "") for s in workflow()["jobs"]["dockerfile-lint"]["steps"])
    assert script_pin("HADOLINT_IMAGE") in run, (
        "the workflow and local-container-checks.sh pin different hadolint images"
    )
    assert "--config .hadolint.yaml" in run
    assert "git ls-files" in run, (
        "hadolint must find Dockerfiles from git, not from a list that goes stale"
    )
    assert "--network none" in run
    assert_hardened(run)


def test_actionlint_job_uses_the_digest_pinned_image() -> None:
    run = "\n".join(s.get("run", "") for s in workflow()["jobs"]["workflow-lint"]["steps"])
    assert script_pin("ACTIONLINT_IMAGE") in run, (
        "the workflow and local-container-checks.sh pin different actionlint images"
    )
    assert ".github/workflows/*.yml" in run
    assert "--network none" in run
    assert_hardened(run)


def assert_hardened(run: str) -> None:
    """A CI tool container gets the shared hardening flags, not a copy of them."""
    assert "source ./scripts/ci/harden-flags.sh" in run
    assert re.search(r'docker run "\$\{HARDEN\[@\]\}"', run), (
        "docker run must use the shared HARDEN flags"
    )
    assert not re.search(r"docker run[^\n]*--(?:rm|read-only|cap-drop|security-opt)", run), (
        "the hardening flags are written once, in scripts/ci/harden-flags.sh"
    )


@pytest.mark.parametrize("job_id", ("dockerfile-lint", "workflow-lint"))
def test_the_lint_jobs_hold_only_the_checkout_permission(job_id: str) -> None:
    # The workflow grants `pull-requests: read` for other jobs; these two only check out and run a container.
    assert workflow()["jobs"][job_id]["permissions"] == {"contents": "read"}


def test_the_shared_hardening_flags_are_the_complete_set() -> None:
    text = HARDEN_FLAGS.read_text(encoding="utf-8")
    assert "HARDEN=(--rm --read-only --cap-drop ALL --security-opt no-new-privileges)" in text
    assert "source ./scripts/ci/harden-flags.sh" in script_text()
    assert "HARDEN=(" not in script_text(), "local-container-checks.sh must not define its own copy"


def image_scan_runs() -> dict[str, str]:
    return {
        s.get("name", s.get("uses", "")): s.get("run", "")
        for s in workflow()["jobs"]["image-scan"]["steps"]
    }


def test_image_scan_job_is_least_privilege_and_does_not_keep_credentials() -> None:
    job = workflow()["jobs"]["image-scan"]
    assert job["permissions"] == {"contents": "read"}
    checkout = job["steps"][0]
    assert re.fullmatch(r"actions/checkout@[0-9a-f]{40}", checkout["uses"])
    assert checkout["with"]["persist-credentials"] is False


def test_image_scan_job_uses_the_trivy_pin_of_the_local_script() -> None:
    job = workflow()["jobs"]["image-scan"]
    assert job["env"]["TRIVY_IMAGE"] == script_pin("TRIVY_IMAGE"), (
        "the workflow and local-container-checks.sh pin different Trivy images"
    )
    assert DIGEST.search(job["env"]["TRIVY_IMAGE"])
    for name, run in image_scan_runs().items():
        if "trivy" in run.lower() and "TRIVY_IMAGE" not in run:
            raise AssertionError(f"step {name!r} names Trivy without the pinned $TRIVY_IMAGE")


def test_image_scan_job_builds_the_migrator_and_runner_targets() -> None:
    run = "\n".join(image_scan_runs().values())
    assert "docker build --target migrator" in run
    assert "docker build --target runner" in run
    assert "apps/cna-web" in run


def test_image_scan_job_scans_with_the_gating_flags_and_the_hardened_container() -> None:
    runs = image_scan_runs()
    scan = next(run for name, run in runs.items() if name.startswith("Trivy"))
    for flag in (
        "--severity HIGH,CRITICAL",
        "--ignore-unfixed",
        "--exit-code 1",
        "--ignorefile /work/.trivyignore.yaml",
        "--scanners vuln,secret",
        "--skip-db-update",
        "--network none",
        "--read-only",
        "--cap-drop ALL",
        "--security-opt no-new-privileges",
        ":/scan:ro",
        ":/work:ro",
    ):
        assert flag in scan, f"the Trivy scan step lacks {flag}"
    assert "migrator runner" in scan, "both images are scanned"
    # The database download is the only step that reaches the network, and it is hardened too.
    download = next(run for name, run in runs.items() if name.startswith("Export"))
    assert "--download-db-only" in download
    assert "--cap-drop ALL" in download and "--security-opt no-new-privileges" in download
    assert "--network none" not in download


def test_image_scan_job_never_widens_the_sandbox() -> None:
    text = "\n".join(image_scan_runs().values())
    for forbidden in (
        "docker login",
        "docker push",
        "--privileged",
        "docker.sock",
        "--network host",
    ):
        assert forbidden not in text, forbidden


def test_image_scan_job_checks_the_migrator_tree_inside_the_built_image() -> None:
    run = image_scan_runs()[
        "The migrator holds Prisma and no build tooling, and the runner holds no Prisma CLI"
    ]
    for banned in ("typescript", "@typescript", "eslint", "vitest", "vite", "tailwindcss", "next"):
        assert banned in run, banned
    for required in ("node_modules/.bin/prisma", ".prisma", "@prisma"):
        assert required in run, required
    assert "prisma validate" in run
    assert "package-lock.json" in run, "the installed tree is compared with the lockfile"
    assert "cna-scan-runner:ci" in run, "the runner is checked for the absence of the Prisma CLI"


def trivy_ignore() -> dict:
    return yaml.safe_load(TRIVY_IGNORE.read_text(encoding="utf-8")) or {}


def test_trivy_ignore_file_suppresses_only_secrets_by_rule_id_and_path() -> None:
    config = trivy_ignore()
    assert set(config) == {"secrets"}, (
        "only secret rules may be suppressed here; a fixable vulnerability is fixed, not ignored"
    )
    assert config["secrets"], "an empty suppression list should be a deleted file"
    for entry in config["secrets"]:
        assert set(entry) == {"id", "paths", "statement"}, entry
        assert re.fullmatch(r"[a-z0-9-]+", entry["id"]), entry
        assert entry["statement"].strip()
        assert entry["paths"], entry
        for path in entry["paths"]:
            assert path.startswith("/app/"), f"{path}: a glob must start at the image's /app"
            literal = re.sub(r"\*+", "", path).strip("/.")
            assert literal.count("/") >= 3, f"{path}: too broad to be a narrow suppression"


def test_every_trivy_secret_suppression_has_a_written_reason_above_it() -> None:
    lines = TRIVY_IGNORE.read_text(encoding="utf-8").splitlines()
    checked = set()
    for index, line in enumerate(lines):
        match = re.match(r"\s*-\s+id:\s+(\S+)\s*$", line)
        if not match:
            continue
        block: list[str] = []
        cursor = index - 1
        while cursor >= 0 and lines[cursor].lstrip().startswith("#"):
            block.insert(0, lines[cursor])
            cursor -= 1
        comment = " ".join(part.lstrip("# ").strip() for part in block)
        assert "Why suppressed" in comment, (
            f"{match.group(1)}: start the reason with 'Why suppressed'"
        )
        assert len(comment) > 300, (
            f"{match.group(1)}: the reason is too short to be a justification"
        )
        assert match.group(1) in comment or "Trivy's `" + match.group(1) + "`" in comment
        checked.add(match.group(1))
    assert checked == {entry["id"] for entry in trivy_ignore()["secrets"]}


@pytest.mark.parametrize("variable", ("HADOLINT_IMAGE", "ACTIONLINT_IMAGE", "TRIVY_IMAGE"))
def test_tool_images_are_pinned_by_digest(variable: str) -> None:
    assert DIGEST.search(script_pin(variable)), f"{variable} has no sha256 digest"


def test_trivy_is_new_enough_for_the_known_advisories() -> None:
    """GHSA-69fq-xp46-6x23 (malicious 0.69.4 to 0.69.6) and the plugin path-traversal fix in 0.72.0."""
    version = re.search(r"trivy:(\d+)\.(\d+)\.(\d+)@", script_pin("TRIVY_IMAGE"))
    assert version, "the Trivy image must be pinned by version and digest"
    assert tuple(int(part) for part in version.groups()) >= (0, 72, 0)


def test_every_tool_image_named_in_300_is_pinned_by_digest() -> None:
    """The gitleaks, hadolint and actionlint images all carry a digest, wherever they appear."""
    references = re.findall(
        r"(?:zricethezav/gitleaks|hadolint/hadolint|rhysd/actionlint):[\w.-]+(?:@sha256:[0-9a-f]{64})?",
        workflow_text(),
    )
    assert len(references) >= 3, "the gitleaks, hadolint and actionlint images should all be found"
    for reference in references:
        assert DIGEST.search(reference), f"{reference} is pinned by tag only"


def test_tools_installed_with_pip_in_300_are_pinned_to_an_exact_version() -> None:
    """ruff, pre-commit, pip-audit, uv and pyyaml are installed with an exact version, so a run is repeatable."""
    pinned = ("pip-audit", "ruff", "pre-commit", "uv", "pyyaml")
    for line in workflow_text().splitlines():
        code = line.split("#", 1)[0]
        if "pip install" not in code or "pip install -e" in code or "uv pip install" in code:
            continue
        for name in pinned:
            if re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", code):
                assert re.search(rf'"{re.escape(name)}==\d', code), (
                    f"{name} is not pinned to an exact version in: {line.strip()}"
                )


def test_shell_in_300_quotes_the_extras_glob() -> None:
    """actionlint's shellcheck flagged `.[dev,...]` (SC2102): unquoted, the shell may treat it as a glob."""
    assert 'pip install -e ".[dev,enrichment,api,aws]"' in workflow_text()
    assert "pip install -e .[" not in workflow_text()


# --- the local script ---


def test_local_script_never_logs_in_pushes_or_widens_the_sandbox() -> None:
    text = script_text()
    for forbidden in (
        "docker login",
        "docker push",
        "--privileged",
        "docker.sock",
        "--network host",
        "--pid host",
        "--ipc host",
    ):
        assert forbidden not in text, forbidden
    # Every tool container is disposable and runs with the shared hardening flags.
    assert 'docker run "${HARDEN[@]}"' in text
    assert text.count("docker run ") == text.count('docker run "${HARDEN[@]}"'), (
        "every docker run is hardened"
    )


def test_local_image_scan_follows_the_ci_policy() -> None:
    """trivy-image reports fixable findings only and reads the same suppressions as the CI job."""
    text = script_text()
    assert "--ignore-unfixed" in text
    assert "--ignorefile /work/.trivyignore.yaml" in text
    assert "TRIVY_IGNORE_UNFIXED" in text


def test_local_script_with_no_check_named_stops_with_exit_code_2() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    result = subprocess.run(
        [bash, str(LOCAL_CHECKS)],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        timeout=120,
        check=False,
    )
    # 2 whether docker is missing, the engine is down, the context is not allowed, or no check was named.
    assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
    assert "ERROR:" in result.stderr


def test_local_script_is_valid_bash() -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is not available")
    result = subprocess.run(
        [bash, "-n", str(LOCAL_CHECKS)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


# --- .hadolint.yaml ---


def hadolint_ignores() -> list[str]:
    return (yaml.safe_load(HADOLINT_CONFIG.read_text(encoding="utf-8")) or {}).get("ignored", [])


def test_hadolint_ignores_only_approved_rules() -> None:
    ignored = hadolint_ignores()
    assert set(ignored) <= APPROVED_HADOLINT_IGNORES, (
        f"unapproved ignore(s): {sorted(set(ignored) - APPROVED_HADOLINT_IGNORES)}"
    )
    assert len(ignored) == len(set(ignored))


def test_every_ignored_hadolint_rule_has_a_written_reason_above_it() -> None:
    """The comment block directly above a run of ignored rules must name each rule and give a reason."""
    lines = HADOLINT_CONFIG.read_text(encoding="utf-8").splitlines()
    checked: set[str] = set()
    for index, line in enumerate(lines):
        match = re.match(r"\s*-\s+(DL\d{4})\s*$", line)
        if not match:
            continue
        # Walk up over the other ignored rules in the same group, then collect the comment block above them.
        top = index
        while top > 0 and re.match(r"\s*-\s+DL\d{4}\s*$", lines[top - 1]):
            top -= 1
        block: list[str] = []
        cursor = top - 1
        while cursor >= 0 and lines[cursor].lstrip().startswith("#"):
            block.insert(0, lines[cursor])
            cursor -= 1
        comment = " ".join(part.lstrip("# ").strip() for part in block)
        rule = match.group(1)
        assert rule in comment, f"{rule} is not named in the comment above it"
        assert "Why ignored" in comment, (
            f"{rule}: the comment must start its reason with 'Why ignored'"
        )
        assert len(comment) > 300, f"{rule}: the reason is too short to be a justification"
        checked.add(rule)
    assert checked == set(hadolint_ignores())


def test_hadolint_fails_on_every_severity() -> None:
    config = yaml.safe_load(HADOLINT_CONFIG.read_text(encoding="utf-8"))
    assert config["failure-threshold"] in {"style", "info"}


# --- Dockerfiles ---


def test_the_four_dockerfiles_are_tracked() -> None:
    names = sorted(p.relative_to(REPO_ROOT).as_posix() for p in tracked_dockerfiles())
    assert names == [
        "Dockerfile",
        "apps/cna-api/Dockerfile",
        "apps/cna-web/Dockerfile",
        "apps/cna-worker/Dockerfile",
    ]


@pytest.mark.parametrize(
    "path", tracked_dockerfiles(), ids=lambda p: p.relative_to(REPO_ROOT).as_posix()
)
class TestDockerfileHygiene:
    def test_every_external_base_image_is_pinned_by_digest(self, path: Path) -> None:
        stages = set()
        for number, keyword, arguments in instructions(path):
            if keyword != "FROM":
                continue
            parts = arguments.split()
            image = parts[0]
            if len(parts) >= 3 and parts[1].upper() == "AS":
                stages.add(parts[2])
            if image in stages or image.startswith("final-"):
                continue  # a reference to an earlier stage, not an external image
            assert DIGEST.search(image), f"{path.name}:{number} FROM {image} has no digest"

    def test_user_is_numeric(self, path: Path) -> None:
        users = [(n, a) for n, k, a in instructions(path) if k == "USER"]
        assert users, "every Dockerfile drops root"
        for number, value in users:
            assert re.fullmatch(r"\d+(:\d+)?", value), f"line {number}: USER {value} is not numeric"
            assert not value.startswith("0"), f"line {number}: USER {value} is root"

    def test_each_numeric_user_is_the_uid_its_stage_created(self, path: Path) -> None:
        # `USER 1001` is only meaningful if that uid is the account the same stage made with --uid.
        stage_uids: set[str] = set()
        for number, keyword, arguments in instructions(path):
            if keyword == "FROM":
                stage_uids = set()
            elif keyword == "RUN":
                for command in re.finditer(r"\b(?:useradd|adduser)\b([^&|;]*)", arguments):
                    stage_uids.update(re.findall(r"--uid\s+(\d+)", command.group(1)))
            elif keyword == "USER":
                uid = arguments.split(":")[0]
                assert uid in stage_uids, (
                    f"line {number}: USER {arguments} is not the --uid of a useradd/adduser in the same stage "
                    f"(found {sorted(stage_uids) or 'none'})"
                )

    def test_cmd_entrypoint_and_healthcheck_use_the_exec_form(self, path: Path) -> None:
        for number, keyword, arguments in instructions(path):
            if keyword in {"CMD", "ENTRYPOINT"}:
                command = arguments
            elif keyword == "HEALTHCHECK":
                if arguments.upper().startswith("NONE"):
                    continue
                command = re.sub(r"^(?:--[\w-]+=\S+\s+)*CMD\s+", "", arguments)
            else:
                continue
            assert command.startswith("[") and command.endswith("]"), (
                f"line {number}: {keyword} is in shell form"
            )
            assert command.count('"') >= 2, (
                f"line {number}: {keyword} must use double quotes (JSON)"
            )

    def test_a_pipe_in_a_run_instruction_has_pipefail(self, path: Path) -> None:
        pipefail_shell = False
        for number, keyword, arguments in instructions(path):
            if keyword == "FROM":
                pipefail_shell = False
            elif keyword == "SHELL":
                pipefail_shell = "pipefail" in arguments
            elif keyword == "RUN" and re.search(r"(?<!\|)\|(?!\|)", arguments):
                assert pipefail_shell or "pipefail" in arguments, (
                    f"line {number}: RUN has a pipe without pipefail"
                )

    def test_inline_hadolint_pragmas_are_the_approved_ones_with_a_reason(self, path: Path) -> None:
        lines = path.read_text(encoding="utf-8").splitlines()
        relative = path.relative_to(REPO_ROOT).as_posix()
        for index, line in enumerate(lines):
            match = re.match(r"\s*#\s*hadolint\s+ignore=([\w,]+)", line)
            if not match:
                continue
            for rule in match.group(1).split(","):
                assert (relative, rule) in APPROVED_INLINE_PRAGMAS, (
                    f"{relative}:{index + 1} ignores {rule}"
                )
            assert index > 0 and lines[index - 1].lstrip().startswith("#"), (
                "an inline ignore needs a reason above it"
            )
