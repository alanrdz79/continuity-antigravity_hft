# ==============================================================================
# HFT GCP ARCHITECTURE - STORAGE MODULE OUTPUTS (BIGTABLE COMPONENTS)
# Target File Location for Implementation: modules/storage/outputs.tf
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Bigtable Instance Outputs
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
# 2. Bigtable Table Outputs
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
  description = "Resource ID of the optional orderbook snapshots table (if enabled)."
  value       = var.enable_auxiliary_tables ? google_bigtable_table.orderbook_snapshots[0].id : null
}

output "bigtable_execution_reports_table_id" {
  description = "Resource ID of the optional execution reports table (if enabled)."
  value       = var.enable_auxiliary_tables ? google_bigtable_table.execution_reports[0].id : null
}
