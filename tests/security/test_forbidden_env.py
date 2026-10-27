"""The appliance refuses a secret-shaped credential variable before any credential exists.

``network_assessment.core.auth.build_azure_credential`` is the only credential path. In the appliance
(``NETWORK_ASSESSMENT_APPLIANCE_CLOUD`` set) each forbidden variable — a client secret, a certificate path,
a username/password pair, a federated token file, an authority override — exits the process
with ``SystemExit`` before ``DefaultAzureCredential`` is constructed; the API's startup
validation does the same. Outside the appliance the chain still excludes the environment
and interactive credentials, so the variables are inert there too.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

from network_assessment.core import auth

APPLIANCE = {
    "NETWORK_ASSESSMENT_APPLIANCE_CLOUD": "azure",
    "AZURE_TENANT_ID": "00000000-0000-0000-0000-000000000002",
}


@pytest.fixture
def recording_identity(monkeypatch):
    """A fake ``azure.identity`` that records every credential construction."""
    constructions: list[dict] = []
    fake = types.ModuleType("azure.identity")

    class DefaultAzureCredential:
        def __init__(self, **kwargs):
            constructions.append(kwargs)

    fake.DefaultAzureCredential = DefaultAzureCredential  # type: ignore[attr-defined]
    package = types.ModuleType("azure")
    package.__path__ = []  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "azure", package)
    monkeypatch.setitem(sys.modules, "azure.identity", fake)
    return constructions


class TestApplianceRefuses:
    @pytest.mark.parametrize("variable", auth.FORBIDDEN_CREDENTIAL_ENV)
    def test_each_forbidden_variable_exits_before_a_credential_exists(
        self, variable, recording_identity
    ):
        env = {**APPLIANCE, variable: "not-a-real-value"}
        with pytest.raises(SystemExit, match=variable):
            auth.build_azure_credential(env)
        assert recording_identity == []

    def test_tenant_id_beside_a_secret_still_refuses(self, recording_identity):
        env = {
            **APPLIANCE,
            "AZURE_CLIENT_ID": "00000000-0000-0000-0000-000000000003",
            "AZURE_CLIENT_SECRET": "x",
        }
        with pytest.raises(SystemExit, match="AZURE_CLIENT_SECRET"):
            auth.build_azure_credential(env)
        assert recording_identity == []

    def test_the_message_names_variables_not_values(self):
        # Built at runtime so no credential-shaped literal sits in the source.
        placeholder = "-".join(["fictional", "value", "never", "shown"])
        with pytest.raises(SystemExit) as exc_info:
            auth.refuse_forbidden_credential_env({**APPLIANCE, "AZURE_PASSWORD": placeholder})
        assert "AZURE_PASSWORD" in str(exc_info.value)
        assert placeholder not in str(exc_info.value)

    def test_empty_forbidden_variables_do_not_refuse(self):
        auth.refuse_forbidden_credential_env({**APPLIANCE, "AZURE_CLIENT_SECRET": ""})


class TestTheChain:
    def test_appliance_builds_the_managed_identity_chain(self, recording_identity):
        env = {**APPLIANCE, "AZURE_CLIENT_ID": "00000000-0000-0000-0000-000000000003"}
        auth.build_azure_credential(env)
        assert len(recording_identity) == 1
        kwargs = recording_identity[0]
        assert kwargs["exclude_environment_credential"] is True
        assert kwargs["exclude_interactive_browser_credential"] is True
        assert kwargs["exclude_shared_token_cache_credential"] is True
        assert kwargs["exclude_visual_studio_code_credential"] is True
        assert kwargs["managed_identity_client_id"] == "00000000-0000-0000-0000-000000000003"

    def test_developer_machine_gets_the_same_exclusions_without_a_client_id(
        self, recording_identity
    ):
        auth.build_azure_credential({"AZURE_TENANT_ID": "t"})
        assert recording_identity[0]["exclude_environment_credential"] is True
        assert recording_identity[0]["managed_identity_client_id"] is None

    def test_no_secret_reading_credential_class_is_ever_requested(self, recording_identity):
        auth.build_azure_credential({**APPLIANCE, "AZURE_CLIENT_ID": "c"})
        assert all("secret" not in k.lower() for kwargs in recording_identity for k in kwargs)


class TestApiStartup:
    def test_appliance_api_refuses_a_forbidden_variable(self):
        from importlib import util

        if util.find_spec("fastapi") is None:
            pytest.skip("fastapi not installed")
        import importlib

        repo_root = Path(auth.__file__).resolve().parents[2]  # network_assessment/core/auth.py
        sys.path.insert(0, str(repo_root))
        spec = importlib.util.spec_from_file_location(
            "network_assessment_api_main_forbidden_env",
            str(repo_root / "apps" / "network-assessment-api" / "main.py"),
        )
        module = sys.modules.get("network_assessment_api_main_under_test")
        if module is None:
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            sys.modules["network_assessment_api_main_under_test"] = module
            spec.loader.exec_module(module)
        env = {
            "NETWORK_ASSESSMENT_APPLIANCE_CLOUD": "azure",
            "DATABASE_URL": "postgresql://user:not-a-real-password@db/cna",
            "NETWORK_ASSESSMENT_API_TOKEN": "not-a-real-token",
            "AZURE_FEDERATED_TOKEN_FILE": "/var/run/secrets/token",
        }
        with pytest.raises(SystemExit, match="AZURE_FEDERATED_TOKEN_FILE"):
            module._validate_startup_config(env)
