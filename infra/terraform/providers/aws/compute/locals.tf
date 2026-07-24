locals {
  cluster_name = "${var.name_prefix}-cluster"

  api_service_name    = "${var.name_prefix}-api"
  worker_service_name = "${var.name_prefix}-worker"
  web_service_name    = "${var.name_prefix}-web"

  # Container names are load-bearing: the service load_balancer block references
  # them, so they must match the container_definitions name exactly.
  api_container_name    = "cna-api"
  worker_container_name = "cna-worker"
  web_container_name    = "cna-web"

  # HTTPS listener (and therefore the API path rule) exists only when a cert ARN
  # is supplied — an ACM cert is created/validated externally (spec §12.2).
  https_enabled = var.alb_certificate_arn != null

  # FinOps: collapse desired_count to zero when scale-to-zero is on.
  api_desired_count    = var.enable_scale_to_zero ? 0 : var.api_min_count
  worker_desired_count = var.enable_scale_to_zero ? 0 : var.worker_min_count
  web_desired_count    = var.enable_scale_to_zero ? 0 : var.web_min_count

  # Container-definition env/secret shapes derived from the input maps.
  api_environment    = [for k, v in var.api_environment : { name = k, value = v }]
  worker_environment = [for k, v in var.worker_environment : { name = k, value = v }]
  web_environment    = [for k, v in var.web_environment : { name = k, value = v }]

  api_secrets    = [for k, arn in var.api_secrets : { name = k, valueFrom = arn }]
  worker_secrets = [for k, arn in var.worker_secrets : { name = k, valueFrom = arn }]
  web_secrets    = [for k, arn in var.web_secrets : { name = k, valueFrom = arn }]

  repository_credentials = var.dockerhub_secret_arn != null ? { credentialsParameter = var.dockerhub_secret_arn } : null
}
