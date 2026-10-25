"""CNA API — discovery orchestration layer.

Accepts discovery jobs from cna-web, runs the Azure discovery engine in
background tasks, maps the resulting topology to security findings, and writes
everything back to PostgreSQL.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from collections.abc import Mapping
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import psycopg2
import psycopg2.extras
from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# Ensure the repo root is on the path so `cna` package is importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cna.api_errors import sanitize_downstream_error
from cna.api_status import Outcome, status_for
from cna.aws import AWS_NOT_INSTALLED, aws_extra_installed
from cna.core.auth import refuse_forbidden_credential_env
from cna.core.finding_taxonomy import classify_traffic_direction
from cna.core.logging_config import JSONFormatter
from cna.core.persistence import EngagementStore
from cna.modules.network.analysis.azure_findings import RULES, RULES_VERSION, evaluate_azure
from cna.modules.network.discovery.azure_discovery import (
    AzureDiscovery,
    AzureDiscoveryOptions,
)


def _configure_structured_logging() -> None:
    """Emit API log records as single-line JSON (level + message + context).

    Requirement 8.2: an error the API emits must be captured as a *structured*
    log record. ``logging.basicConfig`` alone produces unstructured plain-text
    lines, so a JSON error surfaced by ``logger.exception(...)`` could not be
    parsed downstream. Attaching the core engine's :class:`JSONFormatter` to a
    stdout handler on the root logger makes every emitted record (including the
    ``cna-api`` logger and the ``cna`` engine loggers) a parseable JSON object
    carrying at least ``level`` and ``message``, so Container Apps / Log
    Analytics can ingest and query them.
    """
    root = logging.getLogger()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


_configure_structured_logging()
logger = logging.getLogger("cna-api")


# The container starts uvicorn with module path "apps.cna-api.main" from /app,
# so only /app is on sys.path — make the API directory importable so the
# absolute `routers.*` imports resolve in both container and local runs.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from auth import BearerTokenMiddleware  # noqa: E402, I001
from entra import (  # noqa: E402, I001
    AuthError,
    EntraConfig,
    configure as configure_entra,
    refuse_profile_in_appliance,
    require_bearer,
)
from finding_records import finding_to_record  # noqa: E402, I001
import db  # noqa: E402, I001
from routers.chat import router as chat_router  # noqa: E402, I001
from routers.metrics import rebuild_metrics  # noqa: E402
from routers.metrics import router as metrics_router  # noqa: E402
from routers.reports import router as reports_router  # noqa: E402
from routers.diagrams import router as diagrams_router  # noqa: E402

DATABASE_URL = os.environ.get("DATABASE_URL", "")
# Shared bearer secret the web tier must present (SEC-001). Empty in local dev.
CNA_API_TOKEN = os.environ.get("CNA_API_TOKEN", "")
# Set by the deployment ("azure" | "aws"); empty means local dev.
CNA_APPLIANCE_CLOUD = os.environ.get("CNA_APPLIANCE_CLOUD", "")

# A RUNNING job whose updatedAt (bumped by every progress line — see _log) is
# older than this has no live owner and is reaped to FAILED (REL-001 / DATA-003).


def _parse_stale_job_minutes(raw: str | None) -> int:
    """Parse ``CNA_STALE_JOB_MINUTES`` as a positive integer.

    A non-integer or non-positive value would either crash import with a bare
    ``ValueError`` or (for zero / negative) make the reaper fail every RUNNING
    job on each poll, so both are refused at startup with a clear message.
    """
    text = "30" if raw is None or raw.strip() == "" else raw.strip()
    try:
        minutes = int(text)
    except ValueError as exc:
        raise SystemExit(
            f"CNA_STALE_JOB_MINUTES must be a positive integer number of minutes, got {text!r}."
        ) from exc
    if minutes <= 0:
        raise SystemExit(
            f"CNA_STALE_JOB_MINUTES must be greater than zero, got {minutes} — a zero or "
            "negative threshold would mark every running discovery job as failed."
        )
    return minutes


_STALE_JOB_MINUTES = _parse_stale_job_minutes(os.environ.get("CNA_STALE_JOB_MINUTES"))
_STALE_JOB_ERROR = (
    "Discovery stopped reporting progress (the API restarted or the job was "
    "interrupted). Start discovery again."
)

if not DATABASE_URL:
    logger.warning(
        "DATABASE_URL is not set — discovery results will NOT be persisted. "
        "Jobs, findings, and metrics writes will be silently skipped until it is configured."
    )


def _api_version() -> str:
    """Report the installed ``cna`` package version, or ``"unknown"``.

    The version is single-sourced from package metadata (pyproject) rather than
    a literal that drifts from the release. A source checkout with no installed
    dist reports ``"unknown"`` instead of a stale hardcoded number.
    """
    try:
        return _pkg_version("cna")
    except PackageNotFoundError:
        return "unknown"


def _validate_startup_config(env: Mapping[str, str]) -> None:
    """Fail fast on a misconfigured appliance deployment (PY-001 / SEC-001).

    Appliance mode is signalled by ``CNA_APPLIANCE_CLOUD``. In that mode both a
    database and the shared API token are mandatory; booting without them puts
    the API into the silent no-op / unauthenticated states that the audit
    flagged, so the process refuses to start instead. In local dev (no
    appliance cloud) an unauthenticated API is allowed with one warning.
    """
    appliance = bool(env.get("CNA_APPLIANCE_CLOUD"))
    token = env.get("CNA_API_TOKEN", "")
    database_url = env.get("DATABASE_URL", "")
    # An appliance build never honours the test profile (change set H); checked
    # before anything else so the exit names the one thing that is wrong.
    refuse_profile_in_appliance(env)
    if appliance:
        # No secret-shaped credential variable may reach an appliance process: the
        # identity is the user-assigned managed identity (change set G).
        refuse_forbidden_credential_env(env)
    # Entra is validated here so a half-configured tenant/audience pair exits at
    # start-up rather than at the first request.
    entra = EntraConfig.from_env(env)

    if appliance and not database_url:
        raise SystemExit(
            "DATABASE_URL is not set but CNA_APPLIANCE_CLOUD is — refusing to start. "
            "The deployment must supply DATABASE_URL as a container secret."
        )
    if appliance and not token and entra is None:
        raise SystemExit(
            "Neither CNA_API_TOKEN nor CNA_ENTRA_TENANT_ID/CNA_ENTRA_AUDIENCE is set but "
            "CNA_APPLIANCE_CLOUD is — refusing to start. The deployment must "
            "supply CNA_API_TOKEN as a container secret on both the api and the web "
            "containers, or configure Entra bearer validation for the web identity."
        )
    if not token and entra is None and not appliance:
        logger.warning(
            "CNA_API_TOKEN is not set and CNA_APPLIANCE_CLOUD is unset (local dev) — "
            "the API will accept UNAUTHENTICATED requests. Never run this way in production."
        )


_validate_startup_config(os.environ)
# The process-wide Entra validator (None when Entra is not configured).
ENTRA = configure_entra(EntraConfig.from_env(os.environ))

# The internal routes carry the Entra dependency on this router and nowhere else:
# a public route can never inherit it by accident, and a route that must be
# protected is registered here by name (tests/unit/test_cna_api_auth.py holds the
# list). The shared-token middleware below still fronts every non-probe path.
internal = APIRouter(dependencies=[Depends(require_bearer)])


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    """Reap jobs left RUNNING by a previous process on startup (REL-001).

    Single-replica assumption: the API runs one uvicorn worker, so any RUNNING
    job older than the stale threshold was orphaned by a restart/crash and has
    no live owner. Best effort — a reaper failure never blocks startup.
    """
    try:
        reaped = _reap_stale_jobs()
        if reaped:
            logger.warning("startup reaper marked %d stale RUNNING job(s) as FAILED", reaped)
    except Exception:
        logger.exception("startup stale-job reaper failed")
    try:
        yield
    finally:
        # Return every pooled connection to the server on shutdown (T-704).
        db.close_all()


app = FastAPI(title="CNA API", version=_api_version(), lifespan=_lifespan)
app.include_router(metrics_router)
app.include_router(chat_router)
app.include_router(reports_router)
app.include_router(diagrams_router)


@app.exception_handler(AuthError)
async def _handle_auth_error(_request, exc: AuthError) -> JSONResponse:
    """``401 {"error": {"code": "unauthenticated"}}`` / ``403 {"error": {"code":
    "insufficient_role"}}`` from the internal router's Entra dependency."""
    headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
    return JSONResponse(
        status_code=exc.status_code, content={"error": {"code": exc.code}}, headers=headers
    )


