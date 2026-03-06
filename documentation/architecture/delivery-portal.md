# Delivery Portal — Architecture

> Version: 1.0.0 | Status: Active | Date: 2026-03-05

---

## What This Component Does

The delivery portal publishes completed report artifacts to cloud storage
(Azure Blob Storage or AWS S3) and generates a time-limited access URL
for the client. The portal is a static HTML page with pre-signed links —
there is no server-side runtime in the client's environment.

---

## Deployment Targets

| Target | Condition | Access Method |
|---|---|---|
| Azure Blob Storage (static website) | `--azure` flag | SAS token, 7-day TTL max (DD-019) |
| AWS S3 (static website) | `--aws` flag | Pre-signed URL, 7-day TTL max (DD-019) |

TTL is capped at 7 days by code, not configuration. Longer TTLs are rejected
before upload (`DeliveryPortalError` raised).

---

## Publish Flow

```
cna publish run --engagement-id <id> --cloud azure|aws
        │
        ├─ 1. Verify review_complete=True (blocks publish if false)
        ├─ 2. Load all artifacts from EngagementStore.output_paths["reports"]
        ├─ 3. Generate portal HTML (artifact list with titles, descriptions)
        ├─ 4. Upload artifacts + portal to storage
        │     ├─ Azure: BlobServiceClient → container with static website enabled
        │     └─ AWS:   boto3 S3 → bucket with static website + public read policy
        ├─ 5. Generate time-limited URL
        │     ├─ Azure: generate_sas_token(expiry=now+7d)
        │     └─ AWS:   generate_presigned_url(ExpiresIn=604800)
        ├─ 6. Write portal_url to EngagementStore
        └─ 7. Audit log: portal published, URL, TTL, operator identity
```

---

## Retention Policy (DD-019)

All engagement data (discovery checkpoints, reports, portal) is retained for
90 days post-delivery, then deleted:

- Local: `EngagementStore.purge(engagement_id)` deletes the entire `data_dir/{engagement_id}/` tree
- Azure: Blob lifecycle policy (90-day delete rule on the CNA container)
- AWS: S3 lifecycle rule (90-day expiration on the `cna-deliverables-prod/` prefix)

Retention details and client data deletion SLA are documented in
`documentation/policies/data-handling-policy.md`.

---

## CORS Configuration

Both storage targets must have CORS configured to allow the client's browser to
load report artifacts:

```yaml
# Azure Storage CORS rule
allowed_origins: ["*"]
allowed_methods: ["GET"]
max_age_in_seconds: 3600

# AWS S3 CORS rule
AllowedOrigins: ["*"]
AllowedMethods: ["GET"]
MaxAgeSeconds: 3600
```

The `cna publish` command applies these rules automatically on first publish.
