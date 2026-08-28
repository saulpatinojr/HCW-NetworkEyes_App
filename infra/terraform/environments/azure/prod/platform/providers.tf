terraform {
  required_version = ">= 1.9.0, < 2.0.0"

  backend "azurerm" {}

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azapi = {
      source  = "azure/azapi"
      version = "~> 2.0"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }
}

provider "azurerm" {
  # The deploy identity is RG-scoped least-privilege and cannot perform
  # subscription-level provider registration (REVIEW.md R-007). Registration is
  # asserted read-only by workflow 100; azurerm must not attempt it itself.
  resource_provider_registrations = "none"

  features {
    resource_group {
      # Confirmed environment teardown must remove Azure-created child resources
      # that are not addressable in Terraform state, such as Smart Detection.
      prevent_deletion_if_contains_resources = false
    }
  }
  use_oidc = true
}

data "azurerm_client_config" "current" {}

provider "azapi" {
  use_oidc = true
}
