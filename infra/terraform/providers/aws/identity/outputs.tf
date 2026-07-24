output "kms_key_arn" {
  description = "ARN of the customer-managed KMS key (consumed by storage, database, observability for encryption)."
  value       = aws_kms_key.this.arn
}

output "kms_key_id" {
  description = "Key ID of the customer-managed KMS key."
  value       = aws_kms_key.this.key_id
}

output "kms_key_alias" {
  description = "Alias name of the customer-managed KMS key."
  value       = aws_kms_alias.this.name
}

output "task_execution_role_arn" {
  description = "ARN of the ECS task execution role (image pull, log write, secret fetch). Passed to the compute module."
  value       = aws_iam_role.ecs_task_execution.arn
}

output "task_execution_role_name" {
  description = "Name of the ECS task execution role."
  value       = aws_iam_role.ecs_task_execution.name
}

output "task_role_arn" {
  description = "ARN of the ECS task role (application identity). Passed to the compute module."
  value       = aws_iam_role.ecs_task.arn
}

output "task_role_name" {
  description = "Name of the ECS task role."
  value       = aws_iam_role.ecs_task.name
}

output "github_deploy_role_arn" {
  description = "ARN of the GitHub Actions OIDC deploy role."
  value       = aws_iam_role.github_deploy.arn
}
