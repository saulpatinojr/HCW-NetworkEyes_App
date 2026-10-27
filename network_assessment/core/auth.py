"""Authentication and credential management.

Closes TODO_PhaseA: No Authentication / Credential Management Model.

Credential workflow for each operator persona:

  1. LOCAL DEV (Docker, single operator):
     Credentials in .env file (never committed).
     Docker mounts .env via --env-file.
     AWS: env vars AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY
       OR ~/.aws/credentials mount.
     Azure: `az login` (the CLI credential) or a managed identity; AZURE_TENANT_ID and
       AZURE_CLIENT_ID name the tenant and identity. No client secret, ever.

  2. CI/CD PIPELINE (GitHub Actions):
     AWS: OIDC federation — no long-lived keys.
     Azure: Federated identity credential on the SP.
     Secrets stored in GitHub Actions secrets, never in code.

  3. CONTRACTOR / FIELD OPERATOR:
     Credentials fetched from Azure Key Vault at runtime.
     `network-assessment auth login` authenticates to Key Vault using device flow.
     Credentials are memory-only — never written to disk.
     Key Vault URL from AZURE_KEY_VAULT_URL env var.

  4. CREDENTIAL ROTATION:
     AWS: Role assumption is short-lived (1h default). Rotation is automatic.
     Azure: the appliance's user-assigned managed identity has no secret to rotate.
     No long-lived static keys should ever be used for discovery.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Mapping

logger = logging.getLogger("network_assessment.core.auth")


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
        NetworkAssessmentRateLimitError. Credentials cached in memory for session duration.
        Raises NetworkAssessmentAuthError on failure.
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
                "CNA_AWS_ROLE_ARN not set. Set it in .env or pass --role to `network-assessment discover aws`."
            )
        return cls(role_arn=role_arn, external_id=external_id)


# Credential variables the appliance refuses to start with (REFACTOR_APP.md change set G).
# DefaultAzureCredential's environment credential would turn any of them into a
# long-lived secret path; the appliance authenticates with its user-assigned managed
# identity only, and the build below excludes that credential everywhere.
FORBIDDEN_CREDENTIAL_ENV: tuple[str, ...] = (
    "AZURE_CLIENT_SECRET",
    "AZURE_CLIENT_CERTIFICATE_PATH",
    "AZURE_USERNAME",
    "AZURE_PASSWORD",
    "AZURE_FEDERATED_TOKEN_FILE",
    "AZURE_AUTHORITY_HOST",
)
APPLIANCE_ENV = "CNA_APPLIANCE_CLOUD"


def forbidden_credential_env(env: Mapping[str, str] | None = None) -> list[str]:
    """The forbidden credential variables present (non-empty) in ``env``."""
    source = os.environ if env is None else env
    return [name for name in FORBIDDEN_CREDENTIAL_ENV if source.get(name)]


def refuse_forbidden_credential_env(env: Mapping[str, str] | None = None) -> None:
    """Exit before any credential object exists when a forbidden variable is set.

    Raises ``SystemExit`` naming the variables (never their values).
    """
    present = forbidden_credential_env(env)
    if present:
        raise SystemExit(
            "appliance edition: refusing to start, forbidden credential variables set: "
            f"{present}. The appliance authenticates with its user-assigned managed identity "
            "(AZURE_CLIENT_ID) and accepts no client secret, certificate, password or "
            "federated token file."
        )


def is_appliance(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return bool(source.get(APPLIANCE_ENV))


def build_azure_credential(env: Mapping[str, str] | None = None):
    """The one Azure credential the platform uses: ``DefaultAzureCredential`` without the
    environment and interactive credentials.

    What stays in the chain: workload identity (its federated token file is forbidden in
    the appliance, so it is inert there), managed identity (``AZURE_CLIENT_ID`` selects the
    user-assigned identity), the Azure CLI, Azure PowerShell and the Azure Developer CLI —
    the developer paths behind ``az login``. What is excluded: the environment credential
    (client secrets, certificates, username/password), the interactive browser, the shared
    token cache and Visual Studio Code. In the appliance (``CNA_APPLIANCE_CLOUD`` set) a
    forbidden variable exits the process before the credential is built.
    """
    source = os.environ if env is None else env
    if is_appliance(source):
        refuse_forbidden_credential_env(source)
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential(
        exclude_environment_credential=True,
        exclude_interactive_browser_credential=True,
        exclude_shared_token_cache_credential=True,
        exclude_visual_studio_code_credential=True,
        managed_identity_client_id=source.get("AZURE_CLIENT_ID") or None,
    )


class AzureCredentials:
    """The Azure identity the platform runs as: a tenant and the identity's client id.

    There is no client secret: ``get_credential`` returns :func:`build_azure_credential`,
    which resolves to the managed identity in the appliance and to ``az login`` on a
    developer machine. Nothing here is ever persisted.
    """

    def __init__(self, tenant_id: str, client_id: str | None = None):
        self.tenant_id = tenant_id
        self.client_id = client_id

    def get_credential(self):
        """Return the platform's azure-identity credential (see ``build_azure_credential``)."""
        env = dict(os.environ)
        if self.client_id:
            env["AZURE_CLIENT_ID"] = self.client_id
        return build_azure_credential(env)

    @classmethod
    def from_env(cls) -> AzureCredentials:
        """Construct from environment variables; a forbidden credential variable refuses."""
        tenant_id = os.environ.get("AZURE_TENANT_ID", "")
        client_id = os.environ.get("AZURE_CLIENT_ID", "")
        if not tenant_id:
            raise OSError(
                "AZURE_TENANT_ID must be set. Set it in .env or pass --tenant-id to "
                "`network-assessment discover azure`."
            )
        if forbidden_credential_env():
            refuse_forbidden_credential_env()
        return cls(tenant_id=tenant_id, client_id=client_id or None)


class KeyVaultCredentialProvider:
    """Fetches CNA operational secrets from Azure Key Vault at runtime.

    Contractor workflow:
      1. Operator runs `network-assessment auth login` — device flow to authenticate to Key Vault.
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
        Raises NetworkAssessmentAuthError on permission denied.
        """
        # TODO: Phase C — implement SecretClient.get_secret()
        raise NotImplementedError("Phase C")
