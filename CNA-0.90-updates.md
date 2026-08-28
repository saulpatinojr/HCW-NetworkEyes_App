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

- Azure dev **exists and was healthy**, but the running containers are on an
  **8-week-old build** (deployed 2026-07-02; images built since were never deployed).
  None of this PR reaches the demo without a redeploy.
- **13 of 14 workflows run on the self-hosted runner** — if it is offline there is no
  deploy, no fast-redeploy, no key sync. Single biggest operational risk.
- Recommended redeploy path: merge → `200-build-images` → **`220-fast-redeploy`**
  (~2 min image swap; avoids the full 211 run, the Key Vault firewall dance, and the
  unresolved R-007 provider-registration blocker).
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

**Out of scope for 0.9.0 demo (tracked honestly, not hidden):** CLI command wiring +
the eight `EngagementStore` readers (T-412), AWS end-to-end, draw.io rendering inside
the API image, the worker/publish story, Aeonik weight licensing, the self-hosted
runner single point of failure, R-007/R-008.

---

## 4. Demo-day operational checklist

Before the demo, in order:

1. Confirm the **self-hosted runner is online** (Settings → Actions → Runners).
2. Merge this PR, then the polish PR; run `200-build-images`, then
   `220-fast-redeploy` to dev.
3. Hit the dev Front Door URL and `/api/health`; sign in via Entra **and** verify
   `/local-admin` accepts the break-glass password.
4. Pre-run a full Azure discovery on the demo engagement; confirm findings and
   metrics populate.
5. Generate the **Interactive Assessment** deliverable so the Presentation section
   is not an empty state.
6. Test one copilot chat question against live (exercises the Foundry path).
7. Set the demo machine's OS theme deliberately (after the polish PR, both modes are
   safe; before it, use dark).
8. Demo path: Dashboard → Engagement Overview → Inventory → Findings → FinOps →
   Copilot → Report (Book Mode) → Deliverables.
   **Avoid:** anything CLI, the AWS tab, encyclopedia architecture diagrams, FastAPI
   `/docs`.
