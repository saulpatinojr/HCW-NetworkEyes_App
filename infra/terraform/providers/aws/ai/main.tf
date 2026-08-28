# =============================================================================
# AI — Bedrock model management + invoke permissions. Mirrors the Azure ai
# module (AI Foundry account + chat model deployment). This module:
#   1. Creates an IAM policy document for bedrock:InvokeModel (consumed by identity)
#   2. Optionally provisions a Bedrock inference profile for deterministic routing
#   3. Optionally provisions on-demand throughput for the chat model
#   4. Optionally creates a Bedrock guardrail for content filtering
#
# NOTE: Bedrock foundation-model access must still be enabled manually in the
# Bedrock console per region/account before any invocation succeeds. This is an
# AWS platform constraint with no Terraform resource equivalent.
# =============================================================================

data "aws_partition" "current" {}
data "aws_region" "current" {}
data "aws_caller_identity" "current" {}

# ─── IAM policy document (consumed by identity module) ────────────────────────
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "InvokeFoundationModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = local.all_invocable_arns
  }

  # Allow inference profile operations when an inference profile is created.
  dynamic "statement" {
    for_each = var.enable_inference_profile ? [1] : []
    content {
      sid    = "InvokeInferenceProfile"
      effect = "Allow"
      actions = [
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:GetInferenceProfile",
      ]
      resources = [
        "arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:inference-profile/${var.name_prefix}-*"
      ]
    }
  }
}

# ─── Inference Profile (mirrors Azure's cognitive_deployment) ─────────────────
# An application inference profile provides a stable, named endpoint that can
# route to one or more foundation models — analogous to Azure's deployment name
# (e.g. "gpt-chat-latest") which the app references via AZURE_OPENAI_DEPLOYMENT.
# The app references this profile by ARN/ID rather than a raw model ID, enabling
# model version rotation without app config changes.
resource "aws_bedrock_inference_profile" "chat" {
  count = var.enable_inference_profile ? 1 : 0

  name        = local.inference_profile_name
  description = "CNA ${var.environment} chat inference profile — mirrors Azure AI Foundry gpt-chat-latest deployment"
  # `type` is read-only on this resource: a profile you create is APPLICATION
  # by definition (SYSTEM_DEFINED profiles are AWS-managed and only referenced).

  model_source {
    copy_from = local.chat_model_arn
  }

  tags = merge(var.tags, { Name = local.inference_profile_name })
}

# ─── Provisioned Model Throughput (optional, prod-grade) ──────────────────────
# Mirrors Azure's cognitive_deployment capacity/SKU. Provides dedicated
# throughput for predictable latency. Disabled by default (on-demand is fine for
# dev); enable in prod for SLA-backed performance.
resource "aws_bedrock_provisioned_model_throughput" "chat" {
  count = var.enable_provisioned_throughput ? 1 : 0

  provisioned_model_name = "${var.name_prefix}-chat-pmt"
  model_arn              = local.chat_model_arn
  model_units            = var.provisioned_model_units

  # Provisioned throughput has a commitment period; lifecycle prevents
  # accidental destruction that would lose the commitment.
  lifecycle {
    prevent_destroy = false # Set to true in prod after first apply
  }

  tags = merge(var.tags, { Name = "${var.name_prefix}-chat-pmt" })
}

# ─── Bedrock Guardrail ────────────────────────────────────────────────────────
resource "aws_bedrock_guardrail" "this" {
  count = var.enable_guardrail ? 1 : 0

  name                      = "${var.name_prefix}-guardrail"
  description               = "CNA platform content guardrail — blocks harmful inputs/outputs"
  blocked_input_messaging   = "This request was blocked by the content guardrail."
  blocked_outputs_messaging = "The response was blocked by the content guardrail."

  tags = merge(var.tags, { Name = "${var.name_prefix}-guardrail" })
}
