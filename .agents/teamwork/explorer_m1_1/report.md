# Technical Investigation Report: Tooling, Root Terraform Architecture & GCP Service Enablement

- **Subagent**: `explorer_m1_1`
- **Milestone**: Milestone 1 (M1: Foundations, Tooling & Root Configuration)
- **Target Project Directory**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture`
- **Active GCP Project**: `intrepid-decker-480417-e9`
- **Target Region**: `asia-northeast1` (Tokyo, Japan)
- **Date**: 2026-10-09

---

## 1. Executive Summary

This investigation covers the initial tooling prerequisites and the root Terraform foundation for deploying the High-Frequency Trading (HFT) autonomous cloud architecture on Google Cloud Platform. 

Key findings:
1. **Terraform Host Status**: Terraform CLI is currently **not installed** in PATH on the Windows host.
2. **Tooling Remediation Strategy**: Both `winget` (v1.29.380) and standalone binary download via `curl.exe` from HashiCorp's official CDN were verified. Crucially, `C:\Users\alanr\.local\bin` is **already present** in the user's system PATH. Therefore, extracting `terraform.exe` directly into `C:\Users\alanr\.local\bin` guarantees immediate execution without requiring administrative/UAC elevation or system restarts.
3. **GCP Project & Credentials Status**: Google Cloud SDK 585.0.0 and Application Default Credentials (ADC) are fully active and bound to project `intrepid-decker-480417-e9` under `alanrdz787@gmail.com`. The Terraform Google provider can authenticate out of the box with zero additional credential prompts.
4. **Declarative Service Management**: 11 mandatory GCP APIs plus 3 auxiliary APIs are identified. Declarative management via `google_project_service` with `disable_on_destroy = false` and `disable_dependent_services = false` prevents service disruptions to existing compute/storage assets in the project.

---

## 2. Tooling: Automated Terraform Installation Blueprint

### 2.1 Environmental Diagnostics
- Command `terraform version` returned `CommandNotFoundException` (exit code 1).
- Command `winget --version` returned `v1.29.380`.
- Directory `C:\Users\alanr\.local\bin` exists and contains `uv.exe`, `uvw.exe`, `uvx.exe`.
- Inspection of `$env:PATH` confirmed `C:\Users\alanr\.local\bin` is loaded in every PowerShell session.
- HTTP HEAD request via `curl.exe -I https://releases.hashicorp.com/terraform/1.16.5/terraform_1.16.5_windows_amd64.zip` confirmed HTTP 200 OK (size: 36,763,886 bytes).

### 2.2 Recommended Script: `scripts/install_terraform.ps1`
The implementation script has been authored in this working directory as `proposed_install_terraform.ps1`. When copied to `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\scripts\install_terraform.ps1`, it provides a resilient dual-path workflow:
1. Checks if `terraform` is already in PATH. If so, prints version and exits cleanly.
2. Attempts silent installation via `winget install --id HashiCorp.Terraform -e --silent --accept-package-agreements --accept-source-agreements`.
3. If `winget` fails or requires interactive UAC prompts, automatically falls back to downloading the standalone `terraform_${version}_windows_amd64.zip` directly from HashiCorp releases.
4. Extracts `terraform.exe` directly into `$HOME\.local\bin`.
5. Guarantees persistence by validating user environment variable PATH and current session `$env:PATH`.
6. Executes `terraform version` to verify success.

---

## 3. Root Terraform Architecture Specification

The root directory `C:\Users\alanr\teamwork_projects\hft_gcp_architecture` requires four foundational configuration files plus outputs:

### 3.1 Provider Configuration (`main.tf`)
- **Terraform Core**: `required_version = ">= 1.5.0"`.
- **Required Providers**:
  - `hashicorp/google` (`~> 6.0` or `~> 5.38.0`): Core GCP infrastructure.
  - `hashicorp/google-beta` (`~> 6.0`): Low-latency placement policies, gVNIC settings, EventArc v2 features.
  - `hashicorp/random` (`~> 3.6`): Resource name entropy where required.
  - `hashicorp/time` (`~> 0.12`): Propagation sleep periods after enabling APIs.
- **Provider Blocks**:
  - Set default `project = var.project_id`, `region = var.region`, and `zone = var.primary_zone`.
- **Module Orchestration Pattern**:
  - Modules are structured hierarchically:
    - Foundation (M1): `networking`, `iam`, `secrets`.
    - Compute & Ingestion (M2): `pubsub`, `compute`.
    - Storage & Processing (M3): `storage` (Bigtable, Redis), `dataflow`.
    - Safety (M4): `safety_orchestration` (EventArc v2, Cloud Monitoring, Cloud Functions).
  - Explicit `depends_on = [google_project_service.required_services, time_sleep.wait_for_services]` ensures no race condition where API calls hit un-enabled GCP services.

