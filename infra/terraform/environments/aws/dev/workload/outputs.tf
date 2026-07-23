output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = module.compute.cluster_name
}

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = module.compute.alb_dns_name
}

output "cloudfront_domain_name" {
  description = "CloudFront distribution domain name"
  value       = module.security.cloudfront_domain_name
}

output "kms_key_arn" {
  description = "KMS key ARN for platform encryption"
  value       = module.identity.kms_key_arn
}

output "task_execution_role_arn" {
  description = "ECS task execution role ARN"
  value       = module.identity.task_execution_role_arn
}

output "task_role_arn" {
  description = "ECS task role ARN"
  value       = module.identity.task_role_arn
}

output "db_address" {
  description = "RDS instance hostname"
  value       = module.database.address
}

output "db_name" {
  description = "Application database name"
  value       = module.database.db_name
}
