# Changelog

All notable changes to the Cloud Network Assessment (CNA) Platform will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- Added Architecture Decision Records under `docs/adr/` (0001–0005) covering the Anthropic removal, smoke-test removal, Entra redirect-URI ownership, Key Vault network hardening target, and the container image-pull strategy.
- Made the Foundry/AIServices account region configurable via a `foundry_location` workload variable (default `eastus2`) instead of a hardcoded literal.
- Wired live MCP endpoint defaults for Azure and AWS recommendation enrichment through Terraform variables, `.env.example`, and the existing GitHub variable bootstrap flow.
- Added streamable HTTP JSON-RPC tool-call support for the Azure and AWS MCP clients while preserving offline recommendation fallback when endpoints are unavailable.
- Extended CISA ZTMM v2 mappings for AWS WAF, Azure Application Gateway WAF, and Azure Front Door WAF findings into the `Applications and Workloads` pillar.
- Added regression coverage for live MCP JSON-RPC request shaping and WAF `Applications and Workloads` framework mappings.

### Fixed
- Fixed Key Vault Firewall Circumvention in `210-deploy-azure.yml` by dynamically adding/removing the GitHub runner's public IP.
- Fixed Missing Azure CLI Version Pinning in `210-deploy-azure.yml` by injecting an installation step.
- Removed fragile Private IP guessing script since Terraform now natively manages the PostgreSQL private DNS zone.
- Replaced pipeline `gh variable set` mutation with the Terraform GitHub Provider for managing repository variables.
- Removed out-of-band Key Vault certificate import workflow step since certificates are now rotated natively in Terraform.

### Changed
- Consolidated the active task list into this changelog and deployment workflow validation. Live Azure prerequisite, image build, deploy, runtime, teardown, beta acceptance, and cost/footprint checks are now validated through the numbered GitHub Actions workflows and deployment evidence rather than a local TODO file.
- Aligned MCP configuration defaults on `https://mcp.azure.com`, `https://aws-mcp.us-east-1.api.aws/mcp`, and `streamable-http` transport.

