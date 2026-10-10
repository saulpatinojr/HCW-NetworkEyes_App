"""Entra bearer validation on the internal router (change set H).

Tokens are signed here with a throw-away RSA key whose public half is written to a
JWKS file; ``EntraConfig.jwks_from_file`` (the test profile) reads it. Everything
else — issuer, audience, expiry, the ``Discovery.Run`` role in ``roles`` or
``scp``, the 401/403 bodies and the list of routes on the ``internal`` router — is
the real code path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

from tests.unit.test_cna_api_auth_reliability import _load_api_module

_REPO_ROOT = Path(__file__).resolve().parents[2]
_API_DIR = _REPO_ROOT / "apps" / "cna-api"

pytestmark = pytest.mark.skipif(
    any(importlib.util.find_spec(d) is None for d in ("fastapi", "httpx", "psycopg2", "jwt")),
    reason="the API extra is not installed",
)

TENANT = "00000000-0000-0000-0000-000000000001"
AUDIENCE = "api://cna-api-test"
ISSUER = f"https://login.microsoftonline.com/{TENANT}/v2.0"
KID = "test-signing-key"

# Routes that must sit on the internal router (the plan's list, section 7.H).
PROTECTED = {
    "/discovery/start",
    "/discovery/jobs/{job_id}",
    "/discovery/test-access",
    "/discovery/test-connection-aws",
    "/intake",
    "/publish",
}


@pytest.fixture(scope="module")
def api_main():
    return _load_api_module()


@pytest.fixture(scope="module")
def entra():
    if str(_API_DIR) not in sys.path:
        sys.path.insert(0, str(_API_DIR))
    import entra as module

    return module


@pytest.fixture(scope="module")
def signing_key(tmp_path_factory):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from jwt.algorithms import RSAAlgorithm

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update({"kid": KID, "use": "sig", "alg": "RS256"})
    jwks_file = tmp_path_factory.mktemp("jwks") / "keys.json"
    jwks_file.write_text(json.dumps({"keys": [jwk]}), encoding="utf-8")
    pem = private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return pem, jwks_file


@pytest.fixture
def validator(entra, signing_key, monkeypatch):
    _pem, jwks_file = signing_key
    config = entra.EntraConfig(
        tenant_id=TENANT,
        audience=AUDIENCE,
        jwks_url=str(jwks_file),
        issuers=(ISSUER, f"https://sts.windows.net/{TENANT}/"),
        required_role="Discovery.Run",
        jwks_from_file=True,
    )
    instance = entra.EntraValidator(config)
    monkeypatch.setattr(entra, "_validator", instance)
    return instance


def _token(signing_key, **claims) -> str:
    import jwt

    pem, _ = signing_key
    now = int(time.time())
    payload = {"iss": ISSUER, "aud": AUDIENCE, "iat": now, "exp": now + 300, "sub": "web-identity"}
    payload.update(claims)
    return jwt.encode(payload, pem, algorithm="RS256", headers={"kid": KID})


@pytest.fixture
def client(api_main, validator):
    from fastapi.testclient import TestClient

    wrapped = api_main.BearerTokenMiddleware(api_main.app, entra=validator)
    return TestClient(wrapped, raise_server_exceptions=False)


# ── authentication ───────────────────────────────────────────────────────────


def test_no_token_is_401(client):
    resp = client.get("/discovery/jobs/x")
    assert resp.status_code == 401
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


def test_wrong_audience_is_401(client, signing_key):
    resp = client.get(
        "/discovery/jobs/x",
        headers={"Authorization": f"Bearer {_token(signing_key, aud='api://someone-else')}"},
    )
    assert resp.status_code == 401


def test_wrong_issuer_is_401(client, signing_key):
    token = _token(signing_key, iss="https://login.microsoftonline.com/other-tenant/v2.0")
    assert (
        client.get("/discovery/jobs/x", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_expired_token_is_401(client, signing_key):
    token = _token(signing_key, exp=int(time.time()) - 60)
    assert (
        client.get("/discovery/jobs/x", headers={"Authorization": f"Bearer {token}"}).status_code
        == 401
    )


def test_unsigned_token_is_401(client):
    import jwt

    token = jwt.encode(
        {"iss": ISSUER, "aud": AUDIENCE, "exp": int(time.time()) + 60}, "", algorithm="none"
    )
    resp = client.get("/discovery/jobs/x", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401


def test_garbage_bearer_is_401_not_500(client):
    resp = client.get("/discovery/jobs/x", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


# ── authorisation ────────────────────────────────────────────────────────────


def test_valid_token_without_the_role_is_403_insufficient_role(client, signing_key):
    token = _token(signing_key, roles=["Other.Role"], scp="")
    resp = client.get("/discovery/jobs/x", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403
    assert resp.json() == {"error": {"code": "insufficient_role"}}


def test_role_in_roles_reaches_the_route(client, signing_key):
    token = _token(signing_key, roles=["Discovery.Run"])
    resp = client.get("/discovery/jobs/x", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code not in (401, 403)


def test_role_in_scp_reaches_the_route(client, signing_key):
    token = _token(signing_key, scp="Other.Scope Discovery.Run")
    resp = client.get("/discovery/jobs/x", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code not in (401, 403)


def test_dependency_alone_answers_unauthenticated_with_the_plan_body(api_main, validator):
    """The dependency's own 401 (a request that reached the router without claims)."""
    from fastapi.testclient import TestClient

    resp = TestClient(api_main.app, raise_server_exceptions=False).get("/discovery/jobs/x")
    assert resp.status_code == 401
    assert resp.json() == {"error": {"code": "unauthenticated"}}
    assert resp.headers.get("WWW-Authenticate") == "Bearer"


