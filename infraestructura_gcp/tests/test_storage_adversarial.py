r"""
CONTINUITY HFT GCP - Empirical Adversarial Challenge Test Suite for Storage & Stream Processing (Milestone 3).
Target: C:\Users\alanr\teamwork_projects\hft_gcp_architecture\tests\test_storage_adversarial.py

Adversarial test verification scope:
1. Bigtable reverse-timestamp row key mathematical invariants & ordering bounds.
2. Bigtable schema consistency, SSD enforcement, column families ('t', 'q', 'm'), and GC retention policies.
3. Cloud Memorystore Redis Standard HA tier, transit encryption, AUTH, volatile-lru eviction immunity, and kill-switch contract.
4. Private Service Access peering dependency race prevention (depends_on).
5. Dataflow streaming engine security (WORKER_IP_PRIVATE) and performance configuration (Runner v2, Streaming Engine).
6. Root module integration, outputs export, and Terraform CLI validation.
"""

import os
import re
import subprocess
import time
import unittest
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STORAGE_DIR = PROJECT_ROOT / "modules" / "storage"
DATAFLOW_DIR = PROJECT_ROOT / "modules" / "dataflow"
ROOT_MAIN_TF = PROJECT_ROOT / "main.tf"
ROOT_OUTPUTS_TF = PROJECT_ROOT / "outputs.tf"
ROOT_VARS_TF = PROJECT_ROOT / "variables.tf"

BIGTABLE_TF = STORAGE_DIR / "bigtable.tf"
REDIS_TF = STORAGE_DIR / "redis.tf"
STORAGE_VARS_TF = STORAGE_DIR / "variables.tf"
STORAGE_OUTPUTS_TF = STORAGE_DIR / "outputs.tf"

DATAFLOW_MAIN_TF = DATAFLOW_DIR / "main.tf"
DATAFLOW_VARS_TF = DATAFLOW_DIR / "variables.tf"
DATAFLOW_OUTPUTS_TF = DATAFLOW_DIR / "outputs.tf"
BEAM_PROCESSOR_PY = DATAFLOW_DIR / "beam_stream_processor.py"

LONG_MAX = 9223372036854775807  # Java Long.MAX_VALUE / 64-bit signed int max
EMERGENCY_REDIS_KEY = "hft:emergency:kill_switch_active"


def format_row_key(symbol: str, timestamp_micros: int, seq_id: int) -> str:
    inverted_ts = LONG_MAX - timestamp_micros
    return f"{symbol}#{inverted_ts:019d}#{seq_id:010d}"


class TestBigtableReverseTimestampAdversarial(unittest.TestCase):
    """Adversarial stress-testing of Bigtable reverse timestamp row key formatting and ordering."""

    def test_monotonic_reverse_chronological_ordering(self):
        """Assert that strictly increasing timestamps produce strictly decreasing (reverse) row keys."""
        symbol = "BTCUSDT"
        # Spanning microsecond differences across a wide spectrum
        timestamps = [
            1,
            1000,
            1_000_000,
            1_700_000_000_000_000,  # ~ Nov 2023
            1_728_000_000_000_000,  # ~ Oct 2024
            1_760_000_000_000_000,  # ~ Oct 2025
            1_770_000_000_000_000,  # Current era
            LONG_MAX - 1000,
            LONG_MAX,
        ]

        keys = [format_row_key(symbol, ts, 0) for ts in timestamps]

        # In Bigtable, row scans read lexicographically ascending.
        # Newer timestamp -> smaller inverted_ts -> smaller row key -> read first!
        for i in range(len(keys) - 1):
            ts_older = timestamps[i]
            ts_newer = timestamps[i + 1]
            key_older = keys[i]
            key_newer = keys[i + 1]

            self.assertLess(
                key_newer,
                key_older,
                f"Ordering violation! Newer timestamp {ts_newer} produced key {key_newer} "
                f"which is not < older key {key_older} (ts={ts_older})",
            )

    def test_fixed_width_padding_invariance(self):
        """Assert that all inverted timestamps are exactly 19 digits and seq_ids are 10 digits."""
        test_cases = [
            (0, 0),
            (1, 1),
            (999, 999),
            (1_700_000_000_000_000, 100_000),
            (LONG_MAX - 1, 9_999_999_999),
            (LONG_MAX, 0),
        ]

        for ts, seq in test_cases:
            key = format_row_key("SOLUSDT", ts, seq)
            parts = key.split("#")
            self.assertEqual(len(parts), 3, f"Key {key} does not have exactly 3 parts separated by '#'")
            symbol, inverted_str, seq_str = parts

            self.assertEqual(symbol, "SOLUSDT")
            self.assertEqual(
                len(inverted_str),
                19,
                f"Inverted timestamp string '{inverted_str}' does not have fixed length 19 (ts={ts})",
            )
            self.assertEqual(
                len(seq_str),
                10,
                f"Sequence ID string '{seq_str}' does not have fixed length 10 (seq={seq})",
            )
            self.assertTrue(inverted_str.isdigit())
            self.assertTrue(seq_str.isdigit())

    def test_symbol_prefix_isolation(self):
        """Assert that row keys for different symbols sort into strictly disjoint prefix partitions."""
        symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
        ts_list = [1_700_000_000_000_000, 1_750_000_000_000_000]

        all_keys = []
        for sym in symbols:
            for ts in ts_list:
                all_keys.append(format_row_key(sym, ts, 1))

        sorted_keys = sorted(all_keys)

        # Check prefix clustering
        btc_keys = [k for k in sorted_keys if k.startswith("BTCUSDT#")]
        eth_keys = [k for k in sorted_keys if k.startswith("ETHUSDT#")]
        sol_keys = [k for k in sorted_keys if k.startswith("SOLUSDT#")]

        self.assertEqual(len(btc_keys), 2)
        self.assertEqual(len(eth_keys), 2)
        self.assertEqual(len(sol_keys), 2)

        # All BTC keys must precede all ETH keys, which precede SOL keys
        self.assertLess(max(btc_keys), min(eth_keys))
        self.assertLess(max(eth_keys), min(sol_keys))


