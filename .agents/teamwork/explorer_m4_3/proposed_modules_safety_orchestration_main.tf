# ==============================================================================
# CONTINUITY HFT GCP ARCHITECTURE - SAFETY ORCHESTRATION MODULE
# File: modules/safety_orchestration/main.tf
# Provisions:
# 1. Cloud Storage bucket & archive packaging for Gen 2 Cloud Function
# 2. Serverless VPC Access connector for low-latency private Memorystore Redis access
# 3. Gen 2 Emergency Shutdown Cloud Function (asia-northeast1) with Secret Manager env vars
# 4. EventArc v2 Trigger routing Pub/Sub hft-safety-alerts to Cloud Function
# 5. Cloud Monitoring Pub/Sub Notification Channel
# 6. Cloud Monitoring Alert Policies for Latency Spikes (>800ms) & API Errors (429/418)
# ==============================================================================

locals {
  common_labels = {
    environment = var.environment
    managed_by  = "terraform"
    tier        = "safety"
  }

  # Safely parse secret resource ID to plain secret identifier if fully qualified ARN is passed
  resolved_binance_key_secret    = element(split("/", var.binance_api_key_secret_id), length(split("/", var.binance_api_key_secret_id)) - 1)
  resolved_binance_secret_secret = element(split("/", var.binance_api_secret_secret_id), length(split("/", var.binance_api_secret_secret_id)) - 1)
  resolved_redis_token_secret    = element(split("/", var.redis_auth_token_secret_id), length(split("/", var.redis_auth_token_secret_id)) - 1)
  resolved_telegram_bot_secret   = element(split("/", var.telegram_bot_token_secret_id), length(split("/", var.telegram_bot_token_secret_id)) - 1)
  resolved_telegram_chat_secret  = element(split("/", var.telegram_chat_id_secret_id), length(split("/", var.telegram_chat_id_secret_id)) - 1)
}

# ------------------------------------------------------------------------------
# 1. Function Source Packaging & Cloud Storage Deployment Bucket
# ------------------------------------------------------------------------------

data "archive_file" "emergency_shutdown_source" {
  type        = "zip"
  source_dir  = var.function_source_dir
  output_path = "${path.module}/emergency_shutdown_source.zip"
}

resource "google_storage_bucket" "function_source" {
  name                        = var.function_source_bucket_name != null ? var.function_source_bucket_name : "hft-function-source-${var.project_id}"
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = true

  versioning {
    enabled = true
  }

  labels = local.common_labels
}

resource "google_storage_bucket_object" "function_source_zip" {
  name   = "emergency_shutdown_${data.archive_file.emergency_shutdown_source.output_md5}.zip"
  bucket = google_storage_bucket.function_source.name
  source = data.archive_file.emergency_shutdown_source.output_path
}

# ------------------------------------------------------------------------------
# 2. Serverless VPC Access Connector (Private Redis Connectivity)
# ------------------------------------------------------------------------------

resource "google_vpc_access_connector" "serverless_connector" {
  count         = var.create_vpc_connector ? 1 : 0
  name          = var.vpc_connector_name
  project       = var.project_id
  region        = var.region
  network       = var.network_name
  ip_cidr_range = var.vpc_connector_cidr
  min_instances = var.vpc_connector_min_instances
  max_instances = var.vpc_connector_max_instances
  machine_type  = var.vpc_connector_machine_type
}

# ------------------------------------------------------------------------------
# 3. Emergency Shutdown Gen 2 Cloud Function
# ------------------------------------------------------------------------------

resource "google_cloudfunctions2_function" "emergency_shutdown" {
  name        = var.function_name
  location    = var.region
  project     = var.project_id
  description = "Autonomous HFT emergency shutdown and kill-switch orchestrator"

  build_config {
    runtime     = "python311"
    entry_point = var.function_entry_point

    source {
      storage_source {
        bucket = google_storage_bucket.function_source.name
        object = google_storage_bucket_object.function_source_zip.name
      }
    }
  }

  service_config {
    max_instance_count             = var.function_max_instances
    min_instance_count             = var.function_min_instances
    available_memory               = var.function_memory
    timeout_seconds                = var.function_timeout_seconds
    service_account_email          = var.emergency_shutdown_sa_email
    ingress_settings               = var.function_ingress_settings
    all_traffic_on_latest_revision = true

    vpc_connector                 = var.vpc_connector_id != null ? var.vpc_connector_id : (var.create_vpc_connector ? google_vpc_access_connector.serverless_connector[0].id : null)
    vpc_connector_egress_settings = (var.vpc_connector_id != null || var.create_vpc_connector) ? var.vpc_connector_egress_settings : null

    # Secret Manager Injected Environment Variables
    secret_environment_variables {
      key        = "BINANCE_API_KEY"
      project_id = var.project_id
      secret     = local.resolved_binance_key_secret
      version    = "latest"
    }

    secret_environment_variables {
      key        = "BINANCE_API_SECRET"
      project_id = var.project_id
      secret     = local.resolved_binance_secret_secret
      version    = "latest"
    }

    secret_environment_variables {
      key        = "REDIS_AUTH_TOKEN"
      project_id = var.project_id
      secret     = local.resolved_redis_token_secret
      version    = "latest"
    }

    secret_environment_variables {
      key        = "TELEGRAM_BOT_TOKEN"
      project_id = var.project_id
      secret     = local.resolved_telegram_bot_secret
      version    = "latest"
    }

    secret_environment_variables {
      key        = "TELEGRAM_CHAT_ID"
      project_id = var.project_id
      secret     = local.resolved_telegram_chat_secret
      version    = "latest"
    }

    # Operational Runtime Environment Variables
    environment_variables = {
      REDIS_HOST          = var.redis_host
      REDIS_PORT          = tostring(var.redis_port)
      SAFETY_ALERTS_TOPIC = var.safety_alerts_topic_id
      ENVIRONMENT         = var.environment
      LOG_LEVEL           = var.log_level
      KILL_SWITCH_KEY     = var.kill_switch_redis_key
    }
  }

  labels = local.common_labels
}

