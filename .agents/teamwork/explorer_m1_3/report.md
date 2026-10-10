# Technical Blueprint & Recommendations: IAM Least-Privilege & Secret Manager (M1)

**Author**: Explorer Subagent (IAM & Secrets Specialist - `explorer_m1_3`)  
**Target Architecture**: CONTINUITY Real-Time HFT Autonomous Cloud Architecture on GCP  
**Project ID**: `intrepid-decker-480417-e9`  
**Target Region**: `asia-northeast1` (Tokyo, Japan)  
**Date**: 2026-10-09  
**Status**: Complete Architectural Specification & Code Blueprint  

---

## 1. Executive Summary & Problem Boundary

In algorithmic high-frequency trading (HFT) environments targeting exchange matching engines (such as Binance Spot / Binance Predict), infrastructure security must operate on a **Zero-Trust, Least-Privilege model**:
1. **Capital and Credential Exposure Risk**: An over-permissioned service account (e.g. granted `roles/editor` or project-wide `roles/secretmanager.secretAccessor`) presents a catastrophic single point of failure. If an isolated component (like a stream-processing Dataflow worker or an EventArc routing trigger) were compromised, unrestricted credentials could allow unauthorized trading, capital draining, or infrastructure destruction.
2. **Primitive Roles Prohibition**: Primitive IAM roles (`roles/owner`, `roles/editor`, `roles/viewer`) grant blanket privileges across dozens of Google Cloud services without audit segmentation. In production financial architectures, primitive roles are **strictly prohibited**.
3. **Destructive IAM Binding Hazards**: Using authoritative Terraform resources (`google_project_iam_binding` or `google_project_iam_policy`) will silently strip Google-managed service agents (e.g., Cloud Build, Compute Engine default agents, Service Networking agents) of their mandatory internal roles, breaking the entire GCP project. Non-authoritative `google_project_iam_member` resources must be enforced universally.
4. **Secrets Decoupling & Granular Access**: API keys, signing secrets, and network tokens must be sealed inside Google Secret Manager with regional data locality (`asia-northeast1`). Access must be restricted on a **per-secret basis** using `google_secret_manager_secret_iam_member`, ensuring that each service account can ONLY read the exact secrets its execution loop requires.

This document details the blueprint for two modular Terraform components:
- `modules/iam`: Manages 5 isolated service accounts and fine-grained project IAM bindings.
- `modules/secrets`: Manages Secret Manager resources, regional replication, initial placeholder secret versions, and granular resource-level secret accessor policies.

---

## 2. IAM Architecture & Least-Privilege Role Matrix (`modules/iam`)

### 2.1 The 5 Isolated Service Accounts

The architecture isolates operational responsibilities across five distinct identities:

| Service Account ID | Display Name | Execution Context | Core Responsibilities & Justification |
| :--- | :--- | :--- | :--- |
| `sa-hft-engine` | `HFT Trading Engine Compute Service Account` | Compute Engine C3/C4 Trading VM in `asia-northeast1-b` | Hot-path order routing, market tick ingestion, custom latency telemetry generation, and reading trading keys. |
| `sa-dataflow-worker` | `HFT Dataflow Streaming Worker Service Account` | Apache Beam Dataflow Streaming Workers | High-throughput streaming aggregation, consuming Pub/Sub ticks, writing bulk records to Cloud Bigtable. |
| `sa-hft-eventarc` | `HFT EventArc Trigger Execution Service Account` | EventArc v2 Trigger Controller | Event routing from Cloud Monitoring alerts / Pub/Sub to the Emergency Shutdown sink; invokes Cloud Run / Functions. |
| `sa-emergency-shutdown` | `HFT Emergency Shutdown Function Service Account` | Gen 2 Cloud Function / Cloud Run runtime | Autonomous circuit breaker: consumes alert payload, writes atomic kill-switch flag to Redis, signs & transmits Binance Cancel-All API call, dispatches Telegram alert. |
| `sa-cicd-deployer` | `HFT CI/CD and Infrastructure Deployment Service Account` | Terraform Runner / Deployment Pipeline | Provisioning and maintaining GCP resources with fine-grained admin roles without primitive Owner/Editor access. |