@app.exception_handler(db.PoolTimeout)
async def _handle_pool_timeout(_request, exc: db.PoolTimeout) -> JSONResponse:
    """503 when no pooled database connection frees up in time (T-704).

    The pool is bounded so a burst cannot exhaust the database server; a caller
    that waits past the budget is told to retry rather than handed a 500.
    """
    logger.warning("database connection pool timeout: %s", exc)
    return JSONResponse(
        status_code=status_for(Outcome.UNAVAILABLE),
        content={"detail": "database busy; retry shortly"},
        headers={"Retry-After": "2"},
    )


@app.exception_handler(RequestValidationError)
async def _handle_validation_error(_request, exc: RequestValidationError) -> JSONResponse:
    """Return validation errors without the request-body echo (PY-011).

    Pydantic v2 places the offending value in ``input`` and coercion detail in
    ``ctx``; for discovery requests ``input`` is the whole body, which carries
    plaintext cloud secrets. Strip both and return only ``loc``/``msg``/``type``.
    """
    safe = [{k: v for k, v in err.items() if k not in ("input", "ctx")} for err in exc.errors()]
    return JSONResponse(
        status_code=status_for(Outcome.INVALID_REQUEST),
        content={"detail": safe},
    )


# Enforce the bearer when either form is configured. In local dev (neither
# CNA_API_TOKEN nor CNA_ENTRA_* set) no middleware is added — see
# _validate_startup_config, which already refused to start if that happens in
# appliance mode. There is no variable that disables it.
if CNA_API_TOKEN or ENTRA is not None:
    app.add_middleware(BearerTokenMiddleware, token=CNA_API_TOKEN, entra=ENTRA)


