# main.tf - Root Terraform Entrypoint & Module Orchestrator
# High-Frequency Trading (HFT) Autonomous Cloud Architecture on GCP
# Target Project: intrepid-decker-480417-e9 | Region: asia-northeast1 (Tokyo)

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 6.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  # Local or remote GCS backend can be specified:
  # backend "gcs" {
  #   bucket = "intrepid-decker-480417-e9-tfstate"
  #   prefix = "hft-gcp-architecture/state"
  # }
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.primary_zone
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
  zone    = var.primary_zone
}

# ==============================================================================
# MILESTONE 1: FOUNDATION MODULES (Networking, IAM, Secrets)
# ==============================================================================

module "networking" {
  source = "./modules/networking"

  project_id            = var.project_id
  region                = var.region
  network_name          = var.vpc_name
  subnet_cidr_primary   = var.subnet_cidr_primary
  subnet_cidr_secondary = var.subnet_cidr_secondary
  environment           = var.environment

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services
  ]
}

module "iam" {
  source = "./modules/iam"

  project_id  = var.project_id
  environment = var.environment

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services
  ]
}

module "secrets" {
  source = "./modules/secrets"

  project_id                  = var.project_id
  hft_engine_sa_email         = module.iam.hft_engine_sa_email
  emergency_shutdown_sa_email = module.iam.emergency_shutdown_sa_email

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services,
    module.iam
  ]
}

# ==============================================================================
# MILESTONE 2: MARKET INGESTION & COMPUTE (Pub/Sub, C3/C4 VMs)
# ==============================================================================

module "pubsub" {
  source = "./modules/pubsub"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services
  ]
}

module "compute" {
  source = "./modules/compute"

  project_id            = var.project_id
  region                = var.region
  primary_zone          = var.primary_zone
  machine_type          = var.machine_type
  network_id            = module.networking.network_id
  subnet_id             = module.networking.subnet_hft_id
  service_account_email = module.iam.hft_engine_sa_email
  environment           = var.environment

  depends_on = [
    google_project_service.required_services,
    module.networking,
    module.iam
  ]
}

# ==============================================================================
# MILESTONE 3: STORAGE & STREAM PROCESSING (Bigtable, Redis, Dataflow)
# ==============================================================================

module "storage" {
  source = "./modules/storage"

  project_id                         = var.project_id
  region                             = var.region
  secondary_zone                     = var.secondary_zone
  network_id                         = module.networking.network_id
  redis_memory_size_gb               = var.redis_memory_size_gb
  environment                        = var.environment
  private_service_access_connection  = module.networking.private_service_access_connection

  depends_on = [
    google_project_service.required_services,
    module.networking
  ]
}

module "dataflow" {
  source = "./modules/dataflow"

  project_id            = var.project_id
  region                = var.region
  subnet_id             = module.networking.subnet_hft_id
  service_account_email = module.iam.dataflow_worker_sa_email
  trades_topic_id       = module.pubsub.trades_topic_id
  environment           = var.environment

  depends_on = [
    google_project_service.required_services,
    module.networking,
    module.iam,
    module.pubsub,
    module.storage
  ]
}

# ==============================================================================
# MILESTONE 4: AUTONOMOUS SAFETY ORCHESTRATION (EventArc, Functions)
# ==============================================================================

module "safety_orchestration" {
  source = "./modules/safety_orchestration"

  project_id                  = var.project_id
  region                      = var.region
  emergency_shutdown_sa_email = module.iam.emergency_shutdown_sa_email
  eventarc_sa_email           = module.iam.eventarc_sa_email
  safety_alerts_topic_id      = module.pubsub.safety_alerts_topic_id
  environment                 = var.environment

  depends_on = [
    google_project_service.required_services,
    module.iam,
    module.pubsub
  ]
}