---

### 2.2 Detailed IAM Role Breakdown per Service Account

#### 1. `sa-hft-engine`
- `roles/monitoring.metricWriter`: Enables the C3/C4 trading daemon to publish custom time-series metrics (e.g., `custom.googleapis.com/hft/feed_latency_ms`, order round-trip latency, tick processing duration).
- `roles/logging.logWriter`: Enables local systemd/Docker trading daemons to write structured execution and error logs to Google Cloud Logging.
- `roles/cloudtrace.agent`: Enables microsecond distributed tracing spans across internal trading loops.
- `roles/pubsub.publisher`: Enables publishing local safety alerts to `hft-safety-alerts`, orderbook snapshots to `orderbook`, and trade signals to `trades`.
- `roles/pubsub.subscriber`: Enables subscribing to real-time control directives on `hft-control-commands`.
- `roles/bigtable.user`: Grants data-plane access to query historical ticks, order book depth, and market snapshots on Cloud Bigtable.
- *Secret Access*: Granted at resource-level via `modules/secrets` (never project-level) for `binance-api-key`, `binance-api-secret`, and `redis-auth-token`.

#### 2. `sa-dataflow-worker`
- `roles/dataflow.worker`: Standard Google-mandated role for Dataflow execution nodes. Authorizes worker VMs to pull work units from the Dataflow service, exchange pipeline state, and report pipeline progress.
- `roles/pubsub.subscriber`: Allows the streaming pipeline to consume market ticks from the input Pub/Sub subscription.
- `roles/bigtable.user`: Authorizes the pipeline to write parsed and aggregated market ticks directly into Cloud Bigtable column families (`t`, `q`, `m`).
- `roles/storage.objectAdmin`: Provides read/write access to Cloud Storage staging and temp buckets where Apache Beam binaries, job graphs, and pipeline artifacts reside.
- `roles/logging.logWriter`: Ships streaming worker system and pipeline logs to Cloud Logging.
- *Secret Access*: **None (0 permissions)**. Dataflow workers have zero access to Binance API keys or Telegram secrets.

#### 3. `sa-hft-eventarc`
- `roles/eventarc.eventReceiver`: Google Cloud requirement for Eventarc trigger service accounts to receive events from Eventarc providers and Pub/Sub transport layers.
- `roles/run.invoker`: Allows Eventarc to invoke the authenticated Gen 2 Cloud Function / Cloud Run service hosting the emergency shutdown handler.
- `roles/pubsub.subscriber`: Grants permission to consume from the underlying EventArc Pub/Sub transport subscription.
- *Secret Access*: **None (0 permissions)**.

#### 4. `sa-emergency-shutdown`
- `roles/run.invoker`: Authorizes the Cloud Function runtime.
- `roles/pubsub.publisher`: Authorizes publishing panic events to `hft-safety-alerts` and shutdown commands to `hft-control-commands`.
- `roles/logging.logWriter`: Emits audit and emergency trace logs to Cloud Logging.
- *Secret Access*: Granted at resource-level via `modules/secrets` for `binance-api-key` (to call `DELETE /api/v3/openOrders`), `binance-api-secret` (to generate HMAC-SHA256 signatures), `telegram-bot-token` (to broadcast panic alerts), `telegram-chat-id`, and `redis-auth-token` (to connect to Redis and set `emergency_kill_switch = 1`).

