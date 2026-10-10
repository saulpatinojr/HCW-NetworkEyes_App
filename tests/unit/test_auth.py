"""Unit tests for cna.core.auth — credential constructors and env-var loading."""

from __future__ import annotations

import pytest

from cna.core.auth import AWSCredentials, AzureCredentials, KeyVaultCredentialProvider

# ── AWSCredentials ─────────────────────────────────────────────────────────────


class TestAWSCredentials:
    def test_constructor_stores_fields(self):
        creds = AWSCredentials(
            role_arn="arn:aws:iam::123456789012:role/CNA-Discovery",
            external_id="cna-external-secret",
            session_name="CNA-Test",
        )
        assert creds.role_arn == "arn:aws:iam::123456789012:role/CNA-Discovery"
        assert creds.external_id == "cna-external-secret"
        assert creds.session_name == "CNA-Test"

    def test_session_default_name(self):
        creds = AWSCredentials(role_arn="arn:aws:iam::123:role/R", external_id="ext")
        assert creds.session_name == "CNA-Discovery"

    def test_session_starts_as_none(self):
        creds = AWSCredentials(role_arn="arn:aws:iam::123:role/R", external_id="ext")
        assert creds._session is None

    def test_get_session_raises_not_implemented(self):
        """Phase C — boto3 STS assume_role not yet implemented."""
        creds = AWSCredentials(role_arn="arn:aws:iam::123:role/R", external_id="ext")
        with pytest.raises(NotImplementedError):
            creds.get_session()

    def test_from_env_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("CNA_AWS_ROLE_ARN", "arn:aws:iam::999:role/Test")
        monkeypatch.setenv("CNA_AWS_EXTERNAL_ID", "test-ext-id")
        creds = AWSCredentials.from_env()
        assert creds.role_arn == "arn:aws:iam::999:role/Test"
        assert creds.external_id == "test-ext-id"

    def test_from_env_raises_if_role_arn_not_set(self, monkeypatch):
        monkeypatch.delenv("CNA_AWS_ROLE_ARN", raising=False)
        with pytest.raises(OSError, match="CNA_AWS_ROLE_ARN"):
            AWSCredentials.from_env()

    def test_from_env_external_id_optional(self, monkeypatch):
        monkeypatch.setenv("CNA_AWS_ROLE_ARN", "arn:aws:iam::123:role/R")
        monkeypatch.delenv("CNA_AWS_EXTERNAL_ID", raising=False)
        creds = AWSCredentials.from_env()
        assert creds.external_id == ""


# ── AzureCredentials ───────────────────────────────────────────────────────────


class TestAzureCredentials:
    def test_constructor_stores_fields(self):
        creds = AzureCredentials(
            tenant_id="tenant-abc",
            client_id="client-xyz",
            client_secret="super-secret",
        )
        assert creds.tenant_id == "tenant-abc"
        assert creds.client_id == "client-xyz"
        assert creds._client_secret == "super-secret"

    def test_client_secret_optional(self):
        creds = AzureCredentials(tenant_id="t", client_id="c")
        assert creds._client_secret is None

    def test_get_credential_raises_not_implemented(self):
        """Phase C — azure-identity credential not yet implemented."""
        creds = AzureCredentials(tenant_id="t", client_id="c", client_secret="s")
        with pytest.raises(NotImplementedError):
            creds.get_credential()

    def test_from_env_reads_env_vars(self, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "my-tenant-id")
        monkeypatch.setenv("AZURE_CLIENT_ID", "my-client-id")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "my-secret")
        creds = AzureCredentials.from_env()
        assert creds.tenant_id == "my-tenant-id"
        assert creds.client_id == "my-client-id"
        assert creds._client_secret == "my-secret"

    def test_from_env_raises_if_tenant_missing(self, monkeypatch):
        monkeypatch.delenv("AZURE_TENANT_ID", raising=False)
        monkeypatch.setenv("AZURE_CLIENT_ID", "client-id")
        with pytest.raises(OSError, match="AZURE_TENANT_ID"):
            AzureCredentials.from_env()

    def test_from_env_raises_if_client_id_missing(self, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "tenant-id")
        monkeypatch.delenv("AZURE_CLIENT_ID", raising=False)
        with pytest.raises(OSError, match="AZURE_CLIENT_ID"):
            AzureCredentials.from_env()

    def test_from_env_secret_none_if_empty(self, monkeypatch):
        monkeypatch.setenv("AZURE_TENANT_ID", "t")
        monkeypatch.setenv("AZURE_CLIENT_ID", "c")
        monkeypatch.setenv("AZURE_CLIENT_SECRET", "")
        creds = AzureCredentials.from_env()
        assert creds._client_secret is None


# ── KeyVaultCredentialProvider ─────────────────────────────────────────────────


class TestKeyVaultCredentialProvider:
    def test_raises_if_no_vault_url(self, monkeypatch):
        monkeypatch.delenv("AZURE_KEY_VAULT_URL", raising=False)
        with pytest.raises(OSError, match="AZURE_KEY_VAULT_URL"):
            KeyVaultCredentialProvider()

    def test_reads_vault_url_from_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://cna-vault.vault.azure.net/")
        provider = KeyVaultCredentialProvider()
        assert provider.vault_url == "https://cna-vault.vault.azure.net/"

    def test_explicit_vault_url_overrides_env(self, monkeypatch):
        monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://other-vault.vault.azure.net/")
        provider = KeyVaultCredentialProvider(vault_url="https://explicit-vault.vault.azure.net/")
        assert provider.vault_url == "https://explicit-vault.vault.azure.net/"

    def test_get_secret_raises_not_implemented(self, monkeypatch):
        """Phase C — SecretClient.get_secret() not yet implemented."""
        monkeypatch.setenv("AZURE_KEY_VAULT_URL", "https://cna-vault.vault.azure.net/")
        provider = KeyVaultCredentialProvider()
        with pytest.raises(NotImplementedError):
            provider.get_secret("cna-aws-role-arn-eng-001")
