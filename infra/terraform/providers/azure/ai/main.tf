resource "azurerm_cognitive_account" "foundry" {
  name                          = var.foundry_account_name
  location                      = var.foundry_location
  resource_group_name           = var.resource_group_name
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = var.foundry_account_name
  project_management_enabled    = true
  local_auth_enabled            = false
  public_network_access_enabled = false

  identity {
    type = "SystemAssigned"
  }

  tags = merge(var.tags, local.foundry_tags)
}

resource "azapi_resource" "foundry_project" {
  type      = "Microsoft.CognitiveServices/accounts/projects@2025-06-01"
  name      = var.foundry_project_name
  parent_id = azurerm_cognitive_account.foundry.id
  location  = var.foundry_location

  body = {
    identity = {
      type = "SystemAssigned"
    }
    properties = {
      displayName = var.foundry_project_name
      description = "CNA ${var.environment} Foundry project hosting the Azure OpenAI deployment"
    }
  }

  tags = merge(var.tags, local.foundry_tags)
}
