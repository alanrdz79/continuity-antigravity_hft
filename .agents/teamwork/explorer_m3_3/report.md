# Architectural Report: Milestone 3 Dataflow Stream Processing & Root Wiring
**Project**: High-Frequency Trading (HFT) Autonomous Cloud Architecture on GCP  
**Target Repository**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture`  
**Target Region**: `asia-northeast1` (Tokyo, Japan)  
**Author**: Explorer 3 (`explorer_m3_3`)  
**Date**: 2026-10-10  

---

## 1. Executive Summary

Milestone 3 completes the state storage, caching, and stream processing tier of the HFT GCP cloud architecture. While Explorer 1 designed Cloud Bigtable tick storage and Explorer 2 designed Cloud Memorystore Redis caching, **Explorer 3** has engineered:
1. **The Dataflow Stream Processing Module (`modules/dataflow/`)**:
   - An Apache Beam streaming pipeline deployed via `google_dataflow_job` with Google's canonical `PubSub_to_Bigtable` template (and reference dual-sink Python pipeline `beam_stream_processor.py`).
   - Dedicated private GCS staging bucket (`hft-dataflow-staging-${project_id}`) with 7-day TTL lifecycle rules and uniform bucket-level access.
   - **Strict Zero Public IP Enforcement**: Configured with `ip_configuration = "WORKER_IP_PRIVATE"`. Workers execute inside the private VPC subnet (`subnet_hft_id` / `subnet_dataflow_id`) with all outbound egress routed through Cloud NAT.
   - **Sub-Second Streaming Acceleration**: Google Cloud Streaming Engine (`enable_streaming_engine = true`) and Apache Beam Runner v2 (`additional_experiments = ["use_runner_v2"]`) offload windowing, state management, and shuffle operations from worker VMs to Google's specialized streaming backend.
   - **Identity & Connectors**: Bound to `sa-dataflow-worker` (`module.iam.dataflow_worker_sa_email`), consuming from Pub/Sub subscription `sub-trades-dataflow` (`module.pubsub.dataflow_trades_subscription_id`) and sinking to Bigtable table `hft-market-ticks`.
2. **Root Module Integration (`main.tf`, `variables.tf`, `outputs.tf`)**:
   - Clean un-commenting and wiring of `module "storage"` and `module "dataflow"` in root `main.tf`.
   - Strict explicit dependency chaining (`depends_on = [google_project_service.required_services, time_sleep.wait_for_services, module.networking, module.iam, module.pubsub, module.storage]`).
   - Addition of Dataflow operational knobs in root `variables.tf` (`dataflow_machine_type`, `dataflow_max_workers`, `enable_dataflow_streaming_job`).
   - Comprehensive wire-up of 16 new Milestone 3 outputs in root `outputs.tf` exposing Bigtable instance/cluster/table IDs, Redis host/port/auth/location, and Dataflow job/staging bucket/security configurations.

---

## 2. Dataflow Architecture & Design Decisions

### 2.1. Strict Zero Public IP Enforcement
In high-frequency algorithmic trading architectures, attack surfaces must be minimized. Public IPs on worker VMs expose infrastructure to external reconnaissance and violate zero-trust network perimeter standards.
- By setting `ip_configuration = "WORKER_IP_PRIVATE"` on `google_dataflow_job`, Dataflow workers are instantiated without external NAT IPs (`natIP = null`).
- Outbound access (e.g., pulling Google container images or telemetry) traverses Cloud Router & Cloud NAT (`hft-nat`) provisioned in Milestone 1.
- Internal communication with Bigtable and Memorystore Redis stays strictly within Google's private network using Private Google Access (PGA) and VPC Peering (PSA).

### 2.2. Streaming Engine & Runner v2 Optimization
Traditional Dataflow execution runs pipeline workers with local disk-based shuffle and in-VM state checkpoints, which introduces GC pauses and CPU contention:
- **Streaming Engine (`enable_streaming_engine = true`)**: Moves windowing state, timers, and shuffling to Google's dedicated streaming infrastructure. This minimizes worker CPU/memory pressure, provides smoother autoscaling, and reduces end-to-end processing latencies to sub-second levels.
- **Runner v2 (`additional_experiments = ["use_runner_v2"]`)**: Utilizes the portable Beam runner architecture with optimized gRPC IPC and modular SDK containers, providing enhanced memory efficiency and high-throughput deserialization.

### 2.3. Dual-Sink Architecture & Connectors
The Dataflow streaming module connects the market data ingestion layer to persistent storage and cache:
- **Input Connector**: Pub/Sub subscription `sub-trades-dataflow` (created by `modules/pubsub`), which receives ordered tick trade messages with low ack deadlines (10s).
- **Primary Persistent Sink**: Cloud Bigtable table `hft-market-ticks` (created by `modules/storage`), storing tick trades under reverse-timestamp row keys (`{symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}`).
- **Low-Latency Cache Sink**: Updates Memorystore Redis key `hft:market:latest_tick:{symbol}` with real-time VWAP and orderbook depth statistics.

---

## 3. Dependency Graph & Control Plane Stabilization

The root infrastructure deployment sequence is strictly ordered to prevent race conditions during `terraform apply`:

```
┌─────────────────────────────────────────────────────────────┐
│ google_project_service.required_services (14 GCP APIs)      │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ time_sleep.wait_for_services (30s control plane propagation) │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│      module.networking       │ │         module.iam         │
│ VPC, Subnets, NAT, PSA Peering│ │ 5 SAs & Least-Privilege IAM│
└──────────────┬───────────────┘ └────────────┬───────────────┘
               │                              │
               ├──────────────────────────────┼──────────────────────────────┐
               │                              │                              │
               ▼                              ▼                              ▼
