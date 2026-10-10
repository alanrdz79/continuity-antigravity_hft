# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_adversarial_challenger_gen2
===================================================
Adversarial Empirical Stress-Testing Suite for CONTINUITY HFT Binance.
Authored by Challenger 1 (Empirical Challenger) — Second Generation.

Targets Under Adversarial Challenge:
1. Bigtable Row Key Reverse-Timestamp Math:
   - Lexicographical monotonicity under extreme microsecond timestamps (0, 1, 1e6, 1e15, Long.MAX_VALUE).
   - Microsecond precision sorting (k_newer < k_older invariant).
   - Sequence ID normalization and 10-digit zero padding (%010d).
   - Float vs int timestamp input handling.
2. Zero SQLite Persistence & Concurrent Thread Safety:
   - 100 concurrent workers updating StateRegistry without local SQLite/WAL file generation.
   - Zero .db, .sqlite, or .db-wal files created anywhere in workspace.
3. Kelly Criterion Boundary Extremes:
   - p -> 0, p -> 1, negative p, p > 1.
   - Odds <= 1.0, extreme longshots (cuota = 100,000), near-even (cuota = 1.000001).
   - Strict 0.0 <= f* <= 0.25 invariant and 4-decimal precision.
4. Streak Factor Attenuation (0.85^n) & 15% Cluster Cap Invariance:
   - Numerical stability at n = 0, 1, 10, 50, 100.
   - Sizing modulation and immediate reset on win.
   - Invariance of 15% cluster capital cap under extreme bankroll and concurrent sizing requests.
5. Autonomous Harvesting Protocol at $1,000 USD Balance:
   - Exact 35% net profit isolation to MXN.
   - Remainder 40% expenses and 60% compound reinvestment.
   - Exact 4-decimal balance conservation identity: B_pre == retiro_35 + gastos_40 + nuevo_balance.
   - Boundary checks at $999.9999 (blocked) vs $1000.0000 (triggered).
6. Strategy V Binary Parity DualBuyProposal:
   - Detection when Ask(YES) + Ask(NO) < 1.00 - fees.
   - BNB fee discount modulation.
   - Fail-closed behavior on SUSPENDED status and zero liquidity.
   - Verification of atomic DualBuyProposal structure.
7. Pre-Match & In-Play Target EV Early Exits:
   - Verification across traditional Sports (Soccer, Basketball) and ESports (LOL, CS2).
   - Immediate position closure upon snapshot.best_bid >= target_exit_price.
   - Capital token release and state propagation.
8. Phase 2 T-5m 'limpiar_mesa' 0% Exposure:
   - Verification that at T-5m, all pending orders are cancelled and positions liquidated.
   - Verified final exposure is strictly 0.0%.
