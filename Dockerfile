# Multi-stage Dockerfile — hardened
#
# Two builds from one file (REFACTOR_APP.md change set I):
#   EDITION=appliance (default)  the CLI image as before: the full network_assessment package, the engine
#                                with its [azure] extra, graphviz and draw.io.
#   EDITION=lab                  build-only: the engine package without [azure], no apps/,
#                                no server; its CMD is the boundary proof (exit 0 only when
#                                azure is not importable). CI builds it with `--build-arg
#                                EDITION=lab` and never pushes it. The deployable lab
#                                build is HCW-NetworkEyes_AddOn, built on the published
#                                engine with this same pattern.
# Changes from original single-stage:
#   1. Pinned digest on base image (supply chain)
#   2. Builder stage: installs deps only, not full source (smaller final layer)
#   3. Non-root user (network-assessment:network-assessment uid/gid 1001) — CI smoke test verifies this
#   4. COPY --chown so files are owned by non-root user
#   5. Build arg NETWORK_ASSESSMENT_VERSION (default `dev`): only a local `docker build --build-arg NETWORK_ASSESSMENT_VERSION=...` sets it;
#      the images 200-build-images.yml publishes (and 310 promotes) are built without it
#   6. HEALTHCHECK added (required for ECS/AKS task definitions)
#   7. .dockerignore referenced — see .dockerignore in repo root

# python:3.14.10-slim-trixie digest pinned 2026-11-07 (Python 3.14.10 on Debian 13 "trixie", built 2026-11-05; the
# same digest python:3.14-slim pointed to that day). The tag names the Debian release on purpose: every image in this
# repository is Debian trixie (the web image's node:24-trixie-slim included), so a future Debian release under the
# floating tag cannot move one image to another distribution unnoticed. Dependabot's docker ecosystem watches every
# Dockerfile and bumps the digest on each FROM line; the `apt-get upgrade` in the final stage keeps the debs current
# between bumps (TODO.md T-741).
# uv, as a stage rather than an inline `COPY --from=<image>`: Dependabot's docker
# updater only reads `FROM` lines, so this is the line its weekly bump moves.
# Keep the version in step with the `uv==` pins in 300-test-codebase.yml.
ARG EDITION=appliance

FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv

FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS builder

ARG NETWORK_ASSESSMENT_VERSION=dev
WORKDIR /build

RUN apt-get -o Acquire::Retries=0 update --error-on=any && apt-get -o Acquire::Retries=0 install -y --no-install-recommends \
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
COPY packages/network-assessment-azure-engine/pyproject.toml packages/network-assessment-azure-engine/
# The appliance build serves both clouds, so the [aws] extra rides along here; the
# package itself declares boto3 only under that extra (change set K).
RUN uv export --locked --no-default-groups --no-emit-project --no-emit-workspace --extra aws -o /tmp/requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install -r /tmp/requirements.txt \
 && uv export --locked --only-group build -o /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps -r /tmp/build-requirements.txt
COPY packages/network-assessment-azure-engine/ packages/network-assessment-azure-engine/
COPY network_assessment/ network_assessment/
# The engine package first (a workspace member, excluded from the hash-checked export
# above), then the network_assessment package itself; both from the tree, both without build isolation.
RUN uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install ./packages/network-assessment-azure-engine \
 && uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install . \
 && rm -f /tmp/requirements.txt /tmp/build-requirements.txt

# ---- lab builder stage (build-only; change set I) ----
# The engine package alone, without the [azure] extra, into its own prefix. The
# boundary is proved before the final stage exists: a resolvable azure, msal or
# boto3 fails the build here, the same check the AddOn's image runs.
FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS builder-lab

