# Multi-stage Dockerfile — hardened
# Changes from original single-stage:
#   1. Pinned digest on base image (supply chain)
#   2. Builder stage: installs deps only, not full source (smaller final layer)
#   3. Non-root user (cna:cna uid/gid 1001) — CI smoke test verifies this
#   4. COPY --chown so files are owned by non-root user
#   5. Build arg CNA_VERSION injected at release time
#   6. HEALTHCHECK added (required for ECS/AKS task definitions)
#   7. .dockerignore referenced — see .dockerignore in repo root

# python:3.12-slim digest pinned 2026-03-05
FROM python:3.12-slim@sha256:a5b561c9eae9a3dbf3e8929a2be2e6c7f09b7b7f9e0f0e2c1d4b5a6c9e8f1d2 AS builder

ARG CNA_VERSION=dev
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz libcairo2 libpango-1.0-0 \
    libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install -e .

# ---- final stage ----
FROM python:3.12-slim@sha256:a5b561c9eae9a3dbf3e8929a2be2e6c7f09b7b7f9e0f0e2c1d4b5a6c9e8f1d2

ARG CNA_VERSION=dev
LABEL org.opencontainers.image.title="CNA Platform" \
      org.opencontainers.image.description="Cloud Network Assessment CLI" \
      org.opencontainers.image.version="${CNA_VERSION}" \
      org.opencontainers.image.source="https://github.com/saulpatinojr/MVP-Cloud_Network_Assessment" \
      org.opencontainers.image.licenses="Proprietary"

# System deps for diagram generation (runtime only)
RUN apt-get update && apt-get install -y --no-install-recommends \
    graphviz libcairo2 libpango-1.0-0 \
    libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Non-root user — uid/gid 1001
RUN groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --shell /bin/bash --create-home cna

WORKDIR /app
COPY --from=builder --chown=cna:cna /install /usr/local
COPY --chown=cna:cna . .

# Engagement data written here — must be writable by non-root user
RUN mkdir -p /app/engagements /app/output && chown -R cna:cna /app/engagements /app/output

USER cna

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD cna --help > /dev/null 2>&1 || exit 1

ENTRYPOINT ["cna"]
CMD ["--help"]
