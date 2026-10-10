-- Break-glass local admin account: a single non-Entra identity, seeded by
-- prisma/seed-local-admin.ts, that can sign in with a password if Entra ID
-- SSO is ever unavailable. passwordHash stays null for every Entra-provisioned
-- user; only the seeded local-admin row gets one.
ALTER TABLE "User" ADD COLUMN "passwordHash" TEXT;
ALTER TABLE "User" ADD COLUMN "isLocalAdmin" BOOLEAN NOT NULL DEFAULT false;
