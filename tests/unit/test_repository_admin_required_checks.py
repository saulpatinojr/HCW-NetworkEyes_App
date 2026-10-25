"""The repository-admin workflow cannot drift from the live rulesets, or silently weaken them.

``390-repository-admin.yml`` builds the "Protect main" ruleset from a hard-coded ``REQUIRED_CHECKS`` list and
replaces the live ruleset with a PUT. On 2026-10-25 the live ruleset required 11 checks and the list held 7:
running ``protect-main`` with ``apply`` would have dropped four required checks without a word. Two things stop
that from happening again, and both are pinned here:

* **The list is pinned twice.** Every name in ``REQUIRED_CHECKS`` must be a real job name in
  ``300-test-codebase.yml`` (a name that no job reports blocks every pull request for good), and the list must
  equal ``EXPECTED_REQUIRED_CHECKS`` below. The second pin is deliberate friction: the live ruleset cannot be
  read from a test, so the list in the test is the record of what the ruleset is supposed to say.
* **The payloads are the live policy, and the task reads before it writes.** The payloads of ``protect-main``
  and ``protect-release-tags`` equal ``EXPECTED_MAIN`` and ``EXPECTED_TAGS`` below (the live rulesets, read
  2026-10-25 10:10 local), so an apply is a no-op today. Both tasks read the live ruleset, print what the update
  would remove, weaken, add or change, and in apply mode refuse (exit non-zero, no write) to remove a rule, a
  required check, a bypass actor or a ref pattern, to lower an approval count, or to switch off a protection,
  unless the input ``allow_weakening`` is ticked. The behaviour tests run the real step body with a stub ``gh``
  that answers from canned rulesets and records every call, and mutate the payload builder one setting at a time
  to prove each mutation is refused.

They need ``bash`` and ``jq``. GitHub's runners have both; a machine without them skips the behaviour tests,
and ``test_ci_has_the_tools`` fails on CI if either is missing so a skip can never hide there.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
ADMIN_WORKFLOW = WORKFLOWS / "390-repository-admin.yml"
TEST_WORKFLOW = WORKFLOWS / "300-test-codebase.yml"
STEP_NAME = "Run the chosen task"

# The required status checks of the live "Protect main" ruleset (read 2026-10-25, ruleset 25778319), in the
# order the ruleset lists them. CHANGING THE LIVE RULESET AND THIS LIST MUST HAPPEN TOGETHER: add or remove a
# check in the ruleset, in `REQUIRED_CHECKS` of 390-repository-admin.yml and here, in one pull request.
# Otherwise the next `protect-main` run undoes (or never applies) the change.
EXPECTED_REQUIRED_CHECKS = [
    "Lint & Format",
    "Unit Tests (Python 3.14)",
    "Web lint, typecheck & tests",
    "Python Lockfile Consistency",
    "Python Dependency Audit (pip-audit)",
    "Secret Scanning (detect-secrets, gating)",
    "Repository Guardrails",
    "Dockerfile Lint (hadolint)",
    "Workflow Lint (actionlint)",
    "Dependency Review",
    "Image Scan (Trivy)",
]

# The live rulesets (read 2026-10-25, ids 25778319 and 25778333, updated 10:09 and 10:10 local) as the payload
# builders of 390 must produce them, apart from `required_status_checks`, which comes from REQUIRED_CHECKS above.
# CHANGING A LIVE RULESET AND THESE TWO BASELINES MUST HAPPEN TOGETHER, like the check list.
EXPECTED_MAIN = {
    "name": "Protect main",
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
    "bypass_actors": [
        {"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "pull_request"}
    ],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {
            "type": "pull_request",
            "parameters": {
                "required_approving_review_count": 1,
                "dismiss_stale_reviews_on_push": True,
                "required_reviewers": [],
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_review_thread_resolution": True,
                "require_extra_approval_for_unattributed_changes": True,
                "allowed_merge_methods": ["merge", "squash", "rebase"],
            },
        },
        {
            "type": "required_status_checks",
            "parameters": {
                "strict_required_status_checks_policy": False,
                "do_not_enforce_on_create": False,
                "required_status_checks": [{"context": name} for name in EXPECTED_REQUIRED_CHECKS],
            },
        },
    ],
}
EXPECTED_TAGS = {
    "name": "Protect release tags",
    "target": "tag",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["refs/tags/v*"], "exclude": []}},
    "bypass_actors": [{"actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always"}],
    "rules": [
        {"type": "deletion"},
        {"type": "non_fast_forward"},
        {"type": "update"},
        {"type": "creation"},
    ],
}

# What `REQUIRED_CHECKS` held before this guard existed: the list that would have dropped the last four.
STALE_REQUIRED_CHECKS = EXPECTED_REQUIRED_CHECKS[:7]

BASH = shutil.which("bash")
JQ = shutil.which("jq")
needs_tools = pytest.mark.skipif(not (BASH and JQ), reason="bash and jq are required")


def _workflow(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _step() -> dict:
    steps = _workflow(ADMIN_WORKFLOW)["jobs"]["admin"]["steps"]
    matches = [step for step in steps if step.get("name") == STEP_NAME]
    assert len(matches) == 1, f"expected exactly one step named {STEP_NAME!r}"
    return matches[0]


def _required_checks() -> list[str]:
    return json.loads(_step()["env"]["REQUIRED_CHECKS"])


def _job_names_in_300() -> set[str]:
    """Every check name the jobs of 300 report, with ``${{ matrix.<key> }}`` rendered for each matrix value."""
    names: set[str] = set()
    for job_id, job in _workflow(TEST_WORKFLOW)["jobs"].items():
        name = job.get("name", job_id)
        matrix = (job.get("strategy") or {}).get("matrix") or {}
        rendered = [name]
        for key, values in matrix.items():
            placeholder = "${{ matrix." + key + " }}"
            if placeholder in name:
                rendered = [
                    text.replace(placeholder, str(value)) for text in rendered for value in values
                ]
        for text in rendered:
            assert "${{" not in text, f"job {job_id!r} has a name this test cannot render: {text!r}"
            names.add(text)
    return names


def test_ci_has_the_tools() -> None:
    if os.environ.get("CI") == "true":
        assert BASH and JQ, (
            "bash and jq must be on the CI runner; the behaviour tests would otherwise skip"
        )


# --- the list: real job names, and exactly the expected set ---


def test_every_required_check_is_a_job_name_in_300() -> None:
    jobs = _job_names_in_300()
    missing = [name for name in _required_checks() if name not in jobs]
    assert not missing, (
        f"REQUIRED_CHECKS names no job of 300-test-codebase.yml: {missing}. A required check that no job "
        "reports blocks every pull request."
    )


def test_required_checks_equal_the_expected_list() -> None:
    required = _required_checks()
    assert len(required) == len(set(required)), "REQUIRED_CHECKS has a duplicate"
    assert sorted(required) == sorted(EXPECTED_REQUIRED_CHECKS), (
        "REQUIRED_CHECKS in 390-repository-admin.yml differs from EXPECTED_REQUIRED_CHECKS in this test. "
        "The live 'Protect main' ruleset, REQUIRED_CHECKS and this list change together, in one pull request. "
        f"Only in the workflow: {sorted(set(required) - set(EXPECTED_REQUIRED_CHECKS))}. "
        f"Only in the test: {sorted(set(EXPECTED_REQUIRED_CHECKS) - set(required))}."
    )


def test_the_expected_list_is_itself_made_of_job_names() -> None:
    jobs = _job_names_in_300()
    assert [name for name in EXPECTED_REQUIRED_CHECKS if name not in jobs] == []


# --- the inputs and the shape of the step ---


def test_allow_weakening_is_an_explicit_boolean_that_defaults_to_false() -> None:
    workflow = _workflow(ADMIN_WORKFLOW)
    inputs = (workflow.get("on") or workflow.get(True))["workflow_dispatch"]["inputs"]
    assert inputs["allow_weakening"]["type"] == "boolean"
    assert inputs["allow_weakening"]["default"] is False
    # The dry run stays the default.
    assert inputs["apply"]["type"] == "boolean"
    assert inputs["apply"]["default"] is False
    assert _step()["env"]["ALLOW_WEAKENING"] == "${{ inputs.allow_weakening }}"


def test_only_one_place_writes_a_ruleset_and_it_compares_with_the_live_one_first() -> None:
    """A new task cannot replace a ruleset on its own: every write is inside ``upsert_ruleset``."""
    body = _step()["run"]
    assert body.count("-X PUT") == 1
    assert body.count("-X POST") == 1
    function_start = body.index("upsert_ruleset() {")
    compare = body.index('compare_ruleset "$name" "$payload"', function_start)
    refuse = body.index("exit 1", compare)
    assert function_start < compare < refuse < body.index("-X PUT") < body.index("-X POST")
    assert '"${ALLOW_WEAKENING:-false}" != "true"' in body[compare:refuse]


# --- behaviour: the real step body against a stub gh ---

STUB_GH = """#!/usr/bin/env bash
# Stub of `gh api`: answers from the canned files in $FAKE_GH_DIR and records every call there.
set -euo pipefail
[ "$1" = "api" ] || { echo "stub gh: unsupported: $*" >&2; exit 2; }
shift
method=GET; path=""; jq_expr=""
while [ $# -gt 0 ]; do
  case "$1" in
    -H) shift ;;
    -X) method="$2"; shift ;;
    --jq) jq_expr="$2"; shift ;;
    --input) shift ;;
    --paginate) ;;
    -*) echo "stub gh: unsupported flag $1" >&2; exit 2 ;;
    *) path="$1" ;;
  esac
  shift
