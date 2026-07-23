output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.this.id
}

output "vpc_cidr" {
  description = "VPC CIDR block"
  value       = aws_vpc.this.cidr_block
}

output "public_subnet_ids" {
  description = "IDs of the public subnets (NAT Gateway, ALB)"
  value       = aws_subnet.public[*].id
}

output "app_subnet_ids" {
  description = "IDs of the private application (ECS) subnets"
  value       = aws_subnet.app[*].id
}

output "database_subnet_ids" {
  description = "IDs of the private database (RDS) subnets"
  value       = aws_subnet.database[*].id
}

output "alb_security_group_id" {
  description = "Security group ID for the Application Load Balancer"
  value       = aws_security_group.alb.id
}

output "app_security_group_id" {
  description = "Security group ID for ECS application tasks"
  value       = aws_security_group.app.id
}

output "database_security_group_id" {
  description = "Security group ID for RDS PostgreSQL"
  value       = aws_security_group.database.id
}
