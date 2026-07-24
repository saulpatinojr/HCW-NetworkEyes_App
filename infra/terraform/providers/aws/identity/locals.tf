locals {
  execution_role_name = "${var.name_prefix}-ecs-execution"
  task_role_name      = "${var.name_prefix}-ecs-task"
  deploy_role_name    = "${var.name_prefix}-github-deploy"

  # Secrets and artifact buckets are named ${name_prefix}/* and
  # ${name_prefix}-artifacts-* respectively. Granting by name-prefix wildcard
  # (rather than importing the concrete ARNs from the runtime/storage modules)
  # keeps identity free of a dependency cycle — see spec §12.1.
  secret_arn_wildcard   = "arn:${data.aws_partition.current.partition}:secretsmanager:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:secret:${var.name_prefix}/*"
  artifacts_bucket_arn  = "arn:${data.aws_partition.current.partition}:s3:::${var.name_prefix}-artifacts-*"
  artifacts_objects_arn = "arn:${data.aws_partition.current.partition}:s3:::${var.name_prefix}-artifacts-*/*"
}
