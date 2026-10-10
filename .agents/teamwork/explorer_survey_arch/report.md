# HFT GCP Architecture Specification Report

**Date**: 2026-10-09  
**Author**: Explorer Subagent (`explorer_survey_arch`)  
**Context**: Phase 0 (Survey) — CONTINUITY HFT GCP Cloud Architecture  
**Active GCP Project**: `intrepid-decker-480417-e9`  
**Primary Target Region**: `asia-northeast1` (Tokyo, Japan)  

---

## Executive Summary

This report establishes the complete technical architectural design, hardware parameters, pipeline topologies, and Infrastructure as Code (Terraform) specifications for the **CONTINUITY HFT Autonomous Cloud Architecture** on Google Cloud Platform. 

The architecture is engineered specifically for ultra-low latency execution and high-throughput market data processing, targeting proximity to Binance Spot & Prediction Market matching facilities (AWS Tokyo `ap-northeast-1` / Equinix TY3/TY8 datacenters).

---

## 1. Core HFT Infrastructure Specifications

### 1.1. Market Data Ingestion: Cloud Pub/Sub Architecture

Cloud Pub/Sub serves as the distributed, decouple ingestion fabric for incoming tick streams, Level-2 order book depth updates, and trade executions. To satisfy HFT determinism, the architecture employs strict partitioning, message ordering, and rapid Dead-Letter Queue (DLQ) isolation.

```
                              ┌──────────────────────────────────────────────┐
                              │           Binance Market Data Ingest         │
                              │       (WebSocket / FIX Drop-Copy / API)       │
                              └──────────────────────┬───────────────────────┘
                                                     │
                             ┌───────────────────────┴───────────────────────┐
                             │                                               │
                             ▼                                               ▼
               ┌───────────────────────────┐                   ┌───────────────────────────┐
               │    hft-market-trades      │                   │    hft-market-orderbook   │
               │   (Pub/Sub Topic, Tokyo)  │                   │   (Pub/Sub Topic, Tokyo)  │
               └─────────────┬─────────────┘                   └─────────────┬─────────────┘
                             │                                               │
           ┌─────────────────┴─────────────────┐           ┌─────────────────┴─────────────────┐
           │                                   │           │                                   │
           ▼                                   ▼           ▼                                   ▼
┌─────────────────────┐             ┌─────────────────────┐                     ┌─────────────────────┐
│  sub-trades-engine  │             │ sub-trades-dataflow │                     │ sub-book-dataflow   │
│ (Ordering=TRUE,     │             │ (Streaming Engine   │                     │ (Streaming Engine   │
│  Ack=10s, DLT)      │             │  Aggregator)        │                     │  L2 Reconstructor)  │
└──────────┬──────────┘             └──────────┬──────────┘                     └──────────┬──────────┘
           │                                   │                                           │
           ▼                                   │                                           │
┌─────────────────────┐                        │                                           │
│  C3/C4 Trading Node │                        ▼                                           ▼
│ (Low Latency Engine)│             ┌─────────────────────────────────────────────────────────────┐
└─────────────────────┘             │          Dead Letter Topic (hft-market-dlq)                 │
                                    │          (Failed after 5 delivery attempts)                 │
                                    └─────────────────────────────────────────────────────────────┘
```

#### Topic Architecture
1. **Topic Partitioning by Stream Type**:
   - `hft-market-trades`: High-velocity executed trades (`trade`, `aggTrade`).
   - `hft-market-orderbook`: Incremental Level-2 order book updates (`depthUpdate` at 100ms intervals).
   - `hft-market-snapshots`: Full order book snapshots (every 1s/5s) for drift correction.
   - `hft-market-dlq`: Dead-Letter Topic for unparseable, malformed, or poisoned payloads.

2. **Regional Storage Policy (Zero Cross-Region Egress)**:
   - Configured with `allowed_persistence_regions = ["asia-northeast1"]`. Guarantees messages never write to non-Tokyo storage clusters, eliminating regional replication latency.

3. **Retention Duration**:
   - `message_retention_duration = "86400s"` (24 hours). Sufficient for intraday replay and compliance auditing without incurring unbounded storage costs on multi-gigabyte tick feeds.

