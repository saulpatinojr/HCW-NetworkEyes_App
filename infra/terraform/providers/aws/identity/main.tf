# =============================================================================
# Identity — KMS customer-managed key, ECS roles, GitHub OIDC deploy role
# (source: migrate/iam.tf). Mirrors the Azure identity module (Key Vault + KMS,
# managed identity + IAM roles).
# =============================================================================

data "aws_caller_identity" "current" {}
data "aws_partition" "current" {}
data "aws_region" "current" {}

# ─── Customer-managed KMS key ─────────────────────────────────────────────────
resource "aws_kms_key" "this" {
  description             = "${var.name_prefix} customer-managed key (S3, RDS, Secrets Manager, CloudWatch Logs)"
  enable_key_rotation     = true
  deletion_window_in_days = var.kms_deletion_window_days

  tags = merge(var.tags, { Name = "${var.name_prefix}-key" })
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.name_prefix}-key"
  target_key_id = aws_kms_key.this.key_id
}

# ─── ECS trust policy (shared by execution + task roles) ──────────────────────
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    sid     = "EcsTasksAssume"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# ─── ECS task execution role ──────────────────────────────────────────────────
# Used by the ECS agent to pull images, write logs, and fetch secrets.
resource "aws_iam_role" "ecs_task_execution" {
  name               = local.execution_role_name
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = merge(var.tags, { Name = local.execution_role_name })
}

resource "aws_iam_role_policy_attachment" "ecs_task_execution_managed" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "ecs_task_execution_secrets" {
  statement {
    sid       = "ReadNamespacedSecrets"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.secret_arn_wildcard]
  }

  statement {
    sid       = "DecryptWithCmk"
    effect    = "Allow"
    actions   = ["kms:Decrypt"]
    resources = [aws_kms_key.this.arn]
  }
}

resource "aws_iam_role_policy" "ecs_task_execution_secrets" {
  name   = "${var.name_prefix}-ecs-execution-secrets"
  role   = aws_iam_role.ecs_task_execution.id
  policy = data.aws_iam_policy_document.ecs_task_execution_secrets.json
}

# ─── ECS task role (application identity) ─────────────────────────────────────
resource "aws_iam_role" "ecs_task" {
  name               = local.task_role_name
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json

  tags = merge(var.tags, { Name = local.task_role_name })
}

data "aws_iam_policy_document" "ecs_task_app" {
  statement {
    sid    = "ReadNamespacedSecrets"
    effect = "Allow"
    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]
    resources = [local.secret_arn_wildcard]
  }

  statement {
    sid    = "UseCmk"
    effect = "Allow"
    actions = [
      "kms:Decrypt",
      "kms:GenerateDataKey",
    ]
    resources = [aws_kms_key.this.arn]
  }

  statement {
    sid    = "ArtifactsBucketAccess"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
    ]
    resources = [
      local.artifacts_bucket_arn,
      local.artifacts_objects_arn,
    ]
  }
}

resource "aws_iam_role_policy" "ecs_task_app" {
  name   = "${var.name_prefix}-ecs-task-app"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_app.json
}

# Bedrock invoke permissions are produced by the ai module and attached here so
# the task role stays the single application identity (avoids a second role).
resource "aws_iam_role_policy" "ecs_task_bedrock" {
  count  = var.task_bedrock_policy_json != null ? 1 : 0
  name   = "${var.name_prefix}-ecs-task-bedrock"
  role   = aws_iam_role.ecs_task.id
  policy = var.task_bedrock_policy_json
}

# X-Ray daemon needs xray:PutTraceSegments + xray:PutTelemetryRecords.
# Attached to the task role so the sidecar inherits it.
resource "aws_iam_role_policy" "ecs_task_xray" {
  count = var.enable_xray ? 1 : 0
  name  = "${var.name_prefix}-ecs-task-xray"
  role  = aws_iam_role.ecs_task.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "XRayDaemonWrite"
        Effect = "Allow"
        Action = [
          "xray:PutTraceSegments",
          "xray:PutTelemetryRecords",
          "xray:GetSamplingRules",
          "xray:GetSamplingTargets",
          "xray:GetSamplingStatisticSummaries",
        ]
        Resource = ["*"]
      }
    ]
  })
}

# ─── GitHub Actions OIDC deploy role ──────────────────────────────────────────
# thumbprint_list is intentionally omitted (TODO.md T-203). AWS provider 5.x
# validates GitHub's OIDC endpoint against its own trusted CA store, so the
# legacy thumbprint is no longer required. This absence is deliberate — do not
# "fix" it by adding one back.
#
# In particular, do not copy the value from the superseded migrate/ root:
# migrate/iam.tf sets thumbprint_list to a placeholder of forty `f`s, which is
# not a real thumbprint and never was. migrate/ is queued for retirement in
# TODO.md T-401.
#
# Deploy note: AWS permits exactly ONE GitHub OIDC provider per account. If the
# target account already has one — likely if anything else in the org deploys
# from GitHub Actions — this resource must be imported rather than created, or
# the duplicate create fails the entire apply:
#
#   terraform import module.identity.aws_iam_openid_connect_provider.github \
#     arn:aws:iam::<account-id>:oidc-provider/token.actions.githubusercontent.com
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]

  tags = merge(var.tags, { Name = "${var.name_prefix}-github-oidc" })
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    sid     = "GitHubOidc"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_owner}/${var.github_repository}:*"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = local.deploy_role_name
  assume_role_policy = data.aws_iam_policy_document.github_assume.json

  tags = merge(var.tags, { Name = local.deploy_role_name })
}

# Assessment reader roles (parity with Azure Global Reader + Security Reader +
# Billing Reader).
resource "aws_iam_role_policy_attachment" "deploy_readonly" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy_attachment" "deploy_security_audit" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/SecurityAudit"
}

resource "aws_iam_role_policy_attachment" "deploy_billing_reader" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/AWSBillingReadOnlyAccess"
}

# Deploy write permissions — ECS is scoped to Project-tagged resources; the
# broader infra actions are required for a full Terraform apply of this stack.
resource "aws_iam_policy" "deploy_write" {
  name = "${var.name_prefix}-deploy-write"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ECSTagScoped"
        Effect   = "Allow"
        Action   = ["ecs:*"]
        Resource = ["*"]
        Condition = {
          StringEquals = { "aws:ResourceTag/Project" = var.project_name }
        }
      },
      {
        Sid    = "InfraManagement"
        Effect = "Allow"
        Action = [
          "ec2:*",
          "elasticloadbalancing:*",
          "rds:*",
          "s3:*",
          "secretsmanager:*",
          "cloudfront:*",
          "wafv2:*",
          "logs:*",
          "iam:*",
          "kms:*",
          "cloudwatch:*",
          "application-autoscaling:*",
        ]
        Resource = ["*"]
      },
      {
        Sid    = "TerraformState"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:DeleteItem",
        ]
        Resource = ["*"]
      },
    ]
  })
}

resource "aws_iam_role_policy_attachment" "deploy_write" {
  role       = aws_iam_role.github_deploy.name
  policy_arn = aws_iam_policy.deploy_write.arn
}
