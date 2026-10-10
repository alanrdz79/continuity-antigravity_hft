r"""
CONTINUITY HFT GCP Architecture - Empirical Adversarial Challenge Test Suite for Safety Orchestration.
Target: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\tests\test_safety_adversarial.py

Adversarial Verification Scope (Milestone 4 Challenger):
1. Feed Latency Boundary Stress Testing:
   - Exactly 800.0ms (safe, False)
   - Exactly 800.1ms (breach, True)
   - Exactly 799.9ms (safe, False)
   - Microsecond precision: 800.000001ms (breach, True) vs 800.000000ms (safe, False)
   - Extreme values: -50.0ms, 0.0ms, 50000.0ms
   - Cross-module consistency (scripts/test_safety_orchestration vs functions/emergency_shutdown/main)
2. API Status Code Evaluation Stress Testing:
   - 429 (breach, True)
   - 418 (breach, True)
   - 200 (safe, False)
   - 500 (standard, False)
   - Comprehensive boundary matrix: 100, 201, 400, 401, 403, 404, 502, 503, 504
3. Market Status Evaluation Stress Testing:
   - 'SUSPENDED' (breach, True)
   - 'TRADING' (safe, False)
   - Case-insensitivity: 'suspended', 'Suspended', 'SuSpEnDeD' (breach, True)
   - Unrecognized statuses: 'HALT', 'BREAK', 'AUCTION', 'PRE_TRADING' (safe, False)
4. Cryptographic HMAC-SHA256 Signature Generator Verification:
   - Exact match against official Binance API test vector from REST API docs
   - Mathematical proof of payload construction (DELETE /api/v3/openOrders)
   - RFC 2104 compliance: 64-char lowercase hexadecimal digest
   - Multi-symbol and multi-recvWindow invariant preservation
5. 4-Stage Emergency Shutdown Pipeline Contract & Performance:
   - Stage 1: Redis atomic flag 'hft:emergency:kill_switch_active' = 1
   - Stage 2: Signed Binance order purge
   - Stage 3: Engine halt signal 'HALT_ALL_WORKERS'
   - Stage 4: Telegram markdown incident dispatch
   - End-to-end execution latency <= 100ms
6. Infrastructure HCL Verification for Milestone 4:
   - EventArc v2 trigger destination and transport bindings
   - Monitoring alert policies for latency (>800ms) and API errors (429/418)
   - Secret Manager environment variables wiring
   - Serverless VPC connector declaration for private Memorystore Redis
"""

import hashlib
import hmac
import json
import re
import sys
import time
import unittest
from pathlib import Path
from typing import Dict, Any

# Ensure project modules are importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
FUNCTIONS_DIR = PROJECT_ROOT / "functions" / "emergency_shutdown"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(FUNCTIONS_DIR) not in sys.path:
    sys.path.insert(0, str(FUNCTIONS_DIR))

import test_safety_orchestration as tso
import main as esm


