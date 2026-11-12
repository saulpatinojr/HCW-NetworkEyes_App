# The pin of the self-hosted diagram editor (stage drawio-webapp below, REVIEW.md R-019): a release of jgraph/drawio
# and the sha256 of its draw.war. Declared here, before the first FROM, so that the runner can record the version in
# an image label and the weekly check (.github/workflows/380-drawio-pin-check.yml) reads one line. Change both
# together; tests/security/test_drawio_self_hosted.py checks their shape.
ARG DRAWIO_WEBAPP_VERSION=32.6.9
ARG DRAWIO_WEBAPP_SHA256=31afc82b7920c409d0591f6126ccb6c377d7800e7f11ab324f88bdf1e4249ce7

# Every stage is node:26-trixie-slim (Debian 13, glibc), the same Debian release as the Python images, digest pinned
# 2026-11-12 (Node 26.13.0, built 2026-11-05: the digest the HCW MigrateOrchestrator images pin). Moved from Node 24
# (node:24-trixie-slim, Node 24.22.2) to reach the HCW runtime floor, the newest Node.js LTS line
# (saulpatinojr/HCW-HybridCloudWorks#1707). Dependabot's docker ecosystem bumps all six FROM lines together; it does
# not offer the next major, which is moved by hand (see .github/dependabot.yml).
# Until 2026-11-07 the stages were node:24-alpine: the Scout gate in 200-build-images.yml refused every web build
# on main from 2026-11-06 on a HIGH finding in Alpine's musl (CVE-2026-107891) whose fix was only in Alpine edge,
# and the owner chose one distribution for every image instead of a second one to track (TODO.md T-741).
# The base already carries libssl3t64 (libssl.so.3), which Prisma's engines load; the deps, builder and
# migrator-deps stages check that the engines Prisma fetched are the debian-openssl-3.0.x builds this runs. Those are
# the amd64 names, the only platform 200-build-images.yml builds; an arm64 build would fetch linux-arm64-openssl-3.0.x
# and the checks would need that name.

# ── Stage 1: deps ────────────────────────────────────────────────────────────
FROM node:26-trixie-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS deps
WORKDIR /app

# No extra packages: Alpine needed libc6-compat for glibc-built binaries, and Debian is glibc already. npm picks
# the *-linux-x64-gnu builds of the native packages (Next.js SWC, sharp, lightningcss, tailwind oxide) from the
# lockfile. The trailing test fails the build if Prisma fetched an engine for another platform.
COPY package.json package-lock.json* ./
RUN npm ci --legacy-peer-deps \
 && test -f node_modules/@prisma/engines/libquery_engine-debian-openssl-3.0.x.so.node

# ── Stage 2: builder ─────────────────────────────────────────────────────────
FROM node:26-trixie-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS builder
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
# The generated client must hold the debian-openssl-3.0.x query engine, the one the runner (same base) loads; the
# test fails the build if Prisma detected another platform.
RUN npx prisma generate \
 && test -f node_modules/.prisma/client/libquery_engine-debian-openssl-3.0.x.so.node \
 && node scripts/filter-shape-index.mjs lib/drawio-mcp/shape-index.json

ENV NEXT_TELEMETRY_DISABLED=1

# The build writes some of its output group- and world-writable (seen in .next/server). The runner copies these
# files owned by root, and the Image Scan check in 300-test-codebase.yml refuses any file under /app that a user
# other than root can write, so the write bits come off here, in the same layer, for everything the runner copies.
RUN npm run build \
 && chmod -R go-w .next/standalone .next/static public node_modules/.prisma node_modules/@prisma

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
FROM node:26-trixie-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS migrator-deps
WORKDIR /src

# Prisma checkpoint telemetry would try to reach the network and write under $HOME.
ENV CHECKPOINT_DISABLE=1

COPY package.json package-lock.json scripts/migrator-lockfile.mjs ./
RUN node migrator-lockfile.mjs /src /app

WORKDIR /app
RUN npm ci --omit=dev --ignore-scripts --no-audit --no-fund \
 && node node_modules/@prisma/engines/scripts/postinstall.js

