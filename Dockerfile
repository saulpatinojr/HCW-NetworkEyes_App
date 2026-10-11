# Multi-stage Dockerfile — hardened
#
# Two editions from one file (REFACTOR_APP.md change set I):
#   EDITION=appliance (default)  the CLI image as before: the full cna package, the engine
#                                with its [azure] extra, graphviz and draw.io.
#   EDITION=lab                  build-only: the engine package without [azure], no apps/,
#                                no server; its CMD is the boundary proof (exit 0 only when
#                                azure is not importable). CI builds it with `--build-arg
#                                EDITION=lab` and never pushes it. The deployable lab
#                                edition is HCW-NetworkEyes_AddOn, built on the published
#                                engine with this same pattern.
# Changes from original single-stage:
#   1. Pinned digest on base image (supply chain)
#   2. Builder stage: installs deps only, not full source (smaller final layer)
#   3. Non-root user (cna:cna uid/gid 1001) — CI smoke test verifies this
#   4. COPY --chown so files are owned by non-root user
#   5. Build arg CNA_VERSION injected at release time
#   6. HEALTHCHECK added (required for ECS/AKS task definitions)
#   7. .dockerignore referenced — see .dockerignore in repo root

# python:3.14-slim digest pinned 2026-09-30. Dependabot's docker ecosystem watches
# every Dockerfile and bumps this line; nothing else keeps base-image debs current.
# uv, as a stage rather than an inline `COPY --from=<image>`: Dependabot's docker
# updater only reads `FROM` lines, so this is the line its weekly bump moves.
# Keep the version in step with the `uv==` pins in 300-test-codebase.yml.
ARG EDITION=appliance

FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv

FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS builder

ARG CNA_VERSION=dev
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz libcairo2 libpango-1.0-0 \
    libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Every Python image installs from uv.lock (TODO.md T-702): `uv export --locked`
# fails the build if the lock has drifted from pyproject.toml, and
# `--require-hashes` makes the install byte-for-byte the resolution that was
# reviewed. uv is copied in as a pinned, digest-verified binary and stays in
# the builder stage only. Dependencies first (cacheable layer), then the
# package itself with `--no-build-isolation` so the build backend is the
# hash-checked `build` group rather than whatever pip would fetch unpinned.
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
# The engine package is a uv workspace member: its pyproject.toml must be present for
# `uv export --locked` to resolve the workspace, before the source tree is copied.
COPY packages/cna-azure-network-engine/pyproject.toml packages/cna-azure-network-engine/
# The appliance edition serves both clouds, so the [aws] extra rides along here; the
# package itself declares boto3 only under that extra (change set K).
RUN uv export --locked --no-default-groups --no-emit-project --no-emit-workspace --extra aws -o /tmp/requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install -r /tmp/requirements.txt \
 && uv export --locked --only-group build -o /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps -r /tmp/build-requirements.txt
COPY packages/cna-azure-network-engine/ packages/cna-azure-network-engine/
COPY cna/ cna/
# The engine package first (a workspace member, excluded from the hash-checked export
# above), then the cna package itself; both from the tree, both without build isolation.
RUN uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install ./packages/cna-azure-network-engine \
 && uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install . \
 && rm -f /tmp/requirements.txt /tmp/build-requirements.txt

# ---- lab builder stage (build-only; change set I) ----
# The engine package alone, without the [azure] extra, into its own prefix. The
# boundary is proved before the final stage exists: a resolvable azure, msal or
# boto3 fails the build here, the same check the AddOn's image runs.
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS builder-lab

ARG EDITION
RUN test "$EDITION" = "lab" || { echo "builder-lab is only built for EDITION=lab (got '$EDITION')" >&2; exit 1; }
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY packages/cna-azure-network-engine/ packages/cna-azure-network-engine/
# The engine's base dependencies from the lock (hash-checked), then the engine itself
# from the tree with no extras: no cloud SDK is named anywhere in this stage.
RUN uv export --locked --no-default-groups --no-emit-project --no-emit-workspace --package cna-azure-network-engine -o /tmp/lab-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install-lab -r /tmp/lab-requirements.txt \
 && uv export --locked --only-group build -o /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps -r /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install-lab ./packages/cna-azure-network-engine \
 && rm -f /tmp/lab-requirements.txt /tmp/build-requirements.txt \
 && PYTHONPATH=/install-lab/lib/python3.14/site-packages python -m cna_azure_network_engine.edition

