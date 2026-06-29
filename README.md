# Cloud Network Assessment (CNA) Platform

[![CI](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/300-test-codebase.yml/badge.svg)](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/300-test-codebase.yml)
[![Release](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/310-release-version.yml/badge.svg)](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/actions/workflows/310-release-version.yml)

A CNA-branded, multi-user web platform for cloud network assessments across AWS and Azure.
Analysts run network discoveries, AI-powered analysis, and generate presentation-ready deliverables
including an encyclopedia-grade network report. Clients receive deliverables through a
time-limited authenticated portal. Deployed as three Azure Container Apps behind Azure Front Door,
backed by PostgreSQL and authenticated via Microsoft Entra ID.

> **Current status — 0.8 beta, June 2026:** Code, Terraform, workflows, ADFs, changelog, and GitHub Wiki are aligned on `main`. The remaining beta gate is live Azure execution through the numbered GitHub Actions workflows: prerequisite validation, dev deploy, Entra redirect update, runtime validation, and customer-like beta acceptance.

---

## Platform Status

| Area | Status | Notes |
|---|---|---|
| Platform foundation + CLI | ✅ Beta-ready | Python `cna` package |
| Azure discovery engine | ✅ Beta-ready | VNet, peerings, gateways, firewall, NSG, UDR, flow logs |
| AWS discovery stubs | ✅ Beta-ready | VPC, TGW, security groups |
| AI analysis engine | ✅ Beta-ready | Azure OpenAI (gpt-chat-latest) via managed identity, Terraform-managed |
| Web platform (Next.js) | ✅ Beta-ready | Entra ID auth, engagement workflow |
| CNA visual system | ✅ Merged | Navy/teal palette, Aeonik font, SVG brand assets |
| East-West / North-South taxonomy | ✅ Merged | `traffic_direction` on all findings |
| FinOps signals (AZ-COST-001–005) | ✅ Merged | Orphaned PIPs, idle gateways, oversized SKUs, NAT/FW waste |
| BC/DR signals (AZ-BCDR-001–005) | ✅ Merged | Zone redundancy, active-active, single-gateway gaps |
| Topology classifier | ✅ Merged | mesh / hub_spoke / vwan / isolated |
| Future-state Draw.io | ✅ Merged | Recommended topology diff, dashed bright-teal new resources |
| Stat Masters pivot layer | ✅ Merged | PowerBI-style aggregation, TanStack pivot grid |
| Encyclopedia report | ✅ Merged | 6-chapter, Condensed + Expanded editions, WeasyPrint PDF |
| Grounded copilot chat | ✅ Merged | Azure Foundry, stat-master context, citation chips |
| Frontend UX journey (8 steps) | ✅ Merged | Traffic, FinOps, Resilience, Discovery, Book Mode pages |
| CAF naming convention | ✅ Merged | `cna-[env]-[region_short]`, single workload RG per env |
| Teardown workflow (220) | ✅ Merged | `DESTROY`-gated, optional state wipe |
| CI — lint/test | ✅ Passing | ruff, pytest 3.13 + 3.14, Docker build smoke |
| Repository hygiene | ✅ Clean | No open GitHub PRs or Issues as of 2026-06-16 |
| Azure deployment | ⏳ Beta validation pending | Live workflow execution and customer-like validation remain |

---

## Architecture

### Container topology

```
                    ┌──────────────────────────────────────────┐
                    │          Azure Front Door Premium         │
                    │    WAF · CDN · TLS · Custom Domain (opt.) │
                    └─────────────────────┬────────────────────┘
                                          │ HTTPS
                    ┌─────────────────────▼────────────────────┐
                    │        cna-[env]-[region]-ca-web          │
                    │        Next.js 19 / React 19              │
                    │  • Entra ID login (NextAuth v5)           │
                    │  • 8-step engagement journey              │
                    │  • Book Mode encyclopedia report          │
                    │  • Copilot chat panel (grounded)          │
                    └───────────┬──────────────────┬───────────┘
                                │ internal         │ Prisma ORM
              ┌─────────────────▼────────┐  ┌──────▼─────────────────┐
              │  cna-[env]-[region]-ca-api │  │  cna-[env]-[region]-psql │
              │  FastAPI — internal only  │  │  PostgreSQL Flexible    │
              │  /metrics  /chat  /reports│  │  VNet-delegated         │
              └─────────────────┬─────────┘  └────────────────────────┘
                                │
              ┌─────────────────▼────────┐
              │  cna-[env]-[region]-ca-worker       │
              │  Python background worker │
              │  Discovery · AI analysis  │
              │  Report generation (PDF)  │
              └──────────────────────────┘
```

