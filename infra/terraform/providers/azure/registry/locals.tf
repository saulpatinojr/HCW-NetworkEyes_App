locals {
  # ACR names are 5-50 chars, alphanumeric only, globally unique. Derive from the
  # name prefix with hyphens stripped, e.g. cna-dev-scus -> acrcnadevscus.
  registry_name = "acr${replace(var.name_prefix, "-", "")}${var.name_suffix}"
}
