# CLAUDE.md — HCW NetworkEyes App (Cloud Network Assessment)

Instructions for AI coding agents working in this repository. `README.md` is the
human intro page; this file states the rules an agent must not infer wrongly.

## What this repository is

This repository, `saulpatinojr/HCW-NetworkEyes_App`, is the **product** of the Cloud Network
Assessment (CNA) platform and the NetworkEyes App of the HCW App-to-AddOn initiative: the single
source of application code — `apps/cna-web`, `apps/cna-api`, `apps/cna-worker`,
and the `cna` Python package — and the pipeline that builds and publishes their
container images (`200-build-images.yml` → Docker Hub `<namespace>/img-ne-appliance-app`).

Customers consume an appliance, not this repository. History: this repository was the
original `Work-Cloud_Network_Assessment`; on 2026-09-18 it was retired in favour of
`Work-Cloud_Network_Core`, and on 2026-10-10 the owner reversed that: the Core lineage was merged
back here and this repository is the implementation target of `REFACTOR_APP.md` (the HCW
App-to-AddOn plan; its lab edition is `saulpatinojr/HCW-NetworkEyes_AddOn`). **The Core is reference only: nothing
for this repository is written there (owner, 2026-10-11)**; its wiki pages move here (`REVIEW.md` → R-023). Issue and
pull-request numbers in the documents older than that date name threads of the original
repository or of the Core.

Deployment is not this repository's job. Each cloud has its own customer-facing
**appliance repository** that deploys and operates these images:

- Azure: <https://github.com/saulpatinojr/Work-Cloud_Network_Azure_Appliance>
- AWS: <https://github.com/saulpatinojr/Work-Cloud_Network_AWS_Appliance>

The appliances contain only their cloud's Terraform and deploy/update workflows.
They are structurally identical to each other; a feature lands **once, here**, in
the images, and both appliances pick it up. There is no Terraform and no deploy
workflow in this repository; it keeps only `200-build-images`,
`300-test-codebase`, `310-release-version`, `320-release-engine` and `370-registry-cleanup`, plus one
owner-approved exception, `390-repository-admin` (manual, dry-run by default,
approved per run; it deploys nothing and holds no product code). A
deployment fix belongs in the appliance (and its sibling), never here.

## The core ↔ appliance contract

Changing any of the following changes both appliances. Mirror the change into
**both** appliance repositories in the same change set (link the sibling PRs),
or record a `TODO.md` item naming them — never leave one side implied.

1. **Image repository and tag scheme** on Docker Hub: every image is published to the one
   repository `<namespace>/img-ne-appliance-app` (owner convention
   `img-<short name>-<job>-<type>`; the retired `cna` repository holds a different image and is
   never used). The name is written once per layer — `IMAGE_REPOSITORY` in the workflow-level
   `env` of `200-build-images.yml`, `310-release-version.yml` and `370-registry-cleanup.yml`, and
   the `IMAGE_REPOSITORY` environment variable `scripts/ci/sign_image.sh` reads — and
   `tests/security/test_image_repository_name.py` fails if any workflow, script or contract
   names another repository. Tags inside it: `img-ne-appliance-app:{api,worker,web,migrator}-sha-<7>`
   immutable tags plus floating `*-latest`; the CLI image is `img-ne-appliance-app:sha-<7>` /
   `img-ne-appliance-app:latest`.
2. **`.deployment-catalog/latest-build.json`** — fields `sha_tag`, `commit`,
   `built_at`, `run_id`, `images{cli,api,worker,web,migrator}` (immutable tags)
   and `digests{cli,api,worker,web,migrator}` (`docker.io/<ns>/img-ne-appliance-app@sha256:<64>`).
   Written by `200-build-images.yml` after every image passed the vulnerability
   gate and landed on `main` through a self-merging pull request (branch
   `build/latest-manifest`, opened with the GitHub App token because `main` is
   protected, via `.github/actions/self-merging-pr`; the job fails, and the
   dispatch below is skipped, if the manifest does not merge within 30 minutes);
   read by the appliances' image-update workflow, which
   deploys the combined form `docker.io/<ns>/img-ne-appliance-app:<role>-sha-<7>@sha256:<64>` —
   tag for people and for the web tier's image-update check, digest as the
   authoritative pull. Floating `*-latest` tags are never deployed.
3. **`repository_dispatch` event `cna-image-published`** with the manifest as
   `client_payload`, sent by `200-build-images.yml` to every repository listed in
   the `APPLIANCE_REPOS` variable (comma-separated names) under the account in the
   `APPLIANCE_OWNER` variable (required whenever `APPLIANCE_REPOS` is set: the appliances live
   under `saulpatino-cbts`, not under this repository's owner; the job fails with a message
   if it is missing, and a moved repository, which answers a redirect, is a warning). It is
   a fast path only — the appliances also poll the manifest, so a failed dispatch
   is a warning, never a failed build.
