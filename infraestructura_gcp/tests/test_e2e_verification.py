r"""
CONTINUITY HFT GCP Automated Verification Test Suite (Pytest / Unittest).
Target: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\tests\test_e2e_verification.py

Follows the 4-Tier Test Architecture from TEST_INFRA.md:
- Tier 1: Feature Coverage (0 public IPs, PGA, IAM least privilege, Pub/Sub, Bigtable, Redis)
- Tier 2: Boundary & Corner Cases (800ms threshold boundaries, HTTP 429/418, empty instances)
- Tier 3: Cross-Feature Pairwise (Bigtable reverse timestamp math, EventArc -> Redis pipeline)
- Tier 4: Real-World Workload Scenarios (Binance market suspension, HMAC signature validation)
"""

import hashlib
import hmac
import os
import sys
import unittest
from pathlib import Path

# Add scripts directory to sys.path so we can import test modules
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from verify_security_posture import (
    audit_network_isolation,
    audit_subnet_security,
    audit_iam_least_privilege,
    get_mock_data,
)
from test_hft_resilience import (
    format_bigtable_row_key,
    verify_reverse_timestamp_sorting,
    verify_pubsub_resilience_specs,
    verify_redis_emergency_kill_switch_contract,
    get_mock_resilience_data,
    REQUIRED_COLUMN_FAMILIES,
    EMERGENCY_REDIS_KEY,
)
from test_safety_orchestration import (
    evaluate_latency_trigger,
    evaluate_market_status_trigger,
    evaluate_api_status_code_trigger,
    generate_binance_cancel_all_payload,
    execute_simulated_emergency_shutdown,
    LATENCY_THRESHOLD_MS,
)
from test_infrastructure_syntax import (
    run_self_test,
    check_balanced_delimiters,
)


class TestTier1FeatureCoverage(unittest.TestCase):
    """Tier 1: Feature Coverage tests for individual architecture components."""

    def test_network_isolation_compliant_zero_public_ips(self):
        """T1.1: Verify compliant instances have 0 public IPs and pass audit."""
        mock_data = get_mock_data(compliant=True)
        passed, inspected, violations = audit_network_isolation(mock_data["instances"])
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)
        self.assertEqual(len(inspected), 1)
        self.assertEqual(inspected[0]["status"], "PASS")

    def test_subnet_private_google_access_compliant(self):
        """T1.2: Verify subnets with PGA enabled pass audit."""
        mock_data = get_mock_data(compliant=True)
        passed, inspected, violations = audit_subnet_security(mock_data["subnets"])
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)
        self.assertEqual(len(inspected), 3)
        for sub in inspected:
            self.assertEqual(sub["status"], "PASS")

    def test_iam_least_privilege_compliant_no_primitive_roles(self):
        """T1.3: Verify project IAM policy contains 0 primitive Owner/Editor roles for HFT SAs."""
        mock_data = get_mock_data(compliant=True)
        passed, inspected, violations = audit_iam_least_privilege(mock_data["iam_policy"])
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

    def test_pubsub_topic_resilience_inventory(self):
        """T1.4: Verify all required Pub/Sub topics exist with proper ack deadlines."""
        mock_resilience = get_mock_resilience_data()
        passed, violations, details = verify_pubsub_resilience_specs(
            mock_resilience["pubsub_topics"], mock_resilience["pubsub_subscriptions"]
        )
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)
        self.assertEqual(len(details["topics_found"]), 5)

    def test_bigtable_column_families_schema(self):
        """T1.5: Verify Bigtable column families correspond to trades, quotes, and metrics."""
        self.assertIn("t", REQUIRED_COLUMN_FAMILIES)
        self.assertIn("q", REQUIRED_COLUMN_FAMILIES)
        self.assertIn("m", REQUIRED_COLUMN_FAMILIES)

    def test_redis_emergency_kill_switch_contract(self):
        """T1.6: Verify atomic Redis kill switch key contract."""
        passed, violations, details = verify_redis_emergency_kill_switch_contract()
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)
        self.assertEqual(details["key"], EMERGENCY_REDIS_KEY)
        self.assertEqual(details["active_value"], "1")

    def test_terraform_syntax_audit_self_test(self):
        """T1.7: Verify Terraform infrastructure syntax validator against reference fixture."""
        report = run_self_test()
        self.assertEqual(report["status"], "PASSED")
        self.assertEqual(report["summary"]["total_violations"], 0)
        self.assertTrue(report["checks"]["root_files_present"])
        self.assertTrue(report["checks"]["modules_present"])
        self.assertTrue(report["checks"]["syntax_delimiters"])
        self.assertTrue(report["checks"]["anti_leak_secrets"])
        self.assertTrue(report["checks"]["architectural_rules"])


