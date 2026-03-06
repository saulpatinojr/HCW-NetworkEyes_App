# Secret Rotation Runbook

> Version: 1.0.0 | Date: 2026-03-05

Step-by-step procedures for rotating every secret used by the CNA platform.
Run this runbook at the rotation frequencies defined in `documentation/secrets-architecture.md`.

---

## Azure OpenAI API Key (every 90 days)

```bash
# 1. Generate new key in Azure Portal
#    Azure OpenAI → Keys and Endpoint → Regenerate Key 1 (or Key 2 for zero-downtime)

# 2. Update Key Vault (new version created automatically; old version remains for rollback)
az keyvault secret set \
  --vault-name cna-secrets-prod \
  --name cna-openai-api-key \
  --value "<NEW_KEY>"

# 3. Verify
az keyvault secret show \
  --vault-name cna-secrets-prod \
  --name cna-openai-api-key \
  --query "value" -o tsv

# 4. Test
cna analyze --engagement-id test-$(date +%Y%m%d)-0000 --azure --dry-run
# Should complete without auth errors

# 5. Revoke old key in Azure Portal after confirming new key works
```

---

## Azure Client Secret (every 90 days — dev/contractor only)

```bash
# 1. Azure Portal → App registrations → <your app> → Certificates & secrets
#    Add new secret — do NOT delete old one yet

# 2. Update local .env
#    AZURE_CLIENT_SECRET=<NEW_VALUE>

# 3. Test
cna discover azure --engagement-id test-$(date +%Y%m%d)-0000 --tenant-id $AZURE_TENANT_ID --dry-run

# 4. Delete old secret in Azure Portal

# 5. Update contractor .env files out-of-band (secure channel)
```

---

## AWS IAM Access Keys (every 90 days — local dev only; prefer SSO)

```bash
# 1. Create new key
aws iam create-access-key --user-name cna-dev-operator

# 2. Update local .env
#    AWS_ACCESS_KEY_ID=<NEW_KEY_ID>
#    AWS_SECRET_ACCESS_KEY=<NEW_SECRET>

# 3. Test
cna discover aws --engagement-id test-$(date +%Y%m%d)-0000 \
  --org-role arn:aws:iam::$AWS_VENDOR_ACCOUNT_ID:role/CNA-ReadOnly --dry-run

# 4. Deactivate then delete old key
aws iam update-access-key --access-key-id <OLD_KEY_ID> --status Inactive
aws iam delete-access-key --access-key-id <OLD_KEY_ID>
```

---

## GitHub Repository Secrets (on re-creation only)

GitHub secrets for OIDC (`CNA_AWS_ROLE_ARN`, `CNA_AZURE_CLIENT_ID`, etc.) only
change if the underlying role or app registration is recreated.

```
# GitHub → Settings → Secrets and variables → Actions
# Click pencil icon next to secret → enter new value → Update secret
# No workflow restart needed — next job run picks up new value automatically
```

---

## Teams Webhook URL (on team change)

```bash
# 1. Get new webhook from MS Teams channel connector settings

# 2a. Update Key Vault (Azure platform)
az keyvault secret set \
  --vault-name cna-secrets-prod \
  --name cna-teams-webhook-url \
  --value "<NEW_WEBHOOK_URL>"

# 2b. Update SSM (AWS platform)
aws ssm put-parameter \
  --name "/cna/prod/teams-webhook-url" \
  --value "<NEW_WEBHOOK_URL>" \
  --type SecureString \
  --overwrite

# 2c. Update local .env (dev only)
#    TEAMS_WEBHOOK_URL=<NEW_WEBHOOK_URL>

# 3. Test
cna analyze --engagement-id test-$(date +%Y%m%d)-0000 --azure --test-notifications
# Should send a test alert to the Teams channel
```

---

## If a Secret Is Compromised

```bash
# STEP 1 (immediate): Revoke/rotate the leaked secret in the issuing system
# STEP 2: Determine blast radius — what did the secret have access to?
# STEP 3: Remove from git history if committed
git filter-repo --path <file-with-secret> --invert-paths  # or use BFG
git push origin --force --all
git push origin --force --tags

# STEP 4: Reset detect-secrets baseline
detect-secrets scan > .secrets.baseline
git add .secrets.baseline
git commit -m "fix(security): reset secrets baseline after rotation"

# STEP 5: Document in documentation/policies/incident-log.md
# Include: date, secret type, exposure window, rotated by, blast radius assessment
```
