FROM python:3.11-slim

# libpq-dev + gcc needed for psycopg2 compilation; cleaned up after.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only what the API needs to avoid pulling in diagram/report deps.
# The cna package discovery modules only require azure-mgmt-* + pydantic + tenacity.
COPY pyproject.toml /app/
COPY cna/ /app/cna/
COPY apps/cna-api/ /app/apps/cna-api/

RUN pip install --no-cache-dir \
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
RUN pip install --no-cache-dir --no-deps -e .

CMD ["uvicorn", "apps.cna-api.main:app", "--host", "0.0.0.0", "--port", "80"]