COPY prisma/schema.prisma ./prisma/schema.prisma
# The schema engine (`prisma migrate deploy`) and the query engine (seed-local-admin.js) must be the
# debian-openssl-3.0.x builds the migrator (same base) runs; the tests fail the build otherwise.
RUN node_modules/.bin/prisma generate \
 && test -f node_modules/@prisma/engines/schema-engine-debian-openssl-3.0.x \
 && test -f node_modules/.prisma/client/libquery_engine-debian-openssl-3.0.x.so.node

# ── Stage 4: migrator ─────────────────────────────────────────────────────────
# Standalone image used exclusively to run `prisma migrate deploy` once per
# deployment (via workflow 210). Keeping CLI deps out of the runtime image avoids
# chasing Prisma's transitive dep tree (effect, fast-check, etc.) across upgrades.
FROM node:26-trixie-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS migrator
WORKDIR /app

# Debian's security updates first (`apt-get upgrade`, deliberate, TODO.md T-741): the base is pinned by digest, but
# a security upload reaches the mirrors before the official image is rebuilt with it, and on 2026-11-05 the Scout
# gate in 200-build-images.yml (fixable critical and high findings fail the build) refused the Python images on
# exactly that gap (CVE-2026-109518; see the root Dockerfile, whose final stage this RUN mirrors: retries off while
# the base's apt does the upgrade, `--error-on=any` so a missing trixie-security index fails the build).
# Dependabot's docker ecosystem still bumps the digest. Nothing is installed on top: libssl3t64, which Prisma's
# engines load, is part of the base.
#
# The bundled npm CLI is unused here (prisma is invoked directly via
# node_modules/.bin) and periodically carries fixable CVEs in its own
# vendored deps (tar, brace-expansion, undici) — strip it.
#
# Non-root user for the migrator (IMG-002). This container receives the DB-owner connection string and the
# local-admin hash, so it must not run as uid 0. Mirror the runner stage's uid/gid 1001.
#
# One layer for all of it (hadolint DL3059). PUBLISH_CACHE_BUST, named in the command, keeps the publish workflow
# from reusing a cached upgrade layer on a later run of the same commit (see the root Dockerfile).
ARG PUBLISH_CACHE_BUST=
RUN printf 'upgrade run: %s\n' "${PUBLISH_CACHE_BUST}" \
 && apt-get -o Acquire::Retries=0 update --error-on=any \
 && apt-get -o Acquire::Retries=0 upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack \
 && groupadd --gid 1001 nodejs \
 && useradd --uid 1001 --gid nodejs --no-create-home --shell /usr/sbin/nologin nextjs

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
FROM node:26-trixie-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS drawio-webapp

# bash with pipefail: the checksum step is a pipe (`echo | sha256sum -c -`) and a failure on its left must fail the
# build (hadolint DL4006). Debian's default /bin/sh (dash) has no pipefail.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

# The values are declared at the top of this file; redeclaring the names brings them into this stage.
ARG DRAWIO_WEBAPP_VERSION
ARG DRAWIO_WEBAPP_SHA256

