# CNA Platform — Deployment State

> Version: 1.0.0 | Date: 2026-03-05
> This document is the live record of what is deployed, what is pending, and
> what has never been created. Update this when infrastructure is provisioned.

---

## Status Legend

| Symbol | Meaning |
|---|---|
| ✅ | Deployed and running |
| ⚠ | Code/config complete — requires manual provisioning or secret setup |
| ✗ | Not yet created — no infrastructure exists |
| 🔵 | Client-owned infrastructure (read-only discovery target — CNA does not deploy this) |

---

## CNA VENDOR — GitHub (saulpatinojr/MVP-Cloud_Network_Assessment)

| Resource | Status | Blocker |
|---|---|---|
| Source code + documentation | ✅ | — |
| `ci.yml` — lint + test + secret scan | ✅ | — |
| `release.yml` — build + push image | ⚠ | Needs: first `git tag v0.1.0` push |
| `cd-publish.yml` — deploy to cloud | ⚠ | Needs: GitHub Secrets configured (see below) |
| Branch protection rules (main, develop) | ⚠ | Needs: manual setup in repo Settings → Branches |

---

## CNA VENDOR — GitHub Container Registry (ghcr.io)

| Resource | Status | Blocker |
|---|---|---|
| `ghcr.io/saulpatinojr/cna:0.1.0` image | ✗ | `release.yml` has never run (no git tag yet) |

---

## CNA VENDOR — Operator Workstation (Local)

| Resource | Status | Notes |
|---|---|---|
| `cna` CLI (`pip install -e .[dev]`) | ✅ | Working locally |
| `.env` file | ⚠ | Template exists (`.env.example`); cloud creds not yet filled |

---

## CNA VENDOR — Vendor Azure Subscription

| Resource | Status | Blocker |
|---|---|---|
| Azure Key Vault (`cna-secrets-prod`) | ✗ | Not provisioned — see `documentation/secrets-architecture.md` for setup |
| Azure Storage Account (delivery portal) | ✗ | Not provisioned — needed for `cna publish --azure` |
| Managed Identity or App Registration | ✗ | Not created — optional for local dev; required for CD publish to Azure |

---

## CNA VENDOR — Vendor AWS Account

| Resource | Status | Blocker |
|---|---|---|
| S3 Bucket (`cna-deliverables-prod`) | ✗ | Not provisioned — needed for `cna publish --aws` |
| IAM Role `CNA-Publish` + OIDC Trust Policy | ✗ | Not created — needed for `cd-publish.yml` to push to S3 |

---

## GitHub Secrets Required for CD

| Secret | Status | Purpose |
|---|---|---|
| `CNA_AWS_ROLE_ARN` | ✗ Not set | OIDC role ARN for S3 publish |
| `CNA_PUBLISH_BUCKET` | ✗ Not set | S3 bucket name |
| `CNA_AZURE_CLIENT_ID` | ✗ Not set | OIDC federated identity for Azure publish |
| `CNA_AZURE_TENANT_ID` | ✗ Not set | Azure tenant for CD |
| `CNA_AZURE_SUBSCRIPTION_ID` | ✗ Not set | Azure subscription for storage account |
| `GITHUB_TOKEN` | ✅ Auto-issued | No setup needed |

---

## CNA-CLIENT — Azure Tenant (Customer)

> CNA does not deploy anything into the customer environment.
> All resources below are pre-existing client infrastructure that CNA reads.

| Resource | Status | Notes |
|---|---|---|
| Azure AD Tenant | 🔵 Client-owned | Provided by client |
| Management Group hierarchy | 🔵 Client-owned | CNA traverses root MG |
| Subscriptions (1..N) | 🔵 Client-owned | Enumerated via `Subscriptions.list()` |
| VNets / Subnets / NSGs / Route Tables | 🔵 Client-owned | Read via Azure Network APIs |
| ExpressRoute / VPN Gateway | 🔵 Client-owned | Read via `express_route_circuits.list_all()` |
| Azure Firewall / DDoS Protection | 🔵 Client-owned | Read via `azure_firewalls.list_all()` |
| **Reader RBAC at Root MG** | **⚠ Not yet assigned** | **Client must grant before `cna discover azure` can run** |

---

## CNA-CLIENT — AWS Organization (Customer)

> CNA does not deploy anything into the customer environment.
> All resources below are pre-existing client infrastructure that CNA reads.

| Resource | Status | Notes |
|---|---|---|
| AWS Organization (management account) | 🔵 Client-owned | Provided by client |
| Member accounts (1..N) | 🔵 Client-owned | Enumerated via `organizations:ListAccounts` |
| VPCs / Subnets / Security Groups | 🔵 Client-owned | Read via EC2 describe APIs |
| Transit Gateway / Direct Connect | 🔵 Client-owned | Read via EC2 + DC APIs |
| **IAM Role `CNA-ReadOnly` in each member account** | **✗ Not deployed** | **Client must deploy before `cna discover aws` can run** |

---

## Next Actions to Reach First Engagement

1. **Push `v0.1.0` tag** → triggers `release.yml` → GHCR image published
2. **Configure GitHub Secrets** (5 secrets above) → unblocks `cd-publish.yml`
3. **Provision Azure Key Vault** (`az keyvault create ...`) — see `documentation/secrets-architecture.md`
4. **Provision S3 + IAM Role** for CD publish — see `documentation/secrets-architecture.md`
5. **Send client `permission-grant-guide.md`** → client assigns Reader RBAC (Azure) + deploys `CNA-ReadOnly` IAM Role (AWS)
6. **Fill `.env`** with local dev credentials
7. **Run first engagement**: `cna init && cna discover aws|azure && cna analyze && cna review complete && cna report && cna publish`
