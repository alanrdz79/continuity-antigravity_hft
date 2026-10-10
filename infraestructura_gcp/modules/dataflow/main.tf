# ==============================================================================
# HFT GCP ARCHITECTURE - DATAFLOW STREAM PROCESSING MODULE
# Target File Location: modules/dataflow/main.tf
# Target Region / Zone: asia-northeast1 (Tokyo, Japan)
# Primary Engine: Apache Beam Streaming Ingestion & Real-Time Dual Sink
# STRICT SECURITY ENFORCEMENT: 0 Public IPs (WORKER_IP_PRIVATE)
# ==============================================================================

locals {
  # Resolved cluster zone: defaults to primary or secondary zone in Tokyo
  resolved_zone = coalesce(var.zone, "${var.region}-c")

  # Format required by Dataflow: "regions/REGION/subnetworks/SUBNETWORK"
  resolved_subnetwork = can(regex("regions/[^/]+/subnetworks/[^/]+$", var.subnet_id)) ? regex("regions/[^/]+/subnetworks/[^/]+$", var.subnet_id) : "regions/${var.region}/subnetworks/${var.subnet_id}"

  # Resolved staging bucket name
  resolved_staging_bucket = var.staging_bucket_name != "" ? var.staging_bucket_name : "hft-dataflow-staging-${var.project_id}"

  common_labels = merge(
    {
      environment = var.environment
      managed_by  = "terraform"
      component   = "dataflow-stream-processor"
      engine      = "apache-beam"
      region      = var.region
    },
    var.labels
  )
}

# ------------------------------------------------------------------------------
# 1. GCS Bucket for Dataflow Binaries, Staging & Temporary Shuffle Files
# ------------------------------------------------------------------------------
resource "google_storage_bucket" "dataflow_staging" {
  name                        = local.resolved_staging_bucket
  location                    = var.region
  project                     = var.project_id
  uniform_bucket_level_access = true
  force_destroy               = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = false
  }

  lifecycle_rule {
    action {
      type = "Delete"
    }
    condition {
      age = var.staging_bucket_retention_days
    }
  }

  labels = local.common_labels
}

# Explicit Defense-in-Depth IAM Binding on Staging Bucket for Worker Identity
resource "google_storage_bucket_iam_member" "dataflow_worker_staging_admin" {
  count  = var.service_account_email != "" ? 1 : 0
  bucket = google_storage_bucket.dataflow_staging.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${var.service_account_email}"
}

# ------------------------------------------------------------------------------
# 2. Apache Beam Streaming Dataflow Job
# ------------------------------------------------------------------------------
resource "google_dataflow_job" "stream_processor" {
  count = var.enable_streaming_job ? 1 : 0

  name              = var.job_name != "" ? var.job_name : "${var.environment}-hft-stream-processor"
  project           = var.project_id
  region            = var.region
  zone              = local.resolved_zone
  template_gcs_path = var.template_gcs_path
  temp_gcs_location = "${google_storage_bucket.dataflow_staging.url}/temp"

  # STRICT ZERO PUBLIC IP POLICY:
  # Workers never receive external public IPs; all outbound routing is via Cloud NAT
  ip_configuration = "WORKER_IP_PRIVATE"

  # Network placement in isolated private VPC subnet
  subnetwork = local.resolved_subnetwork

  # Least-Privilege Identity: sa-dataflow-worker
  service_account_email = var.service_account_email

  # High-Frequency Trading Performance Flags:
  # Streaming Engine offloads state/windowing to managed service backend
  enable_streaming_engine = var.enable_streaming_engine

  # Runner v2 enables optimized portable Beam container runtime
  additional_experiments = var.use_runner_v2 ? ["use_runner_v2"] : []

  # Worker Capacity & Machine Types
  max_workers  = var.max_workers
  machine_type = var.machine_type

  # Graceful or immediate termination policy on destruction
  on_delete = var.on_delete

  # Pipeline Parameters: Pub/Sub input subscription -> output topic
  parameters = {
    inputSubscription = var.subscription_id != "" ? var.subscription_id : "projects/${var.project_id}/subscriptions/sub-trades-dataflow"
    outputTopic       = var.trades_topic_id != "" ? var.trades_topic_id : "projects/${var.project_id}/topics/hft-market-trades"
  }

  labels = local.common_labels

  depends_on = [
    google_storage_bucket.dataflow_staging,
    google_storage_bucket_iam_member.dataflow_worker_staging_admin
  ]
}