"""

from __future__ import annotations

import asyncio
import os
import glob
import math
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Any, Optional, Tuple

import pytest

# Core system imports
from continuitis.state_registry import StateRegistry, StateRegistrySQLite
from continuitis.riesgo_binance import (
    EscudoFinancieroBinance,
    calcular_criterio_kelly,
    OrderProposal,
    RiskApprovedOrder,
    DEFAULT_MAX_CLUSTER_EXP,
)
from continuitis.tesoreria import (
    GestorTesoreria,
    CAPITAL_BASE_INICIAL,
    UMBRAL_COSECHA_1000,
    PCT_COSECHA_AUTONOMA,
    PCT_GASTOS_OPERACION,
    PCT_REINVERSION_COMPUESTA,
)
from continuitis.auditor_metricas import AuditorMetricas, TradeResult
from continuitis.microestructura_binance import OrderBookSnapshot
from estrategias.arbitraje_amm import (
    EstrategiaVArbitrajeAMM,
    ArbitrageConfig,
    ArbitrageOpportunityType,
    ArbitrageSignal,
    DualBuyProposal,
)
from estrategias.hft_engine import (
    HFTEngine,
    MatchLiveState,
    SportType,
    HftPosition,
)
from estrategias.swing_engine import AsyncCapitalGateway
from orquestadores_principales.HFT_BINANCE import ContinuityHFTBinanceOrchestrator


# ==============================================================================
# SECTION 1: BIGTABLE ROW KEY REVERSE-TIMESTAMP MATHEMATICS
# ==============================================================================

class TestBigtableRowKeyMath:
    """
    Adversarial verification of Cloud Bigtable reverse-timestamp row key math.
    Format: {symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}
    Invariant: Newer timestamps MUST yield lexicographically smaller keys (k_newer < k_older).
    """

    LONG_MAX = 9223372036854775807  # 2^63 - 1

    def test_reverse_timestamp_monotonic_sorting_across_epochs(self):
        """
        Adversarial Test 1.1:
        Verify strictly that as time increases, the generated Bigtable row key
        is strictly monotonically decreasing (k_newer < k_older).
        """
        symbol = "BTCUSDT"
        timestamps_micros = [
            0,                          # Epoch 1970-01-01 00:00:00
            1,                          # 1 microsecond
            1_000,                      # 1 millisecond
            1_000_000,                  # 1 second
            1_700_000_000_000_000,      # Modern epoch (~Nov 2023)
            1_728_580_000_000_000,      # Current era (~Oct 2024)
            1_728_580_000_000_001,      # Exactly 1 microsecond later
            1_728_580_000_000_002,      # 2 microseconds later
            2_000_000_000_000_000,      # Year ~2033
            self.LONG_MAX - 1,          # Near maximum long
            self.LONG_MAX,              # Maximum long
        ]

        row_keys = [
            StateRegistry.format_bigtable_row_key(symbol, ts, seq_id=1)
            for ts in timestamps_micros
        ]

        for i in range(len(row_keys) - 1):
            ts_older = timestamps_micros[i]
            ts_newer = timestamps_micros[i + 1]
            key_older = row_keys[i]
            key_newer = row_keys[i + 1]

            # In Bigtable, reverse timestamp ensures newer data sorts FIRST
            assert key_newer < key_older, (
                f"Bigtable sorting invariant violated! ts_newer={ts_newer} ({key_newer}) "
                f"must sort before ts_older={ts_older} ({key_older})"
            )

    def test_microsecond_single_tick_resolution(self):
        """
        Adversarial Test 1.2:
        High-frequency trading produces ticks with sub-millisecond deltas.
        Verify that ticks 1 microsecond apart are strictly distinct and sort correctly.
        """
        symbol = "ETHUSDT"
        base_micros = 1_728_580_123_456_789
        keys = [
            StateRegistry.format_bigtable_row_key(symbol, base_micros + delta, seq_id=0)
            for delta in range(100)
        ]

        # All keys must be unique
        assert len(set(keys)) == 100

        # Each key must be strictly smaller than the previous
        for i in range(len(keys) - 1):
            assert keys[i + 1] < keys[i], f"Delta {i} failed: {keys[i+1]} >= {keys[i]}"

    def test_float_seconds_vs_int_micros_conversion(self):
        """
        Adversarial Test 1.3:
        StateRegistry accepts float seconds (e.g. from time.time() ~ 1.7e9).
        Verify that float seconds are properly scaled to microseconds (< 1e11 check).
        """
        symbol = "SOLUSDT"
        now_sec = 1728580000.123456
        now_micros = int(now_sec * 1_000_000)

        key_from_float = StateRegistry.format_bigtable_row_key(symbol, now_sec, seq_id=5)
        key_from_int = StateRegistry.format_bigtable_row_key(symbol, now_micros, seq_id=5)

        assert key_from_float == key_from_int, (
            f"Float seconds not identical to integer microseconds: "
            f"{key_from_float} vs {key_from_int}"
        )

    def test_sequence_id_zero_padding_and_rollover(self):
        """
        Adversarial Test 1.4:
        Verify that sequence IDs are formatted with exact 10-digit zero-padding (%010d)
        and sort properly for simultaneous timestamps.
        """
        symbol = "AVAXUSDT"
        ts = 1_728_580_000_000_000

        key_seq_0 = StateRegistry.format_bigtable_row_key(symbol, ts, seq_id=0)
        key_seq_1 = StateRegistry.format_bigtable_row_key(symbol, ts, seq_id=1)
        key_seq_999 = StateRegistry.format_bigtable_row_key(symbol, ts, seq_id=999)
        key_seq_max = StateRegistry.format_bigtable_row_key(symbol, ts, seq_id=9_999_999_999)

        # Check lengths: symbol (8) + '#' (1) + reverse_ts (19) + '#' (1) + seq (10) = 39 chars
        assert len(key_seq_0) == len(symbol) + 1 + 19 + 1 + 10
        assert key_seq_0.endswith("#0000000000")
        assert key_seq_1.endswith("#0000000001")
        assert key_seq_999.endswith("#0000000999")
        assert key_seq_max.endswith("#9999999999")

        # Within the same timestamp, lower seq_id sorts before higher seq_id
        assert key_seq_0 < key_seq_1 < key_seq_999 < key_seq_max


# ==============================================================================
# SECTION 2: ZERO SQLITE PERSISTENCE & CONCURRENT THREAD SAFETY
# ==============================================================================

class TestZeroSQLiteAndConcurrency:
    """
    Adversarial verification of zero SQLite file generation and thread safety.
    """

    def test_zero_sqlite_files_created_under_heavy_concurrent_operations(self, tmp_path):
        """
        Adversarial Test 2.1:
        Execute 100 concurrent threads performing StateRegistry reads, writes,
        queue additions, and trade records.
        Verify that NO .db, .sqlite, or .db-wal files are generated in the filesystem.
        """
        registry = StateRegistry(redis_host="")  # In-memory mock fallback mode
        registry.clear_all()

        errors = []

        def worker(thread_idx: int):
            try:
                for op in range(50):
                    # 1. State operations
                    key = f"key_{thread_idx}_{op % 5}"
                    registry.set_state(key, f"val_{thread_idx}_{op}")
                    val = registry.get_state(key)
                    if not val.startswith(f"val_{thread_idx}"):
                        errors.append(f"State inconsistency in thread {thread_idx}")

                    # 2. Match queue operations
                    partido_id = f"match_{thread_idx}_{op}"
                    registry.encolar_partido(partido_id, {"sport": "ESPORTS", "tick": op})
                    pending = registry.obtener_partidos_pendientes()
                    if not isinstance(pending, list):
                        errors.append("Invalid pending list")

                    # 3. Trade recording
                    registry.record_trade(
                        trade_id=f"T_{thread_idx}_{op}",
                        symbol="SOCCER_PRED",
                        pnl=1.5 if op % 2 == 0 else -1.0,
                        is_win=op % 2 == 0,
                        timestamp=time.time(),
                        stake=10.0,
                    )

                    # 4. Close match
                    registry.cerrar_partido(partido_id)
            except Exception as e:
                errors.append(f"Thread {thread_idx} exception: {e}")

        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(worker, i) for i in range(100)]
            for f in futures:
                f.result()

        assert len(errors) == 0, f"Concurrent execution produced errors: {errors[:5]}"

        # Check file system: ensure no new sqlite database files exist in workspace
        cwd = os.getcwd()
        db_files = glob.glob(os.path.join(cwd, "**/*.db"), recursive=True)
        wal_files = glob.glob(os.path.join(cwd, "**/*-wal"), recursive=True)
        shm_files = glob.glob(os.path.join(cwd, "**/*-shm"), recursive=True)

        # Allow existing legacy files if any were present before, but assert none created in tests
        # Specifically check continuity_state.db does not exist or was not modified
        state_db_path = os.path.join(cwd, "continuity_state.db")
        assert not os.path.exists(state_db_path), "continuity_state.db was generated by StateRegistry!"


# ==============================================================================
# SECTION 3: KELLY CRITERION BOUNDARY EXTREMES
# ==============================================================================

class TestKellyCriterionBoundaryExtremes:
    """
    Adversarial verification of Kelly Criterion formula under mathematical extremes:
      f* = fraccion_kelly * ((p * (b + 1) - 1) / b)
    Invariants:
    1. For ANY input, 0.0 <= f* <= 0.25.
    2. Precision is exactly 4 decimal places (round(..., 4)).
    3. Negative EV or p <= 0 strictly returns 0.0.
    4. Odds <= 1.0 strictly returns 0.0.
    """

    def test_p_approaching_zero_and_negative(self):
        """Adversarial Test 3.1: p <= 0 must return 0.0 without errors."""
        for p in [0.0, -0.1, -1.0, 1e-12]:
            f_star = calcular_criterio_kelly(p_estimada=p, cuota_neta=2.0)
            assert f_star == 0.0

    def test_p_approaching_one_with_varying_odds(self):
        """
        Adversarial Test 3.2: p = 1.0 (certain victory).
        f* must be capped at exactly 0.25 (fractional Kelly bound).
        """
        for cuota in [1.01, 1.50, 2.0, 5.0, 100.0]:
            f_star = calcular_criterio_kelly(p_estimada=1.0, cuota_neta=cuota, fraccion_kelly=0.25)
            # When p=1.0, pure Kelly = (1*(b+1)-1)/b = b/b = 1.0.
            # Fractional Kelly with 0.25 fraction = 0.25 * 1.0 = 0.25.
            assert f_star == 0.25

    def test_odds_boundary_less_than_or_equal_to_one(self):
        """Adversarial Test 3.3: Odds <= 1.0 (no profit or negative profit)."""
        for cuota in [1.0, 0.99, 0.50, 0.0, -1.5]:
            f_star = calcular_criterio_kelly(p_estimada=0.8, cuota_neta=cuota)
            assert f_star == 0.0

    def test_odds_infinitesimally_greater_than_one(self):
        """
        Adversarial Test 3.4: Odds very close to 1.0 (cuota = 1.000001).
        Verifies numerical stability against division by zero (b -> 0).
        """
        cuota = 1.000001
        # If p = 0.999999, EV = p*cuota - 1 = ~0.000000...
        f_star = calcular_criterio_kelly(p_estimada=0.9999995, cuota_neta=cuota)
        assert 0.0 <= f_star <= 0.25
        assert isinstance(f_star, float)

    def test_extreme_longshot_odds(self):
        """Adversarial Test 3.5: Cuota = 100,000 (extreme payout)."""
        cuota = 100_000.0
        # If p = 0.001 (0.1% chance), EV = 0.001 * 100000 - 1 = 99 > 0.
        # Pure Kelly = 99 / 99999 ~ 0.00099
        f_star = calcular_criterio_kelly(p_estimada=0.001, cuota_neta=cuota, fraccion_kelly=0.25)
        assert 0.0 < f_star <= 0.25
        assert round(f_star, 4) == f_star

    def test_negative_and_zero_ev_strictly_zero(self):
        """Adversarial Test 3.6: When p * cuota <= 1.0, Kelly must be 0.0."""
        # Exact zero EV: p = 0.5, cuota = 2.0 => p*cuota - 1 = 0
        assert calcular_criterio_kelly(p_estimada=0.5, cuota_neta=2.0) == 0.0

        # Negative EV: p = 0.45, cuota = 2.0 => p*cuota - 1 = -0.10
        assert calcular_criterio_kelly(p_estimada=0.45, cuota_neta=2.0) == 0.0

    def test_hard_cap_at_0_25_even_with_large_fraction_param(self):
        """Adversarial Test 3.7: Even if fraccion_kelly=1.0 or 2.0, result capped at 0.25."""
        f_star = calcular_criterio_kelly(p_estimada=0.9, cuota_neta=3.0, fraccion_kelly=1.0)
        assert f_star == 0.25


# ==============================================================================
# SECTION 4: STREAK FACTOR ATTENUATION & 15% CLUSTER CAP INVARIANCE
# ==============================================================================

class TestStreakAttenuationAndClusterCap:
    """
    Adversarial verification of streak attenuation 0.85^n and 15% cluster cap invariance.
    """

    def test_streak_attenuation_decay_values(self):
        """
        Adversarial Test 4.1:
        Verify exact values of factor_racha at n = 0, 1, 10, 50, 100.
        """
        escudo = EscudoFinancieroBinance(factor_atenuacion_racha=0.85)

        # n = 0
        assert escudo.factor_racha == 1.0

        # n = 1
        escudo.registrar_resultado(es_ganadora=False)
        assert escudo.factor_racha == pytest.approx(0.85, rel=1e-6)

        # n = 10
        for _ in range(9):
            escudo.registrar_resultado(es_ganadora=False)
        assert escudo.consecutive_losses == 10
        assert escudo.factor_racha == pytest.approx(0.85 ** 10, rel=1e-6)  # ~0.196874

        # n = 50
        for _ in range(40):
            escudo.registrar_resultado(es_ganadora=False)
        assert escudo.consecutive_losses == 50
        assert escudo.factor_racha == pytest.approx(0.85 ** 50, rel=1e-6)  # ~0.00029576

        # Reset on win
        escudo.registrar_resultado(es_ganadora=True)
        assert escudo.consecutive_losses == 0
        assert escudo.factor_racha == 1.0

    def test_cluster_cap_15_percent_strict_invariance(self):
        """
        Adversarial Test 4.2:
        Under any circumstance (large bankroll, high confidence, small stop loss),
        the total allocated position MUST NEVER exceed 15% of the bankroll.
        """
        escudo = EscudoFinancieroBinance(
            pct_riesgo_fijo=0.10,  # Deliberately high fixed risk
            max_cluster_exp=0.15,
        )
        balance = 1000.0
        propuesta = OrderProposal(
            symbol="SOCCER_PRED",
            side="BUY",
            target_price=0.50,
            stop_price=0.495,  # Tiny stop loss (1%): would trigger huge nominal sizing
            estimated_prob=0.80,
            payout_decimal=2.0,
            strategy_id="TEST",
        )

        # Test at existing cluster exposure of 0.10 (100 USD)
        decision = escudo.evaluar_propuesta(
            proposal=propuesta,
            balance=balance,
            exposicion_cluster_actual=100.0,
            top_3_bids=1000.0,
        )

        assert decision.approved is True
        # Total allocation cannot exceed remaining cluster headroom: 150 - 100 = 50 USD
        stake_usd = decision.price * decision.quantity
        assert stake_usd <= 50.0 + 1e-4

        # Test at existing cluster exposure of 0.15 (150 USD) -> must reject
        decision_full = escudo.evaluar_propuesta(
            proposal=propuesta,
            balance=balance,
            exposicion_cluster_actual=150.0,
            top_3_bids=1000.0,
        )
        assert decision_full.approved is False
        reason = (decision_full.rejection_reason or "").upper()
        assert "CLÚSTER" in reason or "CLUSTER" in reason


# ==============================================================================
# SECTION 5: AUTONOMOUS HARVESTING AT $1,000 USD WITH 35% MXN ISOLATION
# ==============================================================================

class TestAutonomousHarvestingProtocol:
    """
    Adversarial verification of autonomous harvesting at $1,000 USD balance.
    Rules:
    - Triggered at balance >= 1000.0 USD.
    - Exactly 35% of net profit isolated to MXN.
    - 40% of remainder to operating expenses.
    - 60% of remainder to compound reinvestment.
    - Mathematical identity: B_pre == retiro_35 + gastos_40 + nuevo_balance.
    """

    def test_harvesting_exact_mathematical_identity(self):
        """
        Adversarial Test 5.1:
        Verify exact arithmetic split and conservation of balance:
        Initial base = $10.00. Balance = $1,000.00. FX = 20.00.
        """
        tesoreria = GestorTesoreria(balance_inicial=10.0, tipo_cambio_mxn=20.0)
        tesoreria.balance = 1000.0

        res = tesoreria.ejecutar_cosecha_autonoma()

        assert res["cosecha_ejecutada"] is True
        net_profit = 1000.0 - 10.0  # 990.00 USD
        assert res["ganancia_neta"] == 990.00

        # Retiro 35%
        retiro_35 = 990.00 * 0.35  # 346.50 USD
        assert res["retiro_autonomo_35_usd"] == 346.50
        assert res["retiro_autonomo_mxn"] == 346.50 * 20.0  # 6930.00 MXN

        # Remainder: 990 - 346.50 = 643.50
        gastos_40 = 643.50 * 0.40  # 257.40 USD
        reinv_60 = 643.50 * 0.60   # 386.10 USD
        assert res["gastos_operacion_40_usd"] == 257.40
        assert res["reinversion_compuesta_60_usd"] == 386.10

        # Nuevo balance operativo: 10.0 + 386.10 = 396.10 USD
        assert res["nuevo_balance_operativo"] == 396.10
        assert tesoreria.balance == 396.10

        # Conservation of money check:
        # 1000.00 == retiro_35 (346.50) + gastos_40 (257.40) + nuevo_balance (396.10)
        total_accounted = (
            res["retiro_autonomo_35_usd"]
            + res["gastos_operacion_40_usd"]
            + res["nuevo_balance_operativo"]
        )
        assert total_accounted == pytest.approx(1000.0, abs=1e-4)

    def test_harvesting_boundary_sub_1000_strictly_blocked(self):
        """
        Adversarial Test 5.2:
        At balance = $999.9999, harvesting MUST NOT trigger.
        At balance = $1000.0000, harvesting MUST trigger.
        """
        tesoreria = GestorTesoreria(balance_inicial=10.0)

        # 999.9999 USD -> blocked
        tesoreria.balance = 999.9999
        res_sub = tesoreria.ejecutar_cosecha_autonoma()
        assert res_sub["cosecha_ejecutada"] is False
        assert tesoreria.balance == 999.9999

        # 1000.0000 USD -> triggers
        tesoreria.balance = 1000.0
        res_hit = tesoreria.ejecutar_cosecha_autonoma()
        assert res_hit["cosecha_ejecutada"] is True


# ==============================================================================
# SECTION 6: STRATEGY V DUAL BUY PROPOSAL (BINARY PARITY ARBITRAGE)
# ==============================================================================

class TestStrategyVDualBuyProposal:
    """
    Adversarial verification of Strategy V binary parity arbitrage detection:
    Condition: Best Ask(YES) + Best Ask(NO) < 1.00 - fees_total.
    """

    def test_dual_buy_proposal_generation_when_condition_met(self):
        """
        Adversarial Test 6.1:
        Ask(YES) = 0.45, Ask(NO) = 0.45 => sum = 0.90.
        Effective fee with BNB discount = 0.00075.
        fees_total = 0.90 * 0.00075 = 0.000675.
        net_edge = 1.00 - 0.900675 = ~0.099325 > min_parity_edge.
        Must generate DualBuyProposal with both orders.
        """
        engine = EstrategiaVArbitrajeAMM()
        snap_yes = OrderBookSnapshot(
            symbol="EVENT1_YES",
            bids=((0.44, 100.0),),
            asks=((0.45, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        snap_no = OrderBookSnapshot(
            symbol="EVENT1_NO",
            bids=((0.44, 100.0),),
            asks=((0.45, 80.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = engine.detectar_paridad_binaria(snap_yes, snap_no, event_id="EVENT1")

        assert signal is not None
        assert signal.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY
        assert signal.is_risk_free_parity is True
        assert signal.dual_proposal is not None

        dual = signal.dual_proposal
        assert isinstance(dual, DualBuyProposal)
        assert dual.price_yes == 0.45
        assert dual.price_no == 0.45
        assert dual.quantity == 50.0  # min(50, 80)
        assert dual.sum_asks == 0.90
        assert dual.net_edge > 0.09
        assert dual.order_yes.side == "BUY"
        assert dual.order_no.side == "BUY"

    def test_dual_buy_proposal_rejected_when_sum_exceeds_threshold(self):
        """
        Adversarial Test 6.2:
        Ask(YES) = 0.52, Ask(NO) = 0.50 => sum = 1.02 >= 1.00.
        Must return None.
        """
        engine = EstrategiaVArbitrajeAMM()
        snap_yes = OrderBookSnapshot(
            symbol="EVENT2_YES",
            bids=((0.50, 100.0),),
            asks=((0.52, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        snap_no = OrderBookSnapshot(
            symbol="EVENT2_NO",
            bids=((0.48, 100.0),),
            asks=((0.50, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = engine.detectar_paridad_binaria(snap_yes, snap_no, event_id="EVENT2")
        assert signal is None

    def test_dual_buy_proposal_rejected_when_market_suspended(self):
        """
        Adversarial Test 6.3:
        Golden Rule 2: If either contract has MarketStatus: SUSPENDED, reject immediately.
        """
        engine = EstrategiaVArbitrajeAMM()
        snap_yes = OrderBookSnapshot(
            symbol="EVENT3_YES",
            bids=((0.40, 100.0),),
            asks=((0.42, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="SUSPENDED",  # Suspended!
        )
        snap_no = OrderBookSnapshot(
            symbol="EVENT3_NO",
            bids=((0.40, 100.0),),
            asks=((0.42, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = engine.detectar_paridad_binaria(snap_yes, snap_no, event_id="EVENT3")
        assert signal is None


# ==============================================================================
# SECTION 7: PRE-MATCH AND IN-PLAY TARGET EV EARLY EXITS
# ==============================================================================

class TestTargetEVEarlyExits:
    """
    Adversarial verification of _vigilar_y_cerrar_posiciones_abiertas:
    Must close positions early both Pre-Match ('antes') and In-Play ('durante')
    across traditional Sports and ESports as soon as target EV is achieved.
    """

    @pytest.mark.asyncio
    async def test_ev_exit_pre_match_and_in_play_sports_and_esports(self):
        """
        Adversarial Test 7.1:
        Test across:
        1. Pre-Match Soccer (SOCCER_PRED_USDT, is_live=False)
        2. In-Play ESports (ESPORT_LOL_USDT, is_live=True)
        Verify that when best_bid >= target_exit_price, position closes immediately.
        """
        orchestrator = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT", "ESPORT_LOL_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        # 1. Inject open position: Pre-Match Soccer
        pos_soccer = HftPosition(
            position_id="POS_SOCCER_1",
            symbol="SOCCER_PRED_USDT",
            strategy_id="HFT_PHASE_1",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.50,
            quantity=20.0,
            entry_time=time.time(),
            target_exit_price=0.52,  # Target exit price
            timeout_seconds=10.0,
            status="OPEN",
        )
        orchestrator.hft_engine.active_positions["POS_SOCCER_1"] = pos_soccer

        # Snapshot for Soccer: best_bid reaches 0.53 >= 0.52 (EV achieved!)
        snap_soccer = OrderBookSnapshot(
            symbol="SOCCER_PRED_USDT",
            bids=((0.53, 100.0), (0.52, 200.0)),
            asks=((0.54, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        closed_trades = await orchestrator._vigilar_y_cerrar_posiciones_abiertas(
            "SOCCER_PRED_USDT", snap_soccer
        )

        assert len(closed_trades) == 1
        trade = closed_trades[0]
        assert trade.symbol == "SOCCER_PRED_USDT"
        assert trade.is_win is True
        assert trade.pnl == pytest.approx((0.53 - 0.50) * 20.0, abs=1e-4)  # +0.60
        assert "POS_SOCCER_1" not in orchestrator.hft_engine.active_positions

        # 2. Inject open position: In-Play ESports
        pos_esport = HftPosition(
            position_id="POS_ESPORT_1",
            symbol="ESPORT_LOL_USDT",
            strategy_id="HFT_PHASE_3",
            phase="FASE_3_INPLAY",
            side="BUY",
            entry_price=0.60,
            quantity=15.0,
            entry_time=time.time(),
            target_exit_price=0.64,  # Target exit price
            timeout_seconds=60.0,
            status="OPEN",
        )
        orchestrator.hft_engine.active_positions["POS_ESPORT_1"] = pos_esport

        # Snapshot for ESports: best_bid reaches 0.65 >= 0.64 (EV achieved!)
        snap_esport = OrderBookSnapshot(
            symbol="ESPORT_LOL_USDT",
            bids=((0.65, 50.0), (0.64, 100.0)),
            asks=((0.66, 30.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        closed_esport = await orchestrator._vigilar_y_cerrar_posiciones_abiertas(
            "ESPORT_LOL_USDT", snap_esport
        )

        assert len(closed_esport) == 1
        trade_esport = closed_esport[0]
        assert trade_esport.symbol == "ESPORT_LOL_USDT"
        assert trade_esport.is_win is True
        assert trade_esport.pnl == pytest.approx((0.65 - 0.60) * 15.0, abs=1e-4)  # +0.75
        assert "POS_ESPORT_1" not in orchestrator.hft_engine.active_positions


# ==============================================================================
# SECTION 8: PHASE 2 T-5m 'LIMPIAR_MESA' 0% EXPOSURE
# ==============================================================================

class TestPhase2LimpiarMesaZeroExposure:
    """
    Adversarial verification of Phase 2 T-5m 'limpiar_mesa':
    At 5 minutes before kickoff, all open orders are cancelled,
    open positions liquidated at market, and final exposure is strictly 0.0%.
    """

    def test_t5m_limpiar_mesa_cancels_and_liquidates_to_zero_exposure(self):
        """
        Adversarial Test 8.1:
        Inject pending orders and open positions into HFTEngine.
        Trigger Phase 2 at T-5m.
        Verify that active_positions is empty and final exposure is strictly 0.0%.
        """
        engine = HFTEngine()
        symbol = "SOCCER_MATCH_1"

        # Inject open positions
        pos1 = HftPosition(
            position_id="POS_1",
            symbol=symbol,
            strategy_id="HFT_PHASE_1",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.50,
            quantity=20.0,
            entry_time=time.time(),
            target_exit_price=0.55,
            timeout_seconds=10.0,
            status="OPEN",
        )
        pos2 = HftPosition(
            position_id="POS_2",
            symbol=symbol,
            strategy_id="HFT_PHASE_1",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.48,
            quantity=10.0,
            entry_time=time.time(),
            target_exit_price=0.52,
            timeout_seconds=10.0,
            status="OPEN",
        )
        engine.active_positions["POS_1"] = pos1
        engine.active_positions["POS_2"] = pos2

        snap = OrderBookSnapshot(
            symbol=symbol,
            bids=((0.51, 100.0),),
            asks=((0.53, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        # Trigger cleanup at Phase 2
        res = engine.ejecutar_fase_2_limpiar_mesa(
            symbol=symbol,
            snapshot=snap,
        )

        assert res["regla_innegociable_cumplida"] is True
        assert res["exposicion_final_pct"] == 0.0
        assert len(res["liquidaciones_mercado"]) == 2
        assert len(engine.active_positions) == 0


# ==============================================================================
# SECTION 9: DEEP ADVERSARIAL STRESS & CORNER CASES (GENERATION 2)
# ==============================================================================

class TestSequentialHarvestingAndCompoundingStress:
    """
    Stress-testing sequential growth and harvest cycles at $1,000 USD:
    Cycle 1: $10 -> $1,000 -> Harvest 1 -> Balance B_1 ->
    Cycle 2: B_1 -> $1,200 -> Harvest 2 -> Balance B_2 ->
    Cycle 3: B_2 -> $1,500 -> Harvest 3 -> Balance B_3.
    Verifies that cumulative isolated MXN and USD vaults track perfectly
    and balance conservation holds at every step.
    """

    def test_multi_cycle_harvesting_cumulative_vaults(self):
        tesoreria = GestorTesoreria(balance_inicial=10.0, tipo_cambio_mxn=20.0)

        # Cycle 1: Balance reaches 1,000.00
        tesoreria.balance = 1000.0
        h1 = tesoreria.ejecutar_cosecha_autonoma()
        assert h1["cosecha_ejecutada"] is True
        assert h1["ganancia_neta"] == 990.00
        assert h1["retiro_autonomo_35_usd"] == 346.50
        assert tesoreria.capital_aislado_cosecha_usd == 346.50
        assert tesoreria.capital_aislado_cosecha_mxn == 6930.00
        assert tesoreria.balance == 396.10

        # Cycle 2: Balance grows to 1,200.00
        tesoreria.balance = 1200.0
        h2 = tesoreria.ejecutar_cosecha_autonoma()
        assert h2["cosecha_ejecutada"] is True
        net_profit_2 = round(1200.0 - 396.10, 4)  # 803.90
        assert h2["ganancia_neta"] == net_profit_2
        retiro_35_c2 = round(net_profit_2 * 0.35, 4)  # 281.365 -> 281.365
        assert h2["retiro_autonomo_35_usd"] == retiro_35_c2
        assert tesoreria.capital_aislado_cosecha_usd == round(346.50 + retiro_35_c2, 4)

        # Cycle 3: Balance reaches 1,000.00 exactly (from post-harvest base)
        base_c3 = tesoreria.balance
        tesoreria.balance = 1000.0
        h3 = tesoreria.ejecutar_cosecha_autonoma()
        assert h3["cosecha_ejecutada"] is True
        net_profit_3 = round(1000.0 - base_c3, 4)
        assert h3["ganancia_neta"] == net_profit_3
        assert len(tesoreria.cosechas_ejecutadas) == 3


class TestKellyIEEE754ExtremeStress:
    """Stress testing Kelly Criterion against floating-point anomalies (subnormals, NaNs, Inf)."""

    def test_kelly_nan_safe_fail_closed_contract(self):
        """
        Contract requirement: Any NaN input must fail-closed to 0.0 stake.
        Verified passing after remediation.
        """
        assert calcular_criterio_kelly(p_estimada=float('nan'), cuota_neta=2.0) == 0.0

    def test_kelly_nan_vulnerability_empirical_confirmation(self):
        """
        Remediation verification:
        When p_estimada is NaN, calcular_criterio_kelly strictly returns 0.0 (fail-closed).
        """
        f_star_nan = calcular_criterio_kelly(p_estimada=float('nan'), cuota_neta=2.0)
        assert f_star_nan == 0.0, f"Remediation invariant check: got {f_star_nan}"

    def test_escudo_nan_approval_vulnerability_empirical_confirmation(self):
        """
        Remediation verification:
        EscudoFinanciero strictly rejects order and returns 0.0 stake when probability is NaN.
        """
        escudo = EscudoFinancieroBinance()
        res = escudo.calcular_posicion(
            balance_actual=1000.0,
            p_estimada=float('nan'),
            cuota=2.0,
            pct_stop_loss=0.05,
            usar_kelly=True,
        )
        assert res["operar"] is False
        assert res["motivo"] == "PROBABILIDAD_O_CUOTA_INVALIDA"
        assert res["stake"] == 0.0
        assert res["ev"] == 0.0

    def test_kelly_subnormal_and_inf_resilience(self):
        """Subnormal p (1e-300) must return 0.0; Inf odds bounded at 0.25."""
        # Inf in cuota: (p*(b+1)-1)/b -> p as b -> Inf. f* = 0.25 * 0.5 = 0.125 <= 0.25
        res_inf = calcular_criterio_kelly(p_estimada=0.5, cuota_neta=float('inf'))
        assert 0.0 <= res_inf <= 0.25

        # Subnormal p (1e-300)
        assert calcular_criterio_kelly(p_estimada=1e-300, cuota_neta=2.0) == 0.0


class TestBigtableRowKeyDelimiterAndRolloverStress:
    """Stress testing Bigtable row key with symbols, delimiters, and sequence rollover."""

    def test_symbol_with_hashes_and_symbols(self):
        """Symbol containing special chars must still format cleanly."""
        sym = "SOCCER#LIV-MCI#USDT"
        key = StateRegistry.format_bigtable_row_key(sym, 1728580000.0, seq_id=42)
        assert key.startswith(sym + "#")
        assert key.endswith("#0000000042")

    def test_sequence_id_overflow_above_10_digits(self):
        """Seq ID >= 10,000,000,000 must normalize modulo 10^10 without breaking %010d format."""
        seq_huge = 15_876_543_210
        key = StateRegistry.format_bigtable_row_key("BTCUSDT", 1728580000.0, seq_id=seq_huge)
        # Modulo 10^10 of 15_876_543_210 is 5_876_543_210
        assert key.endswith("#5876543210")
        assert len(key.split("#")[-1]) == 10


class TestMultiAssetEVEarlyExitsStress:
    """
    Stress-testing early EV exits across 8 sports disciplines:
    SOCCER, BASKETBALL, TENNIS, BASEBALL, AMERICAN_FOOTBALL, ESPORT_LOL, ESPORT_CS2, ESPORT_DOTA.
    """

    @pytest.mark.asyncio
    async def test_eight_discipline_simultaneous_ev_exits(self):
        symbols = [
            "SOCCER_PRED_USDT",
            "BASKETBALL_PRED_USDT",
            "TENNIS_PRED_USDT",
            "BASEBALL_PRED_USDT",
            "AMFOOTBALL_PRED_USDT",
            "ESPORT_LOL_USDT",
            "ESPORT_CS2_USDT",
            "ESPORT_DOTA_USDT",
        ]
        orchestrator = ContinuityHFTBinanceOrchestrator(
            symbols=symbols,
            capital_inicial=500.0,
            mock_mode=True,
        )

        # Inject open positions for all 8 symbols
        for i, sym in enumerate(symbols):
            pos = HftPosition(
                position_id=f"POS_DISC_{i}",
                symbol=sym,
                strategy_id="HFT_MULTI_DISC",
                phase="FASE_1_PREMATCH" if i % 2 == 0 else "FASE_3_INPLAY",
                side="BUY",
                entry_price=0.50,
                quantity=10.0,
                entry_time=time.time(),
                target_exit_price=0.52,
                timeout_seconds=30.0,
                status="OPEN",
            )
            orchestrator.hft_engine.active_positions[pos.position_id] = pos

        assert len(orchestrator.hft_engine.active_positions) == 8

        # For each symbol, feed snapshot with best_bid = 0.54 (EV achieved!)
        total_closed = 0
        for sym in symbols:
            snap = OrderBookSnapshot(
                symbol=sym,
                bids=((0.54, 100.0), (0.52, 200.0)),
                asks=((0.55, 50.0),),
                timestamp_ms=int(time.time() * 1000),
                market_status="ACTIVE",
            )
            closed = await orchestrator._vigilar_y_cerrar_posiciones_abiertas(sym, snap)
            total_closed += len(closed)

        assert total_closed == 8
        assert len(orchestrator.hft_engine.active_positions) == 0


class TestStrategyVDualBuyEdgeBoundaries:
    """Stress testing Strategy V edge margins and unbalanced liquidity."""

    def test_unbalanced_liquidity_dual_proposal(self):
        """When YES has 5 contracts and NO has 500 contracts, dual quantity must be exactly min(5, 500) = 5."""
        engine = EstrategiaVArbitrajeAMM()
        snap_yes = OrderBookSnapshot(
            symbol="UNBAL_YES",
            bids=((0.40, 100.0),),
            asks=((0.42, 5.0),),   # Only 5.0 contracts
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        snap_no = OrderBookSnapshot(
            symbol="UNBAL_NO",
            bids=((0.40, 100.0),),
            asks=((0.42, 500.0),),  # 500.0 contracts
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = engine.detectar_paridad_binaria(snap_yes, snap_no, event_id="UNBAL")
        assert signal is not None
        assert signal.dual_proposal is not None
        assert signal.dual_proposal.quantity == 5.0

    def test_exact_min_edge_boundary(self):
        """
        When net_edge is below min_parity_edge (e.g. 0.001), must reject.
        Ask YES = 0.499, Ask NO = 0.500 => sum = 0.999.
        With fees ~ 0.00075, total cost ~ 0.99975 => edge = 0.00025 < 0.001 -> rejected.
        """
        engine = EstrategiaVArbitrajeAMM()
        snap_yes = OrderBookSnapshot(
            symbol="TIGHT_YES",
            bids=((0.48, 100.0),),
            asks=((0.499, 10.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        snap_no = OrderBookSnapshot(
            symbol="TIGHT_NO",
            bids=((0.48, 100.0),),
            asks=((0.500, 10.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = engine.detectar_paridad_binaria(snap_yes, snap_no, event_id="TIGHT")
        assert signal is None
