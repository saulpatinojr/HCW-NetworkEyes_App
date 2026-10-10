"""Findings for the ``security-secrets`` area (Requirement 6).

This is the *verify-then-close-gaps* record for the security-and-secrets audit:
the ``detect-secrets`` / ``gitleaks`` secret scans and the ``pip-audit`` /
``npm audit`` dependency scans across the repository and its manifests, plus
the scan results recorded for the core repository.

Every finding below records a scan result by **location and key name only** —
never a secret value (Requirement 6.2, Property 12). The secret detections are
described by file path and detector *type* (the "key name" class the detector
assigns, e.g. ``Secret Keyword``, ``Basic Auth Credentials``); the underlying
secret material is never reproduced here or in any downstream output.

Scans performed (design "6. Security & secrets"):

  * **detect-secrets** (``scan --baseline .secrets.baseline``). The committed
    baseline records **21 detections across 12 in-project files** — every one
    marked ``is_verified: false``, i.e. baselined/accepted as a known-safe test
    or example placeholder rather than a live credential. Requirement 6.2 was
    *tightened* to require a remediation entry for **all** detections regardless
    of context — including false positives and known-safe test secrets — so each
    baselined location is recorded here by location + detector type, never value.
    One record additionally captures the baseline drift observed during the scan
    (the live scan surfaces the skill-library reference trees under
    ``.agents/``, ``.claude/``, ``.codex/``, ``.deployment-catalog/`` that the
    committed baseline does not carry).
  * **gitleaks** (``gitleaks detect``). The ``gitleaks`` binary is a Go
    executable not installable through the project's Python dev dependencies and
    was **not available** in the environment, so its scan could not be executed.
    Recorded as a coverage gap (design "Error Handling": a missing tool is
    recorded as a gap, not passed silently).
  * **pip-audit**. Reported **no known vulnerabilities** across the audited
    Python environment. Recorded as a verified-compliant (``INFORMATIONAL``)
    outcome.
  * **npm audit** (``--prefix apps/cna-web``). Reported **four** advisories: a
    critical ``next`` unauthenticated-RCE class, high-severity ``browserslist``
    and ``sharp``, and a moderate ``baseline-browser-mapping`` DoS. Each is
    recorded as its own finding at its reported severity (Requirement 6.3).

The R-006 runtime-secret escalation (Requirement 6.4) this area used to record
left the core with the AWS Terraform whose ``sensitive``-with-no-default inputs
it described (``TODO.md`` T-504); the AWS appliance's ``REVIEW.md`` owns it. No
finding here carries a ``blocker_id``. These records are consumed by the
consolidation step (spec task 14.1).
"""

from __future__ import annotations

from cna.review.model import Finding, Severity

_AREA = "security-secrets"

# The 12 in-project files carrying baselined detect-secrets detections, each
# paired with the detector *type(s)* it flagged and the number of detections.
# Location + key-name only — no secret value is reproduced (Requirement 6.2,
# Property 12). Types are the detector's own classification, e.g. a "Secret
# Keyword" or "Basic Auth Credentials" hit; the material behind each hit stays
# in the file and is never copied here.
_BASELINED_SECRET_LOCATIONS: tuple[tuple[str, str, int], ...] = (
    (".env.example", "Basic Auth Credentials", 1),
    (".github/workflows/200-build-images.yml", "Basic Auth Credentials", 1),
    ("TODO.md", "Secret Keyword", 1),
    ("apps/cna-web/.env.example", "Basic Auth Credentials + Secret Keyword", 3),
    ("apps/cna-web/app/api/local-admin/route.ts", "Secret Keyword", 1),
    ("tests/unit/test_api_errors_properties.py", "AWS Access Key + Basic Auth Credentials", 2),
    ("tests/unit/test_auth.py", "Secret Keyword", 3),
    ("tests/unit/test_aws_discovery.py", "Secret Keyword", 3),
    ("tests/unit/test_azure_discovery.py", "Secret Keyword", 1),
    ("tests/unit/test_cna_api_error_paths.py", "Secret Keyword", 2),
    ("tests/unit/test_review_area_cicd_shapin.py", "Hex High Entropy String", 1),
    ("tests/unit/test_review_sha_pin_properties.py", "Hex High Entropy String", 2),
)


def secret_location_finding(path: str, detector_type: str, count: int = 1) -> Finding:
    """Build a committed-secret ``Finding`` from a location and detector type only.

    This is the pure per-location builder for a detect-secrets detection. It
    takes **only** the file ``path`` and the detector's key-name ``detector_type``
    (plus the detection ``count``) — it has **no parameter for the secret value**,
    so by construction the recorded finding names the location and key name but
    can never reproduce the raw secret material (Requirement 6.2, Property 12).

    Every entry is ``LOW`` (detect-secrets detections in this review are baselined
    ``is_verified: false`` — accepted known-safe placeholders, not live
    credentials).
    """
    plural = "detection" if count == 1 else "detections"
    return Finding(
        area=_AREA,
        severity=Severity.LOW,
        proposed_action=(
            f"detect-secrets flagged {count} baselined {plural} "
            f"({detector_type}) at {path}. Confirm each is a known-safe "
            "test/example placeholder (all are baselined "
            "is_verified=false, not live credentials); keep it in "
            ".secrets.baseline with an audited annotation. Recorded by "
            "location and key-name type only — the secret value is never "
            "reproduced."
        ),
        dedup_key=f"security-secrets:detect-secrets:{path}",
        subject=path,
    )


