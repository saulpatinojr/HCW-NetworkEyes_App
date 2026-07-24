# =============================================================================
# AI — Bedrock invoke permissions (IAM-centric). No migrate equivalent; mirrors
# the Azure ai module's role as the AI access boundary.
#
# PLACEHOLDER: Bedrock foundation-model access must be enabled manually in the
# Bedrock console per region/account. This module only grants IAM permission to
# invoke; it does not (and cannot) grant model access.
# =============================================================================

data "aws_partition" "current" {}
data "aws_region" "current" {}

data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    sid    = "InvokeFoundationModels"
    effect = "Allow"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = local.foundation_model_arns
  }
}

resource "aws_bedrock_guardrail" "this" {
  count = var.enable_guardrail ? 1 : 0

  name                      = "${var.name_prefix}-guardrail"
  blocked_input_messaging   = "This request was blocked by the content guardrail."
  blocked_outputs_messaging = "The response was blocked by the content guardrail."

  tags = merge(var.tags, { Name = "${var.name_prefix}-guardrail" })
}
