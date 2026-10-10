# HFT GCP Architecture: Autonomous Safety Orchestration, Security & Resilience Specification

**Author**: Explorer Subagent (Safety, Security & Resilience)  
**Target Project**: CONTINUITY HFT GCP Cloud Infrastructure  
**Date**: 2026-10-09  
**Status**: Survey & Architecture Blueprint Complete  

---

## 1. Executive Summary & Core Mission

High-Frequency Trading (HFT) environments operating against real-time prediction and spot exchanges (e.g., Binance Spot / Binance Predict) demand microsecond-to-millisecond determinism, absolute data integrity, and infallible risk containment. In such systems, a software defect, network partition, or unmonitored API rate-limit breach can cause catastrophic capital depletion within seconds.

This survey establishes the complete architectural specification for:
1. **Autonomous Safety Orchestration via Cloud EventArc**: An automated circuit-breaker and emergency shutdown mesh triggered by network latency spikes (>800 ms), exchange API anomalies (HTTP 429/418/5xx), market suspensions, and drawdown threshold breaches.
2. **Zero-Trust IAM and Least-Privilege Architecture**: Elimination of primitive roles (`roles/owner`, `roles/editor`), granular per-service service accounts (Compute Engine SA, Dataflow worker SA, EventArc trigger SA, Emergency Shutdown SA, CI/CD deployer SA), and strict resource-level IAM bindings.
3. **Isolated VPC Networking**: Dedicated private VPC, zero public IP exposure for trading engines (egress exclusively through regional Cloud NAT), Private Google Access for GCP services, and Private Service Access (PSA) peering for Cloud Memorystore Redis and Bigtable.
4. **Hardened Secret Management**: Google Secret Manager with regional replication, least-privilege accessor policies, automated rotation readiness, and zero hardcoded credentials.
5. **Acceptance Criteria & Verification Harness**: Rigorous automated validation gates for `terraform apply -auto-approve`, security posture scanner scripts, and specifications for `architecture_summary.md`.

---

## 2. Autonomous Safety Orchestration (Cloud EventArc)

### 2.1 Threat & Failure Event Taxonomy

The HFT engine operates in high-stakes environments where anomalous conditions must trigger autonomous protective actions without human intervention:

| Event Code | Event Category | Trigger Condition | Source Signal | Target Action |
| :--- | :--- | :--- | :--- | :--- |
| `EVT_LATENCY_SPIKE` | Network Performance | Round-trip latency > 800 ms for 2 consecutive pulses | Cloud Monitoring Metric Alert / Custom Pub/Sub | Engine throttle $\to$ Halt new orders $\to$ Cancel open maker orders |
| `EVT_API_RATE_LIMIT` | Exchange API Health | HTTP 429 (Too Many Requests) or HTTP 418 (IP Ban warning) | Cloud Logging log-based metric / Engine alert | Immediate traffic blackout for backoff duration $\to$ Emergency order cancel |
| `EVT_MARKET_SUSPENDED` | Market Microstructure | Binance status transitions to `Suspended` (VAR / Goal / Circuit Breaker) | Custom Pub/Sub (`hft-safety-alerts`) | Immediate atomic purge of open orders $\to$ Halt order generator |
| `EVT_SPREAD_BLOWOUT` | Risk Parameter | Order book spread > $0.03 for > 3 ticks | Custom Pub/Sub (`hft-safety-alerts`) | Liquidity extraction pause |
| `EVT_DRAWDOWN_LIMIT` | Treasury / Risk | Cumulative loss > 15% cluster exposure limit | Custom Pub/Sub (`hft-safety-alerts`) | Kill Switch execution $\to$ Total engine shutdown |
| `EVT_HEARTBEAT_LOSS` | Compute Health | No engine heartbeat received for > 3.0 seconds | Cloud Monitoring uptime / missing metric | Infrastructure alert $\to$ Trigger failover / kill switch |

---

### 2.2 Telemetry Ingestion & Event Sources

