# ==============================================================================
# CONTINUITY HFT GCP ARCHITECTURE - SAFETY ORCHESTRATION MODULE OUTPUTS
# File: modules/safety_orchestration/outputs.tf
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Cloud Function Gen 2 Outputs
# ------------------------------------------------------------------------------

output "emergency_function_id" {
  description = "The fully qualified identifier of the Emergency Shutdown Cloud Function"
  value       = google_cloudfunctions2_function.emergency_shutdown.id
}

output "emergency_function_name" {
  description = "The name of the Emergency Shutdown Cloud Function"
  value       = google_cloudfunctions2_function.emergency_shutdown.name
}

output "emergency_function_uri" {
  description = "The invocation URI of the Emergency Shutdown Cloud Function"
  value       = google_cloudfunctions2_function.emergency_shutdown.service_config[0].uri
}

output "function_uri" {
  description = "Alias for invocation URI of the Emergency Shutdown Cloud Function"
  value       = google_cloudfunctions2_function.emergency_shutdown.service_config[0].uri
}

output "function_source_bucket_name" {
  description = "The name of the Cloud Storage bucket storing function deployment archives"
  value       = google_storage_bucket.function_source.name
}

output "function_source_bucket_url" {
  description = "The gs:// URI of the function source storage bucket"
  value       = google_storage_bucket.function_source.url
}

# ------------------------------------------------------------------------------
# 2. Serverless VPC Access Connector Outputs
# ------------------------------------------------------------------------------

output "vpc_connector_id" {
  description = "The resource ID of the Serverless VPC Access connector utilized by the function"
  value       = var.create_vpc_connector ? google_vpc_access_connector.serverless_connector[0].id : var.vpc_connector_id
}

output "vpc_connector_state" {
  description = "State of the Serverless VPC Access connector"
  value       = var.create_vpc_connector ? google_vpc_access_connector.serverless_connector[0].state : "EXTERNAL_OR_DISABLED"
}

# ------------------------------------------------------------------------------
# 3. EventArc v2 Trigger Outputs
# ------------------------------------------------------------------------------

output "eventarc_trigger_id" {
  description = "The unique resource identifier of the EventArc v2 safety trigger"
  value       = google_eventarc_trigger.emergency_shutdown.id
}

output "eventarc_trigger_name" {
  description = "The name of the EventArc v2 safety trigger"
  value       = google_eventarc_trigger.emergency_shutdown.name
}

# ------------------------------------------------------------------------------
# 4. Cloud Monitoring Alert Policy & Notification Channel Outputs
# ------------------------------------------------------------------------------

output "notification_channel_id" {
  description = "The unique identifier of the Pub/Sub monitoring notification channel"
  value       = google_monitoring_notification_channel.pubsub_safety.id
}

output "notification_channel_name" {
  description = "The resource name of the Pub/Sub monitoring notification channel"
  value       = google_monitoring_notification_channel.pubsub_safety.name
}

output "alert_policy_latency_id" {
  description = "The unique identifier of the feed latency spike alert policy"
  value       = google_monitoring_alert_policy.latency_spike.id
}

output "alert_policy_api_errors_id" {
  description = "The unique identifier of the Binance API error code alert policy"
  value       = google_monitoring_alert_policy.api_errors.id
}

output "alert_policy_ids" {
  description = "List of all Cloud Monitoring alert policy IDs provisioned by safety orchestration"
  value = [
    google_monitoring_alert_policy.latency_spike.id,
    google_monitoring_alert_policy.api_errors.id
  ]
}

# ------------------------------------------------------------------------------
# 5. Operational State & Interface Contracts
# ------------------------------------------------------------------------------

output "kill_switch_redis_key" {
  description = "The Redis key queried by trading engines for kill-switch status"
  value       = var.kill_switch_redis_key
}
