"""Per-area finding emitters for the production-hardening review.

Each module under this package is one owner area's reviewer: it encodes the
``Finding`` records that area's audit produced (residual gaps, plus the
verified-compliant outcomes recorded as ``INFORMATIONAL`` findings so the
consolidated plan reflects what was checked, not only what broke). The
consolidation step (spec task 14.1) collects every area's findings and folds
them into the single ``Remediation_Plan``.
"""

from cna.review.areas.app_typescript import app_typescript_findings
from cna.review.areas.app_typescript_verify import app_typescript_verify_findings
from cna.review.areas.cicd import cicd_findings, cicd_verify_findings
from cna.review.areas.cicd_shapin import (
    cicd_sha_and_escalation_findings,
    find_unpinned_references,
    is_sha_pinned,
    is_third_party_action,
    scan_uses_references,
    sha_pin_findings,
)
from cna.review.areas.containers_packaging import (
    RootUserFindingError,
    VerificationResults,
    containers_packaging_findings,
    containers_packaging_verify_findings,
    effective_final_user,
    is_root_user,
    record_root_user_finding,
)
from cna.review.areas.documentation import (
    documentation_findings,
    documentation_verify_findings,
)
from cna.review.areas.observability import observability_findings
from cna.review.areas.python_engine_api import python_engine_api_findings
from cna.review.areas.python_engine_api_verify import python_engine_api_verify_findings
from cna.review.areas.security_secrets import security_secrets_findings
from cna.review.areas.terraform_relocated import terraform_relocated_findings

__all__ = [
    "RootUserFindingError",
    "VerificationResults",
    "app_typescript_findings",
    "app_typescript_verify_findings",
    "cicd_findings",
    "cicd_sha_and_escalation_findings",
    "cicd_verify_findings",
    "containers_packaging_findings",
    "containers_packaging_verify_findings",
    "documentation_findings",
    "documentation_verify_findings",
    "effective_final_user",
    "find_unpinned_references",
    "is_root_user",
    "is_sha_pinned",
    "is_third_party_action",
    "observability_findings",
    "python_engine_api_findings",
    "python_engine_api_verify_findings",
    "record_root_user_finding",
    "scan_uses_references",
    "security_secrets_findings",
    "sha_pin_findings",
    "terraform_relocated_findings",
]