# ─── DB helpers ───────────────────────────────────────────────────────────────


def _get_db():
    """A pooled connection with ``with conn:`` transaction semantics (T-704).

    Every call site is ``with _get_db() as conn:``; the connection commits on a
    clean exit, rolls back on an exception, and returns to the pool either way.
    """
    return db.connection(DATABASE_URL)


def _update_job(job_id: str, **kwargs: Any) -> None:
    if not DATABASE_URL:
        return
    sets = ", ".join(f'"{k}" = %s' for k in kwargs)
    values = list(kwargs.values()) + [job_id]
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f'UPDATE "DiscoveryJob" SET {sets}, "updatedAt" = NOW() WHERE id = %s',  # noqa: S608
                values,
            )
        conn.commit()


def _replace_discovery_findings(
    engagement_id: str, credential_id: str | None, findings: list[dict]
) -> None:
    """Replace discovery findings for a specific credential (subscription sync group).

    On success: delete old non-AI findings for this credential, then insert fresh ones.
    On failure: this function is never called, so old data is preserved.
    """
    if not DATABASE_URL:
        return
    with _get_db() as conn:
        with conn.cursor() as cur:
            if credential_id:
                # Remove stale findings for this subscription — other subscriptions untouched
                cur.execute(
                    'DELETE FROM "Finding" WHERE "engagementId" = %s AND "credentialId" = %s AND "aiGenerated" = false',
                    (engagement_id, credential_id),
                )
            if findings:
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO "Finding"
                         (id, "engagementId", "credentialId", title, severity, category,
                          description, recommendation, "aiGenerated",
                          "trafficDirection", region, "resourceType", "estCostImpact",
                          "createdAt", "updatedAt")
                       VALUES %s""",
                    [
                        (
                            str(uuid.uuid4()),
                            engagement_id,
                            credential_id,
                            f["title"],
                            f["severity"],
                            f["category"],
                            f["description"],
                            f.get("recommendation", ""),
                            False,
                            f.get("traffic_direction") or None,
                            f.get("region") or None,
                            f.get("resource_type") or None,
                            f.get("est_cost_impact"),
                            datetime.now(UTC),
                            datetime.now(UTC),
                        )
                        for f in findings
                    ],
                )
        conn.commit()


def _advance_engagement_status(engagement_id: str) -> None:
    if not DATABASE_URL:
        return
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE "Engagement"
                   SET status = 'DISCOVERY', "updatedAt" = NOW()
                   WHERE id = %s AND status = 'DRAFT'""",
                (engagement_id,),
            )
        conn.commit()


def _reap_stale_jobs(job_id: str | None = None) -> int:
    """Mark RUNNING jobs whose heartbeat has gone stale as FAILED (REL-001).

    ``updatedAt`` is bumped by every progress line (``_log`` → ``_update_job``),
    so it doubles as a heartbeat: a RUNNING job that has not written progress in
    ``_STALE_JOB_MINUTES`` was orphaned by a restart/crash and has no live owner
    (single-replica assumption). Passing ``job_id`` scopes the reap to one job
    (used by the job-status endpoint); omitting it reaps every stale job (used by
    the startup lifespan). Returns the number of rows updated.
    """
    if not DATABASE_URL:
        return 0
    sql = (
        'UPDATE "DiscoveryJob" '
        "SET status = 'FAILED', \"errorMessage\" = %s, "
        '"completedAt" = NOW(), "updatedAt" = NOW() '
        "WHERE status = 'RUNNING' "
        "AND \"updatedAt\" < NOW() - (%s * INTERVAL '1 minute')"
    )
    params: list[Any] = [_STALE_JOB_ERROR, _STALE_JOB_MINUTES]
    if job_id is not None:
        sql += " AND id = %s"
        params.append(job_id)
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            reaped = cur.rowcount
        conn.commit()
    return reaped


def _database_ready() -> bool:
    """Return True if a ``SELECT 1`` against the database succeeds (PY-008).

    Used by ``/ready`` only. The connection comes from the pool and goes back
    to it (PY-002); a dead one is discarded there. Any failure is logged and
    reported as not-ready.
    """
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
    return True


# ─── Topology → Findings mapper ───────────────────────────────────────────────

