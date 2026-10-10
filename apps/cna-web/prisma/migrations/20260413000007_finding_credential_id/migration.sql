-- Add credentialId to Finding for subscription-scoped sync groups
ALTER TABLE "Finding" ADD COLUMN "credentialId" TEXT;

ALTER TABLE "Finding"
  ADD CONSTRAINT "Finding_credentialId_fkey"
  FOREIGN KEY ("credentialId") REFERENCES "CloudCredential"(id)
  ON DELETE SET NULL ON UPDATE CASCADE;

CREATE INDEX "Finding_credentialId_idx" ON "Finding"("credentialId");
