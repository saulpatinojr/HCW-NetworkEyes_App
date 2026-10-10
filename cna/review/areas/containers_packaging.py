"""Findings for the ``containers-packaging`` area (Requirement 7).

This is a *verify-then-close-gaps* record for the four service Dockerfiles
(root ``Dockerfile``, ``apps/cna-api``, ``apps/cna-web``, ``apps/cna-worker``),
``docker-compose.yml``, and the ``cna`` CLI packaging. The audit against
Requirement 7 confirmed:

  * **7.4 — non-root final ``USER`` (verified compliant).** Every service
    Dockerfile ends on a non-root user (``cna`` uid/gid 1001 for the Python
    images, ``nextjs`` uid 1001 for the web image). :func:`effective_final_user`
    parses each Dockerfile's effective final ``USER`` and
    :func:`record_root_user_finding` decides whether a non-root remediation
    finding is required. None is (Property 15's negative case), so an
    ``INFORMATIONAL`` verified-compliant finding is recorded per image to guard
    against regression to a root/unset ``USER``.
  * **7.2 — docker-compose Web_Service fallback (gap closed here).** The
    committed ``docker-compose.yml`` only defined the Python ``cna`` CLI
    services (``cna``, ``cna-dev``, ``cna-test``); there was no fallback path to
    run the Web_Service (``apps/cna-web``) locally. A ``cna-web`` service was
    added to the compose file and a ``MEDIUM`` finding records the gap that was
    closed.
  * **7.1 — container best practices (gaps closed here).** The root
    ``Dockerfile`` already carries a ``HEALTHCHECK``; the ``cna-api``,
    ``cna-worker``, and ``cna-web`` images did not. Healthchecks were added to
    each and a ``LOW`` finding records the residual best-practice gap.

**Fail-hard on an unrecordable root-user finding (7.5).**
:func:`record_root_user_finding` is the mandatory recording operation: if it
cannot persist a root-user finding it raises :class:`RootUserFindingError`
rather than returning silently, so the review process fails as a whole instead
of continuing with an unrecorded root-user security finding. The sink is
injectable so the caller (and the property test) can exercise the failure path.

These records are consumed by the consolidation step (spec task 14.1).
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from cna.review.model import Finding, Severity

_AREA = "containers-packaging"

# The owning REVIEW.md blocker for runtime secrets supplied at deploy time. A
# private image pull needing registry credentials is a runtime-secret dependency
# and references R-006. The R-006 Escalation_Record itself is owned by spec task
# 10.1 (Security & secrets); this area only *notes* the reference in its
# verification record so no duplicate escalation is emitted here.
_R006 = "R-006"

# The four service Dockerfiles this area owns, keyed by the subject label used
# on the recorded findings. Paths are repo-relative.
SERVICE_DOCKERFILES: dict[str, str] = {
    "Dockerfile": "Dockerfile",
    "apps/cna-api/Dockerfile": "apps/cna-api/Dockerfile",
    "apps/cna-web/Dockerfile": "apps/cna-web/Dockerfile",
    "apps/cna-worker/Dockerfile": "apps/cna-worker/Dockerfile",
}

# A ``USER`` whose resolved name/uid is one of these is the root account. An
# unset final ``USER`` also counts as root (the container default).
_ROOT_USER_NAMES = frozenset({"root", "0"})

_USER_RE = re.compile(r"^\s*USER\s+(?P<spec>\S+)", re.IGNORECASE)
_ARG_RE = re.compile(r"^\s*ARG\s+(?P<name>\w+)(?:=(?P<default>\S+))?", re.IGNORECASE)
_ENV_RE = re.compile(r"^\s*ENV\s+(?P<name>\w+)[=\s]+(?P<value>\S+)", re.IGNORECASE)


class RootUserFindingError(RuntimeError):
    """Raised when a mandatory root-user finding cannot be recorded (7.5).

    Recording a root-user security finding is treated as a fail-hard operation:
    if the sink cannot persist it, the review process aborts rather than
    proceeding with the finding unrecorded.
    """


def effective_final_user(dockerfile_text: str) -> str | None:
    """Return the effective final ``USER`` of a single-image Dockerfile.

    The *last* ``USER`` instruction wins (later stages/instructions override
    earlier ones). ``ARG``/``ENV`` values defined in the file are substituted
    into a ``USER ${VAR}`` reference so an image that parameterises its user is
    resolved rather than mis-flagged. If no ``USER`` instruction is present the
    image runs as root by default, represented as ``None``.

    Only the final build stage's ``USER`` matters for the shipped image, but a
    Dockerfile's final ``USER`` line is always the effective one because a later
    ``FROM`` resets it and would be followed by its own ``USER`` — so scanning
    for the last ``USER`` in file order is correct for these single-image
    Dockerfiles and robust to multi-stage builds.

    :returns: the resolved user token (name or uid) of the final ``USER``, or
        ``None`` when no ``USER`` is set (root by default).
    """
    args: dict[str, str] = {}
    last_user: str | None = None
    for raw in dockerfile_text.splitlines():
        arg_match = _ARG_RE.match(raw)
        if arg_match and arg_match.group("default") is not None:
            args[arg_match.group("name")] = arg_match.group("default")
            continue
        env_match = _ENV_RE.match(raw)
        if env_match:
            args[env_match.group("name")] = env_match.group("value")
            continue
        user_match = _USER_RE.match(raw)
        if user_match:
            last_user = user_match.group("spec")

    if last_user is None:
        return None
    return _resolve(last_user, args)


def _resolve(spec: str, args: dict[str, str]) -> str:
    """Substitute ``${VAR}``/``$VAR`` references, then take the user (drop group).

    A ``USER`` spec may be ``name``, ``uid``, ``name:group`` or ``uid:gid``; the
    user portion (before the colon) is what determines root-ness.
    """

    def _sub(match: re.Match[str]) -> str:
        name = match.group(1) or match.group(2)
        return args.get(name, match.group(0))

    resolved = re.sub(r"\$\{(\w+)\}|\$(\w+)", _sub, spec)
    return resolved.split(":", 1)[0]


def is_root_user(user: str | None) -> bool:
    """True when an effective final ``USER`` is the root account or unset."""
    if user is None:
        return True
    return user.strip().lower() in _ROOT_USER_NAMES


def _root_user_finding(subject: str) -> Finding:
    """Build the non-root remediation finding for a root/unset image (7.4)."""
    return Finding(
        area=_AREA,
        severity=Severity.HIGH,
        proposed_action=(
            f"{subject} runs its process as root (final USER is root or unset). "
            "Add a dedicated non-root user (uid/gid 1001, matching the other "
            "service images) and end the final stage on USER <non-root> so the "
            "container process does not run as root."
        ),
        dedup_key=f"containers-packaging:root-user:{subject}",
        subject=subject,
    )


def record_root_user_finding(
    subject: str,
    user: str | None,
    sink: Callable[[Finding], None],
) -> Finding | None:
    """Record a root-user finding for ``subject`` if it runs as root (7.4, 7.5).

    When the effective final ``user`` is root or unset, a non-root remediation
    :class:`Finding` is built and handed to ``sink`` to persist. Recording is
    **mandatory**: if ``sink`` raises, this function re-raises as
    :class:`RootUserFindingError` so the review process fails as a whole rather
    than continuing with the root-user finding unrecorded (Requirement 7.5).

    When the image already runs non-root, no finding is required and ``None`` is
    returned (Property 15's negative case) — the caller records a
    verified-compliant informational finding separately.

    :param subject: the Dockerfile the finding is about.
    :param user: the effective final ``USER`` as returned by
        :func:`effective_final_user` (``None`` ⇒ unset ⇒ root).
    :param sink: the persistence callback; raising signals a recording failure.
    :returns: the recorded root-user :class:`Finding`, or ``None`` when the
        image is already non-root.
    :raises RootUserFindingError: if ``sink`` fails to persist the finding.
    """
    if not is_root_user(user):
        return None
    finding = _root_user_finding(subject)
    try:
        sink(finding)
    except Exception as exc:  # noqa: BLE001 — fail-hard: escalate any sink failure
        raise RootUserFindingError(
            f"failed to record mandatory root-user finding for {subject!r}; "
            "aborting the review process (Requirement 7.5)"
        ) from exc
    return finding


@dataclass
class _DockerfileAudit:
    """The parsed facts an image contributes to the recorded findings."""

    subject: str
    user: str | None

    @property
    def runs_as_root(self) -> bool:
        return is_root_user(self.user)


def _audit_dockerfiles() -> list[_DockerfileAudit]:
    """The audited effective-USER result for each service Dockerfile.

    The results are the values observed during task 11.1's audit and are the
    inputs the recorded findings below reflect. Every image resolved to a
    non-root final ``USER``:

      * ``Dockerfile`` → ``cna``      (uid/gid 1001)
      * ``apps/cna-api/Dockerfile`` → ``cna``  (uid/gid 1001)
      * ``apps/cna-web/Dockerfile`` → ``nextjs`` (uid 1001)
      * ``apps/cna-worker/Dockerfile`` → ``cna`` (uid/gid 1001)
    """
    audited = {
        "Dockerfile": "cna",
        "apps/cna-api/Dockerfile": "cna",
        "apps/cna-web/Dockerfile": "nextjs",
        "apps/cna-worker/Dockerfile": "cna",
    }
    return [_DockerfileAudit(subject=subject, user=user) for subject, user in audited.items()]


def containers_packaging_findings(
    sink: Callable[[Finding], None] | None = None,
) -> list[Finding]:
    """Return the Requirement 7 findings recorded for this area.

    The root-user check runs through :func:`record_root_user_finding` so the
    fail-hard contract (7.5) is exercised on the same path the audit uses. A
    default in-memory ``sink`` collects the (currently empty) set of root-user
    findings; a caller may pass its own sink to persist elsewhere, and a failing
    sink aborts via :class:`RootUserFindingError`.
    """
    collected: list[Finding] = []
    if sink is None:
        sink = collected.append

    findings: list[Finding] = []

    # 7.4 / 7.5 — non-root audit per image, recorded via the mandatory path.
    for audit in _audit_dockerfiles():
        root_finding = record_root_user_finding(audit.subject, audit.user, sink)
        if root_finding is not None:
            findings.append(root_finding)
        else:
            findings.append(
                Finding(
                    area=_AREA,
                    severity=Severity.INFORMATIONAL,
                    proposed_action=(
                        f"Verified compliant: {audit.subject} ends on a non-root "
                        f"final USER ({audit.user}, uid/gid 1001). Keep the final "
                        "stage on a non-root user so the image cannot regress to "
                        "running as root."
                    ),
                    dedup_key=f"containers-packaging:non-root-verified:{audit.subject}",
                    subject=audit.subject,
                )
            )

    # Any root-user findings collected by the default sink are already in
    # ``findings`` above; guard the invariant that the two paths agree.
    if sink is collected.append:
        assert all(f in findings for f in collected)

    # 7.2 — docker-compose Web_Service fallback (gap closed by adding cna-web).
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.MEDIUM,
            proposed_action=(
                "docker-compose.yml had no fallback path to run the Web_Service "
                "(apps/cna-web) locally — only the Python cna CLI services were "
                "defined. Add a cna-web service that builds apps/cna-web so the "
                "local stack can run the web front end without the cloud."
            ),
            dedup_key="containers-packaging:compose-web-fallback",
            subject="docker-compose.yml",
        )
    )

    # 7.1 — HEALTHCHECK best-practice gap on the non-root service images.
    findings.append(
        Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "The root Dockerfile carries a HEALTHCHECK but the cna-api, "
                "cna-web, and cna-worker images did not. Add a HEALTHCHECK to "
                "each so orchestrators (ECS/AKS/Container Apps) can detect an "
                "unhealthy container."
            ),
            dedup_key="containers-packaging:service-healthchecks",
            subject="apps/cna-api/Dockerfile,apps/cna-web/Dockerfile,apps/cna-worker/Dockerfile",
        )
    )

    return findings


# ── verification records (spec task 11.3) ────────────────────────────────────


@dataclass(frozen=True)
class VerificationResults:
    """The observed outcomes of the container/packaging verification sweep.

    These are the facts task 11.3 gathered so the recorded findings reflect what
    actually ran in this environment rather than an assumed pass. A ``None``
    tool-availability flag or a ``False`` outcome is recorded as a coverage-gap
    finding rather than a silent pass (design "Error Handling": a missing tool is
    a gap in coverage, not a pass).

    :param wheel_build_ok: the wheel built (``pip wheel``/``python -m build``).
    :param clean_install_ok: the wheel installed into a *clean* virtualenv.
    :param cli_help_ok: ``cna --help`` ran from that install with exit code 0.
    :param docker_available: whether a working Docker daemon was reachable.
    :param docker_build_ok: per-image ``docker build`` outcome, keyed by the
        subject Dockerfile; a subject present with ``True`` built, ``False``
        failed, and an absent subject was not attempted.
    :param inspected_users: the runtime ``USER`` observed on each *built* image
        via ``docker inspect`` (empty when Docker was unavailable).
    :param hadolint_available: whether ``hadolint`` was on PATH.
    """

    wheel_build_ok: bool
    clean_install_ok: bool
    cli_help_ok: bool
    docker_available: bool
    docker_build_ok: Mapping[str, bool]
    inspected_users: Mapping[str, str | None]
    hadolint_available: bool


# The results observed during this task's run (Windows, Docker Engine 29.7.x,
# Python 3.14). The wheel built with ``pip wheel``, installed into a clean venv,
# and ``cna --help`` ran (exit 0). All four images built and each inspected
# image ran as its non-root user. ``hadolint`` was not installed, so its step is
# recorded as a coverage gap rather than a pass.
_OBSERVED = VerificationResults(
    wheel_build_ok=True,
    clean_install_ok=True,
    cli_help_ok=True,
    docker_available=True,
    docker_build_ok={
        "Dockerfile": True,
        "apps/cna-api/Dockerfile": True,
        "apps/cna-web/Dockerfile": True,
        "apps/cna-worker/Dockerfile": True,
    },
    inspected_users={
        "Dockerfile": "cna",
        "apps/cna-api/Dockerfile": "cna",
        "apps/cna-web/Dockerfile": "nextjs",
        "apps/cna-worker/Dockerfile": "cna",
    },
    hadolint_available=False,
)


def _packaging_finding(results: VerificationResults) -> Finding:
    """7.3 — wheel build + clean-venv install + ``cna --help`` (verified/gap)."""
    passed = results.wheel_build_ok and results.clean_install_ok and results.cli_help_ok
    if passed:
        return Finding(
            area=_AREA,
            severity=Severity.INFORMATIONAL,
            proposed_action=(
                "Verified compliant (7.3): the cna wheel builds, installs into a "
                "clean virtualenv, and `cna --help` runs from that install with "
                "exit code 0 (the CLI entry point cna = cna.cli.main:cli resolves "
                "from the packaged distribution). Re-run this packaging check on "
                "every evaluation of the Core_Engine package and guard against a "
                "regression in the entry point or wheel metadata."
            ),
            dedup_key="containers-packaging:cli-packaging-verified",
            subject="pyproject.toml::cna",
        )
    steps = []
    if not results.wheel_build_ok:
        steps.append("wheel build")
    if not results.clean_install_ok:
        steps.append("clean-venv install")
    if not results.cli_help_ok:
        steps.append("cna --help")
    return Finding(
        area=_AREA,
        severity=Severity.HIGH,
        proposed_action=(
            "CLI packaging check (7.3) did not pass: "
            f"{', '.join(steps)} failed. Build the wheel, install it into a clean "
            "virtualenv, and confirm `cna --help` runs from the packaged "
            "distribution; fix the entry point / wheel metadata so it does."
        ),
        dedup_key="containers-packaging:cli-packaging-gap",
        subject="pyproject.toml::cna",
    )


def _docker_build_finding(results: VerificationResults) -> Finding:
    """7.1 — ``docker build`` per image (verified, coverage gap, or failure)."""
    if not results.docker_available:
        return Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Coverage gap (7.1): Docker was not available in the review "
                "environment, so `docker build` could not be run for the four "
                "service Dockerfiles. Run `docker build` per image in an "
                "environment with a working Docker daemon to confirm each image "
                "builds reproducibly; this step was not a silent pass."
            ),
            dedup_key="containers-packaging:docker-build-coverage-gap",
            subject="Dockerfile,apps/cna-api/Dockerfile,apps/cna-web/Dockerfile,apps/cna-worker/Dockerfile",
        )
    failed = sorted(s for s, ok in results.docker_build_ok.items() if not ok)
    not_attempted = sorted(set(SERVICE_DOCKERFILES) - set(results.docker_build_ok))
    if failed:
        return Finding(
            area=_AREA,
            severity=Severity.HIGH,
            proposed_action=(
                "docker build failed (7.1) for: "
                f"{', '.join(failed)}. Fix the Dockerfile(s) so each service "
                "image builds cleanly before release."
            ),
            dedup_key="containers-packaging:docker-build-failure",
            subject=",".join(failed),
        )
    built = sorted(s for s, ok in results.docker_build_ok.items() if ok)
    action = (
        "Verified compliant (7.1): `docker build` succeeds for every service "
        f"image ({', '.join(built)}) on the local Docker daemon. No image is "
        "pushed to a live registry (verification is build-only). Guard against "
        "a build regression."
    )
    if not_attempted:
        action += (
            " Coverage gap: not attempted this run — "
            f"{', '.join(not_attempted)}; build these too on the next sweep."
        )
    return Finding(
        area=_AREA,
        severity=Severity.INFORMATIONAL,
        proposed_action=action,
        dedup_key="containers-packaging:docker-build-verified",
        subject=",".join(sorted(SERVICE_DOCKERFILES)),
    )


def _built_image_non_root_finding(results: VerificationResults) -> Finding:
    """7.4 — assert each *built* image's runtime USER is non-root.

    Reuses :func:`is_root_user` (the same predicate the static audit uses) on the
    ``USER`` observed via ``docker inspect`` for each built image, so the built
    artifact — not only the Dockerfile source — is asserted non-root. A root/unset
    runtime user is a HIGH finding; when Docker was unavailable this is a coverage
    gap (the static audit in :func:`containers_packaging_findings` still covers
    7.4 from the Dockerfile source).
    """
    if not results.inspected_users:
        return Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Coverage gap (7.4): no built images were available to inspect "
                "(Docker unavailable), so the runtime USER of the built images "
                "could not be asserted. The Dockerfile-source non-root audit "
                "still applies; inspect the built images' USER where Docker is "
                "available to confirm the built artifact matches the source."
            ),
            dedup_key="containers-packaging:built-image-user-coverage-gap",
            subject="Dockerfile,apps/cna-api/Dockerfile,apps/cna-web/Dockerfile,apps/cna-worker/Dockerfile",
        )
    root_images = sorted(
        subject for subject, user in results.inspected_users.items() if is_root_user(user)
    )
    if root_images:
        return Finding(
            area=_AREA,
            severity=Severity.HIGH,
            proposed_action=(
                "Built image runs as root (7.4): "
                f"{', '.join(root_images)} resolved to a root/unset runtime USER "
                "on the built image. End the final stage on a non-root user so "
                "the shipped container does not run as root."
            ),
            dedup_key="containers-packaging:built-image-runs-as-root",
            subject=",".join(root_images),
        )
    summary = ", ".join(
        f"{subject}={user}" for subject, user in sorted(results.inspected_users.items())
    )
    return Finding(
        area=_AREA,
        severity=Severity.INFORMATIONAL,
        proposed_action=(
            "Verified compliant (7.4): every built image runs as a non-root user "
            f"({summary}), confirmed via docker inspect .Config.User — the built "
            "artifact matches the non-root final USER in each Dockerfile. Guard "
            "against regression."
        ),
        dedup_key="containers-packaging:built-image-non-root-verified",
        subject=",".join(sorted(results.inspected_users)),
    )


def _hadolint_finding(results: VerificationResults) -> Finding:
    """hadolint lint of each Dockerfile (verified or coverage gap)."""
    if not results.hadolint_available:
        return Finding(
            area=_AREA,
            severity=Severity.LOW,
            proposed_action=(
                "Coverage gap: hadolint was not available in the review "
                "environment, so the four service Dockerfiles were not linted by "
                "hadolint. Install hadolint (or run it in CI) and lint each "
                "Dockerfile; this step was recorded as a gap, not a silent pass."
            ),
            dedup_key="containers-packaging:hadolint-coverage-gap",
            subject="Dockerfile,apps/cna-api/Dockerfile,apps/cna-web/Dockerfile,apps/cna-worker/Dockerfile",
        )
    return Finding(
        area=_AREA,
        severity=Severity.INFORMATIONAL,
        proposed_action=(
            "Verified compliant: hadolint reported no blocking findings across "
            "the four service Dockerfiles. Keep hadolint in the container-build "
            "pipeline and guard against regression."
        ),
        dedup_key="containers-packaging:hadolint-verified",
        subject="Dockerfile,apps/cna-api/Dockerfile,apps/cna-web/Dockerfile,apps/cna-worker/Dockerfile",
    )


def _private_pull_note_finding() -> Finding:
    """Note that private image pulls reference R-006 (escalation owned by 10.1).

    This is *not* an Escalation_Record — it carries no ``blocker_id`` so it stays
    a fixable/informational area finding. The R-006 Escalation_Record for runtime
    secrets is owned by spec task 10.1; recording a second one here would double
    it in the consolidated plan. This note records the boundary (design section 7
    escalation boundary) so the coverage is attributable to this task.
    """
    return Finding(
        area=_AREA,
        severity=Severity.INFORMATIONAL,
        proposed_action=(
            "Escalation boundary note: pulling a private base/service image needs "
            f"registry credentials supplied at deploy time — a runtime secret that "
            f"references REVIEW.md {_R006}. The owning Escalation_Record is recorded "
            "by the security-secrets area (spec task 10.1); no image was pushed to "
            "a live registry during this verification (build-only). No duplicate "
            "escalation is emitted here."
        ),
        dedup_key="containers-packaging:private-pull-r006-note",
        subject="docker-compose.yml,Dockerfile",
    )


def containers_packaging_verify_findings(
    results: VerificationResults | None = None,
) -> list[Finding]:
    """Return the Requirement 7.1/7.3/7.4 verification records (spec task 11.3).

    Records the outcome of the container/packaging verification sweep as
    ``Finding`` records so the consolidated plan captures *what was verified* and
    *what remained a coverage gap*, not only what broke:

      * **7.3 — CLI packaging (verified).** Builds the ``cna`` wheel, installs it
        into a clean virtualenv, and runs ``cna --help`` — the most portable
        check and the behavioural core of Requirement 7.3.
      * **7.1 — ``docker build`` per image (verified).** Every service image
        (root, ``cna-api``, ``cna-web``, ``cna-worker``) builds on the local
        Docker daemon. Build-only: **no image is pushed to a live registry.**
      * **7.4 — non-root on the built image.** Reuses :func:`is_root_user` on the
        runtime ``USER`` observed via ``docker inspect`` so the built artifact —
        not only the Dockerfile source — is asserted non-root.
      * **hadolint — coverage gap.** ``hadolint`` was unavailable in this
        environment; its Dockerfile-lint step is recorded as a coverage gap
        rather than a silent pass (design "Error Handling").
      * **Private image pull → R-006 (note only).** Private registry credentials
        are a runtime-secret dependency that references ``R-006``; the owning
        ``Escalation_Record`` is recorded by spec task 10.1, so this area only
        notes the boundary (no ``blocker_id`` here, no duplicate escalation).

    :param results: the observed verification outcomes; defaults to what this
        task's run produced (:data:`_OBSERVED`). Passing an explicit
        :class:`VerificationResults` lets a caller (and the tests) exercise the
        verified, coverage-gap, and failure branches.
    :returns: the recorded verification :class:`Finding` records.
    """
    if results is None:
        results = _OBSERVED
    return [
        _packaging_finding(results),
        _docker_build_finding(results),
        _built_image_non_root_finding(results),
        _hadolint_finding(results),
        _private_pull_note_finding(),
    ]