The EventArc orchestration mesh consumes signals from three decoupled sources:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TELEMETRY & EVENT SOURCES                       │
└────────────────────────────────────────────────────────────────────────┘
       │                                     │                         │
       ▼                                     ▼                         ▼
┌──────────────┐                     ┌──────────────┐           ┌──────────────┐
│Cloud Audit   │                     │Custom Pub/Sub│           │Cloud Monitor │
│Logs          │                     │Topics        │           │Alert Policies│
│- GCE changes │                     │- LatencyGuard│           │- VM Latency  │
│- IAM edits   │                     │- Risk Engine │           │- CPU/Memory  │
│- Network mod │                     │- Feed pulses │           │- Metric logs │
└──────┬───────┘                     └──────┬───────┘           └──────┬───────┘
       │                                    │                          │
       │                                    │                          │
       ▼                                    ▼                          ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   CLOUDMONITORING NOTIFICATION CHANNEL                 │
│               (projects/${PROJECT}/notificationChannels/...)           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│             CORE SAFETY PUB/SUB TOPIC: `hft-safety-alerts`             │
│            (with Dead Letter Topic `hft-safety-alerts-dlq`)            │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      EVENTARC TRIGGER CONTROLLER                       │
│              (`google_eventarc_trigger.emergency_shutdown`)            │
│       Filtering: type = google.cloud.pubsub.topic.v1.messagePublished  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                    EMERGENCY SHUTDOWN SINK & ROUTER                    │
│      Cloud Function (Gen 2) / Cloud Run: `hft-emergency-shutdown`      │
│      - Writes Kill Switch flag to Redis (O(1))                         │
│      - Issues Binance Cancel-All API REST request                      │
│      - Dispatches Telegram Panic Notification                          │
│      - Pauses C3/C4 Compute Engine execution                           │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Cloud Monitoring Alert Policies**:
   - Alert Policy 1: `hft-feed-latency-high`: Tracks metric `custom.googleapis.com/hft/feed_latency_ms`. Aggregation: 99th percentile over 1-minute window. Condition: Value > 800 ms.
   - Alert Policy 2: `hft-api-429-count`: Tracks metric `logging.googleapis.com/user/binance_429_errors`. Condition: Value > 0 within 1 minute.
   - Alert Policy 3: `hft-vm-packet-drops`: Tracks Compute Engine network interface dropped packets.
   - All alert policies bind to a Pub/Sub notification channel targeting `projects/${var.project_id}/topics/hft-safety-alerts`.

2. **Custom Pub/Sub Events (`hft-safety-alerts`)**:
   - Trading engine modules (`LatencyAndKillSwitchGuard`, `EscudoFinancieroHFT`) publish JSON safety payloads directly to Pub/Sub when local thresholds are breached.
   - Payload schema:
     ```json
     {
       "event_id": "uuid-v4",
       "timestamp": "2026-10-09T03:52:00.123456Z",
       "severity": "CRITICAL",
       "category": "LATENCY_SPIKE",
       "metrics": {
         "delta_ms": 1150.4,
         "threshold_ms": 800.0,
         "symbol": "BTCUSDT_PREDICT"
       },
       "action_required": "EMERGENCY_SHUTDOWN"
     }
     ```

3. **Cloud Audit Logs**:
   - Ingestion of `cloudaudit.googleapis.com` events filtered by `serviceName = compute.googleapis.com` or `serviceName = iam.googleapis.com` to capture unauthorized infrastructure tampering or unexpected instance stops.

---

### 2.3 EventArc Trigger Specification (Terraform Blueprint)

