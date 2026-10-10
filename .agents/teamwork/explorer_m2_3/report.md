# Milestone 2 Technical Investigation & Integration Blueprint Report

**Subagent**: `explorer_m2_3` (Root Integration, Module Wiring & Remediations Explorer)  
**Milestone**: Milestone 2 (M2) — Market Ingestion & Ultra-Low-Latency Compute  
**Target Repository**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture`  
**Working Directory**: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m2_3`  
**Date**: 2026-10-09  

---

## Executive Summary

This report delivers the complete architectural integration blueprint and exact remediation code for Milestone 2 of the CONTINUITY HFT GCP Cloud Architecture. It addresses two critical workstreams:

1. **Root Module Integration**: Wiring the newly authored `modules/pubsub` and `modules/compute` into root `main.tf`, and exposing all necessary operational outputs (Compute Engine instance self-link, private IP, Pub/Sub topic IDs, subscription IDs, and placement policies) in root `outputs.tf`.
2. **Carry-Forward Remediations**: Resolving four specific defects identified during Milestone 1 adversarial testing:
   - Pinning the Private Service Access (PSA) global internal address to `10.10.16.0/20` in `modules/networking/main.tf` to avoid dropping Redis return traffic at the firewall.
   - Eliminating Python 3.12+ `SyntaxError: (unicode error) 'unicodeescape'` across all 6 test scripts by converting docstrings to raw strings (`r"""..."""`).
   - Fixing the PowerShell 5.1 parser error (`?.Source`) in `scripts/validate_terraform.ps1`.
   - Correcting the commented downstream service account reference in root `main.tf` line 152 to `module.iam.hft_eventarc_sa_email`.

---

## 1. Root Integration Blueprint

### 1.1. Module Orchestration Graph

```
                                  ┌───────────────────────────────┐
                                  │   google_project_service      │
                                  │    + time_sleep (30s)         │
                                  └───────────────┬───────────────┘
                                                  │
                         ┌────────────────────────┼────────────────────────┐
                         │                        │                        │
                         ▼                        ▼                        ▼
              ┌─────────────────────┐  ┌─────────────────────┐  ┌─────────────────────┐
              │  module.networking  │  │     module.iam      │  │   module.secrets    │
              │  - VPC & Subnets    │  │  - 5 Service Accts  │  │  - Binance API Keys │
              │  - Cloud NAT & PSA  │  │  - Least Privilege  │  │  - Redis/Tg Tokens  │
              └──────────┬──────────┘  └──────────┬──────────┘  └─────────────────────┘
                         │                        │
                         │       ┌────────────────┼────────────────┐
                         │       │                                 │
                         ▼       ▼                                 ▼
              ┌─────────────────────┐                   ┌─────────────────────┐
              │   module.compute    │                   │    module.pubsub    │
              │ - C3/C4 (Tokyo)     │                   │ - Trades, Orderbook │
              │ - gVNIC + Tier 1 Net│                   │ - Snapshots & DLQ   │
              │ - Zero Public IPs   │                   │ - Ordering=True     │
              │ - Compact Colocation│                   │ - Ack=10s           │
              └─────────────────────┘                   └─────────────────────┘
```

### 1.2. Root `main.tf` Wiring for `pubsub` and `compute`

In `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\main.tf`, replace the commented block at lines 100-120 with the following active module declarations:

```hcl
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
```

### 1.3. Root `outputs.tf` Additions for M2

Append the following outputs to `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\outputs.tf`:

