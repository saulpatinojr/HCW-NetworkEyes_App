terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  # backend "s3" {} left empty deliberately -- populated via -backend-config
  # at `terraform init` time, matching the azurerm backend pattern the Azure
  # environments use (see environments/azure/*/workload/providers.tf and the
  # 000-bootstrap-backend.yml workflow, whose AWS equivalent would provision
  # the S3 state bucket + DynamoDB lock table).
  backend "s3" {}

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = local.tags
  }
}
