# ==============================================================================
# PROPOSED ADDITIONS TO ROOT variables.tf FOR MILESTONE 4
# File: variables.tf
# ==============================================================================

variable "enable_serverless_vpc_connector" {
  description = "Enable Serverless VPC Access connector for Cloud Function to reach private Memorystore Redis"
  type        = bool
  default     = true
}

variable "serverless_vpc_connector_cidr" {
  description = "Dedicated /28 CIDR block for Serverless VPC Access connector"
  type        = string
  default     = "10.10.8.0/28"
}

variable "safety_latency_threshold_ms" {
  description = "Feed latency spike threshold in milliseconds triggering the emergency kill-switch"
  type        = number
  default     = 800
}