# Subnets managed by Azure — don't flag missing NSG on these.
# ─── Routes ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health() -> dict:
    # Pure liveness probe — no dependency checks (readiness is /ready). Exempt
    # from bearer auth so orchestrators can probe without the shared secret.
    # CNA_BUILD_SHA is baked into the image by 200-build-images so a deployed
    # instance can say which core commit it runs (Admin → Updates in the web tier).
    return {
        "status": "ok",
        "service": "cna-api",
        "version": _api_version(),
        "build_sha": os.environ.get("CNA_BUILD_SHA", ""),
    }


@app.get("/ready")
def ready() -> JSONResponse:
    """Readiness probe (PY-008): 200 only when the database answers ``SELECT 1``.

    ``/health`` stays a pure liveness signal; this endpoint gates traffic on the
    dependency the API cannot function without. Exempt from bearer auth.
    """
    if not DATABASE_URL:
        return JSONResponse(
            status_code=status_for(Outcome.NOT_CONFIGURED),
            content={"status": "not_ready", "checks": {"database": "not_configured"}},
        )
    try:
        _database_ready()
    except Exception:
        logger.exception("readiness check failed")
        return JSONResponse(
            status_code=status_for(Outcome.NOT_CONFIGURED),
            content={"status": "not_ready", "checks": {"database": "unreachable"}},
        )
    return JSONResponse(
        status_code=status_for(Outcome.SUCCESS),
        content={"status": "ready", "checks": {"database": "ok"}},
    )


# Legacy phase endpoints — honest 501s until the phases are actually wired up.
# The status flows through the single outcome→status mapping so this endpoint
# can never regress to a fabricated 2xx: NOT_IMPLEMENTED maps to 501 (a 5xx),
# which honestly reflects that the intake phase does not run yet (Requirement
# 2.1).
@internal.post("/intake", status_code=status_for(Outcome.NOT_IMPLEMENTED))
def intake(body: dict) -> dict:
    raise HTTPException(
        status_code=status_for(Outcome.NOT_IMPLEMENTED),
        detail="The intake phase is not yet implemented in the API.",
    )


# ─── Client portal publishing (CNA-0.90 §3: the publish story) ───────────────


class PublishRequest(BaseModel):
    engagement_id: str
    ttl_hours: int = 168  # AccessManager hard-caps at 7 days


def _slugify_filename(title: str, extension: str) -> str:
    safe = "".join(c if c.isalnum() or c in " -_" else "" for c in title)
    safe = "-".join(safe.lower().split())[:80] or "deliverable"
    return f"{safe}{extension}"


