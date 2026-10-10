# proposed_storage_variables.tf - Proposed Variables for Redis in modules/storage/variables.tf
# High-Frequency Trading (HFT) Autonomous Cloud Architecture on GCP

variable "project_id" {
  description = "The GCP project ID where storage and caching resources are provisioned"
  type        = string
}

variable "region" {
  description = "Target GCP region for storage resources (asia-northeast1 Tokyo)"
  type        = string
  default     = "asia-northeast1"
}

variable "primary_zone" {
  description = "Primary zone for C3/C4 co-location and Redis primary node (asia-northeast1-b)"
  type        = string
  default     = "asia-northeast1-b"
}

variable "secondary_zone" {
  description = "Secondary zone for Bigtable replication and Redis HA standby replica (asia-northeast1-c)"
  type        = string
  default     = "asia-northeast1-c"
}

variable "environment" {
  description = "Deployment environment name (production, staging, development)"
  type        = string
  default     = "production"
}

variable "network_id" {
  description = "The VPC network ID authorized for Private Service Access (module.networking.network_id)"
  type        = string
}

variable "private_service_access_connection" {
  description = "The Private Service Access connection resource ID for dependency chaining"
  type        = any
}

variable "redis_instance_name" {
  description = "Name of the Cloud Memorystore Redis instance"
  type        = string
  default     = "hft-redis-cache"
}

variable "redis_tier" {
  description = "The service tier of the Redis instance (STANDARD_HA for high availability failover)"
  type        = string
  default     = "STANDARD_HA"
}

variable "redis_memory_size_gb" {
  description = "Redis memory size in GiB (minimum 1 GiB for STANDARD_HA)"
  type        = number
  default     = 1
}

variable "redis_version" {
  description = "Version of Redis software (REDIS_7_0 or REDIS_6_X)"
  type        = string
  default     = "REDIS_7_0"
}

variable "redis_connect_mode" {
  description = "The network connect mode of the Redis instance (PRIVATE_SERVICE_ACCESS)"
  type        = string
  default     = "PRIVATE_SERVICE_ACCESS"
}

variable "redis_auth_enabled" {
  description = "Indicates whether OSS Redis AUTH is enabled for the instance"
  type        = bool
  default     = true
}

variable "redis_transit_encryption_mode" {
  description = "The TLS mode of the Redis instance (SERVER_AUTHENTICATION)"
  type        = string
  default     = "SERVER_AUTHENTICATION"
}

variable "redis_configs" {
  description = "Additional configuration parameters for Redis instance"
  type        = map(string)
  default = {
    maxmemory-policy = "volatile-lru"
    activedefrag     = "yes"
  }
}

variable "redis_auth_secret_id" {
  description = "Optional existing Secret Manager secret ID to update with the live generated AUTH token"
  type        = string
  default     = null
}

variable "create_standalone_auth_secret" {
  description = "Whether to create a dedicated Secret Manager secret for the live Redis AUTH string"
  type        = bool
  default     = false
}

variable "hft_engine_sa_email" {
  description = "Service account email of the HFT trading engine for secret accessor permissions"
  type        = string
  default     = null
}

variable "emergency_shutdown_sa_email" {
  description = "Service account email of the emergency shutdown function for secret accessor permissions"
  type        = string
  default     = null
}

variable "labels" {
  description = "Resource labels to apply to Redis and storage resources"
  type        = map(string)
  default     = {}
}