### Resource group layout (single RG per environment)

All resources — including AI Foundry (deployed to `eastus2`) — share one resource group:

```
rg-cna-dev-scus
├── cna-dev-scus-vnet               Virtual network
├── cna-dev-scus-cae                Container Apps Environment
├── cna-dev-scus-ca-api             Container App (API)
├── cna-dev-scus-ca-worker          Container App (worker)
├── cna-dev-scus-ca-web             Container App (web)
├── cna-dev-scus-psql               PostgreSQL Flexible Server
├── cna-dev-scus-kv                 Key Vault
├── cna-dev-scus-id                 Managed Identity
├── cnadevscusst                    Storage Account
├── cna-dev-scus-afd                Front Door profile
├── cnadevscusfdfp                  Front Door WAF policy
├── cna-dev-scus-nsg                Network Security Group
├── cna-dev-scus-log                Log Analytics workspace
├── cna-dev-scus-appi               Application Insights
├── cna-dev-eus2-aif                AI Foundry account
└── cna-dev-eus2-aif-proj           AI Foundry project
```

### Repository layout

```
apps/
├── cna-web/          Next.js 19 web platform (8-step journey, encyclopedia, copilot)
├── cna-api/          FastAPI — metrics, chat, reports, discovery routers
└── cna-worker/       Python background worker — discovery + report generation
cna/
├── core/             topology_schema · findings_schema · stat_masters · engagement
├── modules/          AWS + Azure discovery, FinOps signals, BC/DR signals, topology classifier
├── ai_engine/        Analysis engine, recommendation engine, chat agent (Foundry)
├── report_engine/    Encyclopedia renderer, WeasyPrint PDF, radar chart SVG
└── diagram_engine/   Draw.io generator, future-state model
infra/terraform/
├── environments/azure/dev/   Dev environment root module
├── environments/azure/prod/  Prod environment root module
└── providers/azure/          Reusable modules: ai, compute, database, identity,
                              security, storage, runtime
.github/workflows/            000–320 banded workflow sequence
GitHub Wiki                   All documentation, runbooks, blogs, and ADRs live in https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/wiki (no in-repo docs/ directory)
CHANGELOG.md                  Release history and deployment-gated follow-up context
scripts/                      bootstrap, validation, cleanup, and CI helper scripts
```

---

## Quick start

### Local development (web)

```bash
cd apps/cna-web
cp .env.example .env.local
# Fill in DATABASE_URL, NEXTAUTH_SECRET, AZURE_AD_* values
npm install
npm run db:migrate
npm run dev          # http://localhost:3000
```

### Local development (Python CLI)

```bash
pip install -e .[dev]
pre-commit install
cp .env.example .env
```

### Clean deployment (first time or after teardown)

```
1. Run `.\scripts\Initialize-CnaGitHubSecrets.ps1` — seed GitHub secrets/variables, create the workload RG using the standard naming convention, prepare tfstate backend resources, and dispatch workflow 000 bootstrap
   → The script creates the `CNA Assessment Tool` GitHub App and captures its generated private key; if that app name already exists, delete the existing app before rerunning the bootstrap
   → For Docker Hub, the script asks for `DOCKERHUB_NAMESPACE` and an organization access token saved as `DOCKERHUB_TOKEN`; the namespace is the Docker login identity
2. Let workflow 000 complete — initialize Terraform remote state and import the existing workload RG into state (one-time per environment)
3. Run workflow 100 — validate all secrets, variables, Azure OIDC
4. Push to main   — workflow 200 auto-builds the CLI plus all three app container images
5. Run workflow 210 (environment: dev) — Terraform apply (~20 min)
   → Copy Front Door hostname from outputs
   → Workflow 210 now updates `CNA_NEXTAUTH_URL`, `KEY_VAULT_NAME`, and `APPLICATION_INSIGHTS_NAME`
   → Workflow 210 also syncs the Entra app home page URL and redirect URI to the Front Door hostname
   → Re-run 210 to apply updated NextAuth URL
6. Navigate to https://<frontdoor-hostname> — sign in with Entra ID
```

