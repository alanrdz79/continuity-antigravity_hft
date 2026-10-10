variable "project_id" {
  type        = string
  description = "The GCP Project ID where IAM service accounts and bindings are provisioned."
}

variable "environment" {
  type        = string
  description = "Deployment environment tag (e.g. production, staging, dev)."
  default     = "production"
}
