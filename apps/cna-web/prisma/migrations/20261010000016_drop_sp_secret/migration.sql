-- REFACTOR_APP.md change set G: Azure discovery runs as the appliance's user-assigned
-- managed identity. The service-principal client id and the AES-256-GCM encrypted client
-- secret are no longer entered, stored, decrypted or transmitted, so the columns go.
-- Rollback: down.sql in this directory re-adds both as nullable TEXT (the values are gone
-- by design; customers who need a non-identity path have none, by owner decision).

-- AlterTable
ALTER TABLE "CloudCredential" DROP COLUMN "spSecretEnc";
ALTER TABLE "CloudCredential" DROP COLUMN "spClientId";
