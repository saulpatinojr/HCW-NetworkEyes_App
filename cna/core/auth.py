"""Authentication and credential management.

Closes TODO_PhaseA: No Authentication / Credential Management Model.

Credential workflow for each operator persona:

  1. LOCAL DEV (Docker, single operator):
     Credentials in .env file (never committed).
     Docker mounts .env via --env-file.
     AWS: env vars AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
       OR ~/.aws/credentials mount.
     Azure: env vars AZURE_CLIENT_ID / AZURE_CLIENT_SECRET / AZURE_TENANT_ID.

  2. CI/CD PIPELINE (GitHub Actions):
     AWS: OIDC federation — no long-lived keys.
     Azure: Federated identity credential on the SP.
     Secrets stored in GitHub Actions secrets, never in code.

  3. CONTRACTOR / FIELD OPERATOR:
     Credentials fetched from Azure Key Vault at runtime.
     `cna auth login` authenticates to Key Vault using device flow.
     Credentials are memory-only — never written to disk.
     Key Vault URL from AZURE_KEY_VAULT_URL env var.

  4. CREDENTIAL ROTATION:
     AWS: Role assumption is short-lived (1h default). Rotation is automatic.
     Azure SP: Secret rotation managed in Key Vault with expiry alerts.
     No long-lived static keys should ever be used for discovery.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger("cna.core.auth")


class AWSCredentials:
    """AWS credentials for cross-account role assumption.

    Uses STS AssumeRole with ExternalId.
    Credentials are in-memory only — never persisted to disk.
    Session duration: 1 hour (AWS default for cross-account roles).
    """

    def __init__(self, role_arn: str, external_id: str, session_name: str = "CNA-Discovery"):
        self.role_arn = role_arn
        self.external_id = external_id
        self.session_name = session_name
        self._session = None

    def get_session(self):
        """Return a boto3 Session with assumed role credentials.

        Phase C implementation: calls sts.assume_role() with retry on
        CNARateLimitError. Credentials cached in memory for session duration.
        Raises CNAAuthError on failure.
        """
        # TODO: Phase C — implement boto3 STS assume_role
        raise NotImplementedError("Phase C")

    @classmethod
    def from_env(cls) -> AWSCredentials:
        """Construct from environment variables (local dev / CI)."""
        role_arn = os.environ.get("CNA_AWS_ROLE_ARN", "")
        external_id = os.environ.get("CNA_AWS_EXTERNAL_ID", "")
        if not role_arn:
            raise OSError(
                "CNA_AWS_ROLE_ARN not set. Set it in .env or pass --role to `cna discover aws`."
            )
        return cls(role_arn=role_arn, external_id=external_id)


class AzureCredentials:
    """Azure credentials for Service Principal authentication.

    Uses azure-identity DefaultAzureCredential chain in production.
    Falls back to explicit SP client secret for contractor workflow.
    Credentials are in-memory only — never persisted to disk.
    """

    def __init__(
        self,
        tenant_id: str,
        client_id: str,
        client_secret: str | None = None,
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self._client_secret = client_secret  # never logged, never serialized

    def get_credential(self):
        """Return an azure-identity credential object.

        Phase C implementation.
        Uses ClientSecretCredential if secret provided,
        DefaultAzureCredential otherwise (supports managed identity, OIDC).
        Raises CNAAuthError on failure.
        """
        # TODO: Phase C — implement azure-identity credential
        raise NotImplementedError("Phase C")

    @classmethod
    def from_env(cls) -> AzureCredentials:
        """Construct from environment variables."""
        tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        client_secret = os.environ.get("AZURE_CLIENT_SECRET", "")
        if not tenant_id or not client_id:
            raise OSError(
                "AZURE_TENANT_ID and AZURE_CLIENT_ID must be set. "
                "Set them in .env or pass --sp-id and --tenant to `cna discover azure`."
            )
        return cls(tenant_id=tenant_id, client_id=client_id, client_secret=client_secret or None)


class KeyVaultCredentialProvider:
    """Fetches CNA operational secrets from Azure Key Vault at runtime.

    Contractor workflow:
      1. Operator runs `cna auth login` — device flow to authenticate to Key Vault.
      2. Platform fetches AWS role ARN + external ID from Key Vault.
      3. Credentials live in memory for the duration of the CLI process.
      4. No secrets are written to disk, logged, or serialized.

    Secret names in Key Vault (conventional):
      cna-aws-role-arn-<engagement_id>
      cna-aws-external-id-<engagement_id>
      cna-azure-sp-secret-<engagement_id>
    """

    def __init__(self, vault_url: str | None = None):
        self.vault_url = vault_url or os.environ.get("AZURE_KEY_VAULT_URL", "")
        if not self.vault_url:
            raise OSError("AZURE_KEY_VAULT_URL not set. Set it in .env or provide via --vault-url.")

    def get_secret(self, secret_name: str) -> str:
        """Retrieve a secret value from Key Vault.

        Phase C implementation using azure-keyvault-secrets.
        Raises CNAAuthError on permission denied.
        """
        # TODO: Phase C — implement SecretClient.get_secret()
        raise NotImplementedError("Phase C")
