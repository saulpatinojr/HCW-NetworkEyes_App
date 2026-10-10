// Break-glass local admin seed step, run once per deploy from the migrator
// image (see Dockerfile "migrator" stage) right after `prisma migrate deploy`.
//
// Reads LOCAL_ADMIN_PASSWORD (a PBKDF2 hash string, never the plaintext —
// see lib/local-admin.ts and the appliance repositories'
// scripts/Initialize-CnaGitHubSecrets.ps1) and
// upserts the single local admin User row. No-ops if the env var isn't set,
// so environments that haven't bootstrapped this secret yet deploy unchanged.
//
// Plain CommonJS (not TypeScript): the migrator image only carries
// prisma/ + node_modules/, not a compiled lib/ tree, so this script must be
// self-contained and runnable directly with `node`.
const { PrismaClient } = require("@prisma/client");

const LOCAL_ADMIN_EMAIL = "local-admin@cna.local";

async function main() {
  const passwordHash = process.env.LOCAL_ADMIN_PASSWORD;
  if (!passwordHash) {
    console.log("[seed-local-admin] LOCAL_ADMIN_PASSWORD not set — skipping (feature not configured for this environment).");
    return;
  }

  const prisma = new PrismaClient();
  try {
    await prisma.user.upsert({
      where: { email: LOCAL_ADMIN_EMAIL },
      create: {
        email: LOCAL_ADMIN_EMAIL,
        name: "Local Admin",
        role: "ADMIN",
        isLocalAdmin: true,
        passwordHash,
      },
      update: {
        passwordHash,
        isLocalAdmin: true,
        role: "ADMIN",
      },
    });
    console.log("[seed-local-admin] Local admin account is up to date.");
  } finally {
    await prisma.$disconnect();
  }
}

main().catch((err) => {
  console.error("[seed-local-admin] Failed:", err);
  process.exit(1);
});
