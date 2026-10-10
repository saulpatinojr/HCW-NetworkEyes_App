# python:3.14-slim digest pinned 2026-09-30 — see root Dockerfile for the same pattern.
# uv, as a stage rather than an inline `COPY --from=<image>`: Dependabot's docker
# updater only reads `FROM` lines, so this is the line its weekly bump moves.
# Keep the version in step with the `uv==` pins in 300-test-codebase.yml.
FROM ghcr.io/astral-sh/uv:0.12.21@sha256:a7aed3216253ee804de3e2d8afa5073baa1a177335345d43845cd4165e43b711 AS uv

FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS builder

WORKDIR /build

# The worker installs no package of its own — only the two Azure SDKs
# apps/cna-worker/main.py imports, resolved from the `worker` dependency group
# in uv.lock (TODO.md T-702) so they are the same versions the CLI and API
# images carry, hash-checked, instead of an unpinned `pip install`. uv stays in
# the builder stage; see the root Dockerfile for the pattern.
COPY --from=uv /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock ./
RUN uv export --locked --only-group worker --no-emit-project -o /tmp/requirements.txt \
 && uv pip install --system --no-cache --require-hashes --no-deps --prefix=/install -r /tmp/requirements.txt \
 && rm -f /tmp/requirements.txt

# ---- final stage ----
FROM python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d

# Non-root user — uid/gid 1001 (matches root Dockerfile's cna user).
RUN groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --no-create-home --shell /usr/sbin/nologin cna

WORKDIR /app
COPY --from=builder --chown=cna:cna /install /usr/local
COPY --chown=cna:cna apps/cna-worker /app/apps/cna-worker

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

# The worker is a run-once batch process (and a retirement candidate — see spec
# task 4.5), so a network liveness probe would be misleading. This smoke check
# verifies the module and its Azure SDK deps import cleanly, which is the
# meaningful "the container is well-formed" signal for a batch image.
HEALTHCHECK --interval=60s --timeout=10s --start-period=5s --retries=2 \
    CMD python -c "import azure.identity, azure.storage.blob" || exit 1

CMD ["python", "apps/cna-worker/main.py"]
