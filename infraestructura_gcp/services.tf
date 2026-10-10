# services.tf - Declarative GCP API Enablement & Protection
# Project: intrepid-decker-480417-e9

locals {
  # All required GCP APIs for the HFT Autonomous Cloud Architecture
  required_services = [
    "compute.googleapis.com",           # Compute Engine (C3/C4 VMs, VPC Networking, Cloud NAT)
    "pubsub.googleapis.com",            # Cloud Pub/Sub market data streaming topics & subscriptions
    "dataflow.googleapis.com",          # Apache Beam stream processing
    "bigtable.googleapis.com",          # Cloud Bigtable low-latency tick history
    "redis.googleapis.com",             # Cloud Memorystore for Redis state cache & kill-switch
    "eventarc.googleapis.com",          # EventArc v2 safety event router
    "cloudfunctions.googleapis.com",    # Cloud Functions v2 emergency shutdown handler
    "secretmanager.googleapis.com",     # Secret Manager for Binance & Telegram credentials
    "monitoring.googleapis.com",        # Cloud Monitoring alert policies & metrics
    "servicenetworking.googleapis.com", # Private Service Access (PSA) peering for Memorystore
    "cloudbuild.googleapis.com",        # Cloud Build engine for serverless functions
    "run.googleapis.com",               # Cloud Run Admin API (underlying host for Gen 2 Cloud Functions)
    "artifactregistry.googleapis.com",  # Artifact Registry for containerized workloads
    "iam.googleapis.com",               # Identity and Access Management for service accounts
    "vpcaccess.googleapis.com"          # Serverless VPC Access API for Cloud Functions private connectivity
  ]
}

resource "google_project_service" "required_services" {
  for_each = toset(local.required_services)

  project                    = var.project_id
  service                    = each.key
  disable_on_destroy         = false
  disable_dependent_services = false
}

# Ensure newly enabled APIs propagate across GCP's control plane before dependent modules execute
resource "time_sleep" "wait_for_services" {
  depends_on      = [google_project_service.required_services]
  create_duration = "30s"
}