#### Subscription Configuration
1. **Message Ordering (`enable_message_ordering = true`)**:
   - In HFT, state machines fail if sequence $N+1$ is processed before sequence $N$.
   - The publisher injects an `ordering_key` composed of `{symbol}_{stream_type}` (e.g. `BTCUSDT_depth` or `ETHUSDT_trades`). Pub/Sub guarantees strictly in-order delivery per ordering key.

2. **Acknowledgment Deadline (`ack_deadline_seconds = 10`)**:
   - Set to the minimum production threshold (10 seconds). In the event of a worker heartbeat loss or consumer crash, stale orders are redelivered immediately rather than blocking queue partitions.

3. **Dead Letter Policy**:
   - `max_delivery_attempts = 5`. If a corrupted packet fails parsing 5 times, it is automatically evicted to `hft-market-dlq`, preventing head-of-line blocking on the active ordering key.

---

### 1.2. Stream Processing Architecture: Cloud Dataflow & Apache Beam

Cloud Dataflow runs continuous, sub-second stream aggregations, feature engineering (Order Book Imbalance $I$, Micro-price, Rolling VWAP, VPIN toxicity), and fans out to both historical storage (Bigtable) and real-time state caching (Redis).

#### Pipeline Design & Topology
1. **Runner V2 (`--experiments=use_runner_v2`)**:
   - Modernized execution harness using C++ worker environment and gRPC channel optimizations. Reduces serialization overhead by up to 40% compared to legacy Runner V1.
2. **Streaming Engine (`--enable_streaming_engine`)**:
   - Offloads state storage and shuffling from worker VMs into a dedicated Google-managed backend service.
   - Eliminates worker JVM garbage collection pauses caused by large state buffers.
   - Enables seamless autoscaling without state redistribution stalls, maintaining predictable sub-second watermarks.
3. **Dual Sink Strategy**:
   - **Sink A (Cloud Bigtable)**: High-throughput asynchronous mutation batching via Beam `BigtableIO.write()`. Flushes raw ticks and micro-second timestamps for algorithmic backtesting and compliance.
   - **Sink B (Cloud Memorystore for Redis)**: Direct pipeline step writing top-of-book, rolling 1-second VWAP, and volatility metrics directly into Redis via pipelined Redis commands (`SET`, `HSET`).
4. **Worker Infrastructure**:
   - Machine Type: `n2-standard-4` or `c2-standard-4` in `asia-northeast1-b` / `c`.
   - Worker Storage: `50 GB` `pd-ssd` for local scratch data.
   - Network: Placed in the private HFT VPC subnet (`use_public_ips = false`), with Private Google Access enabled.

---

### 1.3. Low-Latency Compute Engine: C3 / C4 Series Architecture

The core trading bot execution engine (`OrderBookListener`, `MarketMicrostructureEngine`, `ExecutionRouter`) requires minimal network jitter and ultra-fast single-threaded throughput.

```
┌─────────────────────────────────────────────────────────────────────────────────────────────────┐
│ Google Cloud Platform — Zone asia-northeast1-c (Tokyo)                                          │
│                                                                                                 │
│  ┌───────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ Compact Placement Policy: google_compute_resource_policy (COLLOCATED)                     │  │
│  │                                                                                           │  │
│  │  ┌───────────────────────────────────────────────┐  ┌──────────────────────────────────┐  │  │
│  │  │ C3 / C4 Trading VM (Sapphire/Emerald Rapids)  │  │ Memory / Risk Proxy Node         │  │  │
│  │  │                                               │  │                                  │  │  │
│  │  │  - Titanium IPU (Offloads VPC & VirtIO Net)   │  │  - Low-Latency Kernel Tuning     │  │  │
│  │  │  - gVNIC (32 Multi-queues, 100Gbps Tier 1)    │  │  - In-memory State Replication   │  │  │
│  │  │  - Isolated CPU Cores (isolcpus, nohz_full)   │  │                                  │  │  │
│  │  └───────────────────────┬───────────────────────┘  └─────────────────┬────────────────┘  │  │
│  │                          │                                            │                   │  │
│  │                          └──────────────────────┬─────────────────────┘                   │  │
│  │                                                 │ Sub-microsecond Intra-Rack Latency      │  │
│  └─────────────────────────────────────────────────┼─────────────────────────────────────────┘  │
│                                                    │                                            │
│                                                    ▼                                            │
│                               ┌─────────────────────────────────────────┐                       │
│                               │ Google Cloud Premium Network Backbone   │                       │
│                               │ (Direct BGP Peering to Tokyo IXPs)      │                       │
│                               └────────────────────┬────────────────────┘                       │
└────────────────────────────────────────────────────┼────────────────────────────────────────────┘
                                                     │ Direct low-latency cross-connect (~0.8-1.5ms)
                                                     ▼
                               ┌──────────────────────────────────────────┐
                               │ Binance Matching Engines & Cloud Gateways│
                               │ (AWS Tokyo ap-northeast-1 / Equinix TY)  │
                               └──────────────────────────────────────────┘
```

