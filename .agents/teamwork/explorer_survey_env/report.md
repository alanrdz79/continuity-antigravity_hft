# Phase 0 Survey Report: Environment, Tooling & GCP Infrastructure Readiness

**Author**: Explorer Subagent (`explorer_survey_env`)  
**Date**: 2026-10-09  
**Target Path**: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_survey_env\report.md`  
**Parent Orchestrator**: `orchestrator_hft_gcp` (`922fadba-e6b4-4339-a95e-d2e0ef391991`)  
**Project Objective**: High-Frequency Trading (HFT) Autonomous Cloud Architecture on GCP (Terraform IaC)

---

## 1. Executive Summary

This survey assesses the host environment, tooling availability, active Google Cloud Platform (GCP) project credentials, API enablement status, Asia-Northeast region machine type availability, and target repository state. 

**Core Finding**: Google Cloud SDK (v585.0.0) is installed and fully authenticated with active Application Default Credentials (ADC) for project `intrepid-decker-480417-e9` (`alanrdz787@gmail.com`). However, **Terraform is NOT currently installed** on the host and must be installed prior to running `terraform apply`. Tokyo region (`asia-northeast1`) has extensive C3 and C4 machine type support (specifically in `asia-northeast1-b` and `asia-northeast1-c`), and the target project directory `C:\Users\alanr\teamwork_projects\hft_gcp_architecture` has been initialized.

---

## 2. Environment & Tooling Audit

### 2.1 Terraform Status: ❌ NOT INSTALLED
- **Search Verification**:
  - Full recursive scan performed across user profile directories (`C:\Users\alanr`), `C:\Program Files`, `C:\Program Files (x86)`, `C:\ProgramData`, and root drive `C:\`.
  - Zero instances of `terraform.exe` found.
- **Impact**: Terraform configuration files can be generated and validated syntactically, but execution of `terraform init`, `terraform plan`, and `terraform apply -auto-approve` requires the Terraform binary to be installed on the host.
- **Recommended Action**:
  - The orchestrator or user should install Terraform via Windows Package Manager:
    ```powershell
    winget install HashiCorp.Terraform
    ```
  - Or download `terraform.exe` (v1.8.x or v1.9.x for Windows AMD64) and place it in a system PATH directory (e.g., `C:\Users\alanr\AppData\Local\Microsoft\WinGet\Packages` or `C:\Users\alanr\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin` or `C:\Windows\System32`).

### 2.2 Google Cloud SDK (gcloud): ✅ INSTALLED & CONFIGURED
- **Installation Location**: `C:\Users\alanr\AppData\Local\Google\Cloud SDK\google-cloud-sdk`
- **Version**: `585.0.0` (verified from SDK `VERSION` file)
- **Bundled Python**: Python 3.14.7
- **Active CLI Configuration**:
  - File: `C:\Users\alanr\AppData\Roaming\gcloud\configurations\config_default`
  - Active Profile: `default`
  - Active Account: `alanrdz787@gmail.com`
  - Active Project: `intrepid-decker-480417-e9`
- **Application Default Credentials (ADC)**:
  - File: `C:\Users\alanr\AppData\Roaming\gcloud\application_default_credentials.json`
  - Status: Valid and recently refreshed (2026-10-08 21:48:51 UTC)
  - Type: `authorized_user`
  - Quota Project: `intrepid-decker-480417-e9`
  - Test IAM Permissions Probe: Returned HTTP 200 OK via `cloudresourcemanager.googleapis.com`

---

## 3. GCP Project & Resource Survey

### 3.1 Project Identification
| Property | Value | Source / Evidence |
| :--- | :--- | :--- |
| **Project ID** | `intrepid-decker-480417-e9` | `gcloud/configurations/config_default:3` |
| **Project Number** | `735347232184` | Observed in API calls & Service Usage operations |
| **Account** | `alanrdz787@gmail.com` | `gcloud/configurations/config_default:2` |
| **Billing Account** | Active & Linked | Verified via Service Usage activations (2026-09-23) |

### 3.2 Pre-existing Project Resources
Investigation of gcloud audit and execution logs revealed existing infrastructure components in this project:
1. **Compute Engine VM**:
   - Name: `continuity-hft-binance`
   - Zone: `asia-northeast1-b`
   - Deployment: Configured with Docker and targeted by Cloud Build SSH deployments.
2. **Artifact Registry**:
   - Repository: `antigravity-repo` (Docker format, location `us-central1`).
3. **Cloud Build**:
   - Triggers: `disparador1sisthft` (linked to GitHub repo `continuity-hft-binance`).
   - Multiple builds completed successfully.

---

## 4. GCP APIs Audit & Requirements Matrix

### 4.1 Current Enablement Status
Based on operational logs and Service Usage telemetry:

| API Service | Current Status | Notes / Evidence |
| :--- | :--- | :--- |
| `compute.googleapis.com` | **ENABLED** | Enabled 2026-09-23; active instances in `asia-northeast1-b` |
| `cloudbuild.googleapis.com` | **ENABLED** | Enabled 2026-09-30; builds actively running |
| `artifactregistry.googleapis.com` | **ENABLED** | Repository `antigravity-repo` active |
| `cloudresourcemanager.googleapis.com` | **ENABLED** | ADC permissions verified (HTTP 200) |
| `serviceusage.googleapis.com` | **ENABLED** | Manages API lifecycle |

### 4.2 Target Architecture APIs Required
The HFT GCP Architecture requirements (R1, R2, R3) require provisioning several new GCP services:

| Target API Service | Required By | IaC Resource Types | Enablement Plan |
| :--- | :--- | :--- | :--- |
| `pubsub.googleapis.com` | R1 (Market ingestion) & R2 (Safety alerts) | `google_pubsub_topic`, `google_pubsub_subscription` | Must be declared in `services.tf` |
| `dataflow.googleapis.com` | R1 (Stream processing) | `google_dataflow_job` | Must be declared in `services.tf` |
| `bigtable.googleapis.com` / `bigtableadmin.googleapis.com` | R1 (Historical tick storage) | `google_bigtable_instance`, `google_bigtable_table` | Must be declared in `services.tf` |
| `redis.googleapis.com` | R1 (In-memory state caching) & R2 (Halt flag) | `google_redis_instance` | Must be declared in `services.tf` |
| `servicenetworking.googleapis.com` | R1/R3 (Memorystore Private IP Peering) | `google_service_networking_connection` | Must be declared in `services.tf` |
| `eventarc.googleapis.com` | R2 (Autonomous safety routing) | `google_eventarc_trigger` | Must be declared in `services.tf` |
| `cloudfunctions.googleapis.com` & `run.googleapis.com` | R2 (Emergency shutdown sink) | `google_cloudfunctions2_function` | Must be declared in `services.tf` |
| `secretmanager.googleapis.com` | R3 (API credentials protection) | `google_secret_manager_secret` | Must be declared in `services.tf` |
| `monitoring.googleapis.com` & `logging.googleapis.com` | R2 (Latency metrics & alert policies) | `google_monitoring_alert_policy` | Must be declared in `services.tf` |

### 4.3 Declarative Service Management Strategy
To avoid dependency race conditions during `terraform apply`, the Terraform foundation module must define all required services declaratively:
```hcl
locals {
  required_services = [
    "compute.googleapis.com",
    "pubsub.googleapis.com",
    "dataflow.googleapis.com",
    "bigtable.googleapis.com",
    "redis.googleapis.com",
    "servicenetworking.googleapis.com",
    "eventarc.googleapis.com",
    "cloudfunctions.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "monitoring.googleapis.com",
    "logging.googleapis.com",
    "iam.googleapis.com",
  ]
}

