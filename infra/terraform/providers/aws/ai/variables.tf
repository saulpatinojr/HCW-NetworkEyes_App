variable "name_prefix" {
  description = "Normalized name prefix for AI resources (e.g. cna-dev-use1)"
  type        = string
}

variable "tags" {
  description = "Tags applied to AI resources"
  type        = map(string)
  default     = {}
  nullable    = false
}

variable "model_ids" {
  description = "Bedrock foundation model IDs the task role may invoke. NOTE: model access must be enabled manually in the Bedrock console per region/account before invocation succeeds."
  type        = list(string)
  default     = ["anthropic.claude-3-5-sonnet-20240620-v1:0"]
  nullable    = false
}

variable "enable_guardrail" {
  description = "Create a Bedrock guardrail. Left off by default; the platform may keep using external OpenAI, in which case only the IAM policy document is consumed."
  type        = bool
  default     = false
}
