variable "project_name" {
  description = "Project name used in resource naming (mirrors Azure's var.project_name)"
  type        = string
  default     = "cna"
}

variable "environment" {
  description = "Deployment environment (dev or prod)"
  type        = string
  default     = "dev"
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "region_short" {
  description = "Short region code used in resource naming (mirrors Azure's var.region_short)"
  type        = string
  default     = "use1"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.40.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones for the subnets. Subnet CIDR lists must be the same length and aligned by index."
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
  nullable    = false
}

variable "subnet_public_cidrs" {
  description = "CIDR blocks for the public subnets (ALB, NAT gateways), one per AZ."
  type        = list(string)
  default     = ["10.40.0.0/24", "10.40.1.0/24"]
  nullable    = false
}

variable "subnet_app_cidrs" {
  description = "CIDR blocks for the application (private) subnets (ECS tasks), one per AZ."
  type        = list(string)
  default     = ["10.40.10.0/24", "10.40.11.0/24"]
  nullable    = false
}

variable "subnet_database_cidrs" {
  description = "CIDR blocks for the database subnets (RDS), one per AZ."
  type        = list(string)
  default     = ["10.40.20.0/24", "10.40.21.0/24"]
  nullable    = false
}

variable "single_nat_gateway" {
  description = "Use a single shared NAT gateway (dev cost saving) instead of one per AZ (prod HA)."
  type        = bool
  default     = true
}

variable "flow_log_retention_days" {
  description = "Retention, in days, for the VPC flow-log CloudWatch log group."
  type        = number
  default     = 30
}