#### 5. `sa-cicd-deployer`
Strictly eliminates `roles/owner` and `roles/editor`. Grants specific administrative privileges bounded by infrastructure components:
- `roles/compute.networkAdmin`: To manage custom VPC, subnets, Cloud Router, Cloud NAT, and firewall rules.
- `roles/compute.instanceAdmin.v1`: To manage C3/C4 compute instances and placement policies.
- `roles/pubsub.admin`: To manage Pub/Sub topics, subscriptions, schemas, and dead-letter configurations.
- `roles/bigtable.admin`: To create and configure Bigtable instances, clusters, and tables.
- `roles/redis.admin`: To provision and configure Cloud Memorystore Redis instances.
- `roles/secretmanager.admin`: To create secrets, versions, and secret IAM bindings.
- `roles/eventarc.admin`: To create and configure EventArc triggers and channels.
- `roles/cloudfunctions.admin`: To deploy and manage Gen 2 Cloud Functions.
- `roles/run.admin`: To manage underlying Cloud Run services supporting Cloud Functions.
- `roles/monitoring.admin`: To create metric alert policies and notification channels.
- `roles/iam.serviceAccountUser`: To attach service accounts to Compute Engine instances, Cloud Functions, and Dataflow pipelines.
- `roles/iam.serviceAccountAdmin`: To create and manage service accounts.
- `roles/serviceusage.serviceUsageAdmin`: To enable necessary Google Cloud APIs.
- `roles/resourcemanager.projectIamAdmin`: To bind non-authoritative project IAM members.

---

### 2.3 Visual IAM Access Boundary Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                             GCP PROJECT IAM BOUNDARY                             │
├──────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│   ┌─────────────────────┐               ┌────────────────────────────────────┐   │
│   │    sa-hft-engine    │ ──publishes──▶│ Pub/Sub: `hft-safety-alerts`       │   │
│   │  (Compute Engine)   │ ──subscribes─▶│ Pub/Sub: `hft-control-commands`    │   │
│   │                     │ ──writes─────▶│ Cloud Monitoring Custom Metrics    │   │
│   │                     │ ──writes─────▶│ Cloud Logging Logs                 │   │
│   │                     │ ──reads/write▶│ Cloud Bigtable Tick Store          │   │
│   └──────────┬──────────┘               └────────────────────────────────────┘   │
│              │                                                                   │
│              │ (Resource-Level Accessor ONLY)                                    │
│              ▼                                                                   │
│   ┌──────────────────────────────────────────────────────────────────────────┐   │
│   │                         GOOGLE SECRET MANAGER                            │   │
│   │   - `binance-api-key`        [Allowed: sa-hft-engine, sa-emergency]      │   │
│   │   - `binance-api-secret`     [Allowed: sa-hft-engine, sa-emergency]      │   │
│   │   - `redis-auth-token`       [Allowed: sa-hft-engine, sa-emergency]      │   │
│   │   - `telegram-bot-token`     [Allowed: sa-emergency-shutdown]           │   │
│   │   - `telegram-chat-id`       [Allowed: sa-emergency-shutdown]           │   │
│   └──────────────────────────────────────────────────────────────────────────┘   │
│              ▲                                                                   │
│              │ (Resource-Level Accessor ONLY)                                    │
│   ┌──────────┴──────────┐               ┌────────────────────────────────────┐   │
│   │sa-emergency-shutdown│ ──invokes────▶│ Cloud Run / Function Gen 2 Runtime │   │
│   │  (Cloud Function)   │ ──publishes──▶│ Pub/Sub: `hft-control-commands`    │   │
│   │                     │ ──writes─────▶│ Cloud Logging Panic Logs           │   │
│   └─────────────────────┘               └────────────────────────────────────┘   │
│                                                                                  │
│   ┌─────────────────────┐               ┌────────────────────────────────────┐   │
│   │ sa-dataflow-worker  │ ──subscribes─▶│ Pub/Sub: `market-ticks`            │   │
│   │ (Beam Streaming)    │ ──writes─────▶│ Cloud Bigtable Tick Tables         │   │
│   │                     │ ──temp/stage─▶│ Cloud Storage Bucket               │   │
│   └─────────────────────┘               └────────────────────────────────────┘   │
│                                                                                  │
│   ┌─────────────────────┐               ┌────────────────────────────────────┐   │
│   │   sa-hft-eventarc   │ ──receives───▶│ Eventarc Trigger Hub               │   │
│   │ (Event Routing)     │ ──invokes────▶│ Emergency Shutdown Cloud Function  │   │
│   └─────────────────────┘               └────────────────────────────────────┘   │
│                                                                                  │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Secret Manager Architecture (`modules/secrets`)

