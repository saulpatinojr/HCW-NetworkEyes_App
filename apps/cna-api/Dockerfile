# python:3.14-slim digest pinned — see root Dockerfile for the same pattern.
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS builder

WORKDIR /build

# libpq-dev + gcc needed for psycopg2 compilation; builder-only, not in final image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
  && rm -rf /var/lib/apt/lists/*

# Copy only what the API needs to avoid pulling in diagram/report deps.
# The cna package discovery modules only require azure-mgmt-* + pydantic + tenacity.
COPY pyproject.toml .
COPY cna/ cna/
COPY apps/cna-api/ apps/cna-api/

RUN pip install --no-cache-dir --prefix=/install \
    "fastapi>=0.115" \
    "uvicorn[standard]>=0.30" \
    "pydantic>=2.9" \
    "psycopg2-binary>=2.9" \
    "azure-identity>=1.17" \
    "azure-mgmt-network>=25.0" \
    "azure-mgmt-resource>=23.2" \
    "azure-mgmt-subscription>=3.1" \
    "azure-mgmt-monitor>=6.0" \
    "azure-mgmt-loganalytics>=13.0" \
    "azure-mgmt-compute>=30.0" \
    "azure-storage-blob>=12.19" \
    "boto3>=1.34" \
    "tenacity>=8.4" \
    "jinja2>=3.1" \
    "httpx>=0.27" \
    "click>=8.1" \
    "rich>=13.7"

# Install the cna package itself (no heavy extras — no weasyprint/matplotlib/diagrams)
RUN pip install --no-cache-dir --no-deps --prefix=/install .

# ---- drawio fetch stage ----
# Pinned draw.io desktop release, verified by checksum before it can reach
# the final image. Used headlessly (see scripts/drawio-headless.sh) so the
# encyclopedia report's diagram SVGs render instead of silently degrading.
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5 AS drawio-fetch

ARG DRAWIO_VERSION=31.3.2
ARG DRAWIO_SHA256=725453f32ef7f2f63f8b50b374857a5c312e2aaabcf221cb0600332741ae1094

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
  && rm -rf /var/lib/apt/lists/* \
  && curl -fsSL -o /tmp/drawio.deb \
     "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-amd64-${DRAWIO_VERSION}.deb" \
  && echo "${DRAWIO_SHA256}  /tmp/drawio.deb" | sha256sum -c -

# ---- final stage ----
FROM python:3.14-slim@sha256:cae66f2ef0ec51a9891263eeee7f987dacf0a9879e8aa9353d5606e0530619a5

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
RUN apt-get update \
 && apt-get -y upgrade \
 && apt-get install -y --no-install-recommends /tmp/drawio.deb xvfb xauth libasound2t64 \
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
RUN python -m pip uninstall -y pip

USER cna

# Non-root can't bind <1024; ingress target_port updated to match (see
# infra/terraform/providers/azure/compute/variables.tf: api_target_port).
CMD ["uvicorn", "apps.cna-api.main:app", "--host", "0.0.0.0", "--port", "8080"]