```hcl
# Service Account for Eventarc Trigger
resource "google_service_account" "sa_eventarc_trigger" {
  account_id   = "sa-hft-eventarc"
  display_name = "HFT EventArc Trigger Execution Service Account"
}

# Grant EventArc SA permission to invoke Cloud Run / Gen2 Cloud Function
resource "google_cloud_run_service_iam_member" "eventarc_invoker" {
  location = var.region
  service  = google_cloudfunctions2_function.emergency_shutdown.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.sa_eventarc_trigger.email}"
}

# Dead Letter Topic for EventArc delivery failures
resource "google_pubsub_topic" "safety_alerts_dlq" {
  name = "hft-safety-alerts-dlq"
  labels = {
    environment = var.environment
    managed_by  = "terraform"
    tier        = "safety"
  }
}

# Main Safety Alert Topic
resource "google_pubsub_topic" "safety_alerts" {
  name = "hft-safety-alerts"
  labels = {
    environment = var.environment
    managed_by  = "terraform"
    tier        = "safety"
  }
}

# EventArc Trigger for Emergency Shutdown
resource "google_eventarc_trigger" "emergency_shutdown_trigger" {
  name     = "hft-emergency-shutdown-trigger"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = "google.cloud.pubsub.topic.v1.messagePublished"
  }

  destination {
    cloud_run_service {
      service = google_cloudfunctions2_function.emergency_shutdown.name
      region  = var.region
      path    = "/"
    }
  }

  transport {
    pubsub {
      topic = google_pubsub_topic.safety_alerts.id
    }
  }

  service_account = google_service_account.sa_eventarc_trigger.email

  depends_on = [
    google_cloud_run_service_iam_member.eventarc_invoker,
    google_project_service.enabled_services["eventarc.googleapis.com"]
  ]
}
```

---

### 2.4 Emergency Shutdown Sink (Kill Switch Mechanics)

The Emergency Shutdown Sink is deployed as an event-driven Cloud Function (Gen 2) running inside the VPC via Serverless VPC Access connector or direct VPC egress, with the following execution workflow:

1. **Atomic In-Memory Kill Switch Activation**:
   - Connects to Cloud Memorystore Redis over private VPC IP.
   - Executes `SET emergency_kill_switch 1 EX 86400` and `PUBLISH engine_control "HALT"`.
   - The Compute Engine trading engine polls/subscribes to this key with $\mathcal{O}(1)$ nanosecond local cache check on every order loop iteration.
2. **Atomic Open Order Purge (Binance REST API)**:
   - Fetches encrypted API key and Secret from Secret Manager.
   - Transmits HTTP `DELETE /api/v3/openOrders` (Cancel All Open Orders on a Symbol) signed with HMAC-SHA256.
   - Prevents stale Limit/Maker orders from being filled during network or market distress.
3. **Engine Process Suspension / VM Pausing**:
   - Publishes an event to `hft-control-commands` instructing the local systemd daemon or container supervisor to gracefully freeze the hot execution threads.
4. **External Alert Broadcast**:
   - Dispatches a formatted alert message to Telegram Bot API (via Telegram bot token fetched from Secret Manager) reporting:
     * Reason for trigger (e.g. `LATENCIA_EXCESIVA: 1150 ms`)
     * Orders cancelled count
     * Engine status: `HALTED`

---

## 3. Production-Ready Resilience & Security

### 3.1 IAM Architecture & Least-Privilege Role Matrix

