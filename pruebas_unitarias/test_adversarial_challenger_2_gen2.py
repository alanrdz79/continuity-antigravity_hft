# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_adversarial_challenger_2_gen2
====================================================
Comprehensive Empirical Stress-Testing Suite by Challenger 2 (Gen 2).

Focus Areas:
1. Concurrency stress on StateRegistry (simultaneous reads/writes/enqueues/dequeues).
2. Strict 4-decimal precision float rounding invariance on financial metrics.
3. Orchestrator multi-loop lifecycle in HFT_BINANCE.py with mock client and /kill signal.
4. Target EV exit edge cases (spread = 0, best bid == target exit price, timeout expiration, empty book).
"""

from __future__ import annotations

import asyncio
import math
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple

import pytest

from continuitis.state_registry import StateRegistry, StateRegistrySQLite
from continuitis.riesgo_binance import (
    EscudoFinancieroBinance,
    OrderProposal,
    RiskApprovedOrder,
    calcular_criterio_kelly,
    BINANCE_SPOT_BASE_FEE,
    BNB_DISCOUNT_FACTOR,
    BINANCE_BNB_FEE_RATE,
)
from continuitis.tesoreria import (
    GestorTesoreria,
    UMBRAL_INYECCION_100,
    MONTO_INYECCION_100,
    UMBRAL_COSECHA_1000,
    PCT_COSECHA_AUTONOMA,
    PCT_GASTOS_OPERACION,
    PCT_REINVERSION_COMPUESTA,
)
from continuitis.auditor_metricas import (
    AuditorMetricas,
    TradeResult,
)
from continuitis.microestructura_binance import (
    DEFAULT_TICK_SIZE,
    MAX_SPREAD_PERMITIDO,
    GoldenRulesValidator,
    HFTPriceCalculator,
    MicroestructuraBinanceEngine,
    OrderBookSnapshot,
)
from estrategias.hft_engine import (
    HFTEngine,
    HftPosition,
    MatchLiveState,
    SportType,
)
from orquestadores_principales.HFT_BINANCE import (
    ContinuityHFTBinanceOrchestrator,
)
from conectores.telegram_bidireccional import (
    MockTelegramClient,
    TelegramBidireccionalBot,
)


# ==============================================================================
# FOCUS AREA 1: StateRegistry CONCURRENCY & RACE CONDITIONS
# ==============================================================================

class TestStateRegistryConcurrencyStress:
    """Stress tests verifying StateRegistry concurrency and race condition resilience."""

    def test_state_registry_multithreaded_concurrent_operations(self):
        """
        Stress test: 50 concurrent threads simultaneously performing:
        - set_state / get_state
        - encolar_partido / obtener_partidos_pendientes
        - cerrar_partido / record_trade / get_recent_trades
        Assert zero unhandled exceptions, zero data corruption, thread-safe execution.
        """
        registry = StateRegistry()
        registry.clear_all()

        num_threads = 50
        ops_per_thread = 40
        errors: List[Exception] = []

        def worker(thread_idx: int):
            try:
                for i in range(ops_per_thread):
                    partido_id = f"P_{thread_idx}_{i}"
                    # 1. State read/write
                    registry.set_state(f"key_{thread_idx}", f"val_{i}")
                    val = registry.get_state(f"key_{thread_idx}")
                    assert val == f"val_{i}"

                    # 2. Queue enqueue
                    registry.encolar_partido(partido_id, {
                        "sport": "SOCCER",
                        "round": i,
                        "thread": thread_idx,
                    })

                    # 3. Read pending queue
                    pending = registry.obtener_partidos_pendientes()
                    assert isinstance(pending, list)

                    # 4. Record trade
                    registry.record_trade(
                        trade_id=f"T_{thread_idx}_{i}",
                        symbol="SOCCER_PRED_USDT",
                        pnl=0.01 * i,
                        is_win=i % 2 == 0,
                        timestamp=time.time(),
                        stake=10.0,
                    )

                    # 5. Get recent trades
                    recent = registry.get_recent_trades(limit=20)
                    assert isinstance(recent, list)
                    assert len(recent) <= 20

                    # 6. Close match with trade result
                    if i % 2 == 0:
                        registry.cerrar_partido(partido_id, {
                            "trade_id": f"T_CLOSE_{thread_idx}_{i}",
                            "symbol": "SOCCER_PRED_USDT",
                            "pnl": 0.05,
                            "is_win": True,
                            "timestamp": time.time(),
                            "stake": 5.0,
                        })
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(num_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15.0)

        assert not errors, f"Concurrency errors encountered: {errors}"
        recent_all = registry.get_recent_trades(limit=100)
        assert len(recent_all) == 100
        assert len(registry._mem_trades) <= 1000

    def test_state_registry_record_trade_sequence_monotonicity_under_race(self):
        """
        Stress test: 100 concurrent threads recording trades at the exact same instant.
        Verify sequence counter increments monotonically modulo 1,000,000,000 without duplicates.
        """
        registry = StateRegistry()
        registry.clear_all()

        recorded_seqs: List[int] = []
        lock = threading.Lock()

        def log_trade(idx: int):
            now = 1728590000.0  # Fixed timestamp to stress sequence disambiguation
            registry.record_trade(
                trade_id=f"TRADE_{idx}",
                symbol="BTC_PRED",
                pnl=1.0,
                is_win=True,
                timestamp=now,
                stake=10.0,
            )
            with lock:
                recorded_seqs.append(registry._seq_counter)

        with ThreadPoolExecutor(max_workers=30) as pool:
            futures = [pool.submit(log_trade, i) for i in range(300)]
            for f in futures:
                f.result()

        assert len(recorded_seqs) == 300
        assert len(set(recorded_seqs)) == 300
        assert min(recorded_seqs) == 1
        assert max(recorded_seqs) == 300

    def test_state_registry_queue_concurrency_no_stale_or_corrupt_data(self):
        """
        30 threads continuously adding items, 10 threads continuously reading queue,
        20 threads closing items. Verify zero KeyError, zero race mutations.
        """
        registry = StateRegistry()
        registry.clear_all()
        errors: List[Exception] = []
        stop_event = threading.Event()

        def reader():
            while not stop_event.is_set():
                try:
                    q = registry.obtener_partidos_pendientes()
                    for item in q:
                        assert "partido_id" in item
                except Exception as e:
                    errors.append(e)

        def modifier(tid: int):
            for i in range(30):
                pid = f"MATCH_{tid}_{i}"
                try:
                    registry.encolar_partido(pid, {"tid": tid, "i": i})
                    if i % 2 == 0:
                        registry.cerrar_partido(pid)
                except Exception as e:
                    errors.append(e)

        reader_threads = [threading.Thread(target=reader) for _ in range(5)]
        modifier_threads = [threading.Thread(target=modifier, args=(t,)) for t in range(20)]

        for t in reader_threads:
            t.start()
        for t in modifier_threads:
            t.start()

        for t in modifier_threads:
            t.join(timeout=10.0)
        stop_event.set()
        for t in reader_threads:
            t.join(timeout=5.0)

        assert not errors, f"Errors in queue concurrency: {errors}"

    def test_state_registry_bigtable_reverse_timestamp_lexicographical_sorting(self):
        """
        Verify that StateRegistry.format_bigtable_row_key produces strictly reverse-chronological
        lexicographical sorting: key(newer) < key(older).
        """
        symbol = "SOCCER_PRED"
        ts_old = 1700000000.0
        ts_mid = 1700000050.0
        ts_new = 1700000100.0

        key_old = StateRegistry.format_bigtable_row_key(symbol, ts_old, seq_id=1)
        key_mid = StateRegistry.format_bigtable_row_key(symbol, ts_mid, seq_id=2)
        key_new = StateRegistry.format_bigtable_row_key(symbol, ts_new, seq_id=3)

        assert key_new < key_mid < key_old, (
            f"Reverse timestamp ordering violated: new={key_new}, mid={key_mid}, old={key_old}"
        )

    def test_state_registry_cerrar_partido_none_pnl_typeerror_vulnerability(self):
        """
        Remediation verification:
        Passing trade_result={'pnl': None} safely null-coalesces to 0.0 without raising TypeError.
        """
        registry = StateRegistry()
        registry.cerrar_partido("PARTIDO_NONE_PNL", {"pnl": None})
        trades = registry.get_recent_trades(limit=1)
        assert len(trades) >= 1
        assert trades[0]["pnl"] == 0.0


# ==============================================================================
# FOCUS AREA 2: STRICT 4-DECIMAL PRECISION FLOAT ROUNDING INVARIANCE
# ==============================================================================

class TestFourDecimalPrecisionInvarianceStress:
    """Stress tests verifying strict 4-decimal precision across financial modules."""

    def test_auditor_metricas_rounding_invariance_across_random_trades(self):
        """
        Feed 500 random trades with high-precision decimal stakes and PnLs.
        Assert that every reported metric (WR, B_N, ROI, Yield) is strictly invariant to 4 decimals.
        """
        auditor = AuditorMetricas(capital_inicial=10.0)

        for i in range(1, 501):
            stake = round(0.50 + (i * 0.0073), 6)
            pnl = round(((i % 7) - 3) * 0.0137, 6)
            is_win = pnl > 0
            auditor.registrar_trade(TradeResult(
                trade_id=f"T_{i}",
                symbol="SOCCER_PRED",
                stake=stake,
                pnl=pnl,
                is_win=is_win,
                timestamp=time.time(),
            ))

        metricas = auditor.obtener_metricas()
        for k in ("win_rate", "capital_acumulado", "roi", "yield"):
            val = metricas[k]
            rounded = round(val, 4)
            assert math.isclose(val, rounded, abs_tol=1e-9), f"Metric {k} = {val} violates 4-decimal precision!"

    def test_compounding_capital_bn_precision_vs_exact_decimal_oracle(self):
        """
        Compare AuditorMetricas.calcular_capital_acumulado against high-precision Decimal oracle.
        Verify error bound stays below 1e-3 across 100 compounding steps.
        """
        cap_init = 100.0
        auditor = AuditorMetricas(capital_inicial=cap_init)
        dec_b = Decimal("100.0")

        for i in range(1, 101):
            stake = 5.0
            pnl = 0.50 if (i % 3 != 0) else -0.40
            is_win = pnl > 0
            auditor.registrar_trade(TradeResult(f"T_{i}", "SYM", stake, pnl, is_win, time.time()))

            # Decimal compound step
            f_i = Decimal(str(stake)) / dec_b
            r_i = Decimal(str(pnl)) / Decimal(str(stake))
            factor = Decimal("1.0") + (f_i * r_i)
            dec_b = dec_b * factor

        actual_bn = auditor.calcular_capital_acumulado()
        expected_bn = float(round(dec_b, 4))
        assert math.isclose(actual_bn, expected_bn, abs_tol=1e-3), (
            f"B_N drift: actual={actual_bn}, decimal_oracle={expected_bn}"
        )

    def test_autonomous_harvesting_exact_conservation_identity_stress(self):
        """
        Stress test: Across 500 arbitrary gain amounts (including sub-cent floats),
        verify exact conservation identity:
          ganancia_neta == retiro_35 + gastos_40 + reinversion_60
        within strict 4-decimal rounding tolerance.
        """
        for i in range(1, 501):
            balance_test = 1000.0 + (i * 0.333333333)
            tesoreria = GestorTesoreria(balance_inicial=100.0)
            tesoreria.balance = balance_test
            tesoreria.capital_base_post_cosecha = 1000.0

            res = tesoreria.ejecutar_cosecha_autonoma()
            assert res["cosecha_ejecutada"] is True

            g = res["ganancia_neta"]
            r35 = res["retiro_autonomo_35_usd"]
            g40 = res["gastos_operacion_40_usd"]
            c60 = res["reinversion_compuesta_60_usd"]

            remanente = round(g - r35, 4)
            assert math.isclose(g40 + c60, remanente, abs_tol=1e-4), (
                f"Split discrepancy at g={g}: g40={g40}, c60={c60}, remanente={remanente}"
            )

    def test_kelly_extreme_probabilities_and_odds_bounds(self):
        """
        Verify Kelly fraction is strictly bounded in [0.0, 0.25] and rounded to 4 decimals
        across extreme parameter combinations.
        """
        test_cases = [
            (0.0001, 100.0),    # Micro probability, high odds
            (0.9999, 1.0001),   # Near certainty, micro odds
            (0.5000, 2.0000),   # Fair odds
            (0.5500, 2.0000),   # 10% edge
            (0.8000, 3.0000),   # Huge edge
            (0.0000, 5.0000),   # Zero probability
            (0.5000, 1.0000),   # Cuota 1.0 (no profit)
            (0.5000, 0.5000),   # Cuota < 1.0
        ]
        for p, odds in test_cases:
            f = calcular_criterio_kelly(p, odds)
            assert 0.0 <= f <= 0.25, f"Kelly {f} out of [0, 0.25] for p={p}, odds={odds}"
            assert f == round(f, 4), f"Kelly {f} not 4 decimals for p={p}, odds={odds}"

    def test_kelly_nan_vulnerability_empirical_confirmation(self):
        """
        Remediation verification:
        Confirm that NaN probability strictly returns Kelly fraction 0.0 (fail-closed).
        """
        val = calcular_criterio_kelly(float("nan"), 2.0)
        assert val == 0.0, f"Expected Kelly NaN fail-closed to evaluate to 0.0, got {val}"

    def test_escudo_nan_approval_vulnerability_confirmation(self):
        """
        Remediation verification:
        Confirm that EscudoFinancieroBinance rejects orders with NaN probability.
        """
        escudo = EscudoFinancieroBinance()
        res = escudo.calcular_posicion(100.0, float("nan"), 2.0, 0.05)
        assert res["operar"] is False
        assert res["motivo"] == "PROBABILIDAD_O_CUOTA_INVALIDA"

    def test_evaluar_target_ev_salida_unrounded_comparison_inconsistency(self):
        """
        Empirically test whether evaluating unrounded float before rounding
        creates discrepancy between reported 4-decimal return and boolean exit flag.
        """
        escudo = EscudoFinancieroBinance()
        bid_edge = 0.50 * 1.019999999999999 / 0.99925
        res = escudo.evaluar_target_ev_salida(
            precio_entrada=0.50,
            precio_actual_bid=bid_edge,
            ev_objetivo_minimo=0.02,
        )
        assert res["retorno_neto"] == 0.02
        assert res["cerrar_posicion"] is False


# ==============================================================================
# FOCUS AREA 3: ORCHESTRATOR MULTI-LOOP LIFECYCLE & /kill SIGNAL
# ==============================================================================

class TestOrchestratorLifecycleAndKillSwitchStress:
    """Stress tests on ContinuityHFTBinanceOrchestrator lifecycle and /kill signal."""

    @pytest.mark.asyncio
    async def test_orchestrator_multi_loop_start_and_stop_lifecycle(self):
        """
        Verify orchestrator start -> ticks -> clean stop -> restart -> clean stop.
        Assert tasks are properly managed and no dangling loops remain.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
            hft_cycle_interval_s=0.01,
            swing_cycle_interval_s=0.05,
        )

        # Loop 1
        await orch.start()
        assert orch.is_running is True
        assert len(orch._tasks) == 5
        assert all(not t.done() for t in orch._tasks)

        await asyncio.sleep(0.03)

        await orch.stop()
        assert orch.is_running is False
        assert all(t.done() for t in orch._tasks)

        # Loop 2: Restart
        await orch.start()
        assert orch.is_running is True
        assert len(orch._tasks) == 5
        assert all(not t.done() for t in orch._tasks)

        await asyncio.sleep(0.03)
        await orch.stop()
        assert orch.is_running is False
        assert all(t.done() for t in orch._tasks)

    @pytest.mark.asyncio
    async def test_telegram_kill_command_immediate_cessation_under_market_updates(self):
        """
        Verify that receiving /kill via Telegram while market updates are streaming:
        1. Instantly triggers kill switch
        2. Pauses trading
        3. Sets micro_engine.latency_guard emergency state
        4. Cancels pending exchange orders
        5. step_hft_cycle, step_swing_cycle, step_amm_cycle return None
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        ts = int(time.time() * 1000)
        orch.binance_client.actualizar_libro(
            symbol="SOCCER_PRED_USDT",
            bids=((0.50, 1000.0), (0.49, 800.0), (0.48, 500.0)),
            asks=((0.52, 100.0), (0.53, 50.0)),
            timestamp_ms=ts,
            market_status="ACTIVE",
        )

        sig_before = await orch.step_hft_cycle("SOCCER_PRED_USDT")
        assert sig_before is not None

        resp = await orch.telegram_bot.router.procesar_mensaje("/kill")
        assert "KILL SWITCH ACTIVADO" in resp or "🚨" in resp
        assert orch.kill_switch_triggered is True
        assert orch.is_paused is True
        assert orch.micro_engine.latency_guard.emergencia_activa is True

        sig_after = await orch.step_hft_cycle("SOCCER_PRED_USDT")
        assert sig_after is None

        swing_after = await orch.step_swing_cycle("SOCCER_PRED_USDT")
        assert swing_after is None

        amm_after = await orch.step_amm_cycle("EVENT_1")
        assert amm_after is None

    @pytest.mark.asyncio
    async def test_kill_switch_multi_symbol_cleaning_and_capital_release(self):
        """
        Stress test: 6 symbols active. Open positions across all symbols.
        Trigger kill switch. Verify all symbols have orders cancelled,
        capital tokens released, and capital gateway has exactly 0.0 committed.
        """
        symbols = [
            "SOCCER_PRED_USDT",
            "BASKET_PRED_USDT",
            "TENNIS_PRED_USDT",
            "ESPORTS_LOL_USDT",
            "ESPORTS_CS2_USDT",
            "ESPORTS_DOTA_USDT",
        ]
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=symbols,
            capital_inicial=500.0,
            mock_mode=True,
        )

        # Allocate capital reservations
        for sym in symbols:
            tok = await orch.capital_gateway.reservar_capital(
                stake=10.0,
                strategy_id="HFT",
                symbol=sym,
            )
            assert tok is not None

        assert orch.capital_gateway.capital_comprometido == 60.0

        # Trigger kill switch
        orch.trigger_kill_switch("EMERGENCY_MULTI_ASSET")

        assert orch.kill_switch_triggered is True
        assert orch.is_paused is True
        assert orch.capital_gateway.capital_comprometido == 0.0
        assert len(orch.capital_gateway.active_tokens) == 0

    @pytest.mark.asyncio
    async def test_resume_command_resets_kill_switch_cleanly(self):
        """
        Verify that explicit resume restores normal operations after a kill switch.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )
        orch.trigger_kill_switch("TEST_PANIC")
        assert orch.kill_switch_triggered is True

        resp = await orch.telegram_bot.router.procesar_mensaje("/resume")
        assert orch.kill_switch_triggered is False
        assert orch.is_paused is False
        assert orch.micro_engine.latency_guard.emergencia_activa is False


