#!/bin/sh
# Migrator entrypoint — see the Dockerfile "migrator" stage. Applies pending
# Prisma migrations, then upserts the break-glass local admin account (a no-op
# when LOCAL_ADMIN_PASSWORD is unset). Run once per deployment from workflow 210.
# Replaces the previous inline `sh -c` CMD so the container has a single,
# reviewable entrypoint (IMG-002).
set -eu

node_modules/.bin/prisma migrate deploy
node prisma/seed-local-admin.js
