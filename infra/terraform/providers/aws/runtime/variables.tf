variable "name_prefix" {
  description = "Normalized name prefix for runtime resources (e.g. cna-dev-use1). Also the secret namespace: $${name_prefix}/<secret>."
  type        = string
}

variable "tags" {
  description = "Tags applied to runtime resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "environment" {
  description = "Deployment environment (dev or prod). Controls the secret recovery window (0 in dev, 30 in prod)."
  type        = string
}

variable "db_endpoint" {
  description = "RDS endpoint in host:port form (from the database module) used to build the DATABASE_URL connection string."
  type        = string
}

variable "db_username" {
  description = "Database master username used in the DATABASE_URL connection string."
  type        = string
}

variable "db_password" {
  description = "Database master password used in the DATABASE_URL connection string."
  type        = string
  sensitive   = true
}

variable "db_name" {
  description = "Database name used in the DATABASE_URL connection string."
  type        = string
}

variable "nextauth_secret" {
  description = "Auth.js JWT signing secret."
  type        = string
  sensitive   = true
}

variable "entra_client_secret" {
  description = "Entra ID OAuth client secret."
  type        = string
  sensitive   = true
}

variable "credential_encryption_key" {
  description = "Base64-encoded AES-256 key for encrypting stored credentials."
  type        = string
  sensitive   = true
}

variable "dockerhub_username" {
  description = "Docker Hub username for private image pulls. Empty string disables the Docker Hub secret."
  type        = string
  default     = ""
}

variable "dockerhub_token" {
  description = "Docker Hub access token for private image pulls."
  type        = string
  sensitive   = true
  default     = ""
}