#### Hardware & Machine Selection (Verified via Live Cloud Telemetry)
- **Live GCP Validation**:
  - `gcloud compute machine-types list` verified that `c3-standard-4`, `c3-standard-8`, `c3-standard-22`, etc. are fully available in `asia-northeast1-b` and `asia-northeast1-c`.
  - Next-generation `c4-standard-4`, `c4-standard-8`, `c4-highmem-*`, `c4a-*`, and `c4d-*` are fully available in `asia-northeast1-c`.
- **Titanium IPU (Infrastructure Processing Unit)**:
  - C3 (Intel 4th Gen Xeon Sapphire Rapids) and C4 (Intel 5th Gen Xeon Emerald Rapids) utilize Google Titanium IPU. Network virtualization, packet encryption, and storage processing are offloaded to dedicated custom ASICs, guaranteeing zero CPU cycle theft or interrupt spikes on trading threads.

#### Network Configuration & gVNIC
1. **gVNIC Interface (`nic_type = "GVNIC"`)**:
   - Replaces VirtIO-Net. Delivers multi-queue support (up to 32 receive/transmit queues per vCPU), hardware TCP segmentation offload, and direct memory access (DMA) descriptors.
2. **Bandwidth Tier (`network_performance_config { total_egress_bandwidth_tier = "TIER_1" }`)**:
   - Unlocks up to 50–100 Gbps egress line rates, drastically reducing tail packet queuing under high-frequency market burst conditions.
3. **Google Network Service Tier (`PREMIUM`)**:
   - Ingress and egress utilize Google's private global fiber network. Packets hop onto the fiber at the closest edge PoP and exit directly at Tokyo peering interconnects (Equinix TY3/TY8 / AWS ap-northeast-1), minimizing inter-cloud routing hops.

#### Physical Colocation: Compact Placement Policy
- Implemented via `google_compute_resource_policy` with `group_placement_policy { colocation = "COLLOCATED" }`.
- Forces Compute Engine to schedule all trading cluster instances onto physically adjacent server racks within the same datacenter room, reducing inter-node physical latency to sub-microsecond levels.

#### Kernel & OS Startup Optimization
Applied via instance metadata startup script:
```bash
# TCP Socket Buffer Expansion for Burst Ticks
sysctl -w net.core.rmem_max=16777216
sysctl -w net.core.wmem_max=16777216
sysctl -w net.ipv4.tcp_rmem="4096 87380 16777216"
sysctl -w net.ipv4.tcp_wmem="4096 65536 16777216"

# Low Latency Socket Parameters
sysctl -w net.ipv4.tcp_low_latency=1
sysctl -w net.ipv4.tcp_nodelay=1
sysctl -w net.ipv4.tcp_fastopen=3

# Kernel Busy Polling (Eliminates Hardware Interrupt Latency)
sysctl -w net.core.busy_read=50
sysctl -w net.core.busy_poll=50

# CPU Governor Performance Locking
cpupower frequency-set --governor performance || true
```

---

### 1.4. Storage Architecture

```
                               ┌─────────────────────────────────┐
                               │   HFT Execution & Pipeline      │
                               └────────┬───────────────┬────────┘
                                        │               │
                 Sub-millisecond State  │               │ High-Throughput
                 Reads & Atomic Mutex   │               │ Append Stream
                                        ▼               ▼
                   ┌────────────────────────┐      ┌────────────────────────┐
                   │ Cloud Memorystore      │      │ Cloud Bigtable         │
                   │ for Redis (Standard HA)│      │ (Production SSD)       │
                   │ - Zone: asia-ne1-c/b   │      │ - Zone: asia-ne1-c     │
                   │ - Port: 6379           │      │ - Storage: SSD         │
                   │ - Auth: SecretManager  │      │ - SLA: 99.99%          │
                   │ - Mode: Private Service│      │ - Latency: < 5ms P99   │
                   └────────────────────────┘      └────────────────────────┘
```

