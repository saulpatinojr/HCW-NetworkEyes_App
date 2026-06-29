output "foundry_resource_group_name" {
  value = var.resource_group_name
}

output "foundry_account_id" {
  value = azurerm_cognitive_account.foundry.id
}

output "foundry_account_name" {
  value = azurerm_cognitive_account.foundry.name
}

output "foundry_endpoint" {
  value = azurerm_cognitive_account.foundry.endpoint
}

output "foundry_project_id" {
  value = azapi_resource.foundry_project.id
}

output "foundry_project_name" {
  value = var.foundry_project_name
}
