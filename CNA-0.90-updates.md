# CNA 0.90 Updates — Pre-Demo Review, Cleanup, and Polish Plan

Working document for the 0.9.0 push: a live VP/director demo of the web platform on
the Azure dev environment. This file records the full pre-demo review (UI/UX, code,
infra), the repository cleanup that precedes the polish work, the approved plan, and
the demo-day operational checklist. It is temporary by design — its contents graduate
to `CHANGELOG.md`, `TODO.md`, and the Wiki when 0.9.0 ships, and the file is then
removed (it is registered as an *optional* root document in
`scripts/validate_documentation_model.py`).

---

## 1. Repository cleanup (this PR)

Done before any polish work, per direction:

- **Recovered orphaned work.** Branch `claude/code-review-guidelines-ro2rcl` held five
  finished commits that were never merged (~3,400 lines): Azure discovery test
  coverage 22% → 85% and AWS discovery to 98% (T-408, both coverage omits removed),
  the detect-secrets audit that makes secret scanning a gating check (T-411), and the
  ten-provider assertion in workflow 100 (T-104). Those commits are carried in this
  PR; the branch is deleted after merge.
- **Fixed the recovered tests' hidden CI break.** The new Azure discovery tests import
  `azure.monitor.query` directly, but CI installed only `.[dev]` — they would have
  failed on their first CI run. The test job now installs `.[dev,enrichment]`
  (`.github/workflows/300-test-codebase.yml`), which is also more honest coverage:
  the enrichment paths are now actually exercised.