# ---- drawio fetch stage ----
# Pinned draw.io desktop release, verified by checksum before it can reach
# the final image. The export pipeline (cna/diagram_engine/export_pipeline.py)
# degrades to XML-only output without it — its own warning promises the CLI
# is available "inside the Docker container", which is made true here.
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS drawio-fetch

ARG DRAWIO_VERSION=31.3.2
ARG DRAWIO_SHA256=725453f32ef7f2f63f8b50b374857a5c312e2aaabcf221cb0600332741ae1094

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL -o /tmp/drawio.deb \
     "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-amd64-${DRAWIO_VERSION}.deb" \
  && echo "${DRAWIO_SHA256}  /tmp/drawio.deb" | sha256sum -c -

# ---- final stage: lab (build-only) ----
# No apps/, no server, no EXPOSE, no HEALTHCHECK: the image's only job is the proof.
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS final-lab

COPY --from=builder-lab /install-lab /usr/local
RUN python -m pip uninstall -y pip \
 && groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --no-create-home --shell /usr/sbin/nologin cna
USER cna
ENV CNA_EDITION=lab
# Exit 0 when azure is NOT importable and no identity variable is set; exit 1 otherwise.
CMD ["python", "-m", "cna_azure_network_engine.edition"]

# ---- final stage: appliance ----
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS final-appliance

ARG CNA_VERSION=dev
LABEL org.opencontainers.image.title="CNA Platform" \
      org.opencontainers.image.description="Cloud Network Assessment CLI" \
      org.opencontainers.image.version="${CNA_VERSION}" \
      org.opencontainers.image.source="https://github.com/saulpatinojr/HCW-NetworkEyes_App" \
      org.opencontainers.image.licenses="Proprietary"

# System deps for diagram generation (runtime only). No `apt-get upgrade`:
# the image must be the pinned base digest plus these packages, nothing that
# depends on the day it was built. When Docker Scout fails on a base-image
# deb, the fix is the Dependabot digest bump, not a rebuild (TODO.md T-702).
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz libcairo2 libpango-1.0-0 \
    libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# draw.io desktop CLI + xvfb for headless diagram export (.drawio -> .svg).
# The wrapper shadows /usr/bin/drawio on PATH and supplies xvfb-run,
# --no-sandbox, and a writable HOME — see the script for why each is
# required. `drawio --version` proves the whole chain at build time.
COPY --from=drawio-fetch /tmp/drawio.deb /tmp/drawio.deb
COPY --chmod=755 scripts/drawio-headless.sh /usr/local/bin/drawio
RUN apt-get update \
 && apt-get install -y --no-install-recommends /tmp/drawio.deb xvfb xauth libasound2t64 \
 && rm -rf /var/lib/apt/lists/* /tmp/drawio.deb \
 && drawio --version

# Non-root user — uid/gid 1001
RUN groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --shell /bin/bash --create-home cna

WORKDIR /app
COPY --from=builder --chown=cna:cna /install /usr/local
COPY --chown=cna:cna . .

# Engagement data written here — must be writable by non-root user
RUN mkdir -p /app/engagements /app/output && chown -R cna:cna /app/engagements /app/output

# pip is unused at runtime and vendors CVE-carrying copies of msgpack and
# setuptools (declared in its own pip/_vendor/bom.cdx.json) that no
# `pip install` can replace — strip it from the shipped image, the same
# reasoning the web image uses to strip npm.
RUN python -m pip uninstall -y pip

# Commit the image was built from (200-build-images passes github.sha). The web
# tier compares it with the newest published build (Admin → Updates); empty
# for local builds, which report the running build as unknown.
ARG CNA_BUILD_SHA=
ENV CNA_BUILD_SHA=${CNA_BUILD_SHA}

USER cna
ENV CNA_EDITION=appliance

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD cna --help > /dev/null 2>&1 || exit 1

ENTRYPOINT ["cna"]
CMD ["--help"]

# ---- the edition that was asked for ----
# `docker build .` is the appliance image exactly as before; `--build-arg EDITION=lab`
# selects the build-only lab target. Any other value fails at builder-lab.
FROM final-${EDITION}