ARG EDITION
RUN test "$EDITION" = "lab" || { echo "builder-lab is only built for EDITION=lab (got '$EDITION')" >&2; exit 1; }
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /build
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
COPY packages/network-assessment-azure-engine/ packages/network-assessment-azure-engine/
# The engine's base dependencies from the lock (hash-checked), then the engine itself
# from the tree with no extras: no cloud SDK is named anywhere in this stage.
RUN uv export --locked --no-default-groups --no-emit-project --no-emit-workspace --package network-assessment-azure-engine -o /tmp/lab-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install-lab -r /tmp/lab-requirements.txt \
 && uv export --locked --only-group build -o /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps -r /tmp/build-requirements.txt \
 && uv pip install --system --no-cache --no-deps --no-build-isolation --prefix=/install-lab ./packages/network-assessment-azure-engine \
 && rm -f /tmp/lab-requirements.txt /tmp/build-requirements.txt \
 && PYTHONPATH=/install-lab/lib/python3.14/site-packages python -m network_assessment_azure_engine.edition

# ---- drawio fetch stage ----
# Pinned draw.io desktop release, verified by checksum before it can reach
# the final image. The export pipeline (network_assessment/diagram_engine/export_pipeline.py)
# degrades to XML-only output without it — its own warning promises the CLI
# is available "inside the Docker container", which is made true here.
FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS drawio-fetch

# bash with pipefail: the checksum step below is a pipe (`echo | sha256sum -c -`), and a failure on the left
# of a pipe must fail the build (hadolint DL4006). The default /bin/sh would hide it.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG DRAWIO_VERSION=31.3.2
ARG DRAWIO_SHA256=725453f32ef7f2f63f8b50b374857a5c312e2aaabcf221cb0600332741ae1094

RUN apt-get -o Acquire::Retries=0 update --error-on=any && apt-get -o Acquire::Retries=0 install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL -o /tmp/drawio.deb \
     "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-amd64-${DRAWIO_VERSION}.deb" \
  && echo "${DRAWIO_SHA256}  /tmp/drawio.deb" | sha256sum -c -

# ---- final stage: lab (build-only) ----
# No apps/, no server, no EXPOSE, no HEALTHCHECK: the image's only job is the proof.
FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS final-lab

COPY --from=builder-lab /install-lab /usr/local
RUN python -m pip uninstall -y pip \
 && groupadd --gid 1001 network-assessment \
 && useradd --uid 1001 --gid network-assessment --no-create-home --shell /usr/sbin/nologin network-assessment
# Numeric uid: an orchestrator can prove a numeric user is not root, a name it cannot (hadolint DL3066).
# 1001 is the `network-assessment` user created above; Docker takes its group from /etc/passwd.
USER 1001
ENV NETWORK_ASSESSMENT_EDITION=lab
# Exit 0 when azure is NOT importable and no identity variable is set; exit 1 otherwise.
CMD ["python", "-m", "network_assessment_azure_engine.edition"]

# ---- final stage: appliance ----
FROM python:3.14.10-slim-trixie@sha256:af8a5aa14780025dbfbcfbc81bd8a91ebd87711dd5b0f48ed71090949dd7cb1d AS final-appliance

ARG NETWORK_ASSESSMENT_VERSION=dev
LABEL org.opencontainers.image.title="NetworkEyes" \
      org.opencontainers.image.description="Cloud Network Assessment CLI" \
      org.opencontainers.image.version="${NETWORK_ASSESSMENT_VERSION}" \
      org.opencontainers.image.source="https://github.com/saulpatinojr/HCW-NetworkEyes_App" \
      org.opencontainers.image.licenses="Apache-2.0"

