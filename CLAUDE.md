# CLAUDE.md — HCW NetworkEyes App (Cloud Network Assessment)

Instructions for AI coding agents working in this repository. `README.md` is the
human intro page; this file states the rules an agent must not infer wrongly.

## What this repository is

This repository, `saulpatinojr/HCW-NetworkEyes_App`, is the **product** of the NetworkEyes App of the
HCW App-to-AddOn initiative: the single source of application code — `apps/network-assessment-web`, `apps/network-assessment-api`,
and the `network_assessment` Python package — and the pipeline that builds and publishes their
container images (`200-build-images.yml` → Docker Hub `<namespace>/img-ne-appliance-app`).

Users pull the images, not this repository. **NetworkEyes stands alone** (owner decision 2026-10-25): this
repository builds, scans, signs and publishes its own images and depends on nothing but itself and its own Docker Hub
repository, `docker.io/hybridcloudworks/img-ne-appliance-app`. The dependencies that were removed
stay removed: no workflow, script, Dockerfile, application code, template or live document names, calls, dispatches
to or reads a setting from the appliance repositories (another owner's), and no build, release or cleanup workflow
uses a GitHub App (only the owner-approved `390-repository-admin.yml` does, see `ADMIN_WORKFLOWS` in the boundary
test). The one carve-out is the lab build, `saulpatinojr/HCW-NetworkEyes_AddOn`: it is a downstream build that
pulls from this repository, so documents name and link it, this repository calls nothing in it and reads no setting
from it, and the one rule that reaches into it is a documentation note (*Tell the lab build what changed*, below). `tests/security/test_standalone_boundary.py` (the repository) and
`apps/network-assessment-web/lib/standalone-boundary.test.ts` (the web tier) fail when that comes back. Whoever deploys the images (a
person or a separate project) pulls them from Docker Hub by digest and verifies the cosign signature; this repository
does not know who that is and notifies no one.

History: this repository was the original Cloud Network Assessment repository. On 2026-09-18 its code moved to a
separate core repository, and on 2026-10-10 the owner merged that lineage back here, so this repository is again the
implementation target of `REFACTOR_APP.md` (the HCW App-to-AddOn plan; its lab build is
`saulpatinojr/HCW-NetworkEyes_AddOn`). **The earlier core repository is reference only: nothing for this repository is
written there (owner, 2026-10-11)**; its wiki pages were to move here (`REVIEW.md` → R-023; this repository's wiki was deleted on 2026-10-27, see R-031). Issue and pull-request numbers in
the documents older than that date name threads of the original or the earlier core repository.

Deployment is not this repository's job. There is no Terraform and no deploy workflow in this repository; it keeps
only `200-build-images`, `300-test-codebase`, `310-release-version`, `320-release-engine` and `370-registry-cleanup`,
plus one owner-approved exception, `390-repository-admin` (manual, dry-run by default, approved per run; it deploys
nothing and holds no product code). A deployment fix belongs to whoever deploys, never here.

## The image contract

Changing any of the following changes what a consumer of the images can rely on. Nobody is notified, so record the
change under `Changed` in `CHANGELOG.md` (and in the release notes) where a consumer will look, and in `TODO.md`.

1. **Image repository and tag scheme** on Docker Hub: every image is published to the one
   repository `<namespace>/img-ne-appliance-app` (owner convention
   `img-<short name>-<job>-<type>`; the retired `cna` repository holds a different image and is
   never used). The name is written once per layer — `IMAGE_REPOSITORY` in the workflow-level
   `env` of `200-build-images.yml`, `310-release-version.yml` and `370-registry-cleanup.yml`, and
   the `IMAGE_REPOSITORY` environment variable `scripts/ci/sign_image.sh` reads — and
   `tests/security/test_image_repository_name.py` fails if any workflow, script or contract
   names another repository. Tags inside it: `img-ne-appliance-app:{api,web,migrator}-sha-<7>`
   immutable tags plus floating `*-latest`; the CLI image is `img-ne-appliance-app:sha-<7>` /
   `img-ne-appliance-app:latest`. A release (`310`) adds a version tag to each of the four images of the released
   build: `img-ne-appliance-app:<version>` on the CLI image and `{api,web,migrator}-<version>` on the others.
   **The `worker` image was retired on 2026-10-27** (`REVIEW.md` R-016, owner decision, recorded under `Changed` in `CHANGELOG.md` and in the release notes):
   nothing builds, tags or releases it, its old `worker-*` tags stay on Docker Hub, and `370` keeps its `worker-sha-<7>` pattern only so those age out.
   The `200` rehearsal (a manual dry run of the Docker Hub connection) leaves one throwaway tag, `rehearsal-<run id>`,
   on Docker Hub; it matches no `370` pattern, so nothing prunes it, and it is removed by hand.
2. **The record of a build is the digest table in the step summary of `200-build-images.yml`'s
   `tag-images` job**: one row per component (`cli`, `api`, `web`, `migrator`) with its
   tags, its digest (`docker.io/<ns>/img-ne-appliance-app@sha256:<64>`) and whether it is signed
   (`tag-images` verifies each digest with `scripts/ci/verify_signed_digest.sh` before it moves
   a tag). The `*-latest` tags move only while the built commit is still current: it is the tip of the default branch, or an
   ancestor of the tip with nothing between them that `200` builds from (GitHub's compare of the two commits, matched
   against `200`'s own `on.push.paths`). Otherwise (the tip changed a build path, the commits diverged, or the
   comparison may be truncated) the run attaches its sha tags only, with a warning; if the tip or the comparison cannot
   be read, nothing is tagged. A re-run of `tag-images` is the recovery, and `*-latest` may legitimately stay unmoved
   when a later commit changed a build path (that commit's run owns the tags). The release notes of `310-release-version.yml` list the four version
   tags, their build-time tags and the four digests of the released build. Nothing is committed to the repository and no pull request is opened: there is no
   build manifest and no `.deployment-catalog/` directory. A consumer pulls by digest (tag for people and for the web
   tier's image-update check, digest as the authoritative pull); floating `*-latest` tags are never deployed.
   `370-registry-cleanup.yml` keeps the newest 10 `<component>-sha-<7>` tags per component, the
   `*-latest` tags, every release tag and any sha tag that shares an image with a non-sha tag, and ignores cosign's
   referrer tags (`sha256-<hex>`, `.sig`, `.att`, `.sbom`). Builds that were never released can still age out of the
   newest 10, and so can the other images of a release made before `310` tagged every image; see its header for
   what that does not protect. Tagging is not atomic: if `tag-images` stops part-way, the table shows
   "tagging in progress" without the closing line, and the recovery is to re-run that job (it verifies
   every digest again; re-creating a tag with the digest it already has is not an error).
3. **No push notification.** `200-build-images.yml` calls nothing outside this repository and its
   Docker Hub repository: it sends no dispatch event and reads no variable naming another
   repository.
4. **Runtime environment contract** the images read, set by whoever deploys them: `NETWORK_ASSESSMENT_AI_MODE` (`saas` |
   `byo-api`), `NETWORK_ASSESSMENT_APPLIANCE_CLOUD` (`azure` | `aws`), `NETWORK_ASSESSMENT_AI_ENGINE_DEFAULT`, the SaaS engine variables
   (`AZURE_OPENAI_*` on Azure, `NETWORK_ASSESSMENT_BEDROCK_*` on AWS), and
   `CREDENTIAL_ENCRYPTION_KEY` (web always; api in `byo-api`), and the image-update
   check inputs the web tier reads (`NETWORK_ASSESSMENT_WEB_IMAGE`, `NETWORK_ASSESSMENT_IMAGE_REGISTRY_USERNAME`,
   `NETWORK_ASSESSMENT_IMAGE_REGISTRY_TOKEN`, optional `NETWORK_ASSESSMENT_IMAGE_UPDATE_CHECK_INTERVAL_MINUTES`). `NETWORK_ASSESSMENT_BUILD_SHA` is baked into every
   image by `200-build-images.yml`, never injected. The authoritative inventory is
   `.env.example`. Until a later release removes it, the images also accept the old `CNA_<NAME>` spelling of each setting
   (a new name that has a value wins, a blank one does not hide an old one; `network_assessment/_legacy_env.py` and the web tier's
   `lib/legacy-env.ts` do the copy). That works one way only: an image from before the rename reads only the old names, so
   while old and new images run side by side, and when rolling back, set both names to the same value.
5. **Image signatures and provenance.** `200-build-images.yml` signs every
   published digest with cosign, keyless, under its own OIDC identity
   `https://github.com/<owner>/<this repo>/.github/workflows/200-build-images.yml@refs/heads/main`
   (issuer `https://token.actions.githubusercontent.com`), and attaches
   BuildKit's SLSA v0.2 provenance as a cosign attestation (type
   `slsaprovenance02`, `predicate.builder.id` = the run URL). A consumer should verify all
   three — signature, attestation, builder — before it runs an image; `scripts/ci/verify_signed_digest.sh` is the
   check `310` makes and the README shows the commands. Renaming or moving this repository, this workflow file, or
   its default branch changes the identity and breaks verification for everyone who pinned the old one, so say so in
   `CHANGELOG.md` and the release notes; the cosign release (`COSIGN_VERSION`) is pinned identically in `200` and `310`.
6. **Docker Hub is reached through its OIDC connection only** (the repository variable `DOCKERHUB_CONNECTION`; no
   stored password). The connection needs one ruleset for `main` (`200`; `TODO.md` T-728 records it as done by the owner, not
   re-read here) and a separate tag-only ruleset for `refs/tags/v*` (`310`, scope Image Push) before the first
   release; both are owner steps in `TODO.md` T-728. The one stored credential is the
   personal access token `370-registry-cleanup.yml` uses to delete tags (`REVIEW.md` R-026 step 3).
7. **Releases are cut by the owner**, dry run first: Actions, `310 · Release CLI Tool`, Run workflow, branch `main`,
   `dry_run` ticked (the default); read the summary, which names the commit the image was built from; then tag that
   commit (`git tag vX.Y.Z <sha>`, `git push origin vX.Y.Z`). The release gives all four images a version tag (every
   tag is checked before any is created) and the release notes list the tags and digests. Steps and failure cases: `TODO.md` T-728.

## AI engine rules

- Engine ids are `azure-openai`, `bedrock`, `anthropic`, `openai`. The selection
  rules live in `apps/network-assessment-web/lib/ai-engine-rules.ts` and
  `network_assessment/ai_engine/chat_agent.py` and are pinned by **one shared vector table**
  (`ai-engine-rules.test.ts`, `tests/unit/test_chat_agent.py`). Change both
  files and both tests together.
- `saas` mode uses the cloud-native engine for the appliance's cloud. `byo-api`
  mode uses admin-entered Anthropic/OpenAI keys. Those keys are the **only**
  secrets entered in the app UI; they are AES-256-GCM encrypted
  (`apps/network-assessment-web/lib/crypto.ts` ↔ `network_assessment/core/credential_crypto.py`, kept
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
  this in CI. Long-form docs have no destination since the GitHub Wiki was deleted
  (`REVIEW.md` R-031); do not add markdown files to work around that.
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
- **TypeScript runs side by side in `apps/network-assessment-web`.** `typescript` is the alias `npm:@typescript/typescript6` (the
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
  build, `300` test/release/ops). Numbers are stable; never renumber, reference by
  filename. This repository has `200`, `300`, `310`, `320`, `370` and the one exception `390`.
- **Job names in `300-test-codebase.yml` are required checks.** The `Protect main` ruleset matches them by name. Add a job, never rename one; list
  new job names in the pull request so the owner can add them to the ruleset. Dockerfiles must pass hadolint (`.hadolint.yaml` lists the only
  ignored rules, each with a written reason) and workflows must pass actionlint; run both with
  `bash scripts/ci/local-container-checks.sh hadolint actionlint`.
  The `migrator` image runs only the Prisma CLI, so its `node_modules` comes from the `migrator-deps` stage of `apps/network-assessment-web/Dockerfile` (cut out
  of `package-lock.json` by `apps/network-assessment-web/scripts/migrator-lockfile.mjs`); never copy the builder's `node_modules` into it. The job `Image Scan (Trivy)`
  checks that in the built image and scans the migrator and web runner for fixable HIGH and CRITICAL findings (`.trivyignore.yaml` holds the one
  narrow suppression, with its reason); `bash scripts/ci/local-container-checks.sh trivy-image <image>` runs the same scan locally.
- **Every GitHub Action is pinned to a SHA digest.** `detect-secrets` fails the
  build on any finding not in `.secrets.baseline`; `gitleaks` is advisory.
- **Secrets** travel as GitHub secrets → OIDC / Key Vault / Secrets Manager →
  container secrets (injected by whoever deploys the images). Never on a command
  line, never in a `workflow_dispatch` input, never committed.
- **Vendored agent configuration** (`.claude/`, `.agents/`, `.codex/`, `.kiro/`) is kept out of
  version control under `local/agent-config/` (gitignored, TODO T-411); it is not project
  source and must never contain project-specific facts.
- **`REFACTOR_APP.md`** at the root is the owner-approved refactoring plan this repository
  executes; the documentation model allows it (and the temporary `CNA-0.90-updates.md`) beside the four
  documents and this file, seven root documents at most, until their work has shipped.
- **Tell the lab build what changed.** `saulpatinojr/HCW-NetworkEyes_AddOn` keeps a "what's new"
  file, `docs/whats-new-upstream.md`, that its agents read before changing anything. When a change lands
  here that reaches it (the engine package `packages/network-assessment-azure-engine`, the rules, an
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