def _load_published_deliverables(engagement_id: str) -> list[dict]:
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, title, type, content, "blobPath", "updatedAt"
                   FROM "Deliverable"
                   WHERE "engagementId" = %s
                     AND "publishedAt" IS NOT NULL
                     AND status = 'COMPLETED'
                   ORDER BY "createdAt" ASC""",
                (engagement_id,),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]


def _load_latest_publication(engagement_id: str) -> dict | None:
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, "issuedAt", "expiresAt", "ttlHours",
                          "storageLocation", "deliverableCount"
                   FROM "PortalPublication"
                   WHERE "engagementId" = %s
                   ORDER BY "issuedAt" ASC LIMIT 1""",
                (engagement_id,),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def _record_publication(engagement_id: str, record: dict) -> None:
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO "PortalPublication"
                     (id, "engagementId", cloud, "storageLocation",
                      "deliverableCount", "ttlHours", "issuedAt", "expiresAt", "createdAt")
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())""",
                (
                    str(uuid.uuid4()),
                    engagement_id,
                    record["cloud"],
                    record["storage_location"],
                    record["deliverable_count"],
                    record["ttl_hours"],
                    record["issued_at"],
                    record["expires_at"],
                ),
            )
        conn.commit()


@internal.post("/publish")
def publish(request: PublishRequest) -> dict:
    """Publish the engagement's published deliverables to a client portal.

    Uploads them to a private per-engagement blob container, generates the
    portal index via cna.delivery_portal, and returns a TTL-capped SAS portal
    URL. The signed URL itself is never persisted (AccessManager's contract) —
    only the publication metadata is recorded, so the caller must surface the
    URL immediately. The cna-worker placeholder that once sketched this job is
    superseded by this endpoint.
    """
    if not DATABASE_URL:
        raise HTTPException(
            status_code=status_for(Outcome.NOT_CONFIGURED),
            detail="DATABASE_URL not configured",
        )
    account_name = os.environ.get("AZURE_STORAGE_ACCOUNT_NAME", "")
    if not account_name:
        raise HTTPException(
            status_code=status_for(Outcome.NOT_CONFIGURED),
            detail="AZURE_STORAGE_ACCOUNT_NAME is not configured on the API.",
        )

    engagement_id = request.engagement_id
    deliverables = _load_published_deliverables(engagement_id)
    if not deliverables:
        raise HTTPException(
            status_code=status_for(Outcome.CONFLICT),
            detail=(
                "No published deliverables for this engagement — publish at least one "
                "deliverable in the app before creating the client portal."
            ),
        )

    # Lazy: the delivery_portal stack needs azure-storage-blob, which older
    # API images may not carry.
    from cna.delivery_portal.access_manager import AccessManager
    from cna.delivery_portal.azure_blob_deployer import AzureBlobDeployer
    from cna.delivery_portal.portal_generator import PortalGenerator
    from cna.delivery_portal.retention_engine import RetentionEngine, RetentionExpiredError
    from cna.report_engine.deliverable_manifest import DeliverableManifest, DeliverableRecord

    # DD-019: the retention clock starts at the FIRST publication.
    first_publication = _load_latest_publication(engagement_id)
    delivery_date = (
        first_publication["issuedAt"].isoformat()
        if first_publication and first_publication.get("issuedAt")
        else None
    )
    try:
        RetentionEngine.check(engagement_id, delivery_date)
    except RetentionExpiredError as exc:
        raise HTTPException(status_code=status_for(Outcome.GONE), detail=str(exc)) from None

    try:
        import tempfile

        with tempfile.TemporaryDirectory(prefix="cna-portal-") as tmp:
            tmpdir = Path(tmp)
            manifest = DeliverableManifest(engagement_id=engagement_id)
            file_paths: list[Path] = []
            for row in deliverables:
                content = row.get("content")
                if not content:
                    # Blob-only deliverables would need a download leg; every
                    # current generator stores inline content, so skip and log
                    # rather than fail the whole publication.
                    logger.warning(
                        "publish: deliverable %s has no inline content — skipped", row["id"]
                    )
                    continue
                extension = ".html" if content.lstrip().startswith("<") else ".md"
                path = tmpdir / _slugify_filename(row["title"], extension)
                path.write_text(content, encoding="utf-8")
                file_paths.append(path)
                manifest.add(
                    DeliverableRecord(
                        label=row["title"],
                        path=str(path),
                        format=extension.lstrip("."),
                        lang="en",
                        rendered_at=(
                            row["updatedAt"].isoformat()
                            if row.get("updatedAt")
                            else datetime.now(UTC).isoformat()
                        ),
                    )
                )

            if not file_paths:
                raise HTTPException(
                    status_code=status_for(Outcome.CONFLICT),
                    detail="No publishable deliverable content found for this engagement.",
                )

            # Container per engagement: private, SAS-only, and deletable as a
            # unit when DD-019 retention expires. Engagement ids are cuids
            # (lowercase alphanumeric), which are valid container name parts.
            container = f"portal-{engagement_id.lower()}"[:63]
            deployer = AzureBlobDeployer(
                account_name=account_name,
                container_name=container,
                sas_ttl_hours=request.ttl_hours,
            )
            signed_urls = deployer.upload_all(file_paths)
            storage_location = f"https://{account_name}.blob.core.windows.net/{container}"

            access_record = AccessManager.build_record(
                engagement_id=engagement_id,
                cloud="azure",
                storage_location=storage_location,
                deliverable_count=len(file_paths),
                ttl_hours=request.ttl_hours,
            )

            entries = PortalGenerator.build_entries(
                manifest=manifest,
                signed_urls=signed_urls,
                current_findings_checksum="",
            )
            portal_path = tmpdir / "index.html"
            PortalGenerator().generate(
                manifest=manifest,
                entries=entries,
                published_at=access_record.issued_at,
                expires_at=access_record.expires_at,
                output_path=portal_path,
            )
            portal_blob = deployer.upload(portal_path)
            portal_url = deployer.generate_sas_token(portal_blob)

        _record_publication(
            engagement_id,
            {
                "cloud": "azure",
                "storage_location": storage_location,
                "deliverable_count": len(file_paths),
                "ttl_hours": access_record.ttl_hours,
                "issued_at": access_record.issued_at,
                "expires_at": access_record.expires_at,
            },
        )

        return {
            "ok": True,
            "portal_url": portal_url,
            "deliverable_count": len(file_paths),
            "issued_at": access_record.issued_at,
            "expires_at": access_record.expires_at,
        }
    except HTTPException:
        raise
    except Exception as exc:
        # Raw SDK detail is logged server-side; the caller gets a sanitized,
        # category-level message with no raw exception text (Requirement 2.3).
        sanitized = sanitize_downstream_error(
            exc, logger=logger, context=f"publish for engagement {engagement_id}"
        )
        raise HTTPException(
            status_code=status_for(sanitized.outcome),
            detail=sanitized.client_message,
        ) from None


class TestAccessRequest(BaseModel):
    tenant_id: str
    subscription_ids: list[str] = []


@internal.post("/discovery/test-access")
async def test_access(request: TestAccessRequest) -> dict:
    """Prove the process identity can read the requested subscriptions.

    Replaces ``/discovery/test-connection`` (REFACTOR_APP.md change set G): there is no
    client secret to validate. The appliance's user-assigned managed identity (or ``az
    login`` locally) lists the subscriptions it can see; the response names which of the
    requested ids are reachable and which are not, by id only.
    """
    try:
        from azure.mgmt.subscription import SubscriptionClient

        from cna.core.auth import build_azure_credential

        client = SubscriptionClient(build_azure_credential())
        visible = {
            s.subscription_id: s.display_name
            for s in client.subscriptions.list()
            if s.subscription_id
        }
        requested = [sid for sid in request.subscription_ids if sid]
        reachable = [sid for sid in requested if sid in visible] if requested else sorted(visible)
        missing = [sid for sid in requested if sid not in visible]
        return {
            "ok": not missing,
            "identity": "managed-identity",
            "subscriptions": [{"id": sid, "name": visible[sid]} for sid in reachable],
            "missing": missing,
        }
    except Exception as exc:
        # Raw Azure SDK detail is logged server-side; the caller gets a
        # sanitized, category-level message with no raw text (Requirement 2.3).
        sanitized = sanitize_downstream_error(
            exc, logger=logger, context=f"test-access for tenant {request.tenant_id}"
        )
        raise HTTPException(
            status_code=status_for(sanitized.outcome),
            detail=sanitized.client_message,
        ) from None


class AwsTestConnectionRequest(BaseModel):
    role_arn: str
    external_id: str | None = None
    access_key_id: str
    secret_access_key: str  # plaintext — decrypted by web layer


def _require_aws_installed() -> None:
    """``501 {"error": {"code": "aws_not_installed"}}`` when the ``[aws]`` extra is absent
    (change set K): the route exists, the deployment cannot serve it."""
    if not aws_extra_installed():
        raise HTTPException(
            status_code=status_for(Outcome.NOT_IMPLEMENTED),
            detail={"error": {"code": AWS_NOT_INSTALLED}},
        )


@internal.post("/discovery/test-connection-aws")
async def test_connection_aws(request: AwsTestConnectionRequest) -> dict:
    """Validate AWS keys and prove the CNA read-only role can be assumed."""
    _require_aws_installed()
    try:
        import boto3  # lazy: keeps Azure-only deployments importable without boto3

        session = boto3.Session(
            aws_access_key_id=request.access_key_id,
            aws_secret_access_key=request.secret_access_key,
        )
        sts = session.client("sts")
        identity = sts.get_caller_identity()
        kwargs: dict[str, Any] = {
            "RoleArn": request.role_arn,
            "RoleSessionName": "CNA-TestConnection",
            "DurationSeconds": 900,
        }
        if request.external_id:
            kwargs["ExternalId"] = request.external_id
        assumed = sts.assume_role(**kwargs)
        return {
            "ok": True,
            "caller_account": identity["Account"],
            "assumed_role_arn": assumed["AssumedRoleUser"]["Arn"],
        }
    except Exception as exc:
        # Raw AWS SDK detail is logged server-side; the caller gets a
        # sanitized, category-level message with no raw text (Requirement 2.3).
        sanitized = sanitize_downstream_error(
            exc, logger=logger, context=f"test-connection-aws for role {request.role_arn}"
        )
        raise HTTPException(
            status_code=status_for(sanitized.outcome),
            detail=sanitized.client_message,
        ) from None


class DiscoveryStartRequest(BaseModel):
    job_id: str
    engagement_id: str
    credential_id: str | None = None
    platform: str = "AZURE"  # "AZURE" | "AWS"
    # Azure
    tenant_id: str | None = None
    subscription_ids: list[str] = []
    # AWS
    aws_role_arn: str | None = None
    aws_external_id: str | None = None
    aws_regions: list[str] = []
    aws_access_key_id: str | None = None
    aws_secret_access_key: str | None = None  # plaintext — decrypted by web layer


@internal.post("/discovery/start")
async def start_discovery(
    request: DiscoveryStartRequest, background_tasks: BackgroundTasks
) -> dict:
    if request.platform.upper() == "AWS":
        _require_aws_installed()
        if not request.aws_role_arn:
            raise HTTPException(
                status_code=status_for(Outcome.INVALID_REQUEST),
                detail="aws_role_arn is required for AWS discovery",
            )
        if not request.aws_access_key_id or not request.aws_secret_access_key:
            raise HTTPException(
                status_code=status_for(Outcome.INVALID_REQUEST),
                detail="aws_access_key_id and aws_secret_access_key are required for AWS discovery",
            )
        _update_job(request.job_id, status="RUNNING", startedAt=datetime.now(UTC))
        background_tasks.add_task(_run_aws_discovery, request)
        return {"job_id": request.job_id, "status": "RUNNING"}

    if not request.tenant_id:
        raise HTTPException(
            status_code=status_for(Outcome.INVALID_REQUEST),
            detail="tenant_id is required",
        )
    _update_job(request.job_id, status="RUNNING", startedAt=datetime.now(UTC))
    background_tasks.add_task(_run_azure_discovery, request)
    return {"job_id": request.job_id, "status": "RUNNING"}


@internal.get("/discovery/jobs/{job_id}")
def get_job_status(job_id: str) -> dict:
    if not DATABASE_URL:
        raise HTTPException(
            status_code=status_for(Outcome.NOT_CONFIGURED),
            detail="DATABASE_URL not configured",
        )
    # Reap this job first if its heartbeat has gone stale, so the row read below
    # reflects the FAILED state rather than a RUNNING spinner forever (REL-001).
    _reap_stale_jobs(job_id)
    with _get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, status, "startedAt", "completedAt",
                          "findingsCount", "errorMessage", "progressLog", "updatedAt"
                   FROM "DiscoveryJob" WHERE id = %s""",
                (job_id,),
            )
            row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=status_for(Outcome.NOT_FOUND), detail="job not found")
    return dict(row)


