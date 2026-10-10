# outputs.tf - Root Output Definitions for HFT GCP Architecture
# Milestone 3 Integration: Bigtable, Redis, and Dataflow

# ------------------------------------------------------------------------------
# Core Environment & Provider Outputs
# ------------------------------------------------------------------------------

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

# ------------------------------------------------------------------------------
# Milestone 1: Networking Module Outputs & Interface Contracts
# ------------------------------------------------------------------------------

output "vpc_network_id" {
  description = "The unique identifier of the created VPC network"
  value       = module.networking.network_id
}

output "vpc_network_name" {
  description = "The name of the created VPC network"
  value       = module.networking.network_name
}

output "subnet_hft_id" {
  description = "The unique identifier of the primary HFT engine subnet"
  value       = module.networking.subnet_hft_id
}

output "subnet_hft_name" {
  description = "The name of the primary HFT engine subnet"
  value       = module.networking.subnet_hft_name
}

output "subnet_dataflow_id" {
  description = "The unique identifier of the secondary Dataflow worker subnet"
  value       = module.networking.subnet_dataflow_id
}

output "private_service_access_connection" {
  description = "Private Service Access peering connection ID for Memorystore Redis dependency chaining"
  value       = module.networking.private_service_access_connection
}

# ------------------------------------------------------------------------------
# Milestone 1: IAM Module Outputs & Interface Contracts
# ------------------------------------------------------------------------------

output "hft_engine_sa_email" {
  description = "Email of the C3/C4 HFT Trading Engine Service Account"
  value       = module.iam.hft_engine_sa_email
}

output "dataflow_worker_sa_email" {
  description = "Email of the Dataflow Streaming Worker Service Account"
  value       = module.iam.dataflow_worker_sa_email
}

output "hft_eventarc_sa_email" {
  description = "Email of the EventArc Trigger Service Account"
  value       = module.iam.hft_eventarc_sa_email
}

output "emergency_shutdown_sa_email" {
  description = "Email of the Emergency Shutdown Cloud Function Service Account"
  value       = module.iam.emergency_shutdown_sa_email
}

output "cicd_deployer_sa_email" {
  description = "Email of the CI/CD and Infrastructure Deployment Service Account"
  value       = module.iam.cicd_deployer_sa_email
}

# ------------------------------------------------------------------------------
# Milestone 1: Secret Manager Module Outputs
# ------------------------------------------------------------------------------

output "secret_ids" {
  description = "Map of managed Secret Manager secret resource IDs"
  value       = module.secrets.secret_ids
}

output "binance_api_key_secret_id" {
  description = "Resource ID of the Binance API key secret"
  value       = module.secrets.binance_api_key_secret_id
}

output "binance_api_secret_secret_id" {
  description = "Resource ID of the Binance API secret"
  value       = module.secrets.binance_api_secret_secret_id
}

output "telegram_bot_token_secret_id" {
  description = "Resource ID of the Telegram bot token secret"
  value       = module.secrets.telegram_bot_token_secret_id
}

output "telegram_chat_id_secret_id" {
  description = "Resource ID of the Telegram chat ID secret"
  value       = module.secrets.telegram_chat_id_secret_id
}

output "redis_auth_token_secret_id" {
  description = "Resource ID of the Memorystore Redis AUTH token secret"
  value       = module.secrets.redis_auth_token_secret_id
}

# ------------------------------------------------------------------------------
# Milestone 2: Compute Engine Module Outputs
# ------------------------------------------------------------------------------

output "hft_engine_instance_id" {
  description = "The unique server-assigned identifier of the HFT trading compute instance"
  value       = module.compute.instance_id
}

output "hft_engine_instance_name" {
  description = "The name of the C3/C4 HFT trading instance"
  value       = module.compute.instance_name
}

output "hft_engine_instance_self_link" {
  description = "The URI self link of the HFT trading compute instance"
  value       = module.compute.instance_self_link
}

output "hft_engine_private_ip" {
  description = "Primary RFC 1918 internal IP address of the HFT trading instance (zero public external IP)"
  value       = module.compute.internal_ip
}

output "hft_engine_zone" {
  description = "GCP Zone where the C3/C4 instance is provisioned (e.g. asia-northeast1-b)"
  value       = module.compute.zone
}

output "hft_engine_machine_type" {
  description = "Machine type utilized by the trading instance (e.g. c3-standard-4 or c4-standard-4)"
  value       = module.compute.machine_type
}

output "hft_engine_placement_policy_id" {
  description = "Resource policy ID of the compact collocated placement group"
  value       = module.compute.placement_policy_id
}

# ------------------------------------------------------------------------------
# Milestone 2: Pub/Sub Market Ingestion Module Outputs
# ------------------------------------------------------------------------------

output "pubsub_trades_topic_id" {
  description = "Resource ID of the market trades Pub/Sub topic"
  value       = module.pubsub.trades_topic_id
}

output "pubsub_trades_topic_name" {
  description = "Name of the market trades Pub/Sub topic"
  value       = module.pubsub.trades_topic_name
}

output "pubsub_orderbook_topic_id" {
  description = "Resource ID of the orderbook depth Pub/Sub topic"
  value       = module.pubsub.orderbook_topic_id
}

output "pubsub_orderbook_topic_name" {
  description = "Name of the orderbook depth Pub/Sub topic"
  value       = module.pubsub.orderbook_topic_name
}

output "pubsub_snapshots_topic_id" {
  description = "Resource ID of the market snapshots Pub/Sub topic"
  value       = module.pubsub.snapshots_topic_id
}