### 3.2 Global Input Variables (`variables.tf`)
Variables must enforce strict types, sensible defaults, and validation descriptions:
- `project_id`: string, default `"intrepid-decker-480417-e9"`.
- `region`: string, default `"asia-northeast1"` (Tokyo region, minimized round-trip time to Binance).
- `primary_zone`: string, default `"asia-northeast1-b"` (verified zone containing Intel Sapphire Rapids C3 and Emerald Rapids C4 compute series).
- `secondary_zone`: string, default `"asia-northeast1-c"` (secondary zone for HA replication).
- `environment`: string, default `"production"`.
- `machine_type`: string, default `"c3-standard-4"`.
- `vpc_name`: string, default `"hft-primary-vpc"`.
- `subnet_cidr_primary`: string, default `"10.10.1.0/24"`.
- `subnet_cidr_secondary`: string, default `"10.10.2.0/24"`.
- `redis_memory_size_gb`: number, default `5`.
- `gcp_services`: list(string), listing all required GCP service endpoints.

### 3.3 Concrete Variable Definitions (`terraform.tfvars`)
Pins the operational values for the live deployment in project `intrepid-decker-480417-e9`:
```hcl
project_id            = "intrepid-decker-480417-e9"
region                = "asia-northeast1"
primary_zone          = "asia-northeast1-b"
secondary_zone        = "asia-northeast1-c"
environment           = "production"
machine_type          = "c3-standard-4"
vpc_name              = "hft-primary-vpc"
subnet_cidr_primary   = "10.10.1.0/24"
subnet_cidr_secondary = "10.10.2.0/24"
redis_memory_size_gb  = 5
```

---

## 4. GCP Service Enablement & Protection (`services.tf`)

### 4.1 Required Service Catalog
The following 14 APIs must be enabled declaratively:
| # | Service API | Purpose | Already Active? |
|---|-------------|---------|-----------------|
| 1 | `compute.googleapis.com` | C3/C4 Compute Engine VMs, Custom VPC, Cloud NAT | YES |
| 2 | `pubsub.googleapis.com` | High-throughput market data streaming ingestion | YES |
| 3 | `dataflow.googleapis.com` | Apache Beam streaming data pipeline | NO |
| 4 | `bigtable.googleapis.com` | Low-latency tick history storage (SSD) | NO |
| 5 | `redis.googleapis.com` | Memorystore Redis state cache & emergency kill switch | NO |
| 6 | `eventarc.googleapis.com` | Autonomous safety event routing | NO |
| 7 | `cloudfunctions.googleapis.com` | Serverless emergency shutdown execution | YES |
| 8 | `secretmanager.googleapis.com` | Binance API credentials storage | YES |
| 9 | `monitoring.googleapis.com` | Latency spike & error metric alerts | YES |
| 10 | `servicenetworking.googleapis.com` | Private Services Access (PSA) peering for Redis | NO |
| 11 | `cloudbuild.googleapis.com` | Serverless function compilation and container building | YES |
| 12 | `run.googleapis.com` | Cloud Run Admin API (underlying host for Gen 2 Functions) | YES |
| 13 | `artifactregistry.googleapis.com` | OCI container repository | YES |
| 14 | `iam.googleapis.com` | Service account creation & fine-grained role assignment | YES |

### 4.2 Critical Safety Flags
In Terraform, `google_project_service` defaults can accidentally tear down production services on destruction. To prevent catastrophic accidental deprovisioning:
```hcl
resource "google_project_service" "required_services" {
  for_each = toset(local.required_services)

  project                    = var.project_id
  service                    = each.key
  disable_on_destroy         = false
  disable_dependent_services = false
}
```
- `disable_on_destroy = false`: Ensures that running `terraform destroy` or modifying configurations never disables these critical Google Cloud APIs or shuts down existing workloads running in project `intrepid-decker-480417-e9`.
- `disable_dependent_services = false`: Prevents cascading accidental teardowns of APIs that have shared dependencies (e.g., disabling Cloud Build tearing down Cloud Run or Artifact Registry).

### 4.3 Propagation Race Condition Safeguard
Enabling an API via GCP Service Usage API is asynchronous across Google's global routing infrastructure. There is often a 10 to 30-second delay between when the API reports "ENABLED" and when IAM / Compute Engine APIs accept provision requests.
A `time_sleep` resource is recommended:
```hcl
resource "time_sleep" "wait_for_services" {
  depends_on      = [google_project_service.required_services]
  create_duration = "30s"
}
```
All downstream modules should depend on `[google_project_service.required_services, time_sleep.wait_for_services]`.

---

## 5. Artifact Delivery Summary

The following proposed source files have been generated in this agent's workspace:
1. `proposed_install_terraform.ps1`: Automated installer script for Windows host.
2. `proposed_main.tf`: Root provider and module orchestrator.
3. `proposed_variables.tf`: Fully typed global variables with defaults.
4. `proposed_terraform.tfvars`: Production variable assignments for `intrepid-decker-480417-e9`.
5. `proposed_services.tf`: Declarative API activation with safety safeguards.
6. `proposed_outputs.tf`: Root output definitions.

These files are ready to be integrated into `C:\Users\alanr\teamwork_projects\hft_gcp_architecture` by the implementer subagent during Milestone 1 execution.
