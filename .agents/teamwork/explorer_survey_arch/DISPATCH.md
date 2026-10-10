## 2026-10-09T03:52:26Z
You are an Explorer subagent in Phase 0 (Survey) of the HFT GCP Architecture project.
Your assigned working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_survey_arch
MANDATORY: Read ORIGINAL_REQUEST.md first at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Pay special attention to the section under ## 2026-10-09T03:49:39Z.

Your specific exploration focus:
1. Core HFT Infrastructure Specifications:
   - Pub/Sub architecture: topics, subscriptions for market data ingestion (order books, trades), message ordering, retention, Dead Letter Topics (DLT).
   - Dataflow streaming architecture: Apache Beam streaming pipeline design, runner v2, streaming engine, Pub/Sub to Bigtable/Redis pipeline specifications.
   - Low-Latency Compute Engine: C3 / C4 series instance configuration, gVNIC (Google Virtual NIC) enabled, CPU platform, placement policy / compact placement if applicable, network tier (Premium), region selection (Asia-Northeast, Tokyo asia-northeast1 for Binance matching closeness).
   - Storage Architecture:
     * Cloud Bigtable: instance type, cluster configuration in asia-northeast, storage type (SSD), table schema for tick data (row key design, column families: trades, quotes, latency metrics).
     * Cloud Memorystore for Redis: tier (Basic vs Standard HA), memory size, version, authorized network (VPC peering / private service connection), redis transit encryption/auth.
2. Best Practices & Dependencies:
   - Document all Terraform resource types, module design, variables, outputs, and cross-resource dependencies.
3. Synthesis & Output:
   - Write your complete findings to c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_survey_arch\report.md
   - Write a self-contained handoff report to c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_survey_arch\handoff.md
   - Send a message to your parent with the summary and confirmation when done.