# ── routing ──────────────────────────────────────────────────────────────────


def test_every_internal_route_is_registered_on_the_internal_router(api_main):
    from fastapi.routing import APIRoute

    on_internal = {r.path for r in api_main.internal.routes if isinstance(r, APIRoute)}
    assert on_internal == PROTECTED

    stray = {
        r.path
        for r in api_main.app.routes
        if isinstance(r, APIRoute)
        and (r.path.startswith("/discovery/") or r.path in ("/intake", "/publish"))
        and api_main.require_bearer not in [d.dependency for d in r.dependencies]
    }
    assert stray == set()


def test_probes_need_no_token(client):
    assert client.get("/health").status_code == 200


# ── configuration ────────────────────────────────────────────────────────────


def test_from_env_is_none_when_unset(entra):
    assert entra.EntraConfig.from_env({}) is None


def test_from_env_derives_jwks_and_issuers(entra):
    config = entra.EntraConfig.from_env(
        {"CNA_ENTRA_TENANT_ID": TENANT, "CNA_ENTRA_AUDIENCE": AUDIENCE}
    )
    assert config is not None
    assert config.jwks_url == f"https://login.microsoftonline.com/{TENANT}/discovery/v2.0/keys"
    assert ISSUER in config.issuers
    assert config.required_role == "Discovery.Run"
    assert config.jwks_from_file is False


def test_from_env_refuses_a_non_https_jwks_url(entra):
    with pytest.raises(SystemExit, match="https://"):
        entra.EntraConfig.from_env(
            {
                "CNA_ENTRA_TENANT_ID": TENANT,
                "CNA_ENTRA_AUDIENCE": AUDIENCE,
                "CNA_ENTRA_JWKS_URL": "http://keys.example/jwks",
            }
        )


def test_test_profile_reads_keys_from_a_file(entra, signing_key):
    _pem, jwks_file = signing_key
    config = entra.EntraConfig.from_env(
        {
            "CNA_ENTRA_TENANT_ID": TENANT,
            "CNA_ENTRA_AUDIENCE": AUDIENCE,
            "CNA_ENTRA_JWKS_URL": str(jwks_file),
            "CNA_PROFILE": "test",
        }
    )
    assert config is not None and config.jwks_from_file is True


def test_test_profile_needs_an_existing_file(entra, tmp_path):
    with pytest.raises(SystemExit, match="existing JWKS file"):
        entra.EntraConfig.from_env(
            {
                "CNA_ENTRA_TENANT_ID": TENANT,
                "CNA_ENTRA_AUDIENCE": AUDIENCE,
                "CNA_ENTRA_JWKS_URL": str(tmp_path / "missing.json"),
                "CNA_PROFILE": "test",
            }
        )


def test_there_is_no_switch_that_disables_authentication():
    source = (
        (_API_DIR / "entra.py").read_text(encoding="utf-8")
        + (_API_DIR / "auth.py").read_text(encoding="utf-8")
        + (_API_DIR / "main.py").read_text(encoding="utf-8")
    )
    assert "CNA_AUTH_DISABLED" not in source
    assert "AUTH_DISABLED" not in source
