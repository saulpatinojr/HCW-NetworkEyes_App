# The pin of the self-hosted diagram editor (stage drawio-webapp below, REVIEW.md R-019): a release of jgraph/drawio
# and the sha256 of its draw.war. Declared here, before the first FROM, so that the runner can record the version in
# an image label and the weekly check (.github/workflows/380-drawio-pin-check.yml) reads one line. Change both
# together; tests/security/test_drawio_self_hosted.py checks their shape.
ARG DRAWIO_WEBAPP_VERSION=32.6.1
ARG DRAWIO_WEBAPP_SHA256=44dd56958c8408963457dc98f04d2228408ac145c7aa1d8e6895d9c88d5e42aa

# ── Stage 1: deps ────────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS deps
WORKDIR /app

# Install native build tools (needed by some optional Prisma packages).
RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps

# ── Stage 2: builder ─────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS builder
WORKDIR /app

COPY --from=deps /app/node_modules ./node_modules
COPY . .

# Generate Prisma client before building.
#
# Pin draw.io shape catalog to ALLOWED_LIBS (azure2 + aws4) at build time.
# This is layer #1 of the triple-enforced icon-library pinning; the route
# handler and the Python client re-filter on every call.
#
# One layer for both steps (hadolint DL3059): they read the same COPY . . layer, so splitting them cached nothing.
RUN npx prisma generate \
 && node scripts/filter-shape-index.mjs lib/drawio-mcp/shape-index.json

ENV NEXT_TELEMETRY_DISABLED=1

RUN npm run build

# ── Stage 3: migrator-deps ───────────────────────────────────────────────────
# The migrator's own dependency tree: the Prisma CLI, @prisma/client and what they
# need, and nothing else. The migrator receives the database-owner connection
# string, so it must not carry the web app's build tooling (the TypeScript 7
# compiler, eslint, vitest, vite, tailwind ...) or the Next.js runtime: every
# package in it is attack surface and a scanner finding that `npm audit --omit=dev`
# cannot see (TODO.md T-737).
#
# `prisma` is a production dependency in package.json because it is the CLI that
# prisma/migrate.sh runs. scripts/migrator-lockfile.mjs cuts the closure of prisma
# and @prisma/client out of package-lock.json, entries copied as they are, so
# `npm ci` installs the versions and integrity hashes the web app is audited with
# and fails if the cut-out lockfile does not match its manifest.
#
# Install scripts stay off (`--ignore-scripts`). Prisma needs two things from
# them, done explicitly: @prisma/engines downloads the schema and query engines
# (its own postinstall script, the same download the deps stage makes), and the
# client is generated from the schema. The generated client is what seed-local-admin.js
# loads, so this stage does not depend on the builder (no Next.js build).
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS migrator-deps
WORKDIR /src

# Prisma checkpoint telemetry would try to reach the network and write under $HOME.
ENV CHECKPOINT_DISABLE=1

RUN apk add --no-cache libc6-compat

COPY package.json package-lock.json scripts/migrator-lockfile.mjs ./
RUN node migrator-lockfile.mjs /src /app

WORKDIR /app
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
 && node node_modules/@prisma/engines/scripts/postinstall.js

COPY prisma/schema.prisma ./prisma/schema.prisma
RUN node_modules/.bin/prisma generate

# ── Stage 4: migrator ─────────────────────────────────────────────────────────
# Standalone image used exclusively to run `prisma migrate deploy` once per
# deployment (via workflow 210). Keeping CLI deps out of the runtime image avoids
# chasing Prisma's transitive dep tree (effect, fast-check, etc.) across upgrades.
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS migrator
WORKDIR /app

# No `apk upgrade`: the base is pinned by digest, but libc6-compat is installed unpinned (hadolint DL3018 is
# ignored with a reason in .hadolint.yaml), so a rebuild on another day gets that day's package version on the
# same base. The control that matters is the Docker Scout gate in 200-build-images.yml (fixable critical and high
# findings fail the build). Dependabot's docker ecosystem bumps the digest; a Scout finding on a base apk is
# fixed there (TODO.md T-702).
#
# The bundled npm CLI is unused here (prisma is invoked directly via
# node_modules/.bin) and periodically carries fixable CVEs in its own
# vendored deps (tar, brace-expansion, undici) — strip it.
#
# One layer for both (hadolint DL3059).
RUN apk add --no-cache libc6-compat \
 && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