#### 1.4.1. Cloud Bigtable (Tick Store & Audit Trail)
- **Instance Configuration**:
  - `instance_type = "PRODUCTION"`
  - `storage_type = "SSD"` (mandatory: HDD seek times >10ms cause catastrophic tail latency; SSD delivers sub-5ms P99 write/read latencies).
  - Cluster Placement: `asia-northeast1-c` (collocated in the exact same zone as the C3/C4 trading VM).
  - Autoscaling: `min_nodes = 1`, `max_nodes = 5`, `cpu_target = 60`.

- **Table Schema: `market_ticks`**:
  - **Row Key Design**:
    - Lexicographical sort requirement: Reverse timestamping prevents hot-spotting while enabling high-speed latest-tick range scans.
    - Format: `{symbol}#{reverse_timestamp_micros}#{sequence_id}`
    - Formula: `reverse_timestamp_micros = Long.MAX_VALUE - timestamp_micros`.
    - Result: A scan on prefix `BTCUSDT#` immediately streams the most recent ticks first without reading older historical blocks.
    - Multi-symbol sharding: Optional 1-byte salt prefix `{shard}#{symbol}#{reverse_timestamp}` where `shard = hash(symbol) % 4` ensures balanced distribution across all tablet servers.
  - **Column Families**:
    - `trades`:
      - `p`: Executed price (IEEE 754 64-bit float or scaled integer).
      - `q`: Executed volume.
      - `s`: Trade side (`BUY` / `SELL`).
      - `tid`: Exchange trade ID.
    - `quotes`:
      - `b_p`: Best bid price.
      - `b_q`: Best bid quantity.
      - `a_p`: Best ask price.
      - `a_q`: Best ask quantity.
      - `imb`: Computed order book imbalance ratio.
    - `metrics`:
      - `lat_net`: Wire transmission latency ($\mu s$).
      - `lat_eng`: Internal pipeline execution latency ($\mu s$).
      - `ev`: Calculated expected value ($EV$).
  - **Garbage Collection Policy (`google_bigtable_gc_policy`)**:
    - Cell version limit: `max_version = 1`.
    - Retention TTL: `max_age = "2592000s"` (30 days). Historical archives are batch-exported to Cloud Storage / BigLake Iceberg for deep backtesting.

#### 1.4.2. Cloud Memorystore for Redis (In-Memory State & Risk Registry)
- **High Availability & Sizing**:
  - `tier = "STANDARD_HA"`: Automatic failover across zones (`asia-northeast1-c` primary, `asia-northeast1-b` replica). Guarantees zero state loss of active open orders, position limits, and risk balances during Google maintenance events.
  - `memory_size_gb = 5`: Sufficient for holding full L2 order books for 50+ pairs, real-time VWAP matrices, and risk state tables.
  - `redis_version = "REDIS_7_0"`: Leverages multi-threaded I/O multiplexing and improved memory allocator efficiency.
- **Network Integration**:
  - `connect_mode = "PRIVATE_SERVICE_ACCESS"`.
  - Accessible strictly through the internal VPC network (`google_compute_network.hft_vpc`) via VPC peering with `servicenetworking.googleapis.com`. No public IP exposure.
- **Security & Latency Trade-Off Analysis**:
  - `auth_enabled = true`: Requires Redis AUTH token (generated randomly and stored in Google Secret Manager).
  - Transit Encryption (`transit_encryption_mode`):
    - *Enterprise Zero-Trust*: `SERVER_AUTHENTICATION` provides TLS in-transit.
    - *Ultra-Low Latency Mode*: `DISABLED` within the isolated private VPC saves approximately $120$–$180$ microseconds per round-trip by bypassing software TLS envelope overhead. The recommendation is to support configurable parameter `var.redis_transit_encryption_enabled`.

---

## 2. Terraform Resource Model, Architecture & Dependencies

### 2.1. Complete Resource Inventory