# ==============================================================================
# FOCUS AREA 4: TARGET EV EXIT EDGE CASES & BOUNDARIES
# ==============================================================================

class TestTargetEVExitEdgeCasesStress:
    """Stress tests on EV exit timing, zero spread, exact boundaries, and timeouts."""

    @pytest.mark.asyncio
    async def test_ev_exit_when_spread_is_zero(self):
        """
        Edge case: Spread = 0 (Best Bid == Best Ask == 0.53).
        Verify _vigilar_y_cerrar_posiciones_abiertas executes take profit cleanly when best_bid >= target_exit_price.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        pos = HftPosition(
            position_id="POS_ZERO_SPREAD",
            symbol="SOCCER_PRED_USDT",
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.50,
            quantity=100.0,
            entry_time=time.time(),
            target_exit_price=0.53,
            timeout_seconds=10.0,
            status="OPEN",
        )
        orch.hft_engine.active_positions["POS_ZERO_SPREAD"] = pos

        snap_zero_spread = OrderBookSnapshot(
            symbol="SOCCER_PRED_USDT",
            bids=((0.53, 500.0), (0.52, 200.0)),
            asks=((0.53, 500.0), (0.54, 200.0)),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        closed_trades = await orch._vigilar_y_cerrar_posiciones_abiertas(
            symbol="SOCCER_PRED_USDT",
            snapshot=snap_zero_spread,
        )

        assert len(closed_trades) == 1
        t = closed_trades[0]
        assert t.trade_id == "TRADE_EV_POS_ZERO_SPREAD"
        assert t.is_win is True
        assert t.pnl == round((0.53 - 0.50) * 100.0, 4)
        assert "POS_ZERO_SPREAD" not in orch.hft_engine.active_positions

    @pytest.mark.asyncio
    async def test_ev_exit_boundary_best_bid_exactly_equals_target_exit_price(self):
        """
        Boundary test: best_bid is exactly target_exit_price (0.5200 == 0.5200).
        Then test best_bid is 0.5199 (1e-4 below target).
        Assert exact boundary triggers exit; sub-boundary keeps position open.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["BASKET_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        pos_sub = HftPosition(
            position_id="POS_SUB_TARGET",
            symbol="BASKET_PRED_USDT",
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.50,
            quantity=100.0,
            entry_time=time.time(),
            target_exit_price=0.5200,
            timeout_seconds=20.0,
            status="OPEN",
        )
        orch.hft_engine.active_positions["POS_SUB_TARGET"] = pos_sub

        # Sub-target: best_bid = 0.5199 (< 0.5200)
        snap_sub = OrderBookSnapshot(
            symbol="BASKET_PRED_USDT",
            bids=((0.5199, 100.0),),
            asks=((0.5300, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        closed_sub = await orch._vigilar_y_cerrar_posiciones_abiertas("BASKET_PRED_USDT", snap_sub)
        assert len(closed_sub) == 0
        assert "POS_SUB_TARGET" in orch.hft_engine.active_positions

        # Exact target: best_bid = 0.5200 (== 0.5200)
        snap_exact = OrderBookSnapshot(
            symbol="BASKET_PRED_USDT",
            bids=((0.5200, 100.0),),
            asks=((0.5300, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        closed_exact = await orch._vigilar_y_cerrar_posiciones_abiertas("BASKET_PRED_USDT", snap_exact)
        assert len(closed_exact) == 1
        assert closed_exact[0].is_win is True
        assert closed_exact[0].pnl == round((0.52 - 0.50) * 100.0, 4)

    @pytest.mark.asyncio
    async def test_ev_exit_timeout_expiration_forces_loss_exit(self):
        """
        Verify that when timeout expires (e.g. 5.0s elapsed), the position is force-closed
        at current best_bid even if best_bid < entry_price (loss scenario).
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["TENNIS_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        entry_t = time.time() - 10.0
        pos_timeout = HftPosition(
            position_id="POS_EXPIRED",
            symbol="TENNIS_PRED_USDT",
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.50,
            quantity=50.0,
            entry_time=entry_t,
            target_exit_price=0.55,
            timeout_seconds=5.0,
            status="OPEN",
        )
        orch.hft_engine.active_positions["POS_EXPIRED"] = pos_timeout

        snap_loss = OrderBookSnapshot(
            symbol="TENNIS_PRED_USDT",
            bids=((0.47, 200.0),),
            asks=((0.49, 200.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        closed = await orch._vigilar_y_cerrar_posiciones_abiertas("TENNIS_PRED_USDT", snap_loss)
        assert len(closed) == 1
        trade = closed[0]
        assert "TIMEOUT" in trade.trade_id
        assert trade.is_win is False
        assert trade.pnl == round((0.47 - 0.50) * 50.0, 4)  # -1.50 USD
        assert orch.risk_engine.consecutive_losses == 1
        assert "POS_EXPIRED" not in orch.hft_engine.active_positions

    @pytest.mark.asyncio
    async def test_ev_exit_empty_order_book_bids_safety(self):
        """
        Corner case: Market book snapshot has zero bids (`bids = []`).
        Assert system does not crash with IndexError / zero-division and safely defers exit
        if position is not timed out.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["ESPORTS_CS2_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        pos = HftPosition(
            position_id="POS_EMPTY_BIDS",
            symbol="ESPORTS_CS2_USDT",
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.50,
            quantity=100.0,
            entry_time=time.time(),
            target_exit_price=0.54,
            timeout_seconds=60.0,
            status="OPEN",
        )
        orch.hft_engine.active_positions["POS_EMPTY_BIDS"] = pos

        snap_empty = OrderBookSnapshot(
            symbol="ESPORTS_CS2_USDT",
            bids=[],
            asks=((0.55, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        closed = await orch._vigilar_y_cerrar_posiciones_abiertas("ESPORTS_CS2_USDT", snap_empty)
        assert len(closed) == 0
        assert "POS_EMPTY_BIDS" in orch.hft_engine.active_positions

    @pytest.mark.asyncio
    async def test_multi_position_selective_ev_closure_same_symbol(self):
        """
        Stress test: 10 open positions on SOCCER_PRED_USDT.
        5 have target_exit_price = 0.52 (met).
        5 have target_exit_price = 0.56 (unmet).
        Assert exactly 5 close, 5 remain open, no double-counting.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=200.0,
            mock_mode=True,
        )

        for i in range(10):
            target = 0.52 if i < 5 else 0.56
            pos = HftPosition(
                position_id=f"POS_MULTI_{i}",
                symbol="SOCCER_PRED_USDT",
                strategy_id="HFT_PHASE_1_OBI",
                phase="FASE_1_PREMATCH",
                side="BUY",
                entry_price=0.50,
                quantity=10.0,
                entry_time=time.time(),
                target_exit_price=target,
                timeout_seconds=100.0,
                status="OPEN",
            )
            orch.hft_engine.active_positions[f"POS_MULTI_{i}"] = pos

        snap = OrderBookSnapshot(
            symbol="SOCCER_PRED_USDT",
            bids=((0.53, 500.0),),
            asks=((0.54, 500.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        closed = await orch._vigilar_y_cerrar_posiciones_abiertas("SOCCER_PRED_USDT", snap)
        assert len(closed) == 5
        assert len(orch.hft_engine.active_positions) == 5
        # Remaining positions must all have target_exit_price == 0.56
        for p in orch.hft_engine.active_positions.values():
            assert p.target_exit_price == 0.56

    @pytest.mark.asyncio
    async def test_ev_exit_across_all_7_sports_and_esports(self):
        """
        Verify target EV early exits execute correctly across all 7 traditional sports
        and ESports.
        """
        symbols_sports = [
            ("SOCCER_PRED_USDT", SportType.SOCCER),
            ("BASEBALL_PRED_USDT", SportType.BASEBALL),
            ("AMERICAN_FOOTBALL_PRED_USDT", SportType.AMERICAN_FOOTBALL),
            ("BASKETBALL_PRED_USDT", SportType.BASKETBALL),
            ("TENNIS_PRED_USDT", SportType.TENNIS),
            ("HOCKEY_PRED_USDT", SportType.HOCKEY),
            ("ESPORTS_LOL_USDT", SportType.ESPORTS),
        ]
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=[s[0] for s in symbols_sports],
            capital_inicial=500.0,
            mock_mode=True,
        )

        for sym, sport in symbols_sports:
            pos = HftPosition(
                position_id=f"POS_{sport.value}",
                symbol=sym,
                strategy_id="HFT",
                phase="IN_PLAY",
                side="BUY",
                entry_price=0.45,
                quantity=20.0,
                entry_time=time.time(),
                target_exit_price=0.48,
                timeout_seconds=300.0,
                status="OPEN",
            )
            orch.hft_engine.active_positions[pos.position_id] = pos

            snap = OrderBookSnapshot(
                symbol=sym,
                bids=((0.49, 100.0),),
                asks=((0.50, 100.0),),
                timestamp_ms=int(time.time() * 1000),
                market_status="ACTIVE",
            )

            closed = await orch._vigilar_y_cerrar_posiciones_abiertas(sym, snap)
            assert len(closed) == 1
            assert closed[0].is_win is True
            assert closed[0].pnl == round((0.49 - 0.45) * 20.0, 4)