# The slim base has neither a downloader nor unzip (Alpine's busybox had both): curl, its CA bundle and unzip are
# installed here, in a stage that never ships (the runner copies only /out), and then used once.
RUN apt-get -o Acquire::Retries=0 update --error-on=any \
 && apt-get -o Acquire::Retries=0 install -y --no-install-recommends ca-certificates curl unzip \
 && rm -rf /var/lib/apt/lists/* \
 && curl -fsSL -o /tmp/draw.war "https://github.com/jgraph/drawio/releases/download/v${DRAWIO_WEBAPP_VERSION}/draw.war" \
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

# Read-only for everyone. The runner copies these files without --chown, so they stay owned by root: the app's user
# (uid 1001) can read them but cannot change them, rename them or chmod them back (an owner could always chmod).
RUN find /out -type d -exec chmod 555 {} + \
 && find /out -type f -exec chmod 444 {} +

# ── Stage 5: runner ──────────────────────────────────────────────────────────
FROM node:26-trixie-slim@sha256:5adad64f9a1fca2d51972caa65983634c8a774eb300d72b20f7f2a0f60368072 AS runner
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
# Debian's security updates first (`apt-get upgrade`, deliberate: see the migrator stage above and TODO.md T-741).
# Nothing is installed on top: libssl3t64, which the Prisma query engine loads, is part of the base, and the
# HEALTHCHECK below uses node, so the runner needs no curl or wget.
#
# One layer for the upgrade, the user, the group and the strip (hadolint DL3059). PUBLISH_CACHE_BUST as in the
# migrator stage.
ARG PUBLISH_CACHE_BUST=
RUN printf 'upgrade run: %s\n' "${PUBLISH_CACHE_BUST}" \
 && apt-get -o Acquire::Retries=0 update --error-on=any \
 && apt-get -o Acquire::Retries=0 upgrade -y --no-install-recommends \
 && rm -rf /var/lib/apt/lists/* \
 && groupadd --gid 1001 nodejs \
 && useradd --uid 1001 --gid nodejs --no-create-home --shell /usr/sbin/nologin nextjs \
 && rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx /usr/local/bin/corepack

# Because outputFileTracingRoot is set to the repo root (two levels above the
# app dir), Next.js mirrors the /app path inside .next/standalone — so the
# server entry point lands at .next/standalone/app/server.js, not
# .next/standalone/server.js.  All assets must be placed relative to server.js.
#
# None of the app's files is copied with --chown: they stay owned by root and readable by everyone, so the app's
# user (uid 1001) can run them but cannot change, rename, replace or chmod them (an owner always can chmod its own
# files, so owning them read-only would not be enough). The one place the server writes at run time is
# app/.next/cache (the image optimizer and the fetch cache); it is created below, empty and owned by uid 1001.
# There are no ISR pages, so nothing is regenerated into app/.next/server; if one is ever added, Next.js only logs
# a warning when it cannot write the refreshed page there.
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/public          ./app/public
COPY --from=builder /app/.next/static    ./app/.next/static

# The self-hosted diagram editor (stage drawio-webapp). Served by Next.js as static files under /drawio/; its
# Content-Security-Policy and framing headers come from next.config.ts. No --chown, as above: the files stay owned
# by root and read-only (chmod 444/555 in that stage), so the app's user cannot alter the editor it serves.
COPY --from=drawio-webapp /out ./app/public/drawio

# The version of the editor in this image, readable with `docker inspect` (the pin is declared at the top of this file).
ARG DRAWIO_WEBAPP_VERSION
LABEL io.github.saulpatinojr.drawio-webapp.version="${DRAWIO_WEBAPP_VERSION}" \
      io.github.saulpatinojr.drawio-webapp.source="https://github.com/jgraph/drawio/releases/tag/v${DRAWIO_WEBAPP_VERSION}"

# Prisma runtime only — @prisma/client + generated query engine.
# The Prisma CLI is intentionally excluded; migrations run from the
# migrator stage in workflow 210 before this container is deployed.
# Node.js walks the directory tree, so modules at /app/node_modules are
# found by the server running from /app/app/server.js.
# No --chown and no chown -R: the client and its query engine stay owned by root, so the app's user can load them
# but cannot rewrite them. Nothing writes here at run time (the client is generated in the builder).
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma

# The one writable directory (see above). 300-test-codebase.yml (Image Scan) checks the built runner: uid 1001 owns
# nothing under /app but this directory, and can write nowhere else under /app.
RUN mkdir -p app/.next/cache \
 && chown -R nextjs:nodejs app/.next/cache \
 && chmod 700 app/.next/cache

# Commit the image was built from (200-build-images passes github.sha). The web
# tier compares it with the newest published build (Admin → Updates); empty
# for local builds, which report the running build as unknown.
ARG NETWORK_ASSESSMENT_BUILD_SHA=
ENV NETWORK_ASSESSMENT_BUILD_SHA=${NETWORK_ASSESSMENT_BUILD_SHA}

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
