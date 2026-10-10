-- Rollback of 20261010000016_drop_sp_secret: re-add the columns as nullable TEXT.
-- Prisma does not run this file; apply it by hand only when rolling the api and web
-- images back to a digest that still reads these columns.
ALTER TABLE "CloudCredential" ADD COLUMN "spClientId" TEXT;
ALTER TABLE "CloudCredential" ADD COLUMN "spSecretEnc" TEXT;