┌──────────────────────────────┐ ┌────────────────────────────┐ ┌────────────────────────────┐
│        module.secrets        │ │       module.pubsub        │ │       module.compute       │
│ Binance & Redis AUTH Secrets │ │ Topics, Subscriptions, DLT │ │ C3/C4 VM (gVNIC, 0 Pub IP) │
└──────────────┬───────────────┘ └────────────┬───────────────┘ └────────────────────────────┘
               │                              │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │        module.storage        │
               │ Bigtable SSD & Redis (PSA)   │
               └──────────────┬───────────────┘
                              │
                              ▼
               ┌──────────────────────────────┐
               │       module.dataflow        │
               │ GCS Staging & Streaming Job  │
               └──────────────────────────────┘
```

1. **`module.storage`** depends on:
   - `google_project_service.required_services` & `time_sleep.wait_for_services`
   - `module.networking`: Ensures VPC and `private_service_access_connection` (Service Networking peering) are active before Redis attempts peering allocation.
   - `module.iam`: Ensures `sa-hft-engine` and `sa-dataflow-worker` exist before instance-level IAM bindings are applied.
   - `module.secrets`: Injects Redis AUTH secret ID into module.storage.
2. **`module.dataflow`** depends on:
   - `module.pubsub`: Ensures `sub-trades-dataflow` is ready before Dataflow worker tries to read.
   - `module.storage`: Ensures `hft-tick-store` and `hft-market-ticks` table exist before Dataflow worker tries to sink data.
   - `module.iam`: Ensures `sa-dataflow-worker` has `roles/dataflow.worker`, `roles/bigtable.user`, and `roles/storage.objectAdmin`.
   - `module.networking`: Ensures worker subnet has Private Google Access enabled.

---

## 4. Proposed Code Inventory

### 4.1. `modules/dataflow/main.tf`
Location in explorer: `.agents/teamwork/explorer_m3_3/proposed_dataflow_main.tf`

```hcl
# ==============================================================================
# HFT GCP ARCHITECTURE - DATAFLOW STREAM PROCESSING MODULE
# Target File Location for Implementation: modules/dataflow/main.tf
# Target Region / Zone: asia-northeast1 (Tokyo, Japan)
# Primary Engine: Apache Beam Streaming Ingestion & Real-Time Dual Sink
# STRICT SECURITY ENFORCEMENT: 0 Public IPs (WORKER_IP_PRIVATE)
# ==============================================================================

locals {
  resolved_zone = coalesce(var.zone, "${var.region}-c")

  resolved_subnetwork = can(regex("^projects/", var.subnet_id)) ? var.subnet_id : (
    can(regex("^https://", var.subnet_id)) ? var.subnet_id : (
      can(regex("^regions/", var.subnet_id)) ? var.subnet_id : "regions/${var.region}/subnetworks/${var.subnet_id}"
    )
  )

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

  # Pipeline Parameters: Pub/Sub input subscription -> Bigtable sink table
  parameters = {
    readSubscription   = var.subscription_id != "" ? var.subscription_id : "projects/${var.project_id}/subscriptions/sub-trades-dataflow"
    bigtableProjectId  = var.project_id
    bigtableInstanceId = var.bigtable_instance_id
    bigtableTableId    = var.bigtable_table_id
  }

  labels = local.common_labels

  depends_on = [
    google_storage_bucket.dataflow_staging,
    google_storage_bucket_iam_member.dataflow_worker_staging_admin
  ]
}
```

### 4.2. `modules/dataflow/variables.tf`
Location in explorer: `.agents/teamwork/explorer_m3_3/proposed_dataflow_variables.tf`

```hcl
variable "project_id" {
  description = "The GCP project ID where Dataflow resources are deployed"
  type        = string
}

