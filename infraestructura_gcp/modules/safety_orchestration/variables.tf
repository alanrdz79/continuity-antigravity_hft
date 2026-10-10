# ==============================================================================
# CONTINUITY HFT GCP ARCHITECTURE - SAFETY ORCHESTRATION MODULE VARIABLES
# File: modules/safety_orchestration/variables.tf
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Project & Environment Variables
# ------------------------------------------------------------------------------

variable "project_id" {
  description = "The GCP project ID where safety resources are provisioned"
  type        = string
}

variable "region" {
  description = "Target GCP region (e.g. asia-northeast1 for ultra-low latency to Binance)"
  type        = string
  default     = "asia-northeast1"
}

variable "environment" {
  description = "Deployment environment name (production, staging, demo)"
  type        = string
  default     = "production"
}

# ------------------------------------------------------------------------------
# 2. Service Account Identities
# ------------------------------------------------------------------------------

variable "emergency_shutdown_sa_email" {
  description = "Service account email executing the emergency shutdown function (sa-emergency-shutdown)"
  type        = string
}

variable "eventarc_sa_email" {
  description = "Service account email authorized to invoke target functions via EventArc (sa-hft-eventarc)"
  type        = string
}

# ------------------------------------------------------------------------------
# 3. Cloud Storage & Packaging Variables
# ------------------------------------------------------------------------------

variable "function_source_dir" {
  description = "Local file path containing the emergency shutdown function source code"
  type        = string
  default     = "./functions/emergency_shutdown"
}

variable "function_source_bucket_name" {
  description = "Explicit name for the function source GCS bucket. Defaults to hft-function-source-{project_id} if null"
  type        = string
  default     = null
}

variable "function_source_archive_path" {
  description = "Path to the emergency shutdown zip archive package"
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# 4. Cloud Function Configuration Variables
# ------------------------------------------------------------------------------

variable "function_name" {
  description = "Name of the Gen 2 Cloud Function resource"
  type        = string
  default     = "hft-emergency-shutdown"
}

variable "function_entry_point" {
  description = "Name of the function handler in main.py"
  type        = string
  default     = "emergency_shutdown"
}

variable "function_memory" {
  description = "Memory allocated to the Cloud Function container instance"
  type        = string
  default     = "512M"
}

variable "function_memory_mb" {
  description = "Memory allocated to the Emergency Shutdown Cloud Function (alias)"
  type        = string
  default     = "512M"
}

variable "function_timeout_seconds" {
  description = "Execution timeout for the emergency shutdown function"
  type        = number
  default     = 60
}

variable "function_max_instances" {
  description = "Maximum number of container instances for horizontal scaling"
  type        = number
  default     = 5
}

variable "function_min_instances" {
  description = "Minimum number of container instances (keep warm if set > 0)"
  type        = number
  default     = 0
}

variable "function_ingress_settings" {
  description = "Ingress traffic settings for the Cloud Function"
  type        = string
  default     = "ALLOW_INTERNAL_ONLY"
}

variable "log_level" {
  description = "Logging verbosity inside the emergency shutdown handler"
  type        = string
  default     = "INFO"
}

# ------------------------------------------------------------------------------
# 5. Network & VPC Egress Variables
# ------------------------------------------------------------------------------

variable "network_name" {
  description = "Name of the VPC network where Memorystore Redis is accessible"
  type        = string
  default     = "hft-primary-vpc"
}

variable "create_vpc_connector" {
  description = "Whether to create a Serverless VPC Access connector for reaching private Redis"
  type        = bool
  default     = true
}

variable "vpc_connector_name" {
  description = "Name of the Serverless VPC Access connector resource (1-21 chars, lowercase/hyphens)"
  type        = string
  default     = "hft-serverless-conn"
}

variable "vpc_connector_cidr" {
  description = "Dedicated /28 unallocated CIDR block for Serverless VPC Access connector"
  type        = string
  default     = "10.10.8.0/28"
}

variable "vpc_connector_min_instances" {
  description = "Minimum throughput instances for VPC Access connector"
  type        = number
  default     = 2
}

variable "vpc_connector_max_instances" {
  description = "Maximum throughput instances for VPC Access connector"
  type        = number
  default     = 3
}

variable "vpc_connector_machine_type" {
  description = "Instance type for VPC Access connector"
  type        = string
  default     = "e2-micro"
}

variable "vpc_connector_id" {
  description = "Optional pre-existing Serverless VPC Access connector resource ID. If null, created if create_vpc_connector is true"
  type        = string
  default     = null
}

variable "vpc_connector_egress_settings" {
  description = "VPC connector egress traffic mode (PRIVATE_RANGES_ONLY or ALL_TRAFFIC)"
  type        = string
  default     = "PRIVATE_RANGES_ONLY"
}

# ------------------------------------------------------------------------------
# 6. Redis State Cache & Kill Switch Variables
# ------------------------------------------------------------------------------

variable "redis_host" {
  description = "Internal IP address of Cloud Memorystore Redis instance"
  type        = string
  default     = ""
}

variable "redis_port" {
  description = "TCP port of Cloud Memorystore Redis instance"
  type        = number
  default     = 6379
}

variable "kill_switch_redis_key" {
  description = "Redis key string for atomic kill-switch flag"
  type        = string
  default     = "hft:emergency:kill_switch_active"
}

# ------------------------------------------------------------------------------
# 7. Secret Manager Secret IDs
# ------------------------------------------------------------------------------

variable "binance_api_key_secret_id" {
  description = "Secret Manager secret ID for Binance API Key"
  type        = string
  default     = ""
}

variable "binance_api_secret_secret_id" {
  description = "Secret Manager secret ID for Binance API Secret"
  type        = string
  default     = ""
}

variable "redis_auth_token_secret_id" {
  description = "Secret Manager secret ID for Redis AUTH token"
  type        = string
  default     = ""
}

variable "redis_auth_secret_id" {
  description = "Alias Secret Manager secret ID for Redis AUTH token"
  type        = string
  default     = ""
}

variable "telegram_bot_token_secret_id" {
  description = "Secret Manager secret ID for Telegram Bot Token"
  type        = string
  default     = ""
}

variable "telegram_chat_id_secret_id" {
  description = "Secret Manager secret ID for Telegram Chat ID"
  type        = string
  default     = ""
}

# ------------------------------------------------------------------------------
# 8. EventArc & Pub/Sub Variables
# ------------------------------------------------------------------------------

variable "safety_alerts_topic_id" {
  description = "Resource ID of the hft-safety-alerts Pub/Sub topic"
  type        = string
}

variable "eventarc_trigger_name" {
  description = "Name of the EventArc v2 trigger resource"
  type        = string
  default     = "hft-safety-eventarc-trigger"
}

# ------------------------------------------------------------------------------
# 9. Monitoring Alert Policies Variables
# ------------------------------------------------------------------------------

variable "latency_threshold_ms" {
  description = "Feed latency spike threshold in milliseconds triggering emergency shutdown"
  type        = number
  default     = 800
}

variable "labels" {
  description = "Resource labels to attach to safety orchestration resources"
  type        = map(string)
  default     = {}
}
