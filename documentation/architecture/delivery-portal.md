# CNA Platform — Delivery Portal

> Version: 1.0.0 | Status: ACTIVE | Date: 2026-03-05

---

## Overview

The delivery portal is the final platform component. It takes the deliverables
produced by the report generation engine and makes them accessible to the client
through a password-protected, time-limited portal hosted on S3 or Azure Blob Storage.

---

## Data Flow

```
EngagementStore
  deliverables/manifest.json     ─┬
  findings/report.json           ─┤  (checksum for staleness)
  access/record.json             ─┘  (written after publish)
                                  │
                                  ▼
                         cna publish run
                          │
                          ├─ DD-019: RetentionEngine.check()
                          │     raises RetentionExpiredError if >90 days
                          │
                          ├─ Load DeliverableManifest
                          │
                          ├─ Compute current FindingsReport checksum
                          │
                          ├─ S3Deployer / AzureBlobDeployer
                          │   ├─ configure_cors() / ensure_container()
                          │   ├─ upload(file, content_type=...)  [per file]
                          │   └─ generate_presigned_url() / generate_sas_token()
                          │
                          ├─ PortalGenerator.build_entries()
                          │   └─ DD-013: stale badge if checksum mismatch
                          │
                          ├─ PortalGenerator.generate()  →  index.html
                          │
                          ├─ Upload index.html → pre-signed portal URL
                          │
                          └─ AccessManager.build_record()  →  EngagementStore
                               (metadata only, no URL stored)
                          │
                          ▼
                         Client receives portal URL
                         (expires automatically after TTL)
```

---

## Design Contracts (All Enforced in Code)

| Contract | Where Enforced | What Happens on Violation |
|---|---|---|
| DD-019: 90-day retention | `RetentionEngine.check()` — first check in `cna publish run` | `RetentionExpiredError` raised — no upload proceeds |
| DD-013: Staleness detection | `PortalGenerator.build_entries()` compares checksums | Stale badge rendered in portal HTML |
| Max link TTL: 7 days | `AccessManager.compute_expiry()` + deployer constructors | TTL silently capped; warning logged |
| Content-type headers | `S3Deployer.upload()` + `AzureBlobDeployer.upload()` using `CONTENT_TYPES` map | PDFs, PPTX, HTML served with correct MIME types |
| CORS on S3 bucket | `S3Deployer.configure_cors()` called before every upload batch | Browser downloads work without CORS errors |
| Private container | `AzureBlobDeployer.ensure_container(public_access=None)` | No public Azure Blob access — all downloads via SAS token |
| Pre-signed URL never stored | `AccessManager` stores metadata only | Audit trail has no live download links |
| Deletion is logged | `RetentionEngine.enforce()` logs before executing | Irreversible operations always have an audit record |

---

## Portal HTML Features

- Self-contained single `index.html` — zero JavaScript dependencies
- Severity-independent: shows all deliverable formats and languages
- **Staleness banner**: shown when any entry has a checksum mismatch
- **Stale badge** per row: individual entry flagged with tooltip explaining reason
- **Current badge** per row: confirms this deliverable matches latest analysis
- Download links are injected pre-signed URLs / SAS tokens at publish time
- Expiry date displayed prominently in header
- Footer: data deletion notice per DD-019
- Print-ready: `@media print` styles included

---

## CLI Reference

```bash
# Publish to AWS S3
cna publish run \
  --engagement-id acme-20260305-a3f2 \
  --cloud aws \
  --bucket cna-deliverables-prod \
  --ttl-hours 168

# Publish to Azure Blob Storage
cna publish run \
  --engagement-id acme-20260305-a3f2 \
  --cloud azure \
  --storage-account cnadeliveries \
  --container acme-20260305-a3f2

# Check portal status
cna publish status --engagement-id acme-20260305-a3f2

# Check with custom data dir
cna publish status \
  --engagement-id acme-20260305-a3f2 \
  --data-dir /opt/cna/engagements
```

---

## Security Model

| Concern | How Addressed |
|---|---|
| Client access | Pre-signed URL (S3) or SAS token (Azure) — no public bucket/container |
| Credential storage | `DefaultAzureCredential` / IAM instance profile — no keys in code or config |
| URL leakage | Pre-signed URLs never written to `EngagementStore` — metadata only |
| Indefinite access | Hard 7-day TTL cap on all access links |
| Data retention | `RetentionEngine` enforces 90-day deletion — raises before re-publish of expired data |
| Upload integrity | Content-type headers enforce correct MIME; CORS limits origins to GET only |

---

## Required Permissions

### AWS (CNA-Publish IAM Role)

```json
{
  "Effect": "Allow",
  "Action": [
    "s3:PutObject",
    "s3:PutBucketCors",
    "s3:GetObject",
    "s3:DeleteObject",
    "s3:ListBucket"
  ],
  "Resource": [
    "arn:aws:s3:::cna-deliverables-*",
    "arn:aws:s3:::cna-deliverables-*/*"
  ]
}
```

### Azure (Storage Blob Data Contributor)

- Scoped to the storage account or target container
- `Storage Blob Data Reader` is insufficient — write access required for upload
- User Delegation Key required for SAS token generation (no storage account key)
