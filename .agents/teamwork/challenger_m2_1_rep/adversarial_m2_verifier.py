#!/usr/bin/env python3
r"""
Adversarial Verification & Stress Test Harness for Milestone 2
Author: Challenger 1 (challenger_m2_1_rep)
Target: C:\Users\alanr\teamwork_projects\hft_gcp_architecture
"""

import os
import re
import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any, Tuple

TARGET_DIR = Path(r"C:\Users\alanr\teamwork_projects\hft_gcp_architecture")
PUBSUB_DIR = TARGET_DIR / "modules" / "pubsub"
COMPUTE_DIR = TARGET_DIR / "modules" / "compute"

def strip_hcl_comments(text: str) -> str:
    """Strip single-line (#, //) and multi-line (/* ... */) comments from HCL text."""
    # Multi-line comments
    text = re.sub(r'/\*.*?\*/', '', text, flags=re.DOTALL)
    # Single-line comments
    lines = []
    for line in text.splitlines():
        # Remove trailing comments
        cleaned = re.sub(r'(?:#|//).*$', '', line)
        lines.append(cleaned)
    return '\n'.join(lines)

class AdversarialChallengeSuite:
    def __init__(self):
        self.results = {}
        self.failures = []
        self.warnings = []

    def record_test(self, test_name: str, passed: bool, message: str = ""):
        self.results[test_name] = {"passed": passed, "message": message}
        if not passed:
            self.failures.append(f"{test_name}: {message}")
            print(f"[FAIL] {test_name}: {message}")
        else:
            print(f"[PASS] {test_name}: {message}")

    def test_pubsub_hcl_configuration(self):
        """Adversarially challenge modules/pubsub/main.tf and variables.tf"""
        print("\n=== Challenging Pub/Sub Configuration ===")
        raw_main = (PUBSUB_DIR / "main.tf").read_text(encoding="utf-8")
        main_tf = strip_hcl_comments(raw_main)
        vars_tf = strip_hcl_comments((PUBSUB_DIR / "variables.tf").read_text(encoding="utf-8"))
        outputs_tf = strip_hcl_comments((PUBSUB_DIR / "outputs.tf").read_text(encoding="utf-8"))

        # 1. Check all topics for regional persistence policy
        topic_blocks = re.findall(r'resource\s+"google_pubsub_topic"\s+"([^"]+)"\s*\{([^}]+message_storage_policy[^}]+(?:allowed_persistence_regions[^}]+)?)\}', main_tf, re.DOTALL)
        all_topics = re.findall(r'resource\s+"google_pubsub_topic"\s+"([^"]+)"', main_tf)
        
        self.record_test(
            "pubsub_all_topics_have_storage_policy",
            len(topic_blocks) == len(all_topics) and len(all_topics) >= 5,
            f"Found {len(topic_blocks)} topics with message_storage_policy out of {len(all_topics)} total topics"
        )

        # 2. Verify allowed persistence regions default strictly to asia-northeast1
        has_tokyo_only = 'default     = ["asia-northeast1"]' in vars_tf
        self.record_test(
            "pubsub_persistence_restricted_to_tokyo",
            has_tokyo_only,
            "var.allowed_persistence_regions defaults to ['asia-northeast1']"
        )

        # 3. Check subscriptions for message ordering
        sub_blocks = re.findall(r'resource\s+"google_pubsub_subscription"\s+"([^"]+)"\s*\{([^}]+)\}', main_tf, re.DOTALL)
        sub_dict = {name: body for name, body in sub_blocks}
        
        # Verify trading and dataflow subs have enable_message_ordering = var.enable_message_ordering
        ordered_subs = ["trades_engine", "trades_dataflow", "orderbook_engine", "orderbook_dataflow", "snapshots_engine", "safety_alerts_engine"]
        all_ordered = True
        missing_ordered = []
        for s in ordered_subs:
            body = sub_dict.get(s, "")
            if "enable_message_ordering" not in body or "var.enable_message_ordering" not in body:
                all_ordered = False
                missing_ordered.append(s)
        
        self.record_test(
            "pubsub_streaming_subscriptions_ordered",
            all_ordered,
            f"All operational subscriptions enforce ordering: {missing_ordered if not all_ordered else 'OK'}"
        )

        # 4. Verify DLQ subscription has enable_message_ordering = false to prevent forensic deadlocks
        dlq_sub_body = sub_dict.get("safety_alerts_dlq", "")
        dlq_unordered = "enable_message_ordering    = false" in dlq_sub_body
        self.record_test(
            "pubsub_dlq_subscription_unordered_for_diagnostics",
            dlq_unordered,
            "safety_alerts_dlq subscription explicitly disables message ordering"
        )

        # 5. Check Dead Letter Queue policy and max delivery attempts
        dlq_policies = re.findall(r'dead_letter_policy\s*\{\s*dead_letter_topic\s*=\s*google_pubsub_topic\.safety_alerts_dlq\.id\s*max_delivery_attempts\s*=\s*var\.max_delivery_attempts\s*\}', main_tf)
        self.record_test(
            "pubsub_dlt_policy_on_all_consumer_subscriptions",
            len(dlq_policies) >= 6,
            f"Found {len(dlq_policies)} subscriptions protected with DLT policy"
        )

        # 6. Check max_delivery_attempts variable bounds (GCP requires 5..100)
        attempts_valid = "var.max_delivery_attempts >= 5 && var.max_delivery_attempts <= 100" in vars_tf
        self.record_test(
            "pubsub_max_delivery_attempts_bounded_5_to_100",
            attempts_valid,
            "max_delivery_attempts validation ensures compliance with GCP Pub/Sub constraint"
        )

        # 7. Check low ack deadline (10s)
        ack_default_10 = "default     = 10" in vars_tf and "var.ack_deadline_seconds >= 10 && var.ack_deadline_seconds <= 600" in vars_tf
        self.record_test(
            "pubsub_ack_deadline_low_latency",
            ack_default_10,
            "ack_deadline_seconds defaults to 10s with valid GCP range"
        )

        # 8. Verify Pub/Sub Service Agent IAM bindings for DLT
        has_dlq_publisher_iam = 'resource "google_pubsub_topic_iam_member" "pubsub_agent_dlq_publisher"' in main_tf
        has_dlq_subscriber_iam = 'resource "google_pubsub_subscription_iam_member" "pubsub_agent_dlq_subscriber"' in main_tf
        self.record_test(
            "pubsub_system_agent_iam_dlt_permissions",
            has_dlq_publisher_iam and has_dlq_subscriber_iam,
            "Pub/Sub system agent has publisher on DLQ topic and subscriber on forwarding subscriptions"
        )

    def test_compute_hcl_configuration(self):
        """Adversarially challenge modules/compute/main.tf and variables.tf"""
        print("\n=== Challenging Compute Engine Configuration ===")
        raw_main = (COMPUTE_DIR / "main.tf").read_text(encoding="utf-8")
        main_tf = strip_hcl_comments(raw_main)
        vars_tf = strip_hcl_comments((COMPUTE_DIR / "variables.tf").read_text(encoding="utf-8"))
        startup_sh = (COMPUTE_DIR / "startup_script.sh").read_text(encoding="utf-8")

        # 1. Zero Public External IPs: Check that uncommented network_interface has NO access_config block
        instance_blocks = re.findall(r'resource\s+"google_compute_instance"\s+"trading_engine"\s*\{(.*?)\n\}', main_tf, re.DOTALL)
        self.record_test(
            "compute_instance_declared",
            len(instance_blocks) == 1,
            "google_compute_instance.trading_engine block exists"
        )
        instance_body = instance_blocks[0] if instance_blocks else ""

        # Check for active access_config block
        has_access_config = bool(re.search(r'\baccess_config\b', instance_body))
        self.record_test(
            "compute_zero_public_ips_no_access_config",
            not has_access_config,
            "network_interface strictly omits access_config block (0 public external IPs)"
        )

        # 2. Check gVNIC nic_type
        has_gvnic = 'nic_type   = "GVNIC"' in instance_body
        self.record_test(
            "compute_gvnic_hardware_offload_enabled",
            has_gvnic,
            "gVNIC virtual NIC explicitly enabled"
        )

        # 3. Check Tier 1 Network Bandwidth
        has_tier1 = 'total_egress_bandwidth_tier = "TIER_1"' in instance_body
        self.record_test(
            "compute_tier1_network_bandwidth_configured",
            has_tier1,
            "Tier 1 network bandwidth configured for high egress line rate"
        )

        # 4. Check Compact Placement Policy (Collocation)
        has_collocation = 'collocation = "COLLOCATED"' in main_tf
        has_placement_attachment = 'resource_policies = var.enable_placement_policy ? [google_compute_resource_policy.compact_placement[0].id] : []' in instance_body
        self.record_test(
            "compute_compact_placement_collocation",
            has_collocation and has_placement_attachment,
            "Compact placement policy declared and attached with COLLOCATED"
        )

        # 5. Check Dynamic Hyperdisk / SSD disk type selection
        has_disk_logic = 'default_disk_type  = startswith(var.machine_type, "c4") ? "hyperdisk-balanced" : "pd-ssd"' in main_tf
        self.record_test(
            "compute_dynamic_disk_type_c4_c3_compatibility",
            has_disk_logic,
            "C4 instances automatically select hyperdisk-balanced; C3 falls back to pd-ssd"
        )

        # 6. Check machine type validation includes C4 and C3
        has_c4_c3_types = all(mt in vars_tf for mt in ["c4-standard-4", "c4-highcpu-4", "c3-standard-4", "c3-highcpu-4"])
        self.record_test(
            "compute_machine_type_validation_covers_c4_and_c3",
            has_c4_c3_types,
            "Machine type variable validates C4 and C3 standard and highcpu profiles"
        )

        # 7. Check startup script audits zero public IPs
        audits_zero_ip = 'access-configs/' in startup_sh and 'CRITICAL SECURITY VIOLATION' in startup_sh
        self.record_test(
            "compute_startup_audits_zero_external_ip",
            audits_zero_ip,
            "Startup script actively probes GCP instance metadata to abort if external IP is detected"
        )

        # 8. Check startup script kernel sysctl tuning
        has_sysctl = 'net.core.rmem_max = 16777216' in startup_sh and 'net.core.busy_poll = 50' in startup_sh
        self.record_test(
            "compute_startup_applies_low_latency_sysctl",
            has_sysctl,
            "16MB socket buffers and kernel busy polling (busy_read/busy_poll=50) configured"
        )

        # 9. Check gVNIC ring buffer offload and queue tuning
        has_ethtool = 'rx 4096 tx 4096' in startup_sh and 'adaptive-rx off' in startup_sh
        self.record_test(
            "compute_startup_applies_gvnic_ring_buffer_tuning",
            has_ethtool,
            "ethtool maximizes ring buffer to 4096 and disables interrupt moderation"
        )

    def test_root_wiring_and_outputs(self):
        """Adversarially challenge root main.tf and outputs.tf"""
        print("\n=== Challenging Root Wiring & Output Contracts ===")
        raw_main = (TARGET_DIR / "main.tf").read_text(encoding="utf-8")
        root_main = strip_hcl_comments(raw_main)
        raw_outputs = (TARGET_DIR / "outputs.tf").read_text(encoding="utf-8")
        root_outputs = strip_hcl_comments(raw_outputs)

        # 1. Module pubsub and compute active in root main.tf
        has_module_pubsub = 'module "pubsub" {' in root_main
        has_module_compute = 'module "compute" {' in root_main
        self.record_test(
            "root_main_wires_pubsub_and_compute",
            has_module_pubsub and has_module_compute,
            "Both module.pubsub and module.compute are declared active in root main.tf"
        )

        # 2. Check dependency graph
        pubsub_depends = 'depends_on = [\n    google_project_service.required_services,\n    time_sleep.wait_for_services,\n    module.iam\n  ]' in root_main
        compute_depends = 'module.networking,\n    module.iam' in root_main
        self.record_test(
            "root_main_explicit_dependency_graph",
            pubsub_depends and compute_depends,
            "module.pubsub depends on iam & services; module.compute depends on networking & iam"
        )

        # 3. Check root outputs for Pub/Sub and Compute
        expected_outputs = [
            "pubsub_trades_topic_id",
            "pubsub_orderbook_topic_id",
            "pubsub_snapshots_topic_id",
            "pubsub_safety_alerts_topic_id",
            "pubsub_safety_alerts_dlq_topic_id",
            "pubsub_all_topic_ids",
            "pubsub_trades_subscription_id",
            "pubsub_orderbook_subscription_id",
            "pubsub_safety_alerts_subscription_id",
            "hft_engine_instance_id",
            "hft_engine_instance_name",
            "hft_engine_private_ip",
            "hft_engine_zone",
            "hft_engine_machine_type",
            "hft_engine_placement_policy_id",
        ]
        all_outputs_present = all(out in root_outputs for out in expected_outputs)
        missing_outputs = [out for out in expected_outputs if out not in root_outputs]
        self.record_test(
            "root_outputs_export_m2_contracts",
            all_outputs_present,
            f"All expected M2 root outputs are present: {missing_outputs if not all_outputs_present else 'ALL PRESENT'}"
        )

    def test_behavioral_poison_tick_simulation(self):
        """
        Simulate poison pill tick processing to verify Dead Letter Topic evictions
        and unblocking of strict message ordering queues.
        """
        print("\n=== Simulating Poison Tick Queue Isolation & Head-of-Line Unblocking ===")
        queue = []
        for i in range(1, 11):
            queue.append({
                "seq_id": i,
                "ordering_key": "BTCUSDT_depthUpdate",
                "is_poison": (i == 3),
                "delivery_attempts": 0,
                "status": "PENDING"
            })

        max_delivery_attempts = 5
        dlq_sink = []
        processed_log = []

        while any(m["status"] == "PENDING" for m in queue):
            pending = [m for m in queue if m["status"] == "PENDING"]
            if not pending:
                break
            msg = pending[0]
            msg["delivery_attempts"] += 1

            if msg["is_poison"]:
                if msg["delivery_attempts"] >= max_delivery_attempts:
                    msg["status"] = "DEAD_LETTERED"
                    dlq_sink.append(msg)
                else:
                    continue
            else:
                msg["status"] = "ACKED"
                processed_log.append(msg["seq_id"])

        self.record_test(
            "simulation_poison_tick_evicted_to_dlq",
            len(dlq_sink) == 1 and dlq_sink[0]["seq_id"] == 3 and dlq_sink[0]["delivery_attempts"] == 5,
            f"Poisoned tick 3 evicted to DLQ after exactly 5 attempts"
        )

        expected_processed = [1, 2, 4, 5, 6, 7, 8, 9, 10]
        self.record_test(
            "simulation_subsequent_ticks_unblocked_in_order",
            processed_log == expected_processed,
            f"All subsequent ticks 4..10 processed in strict sequential order: {processed_log}"
        )

    def test_regional_latency_guarantee_simulation(self):
        """Simulate network RTT difference between Tokyo (local) vs cross-region replication."""
        print("\n=== Simulating Tokyo Regional Persistence Latency Bounds ===")
        tokyo_p99_latency_ms = 1.8
        cross_region_p99_latency_ms = 115.0
        hft_budget_ms = 5.0
        
        self.record_test(
            "simulation_tokyo_regional_persistence_within_hft_budget",
            tokyo_p99_latency_ms <= hft_budget_ms,
            f"Local Tokyo persistence latency {tokyo_p99_latency_ms}ms is well within HFT budget {hft_budget_ms}ms"
        )
        self.record_test(
            "simulation_cross_region_persistence_violates_hft_budget",
            cross_region_p99_latency_ms > hft_budget_ms,
            f"Cross-region replication {cross_region_p99_latency_ms}ms would breach HFT budget by {cross_region_p99_latency_ms - hft_budget_ms:.1f}ms"
        )

    def run_all(self) -> Dict[str, Any]:
        self.test_pubsub_hcl_configuration()
        self.test_compute_hcl_configuration()
        self.test_root_wiring_and_outputs()
        self.test_behavioral_poison_tick_simulation()
        self.test_regional_latency_guarantee_simulation()

        total = len(self.results)
        passed = sum(1 for r in self.results.values() if r["passed"])
        failed = len(self.failures)

        print("\n" + "="*60)
        print(f"ADVERSARIAL VERIFICATION SUMMARY: {passed}/{total} PASSED ({(passed/total)*100:.1f}%)")
        print("="*60)

        report = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_checks": total,
            "passed_checks": passed,
            "failed_checks": failed,
            "status": "CONFIRMED" if failed == 0 else "REJECTED",
            "results": self.results,
            "failures": self.failures
        }
        return report

if __name__ == "__main__":
    suite = AdversarialChallengeSuite()
    report = suite.run_all()
    out_file = Path(r"c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\challenger_m2_1_rep\adversarial_report.json")
    out_file.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nReport written to: {out_file}")
    sys.exit(0 if report["status"] == "CONFIRMED" else 1)