- **Verified clean:** full `pytest` green, coverage **87%** against the 80% gate;
  `npm audit` **0 vulnerabilities** (apps/cna-web); `pip-audit` **no known
  vulnerabilities**; `detect-secrets scan --baseline .secrets.baseline` clean.
  Note: GitHub's Dependabot/code-scanning alert list is not readable from this
  session's tooling — the audits above are the local equivalents, and the last
  recorded alert (deepmerge-ts, #30) was remediated in `CHANGELOG.md`. Give the
  repository Security tab one glance after merge to confirm zero pending.
- **Branch/PR state:** no open PRs; `main` plus one stale branch (absorbed here).
  After this PR merges, delete `claude/code-review-guidelines-ro2rcl`.
- **Documentation model:** this file is allowed at the root via a new
  `OPTIONAL_ROOT_DOCUMENTS` set in the guard script — optional, so CI does not start
  requiring it forever. Long-form documentation continues to live in the GitHub Wiki
  per the four-document model (Wiki write access is still blocked, `REVIEW.md` R-009).

---

## 2. Honest review findings (2026-08-28)

### 2.1 UI/UX — the priority

The app mixes **two design eras**. Half the pages are light-first with correct `dark:`
variants; the other half are dark-only. The app defaults to **light** (`#f2f1ed`
ground, white glass cards), so on a light-mode machine roughly 12 pages render their
headings in `#d3e5ec` on white — effectively invisible.

Worst offenders, in demo order of pain:

| Issue | Where |
|---|---|
| Executive **risk score is white-on-white** (`fill="white"`) | `components/charts/risk-gauge.tsx:40` (used on Presentation Overview + Report ch. 1) |
| ~40 invisible headings (`text-navy-100` on white) | connections, documents, findings, diagram, analysis, deliverables, client-deliverables, all 5 presentation pages |
| Copilot **input text invisible in dark mode** (`text-warm-*` classes don't exist; theme defines `warmgray`) | `copilot/page.tsx`, `components/copilot/chat-panel.tsx` (8 sites) |
| Copilot AI answers render as a wall of text (`prose` classes but `@tailwindcss/typography` not installed) | `chat-panel.tsx:126`, `package.json` |
| **Zero loading states** app-wide — heavy pages (Inventory 1,100 lines of server parsing) look frozen on click | entire `app/` — no `loading.tsx`, no Suspense |
| "New engagement" form is unstyled default Tailwind (gray/blue, no glass, no dark) | `engagements/new/page.tsx` |
| Every primary form button is **blue**, not brand teal | `components/ui/submit-button.tsx:22` |
| Raw Azure/exception text shown in the UI, and written into client-facing deliverables | `connections-panel.tsx:155`, `inventory/page.tsx:429`, 6 server actions, `lib/report-orchestrator.ts:98` |
| Charts tuned for dark panels only (near-black grids, slate labels, `sans-serif` not Aeonik) | `charts/chart-theme.ts`, `risk-gauge`, `maturity-radar`, `traffic-breakdown` |
| Literal `[VERIFY]` token visible 5× in FinOps copy; dead disabled "Future state" toggle; "AWS discovery is coming soon." string | `finops/page.tsx`, `diagram/page.tsx:60`, `credential-form.tsx:413` |
| Unguarded one-click deletes (no confirm) on deliverables ×5 | `deliverables/page.tsx:221`, `client-deliverables/page.tsx:145,216,247,284` |
| Findings page runs `prisma.finding.deleteMany()` **on every page render** (destructive dedupe on GET) | `findings/page.tsx:75-94` |

Genuinely strong already: `/dashboard` (bento grid, polished empty state),
engagement Overview (phase stepper), Inventory tables, the Findings filter/risk-matrix
interaction design, the deliverable progress poller, `status-badge.tsx`, and the
token/utility layer in `globals.css` (accessibility-annotated, print-aware). Colors
and fonts are good and **stay** — the fix is applying them consistently.

### 2.2 Code / Python

The demo path **works end-to-end**: web → `POST /discovery/start` (FastAPI) → Azure
discovery → findings + metrics in Postgres → dashboards → grounded copilot chat →
encyclopedia report. All tests pass (458 tests, 87% coverage).

Honest limits found:

- The **`cna` CLI is stubs** — every registered command prints "Phase X: TODO"; the
  real implementations exist but are not wired (`cna/cli/commands/*` vs
  `cna/cli/{discover,analyze,report,publish}.py`) and eight `EngagementStore`
  read-side methods are still missing (T-412). Do not demo the CLI.
- **AWS is not demoable** — web UI has no AWS path (schema fields exist, UI disabled).
- **Encyclopedia diagrams silently don't render** — the draw.io CLI is not installed
  in any image; the renderer degrades to a warning and omits the section.
- `apps/cna-worker` is a placeholder (hardcoded `sample-engagement`), not part of any
  flow.
- API inconsistencies: `/intake` and `/publish` return fake success; several error
  paths return HTTP 200 with an `error` body; raw SDK error text is echoed to
  callers; a missing `DATABASE_URL` makes discovery silently persist nothing.
- Version string mismatch: `cna --version` prints 1.0.0 while the project is 0.8.0b0.

### 2.3 Infra / demo readiness

> **Superseded on 2026-08-28 — read §5 first.** The dev environment described below no
> longer existed by the time this plan was executed: it was deleted out of band around
> 2026-07-21 (state backend included) and had to be rebuilt from nothing. The bullets
> here are preserved as the original review snapshot; §5 records what is actually
> deployed now.

- ~~Azure dev **exists and was healthy**, but the running containers are on an
  **8-week-old build** (deployed 2026-07-02; images built since were never deployed).
  None of this PR reaches the demo without a redeploy.~~ *(The environment was gone
  entirely — see §5.)*
- **13 of 14 workflows run on the self-hosted runner** — if it is offline there is no
  deploy, no fast-redeploy, no key sync. Single biggest operational risk.
- ~~Recommended redeploy path: merge → `200-build-images` → **`220-fast-redeploy`**
  (~2 min image swap; avoids the full 211 run, the Key Vault firewall dance, and the
  unresolved R-007 provider-registration blocker).~~ *(`220` requires existing Container
  Apps to update; with the environment destroyed it failed immediately and the full
  `000` → `100` → `211` path was required instead — see §5.)*
- **No docker-compose fallback** for the web stack (compose only runs the Python
  CLI). Local fallback is `npm run dev` + a real Postgres.
- The `/local-admin` break-glass works against Azure **only if** the
  `LOCAL_ADMIN_PASSWORD` secret was seeded — verify before relying on it. It does
  not work over plain-HTTP local runs (secure-cookie name mismatch).
- The AI Foundry path is the least-proven infra (dev account renamed to `-aif2`
  after a soft-delete collision; model deployment re-declared but unverified). Test
  copilot chat against the live environment before the demo.

---

## 3. Approved polish plan (starts after this PR merges)

> **Status (2026-08-28):** implemented — A, B, C, and D all landed in the polish PR,
> along with the three Copilot review fixes from PR #156 (README doc-count wording,
> stale CHANGELOG omit sentence, pyproject statement-count comment). The B-4 demo-day
> cheat sheet was delivered as a session file rather than a hosted artifact (the
> hosting step was blocked by policy because the page carries break-glass details).
> Out-of-scope items below remain tracked in `TODO.md`/`REVIEW.md`.

Scope agreed: fix **both** light and dark themes properly; fix behavioral hazards;
ship all four experience upgrades. Colors and fonts unchanged.

**A — Theme repair (both modes).** Fix the risk gauge (`currentColor`); convert the
~12 dark-only pages to dual-mode (mechanical `text-navy-100` →
`text-navy-800 dark:text-navy-100` pattern and equivalents for fills/borders); fix
Copilot's `text-warm-*` → `text-warmgray-*`; report cover logo `<picture>` swap;
make chart grid/label colors theme-aware; retire off-brand blue (submit button,
spinner, chips, help modal, auth error page, admin AI page, global error page).

**B — Experience upgrades.** (1) Glass skeleton `loading.tsx` covering the journey
pages + dashboard; (2) install `@tailwindcss/typography` so AI answers render with
real structure; (3) shared `EmptyState` component (modeled on Inventory's) replacing
~20 drifted empty states; (4) demo-day cheat sheet (private artifact).

**C — Behavioral hazards.** Confirmation dialogs on the 5 unguarded deletes; move the
Findings dedupe out of page render; friendly error messages at the 6 raw-passthrough
server actions and 2 raw mono dumps; neutral "section pending review" text instead of
raw errors inside generated deliverables; `[VERIFY]` becomes a footnote; remove the
dead Future-state toggle; soften the AWS coming-soon copy.

**D — API/Python hygiene.** Version string reconciled to 0.8.0b0; `/intake` and
`/publish` return 501 instead of fake success; error responses use real HTTP status
codes and sanitized messages; loud startup log when `DATABASE_URL` is unset.

**Out of scope for 0.9.0 demo (tracked honestly, not hidden):** ~~CLI command wiring +
the eight `EngagementStore` readers (T-412)~~ *(landed post-demo-scope: the readers are
implemented, the five guards removed, and the CLI registry is real — see `TODO.md`
T-412 and `CHANGELOG.md`)*, ~~AWS end-to-end~~ *(v1 landed post-demo-scope:
AWS credentials → connection test → discovery → findings work through the web
platform via the cna engine's AWS rules — see `CHANGELOG.md`; inventory/diagram/
FinOps views remain Azure-shaped)*, ~~draw.io rendering inside
the API image~~ *(landed post-demo-scope: both container images now install the
pinned draw.io CLI with a headless wrapper, verified end-to-end — see
`CHANGELOG.md`; the running dev environment gets it on the next
`200-build-images` → `220-fast-redeploy`)*, ~~the worker/publish story~~
*(landed post-demo-scope: `POST /publish` publishes a no-login, TTL-capped
client portal via the cna delivery_portal stack, with a "Client portal" panel
on the Client Deliverables page — see `CHANGELOG.md`. The cna-worker
placeholder is superseded by it and is a retirement candidate, pending the
owner's call)*, Aeonik
weight licensing, the self-hosted runner single point of failure, R-007/R-008.

---

## 4. Demo-day operational checklist

Before the demo, in order. **Steps 1–2 are done as of 2026-08-28 (§5); 3–8 remain and
all require the live environment.**

1. ~~Confirm the **self-hosted runner is online** (Settings → Actions → Runners).~~
   Done — it carried every workflow run on 2026-08-28.
2. ~~Merge this PR, then the polish PR; run `200-build-images`, then
   `220-fast-redeploy` to dev.~~ Done, by the longer path §5 describes: everything is
   merged, `200` published `sha-11eaa7e`, and `211` deployed it to a rebuilt dev.
3. Hit the dev Front Door URL and `/api/health`; sign in via Entra **and** verify
   `/local-admin` accepts the break-glass password.
   **URL:** `https://cna-dev-scus-afd-ep-dqh0gxcffjcthpbj.a01.azurefd.net`.
   The break-glass check matters more than usual now: the environment is new, so
   confirm `LOCAL_ADMIN_PASSWORD` actually seeded into the rebuilt Key Vault.
4. Pre-run a full Azure discovery on the demo engagement; confirm findings and
   metrics populate. **Not optional this time** — the rebuilt environment has a new,
   empty database, so there is no pre-existing engagement, discovery, or finding
   anywhere in the platform.
5. Generate the **Interactive Assessment** deliverable so the Presentation section
   is not an empty state.
6. Test one copilot chat question against live (exercises the Foundry path).
   **Highest-risk remaining step.** The deployment evidence records
   `foundry_private_dns_validation` and `foundry_managed_identity_inference` as
   `required` — hardcoded markers that no CI step ever flips, meaning the Foundry path
   is verified by a human or not at all. If chat fails, the fallback is to demo
   everything else; nothing outside Copilot depends on it.
7. Set the demo machine's OS theme deliberately (after the polish PR, both modes are
   safe; before it, use dark).
8. Demo path: Dashboard → Engagement Overview → Inventory → Findings → FinOps →
   Copilot → Report (Book Mode) → Deliverables.
   **Avoid:** ~~anything CLI, the AWS tab, encyclopedia architecture diagrams,~~ FastAPI
   `/docs`. *(The CLI, the AWS tab, and the encyclopedia diagrams all became real in the
   post-demo-scope work in §3 and now ship in the deployed images — they are demoable,
   though none has been exercised against this live environment yet.)*

---

## 5. Dev environment rebuild and deployment (2026-08-28)

The demo environment described in §2.3 did not exist when the time came to deploy to it.
This section is the record of what happened and what is standing now.

### 5.1 What was wrong

`350-drift-dev` had been failing every day since **2026-07-21** with
`ResourceGroupNotFound: rg-cna-dev-scus-tfstate` — the *Terraform state* resource group.
The workload side was gone too (`220-fast-redeploy` failed with "The containerapp
'cna-dev-scus-ca-api' does not exist"). No teardown workflow ran in that window, so the
resource groups were deleted directly in the subscription, out of band — consistent with
a sandbox cost sweep. The last successful deploy was 2026-07-02.

Because the state backend went with it, recovery was not a redeploy but a from-scratch
provision: `000-bootstrap-backend` → `100-validate-prereqs` → `211-deploy-azure-split`.

### 5.2 What that exposed: the least-privilege permission model was incomplete

The environment SP's roles are RG-scoped least-privilege (deliberately — see the
bootstrap script's comments). Every grant it held had been created *against the old
environment* and died with it, and the first full apply since that shrink surfaced, one
failure at a time, six things the model never actually covered. All six are now codified
in `scripts/Initialize-CnaGitHubSecrets.ps1`, so a future rebuild needs **no manual
commands**:

| Gap | Fix | PR |
|---|---|---|
| `211` ran `az provider register` — a subscription-level action the RG-scoped SP cannot perform (`REVIEW.md` → R-007's exact class) | Step verifies registration read-only; all four Terraform roots set `resource_provider_registrations = "none"` | #166 |
| `terraform init` could not read the tfstate storage account (it lives in the `-tfstate` RG, outside the workload RG) | `Storage Account Contributor` scoped to that account | #167 |
| The observability module reads the regional Network Watcher and parents the VNet flow log under it, in Azure's `NetworkWatcherRG` | Ensure that RG + watcher exist; `Network Contributor` scoped to it | #167 |
| Traffic Analytics validates the enabling principal against a wide `*/read` set at **subscription** scope | `Reader` at subscription scope | #168 |
| …and against non-read actions (workspace `sharedkeys/action`, data-collection rules/endpoints) at the same scope | `CNA Traffic Analytics Enabler` custom role, eight actions | #169 |
| Attaching the user-assigned identity to Container Apps needs `userAssignedIdentities/assign/action`, which Managed Identity *Contributor* lacks | `Managed Identity Operator` | #171 |
| The migration step creates a Container Apps **Job** (`Microsoft.App/jobs/*`), a separate resource type | `Container Apps Jobs Contributor` | #172 |

Two further blockers were one-time artifacts of the state loss, not permission gaps: two
`github_actions_environment_variable` resources that outlived the state (deleted so
Terraform could recreate them with the new Front Door hostname), and the four Key Vault
secrets that came back with the vault when `recover_soft_deleted_key_vaults` recovered it
from soft-delete — imported via #170
rather than deleted, since purge protection would have wedged the names for 90 days. (The
pull-request numbers in this section are the original repository's, `Work-Cloud_Network_Assessment`,
which is deleted — core `REVIEW.md` → R-014.)

### 5.3 What is deployed

`211 · Deploy Azure Platform (Split)` run **33169632082**, all jobs green, evidence in
`.deployment-catalog/dev/33169632082.json`:

- **URL:** `https://cna-dev-scus-afd-ep-dqh0gxcffjcthpbj.a01.azurefd.net`
- **Images:** `api-`/`web-`/`worker-`/`migrator-sha-11eaa7e` — the build carrying every
  §3 item (CLI readers, draw.io rendering, AWS end-to-end, portal publishing)
- **Health:** `healthy`, origin health 100%, private-endpoint approval passed, canary and
  staged promotion passed
- **Database:** new and empty; the migrator applied the full schema including the two
  migrations added in §3 (`20260828000014_aws_credentials`,
  `20260828000015_portal_publication`)

### 5.4 Standing risks this surfaced

1. **The sweep can recur.** Nothing prevents the same out-of-band deletion. The recovery
   procedure is now one script plus two workflows, but the environment is not protected —
   consider a resource lock or an exclusion from whatever sweeps the sandbox.
2. **`350-drift-dev` was failing daily for five weeks and nobody noticed.** The signal
   that would have caught the deletion the same day existed and went unread. Drift-check
   failures need somewhere to land.
3. **The Foundry path is still unverified** — see §4 step 6.