output "pubsub_snapshots_topic_name" {
  description = "Name of the market snapshots Pub/Sub topic"
  value       = module.pubsub.snapshots_topic_name
}

output "pubsub_safety_alerts_topic_id" {
  description = "Resource ID of the autonomous safety alerts Pub/Sub topic"
  value       = module.pubsub.safety_alerts_topic_id
}

output "pubsub_safety_alerts_dlq_topic_id" {
  description = "Resource ID of the Dead Letter Queue Pub/Sub topic"
  value       = module.pubsub.safety_alerts_dlq_topic_id
}

output "pubsub_all_topic_ids" {
  description = "Map of all provisioned Pub/Sub topic keys to their resource IDs"
  value       = module.pubsub.all_topic_ids
}

output "pubsub_trades_subscription_id" {
  description = "Resource ID of the HFT trading engine trades subscription"
  value       = module.pubsub.trades_subscription_id
}

output "pubsub_orderbook_subscription_id" {
  description = "Resource ID of the HFT trading engine orderbook subscription"
  value       = module.pubsub.orderbook_subscription_id
}

output "pubsub_safety_alerts_subscription_id" {
  description = "Resource ID of the emergency shutdown safety alerts subscription"
  value       = module.pubsub.safety_alerts_subscription_id
}

output "pubsub_dataflow_trades_subscription_id" {
  description = "Resource ID of the Dataflow streaming trades subscription"
  value       = module.pubsub.dataflow_trades_subscription_id
}

# ------------------------------------------------------------------------------
# Milestone 3: Storage Module Outputs (Cloud Bigtable & Cloud Memorystore Redis)
# ------------------------------------------------------------------------------

output "bigtable_instance_id" {
  description = "Resource ID of the Cloud Bigtable production SSD instance"
  value       = module.storage.bigtable_instance_id
}

output "bigtable_instance_name" {
  description = "Name of the Cloud Bigtable instance"
  value       = module.storage.bigtable_instance_name
}

output "bigtable_cluster_id" {
  description = "Identifier of the primary Bigtable SSD cluster in asia-northeast1-c"
  value       = module.storage.bigtable_cluster_id
}

output "bigtable_cluster_zone" {
  description = "GCP zone hosting the Bigtable cluster"
  value       = module.storage.bigtable_cluster_zone
}

output "bigtable_market_ticks_table_id" {
  description = "Resource ID of the primary market ticks Bigtable table"
  value       = module.storage.bigtable_market_ticks_table_id
}

output "bigtable_market_ticks_table_name" {
  description = "Name of the primary market ticks Bigtable table"
  value       = module.storage.bigtable_market_ticks_table_name
}

output "bigtable_column_families" {
  description = "Active column families configured on Bigtable tick table (trades 't', quotes 'q', metrics 'm')"
  value       = module.storage.bigtable_column_families
}

output "bigtable_row_key_spec" {
  description = "Reverse-timestamp row key specification for O(1) head-of-log scans"
  value       = module.storage.bigtable_row_key_spec
}

output "redis_instance_id" {
  description = "Resource ID of the Cloud Memorystore Redis instance"
  value       = module.storage.redis_instance_id
}

output "redis_instance_name" {
  description = "Name of the Cloud Memorystore Redis instance"
  value       = module.storage.redis_instance_name
}

output "redis_host" {
  description = "Internal RFC 1918 IP address of the Memorystore Redis primary node"
  value       = module.storage.redis_host
}

output "redis_port" {
  description = "TCP port of the Memorystore Redis instance"
  value       = module.storage.redis_port
}

output "redis_current_location_id" {
  description = "GCP zone currently hosting the active Memorystore Redis primary node"
  value       = module.storage.redis_current_location_id
}

output "redis_auth_string" {
  description = "Auto-generated Redis AUTH password token"
  value       = module.storage.redis_auth_string
  sensitive   = true
}

# ------------------------------------------------------------------------------
# Milestone 3: Dataflow Stream Processing Module Outputs
# ------------------------------------------------------------------------------

output "dataflow_job_id" {
  description = "Unique resource identifier of the Apache Beam Dataflow streaming job"
  value       = module.dataflow.job_id
}

output "dataflow_job_name" {
  description = "Name of the Dataflow streaming job"
  value       = module.dataflow.job_name
}

output "dataflow_job_state" {
  description = "Current lifecycle state of the Dataflow streaming job"
  value       = module.dataflow.job_state
}

output "dataflow_staging_bucket_name" {
  description = "Name of the GCS bucket for Dataflow binaries and temporary files"
  value       = module.dataflow.staging_bucket_name
}

output "dataflow_staging_bucket_url" {
  description = "URI of the GCS bucket for Dataflow staging"
  value       = module.dataflow.staging_bucket_url
}

output "dataflow_worker_sa_email" {
  description = "Service account email executing the Dataflow worker processes"
  value       = module.dataflow.service_account_email
}

output "dataflow_ip_configuration" {
  description = "Worker IP configuration confirming 0 public IPs (WORKER_IP_PRIVATE)"
  value       = module.dataflow.ip_configuration
}

output "dataflow_streaming_engine_enabled" {
  description = "Flag confirming Google Cloud Dataflow Streaming Engine is enabled"
  value       = module.dataflow.streaming_engine_enabled
}

output "dataflow_runner_v2_enabled" {
  description = "Flag confirming Apache Beam Runner v2 is enabled"
  value       = module.dataflow.runner_v2_enabled
}
