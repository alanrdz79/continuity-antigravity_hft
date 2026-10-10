## 2026-10-09T04:26:34Z
You are Explorer 2 for Milestone 2 (M2: Low-Latency Compute Engine C3/C4 in Tokyo) of the HFT GCP Architecture project.
Your assigned working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_m2_2
Target project path: C:\Users\alanr\teamwork_projects\hft_gcp_architecture
MANDATORY: Read ORIGINAL_REQUEST.md first at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\orchestrator_hft_gcp\PROJECT.md
Read survey findings: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_survey_arch\report.md and c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_survey_env\report.md

Your exploration focus:
1. Design the Compute Engine module (modules/compute):
   - Instance configuration:
     * Machine type variable defaulting to "c4-standard-4" with fallback to "c3-standard-4"
     * Zone: asia-northeast1-b or asia-northeast1-c (where C3/C4 verified available)
     * Image: debian-12 or ubuntu-2204-lts with NVMe / SSD root disk
     * gVNIC enabled: nic_type = "GVNIC"
     * Tier 1 network bandwidth: network_performance_config { total_egress_bandwidth_tier = "TIER_1" }
     * Collocated compact placement policy: google_compute_resource_policy with group_placement_policy { collocated = true }
     * Network interface: attached to module.networking.subnet_hft_id with ZERO access_config (0 public external IPs)
     * Service account: attached to module.iam.hft_engine_sa_email with scope https://www.googleapis.com/auth/cloud-platform
     * Metadata startup script: installs network tuning (TCP socket buffers sysctl, gVNIC queue settings) and validates zero public IP
2. Write complete blueprint code for modules/compute/ (variables.tf, main.tf, outputs.tf).
3. Document in report.md and handoff.md, then send message to parent orchestrator.