# Non-root user for the migrator (IMG-002). This container receives the DB-owner
# connection string and the local-admin hash, so it must not run as uid 0.
# Mirror the runner stage's uid/gid 1001.
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs

# `prisma migrate deploy` needs the whole Prisma CLI dependency tree, not just the
# prisma/@prisma/.prisma directories: prisma depends on @prisma/config (c12,
# effect, deepmerge-ts, empathic) and @prisma/engines (fetch-engine,
# get-platform, debug), and npm hoists all of those to the top-level
# node_modules. The migrator-deps stage holds exactly that tree plus the generated
# client seed-local-admin.js loads, so copy it whole. Never copy the builder's
# node_modules here: it carries every devDependency (tests/unit/test_ci_hygiene.py
# fails if this stage does, and 300-test-codebase.yml scans the built image).
COPY --chown=nextjs:nodejs prisma ./prisma
COPY --from=migrator-deps --chown=nextjs:nodejs /app/node_modules ./node_modules

# Small, reviewable entrypoint copied executable, replacing the inline sh -c.
COPY --chmod=755 prisma/migrate.sh ./prisma/migrate.sh

# Prisma CLI checkpoint telemetry would try to write under $HOME, which the
# migrator user does not have; disable it explicitly.
ENV CHECKPOINT_DISABLE=1
# Numeric uid (hadolint DL3066): 1001 is the `nextjs` user created above. With a uid alone Docker still takes the
# group from /etc/passwd, so the process runs with the same gid as before.
USER 1001

CMD ["./prisma/migrate.sh"]

# ── Stage 4b: drawio-webapp ──────────────────────────────────────────────────
# The diagram editor, served by this image under /drawio/ so that no network topology leaves the deployment for
# the public draw.io embed service (REVIEW.md R-019). This is the draw.io web app, released by jgraph/drawio under
# Apache-2.0 as `draw.war` (a zip of static files; no Java is run). It is pinned by version AND sha256: to move to a
# newer release, change both ARGs together (the checksum is on the release page,
# https://github.com/jgraph/drawio/releases) and run the web tests; tests/security/test_drawio_self_hosted.py fails
# if either is missing or malformed. Dependabot cannot track a release asset, so a bump is a deliberate change.
#
# Local development (`next dev`) has no /drawio/ unless you put the files there (the folder is git-ignored). From the
# repository root, in bash or PowerShell:
#   docker build -f apps/network-assessment-web/Dockerfile --target drawio-webapp -t network-assessment-drawio-webapp apps/network-assessment-web
#   docker create --name network-assessment-drawio-webapp network-assessment-drawio-webapp
#   docker cp network-assessment-drawio-webapp:/out/. apps/network-assessment-web/public/drawio
#   docker rm network-assessment-drawio-webapp
#
# The build fails if the checksum differs. Everything the embedded editor does not use is deleted before the files
# can reach the runner: the Java and OAuth server side (WEB-INF), the viewer and integration bundles, the template
# gallery, the math renderer, source maps and every language file but English. What remains is about 65 MB.
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS drawio-webapp

# ash with pipefail: the checksum step is a pipe (`echo | sha256sum -c -`) and a failure on its left must fail the
# build (hadolint DL4006).
SHELL ["/bin/ash", "-o", "pipefail", "-c"]

# The values are declared at the top of this file; redeclaring the names brings them into this stage.
ARG DRAWIO_WEBAPP_VERSION
ARG DRAWIO_WEBAPP_SHA256

RUN wget -q -O /tmp/draw.war "https://github.com/jgraph/drawio/releases/download/v${DRAWIO_WEBAPP_VERSION}/draw.war" \
 && echo "${DRAWIO_WEBAPP_SHA256}  /tmp/draw.war" | sha256sum -c - \
 && mkdir /out \
 && unzip -q /tmp/draw.war -d /out \
 && rm -f /tmp/draw.war

