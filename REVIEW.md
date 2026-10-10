# Review — human-resolvable blockers

This file tracks **only** items that an engineer cannot resolve independently. Every entry
requires external input: an approval, a credential, an account, an access grant, or a decision
that belongs to a named owner outside the engineering task itself.

Anything an engineer can solve without external input belongs in [`TODO.md`](TODO.md), not here.

**Last reviewed:** 2026-09-23

| ID | Blocker | Owner | Status |
|---|---|---|---|
| [R-001](#r-001--aws-account-and-administrative-access) | AWS account + administrative access for first deploy | AWS account owner | Open — tracked in the AWS appliance's `REVIEW.md` (R-001); deploy layer moved 2026-09-15 |
| [R-002](#r-002--terraform-s3-state-backend-must-be-created-out-of-band) | Terraform S3 state backend + DynamoDB lock table | AWS account owner | Open — tracked in the AWS appliance's `REVIEW.md` (R-002); deploy layer moved 2026-09-15 |
| [R-003](#r-003--github-oidc-deploy-role-must-be-wired-into-ci) | GitHub OIDC deploy role wired into CI secrets | Repository admin | Open — tracked in the AWS appliance's `REVIEW.md` (R-003); deploy layer moved 2026-09-15 |
| [R-004](#r-004--acm-certificates-and-custom-domain-decision) | ACM certificates + custom-domain decision | DNS / domain owner | Open — tracked in the AWS appliance's `REVIEW.md` (R-004); deploy layer moved 2026-09-15 |
| [R-005](#r-005--amazon-bedrock-model-access-opt-in) | Amazon Bedrock foundation-model access opt-in | AWS account owner | Open — tracked in the AWS appliance's `REVIEW.md` (R-005); deploy layer moved 2026-09-15 |
| [R-006](#r-006--runtime-secrets-have-no-defaults-and-must-be-supplied) | Runtime secrets supplied at apply time | Security / secret owner | Open — tracked in the AWS appliance's `REVIEW.md` (R-008); transferred 2026-09-15 |
| [R-007](#r-007--azure-subscription-resource-provider-registration) | `Microsoft.AlertsManagement` provider registration | Azure subscription owner | Resolved — no longer required |
| [R-008](#r-008--live-azure-beta-acceptance-sign-off) | 0.8 beta exit — live Azure acceptance sign-off | Product owner | Open — deploy done 2026-08-28, acceptance outstanding; tracked in the Azure appliance's `REVIEW.md` (R-003); transferred 2026-09-15 |
| [R-009](#r-009--github-wiki-write-access-for-documentation-migration) | GitHub Wiki write access to publish prepared pages | Repository owner | Open — not blocking |
| [R-010](#r-010--the-dev-environment-has-no-protection-against-out-of-band-deletion) | Dev environment deleted out of band; no protection against a repeat | Azure subscription owner | Open — tracked in the Azure appliance's `REVIEW.md` (R-004); transferred 2026-09-15 |
| [R-011](#r-011--security-review-of-the-bring-your-own-ai-key-path-and-provider-egress) | Security review: bring-your-own AI key handling + firewall egress to Anthropic/OpenAI | Security | Open — before the first `byo-api` deploy |
| [R-012](#r-012--token-for-a-shared-project-board-across-three-repositories) | Token type for a shared project board (PAT vs GitHub App / organization) | Repository owner | Open — not blocking |
| [R-013](#r-013--bring-the-core-repository-live-and-cut-the-appliances-over-to-it) | Bring `Work-Cloud_Network_Core` live: secrets, variables, GitHub App, `CORE_REPO` flip | Repository owner | Open — blocks the first image build from this repository |
| [R-014](#r-014--move-the-wiki-and-delete-the-original-repository) | Move the Wiki, then delete `Work-Cloud_Network_Assessment` | Repository owner | Open — pre-deletion checklist; engineering checks done 2026-09-24 |
| [R-015](#r-015--decide-the-customer-facing-appliance-repository-names) | Decide the customer-facing appliance repository names (`*_Appliance` vs `*_Assessment`) | Repository owner | Open — not blocking |
| [R-016](#r-016--retire-appscna-worker-and-its-image-service-and-catalog-slot) | Retire `apps/cna-worker` — placeholder deployed as an always-on service in both appliances | Repository owner | Open — v1.0 review finding IMG-003 / ARCH-101 |
| [R-017](#r-017--stop-publishing-the-cli-image-on-every-push) | Stop building/publishing the CLI image `cna:sha-<7>` (no appliance consumes it) | Repository owner | Open — not blocking |
| [R-018](#r-018--remove-cnareview-from-the-shipped-package) | Move `cna/review/**` out of the shipped package and API image | Repository owner | Open — not blocking |
| [R-019](#r-019--diagram-editor-sends-customer-topology-to-embeddiagramsnet) | Diagram editor posts customer topology XML to public `embed.diagrams.net`; no offline path | Product owner / Security | Open — data-governance decision |
| [R-020](#r-020--aeonik-font-licence-and-oci-licence-label) | Aeonik typeface licence coverage; OCI label `Proprietary` vs Apache-2.0 `LICENSE` | Legal / brand | Open — [VERIFY] |
| [R-021](#r-021--byo-api-mode-scope-for-10) | Ship 1.0 `saas`-only or complete R-011 first | Product owner / Security | Open |
| [R-022](#r-022--version-100-release-identity) | Version 1.0.0 identity: withdrawn `[1.0.0]` heading, version strings, first tag | Repository owner | Open — before the first `v*` tag |

---

## R-001 — AWS account and administrative access

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left the core with `TODO.md` → T-504 and live in the AWS appliance repository, where the blocker is tracked as **R-001** with paths rebased to `infra/terraform/modules/`. This entry is kept for history and for the references below; resolve it there.

**Problem**
The AWS Terraform under `infra/terraform/providers/aws/` and
`infra/terraform/environments/aws/` declares real resources across all eight module boundaries
(90 resources total), but none of it has ever been applied. There is no AWS account, no
administrative principal, and no bootstrap identity available to the engineering team.

**Why it blocks progress**
No AWS deployment step can begin. `terraform init` cannot reach a backend, `terraform plan`
cannot authenticate, and workflow `212-deploy-aws-split.yml` cannot be made functional. This is
the root dependency for R-002 through R-006.

**Required owner**
AWS account owner / cloud finance approver (account creation carries a billing commitment).

**Required action**
1. Provision or nominate the AWS account(s) for `dev` and `prod`.
2. Confirm the deployment region (the Terraform takes it as `var.aws_region`; a fixed
   `us-east-1` aliased provider is used for the CloudFront-scoped WAF regardless).
3. Grant an engineer a principal able to create IAM roles, an OIDC provider, S3, DynamoDB,
   VPC, ECS, RDS, CloudFront, WAFv2, KMS, Secrets Manager, and CloudWatch resources.

**Impact if unresolved**
AWS parity work stays code-only indefinitely. The repository continues to advertise an AWS
deployment path that cannot be executed, and the AWS half of the platform cannot be validated
before a customer engagement.

**References**
- `infra/terraform/providers/aws/` (ai, compute, database, identity, observability, runtime,
  security, storage)
- `infra/terraform/environments/aws/{dev,prod}/{platform,workload}/`
- `.github/workflows/212-deploy-aws-split.yml`
- Tracking issue #110 in the original repository (deleted — R-014)

**Recommended next step**
Name the account owner and confirm the target region and environment count (dev-only first, or
dev + prod together) before any further AWS engineering effort is scheduled.

---

## R-002 — Terraform S3 state backend must be created out of band

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left the core with `TODO.md` → T-504 and live in the AWS appliance repository, where the blocker is tracked as **R-002** with paths rebased to `infra/terraform/modules/`. This entry is kept for history and for the references below; resolve it there.

**Problem**
Every AWS root uses an empty `backend "s3" {}` block — the same init-time-configuration pattern
the Azure side uses for `backend "azurerm" {}`. The bucket and lock table must exist before the
first `terraform init`, and Terraform cannot create the backend it is about to use.

**Why it blocks progress**
`terraform init` fails without `-backend-config` values pointing at a real bucket and table. The
platform state and the workload state are separate, so both keys must be agreed before the first
plan.

**Required owner**
AWS account owner (depends on R-001).

**Required action**
Create, out of band or via a one-time bootstrap job mirroring Azure's
`000-bootstrap-backend.yml`:

| Input | What it is | How it is supplied |
|---|---|---|
| State bucket | S3 bucket for Terraform state, versioning + SSE enabled | `terraform init -backend-config="bucket=..."` |
| Lock table | DynamoDB table with a `LockID` (S) partition key | `-backend-config="dynamodb_table=..."` |
| State key | State object path | `-backend-config="key=aws/<env>/<platform\|workload>.tfstate"` |
| Region | Backend region | `-backend-config="region=..."` |

**Impact if unresolved**
No AWS Terraform command past `validate` can run. State would otherwise be local and
unshareable, which is unsafe for a CI-driven deploy.

**References**
- `infra/terraform/environments/aws/{dev,prod}/{platform,workload}/providers.tf`
- `.github/workflows/000-bootstrap-backend.yml` (the Azure equivalent to mirror)

**Recommended next step**
Decide bucket and table naming (the Azure convention is
`rg-cna-<env>-<region_short>-tfstate`; mirror it for AWS), then create them and record the four
`-backend-config` values in the repository's Actions variables.

---

## R-003 — GitHub OIDC deploy role must be wired into CI

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left the core with `TODO.md` → T-504 and live in the AWS appliance repository, where the blocker is tracked as **R-003** with paths rebased to `infra/terraform/modules/`. This entry is kept for history and for the references below; resolve it there.

**Problem**
The `identity` module provisions the GitHub OIDC provider and a deploy role assumable via
`AssumeRoleWithWebIdentity`, and exports it as the `github_deploy_role_arn` output. Nothing
consumes that output. CI trigger configuration was deliberately left out of scope of the AWS
code-generation work.

**Why it blocks progress**
Workflow `212-deploy-aws-split.yml` has no credential to assume, so it cannot authenticate to AWS
even once the guards are removed. The role ARN is account-specific and cannot be committed.

**Required owner**
Repository admin (GitHub secrets/variables) together with the AWS account owner (role creation).

**Required action**
1. Supply `github_owner` and `github_repository` as real values — they currently default to
   `<GITHUB_OWNER_PLACEHOLDER>` / `<GITHUB_REPO_PLACEHOLDER>` in
   `infra/terraform/providers/aws/identity/variables.tf` and
   `infra/terraform/environments/aws/{dev,prod}/workload/variables.tf`.
2. Apply the `identity` module, or import an existing OIDC provider if the account already has
   one (AWS permits only one GitHub OIDC provider per account).
3. Store the resulting `github_deploy_role_arn` as a repository secret and reference it from
   workflow 212.

**Impact if unresolved**
AWS CI/CD stays non-functional. Any interim workaround would mean long-lived AWS access keys in
GitHub, which contradicts the repository's OIDC-only credential policy.

**References**
- `infra/terraform/providers/aws/identity/` (`aws_iam_openid_connect_provider.github`)
- `.github/workflows/212-deploy-aws-split.yml`
- Related engineering task: [`TODO.md`](TODO.md) → T-201, T-202

**Recommended next step**
Confirm whether the target account already has a GitHub OIDC provider. If it does, the module
must import it rather than create it — plan for that before the first apply.

---

## R-004 — ACM certificates and custom-domain decision

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left the core with `TODO.md` → T-504 and live in the AWS appliance repository, where the blocker is tracked as **R-004** with paths rebased to `infra/terraform/modules/`. This entry is kept for history and for the references below; resolve it there.

**Problem**
TLS certificates are taken as **inputs** (`alb_certificate_arn`, `acm_certificate_arn`, both
defaulting to `null`). The Terraform deliberately does not mint an `aws_acm_certificate`, because
an unvalidated certificate resource hangs waiting on DNS validation.

**Why it blocks progress**
Without certificate ARNs the ALB HTTPS listener and the CloudFront viewer certificate cannot be
configured. The CloudFront certificate additionally **must** live in `us-east-1` regardless of
the deployment region.

**Required owner**
DNS / domain owner (certificate request and DNS validation records), with product input on
whether a custom domain is in scope for beta.

**Required action**
1. Decide whether the beta uses a custom domain (`custom_domain_name`, default `""`) or the
   generated CloudFront domain.
2. If a custom domain is used: request the two ACM certificates (regional for the ALB,
   `us-east-1` for CloudFront), publish the DNS validation records, and pass both ARNs in.
3. If Route 53 hosts the zone, an `aws_acm_certificate_validation` flow can be added instead —
   that is an engineering task once the zone owner is confirmed (see `TODO.md` → T-502).

**Impact if unresolved**
The AWS stack can only be deployed without HTTPS termination at the edge, which is not
acceptable for a client-facing delivery portal.

**References**
- `infra/terraform/providers/aws/compute/` (ALB listener), `infra/terraform/providers/aws/security/`
  (CloudFront + WAFv2)

**Recommended next step**
Confirm the domain decision first — it determines whether R-004 is a two-certificate task or a
single CloudFront-default deployment with no certificate work at all.

---

## R-005 — Amazon Bedrock model access opt-in

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left the core with `TODO.md` → T-504 and live in the AWS appliance repository, where the blocker is tracked as **R-005** with paths rebased to `infra/terraform/modules/`. This entry is kept for history and for the references below; resolve it there.

**Problem**
Amazon Bedrock foundation-model access is granted per account **and** per region through a
console opt-in. No Terraform resource covers this step.

**Why it blocks progress**
`bedrock:InvokeModel` fails until the opt-in is complete, so the `ai` module's inference profile
resolves to a model the platform cannot call. The AI analysis path is a core platform capability,
not an optional extra.

**Required owner**
AWS account owner (the opt-in requires console access and acceptance of model EULA terms).

**Required action**
1. Enable foundation-model access in the Bedrock console for the deployment account and region.
2. Confirm the model IDs in the `ai` module's `model_ids` variable are available in that region;
   adjust the variable if not (that adjustment is an engineering task — `TODO.md` → T-303).

**Impact if unresolved**
AWS AI analysis is unavailable. The fallback is to keep calling the existing Azure OpenAI
endpoint from the AWS deployment, which reintroduces a cross-cloud dependency the AWS parity work
was meant to remove.

**References**
- `infra/terraform/providers/aws/ai/`
- Azure equivalent: AI Foundry `cognitive_deployment`, already Terraform-managed

**Recommended next step**
Perform the opt-in at the same time as R-001 account setup — it is a prerequisite with a
multi-hour approval delay for some models, so it should not be discovered late.

---

## R-006 — Runtime secrets have no defaults and must be supplied

> **Transferred 2026-09-15** to the AWS appliance's `REVIEW.md` as **R-008** (`TODO.md` → T-507). Resolve it there; this entry is history.

**Problem**
Five runtime inputs are declared `sensitive` with **no defaults** and are intentionally absent
from the repository.

**Why it blocks progress**
`terraform apply` on the workload root fails immediately without them. They cannot be committed,
generated by CI, or defaulted safely.

**Required owner**
Security / secret owner (whoever holds the Entra app registration and the Docker Hub
organization).

**Required action**
Supply at apply time, or seed into the chosen secret store:

| Variable | Purpose |
|---|---|
| `db_admin_password` | RDS PostgreSQL master password |
| `nextauth_secret` | NextAuth / Auth.js session secret |
| `entra_client_secret` | Entra ID app-registration client secret |
| `credential_encryption_key` | Application credential-encryption key |
| `dockerhub_username` / `dockerhub_token` | Private image pulls (optional — the module counts off when blank) |

**Impact if unresolved**
No workload apply is possible. Partial supply is worse than none: the database and runtime
modules would apply inconsistently and leave a half-provisioned environment.

**References**
- `infra/terraform/providers/aws/runtime/variables.tf`,
  `infra/terraform/providers/aws/database/variables.tf`
- `.env.example` (the equivalent Azure secret inventory)

**Recommended next step**
Decide where these live for AWS — Secrets Manager seeded out of band, or GitHub environment
secrets passed as `TF_VAR_*`. The Azure side uses Key Vault; the AWS `runtime` module already
provisions Secrets Manager entries, so seeding is the closer mirror.

---

## R-007 — Azure subscription resource-provider registration

> **Note 2026-09-15.** The `100-validate-prereqs` provider check and the `211` registration step this entry discusses are Azure appliance workflows now (`TODO.md` → T-504).

**Status: Resolved — nothing is required of the subscription owner.**

**Original problem**
The Azure subscription was said to need `Microsoft.AlertsManagement` registered before workflow
`211-deploy-azure-split.yml` runs, because Application Insights smart-detection alert deployment
fails during apply if it is not, ~20 minutes into a run.

**Why it is no longer required**
The split refactor removed alerting from the Azure roots entirely. Verified against the current
Terraform on 2026-08-18 (`TODO.md` → T-104): `infra/` contains no `azurerm_application_insights`,
no `azurerm_monitor_smart_detector_alert_rule`, no `azurerm_monitor_metric_alert`, and no
`azurerm_monitor_action_group`. The only monitor resource left is
`azurerm_monitor_diagnostic_setting`, which belongs to `Microsoft.Insights`, not
`Microsoft.AlertsManagement`. Both `azapi_resource` declarations resolve to
`Microsoft.CognitiveServices` and `Microsoft.Network`. Workflow `100-validate-prereqs.yml` had
already reached the same conclusion in a code comment; this is the check against the Terraform
that confirms it.

**What replaced it**
Provider registration is now *asserted*, not assumed. Workflow `100-validate-prereqs.yml` checks
all ten namespaces the roots genuinely need — `Microsoft.App`, `.Network`, `.Storage`, `.KeyVault`,
`.DBforPostgreSQL`, `.CognitiveServices`, `.OperationalInsights`, `.Insights`, `.Cdn`, and
`.ManagedIdentity` — and fails in seconds with the exact `az provider register` command rather
than partway through apply. It previously checked only two of the ten, so the *class* of blocker
R-007 describes was real and largely unguarded; it is now closed for every provider at once, not
just this one.

**2026-08-28 addendum — the leftover register call in 211**
The first full `211` run under the RG-scoped deploy identities (rebuilt dev environment) failed
in seconds on a leftover from the pre-split era: both the `plan` and `apply` jobs still ran an
unconditional `az provider register --namespace Microsoft.App --wait`, which requires the
subscription-scope `register/action` this item says the deploy identity must never hold. That
step is now a read-only verification (fails with the one-time Owner command only on
`NotRegistered`), and all four environment roots set `resource_provider_registrations = "none"`
so the azurerm provider's default auto-registration cannot hit the same wall during plan.
Workflow 100 remains the gating assertion.

**If a future change reintroduces alerting**
Add `Microsoft.AlertsManagement` to `REQUIRED_PROVIDERS` in `100-validate-prereqs.yml` in the same
commit as the alert resource, and reopen this item — the registration is still a subscription-level
operation the deploy identity cannot perform itself.

**References**
- `.github/workflows/100-validate-prereqs.yml` (the `REQUIRED_PROVIDERS` list)
- `infra/terraform/providers/azure/observability/`
- `TODO.md` → T-104

---

## R-008 — Live Azure beta acceptance sign-off

> **Transferred 2026-09-15** to the Azure appliance's `REVIEW.md` as **R-003** (`TODO.md` → T-507). Resolve it there; this entry is history.

**Problem**
The repository is at `0.8.0b0`. Code, Terraform, workflows, and the changelog are aligned on
`main`, but the beta exit gate is live Azure execution: prerequisite validation, dev deploy,
Entra redirect update, runtime validation, and customer-like beta acceptance.

**Why it blocks progress**
Acceptance is a product judgement, not an engineering result. No amount of further engineering
work moves the release posture past `0.8 beta` without someone accepting the live evidence.

**Required owner**
Product owner (with the AWS/Azure account owners for the deploy windows).

**Required action**
1. ~~Schedule the live dev deploy window (workflows 100 → 200 → 211).~~ **Done 2026-08-28** —
   though not as a scheduled window: the dev environment had been deleted out of band (see R-010
   and `CNA-0.90-updates.md` §5), so it was rebuilt from nothing via `000` → `100` → `211`.
   Run `33169632082`, all jobs green.
2. **Review the deployment evidence artifacts produced by the workflow run.** These now exist:
   `.deployment-catalog/dev/33169632082.json` records `health_status: healthy`, 100% origin
   health, and passing canary, staged-promotion, certificate and private-endpoint checks.
   **Read the two `required` markers before accepting** — `foundry_private_dns_validation` and
   `foundry_managed_identity_inference` are never set by any workflow step, so a `healthy`
   verdict does not cover the AI Foundry / Copilot path (`TODO.md` → T-415).
3. Accept or reject the customer-like beta acceptance run, and record the decision.
   Note the acceptance run has not happened yet: the rebuilt environment has an empty database,
   so there is no discovery, finding, or deliverable in it to accept against.

**Impact if unresolved**
The platform stays in beta indefinitely and cannot be offered to a client engagement, regardless
of code readiness.

**References**
- `.github/workflows/100-validate-prereqs.yml`, `200-build-images.yml`,
  `211-deploy-azure-split.yml`
- `scripts/ci/evaluate_deployment_evidence.py`
- [`CHANGELOG.md`](CHANGELOG.md) → `[0.8.0-beta]`

**Recommended next step**
Book the deploy window. R-007 no longer blocks it — see that item; provider registration is now
asserted by workflow `100-validate-prereqs.yml`, which should be run first regardless.

---

## R-009 — GitHub Wiki write access for documentation migration

**Problem**
The documentation model designates the GitHub Wiki as the destination for all long-form
documentation. Seven validated pages were prepared during the consolidation and cannot be
published: the wiki remote returns HTTP 401 to the automation performing the work, while the
repository itself authenticates normally. Wiki write access is scoped out.

**Why it blocks progress**
This no longer blocks the repository — it converged on the four-document end state without the
Wiki. The long-form content that had nowhere else to go was migrated into `TODO.md` handoff notes
instead (T-304 carries the Log Analytics state-migration runbook, T-401 the `migrate/` reference),
and both source files were deleted after that migration was verified. What remains blocked is
putting that documentation in its proper home. Until then, operational runbook content lives in
the engineering backlog, which is the right fallback but the wrong destination.

**Required owner**
Repository owner.

**Required action**
Either grant Wiki write access to the account performing documentation consolidation, or publish
the seven prepared pages manually. The validated page content is attached to the pull request that
introduced this file. The corresponding tasks are `TODO.md` → T-601 (publish) and T-602 (trim the
inline copies once the Wiki has them).

**Impact if unresolved**
Low and contained. No information is lost and no competing source of truth exists — every fact is
either in the repository or in a TODO item's handoff notes. The cost is discoverability: an
operator looking for a state-migration runbook will not think to look in the engineering backlog,
and `TODO.md` carries roughly 80 lines of procedure that do not belong in a work queue.

**References**
- [`TODO.md`](TODO.md) → T-304, T-401 (the content), T-601, T-602 (the cleanup)
- [`README.md`](README.md) → documentation map, where the Wiki links belong

**Recommended next step**
Confirm the Wiki page names before publishing so the cross-links resolve — in particular
`Runbook: Log Analytics Workspace State Migration` and `Legacy AWS Migrate Root`. `Workflows
Guide` and `Secrets Reference` are already referenced by `.env.example` and may already exist;
merge rather than create.

---

## R-010 — The dev environment has no protection against out-of-band deletion

> **Transferred 2026-09-15** to the Azure appliance's `REVIEW.md` as **R-004** (`TODO.md` → T-507). Resolve it there; this entry is history.

**Problem**
The entire Azure dev environment — workload resource group *and* the `-tfstate` resource group
holding the Terraform state — was deleted from `sub-cbtssandbox-ops-tst` around **2026-07-21**,
outside CI. No teardown workflow ran in that window (`330-teardown` last ran 2026-07-01), so the
deletion was performed directly against the subscription, consistent with a sandbox cost sweep.

It was rebuilt on 2026-08-28 (`CNA-0.90-updates.md` §5), but nothing prevents a repeat, and the
rebuild was not cheap: the state loss meant a from-scratch provision, six previously-unknown gaps
in the deploy identity's least-privilege role set, a soft-deleted Key Vault to recover and import,
and roughly half a day of a pre-demo schedule.

**Why it needs an owner**
Whether the sweep is intentional policy is not an engineering question. If the sandbox is *meant*
to be swept, the environment should not be treated as durable and the demo/engagement plan has to
budget a rebuild each time. If it is not meant to be swept, the environment needs protecting. Only
the subscription owner can say which.

**Required owner**
Azure subscription owner (`sub-cbtssandbox-ops-tst`), with whoever administers the sandbox
sweep policy.

**Required action**
1. Establish whether a sweep policy exists for this subscription, what it targets, and on what
   schedule.
2. If the environment should persist: apply a `CanNotDelete` resource lock to
   `rg-cna-dev-scus` and `rg-cna-dev-scus-tfstate` at minimum — the state RG especially, since
   losing it is what turned a redeploy into a rebuild — or request an exclusion from the sweep.
3. If the environment is legitimately ephemeral: record that in the demo/engagement runbook so a
   rebuild is planned rather than discovered, and consider whether the tfstate backend should live
   in a subscription that is not swept.

**Impact if unresolved**
The next sweep repeats the same half-day recovery, at whatever moment it happens to land. The
permission gaps are now codified in `scripts/Initialize-CnaGitHubSecrets.ps1`, so a second rebuild
would be materially faster — but it would still be a rebuild, with a fresh, empty database.

**References**
- [`CNA-0.90-updates.md`](CNA-0.90-updates.md) → §5 (the full rebuild record)
- [`TODO.md`](TODO.md) → T-416 (the drift check that detected this and told no one)
- `.deployment-catalog/dev/33169632082.json` (the rebuild's evidence)

**Recommended next step**
Ask the sandbox administrator the one question that decides everything else: is
`sub-cbtssandbox-ops-tst` swept on a schedule, and can these two resource groups be excluded?

---

## R-011 — Security review of the bring-your-own AI key path and provider egress

**Problem**
The `byo-api` AI mode (`CHANGELOG.md` → Unreleased) introduces two things that did not exist
before and that CBTS engineering standards say need a human security review before they carry
customer traffic:

1. **Admin-entered API keys stored in the application database.** An admin pastes an Anthropic
   and/or OpenAI key on `/admin/ai-engine`; it is probed against the provider, AES-256-GCM
   encrypted with the existing `CREDENTIAL_ENCRYPTION_KEY` scheme (`apps/cna-web/lib/crypto.ts`),
   stored in `AppSetting` (`ai.byo.<provider>.apiKey`), and decrypted server-side only — by the
   web tier for its own completions and by cna-api (`cna/core/credential_crypto.py`) for chat.
   Only the last four characters are ever shown back. cna-api therefore receives
   `CREDENTIAL_ENCRYPTION_KEY` in byo-api deployments, which it did not have before.
2. **New firewall egress.** The platform root opens `api.anthropic.com` and `api.openai.com` on
   the Azure Firewall application rule when `ai_mode = byo-api` (nothing changes in `saas`). The
   AWS roots have no FQDN filter today; whether one should exist is part of the same review.

**Why it needs an owner**
Encryption-at-rest of third-party credentials, the decryption boundary, key-probe behaviour, and
outbound allow-list changes are policy decisions, not engineering ones. The implementation is
complete and tested (Node-generated interop vector, 51 Python + 22 web unit tests), but "complete"
is not "approved".

**Required owner**
Security.

**Required action**
1. Review the key lifecycle: entry (`admin/ai-engine/actions.ts`, admin-only), storage
   (`lib/ai-byo-credentials.ts`), decryption points (`lib/ai-engine.ts`,
   `apps/cna-api/routers/chat.py`), and that no path logs, returns, or persists a plaintext key.
2. Approve or amend the two egress FQDNs and decide whether the AWS appliance needs an equivalent
   outbound control before its first byo-api deploy.
3. Confirm the key-probe (a `GET /v1/models` against the provider at save time) is acceptable, or
   ask for it to be disabled (`setByoApiKey(..., { probe: false })`).

**Impact if unresolved**
`byo-api` cannot be offered to a customer. `saas` deployments are unaffected — the code path is
inert when `CNA_AI_MODE` is `saas` or unset.

**References**
- [`CLAUDE.md`](CLAUDE.md) → AI engine rules
- [`CHANGELOG.md`](CHANGELOG.md) → Unreleased → Added (first two entries)
- `.env.example` → GENAI ENGINE MODE + SWITCHING

---

## R-012 — Token for a shared project board across three repositories

**Problem**
`TODO.md` → T-505 wants one GitHub Project (v2) holding issues and pull requests from the core and
both appliance repositories, populated automatically by an `add-to-project` workflow in each.
User-owned Projects v2 are **not** reachable with a GitHub App installation token — the App that
already backs cross-repository dispatch cannot add items to a user project — so the workflow needs
either a fine-grained personal access token with `project` scope stored as a secret in three
repositories, or the repositories moved under an organization where the App can hold the
`organization_projects` permission.

**Why it needs an owner**
Creating a long-lived personal token, or reorganizing the repositories under an organization, is
the repository owner's decision; CBTS standards prefer the short-lived, identity-based option where
one exists.

**Required owner**
Repository owner.

**Required action**
Choose one:
1. Move the three repositories under a GitHub organization, grant the existing App
   `organization_projects: write`, and use the App token in the `add-to-project` workflows; or
2. Create a fine-grained PAT with `project` scope (and `issues`/`pull_requests: read` on the three
   repositories), store it as `PROJECT_BOARD_TOKEN` in each repository, and set a rotation
   reminder.

**Impact if unresolved**
Work stays visible per repository only; the appliances' `update-available` issues are not
aggregated. Nothing else depends on this.

**References**
- [`TODO.md`](TODO.md) → T-505

---

## R-013 — Bring the core repository live and cut the appliances over to it

**Problem**
`TODO.md` → T-509 moved the core into `Work-Cloud_Network_Core`. A new repository has none of the
configuration the four workflows read: no secrets, no variables, no GitHub App installation. Until it does, `200-build-images` cannot publish, `310-release-version` cannot
release, and the appliances' `230-image-update` keeps polling the original repository's frozen
manifest because their `CORE_REPO` variable still says `Work-Cloud_Network_Assessment`.

**Why it needs an owner**
Repository secrets, variables, App installations and branch protection are settings only the
repository owner can write; none of them can be committed.

**Required owner**
Repository owner.

**Required action** — in this order, so the appliances never lose their image source:
1. On `Work-Cloud_Network_Core` → *Settings*: create the secrets `DOCKERHUB_TOKEN`, `DOCKERHUB_PERSONAL_TOKEN`,
   `GH_APP_ID`, `GH_APP_PRIVATE_KEY` and the variables `DOCKERHUB_NAMESPACE`,
   `DOCKERHUB_PERSONAL_USERNAME`, `APPLIANCE_REPOS`
   (`Work-Cloud_Network_Azure_Appliance,Work-Cloud_Network_AWS_Appliance`) with the values the
   original repository uses. Set *Actions → General → Workflow permissions* to *Read and write*
   (`310` and the manifest commit in `200` need it).
2. No runner to register: every workflow here — and every workflow in both appliances — runs on
   GitHub-hosted runners (`ubuntu-latest`). The self-hosted runner the original repository used is
   retired; remove its registration under R-014.
3. Install the GitHub App that backs the cross-repository dispatch on `Work-Cloud_Network_Core` as
   well: `200` uses it to notify the appliances, and each appliance's `230` uses it to read this
   repository's manifest.
4. Merge the import pull request here, then run `200 · Build Container Images` once from *Run
   workflow* so `.deployment-catalog/latest-build.json` on `main` is written by this repository.
5. In **both** appliances set the variable `CORE_REPO` to `Work-Cloud_Network_Core` and merge their
   repoint pull requests. From that moment `230` polls this repository.
6. Apply the same branch protection to `main` here as the original repository had (required check
   `300 · Test Codebase`, review requirements).
7. Only now proceed to R-014 — the original repository must keep serving its manifest until step 5
   is done.

**Impact if unresolved**
Two repositories claim to be the core; images keep being built from a repository the documents say
is retired, and the appliances never see a build from the new one.

**References**
- [`TODO.md`](TODO.md) → T-509
- `.github/workflows/200-build-images.yml`, `310-release-version.yml`, `370-registry-cleanup.yml`
  (the secrets and variables each reads are in its header and `vars.*` / `secrets.*` references)
- Appliances: `README.md` → *Configuration* (`CORE_REPO`), `230-image-update.yml`

---

## R-014 — Move the Wiki and delete the original repository

**Problem**
The original repository, `Work-Cloud_Network_Assessment`, is retired: its tree has been a pointer
since 2026-09-21 (its pull request #178) and the owner has decided to **delete** it rather than
archive it. Deletion also removes its issues, pull requests, releases, Wiki and the legacy GHCR
packages, so anything the platform still needs from it has to live in this repository or in one of
the two appliances first.

**What engineering verified (2026-09-24)**
- *Files.* All 8,857 paths at its last full commit (`5d3b914`) are in this repository's history —
  `5d3b914` is an ancestor of `main`. 8,851 are on `main` byte-for-byte or superseded by later edits
  here; the other 6 were removed deliberately: `.kiro/specs/production-readiness/*` (#20, vendored-pack
  sweep) and `apps/cna-web/app/(dashboard)/engagements/[id]/analysis/run-form.tsx` (#21, dead-code
  sweep; nothing imported it). The deployment layer had already moved to the appliances (T-504 – T-508).
- *Branches.* Only `main` and the pointer branch exist; no unmerged work.
- *Issues and pull requests.* None open. Closed threads are cited in this repository's documents by
  number only; those citations are historical and are not expected to resolve.
- *Releases and tags.* `v0.1.0` and `v0.8.0` — both commits are on `main` here and their content is
  `CHANGELOG.md` → 0.1.0 and 0.8.0-beta. The tags are **not** recreated here: a `v*.*.*` push
  triggers `310-release-version`, which would rebuild and republish an old commit.
- *Container images.* The appliances pull `docker.io/<namespace>/cna:*-sha-*`; the Azure appliance's
  live catalog entry is on Docker Hub. The GHCR packages those two releases named
  (`ghcr.io/saulpatinojr/Work-Cloud_Network_Assessment`, `ghcr.io/saulpatinojr/MVP-Cloud_Network_Assessment`)
  are used by nothing current; the Azure catalog archives from run `24168247436` to `24585307176`
  name them and become non-restorable, which is accepted.
- *Actions secrets and variables.* The set the original's workflows consumed (`DOCKERHUB_NAMESPACE`,
  `DOCKERHUB_TOKEN`, `DOCKERHUB_PERSONAL_USERNAME`, `DOCKERHUB_PERSONAL_TOKEN`, `APPLIANCE_REPOS`,
  `GH_APP_ID`, `GH_APP_PRIVATE_KEY`) is exactly the set this repository's workflows consume — R-013.
- *Wiki.* Not verifiable from the engineering side (a Wiki is a separate git repository that needs
  write access, R-009); step 1 below.

**Why it needs an owner**
The Wiki move needs write access, repository settings and cloud identity federation can only be read
by an admin, and deleting a repository is owner-only and final after GitHub's 90-day restore window.

**Required owner**
Repository owner.

**Required action** — in this order; the deletion is last
1. Move the Wiki: `git clone https://github.com/saulpatinojr/Work-Cloud_Network_Assessment.wiki.git`, add
   `https://github.com/saulpatinojr/Work-Cloud_Network_Core.wiki.git` as a remote and push `master`
   (create one page in the new Wiki first so the Wiki repository exists). Confirm the page count
   matches. This also closes the destination half of R-009.
2. Set `CORE_REPO` to `Work-Cloud_Network_Core` in **both** appliances (Azure R-005, AWS R-009) and
   run `230 · Image Update` once in each. After the deletion the old value fails with a 404.
3. Make `DOCKERHUB_NAMESPACE` visible to this repository's Actions and run `200 · Build Container
   Images` once (R-013 step 4). Every run so far has failed on that variable, so no manifest has been
   published from here yet.
4. Open <https://github.com/saulpatinojr?tab=packages>. If either legacy GHCR package must survive,
   retag it to Docker Hub before the deletion; otherwise let it go with the repository.
5. Remove the original repository's Actions secrets, variables, environments and any runner
   registration. In Azure and AWS, delete the federated identity credentials / OIDC role trust
   entries whose subject names `repo:saulpatinojr/Work-Cloud_Network_Assessment:*` — they are orphaned.
6. Confirm nothing you still need is owned by that repository: a repository-level project board,
   a GitHub App installation scoped to it, or Dependabot alerts (T-204 now re-triages on this
   repository's Security tab).
7. Delete it: *Settings → Danger Zone → Delete this repository*. GitHub can restore a deleted
   repository for 90 days.

**Impact if unresolved**
The pointer repository lingers with its secrets and variables still set; nothing breaks, but the
documents in three repositories say it is gone.

**References**
- [`TODO.md`](TODO.md) → T-509, T-601 (the Wiki pages still waiting on R-009)
- R-009, R-013; Azure appliance R-005, AWS appliance R-009

---

## R-015 — Decide the customer-facing appliance repository names

**Problem**
The target topology names the customer-facing solutions the **Azure Assessment** and the **AWS
Assessment**, but the repositories are `Work-Cloud_Network_Azure_Appliance` and
`Work-Cloud_Network_AWS_Appliance`. Whether the repositories should be renamed to match is a
product-naming decision, and a rename touches every cross-reference: the `APPLIANCE_REPOS` variable
here, the `cna-image-published` dispatch targets, `cna/review/areas/terraform_relocated.py` and its
tests, `CLAUDE.md`/`README.md` in all three repositories, and the sibling links inside each
appliance.

**Why it needs an owner**
Customer-facing names are the owner's call; GitHub redirects the old name for git and web traffic
but the API dispatch in `200` and the documents must be updated in the same change set.

**Required owner**
Repository owner.

**Required action**
Choose one:
1. Keep `*_Appliance` (no change; the documents already describe them as the customer-facing
   solutions), or
2. Rename both to `Work-Cloud_Network_Azure_Assessment` / `Work-Cloud_Network_AWS_Assessment` and
   open a `TODO.md` item here to update `APPLIANCE_REPOS`, the review-engine constants and every
   document link in the three repositories together.

**Impact if unresolved**
None operationally; the prose and the repository names disagree.

**References**
- [`TODO.md`](TODO.md) → T-509
- `.github/workflows/200-build-images.yml` (`APPLIANCE_REPOS`), `cna/review/areas/terraform_relocated.py`

---

## R-016 — Retire `apps/cna-worker` and its image, service and catalog slot

**Problem**
`apps/cna-worker/main.py` is a 101-line placeholder: it writes a "CNA publish placeholder" HTML
file for a hard-coded `sample-engagement` and exits. `POST /publish` superseded it
(`CHANGELOG.md`, "The client-portal publish story is real"). Both appliances still deploy it as an
always-on service (Azure `modules/compute/main.tf`, AWS `modules/compute/main.tf`), so it exits and
restarts continuously, its image is built and scanned on every push, and `latest-build.json`,
`210`, `230`, `350` and `360` all carry a `worker` slot.

**Why it needs an owner**
Removing it destroys a live Container App in Azure dev and changes the core ↔ appliance contract
(`images.worker`), which `CLAUDE.md` says is never a unilateral cleanup.

**Required owner**
Repository owner.

**Required action**
Approve one coordinated change set across the three repositories: delete `apps/cna-worker` and its
Dockerfile and build job here; remove the worker service, image inputs and catalog fields in both
appliances.

**Impact if unresolved**
Wasted compute, a permanently restarting container in every environment, and documentation that
describes a component that does nothing.

**References**
- v1.0 review findings IMG-003, ARCH-004, ARCH-101, PY-016

## R-017 — Stop publishing the CLI image on every push

**Problem**
No appliance references `images.cli` (`grep` over both appliances: zero hits outside
`320-publish-portal`). It is the largest image (draw.io + Electron + Xvfb) and its root
`COPY . .` ships `TODO.md`, `REVIEW.md` and `cna/review/**` inside a customer-pullable artifact.

**Required owner**
Repository owner.

**Required action**
Decide: keep the CLI image as a developer-only local build (`docker-compose.yml` already has it) and
drop it from `200-build-images.yml`, `310` and the manifest; or keep publishing and fence the build
context.

**Impact if unresolved**
Extra build time and scan noise on every push; repository-internal documents in a shipped image.

**References**
- v1.0 review findings IMG-006, IMG-007, ARCH-102, PROD-004

## R-018 — Remove `cna/review/**` from the shipped package

**Problem**
`cna/review/**` (3,451 lines) is the repository's production-readiness review engine. No product
code imports it (`grep 'cna\.review' apps cna scripts` → 0), yet it is installed into the API image
and its 26 test files consume 54 % of unit-test runtime.

**Required owner**
Repository owner.

**Required action**
Approve moving it under `scripts/` (or a separate tooling package) with its tests, so the shipped
`cna` package contains product code only.

**Impact if unresolved**
Larger images and slower CI; no customer impact.

**References**
- v1.0 review findings ARCH-104, PY-014

## R-019 — Diagram editor sends customer topology to `embed.diagrams.net`

**Problem**
`apps/cna-web/components/diagrams/DrawioEmbed.tsx` iframes the public draw.io embed and posts the
engagement's `.drawio` XML into it. There is no self-hosted or offline fallback, so an appliance
without internet egress from the analyst's browser shows a blank editor, and every customer's
network architecture leaves the appliance boundary to a third party.

**Required owner**
Product owner (feature) and Security (data governance).

**Required action**
Choose: self-host draw.io (static bundle served by the web tier, or a container), or document the
dependency as a customer opt-in with a data-handling statement.

**Impact if unresolved**
Customers with restricted egress cannot use the Diagram page; customer data-handling questions
have no answer.

**References**
- v1.0 review findings UI-002, ARCH-012

## R-020 — Aeonik font licence and OCI licence label

**Problem**
`apps/cna-web/app/fonts/Aeonik-Regular.ttf` and `cna/report_engine/templates/assets/fonts/` ship a
commercial typeface as a webfont and embedded in PDFs with no licence file in the repository. The
OCI image label says `licenses="Proprietary"` while the repository `LICENSE` is Apache-2.0.

**Required owner**
Legal / brand.

**Required action**
Confirm the Aeonik licence covers web-serving and PDF embedding for customer deliverables
[VERIFY]; pick one licence statement for the images and `LICENSE`.

**Impact if unresolved**
Possible licence non-compliance in a customer-facing artifact.

**References**
- v1.0 review finding IMG-015

## R-021 — `byo-api` mode scope for 1.0

**Problem**
Two AI modes × four engines, keys entered in the app UI, and firewall egress to
`api.anthropic.com` / `api.openai.com`; R-011 (security review of that path) is still open.

**Required owner**
Product owner and Security.

**Required action**
Either complete R-011 before 1.0, or ship 1.0 as `saas`-only (managed identity) with `byo-api`
behind a deploy-time flag.

**Impact if unresolved**
1.0 carries an unreviewed secret-handling path.

**References**
- R-011; v1.0 review finding ARCH-106

## R-022 — Version 1.0.0 release identity

**Problem**
`pyproject.toml` says `0.8.0b0`, `apps/cna-web/package.json` `0.8.0-beta.0`; `CHANGELOG.md`
already contains `## [1.0.0] - 2026-05-28`, later withdrawn to `[0.8.0-beta]`; the repository has
no git tags, so `310-release-version` has never run. (The API's hard-coded `0.2.0` was replaced by
the package metadata version in the v1.0 review.)

**Required owner**
Repository owner.

**Required action**
Rename the historical heading (for example `[1.0.0-rc1] — withdrawn`), set the version in
`pyproject.toml` and `package.json` in one commit, and cut the first `v*` tag only after the
Critical and High rows of the v1.0 findings register are closed.

**Impact if unresolved**
A customer cannot tell what "1.0" they run; a new `[1.0.0]` heading would collide.

**References**
- v1.0 review findings RELEASE-004, DOC-001, DOC-022

## R-023 — Wiki content after the restore

- **Decision needed:** the GitHub Wiki linked from `README.md` now points at this repository's wiki
  (<https://github.com/saulpatinojr/HCW-NetworkEyes_App/wiki>), but the pages (architecture, ADRs,
  runbooks, workflow reference) still live on `Work-Cloud_Network_Core`'s wiki. Move them (clone the
  Core wiki repository and push it to this repository's wiki), or keep the Core wiki as the home and
  point the links back.
- **Raised:** 2026-10-10, with the restore of the Core lineage into this repository.
- **Status:** Open

## R-024 — Image signing identity after the restore

- **Decision needed:** both appliances verify images against `IMAGE_SIGNING_IDENTITY`, which names the
  Core's `200-build-images.yml` on its `main`. Once images publish from this repository (after the
  Docker Hub OIDC connection and `DOCKERHUB_ENABLED` exist here), that variable must change in both
  appliance repositories to
  `https://github.com/saulpatinojr/HCW-NetworkEyes_App/.github/workflows/200-build-images.yml@refs/heads/main`,
  or every deploy fails verification. Until then the appliances keep consuming the Core's images.
- **Raised:** 2026-10-10.
- **Status:** Open
