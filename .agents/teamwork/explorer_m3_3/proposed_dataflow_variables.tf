# ==============================================================================
# HFT GCP ARCHITECTURE - DATAFLOW MODULE VARIABLES
# Target File Location for Implementation: modules/dataflow/variables.tf
# ==============================================================================

variable "project_id" {
  description = "The GCP project ID where Dataflow resources are deployed"
  type        = string
}

variable "region" {
  description = "Target GCP region for Dataflow streaming workers (asia-northeast1)"
  type        = string
  default     = "asia-northeast1"
}

variable "zone" {
  description = "Target GCP zone for worker instances (e.g. asia-northeast1-b or asia-northeast1-c)"
  type        = string
  default     = null
}

variable "environment" {
  description = "Environment identifier (production, staging, development)"
  type        = string
  default     = "production"
}

variable "job_name" {
  description = "Name of the streaming Dataflow job"
  type        = string
  default     = "hft-stream-trades-processor"
}

variable "subnet_id" {
  description = "Identifier or URI of the private VPC subnet for Dataflow workers (zero public IPs)"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for Dataflow workers (sa-dataflow-worker)"
  type        = string
}

variable "subscription_id" {
  description = "Pub/Sub subscription resource ID for trades stream ingestion (sub-trades-dataflow)"
  type        = string
  default     = ""
}

variable "trades_topic_id" {
  description = "Optional Pub/Sub topic ID for market trades"
  type        = string
  default     = ""
}

variable "bigtable_instance_id" {
  description = "Cloud Bigtable instance identifier for low-latency tick data sink"
  type        = string
  default     = "hft-tick-store"
}

variable "bigtable_table_id" {
  description = "Cloud Bigtable table name for tick data sink (hft-market-ticks)"
  type        = string
  default     = "hft-market-ticks"
}

variable "template_gcs_path" {
  description = "GCS path to the Dataflow streaming template"
  type        = string
  default     = "gs://dataflow-templates/latest/PubSub_to_Bigtable"
}

variable "staging_bucket_name" {
  description = "Optional explicit name for Dataflow staging GCS bucket (auto-derived if empty)"
  type        = string
  default     = ""
}

variable "staging_bucket_retention_days" {
  description = "Number of days before temporary shuffle and staging artifacts are deleted"
  type        = number
  default     = 7
}

variable "max_workers" {
  description = "Maximum number of worker instances allowed during autoscaling"
  type        = number
  default     = 2
}

variable "machine_type" {
  description = "Compute Engine machine type for Dataflow worker VMs"
  type        = string
  default     = "n2-standard-2"
}

variable "enable_streaming_engine" {
  description = "Enable Dataflow Streaming Engine to offload state processing"
  type        = bool
  default     = true
}

variable "use_runner_v2" {
  description = "Enable Apache Beam Runner v2 optimized container execution"
  type        = bool
  default     = true
}

variable "enable_streaming_job" {
  description = "Toggle to provision the live streaming Dataflow job"
  type        = bool
  default     = true
}

variable "on_delete" {
  description = "Action when job resource is destroyed: 'drain' (process pending) or 'cancel' (immediate halt)"
  type        = string
  default     = "drain"
}

variable "labels" {
  description = "Key-value resource labels to attach to Dataflow jobs and storage"
  type        = map(string)
  default     = {}
}