class TestBigtableSchemaConsistencyAndGCPolicies(unittest.TestCase):
    """Adversarially verify Bigtable SSD enforcement, column families, and GC retention policies in HCL."""

    @classmethod
    def setUpClass(cls):
        cls.bigtable_tf = BIGTABLE_TF.read_text(encoding="utf-8")
        cls.vars_tf = STORAGE_VARS_TF.read_text(encoding="utf-8")

    def test_strict_ssd_storage_type_enforcement(self):
        """Assert that storage_type is strictly 'SSD' with zero HDD allowance."""
        storage_type_match = re.search(
            r'cluster\s*\{[^}]*storage_type\s*=\s*["\']([^"\']+)["\']',
            self.bigtable_tf,
            re.DOTALL,
        )
        self.assertIsNotNone(storage_type_match, "Bigtable cluster block missing storage_type declaration")
        storage_type = storage_type_match.group(1)
        self.assertEqual(
            storage_type,
            "SSD",
            f"CRITICAL LATENCY VIOLATION: Bigtable storage_type is '{storage_type}', must be strictly 'SSD'!",
        )

        # Negative check: HDD must not be present
        self.assertNotIn('"HDD"', self.bigtable_tf, "HDD storage type found in bigtable.tf")

    def test_column_families_t_q_m_declared(self):
        """Assert that market_ticks table explicitly creates column families 't', 'q', and 'm'."""
        table_block_match = re.search(
            r'resource\s+"google_bigtable_table"\s+"market_ticks"\s*\{(.*?)\n\}',
            self.bigtable_tf,
            re.DOTALL,
        )
        self.assertIsNotNone(table_block_match, "google_bigtable_table.market_ticks resource not found")
        table_body = table_block_match.group(1)

        families = re.findall(r'family\s*=\s*["\']([^"\']+)["\']', table_body)
        self.assertIn("t", families, "Column family 't' (trades) missing from market_ticks table")
        self.assertIn("q", families, "Column family 'q' (quotes) missing from market_ticks table")
        self.assertIn("m", families, "Column family 'm' (metrics) missing from market_ticks table")

    def test_gc_policies_durations_and_abandon_policy(self):
        """Assert that GC policies exist for 't' (30d), 'q' (7d), 'm' (14d) with deletion_policy ABANDON."""
        for fam, expected_default in [("trades", "720h"), ("quotes", "168h"), ("metrics", "336h")]:
            gc_match = re.search(
                rf'resource\s+"google_bigtable_gc_policy"\s+"{fam}_gc"\s*\{{([^}}]+)\}}',
                self.bigtable_tf,
                re.DOTALL,
            )
            self.assertIsNotNone(gc_match, f"GC policy resource '{fam}_gc' not found in bigtable.tf")
            gc_body = gc_match.group(1)

            # Check deletion_policy = "ABANDON"
            self.assertRegex(
                gc_body,
                r'deletion_policy\s*=\s*["\']ABANDON["\']',
                f"GC policy '{fam}_gc' must specify deletion_policy = 'ABANDON'",
            )

        # Verify defaults in variables.tf
        self.assertIn('"720h"', self.vars_tf, "gc_trades_max_age default '720h' missing")
        self.assertIn('"168h"', self.vars_tf, "gc_quotes_max_age default '168h' missing")
        self.assertIn('"336h"', self.vars_tf, "gc_metrics_max_age default '336h' missing")

    def test_bigtable_iam_least_privilege_bindings(self):
        """Assert that roles/bigtable.user is granted to trading engine and dataflow worker."""
        engine_binding = re.search(
            r'resource\s+"google_bigtable_instance_iam_member"\s+"hft_engine_user"',
            self.bigtable_tf,
        )
        self.assertIsNotNone(engine_binding, "IAM member 'hft_engine_user' not found in bigtable.tf")

        dataflow_binding = re.search(
            r'resource\s+"google_bigtable_instance_iam_member"\s+"dataflow_worker_user"',
            self.bigtable_tf,
        )
        self.assertIsNotNone(dataflow_binding, "IAM member 'dataflow_worker_user' not found in bigtable.tf")

        # Verify role is bigtable.user and NOT bigtable.admin
        roles = re.findall(r'role\s*=\s*["\']([^"\']+)["\']', self.bigtable_tf)
        for r in roles:
            self.assertEqual(r, "roles/bigtable.user", f"Unexpected broad Bigtable role '{r}' granted")


