# ==============================================================================
# HFT GCP ARCHITECTURE - IAM LEAST-PRIVILEGE MODULE
# Strictly enforces zero primitive roles (No Owner, No Editor)
# Uses non-authoritative google_project_iam_member to prevent project disruptions
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. Dedicated Service Accounts
# ------------------------------------------------------------------------------

# Service Account 1: Compute Engine Trading VM (C3/C4)
resource "google_service_account" "sa_hft_engine" {
  account_id   = "sa-hft-engine"
  display_name = "HFT Trading Engine Compute Service Account"
  description  = "Identity for low-latency C3/C4 trading VM; accesses Pub/Sub, Bigtable, metrics."
  project      = var.project_id
}

# Service Account 2: Dataflow Streaming Processing Workers
resource "google_service_account" "sa_dataflow_worker" {
  account_id   = "sa-dataflow-worker"
  display_name = "HFT Dataflow Streaming Worker Service Account"
  description  = "Identity for Apache Beam Dataflow workers streaming market data into Bigtable."
  project      = var.project_id
}

# Service Account 3: EventArc Trigger Controller
resource "google_service_account" "sa_hft_eventarc" {
  account_id   = "sa-hft-eventarc"
  display_name = "HFT EventArc Trigger Execution Service Account"
  description  = "Identity for EventArc v2 triggers routing latency/error alerts to shutdown sink."
  project      = var.project_id
}

# Service Account 4: Emergency Shutdown Cloud Function (Gen 2)
resource "google_service_account" "sa_emergency_shutdown" {
  account_id   = "sa-emergency-shutdown"
  display_name = "HFT Emergency Shutdown Function Service Account"
  description  = "Identity for emergency kill-switch Cloud Function; executes Binance cancel-all & alerts."
  project      = var.project_id
}

# Service Account 5: CI/CD & Terraform Deployer
resource "google_service_account" "sa_cicd_deployer" {
  account_id   = "sa-cicd-deployer"
  display_name = "HFT CI/CD and Infrastructure Deployment Service Account"
  description  = "Identity for infrastructure provisioning pipelines with granular admin permissions."
  project      = var.project_id
}

# ------------------------------------------------------------------------------
# 2. Project-Level Fine-Grained Role Bindings
# ------------------------------------------------------------------------------

locals {
  # Roles for Trading Engine VM
  hft_engine_roles = [
    "roles/monitoring.metricWriter",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/pubsub.publisher",
    "roles/pubsub.subscriber",
    "roles/bigtable.user",
  ]

  # Roles for Dataflow Worker
  dataflow_worker_roles = [
    "roles/dataflow.worker",
    "roles/pubsub.subscriber",
    "roles/bigtable.user",
    "roles/storage.objectAdmin",
    "roles/logging.logWriter",
  ]

  # Roles for EventArc Trigger
  hft_eventarc_roles = [
    "roles/eventarc.eventReceiver",
    "roles/run.invoker",
    "roles/pubsub.subscriber",
  ]

  # Roles for Emergency Shutdown Cloud Function
  emergency_shutdown_roles = [
    "roles/run.invoker",
    "roles/pubsub.publisher",
    "roles/logging.logWriter",
  ]

  # Scoped Admin Roles for CI/CD Deployer (Strictly NO primitive Owner or Editor)
  cicd_deployer_roles = [
    "roles/compute.networkAdmin",
    "roles/compute.instanceAdmin.v1",
    "roles/pubsub.admin",
    "roles/bigtable.admin",
    "roles/redis.admin",
    "roles/secretmanager.admin",
    "roles/eventarc.admin",
    "roles/cloudfunctions.admin",
    "roles/run.admin",
    "roles/monitoring.admin",
    "roles/iam.serviceAccountUser",
    "roles/iam.serviceAccountAdmin",
    "roles/serviceusage.serviceUsageAdmin",
    "roles/resourcemanager.projectIamAdmin",
  ]
}

# Bindings: sa-hft-engine
resource "google_project_iam_member" "hft_engine_bindings" {
  for_each = toset(local.hft_engine_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.sa_hft_engine.email}"
}

# Bindings: sa-dataflow-worker
resource "google_project_iam_member" "dataflow_worker_bindings" {
  for_each = toset(local.dataflow_worker_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.sa_dataflow_worker.email}"
}

# Bindings: sa-hft-eventarc
resource "google_project_iam_member" "hft_eventarc_bindings" {
  for_each = toset(local.hft_eventarc_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.sa_hft_eventarc.email}"
}

# Bindings: sa-emergency-shutdown
resource "google_project_iam_member" "emergency_shutdown_bindings" {
  for_each = toset(local.emergency_shutdown_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.sa_emergency_shutdown.email}"
}

# Bindings: sa-cicd-deployer
resource "google_project_iam_member" "cicd_deployer_bindings" {
  for_each = toset(local.cicd_deployer_roles)
  project  = var.project_id
  role     = each.value
  member   = "serviceAccount:${google_service_account.sa_cicd_deployer.email}"
}