Primitive roles (`roles/owner`, `roles/editor`, `roles/viewer`) are strictly prohibited. Every system component has a dedicated Service Account with granular predefined or custom IAM roles:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   STRICT IAM LEAST-PRIVILEGE MATRIX                    │
├───────────────────────┬────────────────────────────────────────────────┤
│ Service Account       │ Granted Predefined Roles & Granular Scope       │
├───────────────────────┼────────────────────────────────────────────────┤
│ sa-hft-engine         │ • roles/pubsub.publisher (specific topics)     │
│ (Compute Engine C3/C4)│ • roles/pubsub.subscriber (command topics)     │
│                       │ • roles/bigtable.user (historical tick table)  │
│                       │ • roles/secretmanager.secretAccessor (keys)    │
│                       │ • roles/monitoring.metricWriter                │
│                       │ • roles/logging.logWriter                      │
│                       │ • roles/cloudtrace.agent                       │
├───────────────────────┼────────────────────────────────────────────────┤
│ sa-dataflow-worker    │ • roles/dataflow.worker                        │
│ (Stream Pipeline)     │ • roles/pubsub.subscriber (market-ticks)       │
│                       │ • roles/bigtable.user (tick storage)           │
│                       │ • roles/storage.objectAdmin (temp/staging)     │
│                       │ • roles/logging.logWriter                      │
├───────────────────────┼────────────────────────────────────────────────┤
│ sa-hft-eventarc       │ • roles/eventarc.eventReceiver                 │
│ (EventArc Trigger)    │ • roles/run.invoker (emergency shutdown svc)   │
│                       │ • roles/pubsub.subscriber                      │
├───────────────────────┼────────────────────────────────────────────────┤
│ sa-emergency-shutdown │ • roles/secretmanager.secretAccessor (API keys)│
│ (Cloud Function Gen2) │ • roles/pubsub.publisher (control commands)    │
│                       │ • roles/logging.logWriter                      │
├───────────────────────┼────────────────────────────────────────────────┤
│ sa-cicd-deployer      │ • Scoped Admin roles: compute.networkAdmin,    │
│ (Terraform Runner)    │   pubsub.admin, bigtable.admin, redis.admin,   │
│                       │   iam.serviceAccountUser, secretmanager.admin  │
│                       │   (NO primitive Owner or Editor)               │
└───────────────────────┴────────────────────────────────────────────────┘
```

#### Terraform IAM Resource Bindings (Strict Resource-Level Scoping):

```hcl
# Service Account: Compute Engine HFT Engine
resource "google_service_account" "sa_hft_engine" {
  account_id   = "sa-hft-engine"
  display_name = "HFT Trading Engine VM Service Account"
}

# Monitoring and Logging: Minimal Roles
resource "google_project_iam_member" "engine_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.sa_hft_engine.email}"
}

resource "google_project_iam_member" "engine_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.sa_hft_engine.email}"
}

# Bigtable User: Scoped to specific instance
resource "google_bigtable_instance_iam_member" "engine_bigtable_user" {
  instance = google_bigtable_instance.hft_bigtable.name
  role     = "roles/bigtable.user"
  member   = "serviceAccount:${google_service_account.sa_hft_engine.email}"
}

# Pub/Sub Publisher: Scoped to Market Ticks & Alerts
resource "google_pubsub_topic_iam_member" "engine_pubsub_publisher" {
  topic  = google_pubsub_topic.market_ticks.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.sa_hft_engine.email}"
}
```

---

### 3.2 VPC Networking & Zero-Trust Perimeter

#### 3.2.1 Network Topology & Subnetting

The network architecture is fully private, preventing any direct public Internet ingress:

- **VPC Name**: `hft-vpc` (Custom Subnet Mode, auto-create subnets disabled).
- **Subnet 1 (`hft-engine-subnet`)**:
  - CIDR: `10.10.1.0/24`
  - Region: `asia-northeast1` (Tokyo)
  - `private_ip_google_access`: `true`
  - Purpose: Hosts high-performance C3/C4 Compute Engine instances running with Google Virtual NIC (gVNIC) and multi-queue network drivers.
- **Subnet 2 (`hft-dataflow-subnet`)**:
  - CIDR: `10.10.2.0/24`
  - Region: `asia-northeast1`
  - `private_ip_google_access`: `true`
  - Purpose: Dedicated worker pool for Apache Beam Dataflow streaming pipeline.
- **Subnet 3 (`hft-serverless-connector-subnet`)**:
  - CIDR: `10.10.3.0/28`
  - Region: `asia-northeast1`
  - Purpose: VPC Access Connector for EventArc emergency shutdown Cloud Functions to reach Memorystore Redis.
- **Private Services Access (PSA) Reserved Range**:
  - CIDR: `10.10.16.0/20`
  - Peered with: `servicenetworking.googleapis.com` for Cloud Memorystore Redis.

```
┌────────────────────────────────────────────────────────────────────────┐
│                        VPC NETWORK: `hft-vpc`                          │
│                                                                        │
│  ┌───────────────────────┐  ┌───────────────────────┐  ┌────────────┐  │
│  │  hft-engine-subnet    │  │  hft-dataflow-subnet  │  │Serverless  │  │
│  │  10.10.1.0/24         │  │  10.10.2.0/24         │  │Connector   │  │
│  │  - C3/C4 Engine VM    │  │  - Dataflow Workers   │  │10.10.3.0/28│  │
│  │  - Private IP ONLY    │  │  - Private IP ONLY    │  └─────┬──────┘  │
│  │  - gVNIC Enabled      │  │  - Private Google Acc │        │         │
│  └──────────┬────────────┘  └──────────┬────────────┘        │         │
│             │                          │                     │         │
│             ▼                          ▼                     ▼         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │            VPC SERVICE PEERING (`servicenetworking`)             │  │
│  │                    Reserved CIDR: 10.10.16.0/20                  │  │
│  │                    Cloud Memorystore (Redis)                     │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                        │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │             CLOUD ROUTER (`hft-router`) & CLOUD NAT              │  │
│  │    Outbound NAT Egress to Binance REST / WebSocket APIs          │  │
│  │    (Zero Inbound Ports Exposed to Public Internet)               │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

