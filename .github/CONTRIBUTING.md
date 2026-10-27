# Contributing

Thank you for helping. This guide says how a change gets from your machine into `main`. It is short on purpose:
`CLAUDE.md` holds the rules an AI coding agent must follow (agents and people share the same ones), `README.md` is the
overview, and `TODO.md` is the work queue.

## Before you start

- Search the existing issues and pull requests first.
- For anything bigger than a small fix, open an issue (use a form from the **New issue** page) so the outcome and the
  acceptance criteria are agreed before you write code.
- Never put credentials, tokens, private keys, connection strings, personal data, data from a real environment, tenant or subscription
  identifiers, or real network topology in code, tests, fixtures, logs, issues or pull requests.
- A vulnerability is not an issue. Report it privately as `.github/SECURITY.md` describes.
- By taking part you agree to the `.github/CODE_OF_CONDUCT.md`.

## What lives where

- **Product code:** `apps/cna-web` (Next.js), `apps/cna-api` and `apps/cna-worker` (Python), the `cna` package, and
  `packages/cna-azure-network-engine`. Deployment is not done here: this repository only builds and publishes the
  images. A change to the image tags, the signing identity or
  the runtime environment settings changes what consumers rely on; `CLAUDE.md` explains how to record it.
- **Documents:** the repository keeps `README.md`, `CHANGELOG.md`, `REVIEW.md` and `TODO.md` (plus `CLAUDE.md`, and two
  temporary working documents). `scripts/validate_documentation_model.py` fails the build on any other markdown file.
  Long-form documentation has no destination since the GitHub Wiki was deleted (`REVIEW.md`, R-031). The only other
  markdown is the community files GitHub itself reads from `.github/` (this guide, the security policy, the code of
  conduct, the pull request template and the issue forms).
- **Workflows:** `.github/workflows/` holds only the numbered workflows `200`, `300`, `310`, `320`, `370` and `390`.
  Add a job to an existing workflow rather than a new file. Never rename a job in `300-test-codebase.yml`: the job
  names are the required checks of the `main` ruleset.

## Set up and check your change

Python 3.14 and [uv](https://docs.astral.sh/uv/) are needed. From the repository root:

```bash
uv sync --frozen --all-packages
uv run --frozen --extra dev ruff check .
uv run --frozen --extra dev ruff format --check .
uv run --frozen --extra dev pytest tests/unit tests/security tests/packaging packages/cna-azure-network-engine/tests -q -p no:cacheprovider
python scripts/validate_documentation_model.py
```

For the web app (`apps/cna-web`, Node 24):

```bash
cd apps/cna-web
npm ci
npm run lint && npm run typecheck && npm test
```

Containers and workflows are checked with pinned tools that run in Docker, so nothing has to be installed. With Docker
running (on Windows, Docker Desktop with the `desktop-linux` context):

```bash
bash scripts/ci/local-container-checks.sh all
```

That runs hadolint (Dockerfiles), actionlint (workflows) and two Trivy scans (configuration and dependencies). The
script header explains the options and where the tool versions come from. CI runs the hadolint and actionlint parts
as the jobs `Dockerfile Lint (hadolint)` and `Workflow Lint (actionlint)`.

To scan an image you built (for example `docker build --target migrator -t cna:migrator apps/cna-web`), run
`bash scripts/ci/local-container-checks.sh trivy-image cna:migrator`. CI builds and scans the web `migrator` and `runner`
images in every pull request as the job `Image Scan (Trivy)`; `.trivyignore.yaml` lists the one suppression, with its reason.

## Rules that are easy to get wrong

- **Dependencies are locked.** After you change `pyproject.toml`, run `uv lock` and commit `uv.lock` with it. Never
  edit `uv.lock` by hand and never add a bare `pip install` to a Dockerfile.
- **Pin what runs in CI.** Every GitHub Action is pinned to a full commit SHA with the version in a comment; images and
  tools are pinned by digest. Look the SHA up (for example with `gh api repos/OWNER/REPO/git/ref/tags/TAG`), do not copy
  it from memory.
- **Dockerfiles:** base images are pinned by digest, `USER` is numeric, `CMD`, `ENTRYPOINT` and `HEALTHCHECK` use the
  exec (JSON array) form, and a `RUN` with a pipe sets `pipefail`. `.hadolint.yaml` lists the only rules that are ignored
  and the reason for each; do not add to it without a reason in the same change.
- **Secrets:** `detect-secrets` fails the build on any new finding that is not in `.secrets.baseline`. If you move a line
  that has an audited entry, update that entry's `line_number` by hand.
- **Never hard-code a value at a call site.** Declare it as a setting or a constant and resolve it at runtime.

## Pull requests

- Branch from the current `main` and keep each pull request to one purpose.
- Use short, plain commit subjects in the style of the history, for example `ci(registry): ...`, `fix(ci): ...`,
  `build(deps): ...`.
- Fill in the pull request template. State the commands you ran and what each result proves, say what you did not run
  and why, and say whether the evidence is static, local, from CI, or from a live environment.
- Add or update tests for changed behaviour, including the failure and denial paths. A test that cannot fail proves
  nothing.
- Update `CHANGELOG.md` for what changed. Record unrelated findings in `TODO.md` (engineering work) or `REVIEW.md`
  (needs a human decision) instead of widening the pull request.
- Do not merge while a required check, a review or a security finding is open. Do not push straight to `main`.
