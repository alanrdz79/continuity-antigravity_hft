# ==============================================================================
# HFT GCP ARCHITECTURE - STORAGE & CACHING MODULE VARIABLES
# Target File Location: modules/storage/variables.tf
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Core Project & Environment Configuration
# ------------------------------------------------------------------------------

variable "project_id" {
  type        = string
  description = "The GCP project ID where storage and caching resources are provisioned."
}

variable "region" {
  type        = string
  description = "Primary GCP region for storage infrastructure (asia-northeast1)."
  default     = "asia-northeast1"
}

variable "primary_zone" {
  type        = string
  description = "Primary zone for C3/C4 co-location and Redis primary node (asia-northeast1-b)."
  default     = "asia-northeast1-b"
}

variable "secondary_zone" {
  type        = string
  description = "Secondary GCP zone for Bigtable cluster and Redis standby replica (asia-northeast1-c)."
  default     = "asia-northeast1-c"
}

variable "environment" {
  type        = string
  description = "Deployment environment name (production, staging, development)."
  default     = "production"
}

variable "labels" {
  type        = map(string)
  description = "Resource labels to attach to storage infrastructure."
  default     = {}
}

# ------------------------------------------------------------------------------
# 2. Cloud Bigtable Instance & Cluster Configuration
# ------------------------------------------------------------------------------

variable "bigtable_instance_name" {
  type        = string
  description = "Identifier name for the Cloud Bigtable instance."
  default     = "hft-tick-store"
}

variable "bigtable_display_name" {
  type        = string
  description = "Human-readable display name for the Cloud Bigtable instance."
  default     = "HFT Low-Latency Tick Store"
}

variable "bigtable_cluster_id" {
  type        = string
  description = "Identifier for the primary Bigtable SSD cluster."
  default     = "hft-tick-cluster-01"
}

variable "bigtable_zone" {
  type        = string
  description = "Specific zone for the Bigtable cluster. If null, falls back to secondary_zone (asia-northeast1-c)."
  default     = null
}

variable "bigtable_num_nodes" {
  type        = number
  description = "Static node count for the Bigtable cluster. Recommended: 1 for demo/dev, 3+ for prod."
  default     = 1

  validation {
    condition     = var.bigtable_num_nodes >= 1
    error_message = "Bigtable cluster node count must be at least 1."
  }
}

variable "deletion_protection" {
  type        = bool
  description = "Whether to prevent accidental deletion of Bigtable instance. Set to false for demo/development flexibility."
  default     = false
}

variable "enable_bigtable_autoscaling" {
  type        = bool
  description = "Whether to enable CPU-based autoscaling instead of static node provisioning."
  default     = false
}

variable "bigtable_min_nodes" {
  type        = number
  description = "Minimum node count when autoscaling is enabled."
  default     = 1
}

variable "bigtable_max_nodes" {
  type        = number
  description = "Maximum node count when autoscaling is enabled."
  default     = 5
}

variable "bigtable_cpu_target" {
  type        = number
  description = "Target CPU utilization percentage for Bigtable autoscaling (10-80%)."
  default     = 70
}

# ------------------------------------------------------------------------------
# 3. Bigtable Tables & Partitioning Configuration
# ------------------------------------------------------------------------------

variable "market_ticks_table_name" {
  type        = string
  description = "Table name for high-velocity raw market ticks and L2 depth."
  default     = "hft-market-ticks"
}

variable "market_ticks_split_keys" {
  type        = list(string)
  description = "Pre-split row keys to distribute initial write throughput across Bigtable tablets evenly."
  default     = ["BTCUSDT#", "ETHUSDT#", "SOLUSDT#"]
}

variable "enable_auxiliary_tables" {
  type        = bool
  description = "Whether to provision auxiliary tables (orderbook-snapshots, execution-reports)."
  default     = true
}

