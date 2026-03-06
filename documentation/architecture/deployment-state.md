# CNA Platform — Deployment State

> Version: 1.1.0 | Date: 2026-03-05
> This document is the authoritative status of what is and is not deployed
> across all four platform planes.

---

## The Four Planes

The CNA platform spans two distinct concerns:

| Plane | What It Is | Owner |
|---|---|---|
| **CNA Platform** | The tool itself — code, CI/CD, container image | You (saulpatinojr) |
| **Vendor Cloud** | AWS/Azure infra you own that hosts secrets and deliverables | You |
| **CNA-Client** | The customer’s cloud environment being assessed | Customer |

The CNA platform and Vendor Cloud are your responsibility to stand up.
The CNA-Client environment is granted to you per-engagement by the customer.

---

## Deployment Status by Surface

### ✅ Fully Deployed

| Resource | Location | Notes |
|---|---|---|
| Source code | `main` branch | All engines implemented |
| Documentation | `documentation/` | All policies, arch docs, secrets arch |
| CI workflow (`ci.yml`) | GitHub Actions | Runs on every push: scan → lint → test → docker |
| `develop` branch | GitHub | Protected; CI required |
| Pre-commit hooks | Operator workstation | gitleaks, detect-secrets, ruff |
| `.secrets.baseline` | Repo root | Baseline set |

### ⚠️ Configured, Not Yet Triggered

| Resource | Blocker | Action Needed |
|---|---|---|
| `release.yml` | No git tag exists | `git tag v0.1.0 && git push --tags` |
| `cd-publish.yml` | GitHub Secrets not set | Set secrets (see below) |
| GHCR image | No release tag | Triggered automatically on first tag |

### ❌ Not Yet Created

#### Vendor AWS
| Resource | Why Needed | Setup Doc |
|---|---|---|
| OIDC Provider | `cd-publish.yml` OIDC auth | `secrets-architecture.md` |
| IAM Role: `CNA-Publish` | S3 upload from CI | `secrets-architecture.md` |
| S3 Bucket: `cna-deliverables` | Delivery portal | `delivery-portal.md` |
| SSM Parameter Store `/cna/prod/*` | Optional secrets store | `secrets-architecture.md` |

#### Vendor Azure
| Resource | Why Needed | Setup Doc |
|---|---|---|
| App Registration (Federated OIDC) | `cd-publish.yml` Azure auth | `secrets-architecture.md` |
| Key Vault: `cna-secrets-prod` | Secrets at runtime | `secrets-architecture.md` |
| Storage Account: `cna-deliverables` | Delivery portal | `delivery-portal.md` |

#### GitHub
| Secret | Needed By | Notes |
|---|---|---|
| `CNA_AWS_ROLE_ARN` | `cd-publish.yml` | Set after IAM Role created |
| `CNA_PUBLISH_BUCKET` | `cd-publish.yml` | S3 bucket name |
| `CNA_AZURE_CLIENT_ID` | `cd-publish.yml` | App Registration client ID |
| `CNA_AZURE_TENANT_ID` | `cd-publish.yml` | Azure AD tenant ID |
| `CNA_AZURE_SUBSCRIPTION_ID` | `cd-publish.yml` | Azure subscription |

#### CNA-Client (per engagement)
| Resource | Platform | Who Creates | Notes |
|---|---|---|---|
| IAM Role: `CNA-ReadOnly` | AWS (each member acct) | Customer | See `permission-grant-guide.md` |
| Management Group Reader | Azure (root MG) | Customer | See `permission-grant-guide.md` |
| Reader (root MG) | Azure | Customer | Subscription-level traverse |

---

## Minimum to Run First Engagement

To run a single local engagement right now (no CI/CD, no portal):

```bash
# Azure
az login
cna discover azure --engagement-id <slug>-$(date +%Y%m%d)-0000 --tenant-id <TENANT_ID>
cna analyze     --engagement-id <slug>-...
cna review complete --engagement-id <slug>-...
cna report generate --engagement-id <slug>-...
# Reports written to ~/.cna/engagements/<id>/reports/

# AWS
aws sso login
cna discover aws --engagement-id <slug>-$(date +%Y%m%d)-0000 \
  --org-role arn:aws:iam::<MGMT_ACCT>:role/CNA-ReadOnly
cna analyze     --engagement-id <slug>-...
cna review complete --engagement-id <slug>-...
cna report generate --engagement-id <slug>-...
```

No vendor cloud resources required for local engagement — reports stay on disk.
Portal publish requires S3 or Azure Storage (set those up before first client delivery).
