# ==============================================================================
# HFT GCP ARCHITECTURE - SAFETY ORCHESTRATION MODULE INPUT VARIABLES
# Location: modules/safety_orchestration/variables.tf
# ==============================================================================

variable "project_id" {
  description = "The GCP project ID where safety resources are provisioned"
  type        = string
}

variable "region" {
  description = "Target GCP region for EventArc v2 and Cloud Functions (Tokyo: asia-northeast1)"
  type        = string
  default     = "asia-northeast1"
}

variable "environment" {
  description = "Deployment environment name (production, staging, development)"
  type        = string
  default     = "production"
}

variable "emergency_shutdown_sa_email" {
  description = "Email of the Emergency Shutdown Cloud Function service account (module.iam.emergency_shutdown_sa_email)"
  type        = string
}

variable "eventarc_sa_email" {
  description = "Email of the EventArc trigger service account (module.iam.hft_eventarc_sa_email)"
  type        = string
}

variable "safety_alerts_topic_id" {
  description = "Resource ID of the autonomous safety alerts Pub/Sub topic (module.pubsub.safety_alerts_topic_id)"
  type        = string
}

variable "redis_host" {
  description = "Private IP address of Memorystore Redis instance"
  type        = string
  default     = ""
}

variable "redis_port" {
  description = "Port number of Memorystore Redis instance"
  type        = number
  default     = 6379
}

variable "redis_auth_secret_id" {
  description = "Resource ID of the Secret Manager secret containing the Redis AUTH token"
  type        = string
  default     = ""
}

variable "binance_api_key_secret_id" {
  description = "Resource ID of the Secret Manager secret containing the Binance API key"
  type        = string
  default     = ""
}

variable "binance_api_secret_secret_id" {
  description = "Resource ID of the Secret Manager secret containing the Binance API secret"
  type        = string
  default     = ""
}

variable "telegram_bot_token_secret_id" {
  description = "Resource ID of the Secret Manager secret containing the Telegram Bot token"
  type        = string
  default     = ""
}

variable "telegram_chat_id_secret_id" {
  description = "Resource ID of the Secret Manager secret containing the Telegram Chat ID"
  type        = string
  default     = ""
}

variable "vpc_connector_id" {
  description = "Optional Serverless VPC Access connector ID for Cloud Function private Redis egress"
  type        = string
  default     = null
}

variable "latency_threshold_ms" {
  description = "Latency threshold in milliseconds triggering the emergency alert policy (PLANnew.md Line 130: 800ms)"
  type        = number
  default     = 800
}

variable "function_memory_mb" {
  description = "Memory allocated to the Emergency Shutdown Cloud Function"
  type        = string
  default     = "512M"
}

variable "function_timeout_seconds" {
  description = "Execution timeout in seconds for Emergency Shutdown Cloud Function"
  type        = number
  default     = 60
}

variable "function_min_instances" {
  description = "Minimum instances for Emergency Shutdown Cloud Function (1 eliminates cold starts during panic events)"
  type        = number
  default     = 1
}

variable "function_source_archive_path" {
  description = "Path to the emergency shutdown zip archive package"
  type        = string
  default     = ""
}

variable "labels" {
  description = "Resource labels to attach to safety orchestration resources"
  type        = map(string)
  default     = {}
}
