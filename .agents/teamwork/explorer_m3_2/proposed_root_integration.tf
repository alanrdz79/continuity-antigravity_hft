# proposed_root_integration.tf - Wiring snippet for Root main.tf, variables.tf, and outputs.tf
# High-Frequency Trading (HFT) Autonomous Cloud Architecture on GCP

# ==============================================================================
# 1. ROOT main.tf MODULE CALL
# ==============================================================================
/*
module "storage" {
  source                            = "./modules/storage"
  project_id                        = var.project_id
  region                            = var.region
  primary_zone                      = var.primary_zone
  secondary_zone                    = var.secondary_zone
  network_id                        = module.networking.network_id
  private_service_access_connection = module.networking.private_service_access_connection
  redis_memory_size_gb              = var.redis_memory_size_gb
  redis_version                     = "REDIS_7_0"
  redis_auth_secret_id              = module.secrets.redis_auth_token_secret_id
  hft_engine_sa_email               = module.iam.hft_engine_sa_email
  emergency_shutdown_sa_email       = module.iam.emergency_shutdown_sa_email
  environment                       = var.environment

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services,
    module.networking,
    module.iam,
    module.secrets
  ]
}
*/

# ==============================================================================
# 2. ROOT outputs.tf WIRE-UP
# ==============================================================================
/*
output "redis_instance_id" {
  description = "The unique server-assigned identifier of the Cloud Memorystore Redis instance"
  value       = module.storage.redis_instance_id
}

output "redis_host" {
  description = "The internal RFC 1918 IP address of the primary Redis node"
  value       = module.storage.redis_host
}

output "redis_port" {
  description = "The port number of the Redis instance"
  value       = module.storage.redis_port
}

output "redis_current_location_id" {
  description = "The current zone hosting the primary Redis node"
  value       = module.storage.redis_current_location_id
}

output "redis_auth_string" {
  description = "Auto-generated Redis AUTH password token"
  value       = module.storage.redis_auth_string
  sensitive   = true
}
*/
