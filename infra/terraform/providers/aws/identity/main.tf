data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

# ─── KMS ──────────────────────────────────────────────────────────────────────
# Customer-managed key for encrypting Secrets Manager secrets and RDS storage.
# Mirrors Azure Key Vault in the identity module — both are the trust anchor
# that downstream modules (compute, database, security) reference for
# encryption and secret access.

resource "aws_kms_key" "this" {
  description             = "CNA platform encryption key — ${var.name_prefix}"
  deletion_window_in_days = var.kms_deletion_window_days
  enable_key_rotation     = true
  tags                    = var.tags
}

resource "aws_kms_alias" "this" {
  name          = local.kms_key_alias
  target_key_id = aws_kms_key.this.key_id
}

# ─── IAM assume-role policy ───────────────────────────────────────────────────

data "aws_iam_policy_document" "ecs_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ─── ECS Task Execution Role ──────────────────────────────────────────────────
# Grants the ECS agent permission to pull container images from ECR and
# write container logs to CloudWatch. Mirrors the Azure managed-identity
# pattern used for Container Apps image pull / log write.

resource "aws_iam_role" "ecs_task_execution" {
  name               = local.task_execution_role_name
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allows ECS agent to inject secrets from Secrets Manager into container
# environment variables at container startup. Scoped by name prefix.
data "aws_iam_policy_document" "ecs_task_execution_secrets" {
  statement {
    sid     = "AllowSecretsManagerRead"
    actions = ["secretsmanager:GetSecretValue"]
    resources = [
      "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.name_prefix}/*"
    ]
  }

  statement {
    sid       = "AllowKMSDecrypt"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this.arn]
  }
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name   = "${var.name_prefix}-exec-secrets"
  role   = aws_iam_role.ecs_task_execution.name
  policy = data.aws_iam_policy_document.ecs_task_execution_secrets.json
}

# ─── ECS Task Role ────────────────────────────────────────────────────────────
# Granted to running containers — mirrors Azure user-assigned managed identity.
# Allows application-level AWS calls (Secrets Manager read, KMS decrypt/encrypt).

resource "aws_iam_role" "ecs_task" {
  name               = local.task_role_name
  assume_role_policy = data.aws_iam_policy_document.ecs_assume_role.json
  tags               = var.tags
}

data "aws_iam_policy_document" "ecs_task_app" {
  statement {
    sid     = "AllowSecretsManagerRead"
    actions = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [
      "arn:aws:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.name_prefix}/*"
    ]
  }

  statement {
    sid       = "AllowKMSDecrypt"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.this.arn]
  }
}

resource "aws_iam_role_policy" "ecs_task_app" {
  name   = "${var.name_prefix}-task-app"
  role   = aws_iam_role.ecs_task.name
  policy = data.aws_iam_policy_document.ecs_task_app.json
}