done
echo "$method $path" >> "$FAKE_GH_DIR/calls.log"
if [ "$method" != GET ]; then cat > "$FAKE_GH_DIR/body-$method.json"; echo '{}'; exit 0; fi
case "$path" in
  */rulesets) file="$FAKE_GH_DIR/list.json" ;;
  */rulesets/*) file="$FAKE_GH_DIR/ruleset-${path##*/}.json" ;;
  */branches) file="$FAKE_GH_DIR/branches.json" ;;
  *) echo "stub gh: no answer for $path" >&2; exit 1 ;;
esac
[ -f "$file" ] || { echo "stub gh: not found: $path" >&2; exit 1; }
if [ -n "$jq_expr" ]; then jq -r "$jq_expr" "$file"; else cat "$file"; fi
"""

MAIN_ID = 111
TAGS_ID = 222


def live_main(
    checks: list[str] | None = None, extra_rules=(), extra_bypass=(), pull_request=None
) -> dict:
    """The live 'Protect main' ruleset as the API returns it, with optional changes made to it."""
    ruleset = copy.deepcopy(EXPECTED_MAIN)
    ruleset["id"] = MAIN_ID
    ruleset["bypass_actors"].extend(extra_bypass)
    ruleset["rules"].extend(extra_rules)
    for rule in ruleset["rules"]:
        if rule["type"] == "required_status_checks" and checks is not None:
            rule["parameters"]["required_status_checks"] = [{"context": name} for name in checks]
        if rule["type"] == "pull_request":
            rule["parameters"].update(pull_request or {})
    return ruleset


def live_tags(extra_rules=(), include=("refs/tags/v*",), bypass_mode="always") -> dict:
    ruleset = copy.deepcopy(EXPECTED_TAGS)
    ruleset["id"] = TAGS_ID
    ruleset["conditions"]["ref_name"]["include"] = list(include)
    ruleset["bypass_actors"][0]["bypass_mode"] = bypass_mode
    ruleset["rules"].extend(extra_rules)
    return ruleset


class Run:
    def __init__(self, result: subprocess.CompletedProcess, work: Path):
        self.returncode = result.returncode
        self.output = result.stdout + result.stderr
        self.summary = (work / "summary.md").read_text(encoding="utf-8")
        calls = work / "calls.log"
        self.calls = calls.read_text(encoding="utf-8").splitlines() if calls.exists() else []

    @property
    def writes(self) -> list[str]:
        return [call for call in self.calls if not call.startswith("GET ")]

    def body(self, work: Path, method: str) -> dict:
        return json.loads((work / f"body-{method}.json").read_text(encoding="utf-8"))


def run_step(
    tmp_path: Path,
    task: str,
    *,
    apply: bool = False,
    allow_weakening: bool = False,
    live: list[dict] | None = None,
    required_checks: str | None = None,
    mutate: tuple[str, str] | None = None,
):
    """Run the real step body of 390 with a stub gh. ``live`` is the list of live rulesets."""
    work = tmp_path / "work"
    stubs = tmp_path / "bin"
    work.mkdir(parents=True)
    stubs.mkdir(parents=True)
    gh = stubs / "gh"
    gh.write_text(STUB_GH, encoding="utf-8", newline="\n")
    gh.chmod(gh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    live = live or []
    (work / "list.json").write_text(
        json.dumps([{k: r[k] for k in ("id", "name", "target", "enforcement")} for r in live]),
        encoding="utf-8",
    )
    for ruleset in live:
        (work / f"ruleset-{ruleset['id']}.json").write_text(json.dumps(ruleset), encoding="utf-8")
    (work / "branches.json").write_text(json.dumps([{"name": "main"}]), encoding="utf-8")
    (work / "summary.md").write_text("", encoding="utf-8")
    script = tmp_path / "step.sh"
    body = _step()["run"]
    if mutate:
        old, new = mutate
        assert body.count(old) == 1, f"the mutation target {old!r} is not in the step exactly once"
        body = body.replace(old, new)
    script.write_text(body, encoding="utf-8", newline="\n")
    env = {
        **os.environ,
        "PATH": f"{stubs.as_posix()}{os.pathsep}{os.environ['PATH']}",
        "FAKE_GH_DIR": work.as_posix(),
        "GITHUB_STEP_SUMMARY": (work / "summary.md").as_posix(),
        "GH_TOKEN": "stub",
        "REPO": "owner/repo",
        "DEFAULT_BRANCH": "main",
        "TASK": task,
        "APPLY": "true" if apply else "false",
        "ALLOW_WEAKENING": "true" if allow_weakening else "false",
        "REQUIRED_CHECKS": required_checks or _step()["env"]["REQUIRED_CHECKS"],
        "KEEP_REGEX": _step()["env"]["KEEP_REGEX"],
    }
    result = subprocess.run(
        [BASH, script.as_posix()], env=env, capture_output=True, text=True, timeout=60, check=False
    )
    return Run(result, work), work


@needs_tools
class TestProtectMainDoesNotDropLiveChecks:
    def test_a_dry_run_against_a_matching_live_ruleset_removes_nothing(self, tmp_path):
        run, _ = run_step(tmp_path, "protect-main", live=[live_main(), live_tags()])
        assert run.returncode == 0, run.output
        assert "The update removes and weakens nothing that is live." in run.summary
        assert "The update adds and changes nothing." in run.summary
        assert run.writes == []

    def test_the_stale_seven_check_list_is_reported_and_apply_refuses_it(self, tmp_path):
        """The incident: 7 names in the file, 11 live. The dry run says so; apply stops."""
        stale = json.dumps(STALE_REQUIRED_CHECKS)
        dry, _ = run_step(
            tmp_path / "dry", "protect-main", live=[live_main()], required_checks=stale
        )
        assert dry.returncode == 0, dry.output
        assert "would REMOVE or WEAKEN these" in dry.summary
        for name in EXPECTED_REQUIRED_CHECKS[7:]:
            assert f"- check: {name}" in dry.summary
        assert "Apply would be REFUSED" in dry.summary
        assert dry.writes == []

        applied, _ = run_step(
            tmp_path / "apply",
            "protect-main",
            apply=True,
            live=[live_main()],
            required_checks=stale,
        )
        assert applied.returncode != 0
        assert "REFUSED" in applied.summary
        assert "Nothing was changed." in applied.summary
        assert applied.writes == []

    def test_apply_with_allow_weakening_goes_ahead_and_says_so(self, tmp_path):
        stale = json.dumps(STALE_REQUIRED_CHECKS)
        run, work = run_step(
            tmp_path,
            "protect-main",
            apply=True,
            allow_weakening=True,
            live=[live_main()],
            required_checks=stale,
        )
        assert run.returncode == 0, run.output
        assert run.writes == [f"PUT repos/owner/repo/rulesets/{MAIN_ID}"]
        assert "allow_weakening is ticked" in run.summary
        sent = run.body(work, "PUT")["rules"][-1]["parameters"]["required_status_checks"]
        assert [c["context"] for c in sent] == STALE_REQUIRED_CHECKS

    def test_adding_checks_needs_no_allow_weakening(self, tmp_path):
        """The ordinary change: the live ruleset has 7, the file has 11; apply adds and removes nothing."""
        live = live_main(checks=STALE_REQUIRED_CHECKS)
        run, work = run_step(tmp_path, "protect-main", apply=True, live=[live])
        assert run.returncode == 0, run.output
        assert run.writes == [f"PUT repos/owner/repo/rulesets/{MAIN_ID}"]
        for name in EXPECTED_REQUIRED_CHECKS[7:]:
            assert f"- check: {name}" in run.summary
        assert "The update removes and weakens nothing that is live." in run.summary
        sent = run.body(work, "PUT")["rules"][-1]["parameters"]["required_status_checks"]
        assert [c["context"] for c in sent] == EXPECTED_REQUIRED_CHECKS

    def test_a_check_that_only_the_live_ruleset_has_blocks_apply(self, tmp_path):
        live = live_main(checks=[*EXPECTED_REQUIRED_CHECKS, "Added In The UI"])
        run, _ = run_step(tmp_path, "protect-main", apply=True, live=[live])
        assert run.returncode != 0
        assert "- check: Added In The UI" in run.summary
        assert run.writes == []

    def test_a_rule_or_bypass_actor_only_the_live_ruleset_has_blocks_apply(self, tmp_path):
        signed = live_main(extra_rules=[{"type": "required_signatures"}])
        run, _ = run_step(tmp_path / "rule", "protect-main", apply=True, live=[signed])
        assert run.returncode != 0
        assert "- rule: required_signatures" in run.summary
        assert run.writes == []

        bypass = live_main(
            extra_bypass=[
                {"actor_id": 1, "actor_type": "OrganizationAdmin", "bypass_mode": "always"}
            ]
        )
        run, _ = run_step(tmp_path / "bypass", "protect-main", apply=True, live=[bypass])
        assert run.returncode != 0
        assert "- bypass: OrganizationAdmin 1 (always)" in run.summary
        assert run.writes == []

    def test_with_no_live_ruleset_apply_creates_it(self, tmp_path):
        run, work = run_step(tmp_path, "protect-main", apply=True, live=[])
        assert run.returncode == 0, run.output
        assert run.writes == ["POST repos/owner/repo/rulesets"]
        sent = run.body(work, "POST")["rules"][-1]["parameters"]["required_status_checks"]
        assert [c["context"] for c in sent] == EXPECTED_REQUIRED_CHECKS

    @pytest.mark.parametrize(
        "bad",
        ["[]", "{}", '["a","a"]', '["a",""]', "[1]", "not json"],
    )
    def test_a_malformed_required_checks_value_stops_before_any_write(self, tmp_path, bad):
        run, _ = run_step(
            tmp_path,
            "protect-main",
            apply=True,
            allow_weakening=True,
            live=[live_main()],
            required_checks=bad,
        )
        assert run.returncode != 0
        assert run.writes == []


@needs_tools
class TestProtectReleaseTagsDoesNotDropLiveSettings:
    def test_a_matching_live_ruleset_is_updated_without_removing_anything(self, tmp_path):
        run, _ = run_step(tmp_path, "protect-release-tags", apply=True, live=[live_tags()])
        assert run.returncode == 0, run.output
        assert run.writes == [f"PUT repos/owner/repo/rulesets/{TAGS_ID}"]
        assert "The update removes and weakens nothing that is live." in run.summary

    def test_a_pattern_only_the_live_ruleset_has_blocks_apply(self, tmp_path):
        """The engine-v* tags (TODO.md T-730) get added to the live ruleset by hand: apply must not undo it."""
        live = live_tags(include=("refs/tags/v*", "refs/tags/engine-v*"))
        dry, _ = run_step(tmp_path / "dry", "protect-release-tags", live=[live])
        assert dry.returncode == 0, dry.output
        assert "- include: refs/tags/engine-v*" in dry.summary
        assert "Apply would be REFUSED" in dry.summary
        applied, _ = run_step(tmp_path / "apply", "protect-release-tags", apply=True, live=[live])
        assert applied.returncode != 0
        assert applied.writes == []
        allowed, _ = run_step(
            tmp_path / "allowed",
            "protect-release-tags",
            apply=True,
            allow_weakening=True,
            live=[live],
        )
        assert allowed.returncode == 0, allowed.output
        assert allowed.writes == [f"PUT repos/owner/repo/rulesets/{TAGS_ID}"]

    def test_a_rule_only_the_live_ruleset_has_blocks_apply(self, tmp_path):
        run, _ = run_step(
            tmp_path,
            "protect-release-tags",
            apply=True,
            live=[live_tags(extra_rules=[{"type": "required_signatures"}])],
        )
        assert run.returncode != 0
        assert "- rule: required_signatures" in run.summary
        assert run.writes == []


@needs_tools
def test_show_plan_prints_what_each_task_would_remove_and_writes_nothing(tmp_path):
    live = [live_main(checks=[*EXPECTED_REQUIRED_CHECKS, "Added In The UI"]), live_tags()]
    run, _ = run_step(tmp_path, "show-plan", apply=True, live=live)
    assert run.returncode == 0, run.output
    assert "What protect-main would change in the live ruleset:" in run.summary
    assert "- check: Added In The UI" in run.summary
    assert "What protect-release-tags would change in the live ruleset:" in run.summary
    assert run.writes == []


# --- the payloads are the live policy, and every weakening of it is refused ---


def _payload_sent(tmp_path: Path, task: str, **kwargs) -> dict:
    """The ruleset the task would create: run it against an empty repository and read the POST body."""
    run, work = run_step(tmp_path, task, apply=True, live=[], **kwargs)
    assert run.returncode == 0, run.output
    return run.body(work, "POST")


@needs_tools
def test_the_protect_main_payload_is_the_live_policy(tmp_path) -> None:
    assert _payload_sent(tmp_path, "protect-main") == EXPECTED_MAIN


@needs_tools
def test_the_protect_release_tags_payload_is_the_live_policy(tmp_path) -> None:
    assert _payload_sent(tmp_path, "protect-release-tags") == EXPECTED_TAGS


@needs_tools
@pytest.mark.parametrize(
    "task, live", [("protect-main", live_main), ("protect-release-tags", live_tags)]
)
def test_applying_to_the_live_rulesets_as_they_are_changes_nothing(tmp_path, task, live) -> None:
    run, _ = run_step(tmp_path, task, apply=True, live=[live()])
    assert run.returncode == 0, run.output
    assert "The update removes and weakens nothing that is live." in run.summary
    assert "The update adds and changes nothing." in run.summary


# Each mutation edits ONE setting of the payload builder so that it is weaker than the live ruleset. Apply must
# refuse it and send nothing; with allow_weakening it goes ahead. `old` is asserted to occur exactly once.
# (label: (text in the step, replacement, line the summary must show))
MAIN_MUTATIONS = {
    "approvals lowered": (
        "required_approving_review_count: 1,",
        "required_approving_review_count: 0,",
        "param: pull_request.required_approving_review_count: live 1, payload 0",
    ),
    "stale reviews no longer dismissed": (
        "dismiss_stale_reviews_on_push: true,",
        "dismiss_stale_reviews_on_push: false,",
        "param: pull_request.dismiss_stale_reviews_on_push: live true, payload false",
    ),
    "code owner review off": (
        "require_code_owner_review: true,",
        "require_code_owner_review: false,",
        "param: pull_request.require_code_owner_review: live true, payload false",
    ),
    "last push approval off": (
        "require_last_push_approval: true,",
        "require_last_push_approval: false,",
        "param: pull_request.require_last_push_approval: live true, payload false",
    ),
    "thread resolution off": (
        "required_review_thread_resolution: true,",
        "required_review_thread_resolution: false,",
        "param: pull_request.required_review_thread_resolution: live true, payload false",
    ),
    "extra approval for unattributed changes off": (
        "require_extra_approval_for_unattributed_changes: true,",
        "require_extra_approval_for_unattributed_changes: false,",
        "param: pull_request.require_extra_approval_for_unattributed_changes: live true, payload false",
    ),
    "a merge method dropped": (
        'allowed_merge_methods: ["merge", "squash", "rebase"]',
        'allowed_merge_methods: ["merge", "squash"]',
        "param: pull_request.allowed_merge_methods",
    ),
    "checks no longer enforced on create": (
        "do_not_enforce_on_create: false,",
        "do_not_enforce_on_create: true,",
        "param: required_status_checks.do_not_enforce_on_create",
    ),
    "the deletion rule dropped": (
        '      { type: "deletion" },\n',
        "",
        "- rule: deletion",
    ),
    "the bypass actor dropped": (
        'bypass_actors: [ { actor_id: 5, actor_type: "RepositoryRole", bypass_mode: "pull_request" } ],',
        "bypass_actors: [],",
        "- bypass: RepositoryRole 5 (pull_request)",
    ),
    "a different branch protected": (
        'include: ["~DEFAULT_BRANCH"]',
        'include: ["refs/heads/other"]',
        "- include: ~DEFAULT_BRANCH",
    ),
}
TAGS_MUTATIONS = {
    "the creation rule dropped": (
        '{ type: "update" }, { type: "creation" } ]',
        '{ type: "update" } ]',
        "- rule: creation",
    ),
    "the update rule dropped": (
        '{ type: "update" }, { type: "creation" } ]',
        '{ type: "creation" } ]',
        "- rule: update",
    ),
    "the bypass actor dropped": (
        'bypass_actors: [ { actor_id: 5, actor_type: "RepositoryRole", bypass_mode: "always" } ],',
        "bypass_actors: [],",
        "- bypass: RepositoryRole 5 (always)",
    ),
    "the bypass narrowed": (
        'bypass_mode: "always" } ],',
        'bypass_mode: "pull_request" } ],',
        "- bypass: RepositoryRole 5 (always)",
    ),
    "the tag pattern narrowed": (
        'include: ["refs/tags/v*"]',
        'include: ["refs/tags/v1*"]',
        "- include: refs/tags/v*",
    ),
}


def _mutation_cases(table, task, live):
    return [pytest.param(task, live, *spec, id=f"{task}: {label}") for label, spec in table.items()]


@needs_tools
@pytest.mark.parametrize(
    "task, live, old, new, expected_line",
    _mutation_cases(MAIN_MUTATIONS, "protect-main", live_main)
    + _mutation_cases(TAGS_MUTATIONS, "protect-release-tags", live_tags),
)
def test_a_payload_weaker_than_the_live_ruleset_is_refused_unless_allowed(
    tmp_path, task, live, old, new, expected_line
) -> None:
    refused, _ = run_step(tmp_path / "refused", task, apply=True, live=[live()], mutate=(old, new))
    assert refused.returncode != 0, refused.output
    assert "REFUSED" in refused.summary
    assert expected_line in refused.summary
    assert refused.writes == []

    dry, _ = run_step(tmp_path / "dry", task, live=[live()], mutate=(old, new))
    assert dry.returncode == 0, dry.output
    assert "Apply would be REFUSED" in dry.summary
    assert dry.writes == []

    allowed, _ = run_step(
        tmp_path / "allowed",
        task,
        apply=True,
        allow_weakening=True,
        live=[live()],
        mutate=(old, new),
    )
    assert allowed.returncode == 0, allowed.output
    assert "allow_weakening is ticked" in allowed.summary
    assert len(allowed.writes) == 1 and allowed.writes[0].startswith("PUT ")


@needs_tools
def test_a_payload_that_only_strengthens_the_live_ruleset_needs_no_allowance(tmp_path) -> None:
    """Live has 0 approvals and no code-owner review; the payload (1, on) raises both. Nothing is weakened."""
    live = live_main(
        pull_request={"required_approving_review_count": 0, "require_code_owner_review": False}
    )
    run, _ = run_step(tmp_path, "protect-main", apply=True, live=[live])
    assert run.returncode == 0, run.output
    assert run.writes == [f"PUT repos/owner/repo/rulesets/{MAIN_ID}"]
    assert "param: pull_request.required_approving_review_count: live 0 -> payload 1" in run.summary
    assert (
        "param: pull_request.require_code_owner_review: live false -> payload true" in run.summary
    )
    assert "The update removes and weakens nothing that is live." in run.summary


@needs_tools
def test_a_live_ruleset_stricter_than_the_payload_blocks_apply(tmp_path) -> None:
    """Someone raised the live approvals to 2 by hand: the payload's 1 would lower it."""
    live = live_main(pull_request={"required_approving_review_count": 2})
    run, _ = run_step(tmp_path, "protect-main", apply=True, live=[live])
    assert run.returncode != 0
    assert "param: pull_request.required_approving_review_count: live 2, payload 1" in run.summary
    assert run.writes == []
