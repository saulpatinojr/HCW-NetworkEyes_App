# TODO — engineering work queue

The authoritative engineering backlog for this repository. Every actionable engineering item
discovered anywhere in the repository lives here, ordered by phase and dependency so an engineer
can pick up work without rediscovering the findings.

Items requiring external input — an approval, an account, a credential, an access grant — belong
in [`REVIEW.md`](REVIEW.md), not here. Completed work is recorded in [`CHANGELOG.md`](CHANGELOG.md).

**Last reviewed:** 2026-08-17

| Phase | Theme | Items |
|---|---|---|
| [Phase 1](#phase-1--critical-fixes) | Critical fixes — repository states something untrue | T-101 – T-104 |
| [Phase 2](#phase-2--security-improvements) | Security improvements | T-201 – T-204 |
| [Phase 3](#phase-3--deployment-readiness) | Deployment readiness | T-301 – T-305 |
| [Phase 4](#phase-4--technical-debt) | Technical debt | T-401 – T-414 |
| [Phase 5](#phase-5--feature-enhancements) | Feature enhancements | T-501 – T-502 |
| [Phase 6](#phase-6--documentation-improvements) | Documentation improvements | T-601 – T-608 |

---

## Phase 1 — Critical fixes

Work in this phase corrects places where the repository asserts something that is no longer true.
Each one actively misleads an engineer or a workflow run.

### T-101 — Workflow 212 fail-fast guard contradicts the AWS Terraform it guards

- **Priority:** High
- **Description:** `.github/workflows/212-deploy-aws-split.yml` fails every job with
  `"infra/terraform/providers/aws/* has no resources yet"`. That is no longer accurate: the eight
  AWS provider modules declare 90 resources between them (ai 3, compute 25, database 2,
  identity 16, observability 22, runtime 10, security 4, storage 8). The guard is correct that the
  stack must not be applied yet, but its stated reason is wrong — the real blocker is human
  account setup, not missing code.
- **Dependencies:** None to correct the message. Removing the guard entirely depends on
  `REVIEW.md` → R-001, R-002, R-003.
- **Recommended action:** Rewrite the three `::error::` messages to name the actual blocker
  (AWS account, state backend, and OIDC deploy role — `REVIEW.md` R-001/R-002/R-003) and to point
  at `REVIEW.md` rather than only at issue #110. Keep the fail-fast behaviour until those
  blockers clear.
- **Status:** Done — the header comment and all three `::error::` messages in
  `212-deploy-aws-split.yml` were rewritten to name the real blocker. They now state that the eight
  provider modules declare 90 resources (so this is not a missing-code problem), point at
  `REVIEW.md` R-001 (AWS account), R-002 (S3 state backend + DynamoDB lock table), and R-003 (OIDC
  deploy role in CI secrets) as the human-owned prerequisites, and cross-reference `TODO.md` T-501
  for the real implementation, keeping the issue #110 link as background rather than the sole
  pointer. Fail-fast behaviour and the three-job `policy-gates → plan → apply` shape are unchanged;
  each job still `exit 1`s. The `plan` and `apply` messages are now job-specific — naming the
  missing backend and the missing reviewed plan respectively — rather than three copies of one
  string. Recorded in [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** The guard jobs mirror `211-deploy-azure-split.yml`'s input
  contract and job shape on purpose — preserve that shape when the guard is replaced with real
  steps (see T-501), so the two clouds keep a single deploy interface.

### T-102 — `.env.example` points at a workflow number that does not exist

- **Priority:** Medium
- **Description:** `.env.example` line 6 says *"Workflow 110-sync-keys.yml can download a
  populated .env from Azure Key Vault as a 1-day artifact."* There is no `110-*` workflow; the
  Key Vault sync workflow is `340-sync-keys.yml`. An engineer following the hint finds nothing.
- **Dependencies:** None.
- **Recommended action:** Correct the reference to `340-sync-keys.yml`. While in the file, verify
  the other two workflow references it makes against `.github/workflows/`.
- **Status:** Done — `.env.example` lines 6 and 35 corrected (`110-sync-keys.yml` →
  `340-sync-keys.yml`; the variables comment now names the real consumers 000, 100, 211, 220,
  330–360). The suggested grep across `scripts/` and `.github/` found two further stale names in
  `scripts/Initialize-CnaGitHubSecrets.ps1` (`210-deploy-azure.yml` → `211-deploy-azure-split.yml`,
  `110-sync-keys.yml` → `340-sync-keys.yml`); both corrected. `.env.example` line 164's reference
  to workflow 320 was verified as valid. Recorded in [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** The workflow numbering was rebanded at some point (the 000/100/
  200/300 bands). Other stale numeric references may exist in scripts — grep for `\b0[0-9]{2}-`
  and `\b1[0-9]{2}-` across `scripts/` and `.github/` when fixing this.

### T-103 — Verify the ADR pages referenced by the changelog exist in the Wiki

- **Priority:** Medium
- **Description:** `CHANGELOG.md` previously claimed ADRs 0001–0005 were added under `docs/adr/`.
  That directory has never existed in this repository's git history — the `[1.0.0-prep]` entry
  records that ADRs were migrated to the GitHub Wiki. The changelog references have been corrected
  to name the Wiki, but the target pages have not been confirmed to exist.
- **Dependencies:** Wiki read access.
- **Recommended action:** Confirm ADR-0001 through ADR-0005 exist as Wiki pages (Anthropic
  removal, smoke-test removal, Entra redirect-URI ownership, Key Vault network hardening target,
  container image-pull strategy). Recreate any that are missing from the changelog entries that
  describe them, and link them from the Wiki home page.
- **Status:** Not started
- **Notes for future engineers:** The five ADR subjects are fully described in `CHANGELOG.md`
  under `[Unreleased]` → Added/Removed, so a missing page can be reconstructed from there without
  archaeology.

### T-104 — Add a `Microsoft.AlertsManagement` registration check to workflow 100

- **Priority:** Medium
- **Description:** Azure apply fails partway through if the subscription has not registered the
  `Microsoft.AlertsManagement` provider, and the failure surfaces roughly 20 minutes into a
  `211-deploy-azure-split.yml` run. Workflow `100-validate-prereqs.yml` validates secrets,
  variables, and OIDC but not resource-provider registration.
- **Dependencies:** `REVIEW.md` → R-007 (now closed — see Status).
- **Recommended action:** Add a registration-state assertion to `100-validate-prereqs.yml`,
  failing with a message that names the provider and points at `REVIEW.md` → R-007.
- **Status:** Done, but not as written — **the premise was stale, and the note below turned out to
  be the whole item.**
  1. **`Microsoft.AlertsManagement` is not needed and has not been for some time.** The split
     refactor removed alerting from the Azure roots: `infra/` contains no
     `azurerm_application_insights`, no `azurerm_monitor_smart_detector_alert_rule`, no
     `azurerm_monitor_metric_alert`, and no `azurerm_monitor_action_group`. The only monitor
     resource left is `azurerm_monitor_diagnostic_setting` (`Microsoft.Insights`). Both
     `azapi_resource` declarations resolve to namespaces already covered
     (`Microsoft.CognitiveServices/accounts/projects`,
     `Microsoft.Network/networkWatchers/flowLogs`). `REVIEW.md` → R-007 is closed on this basis —
     it was asking the subscription owner for something no longer required.
  2. **A provider check already existed** in `100-validate-prereqs.yml`, and already carried a
     comment saying AlertsManagement had been dropped. So the item as written was asking for a
     check that was there.
  3. **The real gap was coverage.** That check asserted `Microsoft.App` and `Microsoft.Insights`
     only — 2 of the 10 namespaces these roots actually need. `Microsoft.Cdn`,
     `Microsoft.CognitiveServices`, and `Microsoft.DBforPostgreSQL` in particular are commonly
     *not* registered by default on a fresh subscription, and each fails partway through apply
     exactly as R-007 described. The list is now derived from the declared resource types and
     covers all ten, declared once as `REQUIRED_PROVIDERS` with each namespace commented with the
     resources that require it.
  `Microsoft.Resources` and `Microsoft.Authorization` are deliberately excluded — they are
  registered on every subscription and cannot be unregistered, so asserting them is noise. The
  loop also distinguishes `Registering` (transient; wait and re-run) from `NotRegistered` (run
  `az provider register`), because telling someone to re-register a provider that is mid-flight is
  wrong advice. It reports every failing provider before exiting rather than stopping at the
  first. Verified with a stubbed `az` covering all three states.
- **Notes for future engineers:** Check whether any other provider registration is assumed by the
  Azure roots while adding this — the same class of late failure applies to every one of them.
  This note was the actual work. Keep `REQUIRED_PROVIDERS` in sync when adding a service; the
  workflow comment carries the `grep` that regenerates the resource-type list.

---

## Phase 2 — Security improvements

### T-201 — Consume the `github_deploy_role_arn` output in CI

- **Priority:** High
- **Description:** The `identity` module outputs `github_deploy_role_arn` for the role CI assumes
  via `AssumeRoleWithWebIdentity`. Nothing reads that output — CI trigger wiring was explicitly
  out of scope of the AWS code-generation work.
- **Dependencies:** `REVIEW.md` → R-003 (the role must exist and its ARN must be stored as a
  repository secret).
- **Recommended action:** Reference the stored secret from `212-deploy-aws-split.yml` using
  `aws-actions/configure-aws-credentials` with `id-token: write`, matching the OIDC-only
  credential policy used on the Azure side. No long-lived AWS keys.
- **Status:** Blocked on R-003
- **Notes for future engineers:** The deploy role's trust `sub` condition is scoped to
  `repo:<owner>/<repo>:*`. If the workflow is ever moved to a reusable workflow in another
  repository, that condition must be widened deliberately — it is the only thing preventing
  another repository from assuming the role.

### T-202 — Remove placeholder defaults from the identity module's GitHub variables

- **Priority:** Medium
- **Description:** `github_owner` and `github_repository` default to
  `<GITHUB_OWNER_PLACEHOLDER>` and `<GITHUB_REPO_PLACEHOLDER>` in
  `infra/terraform/providers/aws/identity/variables.tf` and
  `infra/terraform/environments/aws/{dev,prod}/workload/variables.tf`. These are the only literal
  placeholder strings committed anywhere in the AWS Terraform. A default that is syntactically
  valid but semantically wrong will apply successfully and produce a deploy role no one can
  assume.
- **Dependencies:** None.
- **Recommended action:** Drop the defaults so Terraform requires the values, or add a
  `validation` block rejecting any value containing `PLACEHOLDER`.
- **Status:** Done — all six placeholder defaults removed, making the variables required:
  `github_owner` and `github_repository` in
  `infra/terraform/providers/aws/identity/variables.tf` and in both
  `infra/terraform/environments/aws/{dev,prod}/workload/variables.tf`. No literal `PLACEHOLDER`
  string remains anywhere under `infra/`. The "make it required" option was chosen over a
  `validation` block because it is the stricter of the two — a validation rejecting `PLACEHOLDER`
  still permits an empty or wrong value, whereas an absent default makes Terraform refuse to plan.
  Verified safe: nothing supplied these from a default. The drift workflows (350/360) target the
  *Azure* roots, and the only workflow touching the AWS roots is 212, whose three jobs all fail
  fast before Terraform runs. `211-deploy-azure-split.yml` and both drift workflows already pass
  `-var="github_owner=..."` and `-var="github_repository=..."` explicitly — that is the pattern the
  AWS deploy path should follow when T-501 implements it. Recorded in
  [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** Everything else a human must supply is *not* a token in the
  source — account ID, partition, and region resolve from `data.aws_caller_identity.current`,
  `data.aws_partition.current`, and `var.aws_region`; backend settings arrive at
  `terraform init` via `-backend-config`; secrets arrive as `sensitive` variables at apply. Do not
  add new placeholder-string defaults; make the variable required instead.

### T-203 — Confirm no legacy OIDC thumbprint is reused

- **Priority:** Medium
- **Description:** The current `identity` module intentionally omits `thumbprint_list` on
  `aws_iam_openid_connect_provider.github` — AWS provider v5 validates GitHub's OIDC endpoint
  against its trusted CA store, so the legacy thumbprint is no longer required. The superseded
  `migrate/iam.tf` root contains an old placeholder thumbprint that must not be copied forward.
- **Dependencies:** Overlaps with T-401 (retiring `migrate/`).
- **Recommended action:** Verify no thumbprint appears in `infra/terraform/providers/aws/identity/`
  and add a short comment recording why it is absent, so a future reviewer does not "fix" the
  omission.
- **Status:** Done — verified and documented in code. `grep -rn thumbprint infra/` returns **only
  comment lines**: there is no `thumbprint_list` value anywhere under `infra/`, so nothing was
  copied forward. The legacy placeholder existed only in the superseded root, at
  `migrate/iam.tf:139` and `migrate/scripts/Initialize-Migration.ps1:97` — forty `f`s, never a real
  thumbprint — and is now gone from the tree with T-401 (recoverable from history at `7a6b1fa`).
  A short comment already existed above `aws_iam_openid_connect_provider.github`; it was expanded
  rather than duplicated, and now records three things a future reviewer needs: *why* the omission
  is correct (provider 5.x validates GitHub's endpoint against its own trusted CA store), that the
  `migrate/` placeholder must not be copied in, and — the part previously recorded only here in
  `TODO.md` — the one-provider-per-account constraint, with the concrete `terraform import` command
  to use when the target account already has one. That last point is the difference between a clean
  first apply and a failed one, so it belongs next to the resource rather than in the backlog.
  `terraform fmt -check -recursive` still passes and the file's LF endings are unchanged.
- **Notes for future engineers:** AWS permits exactly one GitHub OIDC provider per account. If the
  target account already has one, the module must import it rather than create it — a duplicate
  create fails the whole apply. This is now also stated in the module itself, which is where it will
  actually be read; keep the two in step if either changes.

### T-204 — Triage the 8 open Dependabot advisories on the default branch

- **Priority:** High
- **Category:** Security / dependencies
- **Description:** Pushing a branch during the 2026-08-17 review returned a GitHub advisory notice:
  *"GitHub found 8 vulnerabilities on saulpatinojr/Work-Cloud_Network_Assessment's default branch
  (7 high, 1 moderate)."* Nothing in `TODO.md` or `REVIEW.md` tracks dependency vulnerabilities, so
  these are currently unowned. The individual advisories were not readable from the review
  environment (no Dependabot access), so the affected packages and ecosystems are unconfirmed —
  the repository ships both a Python dependency set (`pyproject.toml`) and a Node one
  (`apps/cna-web/package.json`).
- **Dependencies:** None.
- **Recommended action:** Open
  [the Dependabot alerts page](https://github.com/saulpatinojr/Work-Cloud_Network_Assessment/security/dependabot),
  triage each of the 8 alerts, and record the outcome here — patch, pin, or an explicit accepted-risk
  note with a reason. Prioritise anything reachable from the web platform's request path. Check
  whether `.github/dependabot.yml` covers both ecosystems (`pip` and `npm`) and both lockfiles; if
  an ecosystem is unwatched, alerts for it will never be raised in the first place.
- **Status:** Done — remediated in the `apps/cna-web` npm tree; `npm audit` goes from 4 vulnerable
  packages (3 high, 1 moderate) to **0**, and `pip-audit` over `pyproject.toml` reports no known
  vulnerabilities, confirming the advisories were entirely Node-side as the notes below predicted.
  Fixes: `next` 16.2.11 → 16.3.1 and `eslint-config-next` to match (postcss path traversal,
  GHSA-6g55-p6wh-862q and its incomplete-fix follow-up); `postcss` floor raised to `^8.5.23`
  (resolves 8.5.26); `nanoid` 3.3.12 → 3.3.18 (infinite loop on zero/negative size);
  `brace-expansion` 1.1.16 → 1.1.18 and 5.0.7 → 5.0.9 (unbounded-expansion DoS, CVE-2026-14257 and
  its mitigation bypass). The two transitive packages are pinned through targeted `overrides`
  entries in `package.json` rather than a blanket tree refresh, per the CBTS standard of preferring
  pinned versions in security-sensitive dependencies. `.github/dependabot.yml` was checked as the
  recommended action asked: it already covers `pip`, `npm` (at `/apps/cna-web`), `github-actions`,
  and `docker`, so no ecosystem is unwatched. Verified with `npm ci --legacy-peer-deps`,
  `tsc --noEmit`, and a full `next build` (all routes compile). Recorded in
  [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Follow-up (same day):** Dependabot alert #30 — *"DeepmergeTS has stack exhaustion when merging
  recursive object graphs"*, GHSA-ggr8-5vv4-36mx / CVE-2026-40345, high, CVSS 4.0 8.2 — was raised
  after the work above and is now also fixed. It is the concrete instance of the caveat below:
  `npm audit` reported **0** while this advisory was live, because it was published the same day and
  the npm registry's advisory database had not yet picked it up. GitHub's advisory database is ahead
  of `npm audit`; treat a clean `npm audit` as necessary but not sufficient.
  `deepmerge-ts` reaches the tree only through `prisma` → `@prisma/config@6.19.3`, which pins it at
  **exactly** `7.1.5`, and the Prisma 6.20 prerelease still pins 7.1.5 — so no Prisma release
  resolves this and an `overrides` entry is the only route. Fixed to `^8.0.1` (patched in 8.0.0).
  Forcing a new major onto a dependency Prisma pins exactly is the risk here, so it was verified
  rather than assumed: both versions are ESM with identical `engines` (node >=16); `prisma generate`,
  `prisma version`, `prisma migrate deploy --help`, and `prisma validate` (with `DATABASE_URL` set)
  all succeed; `next build` is clean; and the advisory's own case — two objects self-referencing
  through identical property paths — merges without stack exhaustion on 8.0.1 while ordinary merges
  are unchanged.
- **Docker ecosystem (same-day follow-up):** both pinned base image digests were found stale against
  their tags and refreshed — `node:24-alpine` `a0b9bf06…` → `d32cdf61…` and `python:3.14-slim`
  `cea0e604…` → `ce407646…`, ten `FROM` lines across four Dockerfiles. This is the ecosystem neither
  `npm audit` nor `pip-audit` sees, so it was checked by resolving each tag's current digest from the
  registry and comparing. Note what that does and does not prove: a stale digest means the pin is
  behind, **not** that it carried a CVE — confirming that needs an image scan. The bump could not be
  build-verified locally (no Docker daemon in the review environment) and relies on CI's Docker build
  smoke test plus the existing `docker/scout-action` step. Image internals could not be inspected
  either: the registry's manifest endpoints are reachable through the agent proxy but blob fetches
  redirect to a CDN host it blocks, so the Node/Python patch levels inside the new images were not
  compared against the old ones.
- **GitHub Actions ecosystem: still unverified.** 14 distinct actions are SHA-pinned across the
  workflows. Whether those SHAs are current cannot be checked from an environment whose GitHub access
  is scoped to this repository, since it requires reading the action repositories. Treat this
  ecosystem as an open question, not as clean — it and Docker are the two places a Dependabot alert
  can hide from both auditors.
- **Notes for future engineers:** The alert *count* was never fully reconciled — the Dependabot REST
  API returns 403 for the automation token, so the alerts could not be enumerated and mapped
  one-to-one onto the advisories fixed here; alert #30 surfaced only because a human read the alerts
  page. Confirm that page is clear before closing this out; anything remaining is something
  `npm audit` and `pip-audit` do not see (a GitHub Actions or Docker base-image advisory, both of
  which Dependabot also watches).
  Two traps when regenerating this lockfile: (1) it is stored with **LF** endings while
  `package.json` is **CRLF**, and npm rewrites the lockfile as CRLF on this platform — convert back
  or the diff becomes the whole file; (2) regenerate with **npm 11+**, matching the `node:24-alpine`
  image, because npm 10 silently strips the `libc` fields that select the musl vs glibc native
  binaries for `@next/swc` and `@tailwindcss/oxide`. Also note `npm update` floats the entire tree —
  it pulled in 119 package changes including major transitive jumps (`immer` 10 → 11) — so prefer
  targeted `overrides` plus `npm install --package-lock-only` for security-only work.
  CI already runs a `pip-audit` job in `300-test-codebase.yml`,
  which covers the Python side — check whether that job is passing before assuming the Python
  dependencies are implicated. A green `pip-audit` alongside 7 high advisories would point at the
  Node dependency tree. Per CBTS engineering standards, prefer pinned versions over ranges when
  remediating security-sensitive dependencies.

---

## Phase 3 — Deployment readiness

Everything in this phase is gated on `REVIEW.md` blockers. The order below is the correct apply
order; do not reorder it.

### T-301 — Apply the AWS platform root (networking + VPC endpoints)

- **Priority:** High
- **Description:** The platform root `infra/terraform/environments/aws/{dev,prod}/platform/`
  creates the VPC, three-tier subnets, NAT, security groups, and nine VPC endpoints gated behind
  `var.enable_vpc_endpoints` (default `true`). It must be applied before the workload root, which
  consumes its outputs (VPC / subnet / security-group IDs).
- **Dependencies:** `REVIEW.md` → R-001, R-002. Blocks T-302.
- **Recommended action:** `terraform init` with the four `-backend-config` values from R-002, plan,
  review, apply. Confirm all nine endpoints come up before proceeding.
- **Status:** Blocked on R-001, R-002
- **Notes for future engineers:** The nine endpoints and why each exists —

  | Endpoint | Type | Purpose |
  |---|---|---|
  | S3 | Gateway | Free; routes S3 traffic through the VPC |
  | DynamoDB | Gateway | Free; Terraform state locking |
  | Secrets Manager | Interface | ECS task secret injection |
  | CloudWatch Logs | Interface | ECS `awslogs` driver |
  | ECR API | Interface | Container image pulls |
  | ECR Docker | Interface | Container image pulls |
  | Bedrock Runtime | Interface | AI inference calls |
  | STS | Interface | IAM role credential exchange |
  | X-Ray | Interface | Trace segment submission |

  A dedicated security group (`${name_prefix}-sg-vpce`) allows HTTPS from the app and database
  tiers. The two Gateway endpoints are free; the seven Interface endpoints carry an hourly charge
  per AZ — that is the deliberate trade for keeping service traffic off the NAT gateway.

### T-302 — Apply the AWS workload root in module order

- **Priority:** High
- **Description:** The workload root composes the eight provider modules. They have a required
  order because of IAM and secret dependencies.
- **Dependencies:** T-301, plus `REVIEW.md` → R-004, R-005, R-006.
- **Recommended action:** Apply in this order:
  `identity → storage → database → observability → ai → runtime → compute → security`.
  The workload root reads platform outputs through variables populated from the platform state.
- **Status:** Blocked on T-301
- **Notes for future engineers:** The platform state and workload state are separate state files
  by design, mirroring the Azure split. Cross-state values move as explicit variables, not remote
  state data sources — keep it that way; it is what makes the two roots independently
  destroyable.

### T-303 — Confirm Bedrock model IDs resolve in the target region

- **Priority:** Medium
- **Description:** The `ai` module's `model_ids` variable carries defaults that may not exist in
  every region. A model ID that is unavailable regionally fails at invoke time, not at apply time.
- **Dependencies:** `REVIEW.md` → R-005 (model access opt-in must be done first, otherwise the
  availability check reports a false negative).
- **Recommended action:** After the opt-in, list available foundation models in the deploy region
  and reconcile against the module defaults. Adjust the variable rather than the module.
- **Status:** Blocked on R-005
- **Notes for future engineers:** If the platform keeps calling the external Azure OpenAI endpoint
  from AWS — as the superseded `migrate/` root does today — the `ai` module can be disabled
  entirely and the endpoint stays an environment variable. That is a fallback, not the target
  design.

### T-304 — Log Analytics workspace state migration, for already-deployed Azure environments only

- **Priority:** Low
- **Description:** The Log Analytics workspace (`<name_prefix>-log`) moved from the `compute`
  module (workload state) to the platform landing zone, removing a cross-state dependency. The
  code change is done, but in an environment that was already deployed the resource still
  physically lives in workload state. Applying without migrating state first makes workload want
  to **destroy** the workspace and platform want to **create** it — which deletes all historical
  log data.
- **Dependencies:** Only applies to an environment already deployed with the old layout. As of the
  last check no environment was deployed, so this is a no-op for the initial rollout.
- **Recommended action:** Follow the runbook below before the next apply in any affected
  environment. Run it **once per environment** (dev, then prod).
- **Status:** Not started — not currently applicable
- **Notes for future engineers:**

  **Why the workspace moved.** The workspace used to be created by the `compute` module, which
  lives in workload state. It moved to the platform landing zone so that platform-owned resources
  (firewall, NSGs, VNet flow logs) send diagnostics to a workspace in the same state that creates
  them, removing the cross-state dependency. The code change is done; in an already-deployed
  environment the resource still physically sits in workload state.

  **Preconditions**
  - Azure CLI authenticated with rights to the tfstate storage account.
  - `terraform` 1.14.x on PATH.
  - Both roots initialized against their real backends. The deploy pipeline does this; locally,
    `terraform init -backend-config=...` with the same keys the workflow uses — see
    `211-deploy-azure-split.yml`.
  - **Take a state backup first.**

  **State addresses**

  | | Address |
  |---|---|
  | Source (workload state) | `module.compute.azurerm_log_analytics_workspace.compute` |
  | Destination (platform state) | `azurerm_log_analytics_workspace.platform` |

  The Azure resource ID is unchanged — only which state file tracks it changes:
  `/subscriptions/<SUB>/resourceGroups/rg-<name_prefix>/providers/Microsoft.OperationalInsights/workspaces/<name_prefix>-log`

  **Procedure.** Replace `<env>` with `dev` or `prod`. Backend keys mirror the deploy workflow:
  platform = `<env>.terraform.tfstate`, workload = `<env>.workload.terraform.tfstate`.

  1. Back up both states:
     ```bash
     cd infra/terraform/environments/azure/<env>/workload
     terraform state pull > /tmp/backup-workload-<env>.tfstate
     cd ../platform
     terraform state pull > /tmp/backup-platform-<env>.tfstate
     ```
  2. Remove the workspace from workload state — do **not** destroy. `state rm` forgets the
     resource in Terraform without touching Azure; the workspace keeps running and retains its
     data:
     ```bash
     cd infra/terraform/environments/azure/<env>/workload
     terraform state rm 'module.compute.azurerm_log_analytics_workspace.compute'
     ```
  3. Import the existing workspace into platform state. `name_prefix` = `cna-<env>-scus`; get
     `<SUB>` from `az account show --query id -o tsv`:
     ```bash
     cd ../platform
     terraform import 'azurerm_log_analytics_workspace.platform' \
       "/subscriptions/<SUB>/resourceGroups/rg-<name_prefix>/providers/Microsoft.OperationalInsights/workspaces/<name_prefix>-log"
     ```
  4. Verify both plans are clean:
     ```bash
     cd ../platform && terraform plan    # workspace: NO changes. It WILL want to CREATE the new
                                         # flow-logs storage account + observability diagnostic
                                         # settings — expected and correct.
     cd ../workload && terraform plan    # NO destroy of the workspace. compute env now reads it
                                         # via data source; observability is app-only.
     ```
     **Stop and investigate if the platform plan wants to _create_ the workspace, or the workload
     plan wants to _destroy_ it** — that means the `rm`/`import` did not take.
  5. Apply platform first, then workload. Platform must apply before workload so the workspace and
     its outputs exist for the workload's `data.azurerm_log_analytics_workspace.platform` lookup.
     This matches the deploy order in `211-deploy-azure-split.yml`.

  **Also worth knowing**
  - The dedicated flow-logs storage account (`<name_prefix>flowlog`) and the firewall/NSG/flow-log
    diagnostic settings are **new** platform resources — no migration needed, they appear on the
    first platform apply.
  - Retention is 30 days in `platform/locals.tf` for both environments, reduced from prod's
    previous 90 during the FinOps pass. Reviewed and approved.
  - If you would rather not do state surgery, the alternative is accepting a one-time workspace
    recreation and the loss of log history. Not recommended for prod.

### T-305 — Verify the AWS parity claims against a live deployment

- **Priority:** Medium
- **Description:** The AWS stack is asserted to be at architectural parity with Azure across
  compute, database, edge/WAF, identity/KMS, secrets, storage, AI, tracing, observability, private
  networking, autoscaling, and VPC/networking. Every one of those claims is currently
  code-inspection only — nothing has been applied.
- **Dependencies:** T-302.
- **Recommended action:** After the first successful workload apply, walk the parity matrix
  capability by capability and record the result. Demote any capability that does not hold in
  practice from "complete" to a Phase 5 item.
- **Status:** Blocked on T-302
- **Notes for future engineers:** The parity matrix as authored —

  | Capability | Azure | AWS |
  |---|---|---|
  | Compute (3 containers) | Container Apps | ECS Fargate + ALB |
  | Database | PostgreSQL Flexible Server | RDS PostgreSQL |
  | Edge/CDN + WAF | Front Door Premium + WAF | CloudFront + WAFv2 |
  | WAF Auth.js exclusions | Field-specific exclusions | Custom rules (query params, cookies, headers) |
  | Identity + KMS | Managed Identity + Key Vault RBAC | IAM roles + KMS CMK + GitHub OIDC |
  | Secrets | Key Vault | Secrets Manager |
  | Storage | Storage Account (blob) | S3 (artifacts + static site) |
  | AI model management | AI Foundry + `cognitive_deployment` | Bedrock inference profile + optional provisioned throughput |
  | Distributed tracing | Application Insights | X-Ray (daemon sidecar + sampling rules) |
  | Observability | Log Analytics + diagnostics + flow logs | CloudWatch log groups + metric filters + alarms + VPC flow logs |
  | Private networking | Private endpoints (storage, KV, AI) | VPC endpoints (9) |
  | Scale-to-zero | Container Apps `min_replicas=0` | Application Auto Scaling (CPU + memory + ALB requests) |
  | VPC/networking | VNet + NSG + subnets | VPC + security groups + 3-tier subnets + NAT |

---

## Phase 4 — Technical debt

### T-401 — Retire or reconcile the superseded `migrate/` Terraform root

- **Priority:** High
- **Description:** `migrate/` is a complete, standalone AWS Terraform root (VPC, ALB, ECS, RDS,
  S3, Secrets Manager, CloudFront + WAFv2, IAM, plus a PowerShell bootstrap script) that predates
  and duplicates `infra/terraform/{providers,environments}/aws/`. Two AWS deployment paths exist
  in one repository, with different naming, different IAM, and an obsolete OIDC thumbprint. This
  is the single largest source-of-truth conflict left in the repository.
- **Dependencies:** T-203 benefits from resolving this.
- **Recommended action:** Confirm `migrate/` is fully superseded, check the assessment-level IAM
  policies below against the current `identity` module, then delete the directory and its
  bootstrap script.
- **Status:** Done — the directory and its bootstrap script are deleted. The gate below was
  verified first: `infra/terraform/providers/aws/identity/main.tf` attaches all three
  assessment-level policies to the `github_deploy` role (`ReadOnlyAccess`, `SecurityAudit`,
  `AWSBillingReadOnlyAccess`, each partition-aware via `data.aws_partition`), plus the scoped
  `deploy_write` policy — so nothing the `migrate/` role granted is lost. The stale
  `.secrets.baseline` entries for `migrate/secrets.tf` and `migrate/terraform.tfvars.example`
  were pruned and the gating detect-secrets scan re-verified green. For R-002 (AWS bootstrap):
  `migrate/scripts/Initialize-Migration.ps1` last exists at commit `7a6b1fa` on `main` — read it
  from history (`git show 7a6b1fa:migrate/scripts/Initialize-Migration.ps1`), and remember its
  `iam.tf` neighbour carries the obsolete OIDC thumbprint T-203 says must not be copied forward.
  The IAM policy mapping and directory inventory preserved in the notes below remain queued for
  the Wiki under T-601.
- **Notes for future engineers:** The current stack supersedes `migrate/` on every axis: eight
  module boundaries mirroring Azure, split platform/workload state, VPC endpoints, X-Ray, Bedrock,
  and autoscaling. `migrate/` has none of those. Treat it as history, not as an alternative. The
  Azure→AWS service mapping it documented is the same one recorded under T-305, so it is not
  repeated here.

  **The part worth keeping — assessment-level IAM.** The `migrate/` deploy role carried three
  read-only policies giving the assessment engine the access it needs, deliberately mirroring the
  Azure reader roles. Verify the current `identity` module grants equivalents before deleting:

  | AWS policy | Azure equivalent | Purpose |
  |---|---|---|
  | `ReadOnlyAccess` | Global Reader | Enumerate all resources |
  | `SecurityAudit` | Security Reader | Security findings |
  | `AWSBillingReadOnlyAccess` | Billing Reader | Cost and usage for FinOps |

  Plus a scoped write policy for Terraform to manage CNA infrastructure. If the current `identity`
  module lacks the billing or security-audit grant, the AWS FinOps and security signals will come
  back empty at runtime rather than failing loudly at apply — check this explicitly.

  **What is in the directory.** A single flat Terraform root — `providers.tf` (Terraform + AWS and
  GitHub providers, S3 backend), `variables.tf`, `locals.tf`, `vpc.tf`, `security_groups.tf`,
  `alb.tf`, `ecs.tf`, `rds.tf`, `s3.tf`, `secrets.tf`, `cloudfront.tf`, `iam.tf`, `outputs.tf`,
  `terraform.tfvars.example` — plus `scripts/Initialize-Migration.ps1`, a bootstrap script that
  created the OIDC provider, deploy role, policies, S3 state bucket, DynamoDB lock table, and
  GitHub secrets in one pass. That bootstrap script is the closest thing the repository has to
  Azure's `000-bootstrap-backend.yml` for AWS, so read it before writing the AWS bootstrap
  (`REVIEW.md` → R-002) — but do not run it: it provisions the superseded topology, and its
  `iam.tf` contains the obsolete OIDC thumbprint called out in T-203.

### T-402 — Wire a type checker into dev dependencies and pre-commit

- **Priority:** Medium
- **Description:** The Python review (gate for #110) found neither `ty` nor `mypy` configured —
  no entry in dev dependencies and no `[tool.ty]` / `[tool.mypy]` section in `pyproject.toml`. The
  codebase is mid-migration toward stricter typing with no tool enforcing it.
- **Dependencies:** None.
- **Recommended action:** Add `ty` to the `dev` optional-dependency group and a corresponding
  `pre-commit` hook, then fix or explicitly ignore the initial findings in one pass so the check
  starts green.
- **Status:** Partly done — the tooling is wired; the "starts green" half is **not** achieved, and
  deliberately so. `ty>=0.0.72` is in the `dev` group with a `[tool.ty]` section in
  `pyproject.toml` (py311, `include = ["cna"]`, vendored packs excluded, **no rule suppressed**),
  and a `ty` hook was **appended** to the existing `.pre-commit-config.yaml`, which already carried
  13 hooks across 4 repos (gitleaks, detect-secrets, ruff, ruff-format, and eight hygiene hooks
  including `mixed-line-ending --fix=lf` and `no-commit-to-branch --branch main`). The `ty` hook is
  `repo: local` / `language: system` so it runs the version pinned in the `dev` group; the existing
  remote hooks were left exactly as they were.
  `ty check cna/` reports **96 diagnostics**, so the hook is registered at `stages: [manual]`
  rather than gating. Forcing it green would have meant widening ignore lists, which this item
  explicitly forbids; the backlog is tracked in T-410 instead and the hook becomes gating by
  deleting one line once that clears. Of the original 98, **45 are `unresolved-import` for packages
  that *are* declared dependencies** simply absent from the review container — environment
  artifacts, not defects.
  The first run immediately earned its keep: it found a **guaranteed `TypeError` in production
  code**, now fixed. `aws_discovery.py` called
  `store.write_audit_event(engagement_id, "aws", event={...})`, but that method takes
  `(engagement_id, event)` — so `"aws"` bound to `event` and the keyword raised
  `TypeError: got multiple values for argument 'event'`. It was the only call site, and it sits in
  the access-denied branch that fires whenever an account cannot be assumed, which is routine in
  org-wide discovery. The cloud label now travels inside the event dict, and
  `TestAccessDeniedAuditEvent` covers it using a **real** `EngagementStore` rather than a
  `MagicMock`, since a mock accepts any signature and would not have caught it. Verified by
  reverting the fix and watching the test fail.
- **Notes for future engineers:** `ruff` is already clean across `cna/` (109 files formatted, all
  checks passing) with `select = E,W,F,I,B,C4,UP,S,N` and `target-version = "py311"`. Match that
  strictness posture. Do not widen ignore lists to make the first type-check run pass.
  `.pre-commit-config.yaml` already existed — an earlier note under T-406 claiming otherwise was
  wrong and has been corrected. Check before adding: it holds gitleaks, detect-secrets, ruff, and
  the pre-commit-hooks hygiene set. Note `mixed-line-ending --fix=lf` in particular, which rewrites
  CRLF to LF on commit; a number of tracked files are currently CRLF (`package.json`, several
  `.tf` and test files), so that hook and the tree disagree today.

### T-403 — Close the coverage gap on discovery orchestrator `run()` paths

- **Priority:** Medium
- **Description:** `[tool.coverage.report] fail_under = 80`. The Python review identified the
  discovery orchestrators' `run()` paths as the least-tested and highest-risk code in the package.
- **Dependencies:** None.
- **Recommended action:** Add unit coverage for the AWS and Azure discovery orchestrator entry
  points, including the error and retry branches, before adding further discovery features.
- **Status:** Done — a `TestRun` class was added to `tests/unit/test_aws_discovery.py` (9 cases) and
  `tests/unit/test_azure_discovery.py` (10 cases), taking both `run()` entry points from **zero**
  coverage to **100%**: `AWSDiscovery.run()` 21/21 statements, `AzureDiscovery.run()` 44/44,
  measured with the omit lifted (see T-408). Every cloud SDK collaborator is mocked, so no AWS or
  ARM call is made. Error and retry branches are covered as the notes below require: the AWS suite
  asserts `get_caller_identity` is actually retried once on `CNARateLimitError` and that the retry
  budget is eventually exhausted, and that `CNAAuthError` propagates rather than yielding a silently
  empty topology. The Azure suite covers `validate_access` failing before any scan work, the
  network-only-Reader path where `subscriptions.get()` fails and discovery proceeds with the ID as
  the display name, `--resume` both skipping and not skipping, blocked subscriptions still being
  recorded and checkpointed, and the progress callback being driven. File-level coverage moved from
  32% → 37% (AWS) and 18% → 22% (Azure); the rest of those files is out of scope for this item.
  Recorded in [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** The same review found and fixed a runtime-breaking `with_retry`
  contract bug in the AWS discovery path — exactly the class of defect an orchestrator test would
  have caught. `tenacity` is already a dependency; assert on retry behaviour, not just the happy
  path.

### T-404 — Close the remaining boto3 / azure-mgmt consistency gaps

- **Priority:** Medium
- **Description:** The AWS and Azure discovery paths diverge in session/credential handling and
  error handling. The review fixed the breaking case and flagged the rest as consistency gaps
  rather than defects.
- **Dependencies:** T-403 (tests first makes the refactor safe).
- **Recommended action:** Bring the AWS discovery module's session construction, retry decoration,
  and exception mapping in line with the Azure module's conventions. No hardcoded region or
  account values in either path.
- **Status:** Partly done — the "no hardcoded region or account values" half is closed; the
  exception-mapping half was **deliberately not done** (see below).
  `aws_discovery.py` called `session.client("ec2", region_name="us-east-1")` in
  `_get_enabled_regions()`. `describe_regions()` must reach some enabled region before the region
  list is known, but the literal is wrong in the `aws-us-gov` and `aws-cn` partitions, where
  us-east-1 does not exist. It is now resolved by `_region_for_region_lookup()`, most specific
  source first: the session's own configured region (`AWS_REGION`, profile, or instance metadata),
  then the first explicitly requested region, then the new declared
  `DiscoveryOptions.region_lookup_endpoint` — overridable, and a last resort rather than an inline
  literal. Five tests in `TestRegionLookupEndpoint` cover the order and assert the resolved value
  actually reaches `session.client()`. A sweep of `cna/` found no other inline region literal, no
  hardcoded account ID, and no inline Azure location; the only region literals remaining are the
  `_OPT_IN_REGIONS` set, which is a declared list, not a call-site value. The repository-wide rule
  is now written down in `README.md` → "Repository conventions".
  The other three asks were assessed and found to need no change: **retry decoration** is already
  identical (both modules use the same inline `with_retry()(fn)(...)` idiom — 7 AWS sites, 2
  Azure), and **session construction** is not meaningfully comparable, since a boto3 `Session` and
  an Azure credential/client pair are not analogous objects and each follows its own SDK's idiom.
- **Notes for future engineers:** This item said to converge on the Azure convention "because it is
  the older and more exercised path". For **exception mapping that is backwards, and it was
  deliberately not done.** AWS catches `botocore.exceptions.ClientError` and inspects the error code
  to separate `AccessDenied` from everything else; Azure uses a bare `except Exception` in roughly
  30 places. Converging AWS onto Azure would discard precise discrimination in favour of a catch-all
  that swallows genuine bugs — including the `with_retry` contract defect that prompted this item
  and T-403. Both paths already agree on what matters (raise `CNAAuthError`, with a message, using
  `from e`); AWS simply gets there more precisely. If this is revisited, the convergence should run
  the other way — narrow Azure's broad handlers toward AWS's — and that is a separate piece of work
  against a module at 22% coverage, so it needs tests first. Any behavioural change should be
  called out explicitly rather than landed silently.

### T-405 — Survey the scaffold/wiring gaps flagged during the dead-code sweep

- **Priority:** Low
- **Description:** The dead & stale code sweep (gate for #110) removed four verified-dead items
  from `apps/cna-web/**` (221 lines) and surveyed `cna/**` and `infra/**` without deleting
  anything further. The remaining findings were classified as wiring gaps and intentional
  scaffold rather than dead code, and were left in place deliberately.
- **Dependencies:** Best done after T-501, which closes the largest scaffold.
- **Recommended action:** Re-run the sweep once the AWS deploy path is functional. Anything still
  unreferenced at that point is genuinely dead and can be removed with confidence.
- **Status:** Not started
- **Notes for future engineers:** The sweep confirmed no `TODO`/`FIXME` comment references a
  closed issue, and that the `Phase`/`SCAFFOLD` markers in the source are intentional. Do not
  treat those markers as stale on sight.

### T-406 — Guardrail scripts are untested and one silently passes from the wrong directory

- **Priority:** Medium
- **Category:** Technical debt / CI reliability
- **Description:** The `repository-guardrails` job runs three validators — `validate_module_deps.py`,
  `validate_shape_catalog.py`, `validate_documentation_model.py` — and none of them has a single
  test. Two concrete consequences were confirmed during review:
  1. `scripts/validate_module_deps.py` resolves its target as a **relative** path
     (`MODULES_DIR = Path("cna/modules")`, line 12). Run from anywhere other than the repository
     root it finds no `module.yaml` files, prints `OK: 0 installed modules, all dependencies
     satisfied.` and exits 0. Reproduced: `cd /tmp && python3 <repo>/scripts/validate_module_deps.py`
     → exit 0. It passes in CI only because the job happens to start in the workspace root, so a
     green check does not prove the dependency graph was actually validated.
  2. `scripts/validate_documentation_model.py` (line 24) resolves its root from `__file__`
     (`Path(__file__).resolve().parent.parent`) and is therefore cwd-independent — the correct
     pattern. The three scripts should not disagree on something this basic.
- **Dependencies:** None. Best landed together with T-605 – T-607, which touch the same script.
- **Recommended action:**
  1. Change `validate_module_deps.py` to derive its root from `__file__`, matching
     `validate_documentation_model.py`, and make it fail rather than pass when the modules
     directory is missing or contains zero modules — "nothing found" is a broken invocation, not a
     clean bill of health.
  2. Add `tests/unit/test_guardrail_scripts.py` covering all three validators: a passing fixture, a
     violating fixture, and an assertion on the exit code. Build the fixtures in `tmp_path` and
     invoke each script as a subprocess so the test exercises the real entry point.
  3. Consider a local `pre-commit` hook (`repo: local`, `language: system`) for the three scripts so
     violations surface at commit time rather than at PR time.
- **Status:** Done — `validate_module_deps.py` now derives `MODULES_DIR` from `__file__` and fails
  when the modules directory is missing or holds zero `module.yaml` files, so "nothing found" is
  reported as a broken invocation instead of a clean bill of health. `tests/unit/test_guardrail_scripts.py`
  covers all three validators (22 cases) — passing and violating fixtures built in `tmp_path` and
  invoked as subprocesses, including an explicit cwd-independence test that reproduces the original
  defect. The `pre-commit` hook in recommended action 3 was not added; see the notes below.
  Recorded in [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** All three scripts follow the same shape — a `validate()`/`main()`
  returning a bool/int and `sys.exit()` in `__main__` — so one parametrised test can cover them.
  The stream inconsistency noted here was closed by T-607; all three now report failures on
  `stderr`. The `pre-commit` hook (recommended action 3) was left undone, but the reason
  recorded here originally was **wrong**: it claimed the repository has no
  `.pre-commit-config.yaml`. It does, and always did — 13 hooks across 4 repos. Adding the three
  guard scripts to it is a small, still-open follow-up, not a new-file decision. `validate_shape_catalog.py` is covered only by a
  "still passes against this repository" assertion; it reads a hardcoded catalog path and has no
  fixture seam, so a violating-fixture test for it needs a small refactor first.

### T-407 — The AWS Terraform has no `fmt` or `validate` coverage in CI

- **Priority:** Medium
- **Category:** CI coverage / infrastructure
- **Description:** No workflow runs `terraform fmt -check` or `terraform validate` against
  `infra/terraform/providers/aws/**` or `infra/terraform/environments/aws/**`. Grepping the
  workflows for `terraform init|validate|fmt` returns only Azure roots (`350-drift-dev.yml`,
  `360-drift-prod.yml`, `211-deploy-azure-split.yml`, `000-bootstrap-backend.yml`); the sole
  AWS-targeting workflow, `212-deploy-aws-split.yml`, fails fast before Terraform runs. The
  practical consequence was hit directly while closing T-202: a change to three AWS `variables.tf`
  files could not be checked by any tooling, in CI or locally, and had to be verified by a
  hand-rolled brace-balance script. 90 resources across eight modules are currently unlinted.
- **Dependencies:** None. Deliberately independent of `REVIEW.md` R-001 – R-003 — `fmt` and
  `validate` need neither an AWS account nor credentials, unlike `plan`.
- **Recommended action:** Add a job to `300-test-codebase.yml` that runs `terraform fmt -check
  -recursive` over `infra/terraform/` and `terraform init -backend=false && terraform validate`
  for each AWS root. `-backend=false` is the important flag: it makes validation possible with no
  state backend, which is exactly the situation until R-002 is resolved.
- **Status:** Done — a `terraform-checks` job was added to `300-test-codebase.yml`, so both checks
  now run on every push and PR. `terraform fmt -check -recursive infra/terraform/` covers **both**
  clouds (formatting needs no provider download), and `terraform validate` runs per AWS root after
  `terraform init -backend=false`, which is what makes it possible before the R-002 state backend
  exists. The loop reports each root under its own `::group::` and accumulates failures so one bad
  root does not mask the others.
  Closing this also required fixing four **pre-existing** `fmt` violations that would have turned
  the new job red immediately — all pure alignment, none introduced by recent work:
  `environments/aws/{dev,prod}/workload/main.tf` (an `enable_xray` assignment),
  `providers/aws/observability/variables.tf` (the `alarm_thresholds` object), and
  `providers/aws/security/locals.tf`. Verified with a real `terraform` 1.9.8 binary: `fmt -check
  -recursive` is now clean across `infra/terraform/`, and LF endings are unchanged.
  **`validate` was attempted, failed, and was removed** — see T-409. The first version of this job
  ran `terraform validate` per AWS root after `init -backend=false`. It failed on its first CI run
  (check run 95481918579 on commit `cc3c9db`) and the cause could not be determined: the Actions
  API returns 403 for this automation, and the egress policy blocks `registry.terraform.io`, so the
  failure could be reproduced neither by reading the log nor by running it locally. `fmt` was
  re-verified clean at that exact commit with a real terraform 1.9.8 binary, which is how the
  failure was isolated to the validate step. Only `fmt` shipped; the job is `terraform-fmt`.
- **Notes for future engineers:** Do not fold this into 212 — that workflow is `workflow_dispatch`
  only and fails fast by design, so validation placed there would never run. It belongs in the
  push/PR test pipeline. Note also that the Azure roots would benefit from the same `fmt -check`
  sweep; scope it to `infra/terraform/` as a whole rather than AWS alone.

### T-408 — The discovery orchestrators are omitted from coverage on a false premise

- **Priority:** Medium
- **Category:** Test integrity / CI
- **Description:** `[tool.coverage.run] omit` in `pyproject.toml` excludes
  `cna/modules/network/discovery/aws_discovery.py` and `azure_discovery.py`, with the comment
  *"require live AWS/Azure API calls against real tenants. Covered by integration tests run against
  sandboxed tenants."* That premise is false: `tests/unit/test_aws_discovery.py` and
  `test_azure_discovery.py` already exercise both modules entirely with `MagicMock`/`patch` and make
  no network call, and T-403 has now added 19 more such tests. The consequence is that the
  `fail_under = 80` gate has never measured 1,542 statements — the code T-403 itself calls "the
  least-tested and highest-risk in the package". A regression in either file cannot fail CI on
  coverage grounds.
- **Dependencies:** None, but see the measured cost below before acting.
- **Recommended action:** Removing the two `omit` entries today would take total coverage from
  **84% to 67%** and fail the 80% gate by 13 points (measured across the full suite: 4,240 → 5,782
  statements, 697 → 1,912 missed). Closing that needs roughly **760 further covered statements**
  across the two files. Land it incrementally: keep the entries, drive per-file coverage up with
  mocked tests in the style T-403 established, and remove each `omit` line once its file clears
  ~80% on its own. Do not remove them in one step and lower `fail_under` to compensate — that
  weakens the gate for the whole package to accommodate two files.
- **Status:** Done — **both files are covered and both `omit` lines are gone.**
  46% → **98%** (380 statements, 6 missed), via 46 new tests in `tests/unit/test_aws_discovery.py`
  covering the collectors that had none: `_assume_role`, `_list_org_accounts`,
  `_get_enabled_regions`, `_discover_region`, `_collect_vpcs`, `_collect_igws`, `_collect_peering`,
  `_collect_nacls`, `_collect_tgws`/`_collect_tgw_attachments`, `_collect_dx`,
  `_collect_vpn_gateways`, `_collect_network_firewalls`, `_collect_waf_web_acls`, and
  `_discover_account`. All mocked; no network call. With it measured, the package gate **rises**
  84% → **87.5%**, because the file now sits above the package average.
  **It found a real bug, which is the argument for the whole item.** `_collect_tgw_attachments`
  derived the attachment type as `AttachmentType(raw.replace("-", "_"))`. AWS returns six values
  for `ResourceType`, and that transform mislabelled two of them: `direct-connect-gateway` became
  `direct_connect_gateway` and `tgw-peering` became `tgw_peering`, neither an enum member, so both
  fell through the `except ValueError` to `AttachmentType.VPC`. Every Direct Connect gateway
  attachment on a Transit Gateway was silently recorded as a VPC attachment — wrong in the
  topology, in the diagrams, and in any rule counting VPC attachments. Replaced with a declared
  `_TGW_ATTACHMENT_TYPES` mapping covering all six wire values, and an unmapped value now logs a
  warning naming itself instead of failing silently. Parametrized over every value AWS returns.
  **`azure_discovery.py` is done too: 22% → 85%** (1,189 statements, 178 missed), across five
  batches — the module helpers and subnet classifier; `_init_credentials`, `validate_access`, and
  the subscription listing; `_collect_management_groups`; `_discover_subscription` itself (the
  largest single block, including the fault-isolation contract that one failing collector must not
  lose the subscription); the five phase-2 scans; the resource collectors; and the Azure Monitor
  metrics group with its aggregation helpers.
  **Both `omit` entries are gone and the gate now measures all 1,569 statements.** Package
  coverage went *up*, 84% → **87%**, because both files landed above the package average — the
  13-point shortfall the original estimate predicted never materialised, since it assumed the
  files stayed at their then-current coverage.
  A reusable `_Arm` test double carries the Azure work: the collectors read optional attributes
  directly and coerce them (`int(x or 4)`), so a bare `MagicMock` is the wrong shape —
  `int(MagicMock())` raises. `_Arm` returns `None` for anything not set, which is what the SDK
  does for an unpopulated field.
- **Notes for future engineers:** To measure honestly while the entry is still in place, run
  pytest with `--cov-config` pointing at a copy of the config with the line deleted; that is
  how the figures above were obtained. Also correct the misleading comment when the entries go —
  and note the same block omits `cna/diagram_engine/diagrams_generator.py` and the diagram modules
  for a *genuine* reason (they need the graphviz binary), so do not delete the block wholesale.

### T-409 — `terraform validate` for the AWS roots: failed on first run, cause unknown

- **Priority:** Medium
- **Category:** CI coverage / infrastructure
- **Description:** T-407 originally added `terraform validate` for each AWS root, run after
  `terraform init -backend=false`. It **failed on its first CI execution** (check run 95481918579,
  commit `cc3c9db`, PR #155) and was removed so the rest of that work could land; only
  `terraform fmt -check` shipped. The failure is genuinely undiagnosed, not merely unfixed. Two
  independent walls prevented diagnosis from the authoring environment: every GitHub Actions and
  Checks endpoint returns `403 Resource not accessible by integration` (job logs, check-run detail,
  annotations), and the session egress policy rejects `registry.terraform.io:443` and
  `checkpoint-api.hashicorp.com:443` at CONNECT, so `init` cannot resolve providers locally either.
  `terraform fmt -check -recursive` was re-run against that exact commit with a real terraform
  1.9.8 binary and was clean, which isolates the failure to the validate step rather than the
  formatting one.
- **Dependencies:** None, but the first step needs someone who can read the Actions log.
- **Recommended action:** Read the failing step's output and split on what it says.
  1. **If `init` could not reach the registry** — the runner has the same egress restriction. The
     fix is a provider mirror or committed lock files, not a Terraform change. Note the AWS roots
     carry **no `.terraform.lock.hcl`** at all, while every Azure root does; that asymmetry is the
     first thing to check, since it means the AWS roots must resolve `hashicorp/aws ~> 5.0` fresh
     on every init.
  2. **If `validate` reported config errors** — they are real defects in roots that have never been
     validated by anything, and should be fixed root by root before the step is restored.
  Restore the step in `300-test-codebase.yml` once it passes; the removed version is in this
  repository's history on commit `cc3c9db`.
- **Status:** Done — diagnosed as case 2 (real config errors), fixed, and the validate step
  restored. The original failure's check-run annotations (readable via the REST checks API even
  where the Actions log endpoints are not) named exactly the two failing roots: **both workload
  roots and neither platform root** — which by itself ruled out a registry/egress cause, since
  `init` had to succeed for the platform validates to pass. Reproduced locally with terraform
  1.9.8 and providers resolved from `releases.hashicorp.com` / GitHub releases into a filesystem
  mirror (the registry itself is still egress-blocked from the authoring environment). Two real
  defects, both in modules only the workload roots consume:
  1. `providers/aws/runtime/variables.tf:2` — the `name_prefix` variable's *description* embedded
     an unescaped `${name_prefix}`, which HCL parses as an interpolation inside a variable block:
     "Variables may not be used here", failing `init` before validate even ran. Escaped to
     `$${name_prefix}`. A sweep found no other unescaped `${…}` in any description; the other
     hits are legitimate `${var.*}` interpolations in resource arguments.
  2. `providers/aws/ai/main.tf:59` — `aws_bedrock_inference_profile.chat` set
     `type = "APPLICATION"`, an attribute the provider marks read-only (a profile you create is
     APPLICATION by definition; SYSTEM_DEFINED ones are AWS-managed and only referenced). Removed,
     with a comment recording why.
  After both fixes, all four roots validate clean (`Success! The configuration is valid.`) on
  terraform 1.9.8 with hashicorp/aws 5.100.0, hashicorp/time 0.14.1, hashicorp/random 3.9.0, and
  integrations/github 6.6.0, and `terraform fmt -check -recursive` stays clean. The
  `Terraform validate (AWS roots)` step is restored to the `terraform-checks` job in
  `300-test-codebase.yml`, per-root with `::group::` output and an error naming any failing root.
  **Still open (small follow-up):** the lock files. `terraform providers lock` needs
  `registry.terraform.io`, which the authoring environment cannot reach, so the four AWS roots
  still carry no `.terraform.lock.hcl`. Generate them from a machine with registry access (the
  self-hosted runner qualifies) with
  `terraform providers lock -platform=linux_amd64` per root — pinning matches the Azure roots and
  the CBTS pinned-dependency standard.
- **Notes for future engineers:** Do not restore the step without first reproducing a green run —
  it blocks every PR when red, which is why it was pulled rather than left failing. Generating the
  lock files (`terraform providers lock` for the four AWS roots) is worth doing regardless of the
  outcome: it pins provider versions for supply-chain reasons, matching what the Azure roots
  already do, and it is the CBTS standard of preferring pinned versions in security-sensitive
  dependencies.

### T-410 — Clear the 96 `ty` findings so the type check can gate

- **Priority:** Medium
- **Category:** Type safety
- **Description:** T-402 wired `ty` but could not make it green. `ty check cna/` reports 96
  diagnostics, so the pre-commit hook sits at `stages: [manual]`. Breakdown of the 53
  non-import findings at the time of writing: `unresolved-attribute` 22, `invalid-argument-type`
  17, `unknown-argument` 3, `invalid-parameter-default` 2, and one each of `unsupported-operator`,
  `pydantic-discarded-extra-argument`, `parameter-already-assigned` (**fixed** under T-402 — it was
  a real `TypeError`), `no-matching-overload`, `missing-argument`, `invalid-type-form`,
  `invalid-return-type`, `invalid-raise`, and `invalid-assignment`. Concentrated in
  `aws_discovery.py` (10), `azure_discovery.py` (8), `analysis_engine.py` (8), and `cli/publish.py`
  (7). The remaining ~43 are `unresolved-import` for declared-but-uninstalled packages, which
  resolve wherever the dependencies are actually present.
- **Dependencies:** None. Best done after T-403-style tests exist for whatever is touched, since
  several fixes are in modules at 22–37% coverage.
- **Recommended action:** Work rule by rule, not file by file — `unresolved-attribute` is the
  largest group and the most likely to hide genuine bugs of the kind already found. Two worth
  starting with: `analysis_engine.py:1428` reads `.vnet_id` off `AzureVirtualNetworkGateway`, which
  has no such attribute, and `core/throttle.py:78` can `raise last_exc` while it is still `None`
  (currently unreachable, but only by accident of the loop's structure). When the count reaches
  zero, delete the `stages: [manual]` line from the `ty` hook so it gates.
- **Status:** In progress — 98 → **49** diagnostics as measured in a bare container, and **24**
  once the declared dependencies are actually installed. Thirty fixed, each a real defect rather
  than a style nit:
  `analysis_engine.py` used the builtin `callable` in a type expression (not a type at all) and
  `options: AnalysisOptions = None`; `render_pipeline.py` had the same `= None` on a non-Optional
  parameter, plus `Path("engagements") / self.store.engagement_id` where `engagement_id` is
  `str | None` — that path now raises a `ValueError` naming the missing input instead of an opaque
  `TypeError`; `technical_report.py` called `.startswith()` on `Finding.resource_type`, which is
  `str | None` with default `None`, in two places; and `core/throttle.py` could `raise last_exc`
  while it was still `None` (unreachable today, but only by accident of the loop's shape — it now
  falls through to an explicit `RuntimeError`). Verified behaviourally, not just by re-running the
  checker: `with_retry` still retries then succeeds, both `__init__`s still default correctly, and
  `_output_dir()` raises `ValueError` rather than `TypeError`.
  Three further defects fixed in a second pass, both of the same shape as the T-402 bug — a store
  method called with arguments that do not match its signature, hidden because the tests mock the
  store:
  `aws_discovery.py` called `write_discovery_checkpoint(engagement_id, "aws", account_id=...,
  data=...)`, but that method takes `(engagement_id, platform, account_or_sub_id, data)`. Passing
  `account_id=` raised `TypeError: got an unexpected keyword argument 'account_id'` **inside the
  per-region loop**, so the first region of the first account aborted AWS discovery and no
  checkpoint was ever written. Azure's equivalent call was always correct. Now positional, with
  `TestRegionCheckpointWrite` covering it against a real `EngagementStore` — verified by reverting
  the fix and watching the test fail.
  `AzureSubnet` had no `subnet_type` field while the discovery path already passed one, so Pydantic
  (which defaults to discarding extras) **silently threw away every classification
  `_classify_subnet()` computed** — a function that exists for no other purpose. The field is now
  declared with a `SubnetType.UNKNOWN` default, so checkpoints written before it existed still
  deserialise, and the value survives the JSON round-trip the checkpoint path uses. Note the AWS
  `Subnet` model always had this field; only the Azure model was missing it.
  A third pass found the most fundamental one yet: **`EngagementStore.init()` and `save()` could
  never run.** Both called `config.model_dump(mode="json", default=str)`, and Pydantic v2's
  `model_dump` has no `default` parameter, so both raised
  `TypeError: BaseModel.model_dump() got an unexpected keyword argument 'default'` — an engagement
  could not be created or persisted at all. The argument was redundant as well as invalid:
  `_atomic_write` already passes `default=str` to `json.dump`, and `mode="json"` already renders
  datetimes and enums. Dropping it makes the whole `init` → `save` → `load` cycle work.
  `tests/unit/test_persistence.py` is new — `EngagementStore` had **no test file at all**, which is
  precisely why three separate signature bugs survived a green suite. Ten tests, all against a real
  store on `tmp_path`, including explicit guards that the two previously-wrong call shapes now raise
  `TypeError`.
  Also corrected an error introduced earlier in this same item: `progress_callback` was annotated
  `Callable[[str], None]` on a guess, but `cli/analyze.py` passes
  `progress(cloud, current, total, label)`. The annotation is now
  `Callable[[str, int, int, str], None]`, which removes the two
  `too-many-positional-arguments` findings that annotation had itself created.
  A fourth pass fixed two more genuine crashes:
  `analysis_engine._check_azure_peering_gateway_transit()` read `gw.vnet_id`, which
  `AzureVirtualNetworkGateway` does not have — the model carries `subnet_id`. The rule raised
  `AttributeError` for any subscription that actually had a gateway, so it only ever "worked" when
  the gateway list was empty and the short-circuit skipped it. An ARM subnet id nests under its VNet
  id (`<vnet_id>/subnets/<name>`), which is the real link; `TestAzurePeeringGatewayTransit` covers
  the no-raise case, suppression by a local gateway, and that a gateway in a *different* VNet does
  not count.
  `technical_report._build_context()` called `sorted()` over a set of `Finding.account_id`, which is
  `str | None`. One finding without an account id raises
  `TypeError: '<' not supported between instances of 'str' and 'NoneType'` — reproduced directly.
  Both comprehensions now filter falsy ids.
  A fifth pass closed the Optional-narrowing group, which was six findings sharing one shape.
  `AWSDiscovery._mgmt_session` is `Session | None` because it does not exist until `run()` creates
  it, so every per-account helper dereferenced a possibly-`None` session. A `_mgmt` property now
  narrows it once and raises a named `RuntimeError` instead of letting it surface as
  `AttributeError: 'NoneType' object has no attribute 'client'` several frames deeper. Both
  discovery `run()` methods also took `self.store.engagement_id` — `str | None` — straight into
  models that require `str`; they now fail early with a `ValueError` naming the fix, matching the
  guard added to `render_pipeline._output_dir()`. And `PortalGenerator._filesizeformat` divided its
  own `int` parameter into a float; it uses a local `float` now.
  **Known false positive, deliberately not "fixed":** `cli/publish.py:173,176` reports
  `generate_presigned_url` / `generate_sas_token` missing on the `S3Deployer | AzureBlobDeployer`
  union. The code is correct — `--cloud` is a `click.Choice(["aws", "azure"])`, and the branch that
  selects the method matches the branch that built the deployer. The checker simply cannot tie
  `cloud` to the deployer's type. Narrowing it properly needs the two lazily-imported classes in
  scope at the call site; do that as a small refactor if the noise becomes annoying, not by
  suppressing the rule.
  A sixth pass applied the same narrowing pattern to Azure and cleared the tail.
  `AzureDiscovery._credential` and `._sub_client` start as `None` until `_init_credentials()` runs;
  `_cred` and `_subs` properties now narrow them across **17** read sites. `DiagramExporter`'s
  `_drawio_bin` is `str | None` and would have reached `subprocess.run` as `argv[0]`; it now raises
  `ExportPipelineError` naming the condition. `AnalysisEngine.run()` got the same `engagement_id`
  guard as the two discovery paths. `RenderPipeline` now requires a bound store **at construction**:
  `DeliverableManifest` is a plain dataclass with no validation, so a `None` id was being written
  into the manifest as `null` rather than rejected — the guard moved up from `_output_dir()`, which
  had been enforcing the same invariant one step too late. `render_tgw_topology` claimed
  `-> dict[str, Path]` while actually nesting TGW id → format → Path, unlike its siblings which
  render one diagram each; the annotation now matches (it has no callers today, so nothing broke).
  `_dedup_key` was widened to `str | None`, which is what it always accepted.
  **Noticed, not fixed:** `_dedup_key(None, None)` returns the literal `"None:None"`, so any two
  findings that both lack `rule_id` *and* `resource_id` collide and the second is silently
  deduplicated away. Both fields are Optional on `Finding`. Whether such a finding should exist at
  all is a schema decision rather than a typing one, so it is left here rather than papered over.
  **The count was finally measured honestly.** Running `pip install -e .` and re-checking drops the
  total to **24**, because all nine declared-but-uninstalled packages resolve. What remains is
  **15 `unresolved-import`, every one of them an *undeclared* dependency** (T-414), and just **8**
  real findings: the two T-412 engine writes, four in `foundry_agent_client.py` against an SDK API
  that does not exist (T-413 — invisible until the dependency was installed), a `dict` variance
  issue in the drawio MCP client, and an `EncyclopediaReportRenderer.render` parameter typed
  `list[Finding | dict]` where callers pass `list[Finding]`.
  T-414 is now done, which took the count to **8**, then T-413 to **6**. Measure in an environment
  with dependencies installed; a bare container overstates the count fourfold.
  **The tail is now cleared — 6 → 2.** Four fixes, none of them suppressions:
  1. `DrawioMCPClient.search_shapes` built its payload as an unannotated literal, which infers
     `dict[str, str | int]`; `dict` is invariant, so it did not satisfy `_post`'s
     `dict[str, object]`. Annotated `dict[str, object]`, matching its sibling `create_diagram`,
     which already did this.
  2. `EncyclopediaReportRenderer.render` / `.render_html` / `build_encyclopedia_context` declared
     `findings: list[Finding | dict]` and every caller passes a homogeneous `list[Finding]` —
     rejected for the same invariance reason. All three now take `Sequence[Finding | dict]`, which
     is covariant and is all the code needs: the parameter is only iterated
     (`[normalize_finding(f) for f in findings]`), never mutated.
  3. `RenderPipeline.run()` re-read `self.store.engagement_id` (`str | None`) instead of the
     `self.engagement_id: str` the constructor guard already narrowed, throwing the narrowing away
     at five sites. All five now read the narrowed attribute.
  4. The **two T-412 engine writes are implemented**, not guarded — see that item. Implementing
     `write_deliverable_manifest` is what surfaced (3): the argument type could not be checked
     while the method did not exist.
  **Remaining: 2, both the T-413 stub artifact** — `project.agents` at
  `foundry_agent_client.py:133,159`. `AIProjectClient.agents` is annotated
  `-> AgentsClient  # type: ignore[name-defined]` in the SDK because its companion class is
  imported lazily, so the checker cannot resolve the return type. Verified at runtime that the
  attribute and its `threads`/`messages`/`runs` children all exist. There is no structural fix that
  is not a contortion around working code, so the hook stays non-gating until the SDK ships a
  resolvable annotation. **Unblock condition:** when `ty check` reports 0, delete the
  `stages: [manual]` line from the `ty` hook in `.pre-commit-config.yaml` and update the comment
  above it — that is the entire remaining change.
- **Notes for future engineers:** Do not close this by widening ignore lists or adding
  `# type: ignore` — T-402 is explicit on that point, and the two bugs already found are the
  argument for taking the findings seriously.

### T-411 — Triage the 446 `detect-secrets` findings and close the secret-scanning gap

- **Priority:** High
- **Category:** Security
- **Description:** Three related problems, found while wiring pre-commit under T-402.
  1. **`.secrets.baseline` was corrupt** and had been for some time — invalid JSON, a `]` where a
     `}` belonged on the `TwilioKeyDetector` entry, which broke the `plugins_used` array. Any tool
     reading it failed with *"Unable to read baseline"*. **Fixed** under T-402.
  2. **The corrupt baseline silently broke the commit-time hook.** `detect-secrets` *is* wired in
     `.pre-commit-config.yaml` and has been, so the practical effect of (1) was that the hook
     failed with *"Unable to read baseline"* for anyone who ran `pre-commit install` — a broken
     control rather than a missing one, which is worse, because the config reads as protected.
  3. **`detect-secrets` is not in CI.** It runs at commit time only. The CI `secret-scan` job uses
     `gitleaks`, and that job is `continue-on-error: true` (it needs a paid licence on private
     repos), so no secret scan can currently fail a build. `README.md`'s claim that both "run on
     every commit and CI push" is accurate for commits and overstated for CI.
  With a readable baseline, the first scan reports **446 findings across 325 files**, none ever
  triaged. 367 come from the vendored `.claude/` and `.agents/` packs — third-party security
  documentation full of example tokens — and the pre-commit hook already excludes those and
  `.deployment-catalog/` (build manifests whose image digests trip the hex-entropy detector),
  leaving **31 project findings**. By type across the whole scan: Secret Keyword 279, Hex High
  Entropy String 127, Basic Auth Credentials 16, AWS Access Key 16, JSON Web Token 3, Private Key
  2, IBM Cloud IAM Key 2, Slack Token 1.
- **Dependencies:** None.
- **Recommended action:** Triage the 31 project findings by hand — they look like Terraform
  variable names, `.env.example` / `terraform.tfvars.example` placeholders, and test fixtures, but
  *look like* is not good enough for a category that includes "AWS Access Key" and "Private Key".
  Audit each, then record the verdicts with `detect-secrets scan --baseline .secrets.baseline` and
  `detect-secrets audit .secrets.baseline`. The existing hook gates already — it just could not
  read the baseline — so once the baseline is honest, verify `pre-commit run detect-secrets
  --all-files` passes. Separately, decide the `gitleaks` question: either license it so the CI
  job can drop `continue-on-error`, or stop presenting it as a build-blocking control.
- **Status:** Done — audited by hand, **no real secret found**, and the control now gates.
  **One correction to the description above:** the hook did *not* exclude the vendored packs. Its
  only exclusion was `^\.env\.example$`, so all 8,480 vendored files were in scope. That is why
  the finding count was unmanageable. Excluding `.claude/`, `.agents/`, `.codex/`, and
  `.deployment-catalog/` — the same directories `pyproject.toml` excludes from ruff and
  `validate_documentation_model.py` excludes from the documentation model, on the same grounds —
  takes the count from **446 to 33**. `.env.example` is deliberately no longer excluded: excluding
  it meant a real credential pasted into the template would never be caught, so its placeholders
  are recorded in the baseline instead, which still catches anything new.
  **All 33 audited individually. Every one is a false positive.** By class:

  | Class | Count | Examples |
  |---|---|---|
  | Placeholders in `.example` templates | 8 | `apps/cna-web/.env.example`, `migrate/terraform.tfvars.example` — `change-me-…`, `your-…-secret`, `generate-with-openssl-rand-base64-32`, `sk-...` |
  | Secret **names**, not values | 9 | Key Vault secret names in both `workload/main.tf` roots; `$keyVaultSecret = "cna-azure-openai-endpoint"`; `"DOCKERHUB" + "_USERNAME"`, a name built by concatenation specifically to dodge scanners |
  | References to a secret store | 6 | `${{ secrets.* }}` env bindings; `DB_URL=$(terraform output -raw …)`; the Secrets Manager ARN wildcard in `aws/identity/locals.tf` |
  | Connection strings built from variables | 3 | `aws/runtime/main.tf:19`, `migrate/secrets.tf:14`, and a `description` in `azure/runtime/variables.tf` showing the DSN *format* |
  | Test fixtures | 5 | `test_auth.py` (`"super-secret"`, `"my-secret"`, `"s"`), `test_aws_discovery.py` (`"example-secret-not-real"`, `"b"`) |
  | Local-dev / CI throwaway values | 3 | the `devpassword@localhost` DSN in both `.env.example` files; `test:test@localhost` plus `ci-smoke-secret-not-real` in the 200 smoke test |
  | A checksum | 1 | `scripts/bootstrap-runner.sh:50` — the SHA-256 of the runner tarball, verified at line 177. A supply-chain control, the opposite of a secret |

  **The 16 "AWS Access Key" and 2 "Private Key" findings that made this High priority are all in
  the vendored packs**, not in project code — they are example keys in third-party security
  documentation. No project file produced a finding of either type.
  **The control was verified working, not merely quiet.** A green scan is exactly what a broken
  hook looks like, which is how problem (2) above survived. `detect-secrets-hook` exits 0 against
  the audited baseline, and exits 1 with `Potential secrets about to be committed` when a canary
  file containing an AWS-shaped key is added. The canary was removed afterwards.
  **Problem (3) is closed too.** A gating `detect-secrets` job was added to
  `300-test-codebase.yml`. It runs the hook *through pre-commit* rather than invoking
  `detect-secrets` directly, so the exclusion list lives in exactly one place instead of being
  restated in the workflow and drifting. The `gitleaks` job stays `continue-on-error` — that is a
  licensing constraint, not a choice — but the repository now has a secret scan that can fail a
  build. `README.md` said both "run on every commit and CI push"; it now states which one gates and
  which is advisory.
  **Still open (deliberately):** the per-finding `is_secret: false` labels are *not* set in the
  baseline. `detect-secrets audit` is interactive-only — there is no non-interactive labelling
  mode — and when driven headlessly it offered only `(s)kip/(b)ack/(q)uit`, because the baseline
  stores hashes rather than values and it could not render a verdict prompt. Rather than risk
  mislabelling security data, the verdicts are recorded in the table above, which is reviewable in
  version control rather than buried in JSON. Anyone who wants the labels in the file can run
  `detect-secrets audit .secrets.baseline` at a terminal.
  **The `gitleaks` licensing question is still a decision for the repository owner** — see the
  recommended action. It is no longer urgent now that detect-secrets gates.
- **Notes for future engineers:** Do **not** close this by regenerating the baseline in one step —
  that marks all 446 as reviewed without anyone having reviewed them, which is worse than the
  current state because it looks clean. The baseline is an audit record, not a suppression file.
  That instruction was followed: the baseline covers only the 33 findings in the table above, each
  inspected individually, and the 413 vendored findings are *excluded by path* rather than
  laundered through the baseline as if reviewed.

### T-412 — `cna analyze`, `cna report`, and `cna publish` call EngagementStore methods that do not exist

- **Priority:** High
- **Category:** Correctness / broken feature
- **Description:** Three CLI commands call **ten methods that are absent from `EngagementStore`**.
  Confirmed by `hasattr` against the real class, not inferred: the class defines twelve methods
  (`init`, `load`, `save`, `acquire_lock`, `release_lock`, `write_discovery_checkpoint`,
  `list_completed_checkpoints`, `write_audit_event`, `engagement_dir`, `_atomic_write`,
  `output_paths`, `__init__`) and none of the following exist —

  | Missing method | Called from |
  |---|---|
  | `load_aws_topology` | `cli/analyze.py:83` |
  | `load_azure_topology` | `cli/analyze.py:97` |
  | `load_findings_report` | `cli/report.py:87`, `cli/report.py:149` |
  | `get_delivery_date` | `cli/publish.py:67` |
  | `load_deliverable_manifest` | `cli/publish.py:76` |
  | `load_findings_report_json` | `cli/publish.py:87` |
  | `write_access_record` | `cli/publish.py:179` |
  | `load_access_record` | `cli/publish.py:214` |
  | `write_findings_report` | `ai_engine/analysis_engine.py:1726` |
  | `write_deliverable_manifest` | `report_engine/render_pipeline.py:237` |

  These are not latent: `EngagementStore().load_aws_topology("eng-1")` raises
  `AttributeError: 'EngagementStore' object has no attribute 'load_aws_topology'`. Worse, the call
  in `analyze.py` sits inside `try: ... except FileNotFoundError:`, which does **not** catch
  `AttributeError`, so the command aborts with an unhandled traceback rather than the intended
  "run `cna discover` first" message. No `SCAFFOLD` marker or `NotImplementedError` guard exists on
  any of these paths, so nothing signals that they are unfinished. Found by `ty` on its first run
  (T-402).
- **Dependencies:** None. Blocks any real use of `cna analyze`, `cna report`, or `cna publish`.
- **Recommended action:** Decide first whether these commands are meant to work today or are Phase D
  scaffold — `cli/analyze.py`'s docstring says "Phase D entry point", which suggests the latter, but
  nothing in the code says so. If scaffold, guard each command with an explicit
  `NotImplementedError` naming the blocking item, so the failure is honest. If they are meant to
  work, implement the ten methods on `EngagementStore`; the call sites already pin down the
  contract (arguments and expected return types), and `write_discovery_checkpoint` plus
  `output_paths` show the intended on-disk layout to read back. Cover each with a unit test using a
  real `EngagementStore` on `tmp_path` — a `MagicMock` store accepts any method name and is exactly
  why this survived.
- **Status:** Done as scaffold guards — the repository owner confirmed these commands are Phase D
  scaffold, not intended to work today, so each now fails honestly instead of dying with an
  unhandled `AttributeError`. **Five** commands are guarded, not three: the original survey missed
  `cna report preview` and `cna publish status`, which live in the same groups and call
  `load_findings_report()` and `load_access_record()` respectively.
  Each guard raises `NotImplementedError` naming the exact missing `EngagementStore` methods, so
  the message tells a caller what would have to be built. Verified with `click.testing.CliRunner`:
  all five raise `NotImplementedError` rather than `AttributeError`.
  A useful side effect: `ty` treats code after an unconditional `raise` as unreachable, so guarding
  the commands also removed nine of the eleven findings this item owns — confirmed with a minimal
  probe before relying on it. The count fell 60 → 49.
  **Two call sites were left unguarded** — `analysis_engine.py:1736` (`write_findings_report`) and
  `render_pipeline.py:245` (`write_deliverable_manifest`). Both sit at the end of engines that
  genuinely work and are covered by tests, so guarding them would have deleted working
  functionality to silence a checker.
  **Both are now implemented on `EngagementStore`** rather than guarded, which is what the two
  engines needed to finish their own work: each was building a complete result and then dying with
  `AttributeError` on the last statement. They write to `reports/findings_report.json` and
  `reports/deliverable_manifest.json`, reusing `_atomic_write` (whose `default=str` covers the
  enums and datetimes `FindingsReport.model_dump()` leaves in place) and creating `reports/` if a
  caller skipped `init()`. Filenames are class constants (`FINDINGS_REPORT_FILE`,
  `DELIVERABLE_MANIFEST_FILE`) alongside the existing ones, not inline literals. Parameter names
  match the existing call sites exactly — `write_deliverable_manifest` is called with keywords.
  Covered by five tests in `tests/unit/test_persistence.py` against a real store on `tmp_path`.
  ~~**The eight read-side methods are still missing**, so the five CLI guards stay as they are. When
  those commands become real, these two writers pin down the on-disk layout the readers must
  match.~~
  **Closed — the eight read-side methods are implemented and the five guards are removed** (0.9.x
  follow-up, after the demo scope in `CNA-0.90-updates.md` §3 shipped). `EngagementStore` now has
  `load_aws_topology()` / `load_azure_topology()` (rebuilt from the per-region / per-subscription
  discovery checkpoints, since the root topology models are never persisted; the Azure tenant id is
  recovered from the first subscription checkpoint), `load_findings_report()`,
  `load_findings_report_json()` (the stored file text verbatim — DD-013 checksums the bytes on
  disk), `load_deliverable_manifest()`, `write_access_record()` / `load_access_record()`
  (`access_record.json` at the engagement root, metadata only), and `get_delivery_date()`
  (the publish record's `issued_at`, `None` until first publish — DD-019's "clock not started").
  Every missing-file path raises `FileNotFoundError` with a "run X first" message, the exact type
  the CLI commands catch. The CLI registry (`cna/cli/main.py`) now registers the real commands —
  including a real `cna init` and a new `cna review complete` (the DD-009 sign-off `cna report`
  names) — and the superseded "Phase X: TODO" stubs are deleted; `diagram` and `module` remain
  stubs pending their engines' CLI wiring. Two adjacent defects fixed in the process:
  `RenderPipeline._output_dir` hardcoded `./engagements` and ignored `--data-dir`, and
  `cna publish run` called signing methods against the `S3Deployer | AzureBlobDeployer` union
  (now per-branch closures). Covered per the recommendation: 13 read-side tests against a real
  store on `tmp_path` in `test_persistence.py`, plus `test_cli_pipeline.py` — 14 tests driving the
  registered CLI end-to-end (init → seeded checkpoints → analyze → review gate → report →
  publish status) with no mocks.
- **Notes for future engineers:** The existing tests never caught this because they mock the store.
  That is also how the `write_audit_event` `TypeError` fixed under T-402 survived. When testing
  anything that touches persistence, prefer a real `EngagementStore` pointed at `tmp_path`.

### T-413 — `FoundryAgentClient` is written against azure-ai-projects 1.x, but 2.x is declared

- **Priority:** High
- **Category:** Correctness / dependency mismatch
- **Description:** `cna/ai_engine/foundry_agent_client.py` drives the Foundry agent through
  `agents.threads.create()`, `agents.messages.create()`, and `agents.runs.create_and_process()`.
  Those belong to the **1.x** `azure-ai-projects` agents API. `pyproject.toml` declares
  `azure-ai-projects>=2.3.0`, and 2.x replaced that surface entirely — the installed 2.4.0 exposes
  `AgentsOperations` with `create_session`, `create_version`, `get`, `list`, and friends, and
  `hasattr` confirms **no** `threads`, `messages`, or `runs`. Every call in `run()` therefore raises
  `AttributeError` against the declared dependency.
  The failure is disguised: the whole body sits in `except Exception`, which re-raises as
  `FoundryAgentError("Foundry agent run failed: ...")`. A caller sees a generic agent failure, not a
  version mismatch. This is live code — `RecommendationEngine.__init__` constructs a
  `FoundryAgentClient` when none is injected. The existing tests pass because they only exercise the
  static `_parse()` helper, never the SDK path.
  Found only after `pip install -e .` made the real SDK available to the type checker; in a bare
  container the import is unresolved and the whole module goes unchecked.
- **Dependencies:** None.
- **Recommended action:** Decide which API is intended. Either pin `azure-ai-projects>=1.0,<2` and
  keep the current calls, or port `run()` and `_latest_assistant_text()` to the 2.x surface. Pinning
  backwards deserves a check that nothing else needs 2.x. Whichever way, add one test that exercises
  `run()` against a mocked client shaped like the *declared* SDK version, so the next divergence
  fails a test rather than a deployment.
- **Status:** Done — pinned back to 1.x, per the repository owner's decision, rather than porting
  `run()` to the 2.x surface. `pyproject.toml` now declares `azure-ai-projects>=1.0.0,<2`.
  **Pinning alone was not sufficient**, which is the part worth remembering. In 1.x,
  `AIProjectClient.agents` returns an `AgentsClient` from the **separate `azure-ai-agents`
  package** — that companion package provides `threads`, `messages`, and `runs`, not
  `azure-ai-projects` itself. It was undeclared, so a pin to 1.x on its own would have swapped one
  broken state for another. `azure-ai-agents>=1.1.0,<2` is now declared alongside it. That is the
  same undeclared-dependency class as T-414, found the same way.
  Verified at runtime rather than by the type checker alone: on the pinned pair,
  `AIProjectClient.agents` resolves to `AgentsClient`, and `.threads`, `.messages`, and
  `.runs.create_and_process` all exist. Note only `1.0.0` exists in the 1.x line — there is no
  newer 1.x to move to, so this pin is a ceiling as well as a floor.
- **Notes for future engineers:** Two `ty` findings remain on `project.agents` and are a **type-stub
  artifact, not a bug**: the `agents` property in `azure-ai-projects` 1.0.0 is annotated
  `-> AgentsClient` with a `# type: ignore[name-defined]`, because its companion package is imported
  lazily. The runtime chain is proven to work. Do not "fix" these by restructuring the call.
  Note also the interaction with the broad `except Exception` here. It is what turned a clear
  `AttributeError` into an opaque `FoundryAgentError`, hiding a total failure of this path behind a
  generic message — the same narrow-vs-broad question raised under T-404, and the concrete argument
  for it. If this is revisited, add a test that drives `run()` against a mock shaped like the
  *declared* SDK, so the next divergence fails a test rather than a deployment.

### T-414 — Ten imported packages are not declared as dependencies

- **Priority:** High
- **Category:** Packaging / silent feature loss
- **Description:** `cna/` imports ten distributions that appear nowhere in `pyproject.toml`:
  `azure-mgmt-monitor`, `azure-monitor-query`, `azure-mgmt-compute`, `azure-mgmt-security`,
  `azure-mgmt-privatedns`, `azure-mgmt-managementgroups`, `azure-mgmt-loganalytics`,
  `azure-mgmt-costmanagement`, `cairosvg`, and `mcp`. Confirmed by resolving every import against
  the declared set, and again after `pip install -e .` — the nine *declared* packages resolved, all
  ten of these did not.
  Every one is imported lazily inside `try: ... except ImportError:`, so nothing crashes — on a
  clean install the features simply never activate: Log Analytics diagnostic checks, alert-count
  collection, cost-management queries, private DNS and Compute enrichment, security-centre checks,
  SVG→PNG conversion, and both MCP clients. A deployment looks healthy while producing a thinner
  assessment than the code can generate.
  *(Correcting an earlier draft of this item: the handlers are **not** silent. All 24 `except
  ImportError` blocks in `cna/` either log — 18 at warning level, three at debug — record the reason
  into the model, or are legitimate capability probes. The gap was in the packaging, not the
  handlers.)*
- **Dependencies:** None. Related to T-413, which is the same class of problem from the other
  direction — a *declared* dependency at a version the code cannot use.
- **Recommended action:** Decide per package whether the feature is core or genuinely optional.
  Core ones belong in `[project] dependencies`; optional ones belong in a named extra (say
  `[project.optional-dependencies] enrichment`) with the `except ImportError` path logging a
  message naming the extra to install, rather than passing silently. Pin versions, per the CBTS
  standard for security-sensitive dependencies, and re-run `ty check cna/` afterwards — these ten
  account for all 15 remaining `unresolved-import` findings under T-410.
- **Status:** Done — declared as a `[project.optional-dependencies] enrichment` extra, installable
  with `pip install -e .[enrichment]`. An extra rather than core dependencies, because that matches
  what the code already does: every import is lazy and every handler degrades, so a default install
  behaves exactly as before and nothing new is forced on anyone.
  **The version bounds are the important part, and the obvious ones would have been wrong.** All ten
  install cleanly at their latest release, but installing them revealed that three have shipped a
  major that breaks this code — `managementgroups` 2.x renamed `ManagementGroupsAPI` to
  `ManagementGroupsMgmtClient`, `monitor` 7.x dropped `MonitorManagementClient.diagnostic_settings`,
  and `costmanagement` 5.x changed `QueryComparisonExpression`'s signature. A naive `>=latest` would
  have declared a dependency set the code cannot run against. Each bound was verified by installing
  the version and re-running `ty`; upper bounds are set on all ten, since this failure mode is now
  demonstrated three times over (four with T-413).
  Declaring them dropped `ty check cna/` from 24 diagnostics to **8**, and surfaced four more real
  defects that were invisible while the imports were unresolved — three fixed by the version bounds
  above, one fixed in code (`QueryDefinition` was passed a `dict` where `QueryTimePeriod` is
  declared; it now builds the model with datetimes, which is what its `iso-8601` attribute map
  expects).
- **Notes for future engineers:** The `except ImportError` blocks are doing real work — they keep a
  partial install running — so do not delete them when the extra is installed by default somewhere.
  If you bump any of these past its upper bound, re-run `ty check cna/` **with the package
  installed**: an unresolved import means the entire module goes unchecked, which is exactly how
  four defects hid here.

---

## Phase 5 — Feature enhancements

### T-501 — Implement workflow 212 as a functional AWS deploy

- **Priority:** High
- **Description:** `212-deploy-aws-split.yml` is a scaffold: it mirrors
  `211-deploy-azure-split.yml`'s input contract and job shape, but every job is a guard that fails
  fast. The real sequence — plan → apply → migrate → health verification — is unimplemented.
- **Dependencies:** T-101, T-201, T-301, T-302, and `REVIEW.md` → R-001 through R-006.
- **Recommended action:** Replace the guards job by job, keeping the input contract identical to
  211 so both clouds present one deploy interface. Reuse `scripts/ci/evaluate_deployment_evidence.py`
  for the verification gate rather than writing an AWS-specific evaluator.
- **Status:** Blocked
- **Notes for future engineers:** 211 does plan → apply → migrate → health verification and then
  syncs the Entra app home page URL and redirect URI to the current Front Door hostname. The AWS
  equivalent needs the same post-apply identity sync against the CloudFront domain — that step is
  easy to forget because it is not part of Terraform.

### T-502 — Optional Route 53 + ACM certificate validation flow

- **Priority:** Low
- **Description:** Certificates are inputs (`alb_certificate_arn`, `acm_certificate_arn`, default
  `null`) because minting an unvalidated `aws_acm_certificate` hangs on DNS validation. If the
  zone is hosted in Route 53, an `aws_acm_certificate` +
  `aws_acm_certificate_validation` pair can automate the whole flow.
- **Dependencies:** `REVIEW.md` → R-004 (the domain decision and zone ownership must be settled
  first).
- **Recommended action:** Add the validation flow behind a feature flag defaulting to off, so
  externally hosted DNS keeps the current input-ARN behaviour.
- **Status:** Blocked on R-004
- **Notes for future engineers:** The CloudFront viewer certificate must be in `us-east-1`
  regardless of deployment region — the repository already declares a `us-east-1` aliased provider
  for the CloudFront-scoped WAF; reuse it.

---

## Phase 6 — Documentation improvements

### T-601 — Publish the seven prepared Wiki pages

- **Priority:** Medium
- **Description:** The documentation consolidation displaced long-form content from `README.md`
  and from two non-root documents. Seven validated, ready-to-publish pages were prepared. They are
  not committed to the repository — publishing requires Wiki write access, which the automation
  performing the consolidation does not have.
- **Dependencies:** `REVIEW.md` → R-009 (Wiki write access).
- **Recommended action:** Publish, or merge into existing pages:

  | Page | Content |
  |---|---|
  | `Architecture` | Container topology, RG layout, split-state model, AWS topology, design contracts DD-002…DD-019, capability inventory, naming convention |
  | `Security Posture` | Standing controls, the 2026-07-01 AVM/Learn hardening pass (#111), break-glass login hardening (#112), AWS-side controls |
  | `Workflows Guide` | Per-workflow reference for 000–370, clean-deploy sequence, teardown sequence |
  | `Azure Operating Notes` | Managed RG naming, tfstate RG separation, provider registration, Entra sync, workspace ownership, retention |
  | `AWS Deployment Setup` | Parity matrix, backend bootstrap, identity, secrets, ACM, Bedrock, deploy order, nine VPC endpoints |
  | `Runbook: Log Analytics Workspace State Migration` | The state-surgery procedure now held in T-304 |
  | `Legacy AWS Migrate Root` | The superseded `migrate/` root, IAM policy mapping preserved |

  Then add the links to `README.md`'s documentation map.
- **Status:** Blocked on R-009
- **Notes for future engineers:** `Workflows Guide` and `Secrets Reference` are already referenced
  by `.env.example`, so those pages likely exist — merge rather than create, and do not duplicate.
  The page content is attached to the pull request that introduced this backlog. Nothing is lost
  if it is never published: every fact in those pages is either still in the repository or carried
  in a TODO item's handoff notes.

### T-602 — Trim the long-form runbook content out of TODO.md once the Wiki has it

- **Priority:** Low
- **Description:** `TODO.md` → T-304 currently carries the full Log Analytics workspace state
  migration runbook, and T-401 carries the `migrate/` directory reference. That content is
  operational documentation living in the engineering backlog because the Wiki was unreachable
  when the two source files were removed. It is the right fallback, not the right home.
- **Dependencies:** T-601 (the Wiki pages must exist first).
- **Recommended action:** Once `Runbook: Log Analytics Workspace State Migration` and
  `Legacy AWS Migrate Root` are published and verified, replace the inline procedures in T-304 and
  T-401 with a one-line summary plus the Wiki link.
- **Status:** Blocked on T-601
- **Notes for future engineers:** Do not trim before the Wiki pages are confirmed published and
  rendering. These notes are currently the only copy of that content in the repository.

### T-603 — Add a CI guard for the documentation model

- **Priority:** Low
- **Description:** Nothing prevents documentation sprawl from returning. The model allows exactly
  four markdown files in the repository — `README.md`, `CHANGELOG.md`, `REVIEW.md`, `TODO.md` —
  plus platform-required files under `.github/`.
- **Dependencies:** None — the repository already satisfies the rule, so the guard can be added
  and will pass immediately.
- **Recommended action:** Add a check to `300-test-codebase.yml` that fails when a markdown file
  appears outside that allow-list. Exclude the vendored agent configuration under `.claude/` and
  `.agents/`, matching the exclusion `pyproject.toml` already applies to ruff.
- **Status:** Done — `scripts/validate_documentation_model.py` added and wired into the
  `repository-guardrails` job of `300-test-codebase.yml`, alongside the existing module-dependency
  and shape-catalog guards. It excludes `.claude/`, `.agents/`, and `.codex/`, and pre-allows the
  platform-required `.github/` documents named in the notes below. Recorded in
  [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** The allow-list must also permit the platform-required
  `.github/` documents (`PULL_REQUEST_TEMPLATE.md`, `SECURITY.md`, `CONTRIBUTING.md`, and the
  like) if any are added later — none exist today.

### T-604 — Keep vendored agent configuration free of project documentation

- **Priority:** Low
- **Description:** `.claude/` and `.agents/` hold a vendored, deliberately project-neutral Claude
  Code agent pack — agents, skills, doctrine, orchestration, and playbooks. `pyproject.toml`
  already excludes both from ruff on the grounds that they are "vendored Claude Code agent/skill
  configuration, not this repo's own source", and the pack's own documentation states that nothing
  in `.claude/` may name a client, tenant, or account. They are treated as configuration, not
  documentation, and are out of scope for the documentation model.
- **Dependencies:** T-603 (the guard's exclusion list encodes this decision).
- **Recommended action:** Periodically confirm no project-specific documentation has been written
  into either directory. If any appears, classify it by content and move it to `README.md`,
  `CHANGELOG.md`, `REVIEW.md`, `TODO.md`, or the Wiki as the model requires.
- **Status:** Not started
- **Notes for future engineers:** The distinction that matters is *project-specific* versus
  *project-neutral*. Project-neutral agent knowledge stays in the pack — it is what lets the pack
  drop into another repository unchanged. Anything naming this platform, its subscriptions, or its
  clients does not belong there.

### T-605 — The documentation-model guard enforces "at most four", not "exactly four"

- **Priority:** Medium
- **Category:** CI correctness / documentation model
- **Description:** `scripts/validate_documentation_model.py` only reports markdown files that are
  **not** on the allow-list. It never checks that the four required documents exist. Deleting
  `README.md`, `CHANGELOG.md`, `REVIEW.md`, and `TODO.md` in the same commit leaves the guard
  passing. Reproduced against a fixture repository containing only `scripts/` and no root
  documents: exit 0, `Documentation model OK: no markdown files outside the allow-list.` Both
  `README.md` → "Repository conventions" and T-603 state the model as *exactly* four documents, so
  the guard currently enforces half of the rule it was added for — and the missing half is the one
  that protects the single source of truth.
- **Dependencies:** None.
- **Recommended action:** Add a presence check to `validate()` before the sprawl scan, and report
  both classes of violation in one run so a contributor sees the full picture:

  ```python
  missing = sorted(
      name for name in ALLOWED_ROOT_DOCUMENTS if not (REPO_ROOT / name).is_file()
  )
  if missing:
      print("Documentation model violation — required document(s) missing:")
      for name in missing:
          print(f"  {name}")
  ```

  Return `False` when either `missing` or `violations` is non-empty.
- **Status:** Done — `validate()` now builds a `missing` list from the enumerated root documents and
  returns `False` when either `missing` or `violations` is non-empty, reporting both classes in one
  run. Covered by `tests/unit/test_guardrail_scripts.py` (parametrised over each of the four
  documents, plus the delete-all-four case that previously passed). Recorded in
  [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** `ALLOWED_ROOT_DOCUMENTS` is a `set`, so sort before printing —
  unordered output makes CI logs harder to diff between runs.

### T-606 — The documentation-model guard misses mixed-case and non-`.md` documentation

- **Priority:** Medium
- **Category:** CI correctness / documentation model
- **Description:** The scan is `REPO_ROOT.rglob("*.md")` (line 68), which on Linux is
  case-sensitive and matches one extension. Four sprawl patterns were confirmed to pass the guard
  against a fixture repository, each of which GitHub renders as a document:
  `docs/ROADMAP.MD` (exit 0), `NOTES.Md` at the repository root (exit 0), `docs/NOTES.markdown`
  (exit 0), and `docs/PLAN.rst` (exit 0). Only lowercase `.md` is caught. T-603's stated purpose is
  that "nothing prevents documentation sprawl from returning"; a contributor on a
  case-insensitive filesystem creating `ROADMAP.MD` reintroduces it without CI noticing.
- **Dependencies:** T-605 (same function, land together).
- **Recommended action:** Match on a case-folded suffix set rather than a glob pattern:

  ```python
  DOCUMENT_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".rst", ".adoc"}

  candidates = (
      p for p in REPO_ROOT.rglob("*")
      if p.is_file() and p.suffix.lower() in DOCUMENT_SUFFIXES
  )
  ```

  Compare allow-list membership case-insensitively too, so `readme.md` is not treated as a fifth
  document. Keep the `is_excluded()` short-circuit ahead of the suffix test — the vendored packs
  hold ~5,700 markdown files and are the bulk of the walk.
- **Status:** Done — the glob was replaced by a case-folded `DOCUMENT_SUFFIXES` set (13 extensions;
  the recommended six plus `.asciidoc`, `.textile`, `.rdoc`, `.org`, `.pod`, `.creole`, `.wiki`),
  and root allow-list membership is compared case-insensitively. All four confirmed sprawl patterns
  are now caught, each as a regression case in `tests/unit/test_guardrail_scripts.py`. Recorded in
  [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** Runtime is not a concern: the current full-repository walk over
  5,712 markdown files completes in ~0.12 s locally, and CI checks out clean so `node_modules/`
  is absent. Prefer correctness over cleverness here.

### T-607 — Align guard diagnostics and the `.codex` lint claim with what the code does

- **Priority:** Low
- **Category:** Consistency / documentation accuracy
- **Description:** Two small mismatches introduced alongside the guard:
  1. `validate_documentation_model.py` prints its failure report to `stdout`;
     `validate_shape_catalog.py` prints failures to `stderr`. Two guards in the same CI job report
     failures on different streams, so log capture and annotation behave differently per guard.
  2. The script's module docstring says vendored directories are excluded "matching the ruff
     exclusion in `pyproject.toml`", and `README.md` → "Repository conventions" says `.claude/`,
     `.agents/`, and `.codex/` are "excluded from lint (see `pyproject.toml`)". `pyproject.toml`'s
     `[tool.ruff] extend-exclude` lists only `.claude` and `.agents` — `.codex` is absent. The
     claim is harmless today because `.codex/` contains only `.toml` files (0 `.py`, 0 `.md`), so
     ruff would not lint it regardless, but the statement is not true as written.
- **Dependencies:** None.
- **Recommended action:** Print the violation report to `stderr` in
  `validate_documentation_model.py`, matching `validate_shape_catalog.py`. Then either add
  `".codex"` to `extend-exclude` in `pyproject.toml` — making both statements true and future-proof
  if `.codex/` ever gains Python — or reword the README bullet and the docstring to name only the
  two directories ruff actually excludes. Adding the exclusion is the lower-maintenance option.
- **Status:** Done — both mismatches resolved. The violation report now prints to `stderr`, matching
  `validate_shape_catalog.py` (asserted in `tests/unit/test_guardrail_scripts.py`, which checks
  `stdout` is empty on failure). `".codex"` was added to `[tool.ruff] extend-exclude` in
  `pyproject.toml` — the lower-maintenance option named in the recommended action — making the
  docstring and the README bullet true as written. Recorded in [`CHANGELOG.md`](CHANGELOG.md) →
  Unreleased.
- **Notes for future engineers:** Decide this once and make the docstring, the README bullet, and
  `pyproject.toml` agree. This is precisely the drift class the `documentation-curator` agent added
  in the same commit is meant to catch, which makes it a useful first exercise for that agent.

### T-608 — The documentation-model guard fails on gitignored build artifacts

- **Priority:** High
- **Category:** CI correctness / developer experience
- **Description:** The guard walks the **filesystem** (`REPO_ROOT.rglob`), not the set of files git
  tracks, and `EXCLUDED_DIRS` is a hand-maintained list that covers `node_modules`, `.venv`, and
  `venv` but not the tool caches this repository actually produces. Running the test suite creates
  `.pytest_cache/README.md` — a file pytest writes itself, gitignored at `.gitignore:31` and
  untracked — after which the guard fails:

  ```
  $ python3 -m pytest -q          # writes .pytest_cache/README.md
  $ python3 scripts/validate_documentation_model.py
  Documentation model violation — the repository keeps exactly four
  markdown documents (README.md, CHANGELOG.md, REVIEW.md, TODO.md).
    .pytest_cache/README.md
  Move the content to one of the four documents or the Wiki
  (content determines destination), then delete the file.          # exit 1
  ```

  The advice is nonsense for a pytest artifact, and the script's own docstring advertises that it
  "can be run locally" — running the tests first is the normal developer sequence, so the guard
  fails for most people who try it. CI is unaffected today only because `actions/checkout` runs
  `git clean -ffdx` on the self-hosted workspace before the job. That makes this a latent CI
  failure too: any tool cache created *during* a job before the guardrails step would trip it.
- **Dependencies:** None. Land before or with T-605/T-606 — all three change the same scan.
- **Recommended action:** Enumerate candidates from git rather than from the filesystem, which
  matches the rule being enforced ("the *repository* keeps four documents" — untracked scratch is
  not the repository) and removes the need to maintain `EXCLUDED_DIRS` at all:

  ```python
  import subprocess

  def tracked_files() -> list[Path]:
      out = subprocess.run(
          ["git", "-C", str(REPO_ROOT), "ls-files", "-z"],
          capture_output=True, text=True, check=True,
      ).stdout
      return [Path(p) for p in out.split("\0") if p]
  ```

  Keep the vendored-pack exclusion (`.claude/`, `.agents/`, `.codex/` are tracked and must stay
  out of scope). If a git dependency is unwanted in this script, the minimum viable fix is adding
  `.pytest_cache`, `.ruff_cache`, `.mypy_cache`, `htmlcov`, `.next`, `dist`, and `build` to
  `EXCLUDED_DIRS` — but that list will drift again the next time a tool is added.
- **Status:** Done — candidates now come from `git ls-files -z` via a `tracked_files()` helper rather
  than `REPO_ROOT.rglob`, so untracked scratch is out of scope by construction. Verified against the
  exact reproduction: `.pytest_cache/README.md` present, guard exits 0. `EXCLUDED_DIRS` was kept
  (not removed as the recommended action suggested) because `.claude/`, `.agents/`, and `.codex/`
  hold *tracked* files that must still be excluded per T-604. Recorded in
  [`CHANGELOG.md`](CHANGELOG.md) → Unreleased.
- **Notes for future engineers:** `git ls-files` also fixes the reverse hole — a file that is
  committed but sits under a directory someone later adds to `EXCLUDED_DIRS` stops being checked.
  Note `subprocess` triggers ruff's `S603`, which `pyproject.toml` already ignores repository-wide.
