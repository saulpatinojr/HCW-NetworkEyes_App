terraform {
  required_version = "~> 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
      # WAF for CloudFront must be created in us-east-1. The workload root passes
      # providers = { aws.us_east_1 = aws.us_east_1 }. The default (unaliased)
      # aws provider is used for the distribution, OAC, and bucket policy.
      configuration_aliases = [aws.us_east_1]
    }
  }
}