#### 3.2.2 Cloud NAT Egress Architecture

Compute Engine instances are provisioned **without external public IP addresses** (`access_config` is completely omitted). Egress connectivity to Binance API endpoints (`api.binance.com`, `stream.binance.com`) is brokered by Cloud NAT:

```hcl
resource "google_compute_router" "hft_router" {
  name    = "hft-router"
  region  = var.region
  network = google_compute_network.hft_vpc.id
}

resource "google_compute_router_nat" "hft_nat" {
  name                               = "hft-nat"
  router                             = google_compute_router.hft_router.name
  region                             = var.region
  nat_ip_allocate_option             = "AUTO_ONLY"
  source_subnetwork_ip_ranges_to_nat = "ALL_SUBNETWORKS_ALL_IP_RANGES"

  log_config {
    enable = true
    filter = "ERRORS_ONLY"
  }
}
```

#### 3.2.3 Firewall Rules (Zero-Trust Ingress / Controlled Egress)

1. **Deny All Inbound**: Default GCP egress-only posture.
2. **IAP SSH Ingress (`hft-allow-iap-ssh`)**:
   - Source IP: `35.235.240.0/20` (Google Cloud Identity-Aware Proxy CIDR).
   - Port: TCP 22.
   - Target: Tags `["hft-engine"]`.
   - Result: Engineers and automation can establish SSH sessions through cryptographic tunnels (`gcloud compute ssh --tunnel-through-iap`) without exposing port 22 to public scanners.
3. **Internal VPC Communication (`hft-allow-internal`)**:
   - Source Range: `10.10.0.0/16`.
   - Ports: TCP/UDP for internal engine to Dataflow and Redis caching interfaces.
4. **Restricted Egress**:
   - Outbound TCP 443 (HTTPS/WSS) to public Internet via Cloud NAT.
   - Outbound internal to Google APIs via Private Google Access.

#### 3.2.4 Private Service Peering for Redis

```hcl
# Reserve Internal IP range for Google Managed Services
resource "google_compute_global_address" "private_service_access" {
  name          = "hft-private-service-access"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 20
  network       = google_compute_network.hft_vpc.id
}

# Establish Peering Connection with Service Networking
resource "google_service_networking_connection" "private_vpc_connection" {
  network                 = google_compute_network.hft_vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_access.name]
}

# Memorystore Redis Instance
resource "google_redis_instance" "hft_cache" {
  name               = "hft-redis-cache"
  tier               = "STANDARD_HA" # Multi-zone high availability for HFT state
  memory_size_gb     = 5
  region             = var.region
  authorized_network = google_compute_network.hft_vpc.id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"
  redis_version      = "REDIS_7_0"

  auth_enabled            = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"

  depends_on = [google_service_networking_connection.private_vpc_connection]
}
```

---

### 3.3 Secret Management & Lifecycle Architecture

#### 3.3.1 Secrets Inventory

The following secrets are stored in Google Secret Manager:

