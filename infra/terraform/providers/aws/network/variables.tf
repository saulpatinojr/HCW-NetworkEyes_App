variable "name_prefix" {
  description = "Normalized name prefix for network resources"
  type        = string
}

variable "tags" {
  description = "Tags applied to network resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.40.0.0/16"
}

variable "availability_zones" {
  description = "Availability zones to deploy into (at least two required for RDS subnet group)"
  type        = list(string)
  nullable    = false
}

variable "subnet_public_cidrs" {
  description = "CIDR blocks for public subnets (NAT Gateway, ALB), one per availability zone"
  type        = list(string)
  default     = ["10.40.0.0/24", "10.40.1.0/24"]
  nullable    = false
}

variable "subnet_app_cidrs" {
  description = "CIDR blocks for the private application (ECS) subnets, one per availability zone"
  type        = list(string)
  default     = ["10.40.2.0/23", "10.40.4.0/23"]
  nullable    = false
}

variable "subnet_database_cidrs" {
  description = "CIDR blocks for the private database (RDS) subnets, one per availability zone"
  type        = list(string)
  default     = ["10.40.6.0/24", "10.40.7.0/24"]
  nullable    = false
}
