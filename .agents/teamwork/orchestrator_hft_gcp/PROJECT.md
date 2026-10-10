# Project: Real-Time HFT Autonomous Cloud Architecture on GCP
Scope Document: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\orchestrator_hft_gcp\PROJECT.md`
Target Project Path: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture`
Active GCP Project: `intrepid-decker-480417-e9`
Target Region: `asia-northeast1` (Tokyo, Japan - closest to Binance matching engine)

---

## Architecture Overview
The system implements a production-ready, ultra-low-latency High-Frequency Trading (HFT) autonomous infrastructure on Google Cloud Platform:
1. **Networking Layer**: Dedicated custom VPC with private subnets in `asia-northeast1-b` and `asia-northeast1-c`. Zero public external IP addresses on trading instances. Cloud Router & Cloud NAT for secure external outbound API connectivity to Binance. Private Google Access and Private Service Access (PSA peering) for serverless and managed services.
2. **Security & IAM**: 5 dedicated least-privilege service accounts (`sa-hft-engine`, `sa-dataflow-worker`, `sa-hft-eventarc`, `sa-emergency-shutdown`, `sa-cicd-deployer`). Zero primitive `Owner` or `Editor` roles. Secret Manager for encrypted Binance API keys and trading credentials.
3. **Market Data Streaming**: Multi-topic Google Cloud Pub/Sub with message ordering enabled (`<symbol>_<stream>`), regional storage policy locked to `asia-northeast1`, dead-letter topics (`hft-safety-alerts-dlq`), and low ack deadlines (10s).
4. **Low-Latency Compute Engine**: C3/C4 series instances (Intel Sapphire Rapids / Emerald Rapids) with Google Virtual NIC (gVNIC) enabled, Tier 1 networking bandwidth, Premium Network Tier, and compact placement policy (`COLLOCATED`) for sub-microsecond intra-rack latency.
5. **State Storage & High-Speed Caching**:
   - Cloud Bigtable Production SSD in `asia-northeast1-c` with reverse timestamp row keys (`{symbol}#{Long.MAX_VALUE - timestamp_micros}#{seq_id}`) and column families for trades, quotes, and metrics.
   - Cloud Memorystore for Redis Standard HA with AUTH enabled, in-transit encryption, connected via PSA VPC peering.
6. **Dataflow Stream Processing**: Apache Beam streaming pipeline with Runner v2 and Streaming Engine dual-sinking processed market depth to Bigtable and Redis.
7. **Autonomous Safety Orchestration**: Cloud EventArc v2 triggers binding Cloud Monitoring alerts (network latency spikes > 800ms, API error codes 429/418) and Pub/Sub emergency alerts to an Emergency Shutdown Gen 2 Cloud Function sink (atomic Redis kill-switch flag, Binance cancel-all API request, engine pause, and Telegram alert).

---

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| F1 | Host Tooling & Terraform Provisioning Setup | Verification and automated installation of Terraform CLI on host | M1 | explorer_survey_env |
| F2 | Isolated VPC Network & Cloud NAT | Dedicated VPC, private subnets, Private Google Access, Cloud NAT (0 public IPs) | M1 | explorer_survey_safety |
| F3 | Least-Privilege IAM Matrix | 5 isolated service accounts, fine-grained resource roles, 0 primitive roles | M1 | explorer_survey_safety |
| F4 | Secret Manager Security | Encrypted storage of Binance API credentials with restricted accessor IAM | M1 | explorer_survey_safety |
| F5 | Pub/Sub Market Data Ingestion | Topics (`trades`, `orderbook`, `snapshots`, `dlq`), message ordering, regional policy | M2 | explorer_survey_arch |
| F6 | C3/C4 Low-Latency Compute Engine | C3/C4 VM with gVNIC, Tier 1 networking, collocated placement in Tokyo | M2 | explorer_survey_arch |
| F7 | Cloud Bigtable Tick Storage | SSD instance in `asia-northeast1`, reverse timestamp schema, column families | M3 | explorer_survey_arch |
| F8 | Cloud Memorystore Redis Cache | Redis Standard HA with AUTH, connected via PSA VPC peering | M3 | explorer_survey_arch |
| F9 | Dataflow Stream Processing Pipeline | Apache Beam streaming pipeline definition with Runner v2 & Streaming Engine | M3 | explorer_survey_arch |
| F10 | Cloud EventArc Safety Triggers | EventArc v2 event routing for latency spikes (>800ms) and API errors | M4 | explorer_survey_safety |
| F11 | Emergency Shutdown & Alert Sink | Gen 2 Cloud Function / Pub/Sub alert sink executing atomic kill-switch | M4 | explorer_survey_safety |
| F12 | Live Execution (`terraform apply -auto-approve`) | Automated execution of Terraform to provision live cloud resources in project | M5 | ORIGINAL_REQUEST R1 |
| F13 | Automated Security & Network Verification | Python validation suite verifying 0 public IPs, PGA, and IAM least-privilege | M5 | ORIGINAL_REQUEST AC |
| F14 | Comprehensive Architectural Documentation | Detailed `architecture_summary.md` with procedure, validation, future checklist | M6 | ORIGINAL_REQUEST R4 |

