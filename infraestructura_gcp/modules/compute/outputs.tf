# outputs.tf - Output Definitions for Compute Engine HFT Trading Node Module

output "instance_id" {
  description = "The unique server-assigned identifier of the created compute instance"
  value       = google_compute_instance.trading_engine.instance_id
}

output "instance_name" {
  description = "The name of the created compute instance"
  value       = google_compute_instance.trading_engine.name
}

output "instance_self_link" {
  description = "The URI self link of the created compute instance"
  value       = google_compute_instance.trading_engine.self_link
}

output "self_link" {
  description = "Alias for instance_self_link for root module integration compatibility"
  value       = google_compute_instance.trading_engine.self_link
}

output "internal_ip" {
  description = "Primary RFC 1918 internal IP address of the trading instance"
  value       = google_compute_instance.trading_engine.network_interface[0].network_ip
}

output "instance_private_ip" {
  description = "Alias for internal_ip for root module integration compatibility"
  value       = google_compute_instance.trading_engine.network_interface[0].network_ip
}

output "zone" {
  description = "GCP Zone where the instance is provisioned"
  value       = google_compute_instance.trading_engine.zone
}

output "machine_type" {
  description = "Machine type utilized by the instance"
  value       = google_compute_instance.trading_engine.machine_type
}

output "placement_policy_id" {
  description = "Resource policy ID of the compact collocated placement group"
  value       = var.enable_placement_policy ? google_compute_resource_policy.compact_placement[0].id : null
}

output "placement_policy_name" {
  description = "Name of the compact collocated placement group resource policy"
  value       = var.enable_placement_policy ? google_compute_resource_policy.compact_placement[0].name : null
}

output "service_account_email" {
  description = "Service account email attached to the instance"
  value       = var.service_account_email
}
