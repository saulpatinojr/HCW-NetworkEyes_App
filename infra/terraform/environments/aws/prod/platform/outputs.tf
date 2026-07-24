output "vpc_id" {
  description = "VPC ID."
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "VPC CIDR block."
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "Public subnet IDs (ALB, NAT gateways)."
  value       = aws_subnet.public[*].id
}

output "app_subnet_ids" {
  description = "Application (private) subnet IDs (ECS tasks)."
  value       = aws_subnet.app[*].id
}

output "database_subnet_ids" {
  description = "Database subnet IDs (RDS)."
  value       = aws_subnet.database[*].id
}

output "alb_security_group_id" {
  description = "ALB security group ID."
  value       = aws_security_group.alb.id
}

output "app_security_group_id" {
  description = "Application (ECS task) security group ID."
  value       = aws_security_group.app.id
}

output "database_security_group_id" {
  description = "Database (RDS) security group ID."
  value       = aws_security_group.database.id
}