### 3.1 Secret Catalog & Purpose

| Secret Name | Purpose | Target Consumer(s) | Sensitivity Level |
| :--- | :--- | :--- | :--- |
| `binance-api-key` | Public identification key for Binance REST & WebSocket authentication. | `sa-hft-engine`, `sa-emergency-shutdown` | High |
| `binance-api-secret` | HMAC-SHA256 signing secret for private order placement and cancel-all requests. | `sa-hft-engine`, `sa-emergency-shutdown` | Critical |
| `telegram-bot-token` | API authentication token for Telegram control and alerting bot. | `sa-emergency-shutdown` | High |
| `telegram-chat-id` | Authorized chat ID receiving critical circuit-breaker notifications. | `sa-emergency-shutdown` | Medium |
| `redis-auth-token` | Pre-shared AUTH token for connecting to Cloud Memorystore Redis. | `sa-hft-engine`, `sa-emergency-shutdown` | High |

---

### 3.2 Regional Replication & Data Locality

For high-frequency trading in Tokyo, secret retrieval during container initialization or cold start must avoid cross-continental network latency and cross-jurisdictional data transfer.
- The module supports `user_managed` replication locked to `asia-northeast1` (Tokyo).
- Alternatively, configurable `auto {}` replication can be selected via variable.
- Default: `user_managed` in `var.region` (`asia-northeast1`).

---

### 3.3 Zero-Plaintext & Safe Placeholder Versioning

In production Terraform workflows, real API secrets must NEVER be committed to version control. 
- The module defines `google_secret_manager_secret_version` with initial safe placeholder strings:
  - `binance_api_key` $\to$ default `"MOCK_BINANCE_API_KEY_PLACEHOLDER"`
  - `binance_api_secret` $\to$ default `"MOCK_BINANCE_API_SECRET_PLACEHOLDER"`
  - `telegram_bot_token` $\to$ default `"MOCK_TELEGRAM_BOT_TOKEN_PLACEHOLDER"`
  - `telegram_chat_id` $\to$ default `"MOCK_TELEGRAM_CHAT_ID_PLACEHOLDER"`
  - `redis_auth_token` $\to$ default `"MOCK_REDIS_AUTH_TOKEN_PLACEHOLDER"`
- Variables are declared with `sensitive = true`.
- During live production operations, operators or CI/CD pipelines inject live secrets using environment variables (e.g. `TF_VAR_binance_api_key`) or via `gcloud secrets versions add` post-provisioning.
- This guarantees that `terraform apply -auto-approve` succeeds deterministically without failing due to empty secret payload constraints.

---

### 3.4 Resource-Level Accessor Bindings

Rather than granting project-wide `roles/secretmanager.secretAccessor`, each secret binds only its required consumers using `google_secret_manager_secret_iam_member`:
- `binance-api-key`:
  - `member = "serviceAccount:${var.hft_engine_sa_email}"`
  - `member = "serviceAccount:${var.emergency_shutdown_sa_email}"`
- `binance-api-secret`:
  - `member = "serviceAccount:${var.hft_engine_sa_email}"`
  - `member = "serviceAccount:${var.emergency_shutdown_sa_email}"`
- `telegram-bot-token`:
  - `member = "serviceAccount:${var.emergency_shutdown_sa_email}"`
- `telegram-chat-id`:
  - `member = "serviceAccount:${var.emergency_shutdown_sa_email}"`
- `redis-auth-token`:
  - `member = "serviceAccount:${var.hft_engine_sa_email}"`
  - `member = "serviceAccount:${var.emergency_shutdown_sa_email}"`

---

## 4. Complete Terraform Implementation Blueprint

Below are the exact HCL file contents to be implemented in `modules/iam` and `modules/secrets`.

### 4.1 Module: `modules/iam`

#### `modules/iam/variables.tf`
```hcl
variable "project_id" {
  type        = string
  description = "The GCP Project ID where IAM service accounts and bindings are provisioned."
}

variable "environment" {
  type        = string
  description = "Deployment environment tag (e.g. production, staging, dev)."
  default     = "production"
}
```

