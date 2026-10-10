## 2026-10-09T04:36:54Z
You are the implementation Worker subagent for Milestone 2 (M2: Market Ingestion via Pub/Sub, Low-Latency Compute Engine C3/C4, and Root Integration) of the HFT GCP Architecture project.
Your assigned working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m2
Target project path: C:\Users\alanr\teamwork_projects\hft_gcp_architecture

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read ORIGINAL_REQUEST.md first at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\orchestrator_hft_gcp\PROJECT.md

Read the Explorer blueprints for Milestone 2:
1. Pub/Sub Module: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m2_1\handoff.md and proposed_*.tf
2. Compute Engine Module: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m2_2\handoff.md and proposed_*.tf
3. Root Wiring & Carry-Forward Remediations: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m2_3\handoff.md

Your exclusive write ownership in C:\Users\alanr\teamwork_projects\hft_gcp_architecture:
- modules/pubsub/variables.tf
- modules/pubsub/main.tf
- modules/pubsub/outputs.tf
- modules/compute/variables.tf
- modules/compute/main.tf
- modules/compute/outputs.tf
- modules/compute/startup_script.sh
- modules/networking/main.tf (apply PSA address pinning)
- main.tf (wire pubsub & compute, fix line 152 commented eventarc SA email)
- outputs.tf (export pubsub and compute outputs)
- scripts/*.py and tests/*.py (convert docstrings to raw strings r"""...""")
- scripts/validate_terraform.ps1 (update to standard PowerShell 5.1 syntax)

Implementation instructions:
1. Implement modules/pubsub/:
   - Topics: hft-market-trades, hft-market-orderbook, hft-market-snapshots, hft-safety-alerts, hft-safety-alerts-dlq, plus alias hft-orderbook-depth.
   - Regional Tokyo storage policy (asia-northeast1).
   - Low-latency subscriptions with message ordering, ack deadline 10s, DLT policy with 5 retries.
   - IAM bindings for sa-hft-engine and sa-dataflow-worker.
2. Implement modules/compute/:
   - C3/C4 VM instance in Tokyo (asia-northeast1-b or asia-northeast1-c), machine type c4-standard-4 (fallback c3-standard-4).
   - Dynamic disk type: hyperdisk-balanced for C4, pd-ssd for C3.
   - gVNIC enabled (nic_type = "GVNIC"), Tier 1 network bandwidth tier.
   - Collocated compact placement policy (google_compute_resource_policy collocated = true).
   - Network interface attached to subnet_hft_id with ZERO access_config (0 public external IPs).
   - Service account sa-hft-engine.
   - Startup script tuning TCP socket buffers and gVNIC queue settings.
3. Root wiring & carry-forward fixes:
   - Wire module pubsub and module compute into root main.tf with explicit depends_on.
   - Export outputs in root outputs.tf.
   - Fix 1: Add address = "10.10.16.0" to google_compute_global_address.hft_psa_address in modules/networking/main.tf.
   - Fix 2: Convert docstrings in scripts/*.py and tests/*.py to raw strings r"""...""" to eliminate Python 3.12+ unicode escape errors.
   - Fix 3: In scripts/validate_terraform.ps1, replace ?.Source with PowerShell 5.1 syntax.
   - Fix 4: In main.tf line 152, correct commented reference to module.iam.hft_eventarc_sa_email.
4. Validation:
   - Run terraform init (if needed to recognize new modules).
   - Run terraform fmt -recursive, terraform validate, and terraform plan.
   - Run python scripts/test_infrastructure_syntax.py and verify exit code 0.
   - Run powershell -ExecutionPolicy Bypass -File scripts\validate_terraform.ps1 and verify exit code 0.
5. Documentation:
   - Write report.md and handoff.md in your working directory.
   - Send completion message to parent orchestrator.