4. **Runtime environment contract** the images read, injected by the appliances'
   Terraform: `CNA_AI_MODE` (`saas` | `byo-api`), `CNA_APPLIANCE_CLOUD`
   (`azure` | `aws`), `CNA_AI_ENGINE_DEFAULT`, the SaaS engine variables
   (`AZURE_OPENAI_*` on Azure, `CNA_BEDROCK_*` on AWS), and
   `CREDENTIAL_ENCRYPTION_KEY` (web always; api in `byo-api`), and the image-update
   check inputs the web tier reads (`CNA_WEB_IMAGE`, `CNA_IMAGE_REGISTRY_USERNAME`,
   `CNA_IMAGE_REGISTRY_TOKEN`, `CNA_APPLIANCE_REPO`, optional
   `CNA_IMAGE_UPDATE_CHECK_INTERVAL_MINUTES`). `CNA_BUILD_SHA` is baked into every
   image by `200-build-images.yml`, never injected. The authoritative inventory is
   `.env.example`.
5. **Image signatures and provenance.** `200-build-images.yml` signs every
   published digest with cosign, keyless, under its own OIDC identity
   `https://github.com/<owner>/<this repo>/.github/workflows/200-build-images.yml@refs/heads/main`
   (issuer `https://token.actions.githubusercontent.com`), and attaches
   BuildKit's SLSA v0.2 provenance as a cosign attestation (type
   `slsaprovenance02`, `predicate.builder.id` = the run URL). Both appliances
   verify all three — signature, attestation, builder — before any deploy
   (`210`, `220`) against their `IMAGE_SIGNING_IDENTITY` variable. Renaming or
   moving this repository, this workflow file, or its default branch changes
   the identity and breaks every appliance until that variable is updated; the
   cosign release (`COSIGN_VERSION`) is pinned identically in all three.

## AI engine rules

- Engine ids are `azure-openai`, `bedrock`, `anthropic`, `openai`. The selection
  rules live in `apps/cna-web/lib/ai-engine-rules.ts` and
  `cna/ai_engine/chat_agent.py` and are pinned by **one shared vector table**
  (`ai-engine-rules.test.ts`, `tests/unit/test_chat_agent.py`). Change both
  files and both tests together.
- `saas` mode uses the cloud-native engine for the appliance's cloud. `byo-api`
  mode uses admin-entered Anthropic/OpenAI keys. Those keys are the **only**
  secrets entered in the app UI; they are AES-256-GCM encrypted
  (`apps/cna-web/lib/crypto.ts` ↔ `cna/core/credential_crypto.py`, kept
  byte-compatible by a Node-generated test vector) and stored as `AppSetting`
  rows `ai.byo.<provider>.{apiKey,keyHint,model}`. Never log, return, or
  persist a decrypted key anywhere else; never accept one through env,
  Terraform, or a workflow input.
- Model ids are settings/variables with code defaults, never inline literals at
  call sites. Verify current ids before changing a default.

## Repository conventions that agents get wrong

