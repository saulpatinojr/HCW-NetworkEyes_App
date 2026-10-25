# HCW NetworkEyes App — the Cloud Network Assessment (CNA) platform

[![CI](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/300-test-codebase.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/300-test-codebase.yml)
[![Release](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/310-release-version.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/310-release-version.yml)
[![Images](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/200-build-images.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/200-build-images.yml)
[![Engine release](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/320-release-engine.yml/badge.svg)](https://github.com/saulpatinojr/HCW-NetworkEyes_App/actions/workflows/320-release-engine.yml)
[![python](https://img.shields.io/badge/python-3.14-3776AB?logo=python&logoColor=white)](pyproject.toml)
[![license](https://img.shields.io/github/license/saulpatinojr/HCW-NetworkEyes_App)](LICENSE)
[![lab edition](https://img.shields.io/badge/lab%20edition-HCW--NetworkEyes__AddOn-6f42c1?logo=github)](https://github.com/saulpatinojr/HCW-NetworkEyes_AddOn)

**New here?** Point it at an Azure or AWS environment and it maps the network, checks what it finds against
security, resilience and migration-readiness rules, and writes a report a client can read. Nothing is assumed: every
finding names the fact it came from. A free, upload-only version that needs no cloud access is the lab edition,
[HCW-NetworkEyes_AddOn](https://github.com/saulpatinojr/HCW-NetworkEyes_AddOn), which will appear at
[hybridcloudworks.com/tools/network-assessment](https://hybridcloudworks.com/tools/network-assessment) once its first
image is published.

This repository is the **product** of the Cloud Network Assessment platform: the single home
of the application code and of the pipeline that builds and publishes its container images. It
is the NetworkEyes App of the HCW App-to-AddOn initiative: `REFACTOR_APP.md` is its refactoring
plan and [`HCW-NetworkEyes_AddOn`](https://github.com/saulpatinojr/HCW-NetworkEyes_AddOn) is
its lab edition. Customers consume one of the two **appliance** repositories —
[Azure](https://github.com/saulpatinojr/Work-Cloud_Network_Azure_Appliance) or [AWS](https://github.com/saulpatinojr/Work-Cloud_Network_AWS_Appliance) — which deploy the images published here.

A CNA-branded, multi-user web platform for cloud network assessments across AWS and Azure.
Analysts run network discoveries, AI-powered analysis, and generate presentation-ready
deliverables including an encyclopedia-grade network report. Clients receive deliverables through
a time-limited authenticated portal. The platform deploys as three containerized services behind a
managed edge, backed by PostgreSQL and authenticated via Microsoft Entra ID.

---

## Documentation map

This repository keeps four required documents plus `CLAUDE.md`, and two *optional* temporary
working documents that are removed when their work ships (`REFACTOR_APP.md`, the refactoring plan, and
`CNA-0.90-updates.md`). That makes seven root documents at most; `scripts/validate_documentation_model.py`
enforces the list. The community files GitHub reads (`SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, the pull request template and the issue forms) live in
[`.github/`](.github), not at the root, and the validator allows exactly those. Everything else lives in the
[GitHub Wiki](https://github.com/saulpatinojr/HCW-NetworkEyes_App/wiki).

| Document | Contains |
|---|---|
| `README.md` (this file) | Repository purpose, quick start, configuration, navigation |
| [`CHANGELOG.md`](CHANGELOG.md) | Completed work, by release |
| [`REVIEW.md`](REVIEW.md) | Blockers that require a human decision, approval, or access grant |
| [`TODO.md`](TODO.md) | The engineering work queue — every actionable item, phased |
| [`REFACTOR_APP.md`](REFACTOR_APP.md) | The owner-approved refactoring plan this repository executes (HCW App-to-AddOn initiative, 2026-10): change sets A–K, acceptance criteria, validation commands |
| [`CLAUDE.md`](CLAUDE.md) | Rules for AI coding agents: what this repository is (the core), the contract with the two appliance repositories, and the conventions agents get wrong |
| [`CNA-0.90-updates.md`](CNA-0.90-updates.md) | *Optional, temporary* — the one working-document exception to the four required docs: the 0.9.0 pre-demo review, cleanup record, polish plan, and the 2026-08-28 dev rebuild/deployment record (§5); retired when 0.9.0 ships |
| [GitHub Wiki](https://github.com/saulpatinojr/HCW-NetworkEyes_App/wiki) | Architecture, ADRs, runbooks, workflow reference, security posture, operating notes (deployment guides live with the appliances) |

If you are picking up work on this repository, start with `TODO.md`. If you are waiting on
someone, check `REVIEW.md`.

---

## Repository layout

```
apps/
├── cna-web/          Next.js web platform (8-step journey, encyclopedia, copilot)
├── cna-api/          FastAPI — metrics, chat, reports, discovery routers
└── cna-worker/       Python background worker — discovery + report generation
packages/             cna-azure-network-engine — the Azure engine (model, typed rules, classifier,
                      Resource Graph normalizer, renderers); a uv workspace member the cna package consumes
cna/                  Python package, installed as the `cna` CLI
├── core/             topology/{common,azure,aws} · findings_schema · stat_masters · engagement
├── modules/          AWS + Azure discovery, FinOps signals, BC/DR signals, topology classifier
├── ai_engine/        Azure rule registry (azure_rules), AWS analysis engine, recommendation engine, chat agent
├── report_engine/    Encyclopedia renderer, WeasyPrint PDF, radar chart SVG
├── diagram_engine/   Draw.io generator, future-state model
├── delivery_portal/  Client deliverable delivery
└── cli/              Command-line entry point
scripts/              Repository guards (documentation model, module graph, shape catalog)
                      and the headless draw.io wrapper the images use
tests/                unit/ and integration/
.github/workflows/    200 build images · 300 test · 310 release · 320 engine release · 370 registry cleanup · 390 repository admin
.deployment-catalog/  latest-build.json — the build manifest the appliances consume
local/agent-config/   Vendored agent configuration — gitignored, not project source
```

---

## Repository topology

CNA is delivered as one internal **core** repository (this one) and two customer-facing
**appliance** repositories, one per cloud:

| Repository | Owns | Does not contain |
|---|---|---|
| `HCW-NetworkEyes_App` (this repository; the Core lineage merged back on 2026-10-10) | Application code (`apps/`, `cna/`), container image builds and publishing (`200-build-images.yml`), tests and releases | Customer deployments |
| [`Work-Cloud_Network_Azure_Appliance`](https://github.com/saulpatinojr/Work-Cloud_Network_Azure_Appliance) | Azure Terraform, deploy / update / drift / teardown workflows, the Azure release catalog | Application code, anything AWS |
| [`Work-Cloud_Network_AWS_Appliance`](https://github.com/saulpatinojr/Work-Cloud_Network_AWS_Appliance) | AWS Terraform, the same workflows, the AWS release catalog | Application code, anything Azure |

The two appliances are structurally identical — same file names, workflow numbers, inputs,
catalog schema, scripts, and documents — differing only in the cloud-specific parts each README
enumerates. **Features ship once, here, in the images.** When `200-build-images.yml` publishes a
new image set it opens a pull request that updates `.deployment-catalog/latest-build.json` (it merges itself
once the required checks pass, because `main` is protected) and sends a `repository_dispatch`
(`cna-image-published`) to every repository named in the `APPLIANCE_REPOS` variable, under the account named in
`APPLIANCE_OWNER` (the appliances do not live under this repository's owner); each
appliance also polls the manifest. An appliance auto-deploys new images to `dev` and opens an
"update available" issue for `prod`, which a human approves through its deploy workflow's
approval gate. Every image goes to one Docker Hub repository, `<namespace>/img-ne-appliance-app`
(the owner's `img-<short name>-<job>-<type>` convention; the tags inside it are unchanged). The full
contract is in [`CLAUDE.md`](CLAUDE.md).

The project started as a single repository, `Work-Cloud_Network_Assessment`, which held the core
until 2026-09-18. Its full history is imported here (`TODO.md` → T-509), so commit references in
`CHANGELOG.md` still resolve; the original repository is retired and being deleted (`REVIEW.md`
→ R-014), so its issue and pull-request numbers in the documents are historical references only.
New work, issues and pull requests belong here.

Every deploy is run from the appliance's **Run workflow** dialog, where `ai_mode` selects the AI
provider family: `saas` (Azure OpenAI on Azure, Amazon Bedrock on AWS — provisioned by
Terraform, authenticated with the workload identity) or `byo-api` (no cloud AI resources; an
admin pastes an Anthropic and/or OpenAI API key on the **AI Engine** admin page — the only
secrets ever entered in the app, stored encrypted in the database).

---

## Quick start

### Web platform, locally

```bash
cd apps/cna-web
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
cna --help
```

**AWS (optional).** The base install carries no `boto3`. `pip install -e ".[dev,aws]"` enables
`cna discover aws`, Security Hub collection, the S3 delivery portal, Bedrock chat and the API's
`/discovery/*-aws` routes (which answer `501 aws_not_installed` without it); every AWS module imports
`boto3` behind `cna.aws.require_aws_extra()`. The AWS permission list is
`cna/modules/network/module.aws.yaml`. The appliance images install the extra.

Lint and test the Python package with `ruff check cna/`, `ruff format --check`, and `pytest`.

The container images do not resolve dependencies at build time: they install the resolution
committed in `uv.lock` with hash checking. After changing a dependency in `pyproject.toml`, run
`uv lock` (uv ≥ 0.12.21) and commit the updated lock alongside it — CI fails when the two disagree.

### Deploying an environment

Deployment does not happen from this repository. Each appliance repository owns its cloud's
Terraform, bootstrap, deploy, drift and teardown workflows and documents the procedure in its
`README.md` → *Operating the appliance*: [Azure](https://github.com/saulpatinojr/Work-Cloud_Network_Azure_Appliance) · [AWS](https://github.com/saulpatinojr/Work-Cloud_Network_AWS_Appliance). This repository
only publishes the images they deploy (`200-build-images.yml`). Deployment blockers live in the
appliances' `REVIEW.md` files; the AWS appliance's deploy stays fail-fast until its account,
state backend and OIDC role exist (its R-001 – R-003).

---

## Configuration

Configuration comes from three places, in this order of authority:

1. **GitHub Secrets and Variables** — for this repository, only what the build and release
   workflows need (Docker Hub, the GitHub App for appliance notification). Deployment secrets and
   variables belong to the appliance repositories, where cloud credentials use OIDC and there are
   no long-lived keys.
2. **The appliance's vault** (Azure Key Vault / AWS Secrets Manager) — runtime secrets for a
   deployed environment, injected by the appliance's Terraform; its `340-sync-keys` workflow can
   pull them into a short-lived `.env` artifact.
3. **`.env` / `.env.local`** — local development only, never committed.

`.env.example` at the repository root is the complete inventory of the runtime environment
contract — every variable the images read, each with a one-line description and which side
(appliance Terraform or local `.env`) supplies it.
`apps/cna-web/.env.example` covers the web application specifically. The Wiki's **Secrets
Reference** explains each value in full.

---

## Repository conventions

- **Four documents plus `CLAUDE.md`, one wiki.** `README.md`, `CHANGELOG.md`, `REVIEW.md`,
  `TODO.md`, and `CLAUDE.md` (agent instructions) are the only markdown files in the repository, apart
  from the two optional temporary documents named in "Documentation map" (`REFACTOR_APP.md`, `CNA-0.90-updates.md`) and the
  community files in `.github/`.
  Long-form documentation goes to the Wiki. Content determines destination, not filename.
- **The appliance contract is mirrored, never implied.** Any change to the image tag scheme, the
  build manifest, the `cna-image-published` dispatch, or the runtime environment contract
  (`CNA_AI_MODE`, `CNA_APPLIANCE_CLOUD`, …) is made in both appliance repositories in the same
  change set — see [`CLAUDE.md`](CLAUDE.md).
- **Numbered workflows.** Workflows use numeric bands shared by the core and both appliances:
  `000` bootstrap, `100` validation, `200` build and deploy, `300` test, release, and operations.
  The core keeps `200`, `300`, `310`, `320` (the engine release) and `370`, plus the one owner-approved
  exception `390` (repository admin; manual, dry-run by default); the appliances keep the rest. Within a band, the
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
  cannot fail a build. Do not read it as a gate.
- **Vendored agent configuration** (`.claude/`, `.agents/`, `.codex/`, `.kiro/`) is kept out of version
  control under `local/agent-config/` (gitignored). It is configuration, not project source; lint,
  the documentation model and secret scanning exclude `local/`, and it must never contain
  project-specific facts.

---

*Maintained by Saul Patino Jr. — AWS SA Professional | Azure Solutions Architect Expert*
