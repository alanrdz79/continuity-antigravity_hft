# HFT GCP Autonomous Cloud Architecture

Target project repository for high-frequency trading infrastructure on Google Cloud Platform.

## Architecture Scope
- **Core Infrastructure**: Pub/Sub, Dataflow, Compute Engine (C3/C4 with gVNIC in Asia-Northeast), Memorystore Redis, Cloud Bigtable.
- **Autonomous Safety**: EventArc v2, Cloud Monitoring alert policies, Emergency Kill Switch.
- **Resilience & Security**: Isolated VPC, Private Google Access, Cloud NAT, Secret Manager, Least-Privilege IAM.
- **Documentation**: Comprehensive `architecture_summary.md`.

*Initialized during Phase 0 Survey (Environment & Tooling).*