---

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Foundations: Tooling, VPC, IAM & Secrets | Terraform setup on host, VPC, Subnets, Cloud NAT, 5 Service Accounts, Secret Manager | none | DONE |
| M2 | Market Ingestion & Ultra-Low-Latency Compute | Pub/Sub topics/subscriptions, C3/C4 Compute Engine with gVNIC in Tokyo (`asia-northeast1`) | M1 | DONE |
| M3 | Storage, State Caching & Stream Processing | Cloud Bigtable SSD, Memorystore Redis (PSA peering), Dataflow stream processing config | M1, M2 | DONE |
| M4 | Autonomous Safety Orchestration | EventArc v2 triggers, Cloud Monitoring latency/error alert policies, Emergency Shutdown sink | M1, M2, M3 | DONE |
| M5 | Live Cloud Execution & Security Posture Verification | Run `terraform init/validate/plan/apply -auto-approve`, execute `verify_security_posture.py` live | M1, M2, M3, M4 | DONE |
| M6 | Architectural Documentation & Final Audit | Write `architecture_summary.md`, checklist of future improvements, forensic audit | M5 | DONE |

---

## Code Layout
Target Project Directory: `C:\Users\alanr\teamwork_projects\hft_gcp_architecture`
```
C:\Users\alanr\teamwork_projects\hft_gcp_architecture\
├── main.tf                       # Root Terraform entrypoint and provider configuration
├── variables.tf                  # Global input variables (project_id, region, zone, machine_type)
├── outputs.tf                    # Root output definitions (IPs, topic names, cluster IDs)
├── terraform.tfvars              # Configured variables for project intrepid-decker-480417-e9
├── modules/
│   ├── networking/               # VPC, subnets, Cloud Router, Cloud NAT, PSA peering
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── iam/                      # 5 Service accounts, custom roles, IAM least-privilege bindings
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── secrets/                  # Secret Manager secrets and IAM bindings
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── pubsub/                   # Pub/Sub topics, subscriptions, schemas, DLT
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── compute/                  # C3/C4 instance, gVNIC, placement policy, startup script
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── storage/                  # Cloud Bigtable instance & tables, Memorystore Redis
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── dataflow/                 # Streaming pipeline specification & resources
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   └── safety_orchestration/     # EventArc v2 triggers, Monitoring alerts, Emergency Function
│       ├── main.tf
│       ├── variables.tf
│       └── outputs.tf
├── functions/
│   └── emergency_shutdown/       # Gen 2 Cloud Function code for atomic halt
│       ├── main.py
│       └── requirements.txt
├── scripts/
│   ├── install_terraform.ps1     # Automated installation script for Terraform CLI
│   ├── verify_security_posture.py # Automated live verification of VPC, 0 public IPs, IAM
│   └── run_pipeline_test.py      # E2E test harness for Pub/Sub and safety triggers
└── architecture_summary.md       # Final architectural report and future improvements
```

---

## Interface Contracts
### Networking ↔ Compute & Storage
- VPC Network ID: `module.networking.network_id`
- HFT Subnet ID: `module.networking.subnet_hft_id`
- PSA Connection: `module.networking.private_service_access_connection` (Memorystore Redis must declare `depends_on = [module.networking.private_service_access_connection]`)

### IAM ↔ Compute, Dataflow & Functions
- Compute SA Email: `module.iam.hft_engine_sa_email`
- Dataflow SA Email: `module.iam.dataflow_worker_sa_email`
- Emergency Function SA Email: `module.iam.emergency_shutdown_sa_email`

### Pub/Sub ↔ Compute & Dataflow
- Market Trades Topic: `module.pubsub.trades_topic_id`
- Orderbook Topic: `module.pubsub.orderbook_topic_id`
- Safety Alerts Topic: `module.pubsub.safety_alerts_topic_id`

### Safety Orchestration ↔ Trading Engine & Monitoring
- EventArc Trigger ID: `module.safety_orchestration.eventarc_trigger_id`
- Emergency Function URL: `module.safety_orchestration.emergency_function_uri`
- Kill Switch Redis Key: `hft:emergency:kill_switch_active`