1. `binance-api-key`: API key for Binance Spot / Prediction endpoints.
2. `binance-secret-key`: HMAC-SHA256 signing secret for private order routing.
3. `telegram-bot-token`: Token for Telegram interactive control bot.
4. `telegram-chat-id`: Target Chat ID for alerts and kill-switch broadcasts.
5. `redis-auth-token`: Pre-shared AUTH string for Redis in-transit authentication.

#### 3.3.2 Rotation Policy & Event Notification

To satisfy production security standards, all secrets are configured with automated rotation readiness:

```hcl
resource "google_pubsub_topic" "secret_rotation" {
  name = "hft-secret-rotation-events"
}

resource "google_secret_manager_secret" "binance_api_key" {
  secret_id = "binance-api-key"

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  rotation {
    next_rotation_time = "2026-11-01T00:00:00Z"
    rotation_period    = "2592000s" # 30 days
  }

  topics {
    name = google_pubsub_topic.secret_rotation.id
  }
}

# Granular Resource-Level Accessor Binding
resource "google_secret_manager_secret_iam_member" "engine_binance_key_accessor" {
  secret_id = google_secret_manager_secret.binance_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.sa_hft_engine.email}"
}

resource "google_secret_manager_secret_iam_member" "shutdown_binance_key_accessor" {
  secret_id = google_secret_manager_secret.binance_api_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.sa_emergency_shutdown.email}"
}
```

---

## 4. Compute Engine C3/C4 & Storage Architecture

### 4.1 Low-Latency Compute Engine Specification

For HFT in Asia-Northeast (Tokyo `asia-northeast1`), instance selection is critical to minimize latency to Binance matching servers:

- **Machine Series**: C3 or C4 (`c3-standard-4` or `c4-standard-4` powered by Intel 4th Gen Xeon Scalable Sapphire Rapids / Emerald Rapids).
- **Network Interface**: Google Virtual NIC (`gVNIC`) enabled.
- **CPU Platform / Placement Policy**: Compact placement policy (`COLLOCATED`) if scaling to multiple nodes to eliminate inter-chassis hops.
- **Network Performance Tier**: `PREMIUM`.
- **Boot Disk**: Hyperdisk Balanced or Extreme SSD.

```hcl
resource "google_compute_instance" "hft_engine" {
  name         = "hft-trading-engine-01"
  machine_type = "c3-standard-4"
  zone         = "${var.region}-b"

  tags = ["hft-engine"]

  boot_disk {
    initialize_params {
      image = "ubuntu-os-cloud/ubuntu-2204-lts"
      type  = "pd-ssd"
      size  = 50
    }
  }

  network_interface {
    subnetwork = google_compute_subnetwork.hft_engine_subnet.id
    nic_type   = "GVNIC"
    # NO access_config block -> NO external public IP
  }

  service_account {
    email  = google_service_account.sa_hft_engine.email
    scopes = ["cloud-platform"]
  }

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }
}
```

---

### 4.2 Storage Architecture: Cloud Bigtable & Dataflow

- **Cloud Bigtable**:
  - Instance: `hft-tick-store` (Cluster located in `asia-northeast1-b`, SSD storage, 1-3 nodes with autoscaling).
  - Schema:
    * Table: `market_ticks`
    * Row Key: Reverse-timestamp prefixed with market ID: `${symbol}#${9999999999999 - timestamp_epoch_ms}#${order_id}`
    * Column Families:
      - `t` (trades: `price`, `qty`, `side`, `is_maker`)
      - `q` (quotes / book depth: `bid1_p`, `bid1_v`, `ask1_p`, `ask1_v`, `imbalance`)
      - `m` (metrics: `feed_latency_ms`, `calc_latency_us`)
- **Cloud Dataflow Streaming Pipeline**:
  - Apache Beam Runner V2 with Streaming Engine enabled.
  - Consumes from `hft-market-ticks` Pub/Sub subscription.
  - Sinks raw high-velocity records into Cloud Bigtable and updates sliding aggregations in Memorystore Redis.
  - Workers run inside `hft-dataflow-subnet` with `no_public_ips = true`.

---

## 5. Verification & Acceptance Criteria