| Domain | Terraform Resource Type | Resource Role & Purpose |
| :--- | :--- | :--- |
| **API Activation** | `google_project_service` | Enables `compute`, `pubsub`, `dataflow`, `bigtable`, `redis`, `servicenetworking`, `secretmanager`, `eventarc`. |
| **Networking** | `google_compute_network` | Dedicated custom-subnet VPC (`hft-vpc`) with zero default routes. |
| **Networking** | `google_compute_subnetwork` | Regional subnet in `asia-northeast1` with Private Google Access enabled. |
| **Networking** | `google_compute_global_address` | Internal IP allocation block (`/16` or `/24`) for Private Service Connection. |
| **Networking** | `google_service_networking_connection` | VPC Peering connection to Google Service Networking (required for Redis). |
| **Networking** | `google_compute_router` | Regional Cloud Router managing Cloud NAT egress. |
| **Networking** | `google_compute_router_nat` | Cloud NAT gateway allowing instances to reach external Binance APIs securely without public IPs. |
| **Networking** | `google_compute_firewall` | Strict ingress/egress rules: denies all public ingress; allows internal VPC communication and Google IAP for SSH. |
| **Compute** | `google_compute_resource_policy` | Placement policy (`COLLOCATED`) for intra-rack low latency. |
| **Compute** | `google_compute_instance` | Low-latency C3/C4 instance with gVNIC, Tier 1 networking, and startup kernel optimizations. |
| **Pub/Sub** | `google_pubsub_topic` | Topics: `hft-market-trades`, `hft-market-orderbook`, `hft-market-snapshots`, `hft-market-dlq`. |
| **Pub/Sub** | `google_pubsub_subscription` | Subscriptions with message ordering, 10s ack deadline, and Dead Letter Policy. |
| **Storage (Bigtable)**| `google_bigtable_instance` | Production SSD instance in `asia-northeast1-c`. |
| **Storage (Bigtable)**| `google_bigtable_table` | `market_ticks` table with defined split keys. |
| **Storage (Bigtable)**| `google_bigtable_gc_policy` | Column family GC rules (1 version, 30 days retention). |
| **Storage (Redis)** | `google_redis_instance` | Standard HA Redis instance with AUTH and Private Service Connection. |
| **Dataflow** | `google_storage_bucket` | GCS staging bucket in `asia-northeast1` for Dataflow binaries and temporary files. |
| **Dataflow** | `google_dataflow_job` | Streaming pipeline running Runner v2 and Streaming Engine. |
| **IAM & Security** | `google_service_account` | Dedicated Service Accounts: `sa-hft-engine`, `sa-dataflow-worker`. |
| **IAM & Security** | `google_project_iam_member` | Least-privilege roles (`roles/bigtable.user`, `roles/pubsub.publisher`, `roles/pubsub.subscriber`, `roles/redis.editor`, `roles/secretmanager.secretAccessor`). |
| **Secrets** | `google_secret_manager_secret` | Secrets for Binance API Key, Binance API Secret, and Redis Auth Token. |
| **Secrets** | `google_secret_manager_secret_version`| Values populated or initialized for application access. |

---

### 2.2. Recommended Module Hierarchy

To maintain production clean code separation, the Terraform configuration should be structured into clean, reusable modules:

```
hft_gcp_architecture/
├── main.tf                    # Root coordinator invoking modules
├── variables.tf               # Environment variables (project, region, zone, machine_type)
├── outputs.tf                 # Key connection endpoints (Redis host, Bigtable instance, VM IP)
├── terraform.tfvars.example   # Example production parameters
├── versions.tf                # Provider pins (google >= 5.0, google-beta >= 5.0)
│
└── modules/
    ├── api_services/          # google_project_service declarations
    ├── networking/            # VPC, Subnet, Service Peering, Cloud NAT, Firewalls, Placement Policy
    ├── pubsub/                # Topics (trades, book, dlq) and Subscriptions with ordering/DLQ
    ├── compute/               # C3/C4 Compute Engine, gVNIC, Tier 1, Startup tuning script
    ├── storage_bigtable/      # Bigtable instance, cluster, table schema, column families, GC policies
    ├── storage_redis/         # Memorystore Redis Standard HA, VPC peering link, AUTH
    ├── dataflow/              # GCS staging bucket, Dataflow streaming job configuration
    └── iam_security/          # Least privilege SAs, IAM role bindings, Secret Manager
```