# Debian's security updates first, then the system deps for diagram generation (runtime only).
# `apt-get upgrade` is deliberate (TODO.md T-741): the base is pinned by digest, but a Debian security upload
# reaches the mirrors days before the official image is rebuilt with it. On 2026-11-05 the Scout gate in
# 200-build-images.yml refused every build on main for apt 3.0.3 (CVE-2026-109518, DSA-6607-1, fixed in 3.0.4
# from trixie-security) while the newest python:3.14-slim and debian:trixie-slim digests still shipped 3.0.3, so
# no digest bump could clear it. The upgrade closes that window; Dependabot's weekly digest bump still moves the
# base. The packages below are installed unpinned (hadolint DL3008 is ignored with a reason in .hadolint.yaml),
# so a rebuild on another day gets that day's versions on the same base; the Scout gate, which refuses fixable
# critical and high findings at every build, is the control that matters. `Acquire::Retries=0` on the update and
# the upgrade: the apt doing this upgrade is still the base's 3.0.3, and CVE-2026-109518 needs a download retry to
# slip an unverified package in, so the retry path is closed until the upgraded apt is in place (a mirror hiccup
# then fails the build instead of retrying). PUBLISH_CACHE_BUST is a per-run value the publish workflow passes
# (its run id and attempt); naming it in the command makes this layer's cache key differ on every run, so a
# rebuild of the same commit cannot reuse an older upgrade result from the Actions build cache after a newer
# security upload has reached the mirrors. Unset on a local build, which is fine: the layer is then cached as usual.
# `--error-on=any` makes the update fail if any index (trixie-security above all) cannot be fetched, instead of
# succeeding with a warning and leaving apt unupgraded; the install keeps retries off too, in case the upgrade
# found nothing to do and the base's apt is still the one installing.
ARG PUBLISH_CACHE_BUST=
RUN printf 'upgrade run: %s\n' "${PUBLISH_CACHE_BUST}" \
    && apt-get -o Acquire::Retries=0 update --error-on=any \
    && apt-get -o Acquire::Retries=0 upgrade -y --no-install-recommends \
    && apt-get -o Acquire::Retries=0 install -y --no-install-recommends \
    graphviz libcairo2 libpango-1.0-0 \
    libpangocairo-1.0-0 libgdk-pixbuf-2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# draw.io desktop CLI + xvfb for headless diagram export (.drawio -> .svg).
# The wrapper shadows /usr/bin/drawio on PATH and supplies xvfb-run,
# --no-sandbox, and a writable HOME — see the script for why each is
# required. `drawio --version` proves the whole chain at build time.
COPY --from=drawio-fetch /tmp/drawio.deb /tmp/drawio.deb
COPY --chmod=755 scripts/drawio-headless.sh /usr/local/bin/drawio
RUN apt-get -o Acquire::Retries=0 update --error-on=any \
 && apt-get -o Acquire::Retries=0 install -y --no-install-recommends /tmp/drawio.deb xvfb xauth libasound2t64 \
 && rm -rf /var/lib/apt/lists/* /tmp/drawio.deb \
 && drawio --version

# Non-root user — uid/gid 1001
RUN groupadd --gid 1001 network-assessment \
 && useradd --uid 1001 --gid network-assessment --shell /bin/bash --create-home network-assessment

WORKDIR /app
COPY --from=builder --chown=network-assessment:network-assessment /install /usr/local
COPY --chown=network-assessment:network-assessment . .

# Engagement data written here — must be writable by non-root user
RUN mkdir -p /app/engagements /app/output && chown -R network-assessment:network-assessment /app/engagements /app/output

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

# Numeric uid, see the lab stage (hadolint DL3066).
USER 1001
ENV NETWORK_ASSESSMENT_EDITION=appliance

# Exec form (hadolint DL3025): no shell between Docker and the process.
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["network-assessment", "--help"]

ENTRYPOINT ["network-assessment"]
CMD ["--help"]

# ---- the build that was asked for ----
# `docker build .` is the appliance image exactly as before; `--build-arg EDITION=lab`
# selects the build-only lab target. Any other value fails at builder-lab.
# DL3006 cannot see through `final-${EDITION}`: it is one of the two stages named above (final-lab,
# final-appliance), both pinned by digest, and any other value fails at builder-lab. Ignored on this line only.
# hadolint ignore=DL3006
FROM final-${EDITION}