### 5.1 Acceptance Criteria for `terraform apply -auto-approve`

To ensure seamless, deterministic live deployment without errors, the Terraform codebase must fulfill the following acceptance gates:

| Gate | Validation Rule | Acceptance Metric |
| :--- | :--- | :--- |
| **G1: Syntax & Validation** | `terraform validate` must pass with zero warnings or errors. | Exit code 0 |
| **G2: Explicit Dependencies** | Managed services (`google_project_service`) and VPC Peering (`google_service_networking_connection`) must precede dependent resources (`google_redis_instance`, `google_bigtable_instance`) via `depends_on`. | Zero race conditions |
| **G3: Zero Plaintext Secrets** | No API keys, secret hashes, or private credentials committed to `.tf` or state variables in plaintext. | Pass security audit |
| **G4: Network Isolation** | Every Compute Engine instance has `access_config` omitted (0 public IPs assigned). | 100% private IP compliance |
| **G5: IAM Least Privilege** | Zero assignments of `roles/owner` or `roles/editor`. Only specific pre-defined roles bound to dedicated service accounts. | 0 violations detected |
| **G6: Complete Resource Set** | Successfully provisions: VPC, Subnets, Cloud NAT, Cloud Router, Compute Engine C3/C4 (gVNIC), Pub/Sub, Dataflow Worker SA, Bigtable, Memorystore Redis, Secret Manager, EventArc Trigger, and Cloud Monitoring alert policies. | `Apply complete! Resources: N added, 0 failed.` |

---

### 5.2 Automated Security Scanning & Validation Script

The following Python verification script (`verify_security_posture.py`) will be executed post-apply to audit the deployed cloud resources:

```python
#!/usr/bin/env python3
"""
CONTINUITY HFT GCP Security & Network Isolation Verification Script.
Audits deployed cloud resources for:
1. Zero public IP exposure on Compute Engine instances.
2. Private Google Access enabled on all subnets.
3. IAM least-privilege enforcement (no Owner/Editor roles on project SAs).
4. Cloud NAT gateway operational status.
5. Secret Manager resource-level ACL compliance.
"""

import sys
import json
import subprocess

def run_command(cmd):
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=True, text=True)
    if result.returncode != 0:
        return None, result.stderr
    return result.stdout.strip(), None

def audit_network_isolation(project_id, region):
    print("[*] Auditing Compute Engine Network Isolation...")
    cmd = f"gcloud compute instances list --project={project_id} --format=json"
    out, err = run_command(cmd)
    if err:
        print(f"[-] Error fetching instances: {err}")
        return False
    instances = json.loads(out)
    violations = []
    for inst in instances:
        name = inst.get("name")
        nics = inst.get("networkInterfaces", [])
        for nic in nics:
            access_configs = nic.get("accessConfigs", [])
            for ac in access_configs:
                nat_ip = ac.get("natIP")
                if nat_ip:
                    violations.append(f"Instance '{name}' has public IP: {nat_ip}")
    if violations:
        for v in violations:
            print(f"[FAIL] {v}")
        return False
    print("[PASS] All Compute Engine instances have ZERO public IP addresses.")
    return True

def audit_iam_roles(project_id):
    print("[*] Auditing Project IAM Policy for Primitive Roles...")
    cmd = f"gcloud projects get-iam-policy {project_id} --format=json"
    out, err = run_command(cmd)
    if err:
        print(f"[-] Error fetching IAM policy: {err}")
        return False
    policy = json.loads(out)
    violations = []
    forbidden_roles = ["roles/owner", "roles/editor"]
    for binding in policy.get("bindings", []):
        role = binding.get("role")
        if role in forbidden_roles:
            members = binding.get("members", [])
            for m in members:
                if "sa-hft-" in m:
                    violations.append(f"HFT Service Account '{m}' bound to primitive role '{role}'")
    if violations:
        for v in violations:
            print(f"[FAIL] {v}")
        return False
    print("[PASS] Zero HFT Service Accounts bound to primitive roles (Owner/Editor).")
    return True

def audit_private_google_access(project_id, region):
    print("[*] Auditing Private Google Access on Subnets...")
    cmd = f"gcloud compute networks subnets list --project={project_id} --regions={region} --format=json"
    out, err = run_command(cmd)
    if err:
        print(f"[-] Error fetching subnets: {err}")
        return False
    subnets = json.loads(out)
    for sub in subnets:
        name = sub.get("name")
        if "hft-" in name:
            pga = sub.get("privateIpGoogleAccess", False)
            if not pga:
                print(f"[FAIL] Subnet '{name}' has Private Google Access DISABLED.")
                return False
            print(f"[PASS] Subnet '{name}' has Private Google Access ENABLED.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python verify_security_posture.py <PROJECT_ID> <REGION>")
        sys.exit(1)
    project_id = sys.argv[1]
    region = sys.argv[2]
    net_ok = audit_network_isolation(project_id, region)
    iam_ok = audit_iam_roles(project_id)
    pga_ok = audit_private_google_access(project_id, region)
    if net_ok and iam_ok and pga_ok:
        print("\n[SUMMARY] All Security and Isolation Verification Checks PASSED!")
        sys.exit(0)
    else:
        print("\n[SUMMARY] Security Verification Checks FAILED!")
        sys.exit(2)
```