class TestRedisKillSwitchAndStateCacheAdversarial(unittest.TestCase):
    """Adversarial stress-testing of Redis kill-switch contract, HA tier, and peering dependencies."""

    @classmethod
    def setUpClass(cls):
        cls.redis_tf = REDIS_TF.read_text(encoding="utf-8")
        cls.vars_tf = STORAGE_VARS_TF.read_text(encoding="utf-8")

    def test_redis_standard_ha_tier_enforcement(self):
        """Assert that Redis tier default is STANDARD_HA (sub-second failover replica)."""
        tier_match = re.search(
            r'variable\s+"redis_tier"\s*\{[^}]*default\s*=\s*["\']([^"\']+)["\']',
            self.vars_tf,
            re.DOTALL,
        )
        self.assertIsNotNone(tier_match, "redis_tier variable not found in variables.tf")
        tier = tier_match.group(1)
        self.assertEqual(
            tier,
            "STANDARD_HA",
            f"Redis tier is '{tier}', must be 'STANDARD_HA' for production fault-tolerance",
        )

    def test_redis_psa_dependency_race_prevention(self):
        """Assert that google_redis_instance.hft_redis declares depends_on with PSA connection."""
        depends_match = re.search(
            r'resource\s+"google_redis_instance"\s+"hft_redis"\s*\{[^}]*depends_on\s*=\s*\[([^\]]+)\]',
            self.redis_tf,
            re.DOTALL,
        )
        self.assertIsNotNone(
            depends_match,
            "CRITICAL: depends_on block missing from google_redis_instance.hft_redis!",
        )
        dep_content = depends_match.group(1)
        self.assertIn(
            "var.private_service_access_connection",
            dep_content,
            "CRITICAL: depends_on must include var.private_service_access_connection to prevent API 400 race condition!",
        )

    def test_redis_volatile_lru_kill_switch_immunity(self):
        """Assert that maxmemory-policy is volatile-lru, guaranteeing zero-TTL kill switch cannot be evicted."""
        configs_match = re.search(
            r'variable\s+"redis_configs"\s*\{[^}]*maxmemory-policy\s*=\s*["\']([^"\']+)["\']',
            self.vars_tf,
            re.DOTALL,
        )
        self.assertIsNotNone(configs_match, "redis_configs with maxmemory-policy not found")
        policy = configs_match.group(1)
        self.assertEqual(
            policy,
            "volatile-lru",
            f"Eviction policy '{policy}' could evict non-expiring emergency kill switch key! Must be 'volatile-lru'",
        )

    def test_redis_security_auth_and_transit_encryption(self):
        """Assert that auth_enabled is true and transit_encryption_mode is SERVER_AUTHENTICATION."""
        self.assertRegex(
            self.vars_tf,
            r'variable\s+"redis_auth_enabled"\s*\{[^}]*default\s*=\s*true',
            "redis_auth_enabled must default to true",
        )
        self.assertRegex(
            self.vars_tf,
            r'variable\s+"redis_transit_encryption_mode"\s*\{[^}]*default\s*=\s*["\']SERVER_AUTHENTICATION["\']',
            "redis_transit_encryption_mode must default to SERVER_AUTHENTICATION",
        )

    def test_kill_switch_state_transition_and_fail_closed_contract(self):
        """Adversarially simulate kill-switch state transitions and fail-closed logic under network disconnection."""
        # Simulated state cache
        cache = {EMERGENCY_REDIS_KEY: "0"}

        def is_trading_allowed(c: dict) -> bool:
            # Protocol rule: if key is absent or '0', allowed. If '1', HALT.
            return c.get(EMERGENCY_REDIS_KEY, "0") != "1"

        def fail_closed_check(connection_healthy: bool, c: dict) -> Tuple[bool, str]:
            if not connection_healthy:
                # Under network partition / Redis loss, trading MUST fail closed (halt)
                return False, "FAIL_CLOSED: REDIS_UNREACHABLE"
            if c.get(EMERGENCY_REDIS_KEY) == "1":
                return False, "HALTED: KILL_SWITCH_ACTIVE"
            return True, "TRADING_ACTIVE"

        # 1. Normal state
        allowed, msg = fail_closed_check(True, cache)
        self.assertTrue(allowed)
        self.assertEqual(msg, "TRADING_ACTIVE")

        # 2. Emergency Trigger
        cache[EMERGENCY_REDIS_KEY] = "1"
        allowed, msg = fail_closed_check(True, cache)
        self.assertFalse(allowed)
        self.assertEqual(msg, "HALTED: KILL_SWITCH_ACTIVE")

        # 3. Connection drop (Simulated Redis outage) -> Fail Closed
        allowed, msg = fail_closed_check(False, cache)
        self.assertFalse(allowed)
        self.assertEqual(msg, "FAIL_CLOSED: REDIS_UNREACHABLE")


