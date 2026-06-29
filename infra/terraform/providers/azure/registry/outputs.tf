output "id" {
  description = "Resource ID of the container registry."
  value       = azurerm_container_registry.this.id
}

output "name" {
  description = "Registry name."
  value       = azurerm_container_registry.this.name
}

output "login_server" {
  description = "Registry login server (e.g. acrcnadevscus.azurecr.io) — used as the container_registry_server and image prefix."
  value       = azurerm_container_registry.this.login_server
}