### Removed
- Removed the Anthropic / Foundry-Claude inference path end-to-end (#100): the `foundry-claude` engine and its wire format in `apps/cna-web/lib/ai-engine.ts` and `cna/ai_engine/chat_agent.py`, the `foundry_claude_*` Terraform variables/outputs and `FOUNDRY_CLAUDE_*` container env vars (dev + prod), and the `FOUNDRY_CLAUDE_*` references in `.env.example`, the bootstrap script, and the drift/sync workflows. Azure OpenAI (`gpt-chat-latest`) is now the only supported engine. See `docs/adr/0001`.
- Removed the Foundry private-access smoke test (#98/#99): `scripts/ci/validate_foundry_private_access.sh`, its `211-deploy-azure-split.yml` step, and the associated evidence wiring. See `docs/adr/0002`.
- Removed the deploy-time "Sync Entra app web URLs" step (#101); the NextAuth redirect URI is owned by the Graph-capable bootstrap script on the application object, keeping the deploy identity least-privilege. See `docs/adr/0003`.
- Removed `TODO.md` after migrating completed work and deployment-gated follow-up context into the changelog.

---

## [0.8.0-beta] - 2026-06-16

### Added
- Added Azure Front Door Premium private-origin hardening, private endpoint approval automation, Azure Firewall egress control, subnet-specific NSGs, centralized diagnostics, VNet flow logs, and Azure AI Foundry private access validation gates.
- Added network security ADFs for edge ingress, east-west segmentation, north-south egress, private PaaS connectivity, centralized logging, Front Door private origin, private endpoint approval automation, and virtual network flow logs.
- Added post-deploy Foundry validation from the web Container App to verify private DNS resolution and managed-identity inference.

### Changed
- Changed the project release posture from `1.0.0` to `0.8 beta` while beta validation remains open.
- Updated Terraform, workflows, and documentation to use `cna-*` naming, separate tfstate resource groups, and GitHub Secrets/Variables as the deployment source of truth.
- Updated the AI runtime decision model so Foundry Claude is the Terraform-managed private provider and Azure OpenAI remains optional and out-of-band unless promoted to a first-class Terraform-managed provider.
- Merged or manually landed all open Dependabot PRs and closed the remaining conflicted PRs after their exact dependency updates reached `main`.
- Confirmed GitHub has no open PRs and no open Issues for final beta sync.

### Validation
- `npm ci`, `npx prisma generate`, and `npm run build` passed after dependency updates.
- Terraform validation passed for Azure `dev` and `prod` after network hardening changes.
- Live Azure beta validation is handled by the numbered GitHub Actions deployment workflows and deployment evidence artifacts.

---

## [1.0.0-prep] - 2026-06-15

### Changed
- Standardized active Azure deployment naming on `cna-*` resources with `rg-cna-<env>-<region>` workload resource groups.
- Updated Terraform workload resource group naming and generic CNA tag defaults for customer deployments.
- Aligned deployment, workflow, cleanup, and secrets documentation with GitHub Secrets/Variables as the source of truth.
- Migrated the documentation content set to the GitHub Wiki with generated table-of-contents sections.
- Migrated ADRs to the GitHub Wiki, consolidated remaining gap/footprint notes into the release documentation, and removed obsolete local audit artifacts.

---

## [1.0.0] - 2026-05-28

### Added
- **AWS Provider Expansion (Phase G)**: Added AWS Network Firewall and WAF v2 collectors; rules `AWS-NET-012` and `AWS-NET-013` are now live.
- **CISA ZTMM v2 Framework Mappings**: All 30 rule emissions now include CISA Zero Trust Maturity Model v2 pillar and control mappings.
- **Defender for Cloud Recommendations**: Added `_collect_defender_assessments()` and mapped defender assessments on the unified topology.
- **App Gateway Capacity Metrics**: Collector #9 in `_collect_network_metrics` and rule `AZ-NET-019` are now active.
- **Client Portal Hardening**: Implemented `deleteBlob()`, `generateSasUrl()`, and `cleanupExpiredDeliverables()` to secure the delivery pipeline.
- **Active Roadmap Priorities**: Integrated the following future tasks into the roadmap:
  - MCP integration
  - Draw.io integration
  - AWS assessment rules expansion
  - UI Update for new badging
  - Replatform to AWS

### Changed
- **Sprint 5 WCAG 2.1 / W3C / OWASP Audit Mitigation**: Resolved all 47 findings across the Next.js frontend:
  - **Accessibiity (WAI)**:
    - [WAI-01] Added `aria-hidden` and `aria-label` tags to navigation SVG icons.
    - [WAI-02] Replaced `title` attributes with descriptive `aria-label`, `aria-expanded`, and `aria-controls` on the sidebar toggle.
    - [WAI-03] Replaced the custom `sp-help-modal.tsx` with a fully accessible native dialog modal.
    - [WAI-04/05] Added `aria-expanded` and `aria-controls` to findings group headers and instances rows.
    - [WAI-06] Replaced label-caps `<p>` elements with semantic `<h2>`/`<h3>` headings.
    - [WAI-07] Added `<caption>`, `scope="col"`, and `scope="row"` markup to risk matrix tables.
    - [WAI-08] Added non-color indicators (border/underline) and `aria-pressed`/`aria-checked` to severity filter toggle buttons.
    - [WAI-09] Fixed color contrast for `text-navy-400` to exceed 4.5:1 ratio on light and dark mode.
    - [WAI-10] Added global `focus-visible` ring indicators to `globals.css` for interactive components.
    - [WAI-11] Implemented `role="progressbar"` and `aria-valuenow` on discovery progress bars.
    - [WAI-12] Fixed `<details>`/`<summary>` accessibility bugs for Firefox and NVDA compatibility.
    - [WAI-13] Injected descriptive `aria-label` properties on proportional severity segments.
    - [WAI-14] Added `(opens in new tab)` accessibility text to links with `target="_blank"`.
    - [WAI-16] Added a hidden skip-to-main-content skip link for screen readers.
    - [WAI-17] Added appropriate `aria-label` descriptors to sidebar `<aside>` and `<nav>` landmarks.
    - [WAI-19] Spinner SVGs marked with `aria-hidden="true"` and paired with `sr-only` live regions.
    - [WAI-20/21/23] Forms and selects updated with standard `autocomplete` fields, thicker focus rings, and step indicators.
  - **Security (OWA)**:
    - [OWA-01] Configured nonce-based Content Security Policy (CSP) headers in `next.config.ts` using middleware.
    - [OWA-02] Added per-user API rate limiting (5 requests / 60s) to Server Actions (AI generation and discovery triggers).
    - [OWA-03] Wrapped `deleteEngagement` trigger inside standard `<form>` to enforce CSRF validation.
    - [OWA-04] Restricted NextAuth development-grade cookie fallbacks to non-production environments.
    - [OWA-05] Mitigated timing attacks on the discovery-jobs API by rejecting unauthenticated requests before database lookup.
    - [OWA-06] Implemented magic-byte validation (validating headers, not just extensions) for uploaded documents.
    - [OWA-08] Hardened `lib/auth.ts` to enforce `useSecureCookies: true` in production.
    - [OWA-09] Replaced default native `confirm()` triggers with custom accessible modal dialog confirmation elements.
    - [OWA-10] Added Zod schemas to parse and validate database progress logs.
    - [OWA-12] Mapped raw Azure SDK exception strings to user-friendly messages.
    - [OWA-13/14] Expanded security headers (modern `Permissions-Policy` controls and Strict-Transport-Security preload directives).
  - **W3C Standards (W3C)**:
    - [W3C-01/12] Replaced dual logo instances with unified `<picture>` tag wrapping `next/image` to prevent CLS and duplicate requests.
    - [W3C-02] Appended `aria-hidden="true" focusable="false"` to all decorative SVGs.
    - [W3C-03] Registered standard CSS scrollbar styles side-by-side with webkit engines.
    - [W3C-04] Scoped font-smoothing parameters to preserve ClearType rendering on Windows.
    - [W3C-05] Injected root `<meta name="color-scheme">` tags to prevent flash on load.
    - [W3C-06] Added `@supports (backdrop-filter: blur(1px))` queries for Firefox glass backfalls.
    - [W3C-08] Augmented TypeScript typings module to handle custom CSS property `--bar-pct`.
    - [W3C-09/10] Set `rel="noopener noreferrer"` and unique `aria-label` tags on all deliverable link forms.
- **Sprint 4 Hardening**:
  - Wired Spoke-VNet peerings to emit `AZ-NET-005` if missing local gateways.
  - Configured `AZ-NET-006` rule to alert when subnets lack Flow Log logging.
  - Added FQDN resolution validation against RFC 1918 ranges for Private Endpoints.
- **Sprint 3 Hardening**:
  - Pinned `node:20-alpine` and `gitleaks-action` references in Dockerfiles and test actions to secure SHA digests.
  - Mapped Azure Front Door WAF Policies and added `AZ-NET-018` for Detection-mode WAF configs.
- **Sprint 2 Hardening**:
  - Collected live firewall rules, SNAT exhaustion levels, gateway bandwidth usage, and VNet IP utilization.
  - Hooked Azure Cost Management API and Log Analytics Traffic Analytics for east-west bandwidth tracking.
  - Integrated compliance mappings for HIPAA, FedRAMP, PCI-DSS, and ISO 27001.
- **Sprint 1 Hardening**:
  - Patched `_collect_private_endpoints()` IP collections and `vpn_client_pools` list manipulation bugs.
  - Implemented Spoke-to-Spoke firewall bypass checks (`AZ-NET-012`) and diagnostic settings checks (`AZ-NET-013`).

---

## [0.1.0] - 2026-04-14

### Added
- **Unified 3-Container Platform**:
  - `cna-web`: Next.js 15 frontend panel.
  - `cna-api`: FastAPI internal processing broker.
  - `cna-worker`: Python background tasks engine.
- **Terraform IaC modules**: Provisioning templates for all Azure networking, AI, databases, and container instances.
- **Automated Workflows (000–031)**: Checklists, OIDC credentials sync, fast-redeploy pipelines, and automatic variable updating.
- **OIDC Identity**: NextAuth v5 linked to Microsoft Entra ID with Analyst, Reviewer, Client, and Admin roles.
- **Sync Groups & Topology Merge**: Run isolated per-subscription discovery jobs; merge resources under one global assessment profile.
- **Unique Findings Count**: Deduplicated findings counting in the portal page.
- **Assessment Deliverables**: Supported 5 distinct deliverable documents, including full self-contained `COMPREHENSIVE_ASSESSMENT` HTML formats.
- **MS Learn Enrichment**: Injected live Microsoft Learn documentation matches into AI analysis pipelines.
- **Presentation Dashboard**: Radar charts, maturity indicators, compliance maps, and interactive topologies.

---