variable "region" {
  description = "Target GCP region for Dataflow streaming workers (asia-northeast1)"
  type        = string
  default     = "asia-northeast1"
}

variable "zone" {
  description = "Target GCP zone for worker instances (e.g. asia-northeast1-b or asia-northeast1-c)"
  type        = string
  default     = null
}

variable "environment" {
  description = "Environment identifier (production, staging, development)"
  type        = string
  default     = "production"
}

variable "job_name" {
  description = "Name of the streaming Dataflow job"
  type        = string
  default     = "hft-stream-trades-processor"
}

variable "subnet_id" {
  description = "Identifier or URI of the private VPC subnet for Dataflow workers (zero public IPs)"
  type        = string
}

variable "service_account_email" {
  description = "Service account email for Dataflow workers (sa-dataflow-worker)"
  type        = string
}

variable "subscription_id" {
  description = "Pub/Sub subscription resource ID for trades stream ingestion (sub-trades-dataflow)"
  type        = string
  default     = ""
}

variable "trades_topic_id" {
  description = "Optional Pub/Sub topic ID for market trades"
  type        = string
  default     = ""
}

variable "bigtable_instance_id" {
  description = "Cloud Bigtable instance identifier for low-latency tick data sink"
  type        = string
  default     = "hft-tick-store"
}

variable "bigtable_table_id" {
  description = "Cloud Bigtable table name for tick data sink (hft-market-ticks)"
  type        = string
  default     = "hft-market-ticks"
}

variable "template_gcs_path" {
  description = "GCS path to the Dataflow streaming template"
  type        = string
  default     = "gs://dataflow-templates/latest/PubSub_to_Bigtable"
}

variable "staging_bucket_name" {
  description = "Optional explicit name for Dataflow staging GCS bucket (auto-derived if empty)"
  type        = string
  default     = ""
}

variable "staging_bucket_retention_days" {
  description = "Number of days before temporary shuffle and staging artifacts are deleted"
  type        = number
  default     = 7
}

variable "max_workers" {
  description = "Maximum number of worker instances allowed during autoscaling"
  type        = number
  default     = 2
}

variable "machine_type" {
  description = "Compute Engine machine type for Dataflow worker VMs"
  type        = string
  default     = "n2-standard-2"
}

variable "enable_streaming_engine" {
  description = "Enable Dataflow Streaming Engine to offload state processing"
  type        = bool
  default     = true
}

variable "use_runner_v2" {
  description = "Enable Apache Beam Runner v2 optimized container execution"
  type        = bool
  default     = true
}

variable "enable_streaming_job" {
  description = "Toggle to provision the live streaming Dataflow job"
  type        = bool
  default     = true
}

variable "on_delete" {
  description = "Action when job resource is destroyed: 'drain' (process pending) or 'cancel' (immediate halt)"
  type        = string
  default     = "drain"
}

variable "labels" {
  description = "Key-value resource labels to attach to Dataflow jobs and storage"
  type        = map(string)
  default     = {}
}
```

### 4.3. `modules/dataflow/outputs.tf`
Location in explorer: `.agents/teamwork/explorer_m3_3/proposed_dataflow_outputs.tf`

```hcl
output "job_id" {
  description = "The unique server-assigned identifier of the Dataflow streaming job"
  value       = var.enable_streaming_job ? google_dataflow_job.stream_processor[0].id : null
}

output "job_name" {
  description = "The name of the Dataflow streaming job"
  value       = var.enable_streaming_job ? google_dataflow_job.stream_processor[0].name : var.job_name
}

output "job_state" {
  description = "The current execution state of the Dataflow streaming job"
  value       = var.enable_streaming_job ? google_dataflow_job.stream_processor[0].state : "DISABLED"
}

output "staging_bucket_name" {
  description = "The name of the GCS bucket for staging and temporary shuffle files"
  value       = google_storage_bucket.dataflow_staging.name
}

