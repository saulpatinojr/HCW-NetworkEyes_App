locals {
  cluster_name     = "${var.name_prefix}-ecs"
  api_service_name = "${var.name_prefix}-svc-api"
  worker_service_name = "${var.name_prefix}-svc-worker"
  web_service_name = "${var.name_prefix}-svc-web"
}