class TestLatencyBoundaryAdversarial(unittest.TestCase):
    """Adversarial stress-testing of the 800ms feed latency boundary."""

    def test_latency_exact_boundary_conditions(self):
        """Verify strict inequality > 800.0ms across both test harness and Cloud Function."""
        test_modules = [
            ("scripts/test_safety_orchestration", tso.evaluate_latency_trigger),
            ("functions/emergency_shutdown/main", esm.evaluate_latency_trigger),
        ]

        for mod_name, eval_fn in test_modules:
            # Exactly 800.0ms is on the boundary -> SAFE (False)
            trig_800, r_800 = eval_fn(800.0)
            self.assertFalse(trig_800, f"{mod_name}: 800.0ms must be SAFE (<= 800.0)")
            self.assertIn("safe", r_800.lower())

            # 800.1ms exceeds boundary -> BREACH (True)
            trig_800_1, r_800_1 = eval_fn(800.1)
            self.assertTrue(trig_800_1, f"{mod_name}: 800.1ms must BREACH (> 800.0)")
            self.assertIn("exceeded", r_800_1.lower())

            # 799.9ms is below boundary -> SAFE (False)
            trig_799_9, r_799_9 = eval_fn(799.9)
            self.assertFalse(trig_799_9, f"{mod_name}: 799.9ms must be SAFE (<= 800.0)")
            self.assertIn("safe", r_799_9.lower())

    def test_latency_microsecond_precision(self):
        """Verify microsecond floating point boundary behavior."""
        for eval_fn in [tso.evaluate_latency_trigger, esm.evaluate_latency_trigger]:
            # 800.000001ms breaches threshold
            trig, _ = eval_fn(800.000001)
            self.assertTrue(trig, "800.000001ms must trigger breach")

            # 799.999999ms does not breach threshold
            trig, _ = eval_fn(799.999999)
            self.assertFalse(trig, "799.999999ms must not trigger breach")

    def test_latency_extreme_edge_cases(self):
        """Verify boundary behavior on 0, negative values, and massive latency spikes."""
        for eval_fn in [tso.evaluate_latency_trigger, esm.evaluate_latency_trigger]:
            # Zero latency
            trig_zero, _ = eval_fn(0.0)
            self.assertFalse(trig_zero)

            # Negative latency (clock drift / abnormal skew)
            trig_neg, _ = eval_fn(-50.0)
            self.assertFalse(trig_neg)

            # Massive latency spike (e.g. network partition, 120 seconds)
            trig_massive, r_massive = eval_fn(120000.0)
            self.assertTrue(trig_massive)
            self.assertIn("exceeded", r_massive.lower())


class TestApiStatusCodeAdversarial(unittest.TestCase):
    """Adversarial testing of HTTP status code triggers (429 rate limit and 418 IP ban)."""

    def test_api_status_codes_required_cases(self):
        """Verify exact status codes 429, 418, 200, 500."""
        test_modules = [
            ("scripts/test_safety_orchestration", tso.evaluate_api_status_code_trigger),
            ("functions/emergency_shutdown/main", esm.evaluate_api_status_code_trigger),
        ]

        for mod_name, eval_fn in test_modules:
            # 429: Rate Limit Breach -> True
            trig_429, r_429 = eval_fn(429)
            self.assertTrue(trig_429, f"{mod_name}: HTTP 429 must trigger breach")
            self.assertIn("429", r_429)

            # 418: I'm a teapot / IP Ban -> True
            trig_418, r_418 = eval_fn(418)
            self.assertTrue(trig_418, f"{mod_name}: HTTP 418 must trigger breach")
            self.assertIn("418", r_418)

            # 200: OK -> False
            trig_200, r_200 = eval_fn(200)
            self.assertFalse(trig_200, f"{mod_name}: HTTP 200 must be safe")
            self.assertIn("standard", r_200)

            # 500: Internal Server Error -> False (not a rate limit / ban trigger)
            trig_500, r_500 = eval_fn(500)
            self.assertFalse(trig_500, f"{mod_name}: HTTP 500 must not trigger rate limit breach")
            self.assertIn("standard", r_500)

    def test_api_status_codes_exhaustive_matrix(self):
        """Verify that non-rate-limit HTTP codes do not falsely trigger circuit breakers."""
        non_trigger_codes = [100, 201, 204, 301, 302, 400, 401, 403, 404, 502, 503, 504]
        for code in non_trigger_codes:
            trig_tso, _ = tso.evaluate_api_status_code_trigger(code)
            trig_esm, _ = esm.evaluate_api_status_code_trigger(code)
            self.assertFalse(trig_tso, f"HTTP {code} should not trigger circuit breaker in tso")
            self.assertFalse(trig_esm, f"HTTP {code} should not trigger circuit breaker in esm")


