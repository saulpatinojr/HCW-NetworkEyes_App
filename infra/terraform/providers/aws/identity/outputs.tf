output "kms_key_arn" {
  description = "ARN of the CNA platform KMS encryption key"
  value       = aws_kms_key.this.arn
}

output "kms_key_id" {
  description = "ID of the CNA platform KMS encryption key"
  value       = aws_kms_key.this.key_id
}

output "kms_key_alias" {
  description = "Alias of the CNA platform KMS encryption key"
  value       = aws_kms_alias.this.name
}

output "task_execution_role_arn" {
  description = "ARN of the ECS task execution IAM role (used by the ECS agent for image pull and log write)"
  value       = aws_iam_role.ecs_task_execution.arn
}

output "task_execution_role_name" {
  description = "Name of the ECS task execution IAM role"
  value       = aws_iam_role.ecs_task_execution.name
}

output "task_role_arn" {
  description = "ARN of the ECS task IAM role granted to running containers"
  value       = aws_iam_role.ecs_task.arn
}

output "task_role_name" {
  description = "Name of the ECS task IAM role"
  value       = aws_iam_role.ecs_task.name
}
