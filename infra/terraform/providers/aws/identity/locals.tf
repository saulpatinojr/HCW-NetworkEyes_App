locals {
  task_execution_role_name = "${var.name_prefix}-ecs-exec-role"
  task_role_name           = "${var.name_prefix}-ecs-task-role"
  kms_key_alias            = "alias/${var.name_prefix}-key"
}
