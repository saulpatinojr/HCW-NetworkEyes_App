# Review task: dead & stale/old code sweep

Gate for issue #110 — required before that issue is considered done.

## Copy/paste prompt

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

## Checklist

- [ ] Dead code swept (cna/**)
- [ ] Dead code swept (apps/cna-web/**)
- [ ] Dead code swept (infra/**)
- [ ] Stale comments/TODOs cleaned up
- [ ] Findings summarized in PR description
