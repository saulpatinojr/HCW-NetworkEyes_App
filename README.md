# Cloud Network Assessment (CNA) Platform

[![CI](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/300-test-codebase.yml/badge.svg)](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/300-test-codebase.yml)
[![Release](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/310-release-version.yml/badge.svg)](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/310-release-version.yml)

A CNA-branded, multi-user web platform for cloud network assessments across AWS and Azure.
Analysts run network discoveries, AI-powered analysis, and generate presentation-ready
deliverables including an encyclopedia-grade network report. Clients receive deliverables through
a time-limited authenticated portal. The platform deploys as three containerized services behind a
managed edge, backed by PostgreSQL and authenticated via Microsoft Entra ID.

---

## Documentation map

This repository keeps exactly four documents. Everything else lives in the
[GitHub Wiki](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/wiki).

| Document | Contains |
|---|---|
| `README.md` (this file) | Repository purpose, quick start, configuration, navigation |
| [`CHANGELOG.md`](CHANGELOG.md) | Completed work, by release |
| [`REVIEW.md`](REVIEW.md) | Blockers that require a human decision, approval, or access grant |
| [`TODO.md`](TODO.md) | The engineering work queue — every actionable item, phased |
| [`CNA-0.90-updates.md`](CNA-0.90-updates.md) | *Temporary* — the 0.9.0 pre-demo review, cleanup record, and polish plan; retired when 0.9.0 ships |
| [GitHub Wiki](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/wiki) | Architecture, ADRs, runbooks, workflow reference, security posture, deployment guides |

If you are picking up work on this repository, start with `TODO.md`. If you are waiting on
someone, check `REVIEW.md`.

---

## Repository layout

```
apps/
├── cna-web/          Next.js web platform (8-step journey, encyclopedia, copilot)
├── cna-api/          FastAPI — metrics, chat, reports, discovery routers
└── cna-worker/       Python background worker — discovery + report generation
cna/                  Python package, installed as the `cna` CLI
├── core/             topology_schema · findings_schema · stat_masters · engagement
├── modules/          AWS + Azure discovery, FinOps signals, BC/DR signals, topology classifier
├── ai_engine/        Analysis engine, recommendation engine, chat agent
├── report_engine/    Encyclopedia renderer, WeasyPrint PDF, radar chart SVG
├── diagram_engine/   Draw.io generator, future-state model
├── delivery_portal/  Client deliverable delivery
└── cli/              Command-line entry point
infra/terraform/
├── environments/azure/{dev,prod}/{platform,workload}/   Azure environment composition
├── environments/aws/{dev,prod}/{platform,workload}/     AWS environment composition
├── providers/azure/   Reusable modules: ai, compute, database, identity,
│                      security, storage, runtime, observability
└── providers/aws/     The same eight module boundaries, mirrored
migrate/              Superseded standalone AWS Terraform root — retirement tracked in TODO.md → T-401
scripts/              Bootstrap, validation, cleanup, and CI helper scripts
tests/                unit/ and integration/
.github/workflows/    Numbered workflow sequence (see conventions below)
.claude/ .agents/ .codex/   Vendored agent configuration — not project source
```

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

Other useful scripts: `npm run build`, `npm run lint`, `npm run db:studio`, `npm run db:generate`.

### Python CLI, locally

Requires Python 3.11 or newer.

```bash
pip install -e .[dev]
pre-commit install
cp .env.example .env
cna --help
```

Lint and test the Python package with `ruff check cna/`, `ruff format --check`, and `pytest`.

### Deploying an environment

Deployment runs through the numbered GitHub Actions workflows, in band order: bootstrap the
Terraform backend, validate prerequisites, build images, then deploy. The full step-by-step
procedure — including the Entra redirect-URI sync and the teardown sequence — is in the Wiki's
**Deployment Guide**.

Azure is the deployable path today. The AWS Terraform is authored but has never been applied; its
prerequisites are tracked in [`REVIEW.md`](REVIEW.md) and its remaining work in
[`TODO.md`](TODO.md).

---

## Configuration

Configuration comes from three places, in this order of authority:

1. **GitHub Secrets and Variables** — the source of truth for deployments. Cloud credentials use
   OIDC; there are no long-lived keys.
2. **Azure Key Vault** — runtime secrets for a deployed environment. Workflow `340-sync-keys.yml`
   can pull them into a short-lived `.env` artifact.
3. **`.env` / `.env.local`** — local development only, never committed.

`.env.example` at the repository root is the complete inventory: every GitHub secret, every GitHub
variable, and every local environment variable, each with a one-line description.
`apps/cna-web/.env.example` covers the web application specifically. The Wiki's **Secrets
Reference** explains each value in full.

---

## Repository conventions

- **Four documents, one wiki.** `README.md`, `CHANGELOG.md`, `REVIEW.md`, and `TODO.md` are the
  only markdown files in the repository. Long-form documentation goes to the Wiki. Content
  determines destination, not filename.
- **Numbered workflows.** `.github/workflows/` uses numeric bands: `000` bootstrap, `100`
  validation, `200` build and deploy, `300` test, release, and operations. Within a band, the
  number is stable — reference workflows by filename, not by position. Per-workflow detail is in
  the Wiki's **Workflows Guide**.
- **Resource naming.** Azure resources follow `cna-[env]-[region_short]`, with a single workload
  resource group per environment and a separate resource group for Terraform state.
- **Split state.** Every environment has a `platform` root and a `workload` root with separate
  state files. Platform applies first; workload consumes its outputs through explicit variables.
- **Never hardcode a value at a call site.** Regions, endpoints, account IDs, and every other
  environment-specific value is *declared* — as a Terraform variable, a `DiscoveryOptions` field, or
  a named module-level constant — and resolved at runtime, most specific source first. That is the
  point of the declared lists: they record what to use later, and they can be overridden. A
  declared default is a last resort, never an inline literal. Terraform variables carrying values a
  human must supply take no default at all, so a plan fails rather than applying something
  plausible-but-wrong.
- **PowerShell scripts** use Verb-Noun naming (`Initialize-CnaGitHubSecrets.ps1`).
- **All GitHub Actions are pinned to a SHA digest.** `detect-secrets` runs at commit time and in
  CI, and **fails the build** on any finding not recorded in `.secrets.baseline` — which holds only
  hand-audited false positives, never a suppression dump. `gitleaks` also runs in CI but is
  advisory: it needs a paid licence on private repositories, so its job is `continue-on-error` and
  cannot fail a build. Do not read it as a gate.
- **Vendored agent configuration** under `.claude/`, `.agents/`, and `.codex/` is configuration,
  not project source. It is excluded from lint (see `pyproject.toml`) and from the documentation
  model, and it must never contain project-specific facts.

---

*Maintained by Saul Patino Jr. — AWS SA Professional | Azure Solutions Architect Expert*
