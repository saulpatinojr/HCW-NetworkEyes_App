variable "region" {
  description = "AWS region for CNA platform deployment"
  type        = string
  default     = "us-east-1"
}

variable "region_short" {
  description = "Short region code used in resource names"
  type        = string
  default     = "use1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "dev"
}

variable "project_name" {
  description = "Project name prefix"
  type        = string
  default     = "cna"
}

variable "vpc_cidr" {
  description = "CIDR block for the platform VPC"
  type        = string
  default     = "10.40.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones to deploy into (at least two required for RDS subnet group)"
  type        = list(string)
  default     = ["us-east-1a", "us-east-1b"]
  nullable    = false
}

variable "subnet_public_cidrs" {
  description = "CIDR blocks for public subnets, one per availability zone"
  type        = list(string)
  default     = ["10.40.0.0/24", "10.40.1.0/24"]
  nullable    = false
}

variable "subnet_app_cidrs" {
  description = "CIDR blocks for private application (ECS) subnets, one per availability zone"
  type        = list(string)
  default     = ["10.40.2.0/23", "10.40.4.0/23"]
  nullable    = false
}

variable "subnet_database_cidrs" {
  description = "CIDR blocks for private database (RDS) subnets, one per availability zone"
  type        = list(string)
  default     = ["10.40.6.0/24", "10.40.7.0/24"]
  nullable    = false
}
