# ==============================================================================
# HFT GCP ARCHITECTURE - DATAFLOW MODULE OUTPUTS
# Target File Location for Implementation: modules/dataflow/outputs.tf
# ==============================================================================

output "job_id" {
  description = "The unique server-assigned identifier of the Dataflow streaming job"
  value       = var.enable_streaming_job ? google_dataflow_job.stream_processor[0].id : null
}

output "job_name" {
  description = "The name of the Dataflow streaming job"
  value       = var.enable_streaming_job ? google_dataflow_job.stream_processor[0].name : var.job_name
}

output "job_state" {
  description = "The current execution state of the Dataflow streaming job"
  value       = var.enable_streaming_job ? google_dataflow_job.stream_processor[0].state : "DISABLED"
}

output "staging_bucket_name" {
  description = "The name of the GCS bucket for staging and temporary shuffle files"
  value       = google_storage_bucket.dataflow_staging.name
}

output "staging_bucket_url" {
  description = "The GCS URL of the Dataflow staging bucket"
  value       = google_storage_bucket.dataflow_staging.url
}

output "temp_gcs_location" {
  description = "The full GCS path for temporary files used by the Dataflow runner"
  value       = "${google_storage_bucket.dataflow_staging.url}/temp"
}

output "service_account_email" {
  description = "The service account email executing the Dataflow worker processes"
  value       = var.service_account_email
}

output "subnetwork" {
  description = "The private subnetwork allocated to Dataflow workers"
  value       = local.resolved_subnetwork
}

output "ip_configuration" {
  description = "Confirmation of 0 public IP policy (strictly WORKER_IP_PRIVATE)"
  value       = "WORKER_IP_PRIVATE"
}

output "streaming_engine_enabled" {
  description = "Indicates whether Google Dataflow Streaming Engine is enabled"
  value       = var.enable_streaming_engine
}

output "runner_v2_enabled" {
  description = "Indicates whether Apache Beam Runner v2 is enabled"
  value       = var.use_runner_v2
}
