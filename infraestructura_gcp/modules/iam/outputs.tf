output "hft_engine_sa_email" {
  description = "The email of the HFT trading engine service account."
  value       = google_service_account.sa_hft_engine.email
}

output "hft_engine_sa_id" {
  description = "The fully qualified ID of the HFT trading engine service account."
  value       = google_service_account.sa_hft_engine.id
}

output "dataflow_worker_sa_email" {
  description = "The email of the Dataflow worker service account."
  value       = google_service_account.sa_dataflow_worker.email
}

output "dataflow_worker_sa_id" {
  description = "The fully qualified ID of the Dataflow worker service account."
  value       = google_service_account.sa_dataflow_worker.id
}

output "hft_eventarc_sa_email" {
  description = "The email of the EventArc trigger service account."
  value       = google_service_account.sa_hft_eventarc.email
}

output "hft_eventarc_sa_id" {
  description = "The fully qualified ID of the EventArc trigger service account."
  value       = google_service_account.sa_hft_eventarc.id
}

output "emergency_shutdown_sa_email" {
  description = "The email of the Emergency Shutdown Cloud Function service account."
  value       = google_service_account.sa_emergency_shutdown.email
}

output "emergency_shutdown_sa_id" {
  description = "The fully qualified ID of the Emergency Shutdown Cloud Function service account."
  value       = google_service_account.sa_emergency_shutdown.id
}

output "cicd_deployer_sa_email" {
  description = "The email of the CI/CD deployment service account."
  value       = google_service_account.sa_cicd_deployer.email
}

output "cicd_deployer_sa_id" {
  description = "The fully qualified ID of the CI/CD deployment service account."
  value       = google_service_account.sa_cicd_deployer.id
}
