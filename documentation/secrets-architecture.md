# CNA Platform — Secrets Architecture

> Version: 1.0.0 | Date: 2026-03-05
> This is the authoritative design document for how secrets are sourced,
> stored, rotated, and consumed across all platform surfaces.

---

## Architecture Overview

The CNA platform uses a **three-tier secrets model**:

```
┌──────────────────────────────────────────────────────────────────────────┐
│ TIER 1 — Never a secret (safe in .env.example, code, CLI flags)          │
│ CNA_VERSION, CNA_LOG_LEVEL, AWS_DEFAULT_REGION,                           │
│ AZURE_OPENAI_DEPLOYMENT_GPT4O, engagement IDs                             │
├──────────────────────────────────────────────────────────────────────────┤
│ TIER 2 — Local .env only (operator workstation, never CI)                 │
│ AZURE_CLIENT_SECRET (dev only — prefer az login)                          │
│ AWS_ACCESS_KEY_ID / SECRET (dev only — prefer aws sso login)              │
│ AZURE_OPENAI_API_KEY (dev only — prefer managed identity)                 │
├──────────────────────────────────────────────────────────────────────────┤
│ TIER 3 — Managed secret stores (production + CI/CD)                       │
│ Azure Key Vault ──┬── Azure: DefaultAzureCredential → KV SDK            │
│ AWS SSM / Secrets Manager ─┼── AWS: OIDC → STS → SSM GetParameter        │
│ GitHub Secrets ────────┴── Actions only (CNA_AWS_ROLE_ARN, etc.)        │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Surface Map

Each platform surface has its own secret source. No surface shares credentials
with another unless explicitly designed to do so.

| Surface | Auth Method | Secret Source | Long-Lived Key? |
|---|---|---|---|
| Local dev — Azure | `az login` | Azure CLI token cache | No |
| Local dev — AWS | `aws sso login` | AWS SSO session | No |
| CI (`ci.yml`) | `GITHUB_TOKEN` | GitHub (automatic) | No |
| Release (`release.yml`) | `GITHUB_TOKEN` | GitHub (automatic) | No |
| CD Publish — AWS | OIDC → `sts:AssumeRoleWithWebIdentity` | GitHub Secret: `CNA_AWS_ROLE_ARN` | No |
| CD Publish — Azure | OIDC → Federated Identity | GitHub Secrets: `CNA_AZURE_*` | No |
| Contractor workflow | `KeyVaultCredentialProvider` | Azure Key Vault | No |
| Azure AI (OpenAI) | `DefaultAzureCredential` | Azure Key Vault or Managed Identity | No |

**Zero long-lived keys in any CI/CD surface.** This is enforced by design, not policy.

---

## Tier 3 Deep Dive — Azure Key Vault

### What Lives in Key Vault

| Secret Name | Type | Description | Rotation |
|---|---|---|---|
| `cna-openai-api-key` | Key Vault Secret | Azure OpenAI API key (optional — fallback if managed identity unavailable) | 90 days |
| `cna-teams-webhook-url` | Key Vault Secret | MS Teams channel webhook for CRITICAL alerts | On webhook change |
| `cna-notification-email-from` | Key Vault Secret | Sender address for notifications | On change |

### What Does NOT Live in Key Vault

- Azure AD credentials (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`) — these are not secrets
- `AZURE_CLIENT_SECRET` — if present at all, lives in local `.env` only; production uses managed identity
- Engagement data, discovery output, reports — not secrets

### Access Model

```
Operator workstation
  └─ az login
      └─ DefaultAzureCredential
          └─ Azure Key Vault (Key Vault Secrets User role required)
              └─ cna/core/auth.py — KeyVaultCredentialProvider.get(secret_name)

Contractor (no az login)
  └─ AZURE_CLIENT_ID + AZURE_CLIENT_SECRET in .env
      └─ DefaultAzureCredential (env var path)
          └─ Azure Key Vault (same role)
              └─ KeyVaultCredentialProvider.get(secret_name)
```

### Required RBAC

