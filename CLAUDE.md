# CLAUDE.md — HCW NetworkEyes App (Cloud Network Assessment)

Instructions for AI coding agents working in this repository. `README.md` is the
human intro page; this file states the rules an agent must not infer wrongly.

## What this repository is

This repository, `saulpatinojr/HCW-NetworkEyes_App`, is the **product** of the Cloud Network
Assessment (CNA) platform and the NetworkEyes App of the HCW App-to-AddOn initiative: the single
source of application code — `apps/cna-web`, `apps/cna-api`, `apps/cna-worker`,
and the `cna` Python package — and the pipeline that builds and publishes their
container images (`200-build-images.yml` → Docker Hub `<namespace>/cna`).

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
`300-test-codebase`, `310-release-version` and `370-registry-cleanup`. A
deployment fix belongs in the appliance (and its sibling), never here.

## The core ↔ appliance contract

Changing any of the following changes both appliances. Mirror the change into
**both** appliance repositories in the same change set (link the sibling PRs),
or record a `TODO.md` item naming them — never leave one side implied.

1. **Image tag scheme** on Docker Hub: `cna:{api,worker,web,migrator}-sha-<7>`
   immutable tags plus floating `*-latest`; the CLI image is `cna:sha-<7>` /
   `cna:latest`.
2. **`.deployment-catalog/latest-build.json`** — fields `sha_tag`, `commit`,
   `built_at`, `run_id`, `images{cli,api,worker,web,migrator}` (immutable tags)
   and `digests{cli,api,worker,web,migrator}` (`docker.io/<ns>/cna@sha256:<64>`).
   Written and committed by `200-build-images.yml` after every image passed the
   vulnerability gate; read by the appliances' image-update workflow, which
   deploys the combined form `docker.io/<ns>/cna:<role>-sha-<7>@sha256:<64>` —
   tag for people and for the web tier's image-update check, digest as the
   authoritative pull. Floating `*-latest` tags are never deployed.
3. **`repository_dispatch` event `cna-image-published`** with the manifest as
   `client_payload`, sent by `200-build-images.yml` to every repository listed in
   the `APPLIANCE_REPOS` variable (comma-separated names under this owner). It is
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
  release-push document). `scripts/validate_documentation_model.py` enforces
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
- **Workflows are numbered in bands** (`000` bootstrap, `100` validation, `200`
  build/deploy, `300` test/release/ops). Numbers are stable across core and
  both appliances; never renumber, reference by filename. The core owns `200`,
  `300`, `310`, `370`; every other number belongs to the appliances.
- **Every GitHub Action is pinned to a SHA digest.** `detect-secrets` fails the
  build on any finding not in `.secrets.baseline`; `gitleaks` is advisory.
- **Secrets** travel as GitHub secrets → OIDC / Key Vault / Secrets Manager →
  container secrets (injected by the appliances' Terraform). Never on a command
  line, never in a `workflow_dispatch` input, never committed.
- **Vendored agent configuration** (`.claude/`, `.agents/`, `.codex/`, `.kiro/`) is kept out of
  version control under `local/agent-config/` (gitignored, TODO T-411); it is not project
  source and must never contain project-specific facts.
- **`REFACTOR_APP.md`** at the root is the owner-approved refactoring plan this repository
  executes; the documentation model allows it beside the four documents until its change
  sets have shipped.
- Start with `TODO.md` when picking up work; check `REVIEW.md` when blocked on a
  human decision.
