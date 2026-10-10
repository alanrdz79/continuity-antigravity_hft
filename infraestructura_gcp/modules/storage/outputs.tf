# ==============================================================================
# HFT GCP ARCHITECTURE - STORAGE & CACHING MODULE OUTPUTS
# Target File Location: modules/storage/outputs.tf
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Cloud Bigtable Instance Outputs
# ------------------------------------------------------------------------------

output "bigtable_instance_id" {
  description = "The fully qualified server-assigned identifier of the Cloud Bigtable instance."
  value       = google_bigtable_instance.tick_store.id
}

output "bigtable_instance_name" {
  description = "The name of the Cloud Bigtable instance."
  value       = google_bigtable_instance.tick_store.name
}

output "bigtable_cluster_id" {
  description = "The identifier of the primary Bigtable SSD cluster."
  value       = var.bigtable_cluster_id
}

output "bigtable_cluster_zone" {
  description = "The GCP zone where the Bigtable SSD cluster is deployed (asia-northeast1-c)."
  value       = local.resolved_bigtable_zone
}

output "bigtable_storage_type" {
  description = "Underlying physical storage type for the Bigtable cluster (strictly SSD)."
  value       = "SSD"
}

# ------------------------------------------------------------------------------
# 2. Cloud Bigtable Table Outputs
# ------------------------------------------------------------------------------

output "bigtable_market_ticks_table_id" {
  description = "The unique resource identifier of the primary market ticks table."
  value       = google_bigtable_table.market_ticks.id
}

output "bigtable_market_ticks_table_name" {
  description = "The name of the primary market ticks table (e.g. hft-market-ticks)."
  value       = google_bigtable_table.market_ticks.name
}

output "bigtable_column_families" {
  description = "List of active column families provisioned on the market ticks table."
  value       = ["t", "q", "m"]
}

output "bigtable_row_key_spec" {
  description = "The reverse-timestamp row key specification for deterministic O(1) head-of-log scans."
  value       = "{symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}"
}

output "bigtable_orderbook_snapshots_table_id" {
  description = "Resource ID of the auxiliary orderbook snapshots table (if enabled)."
  value       = var.enable_auxiliary_tables ? google_bigtable_table.orderbook_snapshots[0].id : null
}

output "bigtable_execution_reports_table_id" {
  description = "Resource ID of the auxiliary execution reports table (if enabled)."
  value       = var.enable_auxiliary_tables ? google_bigtable_table.execution_reports[0].id : null
}

# ------------------------------------------------------------------------------
# 3. Cloud Memorystore Redis Outputs
# ------------------------------------------------------------------------------

output "redis_instance_id" {
  description = "The unique server-assigned identifier of the Cloud Memorystore Redis instance."
  value       = google_redis_instance.hft_redis.id
}

output "redis_instance_name" {
  description = "The name of the Cloud Memorystore Redis instance."
  value       = google_redis_instance.hft_redis.name
}

output "redis_host" {
  description = "The internal RFC 1918 IP address of the primary Redis node."
  value       = google_redis_instance.hft_redis.host
}

output "redis_port" {
  description = "The port number of the Redis instance (default 6379)."
  value       = google_redis_instance.hft_redis.port
}

output "redis_current_location_id" {
  description = "The current zone where the primary Redis node is running."
  value       = google_redis_instance.hft_redis.current_location_id
}

output "redis_auth_string" {
  description = "The auto-generated Redis AUTH string (password) for client authentication."
  value       = google_redis_instance.hft_redis.auth_string
  sensitive   = true
}

output "redis_read_endpoint" {
  description = "The IP address of the read endpoint if read replicas are enabled."
  value       = google_redis_instance.hft_redis.read_endpoint
}

output "redis_read_endpoint_port" {
  description = "The port number of the read endpoint if read replicas are enabled."
  value       = google_redis_instance.hft_redis.read_endpoint_port
}

output "redis_server_ca_certs" {
  description = "List of Cloud Memorystore server CA certificates for TLS verification."
  value       = google_redis_instance.hft_redis.server_ca_certs
  sensitive   = true
}

output "redis_auth_secret_version_id" {
  description = "The Secret Manager version ID where the live Redis AUTH token is stored."
  value       = var.enable_redis_auth_secret_version ? google_secret_manager_secret_version.redis_auth_token_live[0].id : (var.create_standalone_auth_secret ? google_secret_manager_secret_version.redis_live_auth_secret_version[0].id : null)
}