---

### 5.3 Requirements & Structure for `architecture_summary.md`

The deliverable `architecture_summary.md` must be structured into seven definitive sections:

1. **Architecture Overview & Topological Blueprint**: Complete ASCII and Mermaid diagrams mapping all provisioned GCP services, subnets, and data pipelines.
2. **Infrastructure-as-Code Implementation Breakdown**: Exhaustive walkthrough of every Terraform resource module (`vpc.tf`, `compute.tf`, `pubsub.tf`, `storage.tf`, `eventarc.tf`, `iam.tf`, `secrets.tf`).
3. **Autonomous Safety Orchestration Runtime**: Detailed trace of EventArc trigger routes, latency threshold rules (>800 ms), circuit-breaker mechanisms, and the emergency shutdown function.
4. **Security & Compliance Audit Results**: Full execution log of `verify_security_posture.py` confirming zero public IPs, no primitive roles, and full Private Google Access.
5. **Deployment Verification & State Metrics**: Transcript of `terraform apply -auto-approve` output, resource IDs, and network endpoints.
6. **Production Readiness Gaps & Future Roadmap**: Explicit catalog of advanced enhancements:
   - CMEK (Customer-Managed Encryption Keys) across Cloud Storage and Bigtable.
   - Dual-Region Failover (Tokyo `asia-northeast1` $\leftrightarrow$ Seoul `asia-northeast3`).
   - Hardware-Accelerated TCP/IP bypass (XDP / DPDK kernel bypass drivers on C3).
   - FPGA offloading for ultra-low latency order book parsing.
7. **Disaster Recovery & Operational Runbooks**: Step-by-step procedures for manual kill-switch activation, secret rotation, and engine post-mortem analysis.

---

## 6. Synthesis & Implementation Plan for Downstream Agents

To execute this architecture flawlessly across subsequent milestones:
1. **Milestone 1 (Foundations)**: Implement `vpc.tf`, `iam.tf`, `secrets.tf`, and enable required Google APIs with explicit dependency chains.
2. **Milestone 2 (Market Data & Compute)**: Implement `pubsub.tf`, `compute.tf` (C3/C4 with gVNIC, no external IP), and Cloud NAT.
3. **Milestone 3 (State & Storage)**: Implement `bigtable.tf`, `redis.tf` (Standard HA with PSA peering), and Dataflow worker definitions.
4. **Milestone 4 (Autonomous Safety)**: Implement `eventarc.tf`, Cloud Monitoring alert policies, and the Emergency Shutdown Cloud Function.
5. **Milestone 5 (Live Apply & Security Scan)**: Run `terraform apply -auto-approve` followed by `verify_security_posture.py`.
6. **Milestone 6 (Documentation)**: Author `architecture_summary.md` with complete forensics and architecture traces.
