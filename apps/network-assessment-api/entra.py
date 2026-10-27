"""Entra ID bearer validation for the internal routes (change set H).

The internal routes (``/discovery/*``, ``/intake``, ``/publish``) are called by the
web tier only. With a shared secret (``NETWORK_ASSESSMENT_API_TOKEN``) every caller that holds the
secret is equal; with Entra the caller is the web tier's own managed identity, the
token is short-lived, signed by the tenant, scoped to this API's app registration
(``NETWORK_ASSESSMENT_ENTRA_AUDIENCE``, its ``api://`` identifier URI) and carries the app role
``Discovery.Run`` that the deployment assigns to that identity.

Configuration (all read once at start-up):

``NETWORK_ASSESSMENT_ENTRA_TENANT_ID``
    The tenant that issues the tokens. Set together with the audience or not at all.
``NETWORK_ASSESSMENT_ENTRA_AUDIENCE``
    The ``aud`` claim to require: the app registration's identifier URI.
``NETWORK_ASSESSMENT_ENTRA_JWKS_URL``
    Where the signing keys come from. Derived from the tenant when unset. Under the
    test profile it names a local JWKS file instead.
``NETWORK_ASSESSMENT_ENTRA_REQUIRED_ROLE``
    The app role (``roles`` claim) or delegated scope (``scp`` claim) a token must
    carry. Default ``Discovery.Run``.
``NETWORK_ASSESSMENT_PROFILE``
    ``test`` makes the JWKS come from the file named by ``NETWORK_ASSESSMENT_ENTRA_JWKS_URL``. It is
    honoured only under pytest or outside the appliance edition; an appliance image
    started with ``NETWORK_ASSESSMENT_PROFILE`` set to anything exits before serving
    (:func:`refuse_profile_in_appliance`). There is no variable that turns
    authentication off.

Signature, ``iss``, ``aud`` and ``exp`` failures are ``401 {"error": {"code":
"unauthenticated"}}``; a valid token without the role is ``403 {"error": {"code":
"insufficient_role"}}``. Neither response carries the token or the reason: the
reason is logged at debug level only.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import jwt
from starlette.requests import Request

logger = logging.getLogger("network-assessment-api")

DEFAULT_REQUIRED_ROLE = "Discovery.Run"
# Entra signs access tokens with RS256 only; anything else is refused outright.
_ALGORITHMS = ("RS256",)
_JWKS_CACHE_SECONDS = 3600


class AuthError(Exception):
    """Raised by :func:`require_bearer`; ``main.py`` renders it as the JSON error body."""

    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def is_appliance_edition(env: Mapping[str, str]) -> bool:
    """True when this process is an appliance build (``NETWORK_ASSESSMENT_EDITION=appliance``) or runs
    in an appliance deployment (``NETWORK_ASSESSMENT_APPLIANCE_CLOUD`` set)."""
    return env.get("NETWORK_ASSESSMENT_EDITION", "") == "appliance" or bool(
        env.get("NETWORK_ASSESSMENT_APPLIANCE_CLOUD")
    )


def refuse_profile_in_appliance(env: Mapping[str, str]) -> None:
    """Exit when an appliance process is started with ``NETWORK_ASSESSMENT_PROFILE`` set to any value."""
    if is_appliance_edition(env) and env.get("NETWORK_ASSESSMENT_PROFILE", "") != "":
        raise SystemExit("appliance edition: NETWORK_ASSESSMENT_PROFILE is not accepted")


def test_profile_allowed(env: Mapping[str, str]) -> bool:
    """The test profile is honoured only under pytest or outside the appliance edition."""
    return "pytest" in sys.modules or not is_appliance_edition(env)


@dataclass(frozen=True)
class EntraConfig:
    tenant_id: str
    audience: str
    jwks_url: str
    issuers: tuple[str, ...]
    required_role: str
    jwks_from_file: bool

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> EntraConfig | None:
        """``None`` when Entra is not configured; ``SystemExit`` when half-configured."""
        source = os.environ if env is None else env
        tenant = source.get("NETWORK_ASSESSMENT_ENTRA_TENANT_ID", "").strip()
        audience = source.get("NETWORK_ASSESSMENT_ENTRA_AUDIENCE", "").strip()
        if not tenant and not audience:
            return None
        if not tenant or not audience:
            raise SystemExit(
                "NETWORK_ASSESSMENT_ENTRA_TENANT_ID and NETWORK_ASSESSMENT_ENTRA_AUDIENCE are set together or not at all — "
                "refusing to start with only one of them."
            )
        profile = source.get("NETWORK_ASSESSMENT_PROFILE", "")
        jwks_from_file = profile == "test" and test_profile_allowed(source)
        jwks_url = source.get("NETWORK_ASSESSMENT_ENTRA_JWKS_URL", "").strip() or (
            f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys"
        )
        if jwks_from_file and not Path(jwks_url).is_file():
            raise SystemExit(
                "NETWORK_ASSESSMENT_PROFILE=test: NETWORK_ASSESSMENT_ENTRA_JWKS_URL must name an existing JWKS file."
            )
        if not jwks_from_file and not jwks_url.startswith("https://"):
            raise SystemExit("NETWORK_ASSESSMENT_ENTRA_JWKS_URL must be an https:// URL.")
        return cls(
            tenant_id=tenant,
            audience=audience,
            jwks_url=jwks_url,
            # v2.0 tokens carry the first form, v1.0 tokens the second (Microsoft Learn,
            # "Access tokens in the Microsoft identity platform", read 2026-10-25: the v1.0
            # example token's iss is https://sts.windows.net/<tenant-id>/ with the trailing
            # slash, the v2.0 one https://login.microsoftonline.com/<tenant-id>/v2.0). Which
            # one a given API receives is set by its `requestedAccessTokenVersion`; accepting
            # both stays correct whichever the app registration uses.
            issuers=(
                f"https://login.microsoftonline.com/{tenant}/v2.0",
                f"https://sts.windows.net/{tenant}/",
            ),
            required_role=source.get("NETWORK_ASSESSMENT_ENTRA_REQUIRED_ROLE", "").strip()
            or DEFAULT_REQUIRED_ROLE,
            jwks_from_file=jwks_from_file,
        )


class EntraValidator:
    """Validates a bearer token against the configured tenant and audience."""

    def __init__(self, config: EntraConfig) -> None:
        self.config = config
        self._jwk_client: jwt.PyJWKClient | None = None
        self._file_keys: jwt.PyJWKSet | None = None

    def _signing_key(self, token: str):
        if self.config.jwks_from_file:
            if self._file_keys is None:
                document = json.loads(Path(self.config.jwks_url).read_text(encoding="utf-8"))
                self._file_keys = jwt.PyJWKSet.from_dict(document)
            kid = jwt.get_unverified_header(token).get("kid")
            if not kid:
                raise jwt.InvalidTokenError("token header carries no kid")
            return self._file_keys[kid].key
        if self._jwk_client is None:
            self._jwk_client = jwt.PyJWKClient(
                self.config.jwks_url, cache_keys=True, lifespan=_JWKS_CACHE_SECONDS
            )
        return self._jwk_client.get_signing_key_from_jwt(token).key

    def validate(self, token: str) -> dict:
        """The claims of a token whose signature, issuer, audience and expiry hold.

        Raises :class:`jwt.PyJWTError` (or ``KeyError`` for an unknown ``kid``) otherwise.
        """
        key = self._signing_key(token)
        return jwt.decode(
            token,
            key,
            algorithms=list(_ALGORITHMS),
            audience=self.config.audience,
            issuer=list(self.config.issuers),
            options={"require": ["exp", "iss", "aud"]},
        )

    def has_role(self, claims: Mapping[str, object]) -> bool:
        role = self.config.required_role
        roles = claims.get("roles") or []
        if isinstance(roles, list | tuple) and role in roles:
            return True
        scopes = claims.get("scp") or ""
        return isinstance(scopes, str) and role in scopes.split()


_validator: EntraValidator | None = None


def configure(config: EntraConfig | None) -> EntraValidator | None:
    """Install the process-wide validator; ``None`` leaves the internal routes to the
    shared-token middleware."""
    global _validator
    _validator = EntraValidator(config) if config is not None else None
    return _validator


def active_validator() -> EntraValidator | None:
    return _validator


def claims_from_header(validator: EntraValidator, authorization: str) -> dict | None:
    """The claims when ``authorization`` is a valid Entra bearer, else ``None``."""
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    try:
        return validator.validate(token.strip())
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        logger.debug("entra token rejected: %s", type(exc).__name__)
        return None


async def require_bearer(request: Request) -> dict:
    """Authenticate (401 ``unauthenticated``) and authorise (403 ``insufficient_role``).

    Attached to the ``internal`` router only. When Entra is not configured the
    shared-token middleware is the whole authentication and the dependency returns
    no claims; it never becomes a way to skip the middleware.
    """
    validator = _validator
    if validator is None:
        return {}
    claims = getattr(request.state, "entra_claims", None)
    if claims is None:
        claims = claims_from_header(validator, request.headers.get("Authorization", ""))
    if claims is None:
        raise AuthError(401, "unauthenticated")
    if not validator.has_role(claims):
        raise AuthError(403, "insufficient_role")
    return claims
