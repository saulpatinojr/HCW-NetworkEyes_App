# python:3.14-slim digest pinned 2026-09-30 — see root Dockerfile for the same pattern.
# uv, as a stage rather than an inline `COPY --from=<image>`: Dependabot's docker
# updater only reads `FROM` lines, so this is the line its weekly bump moves.
# Keep the version in step with the `uv==` pins in 300-test-codebase.yml.
FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS builder

WORKDIR /build

# Install the cna package with its API extra. `.[api]` resolves the core
# dependencies plus fastapi/uvicorn/psycopg2-binary and the three azure-mgmt-*
# enrichment packages the API exercises, from the single source of truth in
# pyproject.toml — no hand-written pip list to drift out of sync (PY-021). The
# heavier deps (diagrams/matplotlib/pandas/weasyprint) come in as core deps;
# that is accepted and removes the silent enrichment degradation (IMG-010).
#
# Installed from uv.lock (TODO.md T-702) — see the root Dockerfile for the
# pattern: `uv export --locked` fails on lock drift, `--require-hashes` pins
# every wheel, the `build` group is the hash-checked build backend, and uv
# never leaves the builder stage. Every wheel is a prebuilt cp314 manylinux
# wheel (psycopg2-binary included), so no compiler or libpq-dev is needed.
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
# The engine package is a uv workspace member: its pyproject.toml must be present for
# `uv export --locked` to resolve the workspace, before the source tree is copied.
COPY packages/cna-azure-network-engine/pyproject.toml packages/cna-azure-network-engine/
RUN uv export --locked --no-default-groups --no-emit-project --no-emit-workspace --extra api --extra aws -o /tmp/requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install -r /tmp/requirements.txt \
 && uv export --locked --only-group build -o /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps -r /tmp/build-requirements.txt
COPY packages/cna-azure-network-engine/ packages/cna-azure-network-engine/
COPY cna/ cna/
COPY apps/cna-api/ apps/cna-api/
# The engine package first (a workspace member, excluded from the hash-checked export
# above), then the cna package itself; both from the tree, both without build isolation.
RUN uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install ./packages/cna-azure-network-engine \
 && uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install . \
 && rm -f /tmp/requirements.txt /tmp/build-requirements.txt

# ---- drawio fetch stage ----
# Pinned draw.io desktop release, verified by checksum before it can reach
# the final image. Used headlessly (see scripts/drawio-headless.sh) so the
# encyclopedia report's diagram SVGs render instead of silently degrading.
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS drawio-fetch

# bash with pipefail, see the root Dockerfile (hadolint DL4006).
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG DRAWIO_VERSION=31.3.2
ARG DRAWIO_SHA256=725453f32ef7f2f63f8b50b374857a5c312e2aaabcf221cb0600332741ae1094

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL -o /tmp/drawio.deb \
     "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-amd64-${DRAWIO_VERSION}.deb" \
  && echo "${DRAWIO_SHA256}  /tmp/drawio.deb" | sha256sum -c -

# ---- final stage ----
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

# Non-root user — uid/gid 1001 (matches root Dockerfile's cna user).
RUN groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --no-create-home --shell /usr/sbin/nologin cna

# draw.io desktop CLI + xvfb for headless diagram SVG export (Electron needs
# an X display even for --export). The wrapper shadows /usr/bin/drawio on
# PATH and supplies xvfb-run, --no-sandbox, and a writable HOME — see the
# script for why each is required. `drawio --version` proves the whole
# chain (deb deps, xvfb, wrapper) at build time rather than at first render.
COPY --from=drawio-fetch /tmp/drawio.deb /tmp/drawio.deb
COPY --chmod=755 scripts/drawio-headless.sh /usr/local/bin/drawio
# No `apt-get upgrade`: the image is the pinned base digest plus these packages
# (see the root Dockerfile; a Scout finding on a base deb is fixed by the
# Dependabot digest bump, TODO.md T-702).
RUN apt-get update \
 && apt-get install -y --no-install-recommends /tmp/drawio.deb xvfb xauth libasound2t64 \
      graphviz libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
      libharfbuzz0b libgdk-pixbuf-2.0-0 \
 && rm -rf /var/lib/apt/lists/* /tmp/drawio.deb \
 && drawio --version

WORKDIR /app
COPY --from=builder --chown=cna:cna /install /usr/local
COPY --chown=cna:cna cna/ /app/cna/
COPY --chown=cna:cna apps/cna-api/ /app/apps/cna-api/

# pip is unused at runtime and vendors CVE-carrying copies of msgpack and
# setuptools (declared in its own pip/_vendor/bom.cdx.json) that no
# `pip install` can replace — strip it from the shipped image, the same
# reasoning the web image uses to strip npm.
# virtualenv arrives through diagrams -> pre-commit -> virtualenv, and ships its own SBOM
# (virtualenv-*.dist-info/sboms/virtualenv.cdx.json) naming the pip wheels it embeds and
# THEIR vendored certifi, urllib3, msgpack and setuptools. Docker Scout reads that SBOM and
# fails the first real build on 1 critical and 11 high findings (run 40240474498). Nothing
# here creates a virtual environment at runtime, so it goes with pip.
RUN python -m pip uninstall -y pip virtualenv

# Commit the image was built from (200-build-images passes github.sha). The web
# tier compares it with the newest published build (Admin → Updates); empty
# for local builds, which report the running build as unknown.
ARG CNA_BUILD_SHA=
ENV CNA_BUILD_SHA=${CNA_BUILD_SHA}

# Numeric uid, see the root Dockerfile (hadolint DL3066). 1001 is the `cna` user created above.
USER 1001

# Liveness for orchestrators (ECS/AKS/Container Apps): the API answers on 8080
# once uvicorn is up. Uses the stdlib (no curl, and pip is stripped).
# Exec form (hadolint DL3025). An uncaught exception (refused connection, timeout, HTTP error) already exits 1,
# so the `|| exit 1` the shell form carried added nothing.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).status < 500 else 1)"]

# Non-root can't bind <1024, so the API listens on 8080.
CMD ["uvicorn", "apps.cna-api.main:app", "--host", "0.0.0.0", "--port", "8080"]
