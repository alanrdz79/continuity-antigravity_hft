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
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
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

  project_id           = var.project_id
  region               = var.region
  network_name         = var.vpc_name
  subnet_hft_cidr      = var.subnet_cidr_primary
  subnet_dataflow_cidr = var.subnet_cidr_secondary
  environment          = var.environment

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
  region                      = var.region
  environment                 = var.environment
  replication_mode            = "user_managed"
  hft_engine_sa_email         = module.iam.hft_engine_sa_email
  emergency_shutdown_sa_email = module.iam.emergency_shutdown_sa_email

  binance_api_key    = var.binance_api_key
  binance_api_secret = var.binance_api_secret
  telegram_bot_token = var.telegram_bot_token
  telegram_chat_id   = var.telegram_chat_id
  redis_auth_token   = var.redis_auth_token

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

  project_id               = var.project_id
  region                   = var.region
  environment              = var.environment
  hft_engine_sa_email      = module.iam.hft_engine_sa_email
  dataflow_worker_sa_email = module.iam.dataflow_worker_sa_email

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services,
    module.iam
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
    time_sleep.wait_for_services,
    module.networking,
    module.iam
  ]
}

# ==============================================================================
# MILESTONE 3: STORAGE & STREAM PROCESSING (Bigtable, Redis, Dataflow)
# ==============================================================================

module "storage" {
  source = "./modules/storage"

  project_id                        = var.project_id
  region                            = var.region
  primary_zone                      = var.primary_zone
  secondary_zone                    = var.secondary_zone
  network_id                        = module.networking.network_id
  private_service_access_connection = module.networking.private_service_access_connection
  redis_memory_size_gb              = var.redis_memory_size_gb
  redis_auth_secret_id              = module.secrets.redis_auth_token_secret_id
  hft_engine_sa_email               = module.iam.hft_engine_sa_email
  dataflow_worker_sa_email          = module.iam.dataflow_worker_sa_email
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

module "dataflow" {
  source = "./modules/dataflow"

  project_id            = var.project_id
  region                = var.region
  zone                  = var.secondary_zone
  subnet_id             = module.networking.subnet_dataflow_id
  service_account_email = module.iam.dataflow_worker_sa_email
  subscription_id       = module.pubsub.dataflow_trades_subscription_id
  trades_topic_id       = module.pubsub.trades_topic_id
  bigtable_instance_id  = module.storage.bigtable_instance_name
  bigtable_table_id     = module.storage.bigtable_market_ticks_table_name
  machine_type          = var.dataflow_machine_type
  max_workers           = var.dataflow_max_workers
  enable_streaming_job  = var.enable_dataflow_streaming_job
  environment           = var.environment

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services,
    module.networking,
    module.iam,
    module.pubsub,
    module.storage
  ]
}

# ==============================================================================
# MILESTONE 4: AUTONOMOUS SAFETY ORCHESTRATION (EventArc, Functions, Monitoring)
# ==============================================================================

module "safety_orchestration" {
  source = "./modules/safety_orchestration"

  project_id                   = var.project_id
  region                       = var.region
  environment                  = var.environment

  # Service Account Identities
  emergency_shutdown_sa_email  = module.iam.emergency_shutdown_sa_email
  eventarc_sa_email            = module.iam.hft_eventarc_sa_email

  # Pub/Sub Integration
  safety_alerts_topic_id       = module.pubsub.safety_alerts_topic_id

  # Redis & Network Integration
  redis_host                   = module.storage.redis_host
  redis_port                   = module.storage.redis_port
  network_name                 = module.networking.network_name
  create_vpc_connector         = var.enable_serverless_vpc_connector
  vpc_connector_cidr           = var.serverless_vpc_connector_cidr

  # Secret Manager Integration
  binance_api_key_secret_id    = module.secrets.binance_api_key_secret_id
  binance_api_secret_secret_id = module.secrets.binance_api_secret_secret_id
  redis_auth_token_secret_id   = module.secrets.redis_auth_token_secret_id
  telegram_bot_token_secret_id = module.secrets.telegram_bot_token_secret_id
  telegram_chat_id_secret_id   = module.secrets.telegram_chat_id_secret_id

  # Monitoring Thresholds
  latency_threshold_ms         = var.safety_latency_threshold_ms

  depends_on = [
    google_project_service.required_services,
    time_sleep.wait_for_services,
    module.networking,
    module.iam,
    module.secrets,
    module.pubsub,
    module.storage
  ]
}
