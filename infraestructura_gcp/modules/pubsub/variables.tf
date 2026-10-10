# ==============================================================================
# HFT GCP ARCHITECTURE - PUBSUB MODULE VARIABLES (modules/pubsub/variables.tf)
# Target Region: asia-northeast1 (Tokyo, Japan)
# ==============================================================================

variable "project_id" {
  type        = string
  description = "The GCP project ID where Pub/Sub topics and subscriptions are provisioned."
}

variable "region" {
  type        = string
  description = "Primary GCP region for Pub/Sub message persistence (asia-northeast1)."
  default     = "asia-northeast1"
}

variable "environment" {
  type        = string
  description = "Deployment environment tag (production, staging, development)."
  default     = "production"
}

variable "allowed_persistence_regions" {
  type        = list(string)
  description = "Strict list of allowed message persistence regions to eliminate cross-region replication latency."
  default     = ["asia-northeast1"]
}

variable "enable_message_ordering" {
  type        = bool
  description = "Whether to enforce strict in-order message delivery per ordering key (<symbol>_<stream>)."
  default     = true
}

variable "ack_deadline_seconds" {
  type        = number
  description = "Acknowledgment deadline in seconds. Set to 10s for ultra-low latency failover."
  default     = 10

  validation {
    condition     = var.ack_deadline_seconds >= 10 && var.ack_deadline_seconds <= 600
    error_message = "The ack_deadline_seconds must be between 10 and 600 seconds."
  }
}

variable "message_retention_duration" {
  type        = string
  description = "Message retention duration for subscriptions (e.g. '604800s' = 7 days)."
  default     = "604800s"
}

variable "topic_message_retention_duration" {
  type        = string
  description = "Message retention duration for topics (e.g. '604800s' = 7 days, or '86400s' = 24 hours)."
  default     = "604800s"
}

variable "max_delivery_attempts" {
  type        = number
  description = "Maximum delivery attempts before evicting poisoned messages to the Dead Letter Queue."
  default     = 5

  validation {
    condition     = var.max_delivery_attempts >= 5 && var.max_delivery_attempts <= 100
    error_message = "max_delivery_attempts must be between 5 and 100."
  }
}

variable "hft_engine_sa_email" {
  type        = string
  description = "Email of the C3/C4 HFT Trading Engine service account (sa-hft-engine)."
  default     = ""
}

variable "dataflow_worker_sa_email" {
  type        = string
  description = "Email of the Dataflow stream processing worker service account (sa-dataflow-worker)."
  default     = ""
}

variable "create_orderbook_depth_alias" {
  type        = bool
  description = "Whether to create the hft-orderbook-depth topic in addition to hft-market-orderbook for test compatibility."
  default     = true
}
