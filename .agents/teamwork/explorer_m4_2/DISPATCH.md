## 2026-10-10T04:45:28Z
You are Explorer 2 for Milestone 4 (M4: Gen 2 Emergency Shutdown Cloud Function) of the HFT GCP Architecture project.
Your assigned working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_2
Target project path: C:\Users\alanr\teamwork_projects\hft_gcp_architecture

MANDATORY: Read ORIGINAL_REQUEST.md first at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\orchestrator_hft_gcp\PROJECT.md
Read TEST_INFRA.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\orchestrator_hft_gcp\TEST_INFRA.md
Read scripts/test_safety_orchestration.py at: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\scripts\test_safety_orchestration.py

Your exploration focus:
1. Design the Gen 2 Cloud Function implementation in functions/emergency_shutdown/:
   - Language / Runtime: Python 3.11+ using functions-framework.
   - Handler contract: functions.cloud_event handler (supporting CloudEvent from EventArc/Pub/Sub) with fallback for direct HTTP invocation.
   - Complete 4-stage emergency execution logic:
     * Stage 1: Atomic Redis Kill Switch. Connect to Cloud Memorystore Redis over TLS with AUTH, execute SET hft:emergency:kill_switch_active 1 (O(1) sub-microsecond atomic flag).
     * Stage 2: Binance Order Purge. Retrieve Binance API credentials from environment/Secret Manager, generate HMAC-SHA256 signed query string with timestamp and recvWindow=5000, and execute HTTP DELETE /api/v3/openOrders with X-MBX-APIKEY header.
     * Stage 3: Engine Halt Signal. Publish engine worker halt message to Pub/Sub topic hft-safety-alerts.
     * Stage 4: Telegram Alert Broadcast. Format structured Markdown/HTML alert message payload and dispatch to Telegram webhook/alert sink.
   - requirements.txt dependencies: functions-framework>=3.5.0, redis>=5.0.0, requests>=2.31.0, google-cloud-pubsub>=2.19.0.
   - Unit tests / mocking: Ensure functions/emergency_shutdown/ code can be exercised in mock mode when credentials or live cloud endpoints are not reached.
2. Deliverables:
   - Complete proposed source code for functions/emergency_shutdown/main.py and requirements.txt.
   - Document findings and proposed code in report.md and a self-contained handoff.md in your working directory c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m4_2.
   - Send completion message to parent orchestrator.