```hcl
# ------------------------------------------------------------------------------
# Milestone 2: Compute Engine Module Outputs
# ------------------------------------------------------------------------------

output "hft_engine_instance_id" {
  description = "The unique server-assigned identifier of the HFT trading compute instance"
  value       = module.compute.instance_id
}

output "hft_engine_instance_name" {
  description = "The name of the C3/C4 HFT trading instance"
  value       = module.compute.instance_name
}

output "hft_engine_instance_self_link" {
  description = "The URI self link of the HFT trading compute instance"
  value       = module.compute.instance_self_link
}

output "hft_engine_private_ip" {
  description = "Primary RFC 1918 internal IP address of the HFT trading instance (zero public external IP)"
  value       = module.compute.internal_ip
}

output "hft_engine_zone" {
  description = "GCP Zone where the C3/C4 instance is provisioned (e.g. asia-northeast1-b)"
  value       = module.compute.zone
}

output "hft_engine_machine_type" {
  description = "Machine type utilized by the trading instance (e.g. c3-standard-4 or c4-standard-4)"
  value       = module.compute.machine_type
}

output "hft_engine_placement_policy_id" {
  description = "Resource policy ID of the compact collocated placement group"
  value       = module.compute.placement_policy_id
}

# ------------------------------------------------------------------------------
# Milestone 2: Pub/Sub Market Ingestion Module Outputs
# ------------------------------------------------------------------------------

output "pubsub_trades_topic_id" {
  description = "Resource ID of the market trades Pub/Sub topic"
  value       = module.pubsub.trades_topic_id
}

output "pubsub_trades_topic_name" {
  description = "Name of the market trades Pub/Sub topic"
  value       = module.pubsub.trades_topic_name
}

output "pubsub_orderbook_topic_id" {
  description = "Resource ID of the orderbook depth Pub/Sub topic"
  value       = module.pubsub.orderbook_topic_id
}

output "pubsub_orderbook_topic_name" {
  description = "Name of the orderbook depth Pub/Sub topic"
  value       = module.pubsub.orderbook_topic_name
}

output "pubsub_snapshots_topic_id" {
  description = "Resource ID of the market snapshots Pub/Sub topic"
  value       = module.pubsub.snapshots_topic_id
}

output "pubsub_snapshots_topic_name" {
  description = "Name of the market snapshots Pub/Sub topic"
  value       = module.pubsub.snapshots_topic_name
}

output "pubsub_safety_alerts_topic_id" {
  description = "Resource ID of the autonomous safety alerts Pub/Sub topic"
  value       = module.pubsub.safety_alerts_topic_id
}

output "pubsub_safety_alerts_dlq_topic_id" {
  description = "Resource ID of the Dead Letter Queue Pub/Sub topic"
  value       = module.pubsub.safety_alerts_dlq_topic_id
}

output "pubsub_all_topic_ids" {
  description = "Map of all provisioned Pub/Sub topic keys to their resource IDs"
  value       = module.pubsub.all_topic_ids
}

output "pubsub_trades_subscription_id" {
  description = "Resource ID of the HFT trading engine trades subscription"
  value       = module.pubsub.trades_subscription_id
}

output "pubsub_orderbook_subscription_id" {
  description = "Resource ID of the HFT trading engine orderbook subscription"
  value       = module.pubsub.orderbook_subscription_id
}

output "pubsub_safety_alerts_subscription_id" {
  description = "Resource ID of the emergency shutdown safety alerts subscription"
  value       = module.pubsub.safety_alerts_subscription_id
}
```

---

## 2. Carry-Forward Remediations Blueprint

### 2.1. Remediation 1: Pin PSA Global Internal Address in `modules/networking/main.tf`

- **Target File**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\modules\networking\main.tf`
- **Location**: Lines 78-87
- **Rationale**: Omitting the `address` attribute causes Google Cloud to dynamically select an arbitrary RFC 1918 block. If GCP assigns `172.16.0.0/20` or `192.168.0.0/20`, packets returning from Memorystore Redis will not match `allow_internal` (`source_ranges = ["10.10.0.0/16"]`) and will be blocked by `deny_all_ingress`. Setting `address = "10.10.16.0"` guarantees that the `/20` block spans `10.10.16.0 - 10.10.31.255`, safely within `10.10.0.0/16` and non-overlapping with subnets `10.10.1.0/24` and `10.10.2.0/24`.

#### Exact Code Modification:
**Before**:
```hcl
# Reserved internal IP address range for Service Networking peering
resource "google_compute_global_address" "hft_psa_address" {
  name          = var.psa_address_name
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = var.psa_prefix_length
  network       = google_compute_network.hft_vpc.id

  description = "Internal IP allocation block for Google Managed Services (Redis)"
}
```

**After**:
```hcl
# Reserved internal IP address range for Service Networking peering
resource "google_compute_global_address" "hft_psa_address" {
  name          = var.psa_address_name
  project       = var.project_id
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  address       = "10.10.16.0"
  prefix_length = var.psa_prefix_length
  network       = google_compute_network.hft_vpc.id

  description = "Internal IP allocation block for Google Managed Services (Redis)"
}
```

---

### 2.2. Remediation 2: Convert Python Docstrings to Raw Strings (`r"""..."""`)

- **Root Cause**: Under Python 3.12+, backslash-U in standard string literals (`"""`) triggers a unicode escape decoder. The text `Target: C:\Users\...` contains `\U`, which fails with:
  `SyntaxError: (unicode error) 'unicodeescape' codec can't decode bytes in position ...: truncated \UXXXXXXXX escape`
- **Verification**: Tested using `ast.parse()` across all 6 files. Converting the initial docstring delimiter to `r"""` achieves 100% valid AST parsing.

#### Exact Code Modifications for All 6 Files:

1. **`scripts/run_all_tests.py`** (Line 2):
   ```python
   # Before (Line 1-2):
   #!/usr/bin/env python3
   """

   # After (Line 1-2):
   #!/usr/bin/env python3
   r"""
   ```

2. **`scripts/test_hft_resilience.py`** (Line 2):
   ```python
   # Before (Line 1-2):
   #!/usr/bin/env python3
   """

   # After (Line 1-2):
   #!/usr/bin/env python3
   r"""
   ```

3. **`scripts/test_infrastructure_syntax.py`** (Line 2):
   ```python
   # Before (Line 1-2):
   #!/usr/bin/env python3
   """

   # After (Line 1-2):
   #!/usr/bin/env python3
   r"""
   ```

4. **`scripts/test_safety_orchestration.py`** (Line 2):
   ```python
   # Before (Line 1-2):
   #!/usr/bin/env python3
   """

   # After (Line 1-2):
   #!/usr/bin/env python3
   r"""
   ```

5. **`scripts/verify_security_posture.py`** (Line 2):
   ```python
   # Before (Line 1-2):
   #!/usr/bin/env python3
   """

   # After (Line 1-2):
   #!/usr/bin/env python3
   r"""
   ```

6. **`tests/test_e2e_verification.py`** (Line 1):
   ```python
   # Before (Line 1):
   """

   # After (Line 1):
   r"""
   ```

---

### 2.3. Remediation 3: Replace PowerShell 7 `?.Source` with PowerShell 5.1 Compatible Syntax

- **Target File**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\scripts\validate_terraform.ps1`
- **Root Cause**: Lines 37 and 104 use the null-conditional operator `?.`, which is unsupported in Windows PowerShell 5.1 and results in a fatal `ParserError`.