# ─── Background discovery task ────────────────────────────────────────────────


# Every internal route above is registered; mount them once.
app.include_router(internal)


def _run_azure_discovery(request: DiscoveryStartRequest) -> None:
    job_id = request.job_id
    engagement_id = request.engagement_id
    progress: list[str] = []

    def _log(msg: str) -> None:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        entry = f"[{ts} UTC] {msg}"
        progress.append(entry)
        logger.info("[job:%s] %s", job_id, msg)
        _update_job(job_id, progressLog=json.dumps(progress))

    try:
        _log("Initialising discovery engine…")
        tmpdir = Path(mkdtemp(prefix="cna-discovery-"))
        store = EngagementStore(data_dir=tmpdir, engagement_id=engagement_id)

        options = AzureDiscoveryOptions(
            tenant_id=request.tenant_id,  # type: ignore[arg-type]
            subscription_ids=request.subscription_ids,
        )

        _log(f"Auth: platform identity (managed identity) | tenant {request.tenant_id}")
        if request.subscription_ids:
            sub_list = ", ".join(request.subscription_ids)
            _log(f"Targeting {len(request.subscription_ids)} subscription(s): {sub_list}")
        else:
            _log("No subscription filter — will discover all accessible subscriptions.")

        # Wire the discovery engine's internal progress into the job's progress log.
        discovery = AzureDiscovery(store, options, progress_callback=_log)

        _log("Running discovery — this may take a few minutes…")
        topology = discovery.run()

        _log(f"Scanned {len(topology.subscriptions)} subscription(s).")
        for sub_topo in topology.subscriptions:
            if sub_topo.discovery_blocked:
                _log(
                    f"  {sub_topo.subscription_name or sub_topo.subscription_id} "
                    "→ discovery blocked; no rules evaluated"
                )

        # One typed rule set for every Azure finding (the cna_azure_network_engine package):
        # pure evaluate(topology), rule ids on every finding, hedge check on every fact.
        _log(f"Evaluating {len(RULES)} Azure rules (rules {RULES_VERSION})…")

        def _rule_progress(_index: int, _total: int, sub_topo, sub_findings) -> None:
            if sub_topo.discovery_blocked:
                return
            _log(
                f"  {sub_topo.subscription_name or sub_topo.subscription_id} "
                f"→ {len(sub_findings)} finding(s)"
            )

        evaluation = evaluate_azure(topology, progress=_rule_progress)
        if evaluation.unknowns:
            _log(
                f"{len(evaluation.unknowns)} rule(s) could not be answered from this topology: "
                + ", ".join(u.rule_id for u in evaluation.unknowns)
            )
        all_findings: list[dict] = [finding_to_record(f) for f in evaluation.findings]

        # Tag ALL findings (existing + new) with a traffic-direction plane
        for f in all_findings:
            if not f.get("traffic_direction"):
                f["traffic_direction"] = classify_traffic_direction(
                    f.get("rule_id", ""),
                    f.get("category", ""),
                    f.get("resource_type", ""),
                )

        if not DATABASE_URL:
            logger.warning(
                "[job:%s] DATABASE_URL is not set — %d finding(s) will NOT be persisted.",
                job_id,
                len(all_findings),
            )
        _log(f"Writing {len(all_findings)} finding(s) to database…")
        _replace_discovery_findings(engagement_id, request.credential_id, all_findings)
        _advance_engagement_status(engagement_id)

        topology_json = topology.model_dump_json()
        _update_job(
            job_id,
            status="COMPLETED",
            completedAt=datetime.now(UTC),
            findingsCount=len(all_findings),
            topologyJson=topology_json,
            progressLog=json.dumps(progress + ["Done."]),
        )

        # Phase C: materialize stat-master records (best effort — never fail the job)
        try:
            count = rebuild_metrics(engagement_id)
            logger.info("[job:%s] rebuilt %d stat-master record(s)", job_id, count)
        except Exception:
            logger.exception("[job:%s] stat-master rebuild failed", job_id)

    except Exception as exc:
        # Raw exception text can embed tenant/client ids, AAD endpoints, DB host
        # or a plaintext secret; persist only the sanitized, category-level
        # message (PY-011). The full detail is logged server-side by the
        # sanitizer and the logger.exception above.
        sanitized = sanitize_downstream_error(
            exc, logger=logger, context=f"azure discovery job {job_id}"
        )
        logger.exception("[job:%s] discovery failed", job_id)
        _update_job(
            job_id,
            status="FAILED",
            errorMessage=sanitized.client_message,
            completedAt=datetime.now(UTC),
            progressLog=json.dumps(progress),
        )