class TestMarketStatusAdversarial(unittest.TestCase):
    """Adversarial testing of market status (SUSPENDED vs TRADING)."""

    def test_market_status_required_cases(self):
        """Verify SUSPENDED triggers breach and TRADING is safe."""
        test_modules = [
            ("scripts/test_safety_orchestration", tso.evaluate_market_status_trigger),
            ("functions/emergency_shutdown/main", esm.evaluate_market_status_trigger),
        ]

        for mod_name, eval_fn in test_modules:
            trig_susp, r_susp = eval_fn("SUSPENDED")
            self.assertTrue(trig_susp, f"{mod_name}: SUSPENDED must trigger breach")
            self.assertIn("SUSPENDED", r_susp)

            trig_trad, r_trad = eval_fn("TRADING")
            self.assertFalse(trig_trad, f"{mod_name}: TRADING must be safe")
            self.assertIn("TRADING", r_trad)

    def test_market_status_case_insensitivity(self):
        """Verify case insensitivity when evaluating market status."""
        for eval_fn in [tso.evaluate_market_status_trigger, esm.evaluate_market_status_trigger]:
            for variant in ["suspended", "Suspended", "SuSpEnDeD", "sUsPeNdEd"]:
                trig, _ = eval_fn(variant)
                self.assertTrue(trig, f"Variant '{variant}' must trigger breach")

    def test_market_status_other_statuses_safe(self):
        """Verify that non-suspended statuses do not trigger market suspension."""
        other_statuses = ["TRADING", "trading", "HALT", "BREAK", "PRE_TRADING", "POST_TRADING", "AUCTION"]
        for stat in other_statuses:
            trig_tso, _ = tso.evaluate_market_status_trigger(stat)
            trig_esm, _ = esm.evaluate_market_status_trigger(stat)
            self.assertFalse(trig_tso, f"Market status '{stat}' should not trigger in tso")
            self.assertFalse(trig_esm, f"Market status '{stat}' should not trigger in esm")