class TestDataflowStreamingAdversarial(unittest.TestCase):
    """Adversarially verify Dataflow stream processing worker isolation and dual-sink pipeline."""

    @classmethod
    def setUpClass(cls):
        cls.dataflow_tf = DATAFLOW_MAIN_TF.read_text(encoding="utf-8")
        cls.beam_py = BEAM_PROCESSOR_PY.read_text(encoding="utf-8")

    def test_dataflow_worker_private_ip_enforcement(self):
        """Assert that ip_configuration is WORKER_IP_PRIVATE (0 public external IPs on workers)."""
        ip_match = re.search(
            r'ip_configuration\s*=\s*["\']([^"\']+)["\']',
            self.dataflow_tf,
        )
        self.assertIsNotNone(ip_match, "ip_configuration missing from google_dataflow_job")
        ip_conf = ip_match.group(1)
        self.assertEqual(
            ip_conf,
            "WORKER_IP_PRIVATE",
            f"SECURITY VIOLATION: Dataflow ip_configuration is '{ip_conf}', must be 'WORKER_IP_PRIVATE'!",
        )

    def test_dataflow_streaming_engine_and_runner_v2(self):
        """Assert that enable_streaming_engine and runner_v2 are enabled for sub-5ms processing."""
        self.assertIn("enable_streaming_engine = var.enable_streaming_engine", self.dataflow_tf)
        self.assertIn('additional_experiments = var.use_runner_v2 ? ["use_runner_v2"] : []', self.dataflow_tf)

    def test_beam_pipeline_dual_sink_schema_consistency(self):
        """Assert that Apache Beam pipeline writes to both Bigtable column families ('t', 'm') and Redis."""
        self.assertIn('row.set_cell("t", b"price"', self.beam_py)
        self.assertIn('row.set_cell("t", b"quantity"', self.beam_py)
        self.assertIn('row.set_cell("m", b"feed_latency_us"', self.beam_py)
        self.assertIn("hft:market:latest_tick:", self.beam_py)


class TestRootTerraformIntegrationAndValidation(unittest.TestCase):
    """Verify root main.tf wiring, outputs export, and execute live terraform validate."""

    def test_root_main_wires_storage_and_dataflow_modules(self):
        root_main = ROOT_MAIN_TF.read_text(encoding="utf-8")
        self.assertIn('module "storage"', root_main)
        self.assertIn('module "dataflow"', root_main)

    def test_root_outputs_export_storage_and_dataflow_contracts(self):
        root_outputs = ROOT_OUTPUTS_TF.read_text(encoding="utf-8")
        required_outputs = [
            "bigtable_instance_id",
            "bigtable_market_ticks_table_id",
            "bigtable_column_families",
            "bigtable_row_key_spec",
            "redis_instance_id",
            "redis_host",
            "redis_auth_string",
            "dataflow_staging_bucket_url",
            "dataflow_job_id",
        ]
        for out in required_outputs:
            self.assertIn(f'output "{out}"', root_outputs, f"Missing required output: {out}")

    def test_terraform_validate_cli_execution(self):
        """Run 'terraform validate' and assert exit code 0."""
        proc = subprocess.run(
            ["terraform", "validate"],
            cwd=str(PROJECT_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(
            proc.returncode,
            0,
            f"terraform validate failed with code {proc.returncode}:\n{proc.stderr}\n{proc.stdout}",
        )
        self.assertIn("The configuration is valid.", proc.stdout)


if __name__ == "__main__":
    unittest.main()
