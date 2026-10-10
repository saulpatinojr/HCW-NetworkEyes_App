# ── Stage 1: deps ────────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS deps
WORKDIR /app

# Install native build tools (needed by some optional Prisma packages).
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

# ── Stage 2: builder ─────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS builder
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
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS migrator
WORKDIR /app

# No `apk upgrade`: the image is the pinned base digest plus libc6-compat,
# nothing that depends on the day it was built. Dependabot's docker ecosystem
# bumps the digest; a Scout finding on a base apk is fixed there (TODO.md T-702).
RUN apk add --no-cache libc6-compat

# The bundled npm CLI is unused here (prisma is invoked directly via
# node_modules/.bin) and periodically carries fixable CVEs in its own
# vendored deps (tar, brace-expansion, undici) — strip it.
RUN rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

# Non-root user for the migrator (IMG-002). This container receives the DB-owner
# connection string and the local-admin hash, so it must not run as uid 0.
# Mirror the runner stage's uid/gid 1001.
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# `prisma migrate deploy` needs the full Prisma CLI dependency tree, not just the
# prisma/@prisma/.prisma directories: prisma@6.19.3 depends on @prisma/config
# (c12, effect, deepmerge-ts, empathic) and @prisma/engines (fetch-engine,
# get-platform, debug), and npm hoists all of those to the top-level
# node_modules rather than nesting them under prisma/ or @prisma/. Copying only a
# subset breaks the CLI at runtime, so copy the whole tree — the security win of
# IMG-002 is the non-root USER below, which we keep. seed-local-admin.js also
# needs @prisma/client from this tree.
COPY --from=builder --chown=nextjs:nodejs /app/prisma ./prisma
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules

# Small, reviewable entrypoint copied executable, replacing the inline sh -c.
COPY --chmod=755 prisma/migrate.sh ./prisma/migrate.sh

# Prisma CLI checkpoint telemetry would try to write under $HOME, which the
# migrator user does not have; disable it explicitly.
ENV CHECKPOINT_DISABLE=1
USER nextjs

CMD ["./prisma/migrate.sh"]

# ── Stage 4: runner ──────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS runner
WORKDIR /app

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

# Commit the image was built from (200-build-images passes github.sha). The web
# tier compares it with the newest published build (Admin → Updates); empty
# for local builds, which report the running build as unknown.
ARG CNA_BUILD_SHA=
ENV CNA_BUILD_SHA=${CNA_BUILD_SHA}

USER nextjs

EXPOSE 3000

# Liveness for orchestrators (Container Apps/ECS/AKS): probe the purpose-built
# /api/health endpoint rather than "/", which triggers a full auth() DB session
# lookup and RSC render on every check (IMG-009). Pass on status < 500 so a 503
# (DB down) still counts as "process alive" for liveness. Uses node (no curl in
# the runtime image).
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD node -e "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"

# server.js lives at /app/app/server.js due to outputFileTracingRoot path mirroring.
CMD ["node", "app/server.js"]
