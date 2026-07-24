output "database_url_secret_arn" {
  description = "ARN of the DATABASE_URL secret."
  value       = aws_secretsmanager_secret.database_url.arn
}

output "database_url_secret_name" {
  description = "Name of the DATABASE_URL secret."
  value       = aws_secretsmanager_secret.database_url.name
}

output "nextauth_secret_arn" {
  description = "ARN of the Auth.js signing-secret secret."
  value       = aws_secretsmanager_secret.nextauth_secret.arn
}

output "nextauth_secret_name" {
  description = "Name of the Auth.js signing-secret secret."
  value       = aws_secretsmanager_secret.nextauth_secret.name
}

output "entra_client_secret_arn" {
  description = "ARN of the Entra ID client-secret secret."
  value       = aws_secretsmanager_secret.entra_client_secret.arn
}

output "entra_client_secret_name" {
  description = "Name of the Entra ID client-secret secret."
  value       = aws_secretsmanager_secret.entra_client_secret.name
}

output "credential_encryption_key_secret_arn" {
  description = "ARN of the credential-encryption-key secret."
  value       = aws_secretsmanager_secret.credential_encryption_key.arn
}

output "credential_encryption_key_secret_name" {
  description = "Name of the credential-encryption-key secret."
  value       = aws_secretsmanager_secret.credential_encryption_key.name
}

output "dockerhub_secret_arn" {
  description = "ARN of the Docker Hub credentials secret, or null when Docker Hub is not configured."
  value       = one(aws_secretsmanager_secret.dockerhub[*].arn)
}

output "dockerhub_secret_name" {
  description = "Name of the Docker Hub credentials secret, or null when Docker Hub is not configured."
  value       = one(aws_secretsmanager_secret.dockerhub[*].name)
}
