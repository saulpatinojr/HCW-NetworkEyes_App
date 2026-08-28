-- AWS end-to-end (CNA-0.90 §3): management-account access key on CloudCredential.
-- The secret is AES-256-GCM encrypted by the web layer, same scheme as spSecretEnc.
ALTER TABLE "CloudCredential" ADD COLUMN "awsAccessKeyId" TEXT;
ALTER TABLE "CloudCredential" ADD COLUMN "awsSecretEnc" TEXT;
