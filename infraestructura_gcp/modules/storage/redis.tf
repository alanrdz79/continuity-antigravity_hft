# ==============================================================================
# HFT GCP ARCHITECTURE - CLOUD MEMORYSTORE REDIS STATE CACHE MODULE
# Target File Location: modules/storage/redis.tf
# High-Frequency Trading (HFT) Sub-Microsecond State Cache & Emergency Kill Switch
# ==============================================================================

resource "google_redis_instance" "hft_redis" {
  name           = var.redis_instance_name
  tier           = var.redis_tier
  memory_size_gb = var.redis_memory_size_gb
  region         = var.region

  # Primary and replica zone placement for ultra-low latency co-location and HA
  location_id             = var.primary_zone
  alternative_location_id = var.secondary_zone

  # Redis Engine Version
  redis_version = var.redis_version

  # Networking & VPC Peering
  connect_mode       = var.redis_connect_mode
  authorized_network = var.network_id

  # Security & Encryption
  auth_enabled            = var.redis_auth_enabled
  transit_encryption_mode = var.redis_transit_encryption_mode

  # High-Frequency Trading Performance & Memory Eviction Tuning
  redis_configs = var.redis_configs

  # Resource labeling
  labels = local.redis_labels

  # CRITICAL DEPENDENCY:
  # Prevents Google Cloud API 400 error by ensuring Service Networking (PSA) peering
  # is fully active before Redis instance provisioning begins.
  depends_on = [
    var.private_service_access_connection
  ]
}

# ==============================================================================
# SECRET MANAGER INTEGRATION: Live Redis AUTH Token Injection
# ==============================================================================

# Inject live GCP-generated AUTH token into Secret Manager target secret
resource "google_secret_manager_secret_version" "redis_auth_token_live" {
  count = var.enable_redis_auth_secret_version ? 1 : 0

  secret      = var.redis_auth_secret_id
  secret_data = google_redis_instance.hft_redis.auth_string
}

# Optional dedicated standalone secret for Live Redis AUTH String if enabled
resource "google_secret_manager_secret" "redis_live_auth_secret" {
  count = var.create_standalone_auth_secret ? 1 : 0

  secret_id = "${var.redis_instance_name}-auth-string"
  project   = var.project_id

  labels = merge(
    var.labels,
    {
      environment = var.environment
      managed_by  = "terraform"
      tier        = "trading-secrets"
    }
  )

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }
}

resource "google_secret_manager_secret_version" "redis_live_auth_secret_version" {
  count = var.create_standalone_auth_secret ? 1 : 0

  secret      = google_secret_manager_secret.redis_live_auth_secret[0].id
  secret_data = google_redis_instance.hft_redis.auth_string
}

resource "google_secret_manager_secret_iam_member" "redis_auth_accessor_engine" {
  count = var.create_standalone_auth_secret && var.hft_engine_sa_email != "" ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.redis_live_auth_secret[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.hft_engine_sa_email}"
}

resource "google_secret_manager_secret_iam_member" "redis_auth_accessor_shutdown" {
  count = var.create_standalone_auth_secret && var.emergency_shutdown_sa_email != "" ? 1 : 0

  project   = var.project_id
  secret_id = google_secret_manager_secret.redis_live_auth_secret[0].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${var.emergency_shutdown_sa_email}"
}