WORKDIR /out

# service-worker.js and workbox-*.js go too: at the top level of /drawio/ they would register a service worker if
# the page were ever opened outside the sandbox. The trailing checks make the trim fail closed: the files the editor
# needs must exist, and the server side and the service worker must not.
RUN rm -rf WEB-INF META-INF templates connect math4 \
 && rm -f js/viewer.min.js js/viewer-static.min.js js/integrate.min.js js/export.js js/embed.dev.js js/open.js js/clear.js \
          export3.html onedrive3.html open.html clear.html teams.html vsdxImporter.html monday-app-association.json \
          service-worker.js workbox-*.js \
 && find . -name '*.map' -delete \
 && find resources -name 'dia_*.txt' ! -name 'dia_en.txt' -delete \
 && test -f index.html && test -f js/app.min.js && test -f resources/dia.txt && test -f mxgraph/css/common.css \
 && test ! -e WEB-INF && test ! -e META-INF && test ! -e service-worker.js && test -z "$(find . -name 'workbox-*' | head -n 1)"

# Apache-2.0 asks that the licence travels with the files (the war carries none of its own at the top level).
COPY third-party/drawio/LICENSE /out/LICENSE

# Read-only for everyone: the runner's user (uid 1001) owns the files after the COPY below but cannot change them.
RUN find /out -type d -exec chmod 555 {} + \
 && find /out -type f -exec chmod 444 {} +

# ── Stage 5: runner ──────────────────────────────────────────────────────────
FROM node:24-alpine@sha256:06d7adf3e0ef61a13f1d28682726366f97a15aa1888c934d3ecec86c33918b53 AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Add a non-root user for Container Apps security best practices.
#
# The bundled npm CLI is unused here (CMD invokes node directly) and
# periodically carries fixable CVEs in its own vendored deps (tar,
# brace-expansion, undici) — strip it.
#
# One layer for the user, the group and the strip (hadolint DL3059).
RUN addgroup --system --gid 1001 nodejs \
 && adduser --system --uid 1001 nextjs \
 && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

# Because outputFileTracingRoot is set to the repo root (two levels above the
# app dir), Next.js mirrors the /app path inside .next/standalone — so the
# server entry point lands at .next/standalone/app/server.js, not
# .next/standalone/server.js.  All assets must be placed relative to server.js.
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/public          ./app/public
COPY --from=builder --chown=nextjs:nodejs /app/.next/static    ./app/.next/static

# The self-hosted diagram editor (stage drawio-webapp). Served by Next.js as static files under /drawio/; its
# Content-Security-Policy and framing headers come from next.config.ts.
COPY --from=drawio-webapp --chown=nextjs:nodejs /out ./app/public/drawio

# The version of the editor in this image, readable with `docker inspect` (the pin is declared at the top of this file).
ARG DRAWIO_WEBAPP_VERSION
LABEL io.github.saulpatinojr.drawio-webapp.version="${DRAWIO_WEBAPP_VERSION}" \
      io.github.saulpatinojr.drawio-webapp.source="https://github.com/jgraph/drawio/releases/tag/v${DRAWIO_WEBAPP_VERSION}"

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

# Numeric uid, see the migrator stage (hadolint DL3066).
USER 1001

EXPOSE 3000

# Liveness for orchestrators (Container Apps/ECS/AKS): probe the purpose-built
# /api/health endpoint rather than "/", which triggers a full auth() DB session
# lookup and RSC render on every check (IMG-009). Pass on status < 500 so a 503
# (DB down) still counts as "process alive" for liveness. Uses node (no curl in
# the runtime image).
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["node", "-e", "fetch('http://127.0.0.1:'+(process.env.PORT||3000)+'/api/health').then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))"]

# server.js lives at /app/app/server.js due to outputFileTracingRoot path mirroring.
CMD ["node", "app/server.js"]
