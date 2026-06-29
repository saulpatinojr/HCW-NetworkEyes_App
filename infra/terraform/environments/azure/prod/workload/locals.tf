locals {
  name_prefix = "${var.project_name}-${var.environment}-${var.region_short}"
  tags = {
    Environment = title(var.environment)
    CostCenter  = "CNA"
    Owner       = "cna-platform"
    Project     = var.project_name
    ManagedBy   = "terraform"
  }

  optional_outbound_urls = compact([
    trimspace(var.azure_mcp_endpoint) != "" && lower(trimspace(var.azure_mcp_endpoint)) != "none" && startswith(lower(trimspace(var.azure_mcp_endpoint)), "http") ? trimspace(var.azure_mcp_endpoint) : null,
    trimspace(var.aws_mcp_endpoint) != "" && lower(trimspace(var.aws_mcp_endpoint)) != "none" && startswith(lower(trimspace(var.aws_mcp_endpoint)), "http") ? trimspace(var.aws_mcp_endpoint) : null,
    trimspace(var.drawio_mcp_url) != "" && lower(trimspace(var.drawio_mcp_url)) != "none" && startswith(lower(trimspace(var.drawio_mcp_url)), "http") ? trimspace(var.drawio_mcp_url) : null,
  ])

  optional_outbound_fqdns = [
    for url in local.optional_outbound_urls : split("/", replace(replace(url, "https://", ""), "http://", ""))[0]
  ]

  # Host the web app calls for Azure OpenAI (the AIServices account's
  # services.ai.azure.com endpoint). Allowed through the egress firewall.
  azure_openai_endpoint_host = split(
    "/",
    replace(
      replace(var.azure_openai_endpoint, "https://", ""),
      "http://",
      ""
    )
  )[0]

  key_vault_host = split("/", trimprefix(module.identity.key_vault_uri, "https://"))[0]

  firewall_application_rule_fqdns = sort(distinct(concat(
    [
      split("/", var.api_image)[0],
      split("/", var.worker_image)[0],
      split("/", var.web_image)[0],
      "index.docker.io",
      "registry-1.docker.io",
      "auth.docker.io",
      "production.cloudfront.docker.com",
      "pkg-containers.githubusercontent.com",
      "${module.storage.storage_account_name}.blob.core.windows.net",
      local.key_vault_host,
      local.azure_openai_endpoint_host,
      "login.microsoftonline.com",
      "management.azure.com",
    ],
    local.optional_outbound_fqdns,
  )))
}
