# ── Stage 1: deps ────────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS deps
WORKDIR /app

# Install native build tools (needed by some optional Prisma packages).
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

# ── Stage 2: builder ─────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Generate Prisma client before building.
RUN npx prisma generate

# Pin draw.io shape catalog to ALLOWED_LIBS (azure2 + aws4) at build time.
# This is layer #1 of the triple-enforced icon-library pinning; the route
# handler and the Python client re-filter on every call.
RUN node scripts/filter-shape-index.mjs lib/drawio-mcp/shape-index.json

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 3: migrator ─────────────────────────────────────────────────────────
# Standalone image used exclusively to run `prisma migrate deploy` once per
# deployment (via workflow 210). Keeping CLI deps out of the runtime image avoids
# chasing Prisma's transitive dep tree (effect, fast-check, etc.) across upgrades.
FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS migrator
WORKDIR /app

# apk upgrade pulls pending Alpine security fixes (e.g. the 2026-08 OpenSSL
# release) so the gating Docker Scout check doesn't fail on base-image apks
# between digest bumps.
RUN apk upgrade --no-cache && apk add --no-cache libc6-compat

# The bundled npm CLI is unused here (prisma is invoked directly via
# node_modules/.bin) and periodically carries fixable CVEs in its own
# vendored deps (tar, brace-expansion, undici) — strip it.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/node_modules ./node_modules

CMD ["sh", "-c", "node_modules/.bin/prisma migrate deploy && node prisma/seed-local-admin.js"]

# ── Stage 4: runner ──────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:e67514e5d0f6c46656005e1b693b2ec9d52e80b641307de684d4a015ba7a4eaf AS runner
WORKDIR /app

# See the migrator stage: pending Alpine security fixes for base-image apks.
RUN apk upgrade --no-cache

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Add a non-root user for Container Apps security best practices.
RUN addgroup --system --gid 1001 nodejs
RUN adduser --system --uid 1001 nextjs

# The bundled npm CLI is unused here (CMD invokes node directly) and
# periodically carries fixable CVEs in its own vendored deps (tar,
# brace-expansion, undici) — strip it.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

# Because outputFileTracingRoot is set to the repo root (two levels above the
# app dir), Next.js mirrors the /app path inside .next/standalone — so the
# server entry point lands at .next/standalone/app/server.js, not
# .next/standalone/server.js.  All assets must be placed relative to server.js.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/public          ./app/public
COPY --from=builder --chown=nextjs:nodejs /app/.next/static    ./app/.next/static

# Prisma runtime only — @prisma/client + generated query engine.
# The Prisma CLI is intentionally excluded; migrations run from the
# migrator stage in workflow 210 before this container is deployed.
# Node.js walks the directory tree, so modules at /app/node_modules are
# found by the server running from /app/app/server.js.
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma

RUN chown -R nextjs:nodejs ./node_modules/.prisma ./node_modules/@prisma

USER nextjs

EXPOSE 3000

# server.js lives at /app/app/server.js due to outputFileTracingRoot path mirroring.
CMD ["node", "app/server.js"]
