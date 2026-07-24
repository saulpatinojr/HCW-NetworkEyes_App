# AWS Setup TODO — human handoff for #110

This repo now contains the AWS Terraform (`infra/terraform/providers/aws/*` + `infra/terraform/environments/aws/*`) and the Python AWS discovery path, mirroring the Azure side. **None of it has been applied** — it is code-generation only. Everything a human must provide before the AWS stack can be deployed is a clearly-named placeholder. This file is the single source of truth for those placeholders.

> ⚠️ No real AWS account ID, IAM role ARN, or OIDC provider ARN appears anywhere in this repo. All are resolved at apply time from data sources or supplied as variables / `-backend-config`.

**How placeholders appear in the code:** the *only* literal placeholder strings committed are `<GITHUB_OWNER_PLACEHOLDER>` and `<GITHUB_REPO_PLACEHOLDER>` (defaults on `github_owner` / `github_repository` in `providers/aws/identity/variables.tf` and `environments/aws/{dev,prod}/workload/variables.tf`). Everything else in the tables below is *not* a token in the source — it is either resolved automatically (account/partition/region via `data` sources), supplied at `terraform init` (`-backend-config`), or passed as a `sensitive`/defaulted variable at apply. The `<…_PLACEHOLDER>` names used elsewhere in this doc are descriptive labels for values a human must provide, not strings to grep for.

## 1. Bootstrap the Terraform S3 backend (before first `init`)

The module/env `providers.tf` files use an **empty** `backend "s3" {}` block — the same init-time-config pattern the Azure side uses for `backend "azurerm" {}`. A human (or a one-time bootstrap workflow, mirroring Azure's `000-bootstrap-backend`) must create out-of-band and then pass via `-backend-config`:

| Placeholder | What it is | How to provide |
|---|---|---|
| `<TF_STATE_BUCKET_PLACEHOLDER>` | S3 bucket for Terraform state | Create an S3 bucket (versioning + SSE on); `terraform init -backend-config="bucket=..."` |
| `<TF_STATE_LOCK_TABLE_PLACEHOLDER>` | DynamoDB table for state locking | Create a table with `LockID` (S) partition key; `-backend-config="dynamodb_table=..."` |
| backend `key`, `region` | state object path + region | `-backend-config="key=aws/<env>/<platform|workload>.tfstate"`, `-backend-config="region=..."` |

The **platform** state and **workload** state are separate; the workload root reads platform outputs (VPC/subnet/SG IDs) via variables populated from the platform state.

## 2. AWS account identity

| Placeholder | Where | Resolution |
|---|---|---|
| AWS account ID | identity/runtime IAM ARNs | Resolved automatically via `data.aws_caller_identity.current.account_id` — **nothing to fill**, listed only so reviewers know no literal ID is committed. |
| partition | all ARN construction | `data.aws_partition.current.partition` (supports GovCloud/China). |
| region | provider + ARNs | `var.aws_region` (+ a fixed `us-east-1` aliased provider for the CloudFront-scoped WAF). |

## 3. GitHub OIDC → IAM (CI deploy trust)

The `identity` module provisions the GitHub OIDC provider + a deploy role assumable via `AssumeRoleWithWebIdentity`. A human must supply:

| Placeholder | What it is | How to provide |
|---|---|---|
| `<GITHUB_OWNER_PLACEHOLDER>` | GitHub org/user that owns the repo | `github_owner` variable |
| `<GITHUB_REPO_PLACEHOLDER>` | repository name | `github_repository` variable |
| `<GITHUB_OIDC_PROVIDER_ARN_PLACEHOLDER>` | ARN of the OIDC provider | **Created by this module** (`aws_iam_openid_connect_provider.github`); if an OIDC provider already exists in the account, import it instead (one per account). |
| `<CI_ROLE_NAME_PLACEHOLDER>` / deploy role ARN | the role CI assumes | **Output** as `github_deploy_role_arn`; wire it into CI secrets/vars *outside this repo change* (CI trigger config is intentionally out of scope). |

Notes:
- The OIDC provider **`thumbprint_list` is intentionally omitted** — AWS provider v5 validates GitHub's OIDC endpoint against its trusted CA store, so the legacy thumbprint is no longer required (and the old `40×f` placeholder in `migrate/` must not be reused).
- The deploy role's trust `sub` condition is scoped to `repo:<GITHUB_OWNER_PLACEHOLDER>/<GITHUB_REPO_PLACEHOLDER>:*`.

## 4. Secrets (supplied at apply, never committed)

All are `sensitive` variables on the `runtime`/`database` modules with **no defaults**:

| Placeholder / variable | Purpose |
|---|---|
| `db_admin_password` | RDS PostgreSQL master password |
| `nextauth_secret` | NextAuth/Auth.js session secret |
| `entra_client_secret` | Entra ID app-registration client secret (auth) |
| `credential_encryption_key` | app credential-encryption key |
| `dockerhub_username` / `dockerhub_token` | private image pulls (optional; module `count`s off when blank) |

## 5. TLS certificates (ACM)

Certificates are taken as **inputs** (default `null`) — the Terraform does **not** mint an unvalidated `aws_acm_certificate` (that would hang on DNS validation).

| Placeholder / variable | Purpose |
|---|---|
| `alb_certificate_arn` | HTTPS listener on the ALB (regional ACM cert) |
| `acm_certificate_arn` | CloudFront viewer cert (**must be in us-east-1**) |
| `custom_domain_name` | optional CloudFront alias; default `""` |

A human must request + DNS-validate these ACM certs (or add a Route 53 + `aws_acm_certificate_validation` flow) and pass the ARNs in.

## 6. Amazon Bedrock (AI module)

| Placeholder / variable | Action required |
|---|---|
| Bedrock **model access** | **Manual, per account + region**: enable foundation-model access in the Bedrock console. No Terraform resource covers this opt-in; `bedrock:InvokeModel` fails until it's done. |
| `model_ids` | Confirm the default model IDs exist in the chosen deploy region; adjust the variable if not. |

If the platform continues to call the external Azure OpenAI endpoint (as `migrate/` does today), the `ai` module can be disabled and the endpoint stays an env var.

## 7. Deploy order (workload root)

`identity → storage → database → observability → ai → runtime → compute → security`. The platform (networking) root must be applied first; the workload root consumes its outputs.

---

_Generated as part of the #110 AWS integration PR. CI/CD trigger wiring and secret population are intentionally out of scope here — see the companion handoff issue._
