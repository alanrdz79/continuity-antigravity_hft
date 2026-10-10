# Dispatch — worker_m4_1
Target: Milestone 4 Implementation Worker (Autonomous Safety Orchestration).
Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m4_1


## 2026-10-10T09:01:15Z

You are the implementation Worker subagent for Milestone 4 (M4: Autonomous Safety Orchestration - EventArc v2 Triggers, Cloud Monitoring Latency & API Error Alert Policies, Gen 2 Emergency Shutdown Cloud Function, and Root Integration) of the HFT GCP Architecture project.
Your assigned working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m4_1
Target project path: C:\Users\alanr\teamwork_projects\hft_gcp_architecture

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read ORIGINAL_REQUEST.md first at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\orchestrator_hft_gcp\PROJECT.md
Read scripts/test_safety_orchestration.py at: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\scripts\test_safety_orchestration.py

Read the Explorer blueprints for Milestone 4:
1. Cloud Monitoring & EventArc Variables:
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_1\proposed_safety_orchestration_variables.tf
2. Gen 2 Cloud Function Implementation:
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_2\proposed_main.py
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_2\proposed_requirements.txt
3. Safety Orchestration Terraform Module & Root Wiring:
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_3\proposed_modules_safety_orchestration_main.tf
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_3\proposed_modules_safety_orchestration_variables.tf
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_3\proposed_modules_safety_orchestration_outputs.tf
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_3\proposed_root_main.tf
   - c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_3\proposed_root_variables.tf

Your exclusive write ownership in C:\Users\alanr\teamwork_projects\hft_gcp_architecture:
- functions/emergency_shutdown/main.py
- functions/emergency_shutdown/requirements.txt
- modules/safety_orchestration/main.tf
- modules/safety_orchestration/variables.tf
- modules/safety_orchestration/outputs.tf
- main.tf (wire module "safety_orchestration")
- variables.tf (declare any new variables)
- outputs.tf (export safety outputs)

Implementation instructions:
1. Implement functions/emergency_shutdown/:
   - Write functions/emergency_shutdown/requirements.txt based on explorer_m4_2's proposed_requirements.txt.
   - Write functions/emergency_shutdown/main.py based on explorer_m4_2's proposed_main.py, implementing the 4-stage emergency shutdown:
     * Stage 1: Atomic Redis Kill Switch (hft:emergency:kill_switch_active = 1).
     * Stage 2: Signed Binance API DELETE /api/v3/openOrders with HMAC-SHA256 signature.
     * Stage 3: Engine halt broadcast to Pub/Sub topic hft-safety-alerts.
     * Stage 4: Telegram alert notification payload formatting and dispatch.
     * Support CloudEvent (EventArc Pub/Sub) and HTTP fallback invocation.
2. Implement modules/safety_orchestration/:
   - Write modules/safety_orchestration/main.tf, variables.tf, outputs.tf:
     * Archive packaging of functions/emergency_shutdown/ with data "archive_file" and GCS source bucket.
     * Gen 2 Cloud Function in asia-northeast1, python311, sa-emergency-shutdown identity, secret environment variables from Secret Manager, and VPC connector support.
     * EventArc v2 Trigger on Pub/Sub topic hft-safety-alerts with sa-hft-eventarc service account, and Cloud Run invoker permissions (roles/run.invoker and roles/cloudfunctions.invoker).
     * Cloud Monitoring Pub/Sub notification channel for topic hft-safety-alerts.
     * Cloud Monitoring Alert Policies: Latency Spike (>800ms) and API Errors (429/418).
3. Root Wiring:
   - In root main.tf: uncomment and wire module "safety_orchestration" with dependencies on networking, iam, secrets, pubsub, storage.
   - In root variables.tf: add any missing variables (e.g., safety_latency_threshold_ms default 800.0, enable_serverless_vpc_connector, etc.).
   - In root outputs.tf: export safety outputs (function_uri, eventarc_trigger_id, alert_policy_ids).
4. Validation:
   - Run terraform init in C:\Users\alanr\teamwork_projects\hft_gcp_architecture to load new module.
   - Run terraform fmt -recursive and terraform validate.
   - Run terraform plan.
   - Run python scripts/test_safety_orchestration.py and verify exit code 0.
   - Run python scripts/test_infrastructure_syntax.py and verify exit code 0.
   - Run python scripts/run_all_tests.py and verify exit code 0.
   - Run python -m pytest tests/ -v and verify exit code 0.
5. Deliverables:
   - Detailed report.md and handoff.md in your working directory c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m4_1.
   - Send completion message to parent orchestrator.
