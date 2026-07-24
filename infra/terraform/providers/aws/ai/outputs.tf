output "task_bedrock_policy_json" {
  description = "IAM policy JSON granting bedrock:InvokeModel on the configured foundation models. Consumed by the identity module and attached to the ECS task role."
  value       = data.aws_iam_policy_document.bedrock_invoke.json
}

output "guardrail_id" {
  description = "Bedrock guardrail ID, or null when enable_guardrail is false."
  value       = one(aws_bedrock_guardrail.this[*].guardrail_id)
}

output "guardrail_arn" {
  description = "Bedrock guardrail ARN, or null when enable_guardrail is false."
  value       = one(aws_bedrock_guardrail.this[*].guardrail_arn)
}
