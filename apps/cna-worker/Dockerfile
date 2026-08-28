# python:3.14-slim digest pinned — see root Dockerfile for the same pattern.
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS builder

WORKDIR /build
COPY pyproject.toml .
COPY apps/cna-worker apps/cna-worker
RUN pip install --no-cache-dir --prefix=/install azure-identity azure-storage-blob

# ---- final stage ----
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5

# Pending Debian security fixes + base pip-toolchain floors, so the gating
# Docker Scout check doesn't fail on base-image packages between digest bumps
# (same pattern as the root and API Dockerfiles).
RUN apt-get update && apt-get -y upgrade && rm -rf /var/lib/apt/lists/* \
 && pip install --no-cache-dir "setuptools>=78.1.1" "msgpack>=1.2.1"

# Non-root user — uid/gid 1001 (matches root Dockerfile's cna user).
RUN groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --no-create-home --shell /usr/sbin/nologin cna

WORKDIR /app
COPY --from=builder --chown=cna:cna /install /usr/local
COPY --chown=cna:cna apps/cna-worker /app/apps/cna-worker

USER cna

CMD ["python", "apps/cna-worker/main.py"]