def _secret_location_findings() -> list[Finding]:
    """One finding per baselined detect-secrets location (location + type only).

    Requirement 6.2 (tightened) requires a remediation entry for **every**
    detection regardless of context — including baselined known-safe test/example
    secrets — so each of the 12 in-project locations is recorded via the pure
    :func:`secret_location_finding` builder, which never takes a secret value
    (Property 12).
    """
    return [
        secret_location_finding(path, detector_type, count)
        for path, detector_type, count in _BASELINED_SECRET_LOCATIONS
    ]


def security_secrets_findings() -> list[Finding]:
    """Return the Requirement 6 findings recorded for the security-secrets area.

    Covers the four scans. No finding
    reproduces a secret value: committed-secret detections are identified by
    location and detector key-name type only (Requirement 6.2, Property 12).
    """
    findings: list[Finding] = []

    # 6.1 / 6.2 — one entry per baselined detect-secrets location (location +
    # key-name type only, all detections regardless of context).
    findings.extend(_secret_location_findings())

    # 6.1 / 6.2 — detect-secrets baseline drift observed during the scan: the
    # live scan surfaces the vendored skill-library reference trees the committed
    # baseline does not carry. Recorded so the plan captures the coverage delta
    # without reproducing any value.
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "detect-secrets scan surfaces additional detections in the "
                "vendored skill-library reference trees (.agents/, .claude/, "
                ".codex/, .deployment-catalog/) that the committed "
                ".secrets.baseline does not carry. Either add these paths to the "
                "detect-secrets should_exclude_file filter (they are third-party "
                "documentation fixtures, not project secrets) or re-audit and "
                "re-baseline them. Recorded by location class only — no value "
                "reproduced."
            ),
            dedup_key="security-secrets:detect-secrets:baseline-drift-skill-libraries",
            subject=".secrets.baseline",
        )
    )

    # 6.1 — gitleaks could not run: the Go binary is not installable via the
    # project's Python dev dependencies and was absent from the environment.
    # Recorded as a coverage gap (a missing tool is a gap, not a silent pass).
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "gitleaks detect could not be executed: the gitleaks binary "
                "(Go, not a Python dev dependency) was unavailable in the "
                "environment. Provision gitleaks in the review/CI toolchain so "
                "the second independent secret scan can run alongside "
                "detect-secrets. Coverage gap — no secret scanning result from "
                "gitleaks was produced."
            ),
            dedup_key="security-secrets:gitleaks:tool-unavailable",
            subject="gitleaks detect",
        )
    )

    # 6.3 — pip-audit: verified compliant (no known vulnerabilities).
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant: pip-audit reported no known vulnerabilities "
                "across the audited Python dependencies. Keep pip-audit in the "
                "quality gate so a newly disclosed advisory is caught."
            ),
            dedup_key="security-secrets:pip-audit:clean",
            subject="pip-audit",
        )
    )

    # 6.3 — npm audit: one finding per reported advisory at its reported severity.
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.CRITICAL,
            proposed_action=(
                "npm audit reports a CRITICAL advisory for 'next' "
                "(16.0.0 - 16.3.2): unauthenticated remote code execution on "
                "Windows-hosted servers and in the Image Optimization API for "
                "AVIF inputs. Upgrade next to >= 16.3.5 (fix available) in "
                "apps/cna-web."
            ),
            dedup_key="security-secrets:npm-audit:next",
            subject="apps/cna-web (next)",
        )
    )
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.HIGH,
            proposed_action=(
                "npm audit reports a HIGH advisory for 'browserslist' "
                "(<= 4.28.6): unbounded memory growth (OOM) via distinct query "
                "results and an uncaught crash / prototype write via untrusted "
                "browserslist-stats.json. Upgrade browserslist (fix available) "
                "in apps/cna-web."
            ),
            dedup_key="security-secrets:npm-audit:browserslist",
            subject="apps/cna-web (browserslist)",
        )
    )
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.HIGH,
            proposed_action=(
                "npm audit reports a HIGH advisory for 'sharp' (< 0.35.4): "
                "libheif vulnerabilities (GHSA-g89c-p67h-r497, "
                "GHSA-2jg2-4ch7-h545). Upgrade sharp to >= 0.35.4 (fix "
                "available) in apps/cna-web."
            ),
            dedup_key="security-secrets:npm-audit:sharp",
            subject="apps/cna-web (sharp)",
        )
    )
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "npm audit reports a MODERATE advisory for "
                "'baseline-browser-mapping' (>= 2.0.0 < 2.11.0): process "
                "termination on invalid input (denial of service). Upgrade "
                "baseline-browser-mapping (fix available) in apps/cna-web."
            ),
            dedup_key="security-secrets:npm-audit:baseline-browser-mapping",
            subject="apps/cna-web (baseline-browser-mapping)",
        )
    )

    # 6.4 — the runtime-secret escalation (R-006) left the core with the AWS
    # Terraform whose variables it described (TODO.md T-504); the AWS
    # appliance's REVIEW.md owns it (R-008 there).

    return findings
