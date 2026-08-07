# TODO — engineering work queue

The authoritative engineering backlog for this repository. Every actionable engineering item
discovered anywhere in the repository lives here, ordered by phase and dependency so an engineer
can pick up work without rediscovering the findings.

Items requiring external input — an approval, an account, a credential, an access grant — belong
in [`REVIEW.md`](REVIEW.md), not here. Completed work is recorded in [`CHANGELOG.md`](CHANGELOG.md).

**Last reviewed:** 2026-08-07

| Phase | Theme | Items |
|---|---|---|
| [Phase 1](#phase-1--critical-fixes) | Critical fixes — repository states something untrue | T-101 – T-104 |
| [Phase 2](#phase-2--security-improvements) | Security improvements | T-201 – T-203 |
| [Phase 3](#phase-3--deployment-readiness) | Deployment readiness | T-301 – T-305 |
| [Phase 4](#phase-4--technical-debt) | Technical debt | T-401 – T-405 |
| [Phase 5](#phase-5--feature-enhancements) | Feature enhancements | T-501 – T-502 |
| [Phase 6](#phase-6--documentation-improvements) | Documentation improvements | T-601 – T-605 |

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
- **Status:** Not started
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
- **Recommended action:** Follow the state-migration runbook before the next apply in any affected
  environment. The runbook currently lives at
  `infra/terraform/MIGRATION-workspace-to-platform.md` and is queued for Wiki migration (T-601).
- **Status:** Not started — not currently applicable
- **Notes for future engineers:** Short version: back up both states with `terraform state pull`,
  `terraform state rm 'module.compute.azurerm_log_analytics_workspace.compute'` from workload,
  `terraform import 'azurerm_log_analytics_workspace.platform' <resource-id>` into platform, verify
  both plans are clean, then apply platform before workload. Stop and investigate if platform still
  wants to *create* the workspace or workload still wants to *destroy* it.

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
- **Dependencies:** T-203 benefits from resolving this; T-602 (Wiki migration of
  `migrate/README.md`) must complete before the directory is deleted.
- **Recommended action:** Confirm `migrate/` is fully superseded, extract anything the current
  modules lack — the three assessment-level IAM policies it documents (`ReadOnlyAccess` /
  Global Reader, `SecurityAudit` / Security Reader, `AWSBillingReadOnlyAccess` / Billing Reader)
  are worth checking against the current `identity` module — then delete the directory and its
  bootstrap script.
- **Status:** Not started
- **Notes for future engineers:** The current stack supersedes `migrate/` on every axis: eight
  module boundaries mirroring Azure, split platform/workload state, VPC endpoints, X-Ray, Bedrock,
  and autoscaling. `migrate/` has none of those. Treat it as history, not as an alternative.

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

### T-601 — Migrate the workspace state-migration runbook to the Wiki

- **Priority:** Medium
- **Description:** `infra/terraform/MIGRATION-workspace-to-platform.md` is an operational runbook.
  Operational runbooks belong in the GitHub Wiki, not in the repository tree.
- **Dependencies:** `REVIEW.md` → R-009 (Wiki write access).
- **Recommended action:** Publish as the Wiki page **`Runbook: Log Analytics Workspace State
  Migration`**, verify the page renders and its code blocks and state addresses survived intact,
  update the `TODO.md` → T-304 pointer to the Wiki URL, then delete the source file.
- **Status:** Blocked on R-009
- **Notes for future engineers:** Do not delete the source file before the Wiki page is confirmed
  published. Validated page content was prepared alongside this backlog and attached to the pull
  request that introduced it.

### T-602 — Migrate the non-root `migrate/README.md` to the Wiki

- **Priority:** Medium
- **Description:** `migrate/README.md` is a non-root README, which the documentation model treats
  as documentation rather than repository metadata. Its content is the architecture mapping, IAM
  model, bootstrap procedure, and deployment steps for the superseded `migrate/` Terraform root.
- **Dependencies:** `REVIEW.md` → R-009. Interacts with T-401 — if `migrate/` is deleted outright,
  the page becomes historical reference rather than a live procedure.
- **Recommended action:** Publish as the Wiki page **`Legacy AWS Migrate Root`**, clearly marked
  superseded by `infra/terraform/{providers,environments}/aws/`, then delete the source file.
- **Status:** Blocked on R-009
- **Notes for future engineers:** The one genuinely useful thing in that document is the
  assessment-level IAM policy mapping (`ReadOnlyAccess` ↔ Global Reader, `SecurityAudit` ↔
  Security Reader, `AWSBillingReadOnlyAccess` ↔ Billing Reader). Preserve it — and check it against
  the current `identity` module while you are there (T-401).

### T-603 — Publish the long-form pages displaced from `README.md`

- **Priority:** Medium
- **Description:** `README.md` was reduced to repository purpose, quick start, configuration, and
  navigation. The architecture description, design contracts, security posture detail, per-workflow
  reference, Azure operating notes, and the AWS deployment-setup reference were displaced and need
  Wiki homes.
- **Dependencies:** `REVIEW.md` → R-009.
- **Recommended action:** Publish or merge into: **`Architecture`** (container topology, resource
  group layout, design contracts DD-002/003/008/009/013/019), **`Security Posture`** (CI pinning,
  secret scanning, non-root containers, OIDC, WAF and break-glass hardening history),
  **`Workflows Guide`** (per-workflow reference for 000–370), **`Azure Operating Notes`** (managed
  RG naming, tfstate RG separation, provider registration, Entra sync), and
  **`AWS Deployment Setup`** (backend bootstrap, identity, secrets, certificates, Bedrock, deploy
  order, VPC endpoints). Then add the links to `README.md`'s documentation map.
- **Status:** Blocked on R-009
- **Notes for future engineers:** `Workflows Guide` and `Secrets Reference` are already referenced
  by `.env.example`, so those two pages likely exist — merge rather than create, and do not
  duplicate.

### T-604 — Add a CI guard for the documentation model

- **Priority:** Low
- **Description:** Nothing prevents documentation sprawl from returning. The model allows exactly
  four markdown files in the repository — `README.md`, `CHANGELOG.md`, `REVIEW.md`, `TODO.md` —
  plus platform-required files under `.github/`.
- **Dependencies:** T-601, T-602 (the guard cannot pass until the two Wiki-bound files are gone).
- **Recommended action:** Add a check to `300-test-codebase.yml` that fails when a markdown file
  appears outside that allow-list. Exclude the vendored agent configuration under `.claude/` and
  `.agents/`, matching the exclusion `pyproject.toml` already applies to ruff.
- **Status:** Blocked on T-601, T-602
- **Notes for future engineers:** The allow-list must also permit the platform-required
  `.github/` documents (`PULL_REQUEST_TEMPLATE.md`, `SECURITY.md`, `CONTRIBUTING.md`, and the
  like) if any are added later — none exist today.

### T-605 — Keep vendored agent configuration free of project documentation

- **Priority:** Low
- **Description:** `.claude/` and `.agents/` hold a vendored, deliberately project-neutral Claude
  Code agent pack — agents, skills, doctrine, orchestration, and playbooks. `pyproject.toml`
  already excludes both from ruff on the grounds that they are "vendored Claude Code agent/skill
  configuration, not this repo's own source", and the pack's own documentation states that nothing
  in `.claude/` may name a client, tenant, or account. They are treated as configuration, not
  documentation, and are out of scope for the documentation model.
- **Dependencies:** T-604 (the guard's exclusion list encodes this decision).
- **Recommended action:** Periodically confirm no project-specific documentation has been written
  into either directory. If any appears, classify it by content and move it to `README.md`,
  `CHANGELOG.md`, `REVIEW.md`, `TODO.md`, or the Wiki as the model requires.
- **Status:** Not started
- **Notes for future engineers:** The distinction that matters is *project-specific* versus
  *project-neutral*. Project-neutral agent knowledge stays in the pack — it is what lets the pack
  drop into another repository unchanged. Anything naming this platform, its subscriptions, or its
  clients does not belong there.
