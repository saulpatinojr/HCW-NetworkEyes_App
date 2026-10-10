# Multi-stage Dockerfile — hardened
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
FROM ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 AS uv

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
RUN uv export --locked --no-default-groups --no-emit-project -o /tmp/requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install -r /tmp/requirements.txt \
 && uv export --locked --only-group build -o /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps -r /tmp/build-requirements.txt
COPY cna/ cna/
RUN uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install . \
 && rm -f /tmp/requirements.txt /tmp/build-requirements.txt

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

# ---- final stage ----
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

ARG CNA_VERSION=dev
LABEL org.opencontainers.image.title="CNA Platform" \
      org.opencontainers.image.description="Cloud Network Assessment CLI" \
      org.opencontainers.image.version="${CNA_VERSION}" \
      org.opencontainers.image.source="https://github.com/saulpatinojr/Work-Cloud_Network_Core" \
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

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD cna --help > /dev/null 2>&1 || exit 1

ENTRYPOINT ["cna"]
CMD ["--help"]
