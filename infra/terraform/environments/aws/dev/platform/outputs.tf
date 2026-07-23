output "vpc_id" {
  description = "VPC ID"
  value       = module.network.vpc_id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = module.network.vpc_cidr
}

output "public_subnet_ids" {
  description = "Public subnet IDs"
  value       = module.network.public_subnet_ids
}

output "app_subnet_ids" {
  description = "Private application subnet IDs"
  value       = module.network.app_subnet_ids
}

output "database_subnet_ids" {
  description = "Private database subnet IDs"
  value       = module.network.database_subnet_ids
}

output "alb_security_group_id" {
  description = "ALB security group ID"
  value       = module.network.alb_security_group_id
}

output "app_security_group_id" {
  description = "Application (ECS) security group ID"
  value       = module.network.app_security_group_id
}

output "database_security_group_id" {
  description = "Database (RDS) security group ID"
  value       = module.network.database_security_group_id
}