```bash
# Assign Key Vault Secrets User to operator or app registration
az role assignment create \
  --role "Key Vault Secrets User" \
  --assignee <OPERATOR_OBJECT_ID_OR_CLIENT_ID> \
  --scope "/subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.KeyVault/vaults/<VAULT_NAME>"
```

### Key Vault Setup (First Time)

```bash
# Create vault
az keyvault create \
  --name cna-secrets-prod \
  --resource-group cna-rg \
  --location eastus \
  --enable-rbac-authorization true   # use RBAC, not vault access policies

# Store OpenAI key (if not using managed identity)
az keyvault secret set \
  --vault-name cna-secrets-prod \
  --name cna-openai-api-key \
  --value "<YOUR_OPENAI_KEY>"

# Store Teams webhook (if used)
az keyvault secret set \
  --vault-name cna-secrets-prod \
  --name cna-teams-webhook-url \
  --value "https://outlook.office.com/webhook/..."

# Set in .env (not the secret value — just the vault URL)
echo 'AZURE_KEY_VAULT_URL=https://cna-secrets-prod.vault.azure.net/' >> .env
```

---

## Tier 3 Deep Dive — AWS SSM Parameter Store

### What Lives in SSM

SSM Parameter Store is the AWS equivalent of Key Vault for this platform.
Used only when the operator chooses AWS as the primary platform (not Azure).

| Parameter Path | Type | Description |
|---|---|---|
| `/cna/prod/openai-api-key` | SecureString | Azure OpenAI API key (if using from AWS context) |
| `/cna/prod/teams-webhook-url` | SecureString | MS Teams webhook |
| `/cna/prod/publish-bucket` | String | S3 bucket name (non-sensitive, but convenient to store here) |

### Access Model

```
Operator (local)
  └─ aws sso login
      └─ IAM identity with ssm:GetParameter on /cna/* path
          └─ cna/core/auth.py — AWSCredentials.get_ssm_parameter(path)

CI/CD (cd-publish.yml)
  └─ OIDC → sts:AssumeRoleWithWebIdentity
      └─ CNA-Publish role (ssm:GetParameter included in role policy)
          └─ AWSCredentials.get_ssm_parameter(path)
```

### SSM Setup (First Time)

```bash
# Store secrets
aws ssm put-parameter \
  --name "/cna/prod/teams-webhook-url" \
  --value "https://outlook.office.com/webhook/..." \
  --type SecureString \
  --key-id alias/aws/ssm   # default KMS key; use custom key for compliance

# Grant CNA-Publish role access
# Add to CNA-Publish role policy:
# {
#   "Effect": "Allow",
#   "Action": ["ssm:GetParameter", "ssm:GetParameters"],
#   "Resource": "arn:aws:ssm:<REGION>:<ACCOUNT_ID>:parameter/cna/*"
# }
```

---

## Tier 3 Deep Dive — GitHub Secrets

GitHub Secrets are used **only** for values that GitHub Actions workflows need
to authenticate to external systems. They are not a general-purpose secret store.

### Complete Inventory

| Secret | Workflow | Purpose | OIDC replaces? |
|---|---|---|---|
| `CNA_AWS_ROLE_ARN` | `cd-publish.yml` | Role ARN for `sts:AssumeRoleWithWebIdentity` | Yes — role itself is the only required value |
| `CNA_PUBLISH_BUCKET` | `cd-publish.yml` | S3 bucket name | No (bucket name is not sensitive but convenient as a secret) |
| `CNA_AZURE_CLIENT_ID` | `cd-publish.yml` | App registration client ID for OIDC | Yes — client ID for federated token exchange |
| `CNA_AZURE_TENANT_ID` | `cd-publish.yml` | Azure AD tenant ID | Yes |
| `CNA_AZURE_SUBSCRIPTION_ID` | `cd-publish.yml` | Subscription for storage account | No (not sensitive) |
| `GITHUB_TOKEN` | All workflows | Auto-issued by GitHub — no setup needed | N/A |

### What OIDC Eliminates

