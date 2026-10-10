# ==============================================================================
# HFT GCP ARCHITECTURE - SECRET MANAGER MODULE
# Hardened Secret Storage, Regional Replication, and Granular IAM Accessor Matrix
# ==============================================================================

locals {
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    tier        = "trading-secrets"
  }

  secrets_definition = {
    "binance-api-key" = {
      secret_data = var.binance_api_key
      accessors   = [var.hft_engine_sa_email, var.emergency_shutdown_sa_email]
    }
    "binance-api-secret" = {
      secret_data = var.binance_api_secret
      accessors   = [var.hft_engine_sa_email, var.emergency_shutdown_sa_email]
    }
    "telegram-bot-token" = {
      secret_data = var.telegram_bot_token
      accessors   = [var.emergency_shutdown_sa_email]
    }
    "telegram-chat-id" = {
      secret_data = var.telegram_chat_id
      accessors   = [var.emergency_shutdown_sa_email]
    }
    "redis-auth-token" = {
      secret_data = var.redis_auth_token
      accessors   = [var.hft_engine_sa_email, var.emergency_shutdown_sa_email]
    }
  }

  # Flatten list of [secret_id, accessor_email] for fine-grained IAM bindings
  secret_accessor_pairs = flatten([
    for secret_id, config in local.secrets_definition : [
      for accessor in config.accessors : {
        key       = "${secret_id}-${accessor}"
        secret_id = secret_id
        accessor  = accessor
      }
    ]
  ])
}

# ------------------------------------------------------------------------------
# 1. Secret Containers
# ------------------------------------------------------------------------------
resource "google_secret_manager_secret" "secrets" {
  for_each  = local.secrets_definition
  secret_id = each.key
  project   = var.project_id
  labels    = local.common_labels

  replication {
    dynamic "user_managed" {
      for_each = var.replication_mode == "user_managed" ? [1] : []
      content {
        replicas {
          location = var.region
        }
      }
    }

    dynamic "auto" {
      for_each = var.replication_mode != "user_managed" ? [1] : []
      content {}
    }
  }
}

# ------------------------------------------------------------------------------
# 2. Secret Versions (Initial Safe Non-Empty Placeholders)
# ------------------------------------------------------------------------------
resource "google_secret_manager_secret_version" "secret_versions" {
  for_each    = local.secrets_definition
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value.secret_data
}

# ------------------------------------------------------------------------------
# 3. Fine-Grained Resource-Level Secret Accessor Bindings
# ------------------------------------------------------------------------------
resource "google_secret_manager_secret_iam_member" "secret_accessors" {
  for_each  = { for item in local.secret_accessor_pairs : item.key => item }
  project   = var.project_id
  secret_id = google_secret_manager_secret.secrets[each.value.secret_id].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${each.value.accessor}"
}