- **Documents:** `README.md`, `CHANGELOG.md`, `REVIEW.md`, `TODO.md`, and this
  `CLAUDE.md` are the only markdown files (plus at most one temporary
  release-push document, and the community files GitHub reads from `.github/`:
  `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `PULL_REQUEST_TEMPLATE.md` and `ISSUE_TEMPLATE/`; never at the root).
  `scripts/validate_documentation_model.py` enforces
  this in CI. Long-form docs go to the GitHub Wiki. Content determines
  destination, not filename.
- **Never hardcode a value at a call site.** Declare it (`DiscoveryOptions`
  field, module-level constant, setting) and resolve at runtime.
- **Python dependencies are locked.** `uv.lock` is the resolution every Python
  image installs (`uv export --locked` + `--require-hashes`); after editing a
  dependency, extra or dependency group in `pyproject.toml`, run `uv lock` and
  commit both files — `300-test-codebase` fails on drift. Never edit `uv.lock`
  by hand, never add a package to a Dockerfile with a bare `pip install`, and
  never re-add `apt-get upgrade` / `apk upgrade` to a final stage: a Docker Scout
  finding on a base-image package is fixed by Dependabot's digest bump. The uv
  version is pinned in the `FROM ghcr.io/astral-sh/uv:… AS uv` stage of each
  Python Dockerfile and the `uv==` steps of `300-test-codebase.yml`; when
  Dependabot bumps the stage, move the workflow pins with it.
- **TypeScript runs side by side in `apps/cna-web`.** `typescript` is the alias `npm:@typescript/typescript6` (the
  TypeScript 6 API that eslint, typescript-eslint and Next.js import) and `@typescript/native` is `npm:typescript@^7`
  (the `tsc` that `npm run typecheck` runs). Never change `typescript` to a plain 7.x: TypeScript 7 has no
  programmatic API until 7.1 and typescript-eslint cannot load against it (Dependabot #209). Dependabot does not track
  either alias, so no ignore rule exists; `lib/typescript-toolchain.test.ts` fails first if the pairing breaks, and the
  same file fails when the typescript-eslint in the lockfile starts accepting TypeScript 7.1, and the non-blocking
  `typescript-canary` job in `300-test-codebase.yml` warns when the newest one on the registry does (and shows how the
  newest TypeScript behaves). Both are cues to finish `TODO.md` T-731 (issue 291), not guarantees.
  `@tanstack/react-table` is on version 9 (`useTable` and `tableFeatures`, not `useReactTable`); do not use its
  deprecated `/legacy` entry point.
- **Workflows are numbered in bands** (`000` bootstrap, `100` validation, `200`
  build/deploy, `300` test/release/ops). Numbers are stable across core and
  both appliances; never renumber, reference by filename. The core owns `200`,
  `300`, `310`, `320`, `370` and the one exception `390`; every other number belongs to
  the appliances.
- **Job names in `300-test-codebase.yml` are required checks.** The `Protect main` ruleset matches them by name. Add a job, never rename one; list
  new job names in the pull request so the owner can add them to the ruleset. Dockerfiles must pass hadolint (`.hadolint.yaml` lists the only
  ignored rules, each with a written reason) and workflows must pass actionlint; run both with
  `bash scripts/ci/local-container-checks.sh hadolint actionlint`.
  The `migrator` image runs only the Prisma CLI, so its `node_modules` comes from the `migrator-deps` stage of `apps/cna-web/Dockerfile` (cut out
  of `package-lock.json` by `apps/cna-web/scripts/migrator-lockfile.mjs`); never copy the builder's `node_modules` into it. The job `Image Scan (Trivy)`
  checks that in the built image and scans the migrator and web runner for fixable HIGH and CRITICAL findings (`.trivyignore.yaml` holds the one
  narrow suppression, with its reason); `bash scripts/ci/local-container-checks.sh trivy-image <image>` runs the same scan locally.
- **Every GitHub Action is pinned to a SHA digest.** `detect-secrets` fails the
  build on any finding not in `.secrets.baseline`; `gitleaks` is advisory.
- **Secrets** travel as GitHub secrets → OIDC / Key Vault / Secrets Manager →
  container secrets (injected by the appliances' Terraform). Never on a command
  line, never in a `workflow_dispatch` input, never committed.
- **Vendored agent configuration** (`.claude/`, `.agents/`, `.codex/`, `.kiro/`) is kept out of
  version control under `local/agent-config/` (gitignored, TODO T-411); it is not project
  source and must never contain project-specific facts.
- **`REFACTOR_APP.md`** at the root is the owner-approved refactoring plan this repository
  executes; the documentation model allows it (and the temporary `CNA-0.90-updates.md`) beside the four
  documents and this file, seven root documents at most, until their work has shipped.
- **Tell the lab edition what changed.** `saulpatinojr/HCW-NetworkEyes_AddOn` keeps a "what's new"
  file, `docs/whats-new-upstream.md`, that its agents read before changing anything. When a change lands
  here that reaches it (the engine package `packages/cna-azure-network-engine`, the rules, an
  `engine-v*` release, or anything it ports or pins), add an entry to that file in the same change set,
  or say in the pull request why none is needed.
- Start with `TODO.md` when picking up work; check `REVIEW.md` when blocked on a
  human decision.

## How to communicate with the owner

The owner is not a specialist in every tool used here. Write for a junior administrator with limited experience and no
memory of earlier sessions.

- **Be conversational and human.** Plain, friendly sentences. Say what happened and why it matters before the detail.
- **Assume little context.** Do not rely on repository history, ticket numbers or earlier chat. Restate what a thing is
  the first time it appears.
- **Avoid jargon.** When a technical term is unavoidable, explain it in a few words the first time, for example
  "a lockfile (the file that records the exact versions installed)".
- **When the owner must act, give numbered steps.** One action per step, short, saying where to click or what to run and
  which shell (bash or PowerShell). Say what they should see when it worked.
- **When you ask the owner a question, make it answerable.** Say what is being decided and why it matters, list the
  options in plain words with what each one means, give a recommendation, and say exactly how to answer (a word to reply
  with, or the steps and the link for where to click). Never ask a bare "A, B or C?" or "OK to proceed?".
- **When the owner has to fill in a form or a setting, give every non-secret value.** For each field, say the exact text
  to type or paste (name, description, URL), which boxes to tick or leave empty, and where to find it. Always supply a
  description wherever a form has a description field. Never put a password, token, client secret, certificate or private
  key in chat, pull requests, issues or documentation; tell the owner to enter each secret only in the approved secure
  settings field, or through a script that reads it from a file.
- **Include links.** Point to the exact settings page, the issue or pull request, and the official documentation
  (Microsoft Learn, GitHub Docs and similar) whenever one exists.
- **Be honest about status.** Separate what was checked, what is assumed, and what is blocked. Never present a guess as a result.

This applies to chat replies, pull request and issue text, and documentation. It does not apply to code comments or
machine-readable files, which keep following the surrounding style.