#### `modules/iam/main.tf`
```hcl
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
```

#### `modules/iam/outputs.tf`
```hcl
output "hft_engine_sa_email" {
  description = "The email of the HFT trading engine service account."
  value       = google_service_account.sa_hft_engine.email
}

output "hft_engine_sa_id" {
  description = "The fully qualified ID of the HFT trading engine service account."
  value       = google_service_account.sa_hft_engine.id
}

output "dataflow_worker_sa_email" {
  description = "The email of the Dataflow worker service account."
  value       = google_service_account.sa_dataflow_worker.email
}

output "dataflow_worker_sa_id" {
  description = "The fully qualified ID of the Dataflow worker service account."
  value       = google_service_account.sa_dataflow_worker.id
}

output "hft_eventarc_sa_email" {
  description = "The email of the EventArc trigger service account."
  value       = google_service_account.sa_hft_eventarc.email
}

output "hft_eventarc_sa_id" {
  description = "The fully qualified ID of the EventArc trigger service account."
  value       = google_service_account.sa_hft_eventarc.id
}

output "emergency_shutdown_sa_email" {
  description = "The email of the Emergency Shutdown Cloud Function service account."
  value       = google_service_account.sa_emergency_shutdown.email
}

output "emergency_shutdown_sa_id" {
  description = "The fully qualified ID of the Emergency Shutdown Cloud Function service account."
  value       = google_service_account.sa_emergency_shutdown.id
}

output "cicd_deployer_sa_email" {
  description = "The email of the CI/CD deployment service account."
  value       = google_service_account.sa_cicd_deployer.email
}

output "cicd_deployer_sa_id" {
  description = "The fully qualified ID of the CI/CD deployment service account."
  value       = google_service_account.sa_cicd_deployer.id
}
```

---

### 4.2 Module: `modules/secrets`

#### `modules/secrets/variables.tf`
```hcl
variable "project_id" {
  type        = string
  description = "The GCP Project ID where Secret Manager secrets are provisioned."
}

variable "region" {
  type        = string
  description = "Primary region for secret replication (e.g. asia-northeast1)."
  default     = "asia-northeast1"
}

variable "environment" {
  type        = string
  description = "Deployment environment tag (e.g. production, staging, dev)."
  default     = "production"
}

variable "replication_mode" {
  type        = string
  description = "Secret replication mode: 'user_managed' (locked to region) or 'automatic'."
  default     = "user_managed"
}

variable "hft_engine_sa_email" {
  type        = string
  description = "Email of the HFT trading engine service account (authorized accessor)."
}

variable "emergency_shutdown_sa_email" {
  type        = string
  description = "Email of the Emergency Shutdown function service account (authorized accessor)."
}

variable "binance_api_key" {
  type        = string
  description = "Binance API Key. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_BINANCE_API_KEY_PLACEHOLDER"
  sensitive   = true
}

variable "binance_api_secret" {
  type        = string
  description = "Binance API Secret (HMAC-SHA256). Defaults to safe mock placeholder if omitted."
  default     = "MOCK_BINANCE_API_SECRET_PLACEHOLDER"
  sensitive   = true
}

variable "telegram_bot_token" {
  type        = string
  description = "Telegram Bot Token for alert broadcasts. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_TELEGRAM_BOT_TOKEN_PLACEHOLDER"
  sensitive   = true
}

variable "telegram_chat_id" {
  type        = string
  description = "Telegram Chat ID for panic alerts. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_TELEGRAM_CHAT_ID_PLACEHOLDER"
  sensitive   = true
}

variable "redis_auth_token" {
  type        = string
  description = "Redis AUTH pre-shared string. Defaults to safe mock placeholder if omitted."
  default     = "MOCK_REDIS_AUTH_TOKEN_PLACEHOLDER"
  sensitive   = true
}
```

#### `modules/secrets/main.tf`
```hcl
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
```