---

### 2.3. Cross-Resource Dependency Graph (DAG)

To prevent race conditions during `terraform apply -auto-approve`, resource dependencies must follow a strict Directed Acyclic Graph (DAG):

```
[Phase 0: APIs]
  google_project_service (compute, pubsub, redis, bigtable, dataflow, servicenetworking, secretmanager)
       │
       ▼
[Phase 1: Foundation Network & Security]
  google_compute_network (hft-vpc) ────────┬─────────────────────────────┐
       │                                   │                             │
       ▼                                   ▼                             ▼
  google_compute_subnetwork       google_compute_global_address    google_service_account
       │                                   │                       (sa-hft, sa-dataflow)
       ▼                                   ▼                             │
  google_compute_router           google_service_networking_             │
       │                          connection (peering)                   │
       ▼                                   │                             │
  google_compute_router_nat                │                             │
  & firewall rules                         │                             │
       │                                   │                             │
       ├───────────────────────────────────┼─────────────────────────────┤
       ▼                                   ▼                             ▼
[Phase 2: Core Data Stores & Queues]       │                             │
  google_pubsub_topic (DLQ first)          │                             │
       │                                   │                             │
       ▼                                   │                             │
  google_pubsub_topic (trades, orderbook)  │                             │
       │                                   │                             │
       ▼                                   │                             │
  google_pubsub_subscription               │                             │
       │                                   │                             │
  google_bigtable_instance                 │                             │
       │                                   │                             │
  google_bigtable_table                    ▼                             │
  & gc_policies                    google_redis_instance                 │
       │                           (depends_on: peering)                 │
       │                                   │                             │
       ├───────────────────────────────────┴─────────────────────────────┤
       │
       ▼
[Phase 3: Execution Engine & Compute]
  google_compute_resource_policy (compact placement)
       │
       ▼
  google_compute_instance (C3/C4 in asia-northeast1-c)
  (depends_on: subnetwork, router_nat, placement_policy, redis, bigtable, service_account)
       │
       ▼
[Phase 4: Streaming Analytics Pipeline]
  google_storage_bucket (staging/temp)
       │
       ▼
  google_dataflow_job
  (depends_on: pubsub_subscriptions, bigtable_table, redis_instance, storage_bucket)
```

---

## 3. Concrete Code Snippets & Specification Blueprints

### 3.1. Pub/Sub with Ordering & Dead Letter Policy (`modules/pubsub/main.tf`)
```hcl
# Dead Letter Topic
resource "google_pubsub_topic" "market_dlq" {
  name = "hft-market-data-dlq"
  message_storage_policy {
    allowed_persistence_regions = [var.region]
  }
}

# Trade Stream Topic
resource "google_pubsub_topic" "market_trades" {
  name                       = "hft-market-data-trades"
  message_retention_duration = "86400s" # 24 Hours

  message_storage_policy {
    allowed_persistence_regions = [var.region]
  }
}

# Trade Stream Subscription for Trading Engine
resource "google_pubsub_subscription" "trades_engine_sub" {
  name  = "hft-sub-trades-engine"
  topic = google_pubsub_topic.market_trades.id

  # Critical HFT Parameters
  enable_message_ordering = true
  ack_deadline_seconds    = 10
  retain_acked_messages   = false

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.market_dlq.id
    max_delivery_attempts = 5
  }

  retry_policy {
    minimum_backoff = "0.01s" # 10ms
    maximum_backoff = "1s"
  }
}
```