# ------------------------------------------------------------------------------
# 4. Fine-Grained IAM Invoker Bindings for EventArc
# ------------------------------------------------------------------------------

# Allow EventArc service account to invoke Cloud Run underlying service
resource "google_cloud_run_service_iam_member" "eventarc_run_invoker" {
  project  = var.project_id
  location = var.region
  service  = google_cloudfunctions2_function.emergency_shutdown.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${var.eventarc_sa_email}"
}

# Allow EventArc service account to invoke Cloud Function Gen 2
resource "google_cloudfunctions2_function_iam_member" "eventarc_cf_invoker" {
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.emergency_shutdown.name
  role           = "roles/cloudfunctions.invoker"
  member         = "serviceAccount:${var.eventarc_sa_email}"
}

# ------------------------------------------------------------------------------
# 5. EventArc v2 Trigger (Pub/Sub -> Emergency Shutdown Cloud Function)
# ------------------------------------------------------------------------------

resource "google_eventarc_trigger" "emergency_shutdown" {
  name            = var.eventarc_trigger_name
  location        = var.region
  project         = var.project_id
  service_account = var.eventarc_sa_email

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.emergency_shutdown.name
      region  = var.region
    }
  }

  transport {
    pubsub {
      topic = var.safety_alerts_topic_id
    }
  }

  labels = local.common_labels

  depends_on = [
    google_cloudfunctions2_function.emergency_shutdown,
    google_cloud_run_service_iam_member.eventarc_run_invoker
  ]
}

# ------------------------------------------------------------------------------
# 6. Cloud Monitoring Notification Channel (Pub/Sub)
# ------------------------------------------------------------------------------

resource "google_monitoring_notification_channel" "pubsub_safety" {
  display_name = "HFT Safety Alerts PubSub Channel"
  project      = var.project_id
  type         = "pubsub"
  labels = {
    topic = var.safety_alerts_topic_id
  }
  description = "Routes critical HFT latency spikes and API error breaches to hft-safety-alerts Pub/Sub topic"
  enabled     = true

  user_labels = local.common_labels
}

# ------------------------------------------------------------------------------
# 7. Cloud Monitoring Alert Policy: Latency Spike (>800ms)
# ------------------------------------------------------------------------------

resource "google_monitoring_alert_policy" "latency_spike" {
  display_name = "HFT Critical Feed Latency Spike (>800ms)"
  project      = var.project_id
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "Feed Latency breaches 800ms threshold"
    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"custom.googleapis.com/hft/feed_latency_ms\""
      duration        = "0s" # Immediate evaluation for HFT circuit-breaker
      comparison      = "COMPARISON_GT"
      threshold_value = var.latency_threshold_ms

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_MAX"
        cross_series_reducer = "REDUCE_MAX"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.pubsub_safety.name
  ]

  documentation {
    content   = "🚨 CRITICAL LATENCY SPIKE: Feed latency exceeded ${var.latency_threshold_ms}ms threshold. Emergency kill-switch and batch order cancellation initiated autonomously."
    mime_type = "text/markdown"
  }

  user_labels = merge(local.common_labels, {
    severity = "critical"
  })
}

# ------------------------------------------------------------------------------
# 8. Cloud Monitoring Alert Policy: API Error / Rate Limit Breach (429/418)
# ------------------------------------------------------------------------------

resource "google_monitoring_alert_policy" "api_errors" {
  display_name = "HFT Binance API Rate Limit / Ban Breach (429/418)"
  project      = var.project_id
  combiner     = "OR"
  enabled      = true

  conditions {
    display_name = "HTTP 429 or 418 received from Binance Gateway"
    condition_threshold {
      filter          = "resource.type = \"gce_instance\" AND metric.type = \"custom.googleapis.com/hft/api_error_code\""
      duration        = "0s" # Immediate evaluation
      comparison      = "COMPARISON_GT"
      threshold_value = 0

      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }

      trigger {
        count = 1
      }
    }
  }

  notification_channels = [
    google_monitoring_notification_channel.pubsub_safety.name
  ]

  documentation {
    content   = "🚨 API RATE LIMIT / IP BAN: HTTP 429 (Rate Limit) or HTTP 418 (IP Ban) received from Binance Gateway. Autonomous safety pause triggered."
    mime_type = "text/markdown"
  }

  user_labels = merge(local.common_labels, {
    severity = "critical"
  })
}
