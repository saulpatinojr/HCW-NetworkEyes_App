"""An appliance process never honours ``CNA_PROFILE`` (change set H).

The test profile makes Entra validation read its signing keys from a local file. It
is meant for pytest and local development only; an appliance image started with
``CNA_PROFILE`` set to any value exits before serving, so no deployment can be
talked into accepting self-signed tokens.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "apps" / "network-assessment-api"

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("fastapi") is None or importlib.util.find_spec("jwt") is None,
    reason="the API extra (fastapi, pyjwt) is not installed",
)


def _entra():
    if str(API_DIR) not in sys.path:
        sys.path.insert(0, str(API_DIR))
    import entra

    return entra


_BASE = {"DATABASE_URL": "postgresql://cna@db.internal/cna", "CNA_API_TOKEN": "x" * 32}


@pytest.mark.parametrize(
    "edition_env", [{"CNA_EDITION": "appliance"}, {"CNA_APPLIANCE_CLOUD": "azure"}]
)
@pytest.mark.parametrize("profile", ["test", "dev", "anything"])
def test_appliance_refuses_any_profile(edition_env: dict[str, str], profile: str):
    entra = _entra()
    with pytest.raises(SystemExit, match="appliance edition: CNA_PROFILE is not accepted"):
        entra.refuse_profile_in_appliance({**_BASE, **edition_env, "CNA_PROFILE": profile})


def test_local_development_may_set_a_profile():
    entra = _entra()
    entra.refuse_profile_in_appliance({"CNA_PROFILE": "test"})


def test_the_api_startup_check_exits_before_anything_else(api_main):
    with pytest.raises(SystemExit, match="CNA_PROFILE is not accepted"):
        api_main._validate_startup_config(
            {**_BASE, "CNA_EDITION": "appliance", "CNA_PROFILE": "test"}
        )


def test_half_configured_entra_exits(api_main):
    with pytest.raises(SystemExit, match="CNA_ENTRA_TENANT_ID and CNA_ENTRA_AUDIENCE"):
        api_main._validate_startup_config({**_BASE, "CNA_ENTRA_TENANT_ID": "t"})


def test_appliance_accepts_entra_in_place_of_the_shared_token(api_main):
    env = {
        "DATABASE_URL": _BASE["DATABASE_URL"],
        "CNA_APPLIANCE_CLOUD": "azure",
        "CNA_ENTRA_TENANT_ID": "00000000-0000-0000-0000-000000000001",
        "CNA_ENTRA_AUDIENCE": "api://network-assessment-api-test",
    }
    api_main._validate_startup_config(env)


def test_appliance_with_neither_bearer_exits(api_main):
    with pytest.raises(SystemExit, match="Neither CNA_API_TOKEN nor CNA_ENTRA"):
        api_main._validate_startup_config(
            {"DATABASE_URL": _BASE["DATABASE_URL"], "CNA_APPLIANCE_CLOUD": "azure"}
        )


@pytest.fixture(scope="module")
def api_main():
    from tests.unit.test_network_assessment_api_auth_reliability import _load_api_module

    if importlib.util.find_spec("psycopg2") is None:
        pytest.skip("psycopg2 not installed")
    return _load_api_module()
