output "instance_id" {
  description = "RDS instance identifier."
  value       = aws_db_instance.this.id
}

output "instance_arn" {
  description = "RDS instance ARN."
  value       = aws_db_instance.this.arn
}

output "address" {
  description = "RDS instance hostname (no port). Passed to runtime for the DATABASE_URL secret."
  value       = aws_db_instance.this.address
}

output "endpoint" {
  description = "RDS connection endpoint in host:port form."
  value       = aws_db_instance.this.endpoint
}

output "port" {
  description = "RDS listening port."
  value       = aws_db_instance.this.port
}

output "db_name" {
  description = "Initial database name."
  value       = aws_db_instance.this.db_name
}
