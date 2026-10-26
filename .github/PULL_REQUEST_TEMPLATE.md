## Summary

<!-- Say in plain words what changes and why, before the detail. Write for someone who has not followed earlier work. -->

## Related issue or decision

<!-- Use a closing keyword (Closes #123) only when this pull request completes the issue. Link TODO.md / REVIEW.md ids too. -->

Closes #

## Type of change

- [ ] Feature or behaviour change
- [ ] Bug fix
- [ ] Refactor or performance
- [ ] Documentation or process
- [ ] Dependency update
- [ ] CI/CD or repository policy
- [ ] Container image or build
- [ ] Security or privacy
- [ ] Breaking change

## Scope and impact

<!-- Components, APIs, data and migrations, permissions, rollout, compatibility and rollback. Say "None" where a line does not apply. -->

## Verification

<!-- Exact commands, and what each result proves. Say which checks you did not run and why. -->

- Checks run:
- Important result or evidence:
- Checks not run and why:
- Evidence level: [ ] Static [ ] Local [ ] CI [ ] Live (name the environment)

## Image contract (delete this section if the change does not touch it)

- [ ] The image tag scheme, the signing identity and the runtime environment settings are unchanged, or the change is recorded under `Changed` in `CHANGELOG.md` and in `TODO.md`.
- [ ] `.env.example` lists every setting the code reads.
- [ ] If the change reaches the lab build (engine package, rules, an `engine-v*` release), an entry was added to `docs/whats-new-upstream.md` in `HCW-NetworkEyes_AddOn`, or this description says why none is needed.

## CI, containers and dependencies

- [ ] Every new GitHub Action is pinned to a full commit SHA with its version in a comment, and tools and images are pinned by digest.
- [ ] No job in `300-test-codebase.yml` was renamed (the names are required checks). New job names are listed here so the owner can add them to the ruleset:
- [ ] `pyproject.toml` changes come with a regenerated `uv.lock` (`uv lock`).
- [ ] Dockerfile changes pass `scripts/ci/local-container-checks.sh hadolint`, and any new ignored rule has its reason in `.hadolint.yaml`.
- [ ] No new markdown file outside the documentation model (`scripts/validate_documentation_model.py` passes).

## Security and data

- [ ] No credentials, private keys, tokens, connection strings, personal data, customer data or real tenant identifiers were added.
- [ ] Authorization, least privilege and denial paths are tested where they apply.
- [ ] Logs and telemetry carry identifiers, not payloads, paths or secrets.
- [ ] New permissions, dependencies, base images and trust boundaries are called out above.

## Documentation and follow-up

- [ ] `CHANGELOG.md` records the change; unrelated findings went to `TODO.md` or `REVIEW.md`.
- [ ] Rollback is described when the change affects a shared environment or a published image.
- [ ] Required reviewers, approvals and checks are complete or called out here.