variable "orderbook_snapshots_table_name" {
  type        = string
  description = "Table name for periodic full L2/L3 orderbook depth snapshots."
  default     = "hft-orderbook-snapshots"
}

variable "execution_reports_table_name" {
  type        = string
  description = "Table name for order lifecycle events and trade confirmations."
  default     = "hft-execution-reports"
}

# ------------------------------------------------------------------------------
# 4. Garbage Collection (GC) Retention Durations
# ------------------------------------------------------------------------------

variable "gc_trades_max_age" {
  type        = string
  description = "Retention duration for trade executions in column family 't' (e.g. '720h' = 30 days)."
  default     = "720h"
}

variable "gc_quotes_max_age" {
  type        = string
  description = "Retention duration for high-frequency quotes in column family 'q' (e.g. '168h' = 7 days)."
  default     = "168h"
}

variable "gc_metrics_max_age" {
  type        = string
  description = "Retention duration for latency and risk metrics in column family 'm' (e.g. '336h' = 14 days)."
  default     = "336h"
}

# ------------------------------------------------------------------------------
# 5. Cloud Memorystore Redis Configuration
# ------------------------------------------------------------------------------

variable "network_id" {
  type        = string
  description = "The VPC network ID authorized for Private Service Access (module.networking.network_id)."
}

variable "private_service_access_connection" {
  type        = any
  description = "PSA peering connection resource reference to enforce provisioning dependency ordering."
  default     = null
}

variable "redis_instance_name" {
  type        = string
  description = "Name of the Cloud Memorystore Redis instance."
  default     = "hft-redis-cache"
}

variable "redis_tier" {
  type        = string
  description = "The service tier of the Redis instance (STANDARD_HA for high availability failover)."
  default     = "STANDARD_HA"
}

variable "redis_memory_size_gb" {
  type        = number
  description = "Redis memory size in GiB (minimum 1 GiB for STANDARD_HA)."
  default     = 1
}

variable "redis_version" {
  type        = string
  description = "Version of Redis software (REDIS_7_0 or REDIS_6_X)."
  default     = "REDIS_7_0"
}

variable "redis_connect_mode" {
  type        = string
  description = "The network connect mode of the Redis instance (PRIVATE_SERVICE_ACCESS)."
  default     = "PRIVATE_SERVICE_ACCESS"
}

variable "redis_auth_enabled" {
  type        = bool
  description = "Indicates whether OSS Redis AUTH is enabled for the instance."
  default     = true
}

variable "redis_transit_encryption_mode" {
  type        = string
  description = "The TLS mode of the Redis instance (SERVER_AUTHENTICATION)."
  default     = "SERVER_AUTHENTICATION"
}

variable "redis_configs" {
  type        = map(string)
  description = "Additional configuration parameters for Redis instance."
  default = {
    maxmemory-policy = "volatile-lru"
    activedefrag     = "yes"
  }
}

variable "enable_redis_auth_secret_version" {
  type        = bool
  description = "Whether to inject live generated Redis AUTH token into Secret Manager."
  default     = true
}

variable "redis_auth_secret_id" {
  type        = string
  description = "Existing Secret Manager secret ID to update with the live generated AUTH token."
  default     = null
}

variable "create_standalone_auth_secret" {
  type        = bool
  description = "Whether to create a dedicated Secret Manager secret for the live Redis AUTH string."
  default     = false
}

# ------------------------------------------------------------------------------
# 6. Service Account IAM Identities
# ------------------------------------------------------------------------------

variable "hft_engine_sa_email" {
  type        = string
  description = "Service account email of the C3/C4 HFT Trading Engine VM (sa-hft-engine)."
  default     = ""
}

variable "dataflow_worker_sa_email" {
  type        = string
  description = "Service account email of the Apache Beam Dataflow worker (sa-dataflow-worker)."
  default     = ""
}

variable "emergency_shutdown_sa_email" {
  type        = string
  description = "Service account email of the emergency shutdown function (sa-emergency-shutdown)."
  default     = ""
}
