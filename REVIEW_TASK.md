# Review task: Python code review

Gate for issue #110 — required before that issue is considered done.

## Copy/paste prompt

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

## Checklist

- [x] `ruff check` clean — `ruff 0.15.21 check cna/` = "All checks passed" (baseline already clean; no ignores widened)
- [x] `ruff format --check` clean — all 109 files already formatted
- [x] Type checking pass (if `ty`/mypy configured) — N/A: neither `ty` nor mypy is wired in (not in dev deps, no `[tool.ty]`/`[tool.mypy]`). A meaningful run isn't possible in this env (managed Python execution-blocked, no deps installed). Recommendation in PR: add `ty` to dev deps + pre-commit.
- [x] boto3/azure-mgmt-* usage reviewed for consistency — found + fixed a runtime-breaking `with_retry` contract bug in AWS discovery; remaining consistency gaps flagged in PR
- [x] Coverage gaps reviewed against 80% threshold — discovery orchestrators (`run()` paths) are the least-tested/highest-risk; detailed in PR
- [x] Findings summarized in PR description