def _run_aws_discovery(request: DiscoveryStartRequest) -> None:
    """AWS counterpart of _run_azure_discovery (CNA-0.90 §3: AWS end-to-end).

    Findings come from the cna package's AnalysisEngine AWS rules; the Azure
    path evaluates the typed rule registry instead. Both write through
    finding_to_record so every persisted finding carries its rule id.
    """
    job_id = request.job_id
    engagement_id = request.engagement_id
    progress: list[str] = []

    def _log(msg: str) -> None:
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        entry = f"[{ts} UTC] {msg}"
        progress.append(entry)
        logger.info("[job:%s] %s", job_id, msg)
        _update_job(job_id, progressLog=json.dumps(progress))

    try:
        # Lazy: keeps Azure-only deployments importable without boto3.
        from cna.ai_engine.analysis_engine import AnalysisEngine, AnalysisOptions
        from cna.modules.network.discovery.aws_discovery import (
            AWSDiscovery,
        )
        from cna.modules.network.discovery.aws_discovery import (
            DiscoveryOptions as AwsDiscoveryOptions,
        )

        _log("Initialising AWS discovery engine…")
        tmpdir = Path(mkdtemp(prefix="cna-discovery-"))
        store = EngagementStore(data_dir=tmpdir, engagement_id=engagement_id)

        options = AwsDiscoveryOptions(
            org_role_arn=request.aws_role_arn,  # type: ignore[arg-type]  # validated at the endpoint
            external_id=request.aws_external_id,
            regions=request.aws_regions,
            access_key_id=request.aws_access_key_id,
            secret_access_key=request.aws_secret_access_key,
        )

        _log(f"Role: {request.aws_role_arn}")
        if request.aws_regions:
            _log(
                f"Targeting {len(request.aws_regions)} region(s): {', '.join(request.aws_regions)}"
            )
        else:
            _log("No region filter — will discover all enabled regions.")

        discovery = AWSDiscovery(store, options)

        _log("Running discovery — this may take a few minutes…")
        topology = discovery.run()

        blocked = sum(1 for r in topology.regions if r.discovery_blocked)
        _log(
            f"Scanned {len(topology.regions)} region(s) across "
            f"{len(topology.accounts)} account(s)" + (f" — {blocked} blocked." if blocked else ".")
        )

        _log("Running analysis rules…")
        engine = AnalysisEngine(
            store=store,
            options=AnalysisOptions(load_aws=True, load_azure=False, dry_run=True),
        )
        report = engine.run(aws_topology=topology)
        all_findings = [finding_to_record(f) for f in report.findings]
        _log(f"Analysis → {len(all_findings)} finding(s).")

        # Tag findings with a traffic-direction plane (same as the Azure path)
        for f in all_findings:
            if not f.get("traffic_direction"):
                f["traffic_direction"] = classify_traffic_direction(
                    f.get("rule_id", ""),
                    f.get("category", ""),
                    f.get("resource_type", ""),
                )

        if not DATABASE_URL:
            logger.warning(
                "[job:%s] DATABASE_URL is not set — %d finding(s) will NOT be persisted.",
                job_id,
                len(all_findings),
            )
        _log(f"Writing {len(all_findings)} finding(s) to database…")
        _replace_discovery_findings(engagement_id, request.credential_id, all_findings)
        _advance_engagement_status(engagement_id)

        _update_job(
            job_id,
            status="COMPLETED",
            completedAt=datetime.now(UTC),
            findingsCount=len(all_findings),
            topologyJson=topology.model_dump_json(),
            progressLog=json.dumps(progress + ["Done."]),
        )

    except Exception as exc:
        # Sanitize before persisting — raw boto3/psycopg2 text can carry ARNs,
        # endpoints, or a plaintext secret into DiscoveryJob.errorMessage (PY-011).
        sanitized = sanitize_downstream_error(
            exc, logger=logger, context=f"aws discovery job {job_id}"
        )
        logger.exception("[job:%s] AWS discovery failed", job_id)
        _update_job(
            job_id,
            status="FAILED",
            errorMessage=sanitized.client_message,
            completedAt=datetime.now(UTC),
            progressLog=json.dumps(progress),
        )
