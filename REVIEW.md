# Review — human-resolvable blockers

This file tracks **only** items that an engineer cannot resolve independently. Every entry
requires external input: an approval, a credential, an account, an access grant, or a decision
that belongs to a named owner outside the engineering task itself.

Anything an engineer can solve without external input belongs in [`TODO.md`](TODO.md), not here.

**Last reviewed:** 2026-10-25

| ID | Blocker | Owner | Status |
|---|---|---|---|
| [R-001](#r-001--aws-account-and-administrative-access) | AWS account + administrative access for first deploy | AWS account owner | Not tracked here — the deploy layer left this repository on 2026-09-15 (`TODO.md` T-504) |
| [R-002](#r-002--terraform-s3-state-backend-must-be-created-out-of-band) | Terraform S3 state backend + DynamoDB lock table | AWS account owner | Not tracked here — the deploy layer left this repository on 2026-09-15 (`TODO.md` T-504) |
| [R-003](#r-003--github-oidc-deploy-role-must-be-wired-into-ci) | GitHub OIDC deploy role wired into CI secrets | Repository admin | Not tracked here — the deploy layer left this repository on 2026-09-15 (`TODO.md` T-504) |
| [R-004](#r-004--acm-certificates-and-custom-domain-decision) | ACM certificates + custom-domain decision | DNS / domain owner | Not tracked here — the deploy layer left this repository on 2026-09-15 (`TODO.md` T-504) |
| [R-005](#r-005--amazon-bedrock-model-access-opt-in) | Amazon Bedrock foundation-model access opt-in | AWS account owner | Not tracked here — the deploy layer left this repository on 2026-09-15 (`TODO.md` T-504) |
| [R-006](#r-006--runtime-secrets-have-no-defaults-and-must-be-supplied) | Runtime secrets supplied at apply time | Security / secret owner | Not tracked here — left this repository on 2026-09-15 (`TODO.md` T-507) |
| [R-007](#r-007--azure-subscription-resource-provider-registration) | `Microsoft.AlertsManagement` provider registration | Azure subscription owner | Resolved — no longer required |
| [R-008](#r-008--live-azure-beta-acceptance-sign-off) | 0.8 beta exit — live Azure acceptance sign-off | Product owner | Not tracked here — deploy done 2026-08-28, acceptance outstanding; left this repository on 2026-09-15 (`TODO.md` T-507) |
| [R-009](#r-009--github-wiki-write-access-for-documentation-migration) | GitHub Wiki write access to publish prepared pages | Repository owner | Open — not blocking |
| [R-010](#r-010--the-dev-environment-has-no-protection-against-out-of-band-deletion) | Dev environment deleted out of band; no protection against a repeat | Azure subscription owner | Not tracked here — left this repository on 2026-09-15 (`TODO.md` T-507) |
| [R-011](#r-011--security-review-of-the-bring-your-own-ai-key-path-and-provider-egress) | Security review: bring-your-own AI key handling + firewall egress to Anthropic/OpenAI | Security | Open — before the first `byo-api` deploy |
| [R-012](#r-012--token-for-a-shared-project-board) | Token type for a shared project board (PAT vs GitHub App / organization) | Repository owner | Open — not blocking |
| [R-013](#r-013--bring-this-repository-live-the-docker-hub-repository-its-oidc-connection-and-the-first-publish) | Bring this repository live: the Docker Hub repository, its OIDC connection, the variables and the first publish | Repository owner | Open — blocks the first image publish from this repository (T-728) |
| [R-014](#r-014--move-the-wiki-and-delete-the-original-repository) | Move the Wiki, then delete the original repository | Repository owner | Superseded 2026-10-11 — this repository (the renamed original) is the product and is not deleted; the Wiki moves here (R-023) |
| [R-015](#r-015--decide-the-customer-facing-appliance-repository-names) | Decide the customer-facing appliance repository names | Repository owner | Withdrawn 2026-10-25 — not this repository's decision |
| [R-016](#r-016--retire-appscna-worker-and-its-image-and-service) | Retire `apps/cna-worker` — placeholder that runs as an always-on service in a deployment | Repository owner | Open — v1.0 review finding IMG-003 / ARCH-101 |
| [R-017](#r-017--stop-publishing-the-cli-image-on-every-push) | Stop building/publishing the CLI image `sha-<7>` (nothing in this repository pulls it except the release) | Repository owner | Open — not blocking |
| [R-018](#r-018--remove-cnareview-from-the-shipped-package) | Move `cna/review/**` out of the shipped package and API image | Repository owner | Open — not blocking |
| [R-019](#r-019--diagram-editor-sends-customer-topology-to-embeddiagramsnet) | Diagram editor posts customer topology XML to public `embed.diagrams.net`; no offline path | Product owner / Security | Decided 2026-10-25 — self-host; implemented (ticket #248) |
| [R-020](#r-020--aeonik-font-licence-and-oci-licence-label) | Aeonik typeface licence coverage; OCI label `Proprietary` vs Apache-2.0 `LICENSE` | Legal / brand | Licence label decided 2026-10-25 (Apache-2.0, done); font licence still to be confirmed — owner |
| [R-021](#r-021--byo-api-mode-scope-for-10) | Ship 1.0 `saas`-only or complete R-011 first | Product owner / Security | Open |
| [R-022](#r-022--version-100-release-identity) | Version 1.0.0 identity: withdrawn `[1.0.0]` heading, version strings, first tag | Repository owner | Open — before the first `v*` tag |
| [R-025](#r-025--the-drawio-mcp-route-is-internal-only) | Is `/api/drawio-mcp` public or internal only? | Repository owner | Decided 2026-10-24 — internal only; implemented (ticket #245) |
| [R-026](#r-026--owner-steps-after-the-governance-and-ci-hygiene-change) | Add three new checks to the `Protect main` ruleset; confirm private vulnerability reporting; the `370` token | Repository owner | Step 1 done; steps 2 and 3 open (tickets #247, #252, #253) |
| [R-027](#r-027--remove-the-orphaned-cloud-trust-entries-of-the-earlier-repository-name) | Remove the cloud trust entries (Azure federated credentials, AWS role trust) that name this repository by its earlier name | Repository owner / cloud account owners | Open — not blocking |
| [R-028](#r-028--should-the-default-model-ids-of-the-bring-your-own-engines-follow-the-vendors-current-models) | Should the default model ids of the bring-your-own engines follow the vendors' current models? | Product owner | Open — not blocking |

---

## R-001 — AWS account and administrative access

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left this repository with `TODO.md` → T-504. It is not tracked here; this entry is kept as history.

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

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left this repository with `TODO.md` → T-504. It is not tracked here; this entry is kept as history.

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

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left this repository with `TODO.md` → T-504. It is not tracked here; this entry is kept as history.

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

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left this repository with `TODO.md` → T-504. It is not tracked here; this entry is kept as history.

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

> **Moved 2026-09-15.** The Terraform and workflows this blocker gates left this repository with `TODO.md` → T-504. It is not tracked here; this entry is kept as history.

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

> **Left this repository 2026-09-15** (`TODO.md` → T-507). It is not tracked here; this entry is history.

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

> **Note 2026-09-15.** The `100-validate-prereqs` provider check and the `211` registration step this entry discusses are no longer in this repository (`TODO.md` → T-504).

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

> **Left this repository 2026-09-15** (`TODO.md` → T-507). It is not tracked here; this entry is history.

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
   The run's deployment record (removed from this repository with T-504) recorded `health_status: healthy`, 100% origin
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

> **Left this repository 2026-09-15** (`TODO.md` → T-507). It is not tracked here; this entry is history.

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
- The deployment record of that run (the rebuild's evidence; removed from this repository with T-504)

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
2. Approve or amend the two egress FQDNs and decide whether an AWS deployment needs an equivalent
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

## R-012 — Token for a shared project board

**Problem**
`TODO.md` → T-505 wants one GitHub Project (v2) holding this repository's issues and pull requests, populated
automatically by an `add-to-project` workflow. User-owned Projects v2 are **not** reachable with a GitHub App
installation token, so the workflow needs either a fine-grained personal access token with `project` scope stored as
a secret in this repository, or the repositories moved under an organization where the App can hold the
`organization_projects` permission.

**Why it needs an owner**
Creating a long-lived personal token, or reorganizing the repositories under an organization, is
the repository owner's decision; CBTS standards prefer the short-lived, identity-based option where
one exists.

**Required owner**
Repository owner.

**Required action**
Choose one:
1. Move the repositories under a GitHub organization, grant the App
   `organization_projects: write`, and use the App token in the `add-to-project` workflow; or
2. Create a classic personal access token with the `project` scope (GitHub's fine-grained tokens do not cover a
   user-owned project; check GitHub's current documentation before choosing), store it as `PROJECT_BOARD_TOKEN`
   here, and set a rotation reminder.

**Impact if unresolved**
Work stays visible per repository only. Nothing else depends on this.

**References**
- [`TODO.md`](TODO.md) → T-505

---

## R-013 — Bring this repository live: the Docker Hub repository, its OIDC connection and the first publish

**Problem**
NetworkEyes stands alone (owner decision 2026-10-25): this repository builds, signs and publishes its own images to
Docker Hub and depends on nothing but itself and that registry. The publishing workflows read repository variables and
a Docker Hub OIDC connection that only the owner can create; none of them can be committed. Until they exist, no image
is published from this repository.

**Why it needs an owner**
Docker Hub repositories and OIDC connections, repository variables and branch protection are settings only the
repository owner can write.

**Required owner**
Repository owner.

**Required action** — `TODO.md` → T-728 has the pages, the subject-claim rules and the exact commands. In short, in
this order:
1. On Docker Hub, in the `hybridcloudworks` organisation, create the **public** repository `img-ne-appliance-app`.
2. In Docker Home, create the OIDC connection with one ruleset for `main` (scope Image Push on that repository, used
   by `200`) and, before the first release, a SECOND ruleset for `refs/tags/v*` (Image Push only, used by `310`).
3. On this repository → *Settings → Secrets and variables → Actions → Variables*: `DOCKERHUB_NAMESPACE`,
   `DOCKERHUB_CONNECTION` (not `DOCKERHUB_ENABLED` yet: step 4). No registry token is created for publishing (the registry cleanup
   `370` still uses a personal access token, step 3 of R-026). Leave *Actions → General → Workflow permissions* on
   *read-only*, which is how it is set (read 2026-10-25): `310` declares its own `contents: write` for the release job.
4. Decide Docker Scout's credential and run the dry run of the connection (`200` with `rehearsal` ticked: one job that
   logs in, pushes, signs, attests, verifies and tags a throwaway image `rehearsal-<run id>`, which you remove by
   hand); both are in T-728. Only when the dry run is green and the Scout decision is settled, set
   `DOCKERHUB_ENABLED` to `true`.
5. Run `200 · Build Container Images` once from *Run workflow* (or push to `main` touching a Dockerfile). To release:
   run `310 · Release CLI Tool` as a dry run first, then tag the commit it names (README → *Publishing the images*; the checks are under *Verifying images*).
6. Keep the branch protection on `main` here (required check `300 · Test Codebase`, review requirements).

**Impact if unresolved**
No image is published from this repository, so there is nothing to scan, sign, release or pull.

**References**
- [`TODO.md`](TODO.md) → T-728 (the owner steps with commands)
- `.github/workflows/200-build-images.yml`, `310-release-version.yml`, `370-registry-cleanup.yml`
  (the variables each reads are in its header and `vars.*` references)

---

## R-014 — Move the Wiki and delete the original repository

> **Superseded 2026-10-11.** The original repository is this one, renamed `HCW-NetworkEyes_App`. On 2026-10-10 the
> owner merged the lineage of the separate core repository back here, and on 2026-10-11 decided that this repository is
> the product and the separate core repository is reference only. Nothing here is deleted. Of the earlier plan only
> the Wiki move survives, reversed in direction: the pages on the earlier core repository's wiki come back to this
> repository's wiki (R-023). The earlier plan (delete the original after repointing other repositories' variables and
> migrating the legacy container packages) is withdrawn; this repository sets nothing in any other repository.

---

## R-015 — Decide the customer-facing appliance repository names

> **Withdrawn 2026-10-25.** The repositories that deploy the images belong to another owner's account and are not
> part of this repository (NetworkEyes stands alone, see R-013). Their names are not this repository's decision, and
> the variables, dispatch targets and review-engine constants the earlier text said a rename would touch no longer exist.

---

## R-016 — Retire `apps/cna-worker` and its image and service

**Problem**
`apps/cna-worker/main.py` is a 101-line placeholder: it writes a "CNA publish placeholder" HTML
file for a hard-coded `sample-engagement` and exits. `POST /publish` superseded it
(`CHANGELOG.md`, "The client-portal publish story is real"). A deployment of the images still runs it as an
always-on service, so it exits and restarts continuously, and its image is built and scanned on every push.

**Why it needs an owner**
Removing it changes the published image set (the `worker` image and its `worker-<version>` release tag), which consumers rely on and which `CLAUDE.md`
(*The image contract*) says is never a unilateral cleanup.

**Required owner**
Repository owner.

**Required action**
Approve deleting `apps/cna-worker` and its Dockerfile and build job here, recorded under `Changed` in `CHANGELOG.md`
and in the release notes so that whoever deploys the images can drop the worker service.

**Impact if unresolved**
Wasted compute, a permanently restarting container in every environment, and documentation that
describes a component that does nothing.

**References**
- v1.0 review findings IMG-003, ARCH-004, ARCH-101, PY-016

## R-017 — Stop publishing the CLI image on every push

**Problem**
Nothing in this repository pulls the CLI image (`sha-<7>`) except the release, which gives it the `<version>` tag (the other four images get `<component>-<version>`).
It is the largest image (draw.io + Electron + Xvfb) and its root
`COPY . .` ships `TODO.md`, `REVIEW.md` and `cna/review/**` inside a customer-pullable artifact.

**Required owner**
Repository owner.

**Required action**
Decide: keep the CLI image as a developer-only local build (`docker-compose.yml` already has it) and
drop it from `200-build-images.yml` and `310` (a release would then lose the plain `<version>` tag, which sits on the CLI image); or
keep publishing and fence the build context.

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

**Decision (2026-10-25, ticket #248, taken under the owner's instruction to close the open issues): `self-host`.**
The editor is the draw.io web app (`draw.war` of the jgraph/drawio release, Apache-2.0, pinned by version and sha256 in
the `drawio-webapp` stage of `apps/cna-web/Dockerfile`), served by the web image under `/drawio/`. Not chosen: a customer
opt-in to the public service (a data-handling statement does not make a customer's network layout leave the
appliance) and disabling the Diagram page (the page is the product's editor).

**What now applies**
- The iframe loads `/drawio/index.html?embed=1&proto=json&offline=1&stealth=1&...` from the same deployment. No request
  goes to a draw.io or diagrams.net host, and the page needs no internet egress from the analyst's browser.
- The editor's files carry their own Content-Security-Policy (`next.config.ts`, values in `lib/drawio-embed.ts`):
  `default-src 'none'`, `connect-src 'self'`, no inline script. Even a hostile diagram cannot make the browser send data to
  another host. The application's own CSP now has `frame-src 'self'` only.
- The editor runs in a sandbox without `allow-same-origin`, so its scripts get an opaque origin and cannot read the
  application's cookies, storage or same-origin responses. The sandbox is set twice: as the `sandbox` attribute of the
  iframe and as the `sandbox` directive of the editor's own CSP, so it also holds when someone opens
  `/drawio/index.html` directly (without the directive that visit would run the editor as the application's origin, with
  the session cookie readable; checked in a browser, see `CHANGELOG.md`). The editor's service worker files are deleted
  from the image so nothing registers one on the application's origin. The price of the sandbox is that the host page
  answers the editor with `postMessage(..., "*")` (the only target an opaque origin accepts) to the one window it
  created, and that `/drawio/*` is sent with `Access-Control-Allow-Origin: *`: the editor fetches its language file with
  XHR and an opaque origin needs CORS for that. Those files are public Apache-2.0 static content with no customer data;
  a browser that applies Private Network Access lets any website read them from an appliance on a private address,
  which exposes nothing that is not public. Scoping the header to the fetched paths was left out: the set of paths
  depends on which editor features are used, and a miss breaks the editor.
- The files in the image are read-only (mode 444/555) and carry the version in the image label
  `io.github.saulpatinojr.drawio-webapp.version`.
- The "Launch draw.io" link to the public site on the Diagram page is gone, and the MCP `create_diagram` result returns
  the same-origin path instead of the public viewer.
- Guards: `apps/cna-web/lib/drawio-embed.test.ts` (embed URL has no host; every CSP directive has exactly its expected
  sources, no bare `*`, host or scheme; the CSP carries the sandbox without `allow-same-origin`; `next.config.ts` sends
  those headers on `/drawio/:path*`; the middleware matcher leaves the path out; no web source or test file names a public
  host), `apps/cna-web/components/diagrams/DrawioEmbed.test.tsx` (the rendered iframe is sandboxed; messages from another
  window or another origin are ignored; replies go to the iframe's window only) and
  `tests/security/test_drawio_self_hosted.py` (pin shape, checksum verified before the unzip in one `&&` chain, the trim
  fails closed, read-only files, licence, label, the weekly workflow, no live file names a public host).
- **Owner and cadence:** the repository owner owns the pin. Review it monthly (the first Monday of the month) and on
  every security advisory: the workflow `380 · draw.io Editor Pin Check` runs weekly, compares `ARG DRAWIO_WEBAPP_VERSION`
  with the newest jgraph/drawio release and the advisories published since the pinned release, and opens or updates one
  issue titled "draw.io editor pin is out of date" (it closes it when the pin is current). Advisories:
  https://github.com/jgraph/drawio/security/advisories. At 32.6.1 the published ones are fixed (the newest, GHSA-v2pv-rjf8-9w9v
  and GHSA-ff67-v9r9-6877, fixed in 31.4.6, are query-parameter exfiltration bugs of the kind that `connect-src 'self'`
  and the sandbox cap anyway). To bump: change both ARGs, run the web and security tests, rebuild, repeat the browser
  check, add a `CHANGELOG.md` line.
- Known limits: the draw.io project calls its Docker image "a test version" and sells a supported production edition;
  the Apache-2.0 code is free to use as done here, but support and security fixes come from bumping the pin. Dependabot
  cannot track a release asset (the reminder above stands in for it). The editor files add about 65 MB to the web
  image. Local development has no `/drawio/` until the files are copied in (comment on the Dockerfile stage).

**Impact if unresolved**
Resolved: no customer topology leaves the deployment through the editor.

**References**
- v1.0 review findings UI-002, ARCH-012

## R-020 — Aeonik font licence and OCI licence label

**Problem**
`apps/cna-web/app/fonts/Aeonik-Regular.ttf` and `cna/report_engine/templates/assets/fonts/` ship a
commercial typeface as a webfont and embedded in PDFs with no licence file in the repository. The
OCI image label says `licenses="Proprietary"` while the repository `LICENSE` is Apache-2.0.

**Required owner**
Legal / brand (the font part only; the label part is decided and done).

**Decision, 2026-10-25 (owner)**
Apache-2.0 for the code and for the image label. Done in ticket #251: `org.opencontainers.image.licenses` in
`Dockerfile` now reads `Apache-2.0`, matching `LICENSE`, and a new `NOTICE` file says the Aeonik typeface is
separately licensed. `tests/unit/test_licence_statement.py` fails if the label, `LICENSE` and `NOTICE` stop agreeing.

**Still open: the Aeonik font licence**
What was checked on 2026-10-25: the font file's own metadata names "Mark Bloom and Joe Leadbeater (c) 2018",
version 1.000, and the licence "This Is Our Shop EULA" (thisisourshop.com, which no longer resolves). CoType Foundry
now sells Aeonik under four agreements (desktop, web, app, trial; https://cotypefoundry.com/licensing/). Its trial
agreement allows internal evaluation only, forbids use on any public website or in final commercial files, and
forbids passing the font on to anyone (https://www.datocms-assets.com/135497/1731056476-cotype-eula-trial-24.pdf).
Nothing in the repository shows which agreement, if any, covers the copy that is committed here and shipped in the
web image and in PDF reports, so `NOTICE` lists it as "licence to be confirmed".

**Required action**
Either show proof of a CoType (or This Is Our Shop) desktop and web licence that covers serving the font on the web
and embedding it in customer PDFs, and record it here; or replace Aeonik with a font under an open licence (for
example one under the SIL Open Font License) in `apps/cna-web/app/fonts/`, `apps/cna-web/app/layout.tsx`,
`apps/cna-web/app/globals.css` and `cna/report_engine/templates/`. Recommended default: replace it, because the
repository is public and the font file is downloadable from it.

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

- **Decision (owner, 2026-10-11):** this repository's wiki (<https://github.com/saulpatinojr/HCW-NetworkEyes_App/wiki>)
  is the home; the earlier core repository is reference only and receives nothing. The pages (architecture, ADRs,
  runbooks, workflow reference) still live on that repository's wiki until the owner moves them. PowerShell, any
  folder (create one page in this repository's wiki first so its wiki repository exists). The command asks for the
  address of the earlier core repository's wiki, which its **Wiki** tab shows and which ends in `.wiki.git`:

  ```powershell
  $source = Read-Host "Address of the earlier core repository's wiki (ends in .wiki.git)"; git clone -q $source $env:TEMP\hcw-ne-wiki; git -C $env:TEMP\hcw-ne-wiki remote add app https://github.com/saulpatinojr/HCW-NetworkEyes_App.wiki.git; git -C $env:TEMP\hcw-ne-wiki -c user.email=34853639+saulpatinojr@users.noreply.github.com -c user.name=saulpatinojr push app master --force
  ```

  Success looks like: the page count at the App wiki equals the earlier wiki's. The earlier wiki is left as is.
- **Raised:** 2026-10-10, with the restore of the Core lineage into this repository.
- **Status:** Decided; the move is an owner step

## R-024 — Image signing identity after the restore

- **Decision (2026-10-25):** nothing to decide. Images are signed under this repository's own identity,
  `https://github.com/saulpatinojr/HCW-NetworkEyes_App/.github/workflows/200-build-images.yml@refs/heads/main`, and no
  other repository's configuration is changed from here. Whoever verifies the images uses that identity (README,
  *Publishing the images* and *Verifying images*). Renaming or moving this repository, that workflow file or the default
  branch changes the identity and must be announced in `CHANGELOG.md` and the release notes.
- **Raised:** 2026-10-10.
- **Status:** Superseded 2026-10-25

## R-025 — The draw.io MCP route is internal only

- **Decision (owner, 2026-10-24, ticket #245):** `internal-only`. The web route `/api/drawio-mcp/*` in `apps/cna-web`
  (it searches a built-in icon list and echoes posted draw.io XML; no database) used to answer anyone who could reach
  the web app, because the middleware excludes `/api` and the handler had no check. Its one caller is the Python client
  `cna/ai_engine/mcp_client/drawio_mcp_client.py`, which sends no cookie, so a sign-in check would have broken it.
- **What now applies:** the route answers `401` unless the request carries `Authorization: Bearer <CNA_API_TOKEN>`, the
  shared secret the api and web containers already hold (compared in constant time, never logged, never echoed). With no
  token configured on the web container every request is refused. The Python client sends the same header from the same
  setting. This adds no new setting. Not chosen: `public-exempt` (an intentional open route).
- **Raised:** 2026-10-24, ticket #245.
- **Status:** Decided and implemented in the pull request linked from the ticket; the note for deployers is `TODO.md` T-735

## R-026 — Owner steps after the governance and CI hygiene change

- **What changed:** the pull request for tickets #247, #252 and #253 added `.github/SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `PULL_REQUEST_TEMPLATE.md`, three issue forms, and three jobs in `300-test-codebase.yml`. It did not change a repository setting, the ruleset, a secret or a variable.
- **Step 1 — make the new checks required (ruleset). Done:** a read-back of the live ruleset on 2026-10-25 (<https://github.com/saulpatinojr/HCW-NetworkEyes_App/rules/25778319>) lists `Dockerfile Lint (hadolint)`, `Workflow Lint (actionlint)`, `Dependency Review` and `Image Scan (Trivy)` among its required checks. The original instruction follows for the record. Open <https://github.com/saulpatinojr/HCW-NetworkEyes_App/settings/rules>, choose `Protect main`, find `Require status checks to pass`, and add these three, exactly as written, keeping the seven that are already there: `Dockerfile Lint (hadolint)`, `Workflow Lint (actionlint)`, `Dependency Review`. Add them only after the pull request has merged and each has run once, otherwise GitHub offers no name to pick. `Dependency Review` is skipped on a push or a manual run and counts as passed there.
- **Step 2 — confirm private vulnerability reporting.** A read-only check on 2026-10-25 returned `enabled: true`. Open <https://github.com/saulpatinojr/HCW-NetworkEyes_App/security> and confirm that `Report a vulnerability` is shown; `.github/SECURITY.md` sends reporters there.
- **Step 3 — the `370` registry token (ticket #252, unchanged).** `370-registry-cleanup.yml` still uses the personal access token `DOCKERHUB_PERSONAL_TOKEN`; Docker Hub's OIDC connection does not replace it for deleting tags. The decision to keep it or to change how tags are removed is still open.
- **Raised:** 2026-10-25.
- **Status:** Open

## R-027 — Remove the orphaned cloud trust entries of the earlier repository name

- **Why this is here:** the earlier plan for the original repository (R-014) ended with a step that told the owner to delete the Azure federated identity credentials and the AWS OIDC role trust entries whose subject names that repository. R-014 is superseded and its text was dropped, so nothing else reminds the owner. This repository is that original, renamed, and GitHub puts the current repository name in a run's OIDC token, so an entry that still carries the earlier name matches no run of this repository. It is dead trust, and it would grant access again if anyone ever created a repository with that name under the same owner. (The earlier name is not written here on purpose: the standalone guard forbids it in live files. It is in this repository's git history and in the two clouds' trust entries themselves.)
- **Where to look.** Azure: Microsoft Entra admin center → App registrations → each application used for GitHub deployments → Certificates & secrets → Federated credentials; the subject looks like `repo:saulpatinojr/<name>:ref:refs/heads/main` or `...:environment:<name>`. AWS: IAM → Roles → the GitHub deploy role → Trust relationships; the condition on `token.actions.githubusercontent.com:sub`. Documentation: <https://learn.microsoft.com/entra/workload-id/workload-identity-federation-create-trust> and <https://docs.github.com/actions/security-for-github-actions/security-hardening-your-deployments/about-security-hardening-with-openid-connect>.
- **What to do.** Delete every entry whose repository part is not a repository you still deploy from. Keep entries for `HCW-NetworkEyes_App` and for the other current repositories. If you keep a subject for this repository, use the immutable form with the owner and repository ids (as `TODO.md` T-728 does for Docker Hub) so a rename never leaves a stale entry again.
- **Impact if unresolved:** none today; a standing, unused grant.
- **Raised:** 2026-10-25.
- **Status:** Open — not blocking

## R-028 — Should the default model ids of the bring-your-own engines follow the vendors' current models?

- **Why this is here:** the code defaults are `claude-opus-5` and `gpt-5.4` (`cna/ai_engine/chat_agent.py`, `apps/cna-web/lib/ai-engine.ts`; `.env.example` explains the override variables). The `.env.example` note asked someone to verify they are current. Checked 2026-10-25: both are still available. Anthropic lists Claude Opus 5 as a legacy model that is still available; the current Opus is `claude-opus-5-5` (<https://platform.claude.com/docs/en/models/overview>). OpenAI's deprecations page lists no retirement for `gpt-5.4`, whose flagship successors are `gpt-6-astra` and `gpt-6.1-sol` (<https://developers.openai.com/api/docs/deprecations>, <https://developers.openai.com/api/docs/models>). Nothing is broken, so nothing was changed.
- **The decision:** keep the two defaults, or move them to the current models. A move changes the price per assessment and the wording customers see, which is why it is yours to decide, not an engineer's.
- **Recommendation:** keep the defaults until Anthropic or OpenAI announces a retirement date for them, because customers who set no override would otherwise see answers change on the day of an upgrade.
- **How to answer:** reply "keep" or "move to current" on the issue or pull request that links this entry. If "move", an engineer changes the constants in both files together (they are pinned by one shared vector table, see `CLAUDE.md`, "AI engine rules") and updates `.env.example`.
- **Impact if unresolved:** none today; a retirement notice from either vendor would turn it into an urgent change.
- **Raised:** 2026-10-25.
- **Status:** Open — not blocking
