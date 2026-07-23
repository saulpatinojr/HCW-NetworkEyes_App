output "instance_id" {
  description = "RDS instance identifier"
  value       = aws_db_instance.this.id
}

output "instance_arn" {
  description = "RDS instance ARN"
  value       = aws_db_instance.this.arn
}

output "address" {
  description = "RDS instance hostname"
  value       = aws_db_instance.this.address
}

output "port" {
  description = "RDS instance port"
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Application database name"
  value       = aws_db_instance.this.db_name
}

output "connection_string" {
  description = "DATABASE_URL for Prisma / SQLAlchemy. Contains admin password — treat as sensitive."
  value       = "postgresql://${var.admin_username}:${urlencode(var.admin_password)}@${aws_db_instance.this.address}:${aws_db_instance.this.port}/${local.db_name}?sslmode=require"
  sensitive   = true
}