class TestTier2BoundaryAndCorners(unittest.TestCase):
    """Tier 2: Boundary and Corner Case checks."""

    def test_network_isolation_catches_public_ip_violation(self):
        """T2.1: Detector correctly flags instance with public natIP."""
        mock_bad = get_mock_data(compliant=False)
        passed, inspected, violations = audit_network_isolation(mock_bad["instances"])
        self.assertFalse(passed)
        self.assertGreater(len(violations), 0)
        self.assertIn("public IP", violations[0])

    def test_subnet_catches_disabled_private_google_access(self):
        """T2.2: Detector correctly flags subnet with privateIpGoogleAccess=False."""
        mock_bad = get_mock_data(compliant=False)
        passed, inspected, violations = audit_subnet_security(mock_bad["subnets"])
        self.assertFalse(passed)
        self.assertGreater(len(violations), 0)
        self.assertIn("Private Google Access DISABLED", violations[0])

    def test_iam_catches_primitive_editor_role(self):
        """T2.3: Detector correctly flags primitive roles (roles/editor) assigned to HFT SAs."""
        mock_bad = get_mock_data(compliant=False)
        passed, inspected, violations = audit_iam_least_privilege(mock_bad["iam_policy"])
        self.assertFalse(passed)
        self.assertGreater(len(violations), 0)
        self.assertIn("roles/editor", violations[0])

    def test_latency_threshold_boundary_precision(self):
        """T2.4: Test exact boundary precision for latency rule (800.0ms)."""
        # Exactly 800.0ms does not trigger (> 800ms rule)
        trig_800, _ = evaluate_latency_trigger(800.0)
        self.assertFalse(trig_800)

        # 800.001ms triggers
        trig_800_1, _ = evaluate_latency_trigger(800.001)
        self.assertTrue(trig_800_1)

        # 799.9ms does not trigger
        trig_799, _ = evaluate_latency_trigger(799.9)
        self.assertFalse(trig_799)

        # 1200.0ms triggers
        trig_1200, _ = evaluate_latency_trigger(1200.0)
        self.assertTrue(trig_1200)

    def test_api_status_codes_boundary(self):
        """T2.5: Test HTTP response codes triggering circuit breakers."""
        trig_200, _ = evaluate_api_status_code_trigger(200)
        self.assertFalse(trig_200)

        trig_429, _ = evaluate_api_status_code_trigger(429)
        self.assertTrue(trig_429)

        trig_418, _ = evaluate_api_status_code_trigger(418)
        self.assertTrue(trig_418)

    def test_empty_instance_list_graceful_pass(self):
        """T2.6: Empty instance list produces 0 violations."""
        passed, inspected, violations = audit_network_isolation([])
        self.assertTrue(passed)
        self.assertEqual(len(violations), 0)

    def test_syntax_delimiter_checker_detects_unmatched_brace(self):
        """T2.7: Delimiter checker detects unmatched brace in malformed file."""
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".tf", delete=False) as tf:
            tf.write('resource "google_compute_instance" "bad" {\n  name = "broken"\n')
            tf_path = Path(tf.name)
        try:
            ok, errs = check_balanced_delimiters(tf_path)
            self.assertFalse(ok)
            self.assertGreater(len(errs), 0)
        finally:
            if tf_path.exists():
                tf_path.unlink()


class TestTier3CrossFeaturePairwise(unittest.TestCase):
    """Tier 3: Cross-Feature interaction tests."""

    def test_bigtable_reverse_timestamp_mathematical_ordering(self):
        """T3.1: Mathematical proof of reverse-timestamp lexicographical sorting."""
        passed, errors = verify_reverse_timestamp_sorting()
        self.assertTrue(passed)
        self.assertEqual(len(errors), 0)

        # Additional multi-timestamp validation
        timestamps = [1000, 2000, 5000, 10000, 999999]
        keys = [format_bigtable_row_key("ETHUSDT", ts, idx) for idx, ts in enumerate(timestamps)]
        # Since timestamps are strictly increasing, keys must be strictly decreasing!
        for i in range(len(keys) - 1):
            self.assertGreater(keys[i], keys[i + 1])

    def test_emergency_event_to_redis_kill_switch_pipeline(self):
        """T3.2: Verify pipeline integration between safety trigger and Redis kill flag."""
        latency = 850.0  # Spikes above 800ms
        should_halt, reason = evaluate_latency_trigger(latency)
        self.assertTrue(should_halt)

        result = execute_simulated_emergency_shutdown(reason=reason, symbol="BTCUSDT")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["redis_flag_set"][EMERGENCY_REDIS_KEY], "1")
        self.assertEqual(result["engine_halt_signal"]["action"], "HALT_ALL_WORKERS")


class TestTier4RealWorldOperationalScenarios(unittest.TestCase):
    """Tier 4: Real-world operational scenarios."""

    def test_market_suspended_triggers_emergency_purge_with_valid_hmac(self):
        """T4.1: Market suspension triggers full order purge with valid HMAC-SHA256 signature."""
        status = "SUSPENDED"
        triggered, reason = evaluate_market_status_trigger(status)
        self.assertTrue(triggered)

        api_key = "test_binance_api_key_123456789"
        secret_key = "test_binance_secret_key_abcdefgh"
        symbol = "SOLUSDT"

        payload = generate_binance_cancel_all_payload(symbol, api_key, secret_key)
        self.assertEqual(payload["method"], "DELETE")
        self.assertEqual(payload["headers"]["X-MBX-APIKEY"], api_key)
        self.assertEqual(payload["params"]["symbol"], symbol)

        # Verify HMAC-SHA256 signature
        query_str = f"symbol={symbol}&timestamp={payload['params']['timestamp']}&recvWindow=5000"
        expected_sig = hmac.new(
            secret_key.encode("utf-8"), query_str.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        self.assertEqual(payload["params"]["signature"], expected_sig)


if __name__ == "__main__":
    unittest.main()
