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
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
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
    cognitive_account {
      # Cognitive/AIServices accounts soft-delete by default and keep their name
      # reserved (subscription+region scoped). With a static account name this
      # blocks recreate with a 409 "soft-deleted, must purge". Purge on a
      # Terraform-managed destroy so the name frees immediately. NOTE: this only
      # fires on `terraform destroy`; the RG-level `az group delete` teardown
      # bypasses it, so 330-teardown.yml also purges by name as a backstop.
      purge_soft_delete_on_destroy = true
    }
    key_vault {
      # This vault has purge protection ENABLED (tenant policy; see workload
      # main.tf key_vault_purge_protection_enabled = true), so a soft-deleted
      # vault CANNOT be purged before the 90-day retention elapses — not by this
      # flag, not by az keyvault purge, not by anyone. recover_soft_deleted_key_vaults
      # lets a re-deploy RECOVER the same-named vault instead of failing. The
      # 'already exists / needs import' on individual secrets after a state wipe is
      # handled by recovering the vault (and bumping key_vault_name_suffix only as
      # a last resort). purge_soft_delete_on_destroy is left at its true default
      # but is a no-op while purge protection is on.
      recover_soft_deleted_key_vaults = true
    }
  }
  use_oidc = true
}

data "azurerm_client_config" "current" {}

provider "azapi" {
  use_oidc = true
}

provider "github" {
  owner = var.github_owner
  token = var.github_token
}
