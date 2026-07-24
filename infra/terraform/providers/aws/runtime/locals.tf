locals {
  # Dev deletes secrets immediately (0-day recovery window) so a teardown +
  # redeploy does not collide with a soft-deleted same-named secret. Prod keeps
  # the 30-day recovery window.
  recovery_window   = var.environment == "dev" ? 0 : 30
  dockerhub_enabled = var.dockerhub_username != ""
}