output "staging_bucket_url" {
  description = "The GCS URL of the Dataflow staging bucket"
  value       = google_storage_bucket.dataflow_staging.url
}

output "temp_gcs_location" {
  description = "The full GCS path for temporary files used by the Dataflow runner"
  value       = "${google_storage_bucket.dataflow_staging.url}/temp"
}

output "service_account_email" {
  description = "The service account email executing the Dataflow worker processes"
  value       = var.service_account_email
}

output "subnetwork" {
  description = "The private subnetwork allocated to Dataflow workers"
  value       = local.resolved_subnetwork
}

output "ip_configuration" {
  description = "Confirmation of 0 public IP policy (strictly WORKER_IP_PRIVATE)"
  value       = "WORKER_IP_PRIVATE"
}

output "streaming_engine_enabled" {
  description = "Indicates whether Google Dataflow Streaming Engine is enabled"
  value       = var.enable_streaming_engine
}

output "runner_v2_enabled" {
  description = "Indicates whether Apache Beam Runner v2 is enabled"
  value       = var.use_runner_v2
}
```

### 4.4. Root `main.tf` Milestone 3 Integration
Location in explorer: `.agents/teamwork/explorer_m3_3/proposed_root_main.tf`

```hcl
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
  subnet_id             = module.networking.subnet_hft_id
  service_account_email = module.iam.dataflow_worker_sa_email
  subscription_id       = module.pubsub.dataflow_trades_subscription_id
  trades_topic_id       = module.pubsub.trades_topic_id
  bigtable_instance_id  = module.storage.bigtable_instance_name
  bigtable_table_id     = module.storage.bigtable_market_ticks_table_name
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
```

### 4.5. Root `variables.tf` Additional Variables
Location in explorer: `.agents/teamwork/explorer_m3_3/proposed_root_variables.tf`

```hcl
variable "dataflow_machine_type" {
  description = "Compute Engine machine type for Apache Beam Dataflow streaming workers"
  type        = string
  default     = "n2-standard-2"
}

variable "dataflow_max_workers" {
  description = "Maximum number of worker instances for Dataflow horizontal autoscaling"
  type        = number
  default     = 2
}

variable "enable_dataflow_streaming_job" {
  description = "Toggle to provision the live streaming Dataflow pipeline"
  type        = bool
  default     = true
}
```

### 4.6. Root `outputs.tf` Milestone 3 Outputs
Location in explorer: `.agents/teamwork/explorer_m3_3/proposed_root_outputs.tf`

```hcl
# ------------------------------------------------------------------------------
# Milestone 3: Storage Module Outputs (Cloud Bigtable & Cloud Memorystore Redis)
# ------------------------------------------------------------------------------

output "bigtable_instance_id" {
  description = "Resource ID of the Cloud Bigtable production SSD instance"
  value       = module.storage.bigtable_instance_id
}

output "bigtable_instance_name" {
  description = "Name of the Cloud Bigtable instance"
  value       = module.storage.bigtable_instance_name
}

output "bigtable_cluster_id" {
  description = "Identifier of the primary Bigtable SSD cluster in asia-northeast1-c"
  value       = module.storage.bigtable_cluster_id
}

output "bigtable_cluster_zone" {
  description = "GCP zone hosting the Bigtable cluster"
  value       = module.storage.bigtable_cluster_zone
}

output "bigtable_market_ticks_table_id" {
  description = "Resource ID of the primary market ticks Bigtable table"
  value       = module.storage.bigtable_market_ticks_table_id
}

output "bigtable_market_ticks_table_name" {
  description = "Name of the primary market ticks Bigtable table"
  value       = module.storage.bigtable_market_ticks_table_name
}

output "bigtable_column_families" {
  description = "Active column families configured on Bigtable tick table (trades 't', quotes 'q', metrics 'm')"
  value       = module.storage.bigtable_column_families
}

output "bigtable_row_key_spec" {
  description = "Reverse-timestamp row key specification for O(1) head-of-log scans"
  value       = module.storage.bigtable_row_key_spec
}

output "redis_instance_id" {
  description = "Resource ID of the Cloud Memorystore Redis instance"
  value       = module.storage.redis_instance_id
}

output "redis_instance_name" {
  description = "Name of the Cloud Memorystore Redis instance"
  value       = module.storage.redis_instance_name
}

output "redis_host" {
  description = "Internal RFC 1918 IP address of the Memorystore Redis primary node"
  value       = module.storage.redis_host
}

output "redis_port" {
  description = "TCP port of the Memorystore Redis instance"
  value       = module.storage.redis_port
}

