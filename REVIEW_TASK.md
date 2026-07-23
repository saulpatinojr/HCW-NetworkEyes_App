# Review tasks — gate for issue #110

Both tasks below are required before issue #110 is considered done.

## Task 1: Python code review

### Copy/paste prompt

```
Do a Python code review of this repository (saulpatinojr/Work-Cloud_Network_Assessment), scoped
to the `cna/` package (CLI, discovery, deployment, diagram engine, modules). Use the
`python-engineer` agent — this repo already standardizes on uv + ruff + pyproject-first layout
(see pyproject.toml: ruff select = E,W,F,I,B,C4,UP,S,N; py311 target).

Focus on:
- `ruff check` and `ruff format --check` clean (fix or justify every violation, do not just
  widen the ignore list)
- Type coverage / correctness for new or recently-touched modules (this repo is mid-migration
  toward stricter typing — check whether `ty` is wired in and run it if so)
- boto3 / azure-mgmt-* client usage: correct session/credential handling, no hardcoded
  region/account values, consistent error handling and retry (tenacity) usage between the AWS
  and Azure discovery paths
- Test coverage gaps versus `[tool.coverage.report] fail_under = 80` in pyproject.toml
- Consistency between the Azure discovery/deploy modules and any new AWS discovery/deploy
  modules added as part of the #110 AWS integration work — they should follow the same
  structure and error-handling conventions

Do not change behavior silently — if a fix changes semantics, call it out explicitly in the PR
description. Commit fixes on this branch (review/python-code-review). When done, mark this
file's checklist below and summarize findings in the PR description.
```

### Checklist

- [x] `ruff check` clean — `ruff 0.15.21 check cna/` = "All checks passed" (baseline already clean; no ignores widened)
- [x] `ruff format --check` clean — all 109 files already formatted
- [x] Type checking pass (if `ty`/mypy configured) — N/A: neither `ty` nor mypy is wired in (not in dev deps, no `[tool.ty]`/`[tool.mypy]`). A meaningful run isn't possible in this env (managed Python execution-blocked, no deps installed). Recommendation in PR: add `ty` to dev deps + pre-commit.
- [x] boto3/azure-mgmt-* usage reviewed for consistency — found + fixed a runtime-breaking `with_retry` contract bug in AWS discovery; remaining consistency gaps flagged in PR
- [x] Coverage gaps reviewed against 80% threshold — discovery orchestrators (`run()` paths) are the least-tested/highest-risk; detailed in PR
- [x] Findings summarized in PR description

## Task 2: Dead & stale/old code sweep

### Copy/paste prompt

```
Review this repository (saulpatinojr/Work-Cloud_Network_Assessment) for dead code and stale/old
code. Use the `simplify` skill for reuse/simplification/efficiency cleanups, and the
`code-review` skill for a structured pass. Focus on:

- Unused functions, classes, modules, and exports (cna/**, apps/cna-web/**, infra/**)
- Commented-out code blocks left behind from prior refactors
- Superseded implementations now that AWS scaffolding replaced PR #129's approach (check for
  any leftover references to the old copilot/aws-integration-terraform-modules branch content)
- Stale TODO/FIXME comments referencing already-closed issues (#129, #130-#138)
- Unreferenced Terraform modules/variables under infra/terraform/providers/**
- Orphaned test fixtures or fixtures for removed code paths

Do not remove anything you're not confident is dead — flag uncertain cases in the PR description
instead of deleting. Open findings and fixes as commits on this PR (review/dead-and-stale-code).
When done, mark this file's checklist below and update the PR description with a summary.
```

### Checklist

- [x] Dead code swept (cna/**) — surveyed; findings are wiring-gap/scaffold, flagged in PR (no confident deletions)
- [x] Dead code swept (apps/cna-web/**) — 4 verified-dead removals committed (221 lines)
- [x] Dead code swept (infra/**) — surveyed; AWS modules are intentional #110 scaffold, flagged
- [x] Stale comments/TODOs cleaned up — none reference closed issues; Phase/SCAFFOLD markers are intentional
- [x] Findings summarized in PR description
