# =============================================================================
# Runtime — Secrets Manager secrets + versions (source: migrate/secrets.tf).
# Mirrors the Azure runtime module (Key Vault secret writes after identity /
# database exist). secret_string is ignored after creation so rotation outside
# Terraform does not trigger drift.
# =============================================================================

# ─── DATABASE_URL ─────────────────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "database_url" {
  name                    = "${var.name_prefix}/database-url"
  description             = "PostgreSQL connection string for Prisma"
  recovery_window_in_days = local.recovery_window

  tags = merge(var.tags, { Name = "${var.name_prefix}-database-url" })
}

resource "aws_secretsmanager_secret_version" "database_url" {
  secret_id     = aws_secretsmanager_secret.database_url.id
  secret_string = "postgresql://${var.db_username}:${urlencode(var.db_password)}@${var.db_endpoint}/${var.db_name}?sslmode=require"

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ─── Auth.js signing secret ───────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "nextauth_secret" {
  name                    = "${var.name_prefix}/nextauth-secret"
  description             = "Auth.js JWT signing secret"
  recovery_window_in_days = local.recovery_window

  tags = merge(var.tags, { Name = "${var.name_prefix}-nextauth-secret" })
}

resource "aws_secretsmanager_secret_version" "nextauth_secret" {
  secret_id     = aws_secretsmanager_secret.nextauth_secret.id
  secret_string = var.nextauth_secret

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ─── Entra ID client secret ───────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "entra_client_secret" {
  name                    = "${var.name_prefix}/entra-client-secret"
  description             = "Entra ID OAuth client secret"
  recovery_window_in_days = local.recovery_window

  tags = merge(var.tags, { Name = "${var.name_prefix}-entra-client-secret" })
}

resource "aws_secretsmanager_secret_version" "entra_client_secret" {
  secret_id     = aws_secretsmanager_secret.entra_client_secret.id
  secret_string = var.entra_client_secret

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ─── Credential encryption key ────────────────────────────────────────────────
resource "aws_secretsmanager_secret" "credential_encryption_key" {
  name                    = "${var.name_prefix}/credential-encryption-key"
  description             = "AES-256 key for encrypting stored credentials"
  recovery_window_in_days = local.recovery_window

  tags = merge(var.tags, { Name = "${var.name_prefix}-credential-encryption-key" })
}

resource "aws_secretsmanager_secret_version" "credential_encryption_key" {
  secret_id     = aws_secretsmanager_secret.credential_encryption_key.id
  secret_string = var.credential_encryption_key

  lifecycle {
    ignore_changes = [secret_string]
  }
}

# ─── Docker Hub credentials (optional) ────────────────────────────────────────
resource "aws_secretsmanager_secret" "dockerhub" {
  count                   = local.dockerhub_enabled ? 1 : 0
  name                    = "${var.name_prefix}/dockerhub-credentials"
  description             = "Docker Hub credentials for private image pulls"
  recovery_window_in_days = local.recovery_window

  tags = merge(var.tags, { Name = "${var.name_prefix}-dockerhub-credentials" })
}

resource "aws_secretsmanager_secret_version" "dockerhub" {
  count     = local.dockerhub_enabled ? 1 : 0
  secret_id = aws_secretsmanager_secret.dockerhub[0].id
  secret_string = jsonencode({
    username = var.dockerhub_username
    password = var.dockerhub_token
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
