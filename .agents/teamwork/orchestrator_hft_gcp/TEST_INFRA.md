# E2E Test Infra: HFT GCP Architecture
Scope Document: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\orchestrator_hft_gcp\TEST_INFRA.md`

## Test Philosophy
- **Requirement-Driven & Opaque-Box**: Derived strictly from user acceptance criteria in `ORIGINAL_REQUEST.md` (## 2026-10-09T03:49:39Z).
- **Independent Validation**: Test suite exercises live cloud resources via GCP APIs, Terraform state validation, security scans, and metric triggers.
- **Methodology**: 4-Tier verification (Tier 1: Feature Coverage, Tier 2: Boundary & Corner Cases, Tier 3: Cross-Feature Pairwise, Tier 4: Real-World Workload Simulation).

## Feature Inventory & Test Coverage
| # | Feature | Requirement | Tier 1 (Coverage) | Tier 2 (Boundary) | Tier 3 (Cross-Feature) | Tier 4 (Real-World) |
|---|---------|-------------|:-----------------:|:-----------------:|:----------------------:|:-------------------:|
| F1 | Host Tooling (Terraform) | R1 | T1.1 - T1.5 | T2.1 - T2.5 | T3.1 | T4.1 |
| F2 | Isolated VPC & Cloud NAT | R3 | T1.6 - T1.10 | T2.6 - T2.10 | T3.2 | T4.2 |
| F3 | Least-Privilege IAM Matrix | R3 | T1.11 - T1.15 | T2.11 - T2.15 | T3.3 | T4.2 |
| F4 | Secret Manager Security | R3 | T1.16 - T1.20 | T2.16 - T2.20 | T3.4 | T4.3 |
| F5 | Pub/Sub Market Ingestion | R1 | T1.21 - T1.25 | T2.21 - T2.25 | T3.5 | T4.1 |
| F6 | C3/C4 Low-Latency Compute | R1 | T1.26 - T1.30 | T2.26 - T2.30 | T3.6 | T4.1 |
| F7 | Cloud Bigtable Tick Storage | R1 | T1.31 - T1.35 | T2.31 - T2.35 | T3.7 | T4.3 |
| F8 | Cloud Memorystore Redis | R1 | T1.36 - T1.40 | T2.36 - T2.40 | T3.8 | T4.3 |
| F9 | Dataflow Stream Processing | R1 | T1.41 - T1.45 | T2.41 - T2.45 | T3.9 | T4.3 |
| F10 | EventArc Safety Triggers | R2 | T1.46 - T1.50 | T2.46 - T2.50 | T3.10 | T4.4 |
| F11 | Emergency Shutdown Sink | R2 | T1.51 - T1.55 | T2.51 - T2.55 | T3.11 | T4.4 |
| F12 | Live Execution (`terraform apply`) | AC | T1.56 - T1.60 | T2.56 - T2.60 | T3.12 | T4.5 |
| F13 | Security & Network Scanners | AC | T1.61 - T1.65 | T2.61 - T2.65 | T3.13 | T4.5 |
| F14 | Architectural Report | R4 | T1.66 - T1.70 | T2.66 - T2.70 | T3.14 | T4.5 |

## Test Architecture
- **Test Runner Location**: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture\scripts`
  - `verify_security_posture.py`: Validates 0 public IPs on VMs, Private Google Access enabled on subnets, zero primitive Owner/Editor roles.
  - `validate_terraform_syntax.ps1`: Executes `terraform fmt -check`, `terraform validate`, and `terraform plan`.
  - `test_safety_orchestration.py`: Injects latency metric alert and verifies EventArc route to emergency shutdown sink.
- **Pass/Fail Semantics**:
  - Exit code 0 on all test scripts.
  - `terraform apply -auto-approve` completes with 0 errors and live resources in state.
  - `architecture_summary.md` satisfies all structural and analytical criteria.

## Coverage Thresholds
- Tier 1: 70 granular checks (5 per feature).
- Tier 2: 70 boundary and error handling checks (5 per feature).
- Tier 3: 14 cross-feature interaction verifications.
- Tier 4: 5 end-to-end real-world operational scenarios.
- **Total Minimum Test Checks**: 159 checks.
