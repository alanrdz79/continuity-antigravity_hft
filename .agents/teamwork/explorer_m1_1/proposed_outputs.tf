# outputs.tf - Root Output Definitions for HFT Architecture

output "project_id" {
  description = "Active GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "Target ultra-low latency GCP region"
  value       = var.region
}

output "primary_zone" {
  description = "Primary trading engine compute zone"
  value       = var.primary_zone
}

output "secondary_zone" {
  description = "Secondary storage and HA zone"
  value       = var.secondary_zone
}

output "environment" {
  description = "Active deployment environment"
  value       = var.environment
}

output "enabled_services" {
  description = "GCP APIs managed and enabled declaratively by Terraform"
  value       = [for s in google_project_service.required_services : s.service]
}
