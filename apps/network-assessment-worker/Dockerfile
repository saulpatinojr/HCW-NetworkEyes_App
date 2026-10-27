# python:3.14-slim digest pinned 2026-09-30 — see root Dockerfile for the same pattern.
# uv, as a stage rather than an inline `COPY --from=<image>`: Dependabot's docker
# updater only reads `FROM` lines, so this is the line its weekly bump moves.
# Keep the version in step with the `uv==` pins in 300-test-codebase.yml.
FROM ghcr.io/astral-sh/uv:0.13.6@sha256:af22a52f5eafef3d78e551599d405c02df61919d18028f0cea8eda93bc9986d0 AS uv

FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170 AS builder

WORKDIR /build

# The worker installs no package of its own — only the two Azure SDKs
# apps/network-assessment-worker/main.py imports, resolved from the `worker` dependency group
# in uv.lock (TODO.md T-702) so they are the same versions the CLI and API
# images carry, hash-checked, instead of an unpinned `pip install`. uv stays in
# the builder stage; see the root Dockerfile for the pattern.
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
# The engine package is a uv workspace member: its pyproject.toml must be present for
# `uv export --locked` to resolve the workspace, before the source tree is copied.
COPY packages/network-assessment-azure-engine/pyproject.toml packages/network-assessment-azure-engine/
RUN uv export --locked --only-group worker --no-emit-project --no-emit-workspace -o /tmp/requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install -r /tmp/requirements.txt \
 && rm -f /tmp/requirements.txt

# ---- final stage ----
FROM python:3.14-slim@sha256:a2b82f3c48559aa0a8446d9af49826b6e2b2016f4cd2afabfe6013ec53729170

# Non-root user — uid/gid 1001 (matches root Dockerfile's network-assessment user).
RUN groupadd --gid 1001 network-assessment \
 && useradd --uid 1001 --gid network-assessment --no-create-home --shell /usr/sbin/nologin network-assessment

WORKDIR /app
COPY --from=builder --chown=network-assessment:network-assessment /install /usr/local
COPY --chown=network-assessment:network-assessment apps/network-assessment-worker /app/apps/network-assessment-worker

# pip is unused at runtime and vendors CVE-carrying copies of msgpack and
# setuptools (declared in its own pip/_vendor/bom.cdx.json) that no
# `pip install` can replace — strip it from the shipped image, the same
# reasoning the web image uses to strip npm.
RUN python -m pip uninstall -y pip

# Commit the image was built from (200-build-images passes github.sha). The web
# tier compares it with the newest published build (Admin → Updates); empty
# for local builds, which report the running build as unknown.
ARG NETWORK_ASSESSMENT_BUILD_SHA=
ENV NETWORK_ASSESSMENT_BUILD_SHA=${NETWORK_ASSESSMENT_BUILD_SHA}

# Numeric uid, see the root Dockerfile (hadolint DL3066). 1001 is the `network-assessment` user created above.
USER 1001

# The worker is a run-once batch process (and a retirement candidate — see spec
# task 4.5), so a network liveness probe would be misleading. This smoke check
# verifies the module and its Azure SDK deps import cleanly, which is the
# meaningful "the container is well-formed" signal for a batch image.
# Exec form (hadolint DL3025); a failed import exits 1 by itself.
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=2 \
    CMD ["python", "-c", "import azure.identity, azure.storage.blob"]

CMD ["python", "apps/network-assessment-worker/main.py"]
