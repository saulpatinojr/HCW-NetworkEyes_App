"""CNA platform exception taxonomy.

Closes TODO_PhaseA: No Error Taxonomy.

Every exception type maps to a distinct handling behavior:
  - CNAAuthError          : stop, surface to operator, do not retry
  - CNAPermissionError    : log to coverage report, continue to next resource
  - CNARateLimitError     : exponential backoff, retry up to MAX_RETRIES
  - CNANetworkError       : retry with backoff, mark resource as uncertain if exceeded
  - CNAMalformedResponse  : log, skip resource, flag data_confidence=LOW
  - CNAPartialResult      : log, continue, flag coverage as partial
  - CNAServiceUnavailable : log to coverage report, continue to next service
  - EngagementLockError   : stop, surface to operator, do not proceed
  - EngagementNotFoundError: stop, surface to operator
  - DiagramGenerationError: log, skip diagram, do not fail entire engagement
  - ExportPipelineError   : log, skip format (e.g. skip .pdf, still write .drawio)
  - ReviewGateError       : stop, block report generation (DD-009 enforcement)
"""

from __future__ import annotations


class CNABaseError(Exception):
    """Base for all CNA errors. Carries an optional remediation hint."""

    def __init__(self, message: str, remediation: str = ""):
        super().__init__(message)
        self.remediation = remediation


# ── Discovery errors ───────────────────────────────────────────────────


class CNAAuthError(CNABaseError):
    """Authentication failed. Cannot assume role / SP login failed.
    Handling: STOP. Surface to operator. Do not retry.
    """


class CNAPermissionError(CNABaseError):
    """API call denied (AccessDenied / AuthorizationFailed).
    Handling: LOG to coverage report. Continue to next resource/service.
    Caller must append to DiscoveryCoverageReport.block_reasons.
    """

    def __init__(self, message: str, service: str = "", action: str = "", resource: str = ""):
        super().__init__(
            message, remediation=f"Grant {action} on {resource or 'scope'} in {service}"
        )
        self.service = service
        self.action = action
        self.resource = resource


class CNARateLimitError(CNABaseError):
    """API rate limit hit (ThrottlingException / TooManyRequests).
    Handling: Exponential backoff. Retry up to MAX_RETRIES (default: 5).
    Use tenacity @retry decorator with wait_exponential.
    """

    def __init__(self, message: str, retry_after_seconds: float = 0.0):
        super().__init__(message, remediation="Wait and retry. Reduce --concurrency if persistent.")
        self.retry_after_seconds = retry_after_seconds


class CNANetworkError(CNABaseError):
    """Transient network failure (timeout, connection reset).
    Handling: Retry with backoff. If MAX_RETRIES exceeded, mark resource uncertain.
    """


class CNAMalformedResponse(CNABaseError):
    """API returned unexpected/unparseable response shape.
    Handling: LOG. Skip resource. Set data_confidence=LOW on affected finding.
    """

    def __init__(self, message: str, raw_response: str = ""):
        super().__init__(message)
        self.raw_response = raw_response[:500]  # truncate for safety


class CNAPartialResult(CNABaseError):
    """Pagination incomplete or result set truncated by API.
    Handling: LOG. Continue. Flag coverage as partial for affected account/region.
    """


class CNAServiceUnavailable(CNABaseError):
    """Service not available in this region/account.
    Handling: LOG to coverage report. Continue to next service.
    This is normal — not all services are available in all regions.
    """

    def __init__(self, message: str, service: str = "", region: str = ""):
        super().__init__(message)
        self.service = service
        self.region = region


# ── Engagement errors ──────────────────────────────────────────────────


class EngagementNotFoundError(CNABaseError):
    """Engagement ID not found in data store."""


class EngagementLockError(CNABaseError):
    """Engagement is locked by another process."""


class ReviewGateError(CNABaseError):
    """Report generation attempted without human review sign-off.
    DD-009 enforcement: this exception is raised by report_engine before
    generating any output if engagement.review_complete is False.
    Handling: STOP. Block report. Surface to operator with remediation.
    """

    def __init__(self, engagement_id: str):
        super().__init__(
            f"Report generation blocked for '{engagement_id}': human review not complete.",
            remediation="Run `cna review --approve-all` or review individual findings first.",
        )


# ── Diagram / export errors ───────────────────────────────────────────────


class DiagramGenerationError(CNABaseError):
    """Diagram generation failed for a specific topology input.
    Handling: LOG. Skip this diagram. Do not fail the entire engagement.
    """


class ExportPipelineError(CNABaseError):
    """A specific export format failed (e.g., .pdf conversion).
    Handling: LOG. Skip that format. Other formats already written are preserved.
    """


# ── Module errors ─────────────────────────────────────────────────────────


class ModuleDependencyError(CNABaseError):
    """Module invoked before its declared depends_on modules have run.
    Closes TODO_PhaseA: Module depends_on not enforced.
    Handling: STOP. Surface to operator. Do not proceed.
    """

    def __init__(self, module: str, missing_dependency: str):
        super().__init__(
            f"Module '{module}' requires '{missing_dependency}' to have completed discovery first.",
            remediation=f"Run `cna discover` and ensure '{missing_dependency}' completes before '{module}'.",
        )
