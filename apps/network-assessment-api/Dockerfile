# python:3.14.10-slim-trixie digest pinned 2026-11-07 (Python 3.14.10 on Debian 13 "trixie", built 2026-11-05) — see
# the root Dockerfile for why the tag names the Debian release.
# uv, as a stage rather than an inline `COPY --from=<image>`: Dependabot's docker
# updater only reads `FROM` lines, so this is the line its weekly bump moves.
# Keep the version in step with the `uv==` pins in 300-test-codebase.yml.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS builder

WORKDIR /build

# Install the network_assessment package with its API extra. `.[api]` resolves the core
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
COPY packages/network-assessment-azure-engine/pyproject.toml packages/network-assessment-azure-engine/
RUN uv export --locked --no-default-groups --no-emit-project --no-emit-workspace --extra api --extra aws -o /tmp/requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install -r /tmp/requirements.txt \
 && uv export --locked --only-group build -o /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps -r /tmp/build-requirements.txt
COPY packages/network-assessment-azure-engine/ packages/network-assessment-azure-engine/
COPY network_assessment/ network_assessment/
COPY apps/network-assessment-api/ apps/network-assessment-api/
# The engine package first (a workspace member, excluded from the hash-checked export
# above), then the network_assessment package itself; both from the tree, both without build isolation.
RUN uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install ./packages/network-assessment-azure-engine \
 && uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install . \
 && rm -f /tmp/requirements.txt /tmp/build-requirements.txt

# ---- drawio fetch stage ----
# Pinned draw.io desktop release, verified by checksum before it can reach
# the final image. Used headlessly (see scripts/drawio-headless.sh) so the
# encyclopedia report's diagram SVGs render instead of silently degrading.
FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS drawio-fetch

# bash with pipefail, see the root Dockerfile (hadolint DL4006).
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG DRAWIO_VERSION=31.3.2
ARG DRAWIO_SHA256=725453f32ef7f2f63f8b50b374857a5c312e2aaabcf221cb0600332741ae1094

RUN apt-get -o Acquire::Retries=0 update --error-on=any && apt-get -o Acquire::Retries=0 install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL -o /tmp/drawio.deb \
     "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-amd64-${DRAWIO_VERSION}.deb" \
  && echo "${DRAWIO_SHA256}  /tmp/drawio.deb" | sha256sum -c -

# ---- final stage ----
# Named so tests/unit/test_ci_hygiene.py can find the shipped stage; the build target is unchanged (it is the last stage).
FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS final

# Non-root user — uid/gid 1001 (matches root Dockerfile's network-assessment user).
RUN groupadd --gid 1001 network-assessment \
 && useradd --uid 1001 --gid network-assessment --no-create-home --shell /usr/sbin/nologin network-assessment

# draw.io desktop CLI + xvfb for headless diagram SVG export (Electron needs
# an X display even for --export). The wrapper shadows /usr/bin/drawio on
# PATH and supplies xvfb-run, --no-sandbox, and a writable HOME — see the
# script for why each is required. `drawio --version` proves the whole
# chain (deb deps, xvfb, wrapper) at build time rather than at first render.
COPY --from=drawio-fetch /tmp/drawio.deb /tmp/drawio.deb
COPY --chmod=755 scripts/drawio-headless.sh /usr/local/bin/drawio
# Debian's security updates first (`apt-get upgrade`, deliberate: a security upload reaches the mirrors before
# the official base image is rebuilt with it, and on 2026-11-05 no python:3.14-slim digest was free of
# CVE-2026-109518; see the root Dockerfile and TODO.md T-741), then these packages. `Acquire::Retries=0` closes
# that CVE's retry path while the base's apt 3.0.3 is the one doing the upgrade (see the root Dockerfile).
# PUBLISH_CACHE_BUST, named in the command, keeps the publish workflow from reusing a cached upgrade layer on a
# later run of the same commit (see the root Dockerfile's final-appliance stage).
ARG PUBLISH_CACHE_BUST=
RUN printf 'upgrade run: %s\n' "${PUBLISH_CACHE_BUST}" \
 && apt-get -o Acquire::Retries=0 update --error-on=any \
 && apt-get -o Acquire::Retries=0 upgrade -y --no-install-recommends \
 && apt-get -o Acquire::Retries=0 install -y --no-install-recommends /tmp/drawio.deb xvfb xauth libasound2t64 \
      graphviz libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libpangoft2-1.0-0 \
      libharfbuzz0b libgdk-pixbuf-2.0-0 \
 && rm -rf /var/lib/apt/lists/* /tmp/drawio.deb \
 && drawio --version

WORKDIR /app
COPY --from=builder --chown=network-assessment:network-assessment /install /usr/local
COPY --chown=network-assessment:network-assessment network_assessment/ /app/network_assessment/
COPY --chown=network-assessment:network-assessment apps/network-assessment-api/ /app/apps/network-assessment-api/

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
ARG NETWORK_ASSESSMENT_BUILD_SHA=
ENV NETWORK_ASSESSMENT_BUILD_SHA=${NETWORK_ASSESSMENT_BUILD_SHA}

# Numeric uid, see the root Dockerfile (hadolint DL3066). 1001 is the `network-assessment` user created above.
USER 1001

# Liveness for orchestrators (ECS/AKS/Container Apps): the API answers on 8080
# once uvicorn is up. Uses the stdlib (no curl, and pip is stripped).
# Exec form (hadolint DL3025). An uncaught exception (refused connection, timeout, HTTP error) already exits 1,
# so the `|| exit 1` the shell form carried added nothing.
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD ["python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=5).status < 500 else 1)"]

# Non-root can't bind <1024, so the API listens on 8080.
CMD ["uvicorn", "apps.network-assessment-api.main:app", "--host", "0.0.0.0", "--port", "8080"]