class TestHmacSha256CryptographicVerification(unittest.TestCase):
    """Mathematical and empirical cryptographic verification of HMAC-SHA256 signatures."""

    def test_binance_official_api_test_vector(self):
        """
        Verify exact match against the official Binance REST API documentation test vector.
        Source: binance-spot-api-docs 'SIGNED Endpoint Examples for POST /api/v3/order'
        Key: 'NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j'
        Payload: 'symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1&recvWindow=5000&timestamp=1499827319559'
        Expected Signature: 'c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71'
        """
        secret_key = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
        query_string = (
            "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1&recvWindow=5000&timestamp=1499827319559"
        )
        expected_sig = "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"

        calculated_sig = hmac.new(
            secret_key.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        self.assertEqual(
            calculated_sig,
            expected_sig,
            "Cryptographic oracle failed: calculated signature does not match Binance official test vector!",
        )

    def test_binance_cancel_all_payload_generation_contract(self):
        """
        Empirically verify generate_binance_cancel_all_payload construction and signature.
        Checks both scripts/test_safety_orchestration and functions/emergency_shutdown/main.
        """
        api_key = "dummy_api_key_for_testing_purposes_only"
        secret_key = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
        symbol = "BTCUSDT"

        for fn, name in [
            (tso.generate_binance_cancel_all_payload, "tso"),
            (esm.generate_binance_cancel_all_payload, "esm"),
        ]:
            t_before = int(time.time() * 1000)
            payload = fn(symbol=symbol, api_key=api_key, secret_key=secret_key)
            t_after = int(time.time() * 1000)

            # Contract checks
            self.assertEqual(payload["method"], "DELETE", f"{name}: Method must be DELETE")
            self.assertEqual(payload["endpoint"], "https://api.binance.com/api/v3/openOrders")
            self.assertEqual(payload["headers"]["X-MBX-APIKEY"], api_key)
            self.assertEqual(payload["params"]["symbol"], symbol)
            self.assertEqual(payload["params"]["recvWindow"], 5000)

            # Timestamp sanity check (monotonic within invocation window)
            ts = payload["params"]["timestamp"]
            self.assertTrue(t_before <= ts <= t_after + 50, f"{name}: Timestamp out of bounds")

            # Signature cryptographic verification
            reconstructed_query = f"symbol={symbol}&timestamp={ts}&recvWindow=5000"
            expected_hmac = hmac.new(
                secret_key.encode("utf-8"),
                reconstructed_query.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            actual_sig = payload["params"]["signature"]
            self.assertEqual(
                actual_sig,
                expected_hmac,
                f"{name}: Signature mismatch on DELETE /api/v3/openOrders query string",
            )

            # Format verification: 64 hexadecimal characters
            self.assertTrue(re.match(r"^[0-9a-f]{64}$", actual_sig), f"{name}: Signature must be 64 lowercase hex chars")

    def test_hmac_signature_multi_symbol_and_window(self):
        """Verify HMAC signature calculation across multiple symbols and custom recvWindow parameters."""
        secret = "test_super_secret_hft_key_2026_q4"
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
        recv_windows = [1000, 2500, 5000, 10000, 60000]

        for sym in symbols:
            for rw in recv_windows:
                payload = esm.generate_binance_cancel_all_payload(
                    symbol=sym, api_key="test_key", secret_key=secret, recv_window=rw
                )
                ts = payload["params"]["timestamp"]
                expected_query = f"symbol={sym}&timestamp={ts}&recvWindow={rw}"
                expected_sig = hmac.new(
                    secret.encode("utf-8"), expected_query.encode("utf-8"), hashlib.sha256
                ).hexdigest()
                self.assertEqual(payload["params"]["signature"], expected_sig)


class TestEmergencyShutdownPipelineAdversarial(unittest.TestCase):
    """Stress-test end-to-end 4-stage emergency shutdown execution and latencies."""

    def test_full_pipeline_contract_and_latency(self):
        """Verify all 4 stages execute correctly and total execution time is under 100ms."""
        reason = "TEST_ADVERSARIAL_CIRCUIT_BREAKER_INVOCATION: Feed latency 1250ms breached 800ms"
        symbol = "BTCUSDT"

        t0 = time.perf_counter()
        result = esm.execute_emergency_shutdown(reason=reason, symbol=symbol, mock=True)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        # Assert status and reason
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["reason"], reason)
        self.assertEqual(result["symbol"], symbol)

        # Stage 1: Redis Kill Switch Contract
        redis_dict = result["redis_flag_set"]
        self.assertIn("hft:emergency:kill_switch_active", redis_dict)
        self.assertEqual(redis_dict["hft:emergency:kill_switch_active"], "1")

        # Stage 2: Binance Purge Contract
        purge = result["binance_purge_payload"]
        self.assertEqual(purge["method"], "DELETE")
        self.assertEqual(purge["params"]["symbol"], symbol)
        self.assertTrue(len(purge["params"]["signature"]) == 64)

        # Stage 3: Engine Halt Signal Contract
        halt = result["engine_halt_signal"]
        self.assertEqual(halt["action"], "HALT_ALL_WORKERS")
        self.assertEqual(halt["reason"], reason)

        # Stage 4: Telegram Alert Contract
        alert = result["telegram_alert"]
        self.assertIn("CONTINUITY HFT EMERGENCY KILL SWITCH ACTIVATED", alert)
        self.assertIn(symbol, alert)

        # Latency requirement: In mock mode, the pipeline must complete in < 100ms
        self.assertLess(elapsed_ms, 100.0, f"Shutdown execution took too long: {elapsed_ms:.2f}ms")

    def test_cloudevent_context_parser_robustness(self):
        """Verify CloudEvent parser handles various incident payloads gracefully."""
        # Test Case 1: Plain dictionary
        event_dict = {"reason": "LATENCY_SPIKE_950MS", "symbol": "ETHUSDT", "mock": True}
        reason, sym, _, mock, is_health = esm.extract_incident_context(event_dict)
        self.assertEqual(reason, "LATENCY_SPIKE_950MS")
        self.assertEqual(sym, "ETHUSDT")
        self.assertTrue(mock)
        self.assertFalse(is_health)

        # Test Case 2: Health check request
        class MockHealthRequest:
            path = "/health"
            method = "GET"
            args = {}
            def get_json(self, silent=True):
                return {}

        reason_h, _, _, _, is_health_probe = esm.extract_incident_context(MockHealthRequest())
        self.assertTrue(is_health_probe)
        self.assertEqual(reason_h, "HEALTH_CHECK")


class TestSafetyOrchestrationTerraformInvariants(unittest.TestCase):
    """Verify Terraform declarations and architectural invariants for Milestone 4."""

    @classmethod
    def setUpClass(cls):
        cls.safety_main_tf = (PROJECT_ROOT / "modules" / "safety_orchestration" / "main.tf").read_text(encoding="utf-8")
        cls.safety_vars_tf = (PROJECT_ROOT / "modules" / "safety_orchestration" / "variables.tf").read_text(encoding="utf-8")
        cls.safety_outputs_tf = (PROJECT_ROOT / "modules" / "safety_orchestration" / "outputs.tf").read_text(encoding="utf-8")
        cls.root_main_tf = (PROJECT_ROOT / "main.tf").read_text(encoding="utf-8")
        cls.root_vars_tf = (PROJECT_ROOT / "variables.tf").read_text(encoding="utf-8")
        cls.root_outputs_tf = (PROJECT_ROOT / "outputs.tf").read_text(encoding="utf-8")

    def test_eventarc_trigger_wiring(self):
        """Verify EventArc trigger is configured with Pub/Sub messagePublished and points to Cloud Run / Function."""
        self.assertIn('resource "google_eventarc_trigger" "emergency_shutdown"', self.safety_main_tf)
        self.assertIn('value     = "google.cloud.pubsub.topic.v1.messagePublished"', self.safety_main_tf)
        self.assertIn('cloud_run_service', self.safety_main_tf)
        self.assertIn('topic = var.safety_alerts_topic_id', self.safety_main_tf)

    def test_monitoring_alert_policies_declarations(self):
        """Verify Cloud Monitoring alert policies exist for Latency (>800ms) and API errors (429/418)."""
        self.assertIn('resource "google_monitoring_alert_policy" "latency_spike"', self.safety_main_tf)
        self.assertIn('threshold_value = var.latency_threshold_ms', self.safety_main_tf)
        self.assertIn('resource "google_monitoring_alert_policy" "api_errors"', self.safety_main_tf)
        self.assertIn('resource "google_monitoring_notification_channel" "pubsub_safety"', self.safety_main_tf)

    def test_serverless_vpc_connector_declared(self):
        """Verify Serverless VPC Access connector resource is declared for Redis private connectivity."""
        self.assertIn('resource "google_vpc_access_connector" "serverless_connector"', self.safety_main_tf)
        self.assertIn('vpc_connector', self.safety_main_tf)

    def test_root_module_wiring_active(self):
        """Verify root main.tf active wiring of safety_orchestration module."""
        self.assertIn('module "safety_orchestration"', self.root_main_tf)
        # Verify it is not commented out
        self.assertNotIn('# module "safety_orchestration"', self.root_main_tf)
        self.assertIn('emergency_shutdown_sa_email = module.iam.emergency_shutdown_sa_email', self.root_main_tf)
        self.assertIn('safety_alerts_topic_id = module.pubsub.safety_alerts_topic_id', self.root_main_tf)
        self.assertIn('redis_host           = module.storage.redis_host', self.root_main_tf)


if __name__ == "__main__":
    unittest.main()