Without OIDC, you would need:
- `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` as secrets (long-lived, rotatable, leak risk)
- `AZURE_CLIENT_SECRET` as a secret (long-lived, rotatable, leak risk)

With OIDC, you need only the Role ARN / Client ID (non-secret identifiers).
The actual credential (JWT) is issued per-job by GitHub and exchanged for a
short-lived cloud token. It expires when the job ends.

---

## Secret Rotation Policy

| Secret | Where Stored | Rotation Frequency | Who Rotates | Method |
|---|---|---|---|---|
| Azure OpenAI API Key | Key Vault | Every 90 days | Operator | `az keyvault secret set` with new version; old version auto-expires |
| Teams Webhook URL | Key Vault / SSM | On any team change | Operator | Replace secret value; no code change needed |
| `AZURE_CLIENT_SECRET` (dev only) | Local `.env` only | Every 90 days | Operator | Azure Portal → App registrations → Certificates & secrets |
| GitHub `CNA_AWS_ROLE_ARN` | GitHub Secrets | Only on role re-creation | Operator | Update secret value in GitHub Settings |
| GitHub `CNA_AZURE_CLIENT_ID` | GitHub Secrets | Only on app re-creation | Operator | Update secret value in GitHub Settings |
| AWS IAM Role Keys (dev) | Local `.env` | 90 days max — prefer SSO | Operator | `aws iam create-access-key` + delete old key |

**OIDC tokens**: No rotation needed — they are ephemeral (per-job lifetime).
**Managed Identity tokens**: No rotation needed — managed by Azure platform.

---

## Secret Detection Controls

Four overlapping controls prevent secrets from entering the repo:

| Layer | Control | When It Runs |
|---|---|---|
| L1 | `.gitignore` — `.env`, `*.pem`, `*.key`, `secrets/` excluded | Prevents file from being staged |
| L2 | `detect-secrets` pre-commit hook | Before every local commit |
| L3 | `gitleaks` pre-commit hook | Before every local commit |
| L4 | `gitleaks-action` in CI | On every push and PR to main/develop |

If a secret bypasses L1–L3 (impossible for `.env` due to `.gitignore`, but
possible if someone hardcodes a value), L4 catches it and blocks the PR.

**What to do if a secret is committed:**
1. Immediately rotate/revoke the leaked secret in the issuing system
2. Remove from git history: `git filter-repo --path <file> --invert-paths`
3. Force push (requires branch protection bypass)
4. Run `detect-secrets scan > .secrets.baseline` to reset baseline
5. Document the incident in `documentation/policies/incident-log.md`

---

## Frequently Asked Questions

**Q: Do I need Azure Key Vault for a single-operator local engagement?**
No. Run `az login` and leave `AZURE_KEY_VAULT_URL` blank in `.env`.
The platform only calls `KeyVaultCredentialProvider` if `AZURE_KEY_VAULT_URL` is set.

**Q: Do I need AWS SSM for a local AWS engagement?**
No. Run `aws sso login` or `aws configure` and set credentials in `.env`.
SSM is an optional enhancement for teams and multi-operator setups.

**Q: Can I run CI without setting any GitHub secrets?**
Yes. `ci.yml` and `release.yml` need only `GITHUB_TOKEN`, which is automatic.
Only `cd-publish.yml` needs the cloud secrets, and only when you run it.

**Q: What if I only test Azure first?**
Set only the Azure GitHub secrets (`CNA_AZURE_*`). Leave AWS secrets unset.
`cd-publish.yml` only attempts OIDC for the cloud you select in the `cloud` input.

**Q: Are engagement IDs secrets?**
No. They contain no client data (format: `<slug>-<date>-<hex>`). They are used
as folder names and blob prefixes. Do not treat them as secrets.

**Q: Is `CNA_PUBLISH_BUCKET` sensitive?**
Not technically — an S3 bucket name is not a credential. It is stored as a
GitHub Secret for convenience so the CD workflow does not need a hardcoded value.
If you prefer, you can move it to a GitHub Actions variable (non-secret).
