locals {
  api_log_group_name    = "/ecs/${var.name_prefix}/api"
  worker_log_group_name = "/ecs/${var.name_prefix}/worker"
  web_log_group_name    = "/ecs/${var.name_prefix}/web"

  # ECS cluster/service and RDS instance names are deterministic from
  # name_prefix (see compute + database modules), so the alarms can reference
  # them by dimension even though observability applies BEFORE compute — the
  # alarms simply report INSUFFICIENT_DATA until those resources exist.
  cluster_name   = "${var.name_prefix}-cluster"
  db_instance_id = "${var.name_prefix}-psql"

  services = {
    api    = "${var.name_prefix}-api"
    worker = "${var.name_prefix}-worker"
    web    = "${var.name_prefix}-web"
  }

  alarm_services = var.enable_alarms ? local.services : {}

  alarms_topic_arn = var.sns_topic_arn != null ? var.sns_topic_arn : one(aws_sns_topic.alarms[*].arn)
  alarm_actions    = local.alarms_topic_arn != null ? [local.alarms_topic_arn] : []
}