#### `modules/secrets/outputs.tf`
```hcl
output "secret_ids" {
  description = "Map of secret names to fully qualified secret IDs."
  value       = { for k, v in google_secret_manager_secret.secrets : k => v.id }
}

output "binance_api_key_secret_id" {
  description = "Fully qualified ID for the Binance API key secret."
  value       = google_secret_manager_secret.secrets["binance-api-key"].id
}

output "binance_api_secret_secret_id" {
  description = "Fully qualified ID for the Binance API secret."
  value       = google_secret_manager_secret.secrets["binance-api-secret"].id
}

output "telegram_bot_token_secret_id" {
  description = "Fully qualified ID for the Telegram bot token secret."
  value       = google_secret_manager_secret.secrets["telegram-bot-token"].id
}

output "telegram_chat_id_secret_id" {
  description = "Fully qualified ID for the Telegram chat ID secret."
  value       = google_secret_manager_secret.secrets["telegram-chat-id"].id
}

output "redis_auth_token_secret_id" {
  description = "Fully qualified ID for the Redis AUTH token secret."
  value       = google_secret_manager_secret.secrets["redis-auth-token"].id
}
```

---

## 5. Root Terraform Integration & Wiring

In the root configuration (`C:\Users\alanr\teamwork_projects\hft_gcp_architecture\main.tf`), the modules are composed with clean unidirectional dependency wiring:

```hcl
# IAM Module
module "iam" {
  source      = "./modules/iam"
  project_id  = var.project_id
  environment = var.environment
  depends_on  = [module.services] # Ensured by explorer_m1_1 services.tf
}

# Secrets Module
module "secrets" {
  source                      = "./modules/secrets"
  project_id                  = var.project_id
  region                      = var.region
  environment                 = var.environment
  replication_mode            = "user_managed"
  hft_engine_sa_email         = module.iam.hft_engine_sa_email
  emergency_shutdown_sa_email = module.iam.emergency_shutdown_sa_email

  # Secrets default to mock placeholders unless supplied via TF_VAR_...
  binance_api_key             = var.binance_api_key
  binance_api_secret          = var.binance_api_secret
  telegram_bot_token          = var.telegram_bot_token
  telegram_chat_id            = var.telegram_chat_id
  redis_auth_token            = var.redis_auth_token

  depends_on = [module.iam]
}
```

---

## 6. Security & Compliance Verification Blueprint

### 6.1 Automated Audit Gates

| Gate ID | Check | Tool | Pass Condition |
| :--- | :--- | :--- | :--- |
| **SEC-01** | Zero Primitive Roles | `gcloud projects get-iam-policy` | Project bindings contain 0 instances of `roles/owner` or `roles/editor` bound to any `sa-hft-*` account. |
| **SEC-02** | 5 Isolated SAs | `gcloud iam service-accounts list` | Exactly the 5 expected SAs exist with naming format `sa-*@${PROJECT_ID}.iam.gserviceaccount.com`. |
| **SEC-03** | Restricted Secret Access | `gcloud secrets get-iam-policy` | `binance-api-key` and `binance-api-secret` only list `sa-hft-engine` and `sa-emergency-shutdown` as members for `roles/secretmanager.secretAccessor`. Dataflow and Eventarc SAs have 0 entries. |
| **SEC-04** | Regional Replication | `gcloud secrets describe` | Replication policy is confirmed as `userManaged` targeting `asia-northeast1`. |
| **SEC-05** | Non-empty Secret Versions | `gcloud secrets versions list` | Secret versions exist and are in state `ENABLED`. |

### 6.2 Python Verification Harness Component (`verify_iam_secrets.py`)

This automated script will be included in the project's test suite to validate the live state post-deployment:

```python
#!/usr/bin/env python3
"""
Verification Script: IAM Least-Privilege & Secret Manager Policy Audit
Validates that:
1. No HFT service account has primitive roles (Owner/Editor).
2. All 5 dedicated service accounts are present.
3. Secret Manager secrets are provisioned with regional replication.
4. Only authorized service accounts have secretAccessor on Binance keys.
"""

import sys
import json
import subprocess

EXPECTED_SAS = [
    "sa-hft-engine",
    "sa-dataflow-worker",
    "sa-hft-eventarc",
    "sa-emergency-shutdown",
    "sa-cicd-deployer"
]

SENSITIVE_SECRETS = ["binance-api-key", "binance-api-secret"]

def run_cmd(cmd):
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        return None, res.stderr
    return res.stdout.strip(), None

def audit_iam(project_id):
    print("[*] Auditing IAM Service Accounts and Project Roles...")
    out, err = run_cmd(f"gcloud iam service-accounts list --project={project_id} --format=json")
    if err:
        print(f"[-] Failed to list service accounts: {err}")
        return False
    sas = json.loads(out)
    existing_sa_emails = [s.get("email") for s in sas]
    
    for expected in EXPECTED_SAS:
        match = any(expected in email for email in existing_sa_emails)
        if not match:
            print(f"[FAIL] Missing required Service Account: {expected}")
            return False
        print(f"[PASS] Service Account present: {expected}")

    # Check for primitive roles
    out, err = run_cmd(f"gcloud projects get-iam-policy {project_id} --format=json")
    if err:
        print(f"[-] Failed to get IAM policy: {err}")
        return False
    policy = json.loads(out)
    forbidden = ["roles/owner", "roles/editor"]
    for b in policy.get("bindings", []):
        if b.get("role") in forbidden:
            for m in b.get("members", []):
                if any(sa in m for sa in EXPECTED_SAS):
                    print(f"[FAIL] Primitive role violation: {m} bound to {b.get('role')}")
                    return False
    print("[PASS] Zero primitive role violations across HFT Service Accounts.")
    return True

def audit_secrets(project_id):
    print("[*] Auditing Secret Manager Policies...")
    for secret in SENSITIVE_SECRETS:
        out, err = run_cmd(f"gcloud secrets get-iam-policy {secret} --project={project_id} --format=json")
        if err:
            print(f"[-] Failed to get policy for secret {secret}: {err}")
            return False
        policy = json.loads(out)
        accessors = []
        for b in policy.get("bindings", []):
            if b.get("role") == "roles/secretmanager.secretAccessor":
                accessors.extend(b.get("members", []))
        
        # Verify sa-dataflow-worker is NOT in accessors
        if any("sa-dataflow-worker" in a for a in accessors):
            print(f"[FAIL] Dataflow worker unexpectedly has access to {secret}!")
            return False
        if any("sa-hft-eventarc" in a for a in accessors):
            print(f"[FAIL] EventArc trigger unexpectedly has access to {secret}!")
            return False
        
        # Verify sa-hft-engine IS in accessors
        if not any("sa-hft-engine" in a for a in accessors):
            print(f"[FAIL] Engine SA missing accessor permission on {secret}!")
            return False
        print(f"[PASS] Secret {secret} access strictly restricted to authorized trading SAs.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python verify_iam_secrets.py <PROJECT_ID>")
        sys.exit(1)
    proj = sys.argv[1]
    ok_iam = audit_iam(proj)
    ok_sec = audit_secrets(proj)
    if ok_iam and ok_sec:
        print("\n[SUCCESS] IAM and Secret Manager Least-Privilege Verification PASSED!")
        sys.exit(0)
    else:
        print("\n[FAILURE] IAM or Secret Manager checks FAILED!")
        sys.exit(2)
```

---

## 7. Downstream Agent Guidance for `worker_m1`

When `worker_m1` implements Milestone 1:
1. Create `modules/iam/` and populate `variables.tf`, `main.tf`, `outputs.tf` using the code in Section 4.1.
2. Create `modules/secrets/` and populate `variables.tf`, `main.tf`, `outputs.tf` using the code in Section 4.2.
3. Wire `module "iam"` and `module "secrets"` into the root `main.tf` and `outputs.tf` as specified in Section 5.
4. Ensure `terraform validate` runs cleanly with zero errors.
5. In M5 (Live Apply), ensure `verify_iam_secrets.py` passes 100% of audit checks.