To wipe an environment and redeploy clean:

```
1. Run workflow 220 — type DESTROY to confirm teardown
2. Leave `delete_drifted_resources=false` on the first run and review the cleanup preview
3. Re-run workflow 220 with `delete_drifted_resources=true` only after confirming the preview lists only CNA-owned targets
4. Keep `destroy_tfstate_backend=false` unless intentionally resetting Terraform state
5. Follow deployment steps above
```

---

## CI/CD workflows

| File | Trigger | Purpose |
|---|---|---|
| `000-bootstrap-backend.yml` | Manual (one-time per environment) | Creates workload RG, provisions tfstate backend in a separate convention-based RG, imports app RG into state |
| `100-validate-prereqs.yml` | Manual | Validates all secrets, variables, OIDC |
| `110-sync-keys.yml` | Manual | Pulls Key Vault secrets → `.env` artifact |
| `120-fast-redeploy.yml` | Manual | Fast image update via `az containerapp update`, auto-targeting the workload RG from repo variables |
| `200-build-images.yml` | Push to `main` | Builds + pushes cna, cna-api, cna-worker, cna-web, and cna-migrator to Docker Hub |
| `210-deploy-azure.yml` | Manual + nightly | Terraform plan → apply → health verification |
| `220-teardown.yml` | Manual (`DESTROY`) | Full environment teardown with safety gate |
| `300-test-codebase.yml` | Push/PR to `main` | Secret scan → ruff lint → pytest → Docker smoke |
| `310-release-version.yml` | `git tag v*.*.*` | Tags Docker Hub CLI image + creates GitHub Release |
| `320-publish-portal.yml` | Manual | Delivers reports to client portals from the CLI image, with artifact-backed engagement content and Azure/AWS storage support |

---

## Design contracts (enforced in code)

| DD | Contract | Enforced in |
|---|---|---|
| DD-002 | `observed_state` = discovered fact only | `ObservedStateEnforcer` |
| DD-003 | Findings and recommendations are separate paths | `AnalysisEngine` vs `RecommendationEngine` |
| DD-008 | AI engine reads from store only | `AnalysisEngine` |
| DD-009 | `review_complete=True` required before PDF render | `RenderPipeline._enforce_review_gate()` |
| DD-013 | Deliverable staleness via SHA-256 checksum | `DeliverableManifest` |
| DD-019 | 90-day retention enforced | `RetentionEngine.check()` |

---

## Security

- All GitHub Actions pinned to SHA digest
- `gitleaks` + `detect-secrets` on every commit and CI push
- Containers run as non-root (uid 1001)
- OIDC for all CI/CD cloud credentials — no long-lived keys
- Azure release gated by direct Azure Monitor + App Insights evidence
- Encyclopedia/branded reports flagged `[REVIEW REQUIRED]` before client delivery
- Cost estimates in FinOps findings flagged `[VERIFY]` for analyst review

---

*Maintained by Saul Patino Jr. — AWS SA Professional | Azure Solutions Architect Expert*
*CNA Platform · June 2026*
## Azure Notes

- Container Apps creates a separate Azure-managed infrastructure resource group for the managed environment. This repo now names it deterministically as `rg-cna-<environment>-<region_short>-cae-managed`, for example `rg-cna-dev-scus-cae-managed`.
- This managed RG is expected and separate from the workload RG. It contains Azure-managed infrastructure such as the Container Apps environment load balancer and public IP.
- The Terraform state backend remains separate in `rg-cna-<environment>-<region_short>-tfstate` to avoid backend/self-destroy lifecycle problems.
- The subscription must have `Microsoft.AlertsManagement` registered before `210` so Application Insights smart-detection alert deployment does not fail.
- Workflow `210-deploy-azure.yml` syncs the Entra app home page URL and redirect URI from the current Front Door hostname after Terraform apply.