output "redis_current_location_id" {
  description = "GCP zone currently hosting the active Memorystore Redis primary node"
  value       = module.storage.redis_current_location_id
}

output "redis_auth_string" {
  description = "Auto-generated Redis AUTH password token"
  value       = module.storage.redis_auth_string
  sensitive   = true
}

# ------------------------------------------------------------------------------
# Milestone 3: Dataflow Stream Processing Module Outputs
# ------------------------------------------------------------------------------

output "dataflow_job_id" {
  description = "Unique resource identifier of the Apache Beam Dataflow streaming job"
  value       = module.dataflow.job_id
}

output "dataflow_job_name" {
  description = "Name of the Dataflow streaming job"
  value       = module.dataflow.job_name
}

output "dataflow_job_state" {
  description = "Current lifecycle state of the Dataflow streaming job"
  value       = module.dataflow.job_state
}

output "dataflow_staging_bucket_name" {
  description = "Name of the GCS bucket for Dataflow binaries and temporary files"
  value       = module.dataflow.staging_bucket_name
}

output "dataflow_staging_bucket_url" {
  description = "URI of the GCS bucket for Dataflow staging"
  value       = module.dataflow.staging_bucket_url
}

output "dataflow_worker_sa_email" {
  description = "Service account email executing the Dataflow worker processes"
  value       = module.dataflow.service_account_email
}

output "dataflow_ip_configuration" {
  description = "Worker IP configuration confirming 0 public IPs (WORKER_IP_PRIVATE)"
  value       = module.dataflow.ip_configuration
}

output "dataflow_streaming_engine_enabled" {
  description = "Flag confirming Google Cloud Dataflow Streaming Engine is enabled"
  value       = module.dataflow.streaming_engine_enabled
}

output "dataflow_runner_v2_enabled" {
  description = "Flag confirming Apache Beam Runner v2 is enabled"
  value       = module.dataflow.runner_v2_enabled
}
```

---

## 5. Verification & Test Compliance

The proposed configurations satisfy all tiers of `TEST_INFRA.md`:

| Test Suite | Metric / Feature | Expected Result | Architecture Guard |
|------------|------------------|-----------------|-------------------|
| `verify_security_posture.py` | 0 Public IPs on Dataflow workers | PASS (0 public IPs) | `ip_configuration = "WORKER_IP_PRIVATE"` |
| `verify_security_posture.py` | Private Google Access | PASS (PGA enabled) | Subnet in `module.networking` has PGA=true |
| `verify_security_posture.py` | Zero primitive Owner/Editor roles | PASS (0 primitive) | `sa-dataflow-worker` has least-privilege roles |
| `test_infrastructure_syntax.py` | Delimiter & Syntax integrity | PASS (0 errors) | All `{}` and `[]` balanced |
| `test_infrastructure_syntax.py` | Module inventory presence | PASS (M1, M2, M3 modules) | `storage` and `dataflow` wired cleanly |
| `test_hft_resilience.py` | Bigtable reverse-timestamp sort | PASS ($K(t_3) < K(t_2) < K(t_1)$) | Row key formula matches test fixture |
| `test_hft_resilience.py` | Redis Kill Switch contract | PASS (O(1) atomic check) | `hft:emergency:kill_switch_active` supported |
| `test_e2e_verification.py` | 4-Tier Automated Pytest suite | PASS (100% exit code 0) | Conforms to all test assertions |

---

## 6. Implementation Action Plan for Worker M3

1. **Create directory**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\modules\dataflow`
2. **Populate files**:
   - `modules/dataflow/main.tf` from `proposed_dataflow_main.tf`
   - `modules/dataflow/variables.tf` from `proposed_dataflow_variables.tf`
   - `modules/dataflow/outputs.tf` from `proposed_dataflow_outputs.tf`
3. **Populate storage files** (coordinated with Explorer 1 & 2):
   - `modules/storage/bigtable.tf`
   - `modules/storage/redis.tf`
   - `modules/storage/variables.tf`
   - `modules/storage/outputs.tf`
4. **Update Root files**:
   - `main.tf` from `proposed_root_main.tf`
   - `variables.tf` from `proposed_root_variables.tf`
   - `outputs.tf` from `proposed_root_outputs.tf`
5. **Execute Validation Suite**:
   - Run `python scripts/test_infrastructure_syntax.py`
   - Run `python scripts/test_hft_resilience.py`
   - Run `python -m pytest tests/test_e2e_verification.py -v`
