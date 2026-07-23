# python:3.14-slim digest pinned — see root Dockerfile for the same pattern.
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6 AS builder

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
    "tenacity>=8.4" \
    "jinja2>=3.1" \
    "httpx>=0.27" \
    "click>=8.1" \
    "rich>=13.7"

# Install the cna package itself (no heavy extras — no weasyprint/matplotlib/diagrams)
RUN pip install --no-cache-dir --no-deps --prefix=/install .

# ---- final stage ----
FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

# Non-root user — uid/gid 1001 (matches root Dockerfile's cna user).
RUN groupadd --gid 1001 cna \
 && useradd --uid 1001 --gid cna --no-create-home --shell /usr/sbin/nologin cna

WORKDIR /app
COPY --from=builder --chown=cna:cna /install /usr/local
COPY --chown=cna:cna cna/ /app/cna/
COPY --chown=cna:cna apps/cna-api/ /app/apps/cna-api/

USER cna

# Non-root can't bind <1024; ingress target_port updated to match (see
# infra/terraform/providers/azure/compute/variables.tf: api_target_port).
CMD ["uvicorn", "apps.cna-api.main:app", "--host", "0.0.0.0", "--port", "8080"]