resource "google_project_service" "enabled_apis" {
  for_each                   = toset(local.required_services)
  project                    = var.project_id
  service                    = each.key
  disable_dependent_services = false
  disable_on_destroy         = false
}
```
All downstream modules (Compute, Redis, Bigtable, PubSub, EventArc) must explicitly declare `depends_on = [google_project_service.enabled_apis]`.

---

## 5. Asia-Northeast Region & Machine Type Availability

### 5.1 Geographic Proximity Rationale
- Binance Spot matching infrastructure is physically located in Tokyo, Japan.
- High-Frequency Trading latency constraints require sub-millisecond execution loops.
- Target Region: **`asia-northeast1` (Tokyo)**.
- Alternative / Failover Region: **`asia-northeast3` (Seoul)**.

### 5.2 Zone-by-Zone Machine Type Audit in `asia-northeast1`
An exhaustive aggregated machine type audit was extracted from gcloud compute queries for `asia-northeast1`:

| Zone | C3 Machine Types (Sapphire Rapids) | C4 Machine Types (Emerald Rapids) | High-Performance Features | Recommended for HFT? |
| :--- | :--- | :--- | :--- | :--- |
| **`asia-northeast1-a`** | ❌ None | ✅ `c4-standard-2` to `c4-standard-288`, `c4-highcpu-*`, `c4-highmem-*`, `-lssd` | gVNIC default, up to 100 Gbps networking | **Yes (C4 only)** |
| **`asia-northeast1-b`** | ✅ `c3-standard-4` to `c3-standard-176`, `c3-highcpu-*`, `c3-highmem-*`, `-lssd`, `c3-metal` | ✅ `c4-standard-2` to `c4-standard-288`, `c4-highcpu-*`, `c4-highmem-*`, `-lssd` | gVNIC default, Titanium offload engine | **PREMIUM (Recommended)** |
| **`asia-northeast1-c`** | ✅ `c3-standard-4` to `c3-standard-176`, `c3-highcpu-*`, `c3-highmem-*` | ✅ `c4-standard-2` to `c4-standard-288`, `c4-highcpu-*`, `c4-highmem-*` | gVNIC default | **Yes (Secondary)** |

### 5.3 Hardware Specifications for HFT
1. **Compute Engine C3 Series**:
   - Processor: 4th Gen Intel Xeon Scalable (Sapphire Rapids) with Titanium DPU.
   - Networking: Default Google Virtual NIC (gVNIC) with Tier 1 networking options.
   - Smallest instance: `c3-standard-4` (4 vCPUs, 16 GiB RAM).
2. **Compute Engine C4 Series**:
   - Processor: 5th Gen Intel Xeon Scalable (Emerald Rapids) with Titanium DPU.
   - Networking: Default gVNIC, reduced packet processing jitter.
   - Smallest instance: `c4-standard-2` (2 vCPUs, 7.5 GiB RAM) or `c4-standard-4` (4 vCPUs, 15 GiB RAM).

### 5.4 Quota Considerations & Graceful Fallback Strategy
- Standard or newly activated GCP billing projects frequently have standard Compute Engine CPU quotas (e.g., 24 to 32 vCPUs across all standard types), but regional C3/C4 quotas (`C3_CPUS` or `C4_CPUS` in `asia-northeast1`) may initially be restricted or require quota increase requests.
- **Implementation Recommendation**:
  - Expose `machine_type` as a configurable variable in Terraform:
    ```hcl
    variable "machine_type" {
      description = "Compute Engine machine type for HFT execution engine"
      type        = string
      default     = "c4-standard-4" # Optimal latency/cost footprint
    }
    ```
  - Document fallback choices:
    1. Primary: `c4-standard-4` (Zone `asia-northeast1-b`)
    2. Alternate: `c3-standard-4` (Zone `asia-northeast1-b`)
    3. Fallback: `c2-standard-4` (Compute-optimized Cascade Lake, available across all zones)
    4. General Fallback: `n2-standard-4` (with `nic_type = "GVNIC"`)

---

## 6. Target Directory Inspection

### 6.1 Status & Structure
- **Target Path**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture`
- **Initial State**: Did not exist at survey dispatch.
- **Survey Action**: Directory created and initialized with baseline `README.md`.
- **Target Architecture Layout**:
  ```
  C:\Users\alanr\teamwork_projects\hft_gcp_architecture/
  ├── README.md
  ├── main.tf                 # Root module orchestrating all subsystems
  ├── variables.tf            # Project ID, region, zones, machine types, CIDR blocks
  ├── outputs.tf              # Endpoints, topics, instance IDs, connection strings
  ├── terraform.tfvars        # Default variable values for intrepid-decker-480417-e9
  ├── versions.tf             # Terraform >= 1.5, Google provider ~> 5.0
  ├── architecture_summary.md # Comprehensive delivery documentation
  └── modules/
      ├── vpc/                # Isolated VPC, subnets, Cloud NAT, IAP firewall, PSA
      ├── iam/                # Dedicated least-privilege service accounts & bindings
      ├── compute/            # C3/C4 Compute Engine with gVNIC in asia-northeast1-b
      ├── pubsub/             # Market data ingestion topics, safety topics, subscriptions
      ├── dataflow/           # Streaming pipeline from Pub/Sub to storage sinks
      ├── storage/            # Cloud Bigtable (tick data) & Memorystore Redis (caching)
      ├── eventarc/           # Autonomous safety triggers & Emergency Shutdown sink
      └── secrets/            # Secret Manager for Binance credentials & API keys
  ```

---

## 7. Actionable Findings & Next Steps for Orchestrator

1. **Install Terraform**:
   - Instruct the user or orchestrator to run `winget install HashiCorp.Terraform` so `terraform` is accessible via PATH.
2. **Provider Configuration**:
   - Configure the root `versions.tf` / `main.tf` to inherit the verified ADC credentials and target project:
     ```hcl
     provider "google" {
       project = "intrepid-decker-480417-e9"
       region  = "asia-northeast1"
     }
     ```
3. **Module Execution Sequence**:
   - Milestone 1: VPC Networking, IAM service accounts, Secret Manager.
   - Milestone 2: Pub/Sub and Storage (Cloud Bigtable SSD cluster, Memorystore Redis with PSA peering).
   - Milestone 3: Compute Engine C3/C4 in `asia-northeast1-b` with Cloud NAT egress and gVNIC.
   - Milestone 4: EventArc Autonomous Safety Orchestration (latency alert policy -> trigger -> emergency kill switch).
   - Milestone 5: Verification & Architectural Documentation (`architecture_summary.md`).
