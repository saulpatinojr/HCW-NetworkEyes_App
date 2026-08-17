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
| [Phase 4](#phase-4--technical-debt) | Technical debt | T-401 – T-406 |
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
- **Status:** Not started
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
- **Dependencies:** `REVIEW.md` → R-007 (the subscription owner must register it first; this task
  makes the failure detectable, it does not resolve it).
- **Recommended action:** Add a registration-state assertion to `100-validate-prereqs.yml`,
  failing with a message that names the provider and points at `REVIEW.md` → R-007.
- **Status:** Not started
- **Notes for future engineers:** Check whether any other provider registration is assumed by the
  Azure roots while adding this — the same class of late failure applies to every one of them.

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
- **Status:** Not started
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
- **Status:** Not started
- **Notes for future engineers:** AWS permits exactly one GitHub OIDC provider per account. If the
  target account already has one, the module must import it rather than create it — a duplicate
  create fails the whole apply.

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
- **Status:** Not started
- **Notes for future engineers:** CI already runs a `pip-audit` job in `300-test-codebase.yml`,
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
- **Status:** Not started
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
- **Status:** Not started
- **Notes for future engineers:** `ruff` is already clean across `cna/` (109 files formatted, all
  checks passing) with `select = E,W,F,I,B,C4,UP,S,N` and `target-version = "py311"`. Match that
  strictness posture. Do not widen ignore lists to make the first type-check run pass.

### T-403 — Close the coverage gap on discovery orchestrator `run()` paths

- **Priority:** Medium
- **Description:** `[tool.coverage.report] fail_under = 80`. The Python review identified the
  discovery orchestrators' `run()` paths as the least-tested and highest-risk code in the package.
- **Dependencies:** None.
- **Recommended action:** Add unit coverage for the AWS and Azure discovery orchestrator entry
  points, including the error and retry branches, before adding further discovery features.
- **Status:** Not started
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
- **Status:** Not started
- **Notes for future engineers:** The convention to converge on is the Azure one — it is the older
  and more exercised path. Any behavioural change should be called out explicitly rather than
  landed silently.

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
  `stderr`. The `pre-commit` hook (recommended action 3) was deliberately left undone — this
  repository has no `.pre-commit-config.yaml` and adding one is a separate decision about local
  tooling, not part of closing the test gap. `validate_shape_catalog.py` is covered only by a
  "still passes against this repository" assertion; it reads a hardcoded catalog path and has no
  fixture seam, so a violating-fixture test for it needs a small refactor first.

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
