# proposed_storage_outputs.tf - Proposed Outputs for Redis in modules/storage/outputs.tf
# High-Frequency Trading (HFT) Autonomous Cloud Architecture on GCP

output "redis_instance_id" {
  description = "The unique server-assigned identifier of the Cloud Memorystore Redis instance"
  value       = google_redis_instance.hft_redis.id
}

output "redis_instance_name" {
  description = "The name of the Cloud Memorystore Redis instance"
  value       = google_redis_instance.hft_redis.name
}

output "redis_host" {
  description = "The internal RFC 1918 IP address of the primary Redis node"
  value       = google_redis_instance.hft_redis.host
}

output "redis_port" {
  description = "The port number of the Redis instance (default 6379)"
  value       = google_redis_instance.hft_redis.port
}

output "redis_current_location_id" {
  description = "The current zone where the primary Redis node is running"
  value       = google_redis_instance.hft_redis.current_location_id
}

output "redis_auth_string" {
  description = "The auto-generated Redis AUTH string (password) for client authentication"
  value       = google_redis_instance.hft_redis.auth_string
  sensitive   = true
}

output "redis_read_endpoint" {
  description = "The IP address of the read endpoint if read replicas are enabled"
  value       = google_redis_instance.hft_redis.read_endpoint
}

output "redis_read_endpoint_port" {
  description = "The port number of the read endpoint if read replicas are enabled"
  value       = google_redis_instance.hft_redis.read_endpoint_port
}

output "redis_server_ca_certs" {
  description = "List of Cloud Memorystore server CA certificates for TLS verification"
  value       = google_redis_instance.hft_redis.server_ca_certs
  sensitive   = true
}

output "redis_auth_secret_version_id" {
  description = "The Secret Manager version ID where the live Redis AUTH token is stored"
  value       = var.redis_auth_secret_id != null ? google_secret_manager_secret_version.redis_auth_token_live[0].id : (var.create_standalone_auth_secret ? google_secret_manager_secret_version.redis_live_auth_secret_version[0].id : null)
}
