-- Make credentialId nullable on DiscoveryJob so that deleting a
-- CloudCredential does not violate the foreign key constraint. Existing
-- discovery jobs retain their topology/findings data; the credential
-- reference is simply set to NULL when the credential is removed.

-- Step 1: Drop the existing NOT NULL + FK constraint
ALTER TABLE "DiscoveryJob" ALTER COLUMN "credentialId" DROP NOT NULL;

-- Step 2: Drop the old FK (Restrict / no onDelete action)
ALTER TABLE "DiscoveryJob" DROP CONSTRAINT IF EXISTS "DiscoveryJob_credentialId_fkey";

-- Step 3: Re-add FK with ON DELETE SET NULL
ALTER TABLE "DiscoveryJob"
  ADD CONSTRAINT "DiscoveryJob_credentialId_fkey"
  FOREIGN KEY ("credentialId")
  REFERENCES "CloudCredential"("id")
  ON DELETE SET NULL
  ON UPDATE CASCADE;
