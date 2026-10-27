# HCW NetworkEyes App — Cloud Network Assessment

[![CI](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/300-test-codebase.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/300-test-codebase.yml)
[![Release](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/310-release-version.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/310-release-version.yml)
[![Images](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/200-build-images.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/200-build-images.yml)
[![Engine release](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/320-release-engine.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/320-release-engine.yml)
[![python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![license](https://img.shields.io/github/license/saulpatinojr/HCW-NetworkEyes_App)](LICENSE)
[![lab build](https://img.shields.io/badge/lab%20build-HCW--NetworkEyes__AddOn-6f42c1?logo=github)](https://github.com/saulpatinojr/HCW-NetworkEyes_AddOn)

**New here?** Point it at an Azure or AWS environment and it maps the network, checks what it finds against
security, resilience and migration-readiness rules, and writes a report you can share. Nothing is assumed: every
finding names the fact it came from. A free, upload-only version that needs no cloud access is the lab build,
[HCW-NetworkEyes_AddOn](https://github.com/saulpatinojr/HCW-NetworkEyes_AddOn), which will appear at
[hybridcloudworks.com/tools/network-assessment](https://hybridcloudworks.com/tools/network-assessment) once its first
image is published. NetworkEyes is a free tool for followers of Hybrid Cloud Works, shared through GitHub. There is no
paid edition.

This repository is the **product** of NetworkEyes, a Cloud Network Assessment tool: the single home
of the application code and of the pipeline that builds and publishes its container images. It
is the NetworkEyes App of the HCW App-to-AddOn initiative: `REFACTOR_APP.md` is its refactoring
plan and [`HCW-NetworkEyes_AddOn`](https://github.com/saulpatinojr/HCW-NetworkEyes_AddOn) is
its lab build. It stands alone: it builds, signs and publishes its own container images to Docker Hub
(`docker.io/hybridcloudworks/img-ne-appliance-app`), deploys nothing and notifies no one; see
[Publishing the images](#publishing-the-images).

A multi-user web app for cloud network assessments across AWS and Azure.
Analysts run network discoveries, AI-powered analysis, and generate presentation-ready
deliverables including an encyclopedia-grade network report. Users share deliverables through
a time-limited authenticated portal. The app deploys as three containerized services behind a
managed edge, backed by PostgreSQL and authenticated via Microsoft Entra ID.

---

## Documentation map

This repository keeps four required documents at the root plus `CLAUDE.md`, and one *optional* temporary
working document that is removed when its work ships (`REFACTOR_APP.md`, the refactoring plan). That makes six
root documents at most. Long-form documentation (guides, architecture, runbooks, decision records) lives in the
[`docs/`](docs) folder, at any depth below it; nothing in it is required, and it is reviewed in pull requests like
code (the GitHub Wiki that used to hold it was deleted on 2026-10-27; `REVIEW.md`, R-031). The community files GitHub
reads (`SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, the pull request template and the issue forms) live in
[`.github/`](.github), not at the root and not in `docs/`. Nothing else is allowed:
`scripts/validate_documentation_model.py` fails the build on any other document file (a file ending in `.md`,
`.rst`, `.adoc` and the like), for example in `doc/`, `documentation/`, `Docs/` or a `docs` folder anywhere other
than the top level of the repository (a `docs` folder inside `docs/` itself is only a subfolder and is fine). This
section is the model's one full statement: the other documents point here, and a test keeps its count and its list in
step with the validator.

| Document | Contains |
|---|---|
| `README.md` (this file) | Repository purpose, quick start, configuration, navigation |
| [`CHANGELOG.md`](CHANGELOG.md) | Completed work, by release |
| [`REVIEW.md`](REVIEW.md) | Blockers that require a human decision, approval, or access grant |
| [`TODO.md`](TODO.md) | The engineering work queue — every actionable item, phased |
| [`REFACTOR_APP.md`](REFACTOR_APP.md) | *Optional, temporary* — the owner-approved refactoring plan this repository executes (HCW App-to-AddOn initiative, 2026-10): change sets A–K, acceptance criteria, validation commands |
| [`CLAUDE.md`](CLAUDE.md) | Rules for AI coding agents: what this repository is, the image contract, and the conventions agents get wrong |
| [`docs/`](docs) | Long-form documentation. There are no pages yet; [`docs/README.md`](docs/README.md) says what belongs there and how pages are named and reviewed |

If you are picking up work on this repository, start with `TODO.md`. If you are waiting on
someone, check `REVIEW.md`.

---

## Repository layout

```
apps/
├── network-assessment-web/          Next.js web platform (8-step journey, encyclopedia, copilot)
└── network-assessment-api/          FastAPI — metrics, chat, reports, discovery, and publishing (`POST /publish`) routers
packages/             network-assessment-azure-engine — the Azure engine (model, typed rules, classifier,
                      Resource Graph normalizer, renderers); a uv workspace member the network_assessment package consumes
network_assessment/   Python package, installed as the `network-assessment` CLI (the old `cna` command still works)
├── core/             topology/{common,azure,aws} · findings_schema · stat_masters · engagement
├── modules/          AWS + Azure discovery, FinOps signals, BC/DR signals, topology classifier
├── ai_engine/        Azure rule registry (azure_rules), AWS analysis engine, recommendation engine, chat agent
├── report_engine/    Encyclopedia renderer, WeasyPrint PDF, radar chart SVG
├── diagram_engine/   Draw.io generator, future-state model
├── delivery_portal/  Deliverable sharing portal
└── cli/              Command-line entry point
scripts/              Repository guards (documentation model, module graph, shape catalog)
                      and the headless draw.io wrapper the images use
tests/                unit/ and integration/
docs/                 Long-form documentation (no pages yet; see the Documentation map) and
                      roles/, the custom Azure role definition as a JSON file
.github/workflows/    200 build images · 300 test · 310 release · 320 engine release · 370 registry cleanup · 390 repository admin
local/agent-config/   Vendored agent configuration — gitignored, not project source
```

---

## Publishing the images

NetworkEyes stands alone (owner decision 2026-10-25): this repository builds, scans, signs and publishes its own
images and depends on nothing but itself and its own Docker Hub repository. It deploys nothing, calls no other
repository and notifies no one. Whoever runs the images (a person or a separate project) takes them from Docker Hub.

- **Where.** One public Docker Hub repository, `docker.io/hybridcloudworks/img-ne-appliance-app` (the owner's
  `img-<short name>-<job>-<type>` convention). Tags: `<component>-sha-<7>` for `api`, `web` and `migrator`,
  `sha-<7>` for the CLI image, floating `*-latest` (moved only while the built commit is still current: the tip of the default branch, or an
  ancestor of it with nothing between them that `200` builds from; otherwise only the sha tags are attached), and for a release the version tags `X.Y.Z` on the CLI image and `api-X.Y.Z`,
  `web-X.Y.Z` and `migrator-X.Y.Z` on the others. There is no `worker` image any more (retired on 2026-10-27, `REVIEW.md` R-016):
  its old `worker-*` tags stay on Docker Hub and are no longer updated, and a deployment that still runs a worker service can drop it.
- **How an image is published.** `200-build-images.yml` pushes each image by digest, has Docker Scout scan it, signs it
  with cosign (keyless, under the workflow's own GitHub identity) and attaches the build provenance; only when all four
  images pass does it attach the tags. It logs in to Docker Hub through Docker's OIDC connection (the repository
  variable `DOCKERHUB_CONNECTION`), so no Docker Hub password is stored for it. The record of a build is a table in
  the step summary of the run (one row per component: tags, digest, signed); it commits nothing and notifies no other
  repository.
- **Releases.** A `v*.*.*` tag runs `310-release-version.yml`, which gives the four images `200`
  already built and signed for that commit, or for the last build before it when only documentation, tests or another
  workflow changed since, their version tags (it checks all four first and creates none if one already exists with
  another digest), and lists each version tag, its build-time tag and its digest in the release notes. A tag on a commit that
  changed a file `200` builds from fails and names it and the nearest built commit. The Docker Hub connection needs a
  separate tag-only rule (`refs/tags/v*`, Image Push) for this workflow before the first release (`TODO.md` T-728; the connection has not been read from here, so it is
  not confirmed that the rule exists yet).
- **Cutting a release (owner steps).** (1) In the browser: Actions, **310 · Release CLI Tool**, **Run workflow**, branch
  `main`, leave **dry_run** ticked (the default). It finds and verifies the image of the latest build, prints what it
  would promote and the commit it was built from, and creates nothing. (2) If the summary looks right, tag that
  commit. Bash or PowerShell, in a clone of this repository (use the commit shown in the summary for `<sha>`):
  `git tag vX.Y.Z <sha>` then `git push origin vX.Y.Z`. (3) The tag run adds the four version tags and creates the GitHub
  Release. `TODO.md` T-728 has the one-time Docker Hub steps and what to do when a run fails.

The project started as a single repository that held the core until 2026-09-18. Its full history is imported here
(`TODO.md` → T-509), so commit references in `CHANGELOG.md` still resolve; this repository is that original, renamed
(`REVIEW.md` → R-014), so issue and pull-request numbers in documents older than 2026-10-10 name threads of the
earlier repositories and are historical references only. New work, issues and pull requests belong here.

The AI provider family is chosen at deploy time by `NETWORK_ASSESSMENT_AI_MODE`: `saas` (Azure OpenAI on Azure, Amazon Bedrock on AWS,
authenticated with the workload identity) or `byo-api` (no cloud AI resources; an admin pastes an Anthropic and/or
OpenAI API key on the **AI Engine** admin page — the only secrets ever entered in the app, stored encrypted in the
database).

### Verifying images

Every published digest is signed (cosign, keyless) and carries a SLSA provenance attestation made by `200-build-images.yml`
on `main`. Resolve a tag to a digest, then verify that exact digest before you run it. A digest that does not verify must
not be deployed. A released image has a version tag (`X.Y.Z` for the CLI image, `<component>-X.Y.Z` for the others); the
release notes list each version tag with its digest, and you verify the digest, not the tag.

```bash
IMAGE=docker.io/hybridcloudworks/img-ne-appliance-app@sha256:<64 hex>
ID=https://github.com/saulpatinojr/HCW-NetworkEyes_App/.github/workflows/200-build-images.yml@refs/heads/main
ISS=https://token.actions.githubusercontent.com
cosign verify "$IMAGE" --certificate-identity "$ID" --certificate-oidc-issuer "$ISS"
cosign verify-attestation "$IMAGE" --type slsaprovenance02 --certificate-identity "$ID" --certificate-oidc-issuer "$ISS"   | jq -r '.payload | @base64d | fromjson | .predicate.builder.id'
```

The last command prints the attestation's `predicate.builder.id`, which must begin with
`https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/runs/` (a run of this repository). `cosign verify-attestation`
alone does not check it; `scripts/ci/verify_signed_digest.sh` does.

Pass `--use-signed-timestamps` if you want the signed timestamp from the timestamp authority; without it cosign 3 uses the
transparency-log time. The identity string must match exactly: renaming or
transferring the repository, or renaming the workflow file or the default branch, changes it (the change is announced in the
release notes). `scripts/ci/verify_signed_digest.sh` does the same checks and also binds the digest to a commit. The four
digests of each build are in the step summary of its `200-build-images.yml` run, and those of a release are in its release
notes.

---

## Quick start

### Web platform, locally

```bash
cd apps/network-assessment-web
cp .env.example .env.local
# Fill in DATABASE_URL, NEXTAUTH_SECRET, AZURE_AD_* values
npm install
npm run db:migrate
npm run dev          # http://localhost:3000
```

Other useful scripts: `npm run build`, `npm run lint`, `npm run typecheck`, `npm test`, `npm run db:studio`, `npm run db:generate` — the first three plus `npm test` are what `300 · Test Codebase` runs for the web tier.

### Python CLI, locally

Requires Python 3.11 or newer.

```bash
pip install -e .[dev]
pre-commit install
cp .env.example .env
network-assessment --help
```

**AWS (optional).** The base install carries no `boto3`. `pip install -e ".[dev,aws]"` enables
`network-assessment discover aws`, Security Hub collection, the S3 delivery portal, Bedrock chat and the API's
`/discovery/*-aws` routes (which answer `501 aws_not_installed` without it); every AWS module imports
`boto3` behind `network_assessment.aws.require_aws_extra()`. The AWS permission list is
`network_assessment/modules/network/module.aws.yaml`. The appliance images install the extra.

Lint and test the Python package with `ruff check network_assessment/`, `ruff format --check`, and `pytest`.

The container images do not resolve dependencies at build time: they install the resolution
committed in `uv.lock` with hash checking. After changing a dependency in `pyproject.toml`, run
`uv lock` (uv ≥ 0.12.21) and commit the updated lock alongside it — CI fails when the two disagree.

### Deploying an environment

Deployment does not happen from this repository, which only publishes the images. Run them with your own process: pull
by digest, verify the signature (see [Publishing the images](#publishing-the-images)) and
supply the runtime settings listed in `.env.example`.

---

## Configuration

Configuration comes from three places, in this order of authority:

1. **GitHub Secrets and Variables** — for this repository, only what its workflows need (names only; values are never
   in the repository): `DOCKERHUB_NAMESPACE`, `DOCKERHUB_CONNECTION` (the Docker Hub OIDC connection id) and
   `DOCKERHUB_ENABLED` (the publishing switch) for `200` and `310`; `DOCKERHUB_PERSONAL_USERNAME` (variable) and
   `DOCKERHUB_PERSONAL_TOKEN` (secret) for the registry cleanup `370`; `PYPI_PUBLISH_ENABLED` for the engine release
   `320`; and, for the owner-approved `390` only, the credentials of the `admin-ops` environment (`APP_CLIENT_ID`,
   `APP_PRIVATE_KEY`, `PROJECT_TOKEN`). The build, release and registry-cleanup workflows use no GitHub App and notify
   no other repository; the App credentials in `admin-ops` belong to the separate `390-repository-admin.yml` only. `TODO.md` T-728 and `REVIEW.md` R-026 have the steps. Deployment secrets and
   variables belong to whoever deploys the images.
2. **The deployment's vault** (Azure Key Vault / AWS Secrets Manager) — runtime secrets for a deployed environment,
   injected by whoever deploys the images.
3. **`.env` / `.env.local`** — local development only, never committed.

`.env.example` at the repository root is the complete inventory of the runtime environment
contract — every variable the images read, each with a one-line description and which side
(the deployment or local `.env`) supplies it.
`apps/network-assessment-web/.env.example` covers the web application specifically. Each value is explained by the comment
next to it.

---

## Licence

The code in this repository and the container images built from it are licensed under the
[Apache License, Version 2.0](LICENSE). The image label `org.opencontainers.image.licenses` says `Apache-2.0`. The
[`NOTICE`](NOTICE) file lists what the Apache licence does not cover: the Aeonik typeface, and the names "Hybrid Cloud
Works" and "NetworkEyes", and the Hybrid Cloud Works logo (section 6 of the licence grants no permission
to use them, except for reasonable and customary use in describing the origin of the Work and reproducing the content of
`NOTICE`). For the typeface the owner states that no separate licence is required (2026-10-25); this repository holds no
licence file for it and has not verified the statement (`REVIEW.md`, R-020). The copyright holder is Hybrid Cloud Works
(owner's statement, 2026-10-26; `REVIEW.md`, R-030).

## Repository conventions

- **Documents go where the Documentation map says.** The model is set out in full once, in the Documentation map
  above; `scripts/validate_documentation_model.py` enforces it in CI. Long-form documentation goes in `docs/`.
  Do not add a document file anywhere else.
- **Image contract changes are recorded, never implied.** Any change to the image tag scheme, the
  signed-digest record, or the runtime environment contract
  (`NETWORK_ASSESSMENT_AI_MODE`, `NETWORK_ASSESSMENT_APPLIANCE_CLOUD`, …) is recorded under `Changed` in `CHANGELOG.md` and in the release notes,
  where a consumer will look; nobody is notified — see [`CLAUDE.md`](CLAUDE.md).
- **Numbered workflows.** Workflows use numeric bands:
  `000` bootstrap, `100` validation, `200` build, `300` test, release, and operations.
  This repository has `200`, `300`, `310`, `320` (the engine release) and `370`, plus the one owner-approved
  exception `390` (repository admin; manual, dry-run by default). Within a band, the
  number is stable — reference workflows by filename, not by position, and never renumber.
- **Never hardcode a value at a call site.** Regions, endpoints, account IDs, and every other
  environment-specific value is *declared* — as a `DiscoveryOptions` field, a named module-level
  constant, or a setting — and resolved at runtime, most specific source first. That is the point
  of the declared lists: they record what to use later, and they can be overridden. A declared
  default is a last resort, never an inline literal.
- **All GitHub Actions are pinned to a SHA digest.** `detect-secrets` runs at commit time and in
  CI, and **fails the build** on any finding not recorded in `.secrets.baseline` — which holds only
  hand-audited false positives, never a suppression dump. `gitleaks` also runs in CI but is
  advisory: it needs a paid licence on private repositories, so its job is `continue-on-error` and
  cannot fail a build. Do not read it as a gate. Its 122 hits in the full history were all checked on
  2026-10-25 and are false positives; `.gitleaksignore` lists them one by one (by fingerprint, so a new
  finding still shows) with the reason for each class.
- **Vendored agent configuration** (`.claude/`, `.agents/`, `.codex/`, `.kiro/`) is kept out of version
  control under `local/agent-config/` (gitignored). It is configuration, not project source; lint,
  the documentation model and secret scanning exclude `local/`, and it must never contain
  project-specific facts.

---

*Maintained by Saul Patino Jr. — AWS SA Professional | Azure Solutions Architect Expert*
