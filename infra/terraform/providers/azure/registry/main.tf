# Azure Container Registry for first-party CNA images. Pulled by the Container
# Apps via managed identity (AcrPull granted in the workload root); pushed by the
# build pipeline via the deploy identity (AcrPush). Admin user is disabled — all
# auth is Entra/managed-identity, consistent with the rest of the platform.
#
# SKU Basic + public endpoint + egress-firewall allowlist is the current posture.
# A private endpoint (Premium) is a later hardening follow-up — see docs/adr/0005.
resource "azurerm_container_registry" "this" {
  name                          = local.registry_name
  resource_group_name           = var.resource_group_name
  location                      = var.location
  sku                           = var.sku
  admin_enabled                 = false
  public_network_access_enabled = true

  tags = var.tags
}
