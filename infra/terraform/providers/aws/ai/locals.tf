locals {
  # Region is embedded in the foundation-model ARN; account is omitted because
  # foundation models are AWS-owned (arn:...:bedrock:<region>::foundation-model/<id>).
  foundation_model_arns = [
    for m in var.model_ids :
    "arn:${data.aws_partition.current.partition}:bedrock:${data.aws_region.current.name}::foundation-model/${m}"
  ]
}