#### Exact Code Modification:

**Location 1 — Line 37**:
```powershell
# Before:
$TerraformBin = (Get-Command terraform -ErrorAction SilentlyContinue)?.Source

# After:
$TerraformCmd = Get-Command terraform -ErrorAction SilentlyContinue
$TerraformBin = if ($TerraformCmd) { $TerraformCmd.Source } else { $null }
```

**Location 2 — Lines 104-107**:
```powershell
# Before:
    $PythonBin = (Get-Command python -ErrorAction SilentlyContinue)?.Source
    if (-not $PythonBin) {
        $PythonBin = "python"
    }

# After:
    $PythonCmd = Get-Command python -ErrorAction SilentlyContinue
    $PythonBin = if ($PythonCmd) { $PythonCmd.Source } else { "python" }
```

---

### 2.4. Remediation 4: Fix Commented M4 Downstream Service Account Reference in `main.tf`

- **Target File**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\main.tf`
- **Location**: Line 152
- **Root Cause**: `modules/iam/outputs.tf` exports `output "hft_eventarc_sa_email"`. Line 152 in `main.tf` had `# eventarc_sa_email = module.iam.eventarc_sa_email`. When M4 is uncommented, Terraform fails with `Unsupported attribute`.

#### Exact Code Modification:
```hcl
# Before (Line 152):
#   eventarc_sa_email           = module.iam.eventarc_sa_email

# After (Line 152):
#   eventarc_sa_email           = module.iam.hft_eventarc_sa_email
```

---

## 3. Downstream Interface Contract Verification

| Consumer | Parameter | Source Module | Source Output | Status |
|----------|-----------|---------------|---------------|--------|
| `module.compute` | `network_id` | `module.networking` | `network_id` | Verified Compatible |
| `module.compute` | `subnet_id` | `module.networking` | `subnet_hft_id` | Verified Compatible |
| `module.compute` | `service_account_email` | `module.iam` | `hft_engine_sa_email` | Verified Compatible |
| `module.pubsub` | `hft_engine_sa_email` | `module.iam` | `hft_engine_sa_email` | Verified Compatible |
| `module.pubsub` | `dataflow_worker_sa_email` | `module.iam` | `dataflow_worker_sa_email` | Verified Compatible |
| `module.dataflow` (M3) | `trades_topic_id` | `module.pubsub` | `trades_topic_id` | Verified Compatible |
| `module.safety_orchestration` (M4) | `safety_alerts_topic_id` | `module.pubsub` | `safety_alerts_topic_id` | Verified Compatible |
| `module.safety_orchestration` (M4) | `eventarc_sa_email` | `module.iam` | `hft_eventarc_sa_email` | Verified Compatible (Fixed) |
| Root `outputs.tf` | `hft_engine_private_ip` | `module.compute` | `internal_ip` | Verified Compatible |
| Root `outputs.tf` | `hft_engine_instance_self_link` | `module.compute` | `instance_self_link` | Verified Compatible |

---

## 4. Verification & Testing Instructions for Implementer

Following application of these changes by the implementer:

1. **Verify Python Syntax**:
   ```bash
   python -c "import ast, glob; [print(f, 'OK') for f in glob.glob('**/*.py', recursive=True) if ast.parse(open(f, encoding='utf-8').read())]"
   ```
2. **Verify PowerShell 5.1 Script**:
   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\validate_terraform.ps1
   ```
3. **Verify Terraform Formatting & Validation**:
   ```powershell
   terraform fmt -check -diff -recursive
   terraform init -backend=false
   terraform validate
   ```
4. **Verify Plan Execution**:
   ```powershell
   terraform plan -no-color
   ```
   *Expected outcome*: `terraform validate` succeeds with zero errors, and plan includes all resources across M1 and M2.