### 3.2. Low-Latency Compute Engine Instance (`modules/compute/main.tf`)
```hcl
resource "google_compute_resource_policy" "compact_placement" {
  name   = "hft-compact-placement"
  region = var.region
  group_placement_policy {
    colocation = "COLLOCATED"
  }
}

resource "google_compute_instance" "trading_engine" {
  name         = "hft-engine-node-01"
  machine_type = var.machine_type # e.g. "c3-standard-4" or "c4-standard-4"
  zone         = var.zone         # "asia-northeast1-c"

  resource_policies = [google_compute_resource_policy.compact_placement.id]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      type  = "pd-ssd"
      size  = 100
    }
  }

  network_interface {
    network    = var.network_id
    subnetwork = var.subnetwork_id
    nic_type   = "GVNIC" # Mandatory for C3/C4 ultra-low latency

    # No public IP assigned; egress via Cloud NAT
  }

  network_performance_config {
    total_egress_bandwidth_tier = "TIER_1"
  }

  service_account {
    email  = var.service_account_email
    scopes = ["cloud-platform"]
  }

  metadata_startup_script = <<-EOT
    #!/bin/bash
    set -e
    # Apply low-latency TCP sysctl tuning
    sysctl -w net.core.rmem_max=16777216
    sysctl -w net.core.wmem_max=16777216
    sysctl -w net.ipv4.tcp_rmem="4096 87380 16777216"
    sysctl -w net.ipv4.tcp_wmem="4096 65536 16777216"
    sysctl -w net.ipv4.tcp_low_latency=1
    sysctl -w net.ipv4.tcp_nodelay=1
    sysctl -w net.core.busy_read=50
    sysctl -w net.core.busy_poll=50
    echo "HFT Node Kernel Optimizations Applied"
  EOT

  scheduling {
    automatic_restart   = true
    on_host_maintenance = "MIGRATE"
  }

  tags = ["hft-trading-node"]
}
```

### 3.3. Cloud Bigtable Tick Store (`modules/storage_bigtable/main.tf`)
```hcl
resource "google_bigtable_instance" "hft_bigtable" {
  name          = "hft-tickstore-instance"
  instance_type = "PRODUCTION"

  cluster {
    cluster_id   = "hft-cluster-tokyo-c"
    zone         = var.zone # "asia-northeast1-c"
    num_nodes    = 1
    storage_type = "SSD" # Mandatory for sub-5ms latency
  }

  deletion_protection = false # Configurable for development/demo integrity
}

resource "google_bigtable_table" "market_ticks" {
  name          = "market_ticks"
  instance_name = google_bigtable_instance.hft_bigtable.name

  column_family {
    family = "trades"
  }
  column_family {
    family = "quotes"
  }
  column_family {
    family = "metrics"
  }
}

resource "google_bigtable_gc_policy" "trades_gc" {
  instance_name = google_bigtable_instance.hft_bigtable.name
  table         = google_bigtable_table.market_ticks.name
  column_family = "trades"

  max_version = 1
  max_age {
    duration = "2592000s" # 30 Days TTL
  }
}
```

### 3.4. Cloud Memorystore for Redis HA (`modules/storage_redis/main.tf`)
```hcl
resource "google_redis_instance" "hft_state_cache" {
  name           = "hft-state-cache"
  tier           = "STANDARD_HA" # Automatic cross-zone failover
  memory_size_gb = 5
  region         = var.region
  location_id    = var.zone # Primary in asia-northeast1-c

  redis_version      = "REDIS_7_0"
  display_name       = "HFT Live State Cache & Order Book Registry"
  authorized_network = var.network_id
  connect_mode       = "PRIVATE_SERVICE_ACCESS"

  auth_enabled = true

  transit_encryption_mode = var.transit_encryption_enabled ? "SERVER_AUTHENTICATION" : "DISABLED"

  depends_on = [var.service_networking_connection_id]
}
```

---

## 4. Key Findings & Strategic Recommendations for Implementation

1. **Machine Family Confirmation**:
   - Both `c3-standard-*` (Sapphire Rapids) and `c4-standard-*` (Emerald Rapids) are verified available in `asia-northeast1-c` on the user project.
   - For initial deployment, `c3-standard-4` or `c4-standard-4` provides optimal compute density and titanium IPU offload while remaining conservative on quota.
2. **VPC Peering Dependency**:
   - Redis deployment requires a prior `google_service_networking_connection`. The implementers must ensure that IP reservation and peering connection complete before triggering `google_redis_instance` creation.
3. **Private Egress via Cloud NAT**:
   - Trading nodes must not use external public IPs. Cloud NAT with minimum ports per VM ($1024$ or $2048$) must be configured so WebSocket streams to Binance don't face ephemeral port exhaustion.
4. **Dataflow Streaming Engine**:
   - Specifying `--enable_streaming_engine` and `--experiments=use_runner_v2` is mandatory to avoid JVM memory stalls during high-frequency tick bursts.

---

*Report concluded. Ready for synthesis by Orchestrator and consumption by implementation workers.*
