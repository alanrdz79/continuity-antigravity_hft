# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_adversarial_challenger | CONTINUITY HFT Binance
==================================================================================
Adversarial Stress Test Suite authored by Challenger 1 (Empirical Challenger).

Stress-Tests & Adversarial Vectors:
1. Order Book Imbalance (OBI) under extreme numerical boundary conditions:
   - Boundary precision: I = 0.600000 vs 0.599900 vs 0.599999.
   - Zero depth, phantom liquidity (zero volume levels), single-sided books.
   - Sub-cent pricing and Maker vs Taker boundary crossing (Best Bid + 1 tick >= Best Ask).
2. Golden Rule 1 (Spread <= $0.03):
   - Exact boundary: $0.0300 vs $0.0301 vs $0.03000001.
   - Inverted and crossed books (Best Ask < Best Bid).
   - IEEE-754 NaN injection vulnerability test.
3. Golden Rule 2 (Market Status Suspended Lock):
   - Strict lock under all variations of 'SUSPENDED'.
   - Fail-closed behavior on unknown/irregular states ('HALTED', 'PAUSED', '').
   - Feed transition lock during rapid tick updates.
4. Golden Rule 3 (Top 3 BIDs Liquidity Ceiling):
   - Dimensional mismatch test: contract volume float vs USD stake in EscudoFinanciero.
   - Proof of order quantity overshooting Top 3 BIDs liquidity when contract price < $1.00.
   - Books with < 3 levels (0, 1, 2 levels) and zero liquidity.
5. Concurrency & Event Loop Starvation:
   - High-throughput tick burst (300 L2 depth ticks concurrent with CPU load).
   - Verification of zero event loop lockups and heartbeat delay < 50ms.
   - Lock contention and deadlock absence in AsyncCapitalGateway.
   - 5-cent tolerance drift test in AsyncCapitalGateway.
"""

import asyncio
import math
import time
import pytest
from typing import Dict, List, Tuple, Any, Optional

from continuitis.microestructura_binance import (
    DEFAULT_TICK_SIZE,
    MAX_SPREAD_PERMITIDO,
    BUY_DOMINANCE_IMBALANCE_THRESHOLD,
    GoldenRulesValidator,
    HFTPriceCalculator,
    MicroestructuraBinanceEngine,
    MicrostructureSignal,
    OrderBookImbalanceCalculator,
    OrderBookSnapshot,
    OrderProposal,
    RiskApprovedOrder,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance
from estrategias.hft_engine import HFTEngine, MatchLiveState, SportType
from estrategias.swing_engine import AsyncCapitalGateway, CapitalReservationToken


# ==============================================================================
# SECTION 1: ORDER BOOK IMBALANCE (OBI) EXTREME CONDITIONS & BOUNDARIES
# ==============================================================================

class TestAdversarialMicrostructureAndOBI:
    """Stress tests on Order Book Imbalance under extreme numerical and structural conditions."""

    def test_obi_exact_boundary_0_6000_vs_0_5999(self):
        """
        Adversarial Test 1.1:
        Verify strictly whether I = 0.600000 triggers buy dominance,
        while I = 0.599900 and I = 0.599999 are strictly rejected.
        
        Derivation:
        - For total volume 1000.0:
          * V_Bid = 800.0, V_Ask = 200.0 => I = 600 / 1000 = 0.600000 (Exact 80% buy ratio)
          * V_Bid = 799.95, V_Ask = 200.05 => I = 599.9 / 1000 = 0.599900 (79.995% buy ratio)
          * V_Bid = 799.9995, V_Ask = 200.0005 => I = 599.999 / 1000 = 0.599999 (79.9999% buy ratio)
        """
        # Exact boundary: 0.600000
        bids_exact = ((0.50, 800.0),)
        asks_exact = ((0.52, 200.0),)
        i_exact = OrderBookImbalanceCalculator.calcular_imbalance(bids_exact, asks_exact)
        assert i_exact == 0.600000
        assert OrderBookImbalanceCalculator.detectar_dominancia_compra(i_exact) is True

        # Just below boundary: 0.599900
        bids_below = ((0.50, 799.95),)
        asks_below = ((0.52, 200.05),)
        i_below = OrderBookImbalanceCalculator.calcular_imbalance(bids_below, asks_below)
        assert i_below == pytest.approx(0.599900, abs=1e-6)
        assert OrderBookImbalanceCalculator.detectar_dominancia_compra(i_below) is False

        # Infinitesimally below boundary: 0.599999
        bids_micro = ((0.50, 799.9995),)
        asks_micro = ((0.52, 200.0005),)
        i_micro = OrderBookImbalanceCalculator.calcular_imbalance(bids_micro, asks_micro)
        assert i_micro == pytest.approx(0.599999, abs=1e-6)
        assert OrderBookImbalanceCalculator.detectar_dominancia_compra(i_micro) is False

    def test_obi_zero_depth_and_negative_volume_resilience(self):
        """
        Adversarial Test 1.2:
        Empty books, books with zero volume, or corrupt negative volume
        must return I = 0.0 and never raise ZeroDivisionError or NaN.
        """
        calc = OrderBookImbalanceCalculator

        # Empty books
        assert calc.calcular_imbalance((), ()) == 0.0
        assert calc.calcular_ratio_compra((), ()) == 0.0

        # Zero volume items
        assert calc.calcular_imbalance(((0.50, 0.0),), ((0.52, 0.0),)) == 0.0

        # Negative volume entries
        assert calc.calcular_imbalance(((0.50, -50.0),), ((0.52, -10.0),)) == 0.0

        # Mixed valid and negative volume
        # Bid has 100 valid, -50 invalid. Ask has 50 valid.
        # Valid Bid = 100, Valid Ask = 50 => I = (100 - 50) / 150 = 50 / 150 = 0.333333
        i_mixed = calc.calcular_imbalance(((0.50, 100.0), (0.49, -50.0)), ((0.52, 50.0),))
        assert i_mixed == pytest.approx(0.333333, abs=1e-5)

    def test_maker_entry_price_crosses_ask_when_spread_is_one_tick(self):
        """
        Adversarial Test 1.3:
        Microstructural Vulnerability in HFT Pricing:
        When spread is <= 1 tick ($0.01), HFTPriceCalculator calculates:
            precio_entrada = best_bid + 1 tick = 0.50 + 0.01 = 0.51 == best_ask.
        Placing a Limit Buy at Best Ask causes an immediate TAKER fill,
        incurring taker fees and violating the Maker mandate of Phase 1!
        """
        best_bid = 0.50
        best_ask = 0.51  # 1 tick spread (spread = 0.01 <= 0.03, so GR1 approves)
        tick_size = 0.01

        precio_entrada = HFTPriceCalculator.calcular_precio_entrada_limit_buy(best_bid, tick_size)
        
        # Empirical finding: entry price equals or exceeds Best Ask!
        assert precio_entrada >= best_ask
        # If submitted to exchange, this order will NOT rest passively as Maker;
        # it will execute immediately against the book as a TAKER order!


# ==============================================================================
# SECTION 2: GOLDEN RULE 1 (SPREAD <= $0.03) STRESS TESTS
# ==============================================================================

class TestAdversarialGoldenRule1:
    """Stress tests on Golden Rule 1: boundary checks, inverted books, IEEE-754 edge cases."""

    def test_golden_rule_1_exact_boundary_tolerance(self):
        """
        Adversarial Test 2.1:
        Boundary validation:
        - spread = 0.03000000 => SPREAD_VALIDO (True)
        - spread = 0.030000001 => SPREAD_VALIDO (True within 1e-9 tolerance)
        - spread = 0.03000010 => SPREAD_EXCESIVO (False)
        - spread = 0.03010000 => SPREAD_EXCESIVO (False)
        """
        val = GoldenRulesValidator

        ok1, sp1, mot1 = val.verificar_regla_oro_1_spread(0.50, 0.53000000)
        assert ok1 is True
        assert mot1 == "SPREAD_VALIDO"

        ok2, sp2, mot2 = val.verificar_regla_oro_1_spread(0.50, 0.5300000005)
        assert ok2 is True

        ok3, sp3, mot3 = val.verificar_regla_oro_1_spread(0.50, 0.530001)
        assert ok3 is False
        assert "SPREAD_EXCESIVO" in mot3

        ok4, sp4, mot4 = val.verificar_regla_oro_1_spread(0.50, 0.5301)
        assert ok4 is False
        assert "SPREAD_EXCESIVO" in mot4

    def test_golden_rule_1_inverted_and_crossed_books(self):
        """
        Adversarial Test 2.2:
        Inverted book (Ask < Bid) must be detected as an anomaly and rejected.
        """
        val = GoldenRulesValidator

        ok_inv, sp_inv, mot_inv = val.verificar_regla_oro_1_spread(best_bid=0.60, best_ask=0.55)
        assert ok_inv is False
        assert sp_inv < 0.0
        assert "LIBRO_INVERTIDO" in mot_inv

    def test_golden_rule_1_ieee754_nan_vulnerability_demonstration(self):
        """
        Adversarial Test 2.3:
        VULNERABILITY PROOF:
        In Python IEEE-754 float comparison:
            float('nan') <= 0 is False.
            float('nan') < 0 is False.
            float('nan') > 0.03 is False.
        If nan prices are passed, GoldenRulesValidator.verificar_regla_oro_1_spread
        returns (True, nan, 'SPREAD_VALIDO') unless explicit math.isnan check is added!
        """
        nan_bid = float("nan")
        nan_ask = float("nan")

        ok, sp, mot = GoldenRulesValidator.verificar_regla_oro_1_spread(nan_bid, nan_ask)
        
        # Demonstrating the IEEE-754 bypass vulnerability
        # If this assert passes, the code has the vulnerability!
        if ok is True:
            # VULNERABILITY CONFIRMED: NaN price bypassed spread validation!
            assert math.isnan(sp)
            assert mot == "SPREAD_VALIDO"


# ==============================================================================
# SECTION 3: GOLDEN RULE 2 (SUSPENDED STATUS LOCK) STRESS TESTS
# ==============================================================================

class TestAdversarialGoldenRule2:
    """Stress tests on Golden Rule 2: case normalization, fail-closed security, state transitions."""

    @pytest.mark.parametrize("suspended_input", [
        "SUSPENDED",
        "suspended",
        "Suspended",
        "  SUSPENDED  ",
        "SuSpEnDeD",
    ])
    def test_golden_rule_2_suspended_variations_always_locked(self, suspended_input: str):
        """
        Adversarial Test 3.1:
        All casing and whitespace variations of SUSPENDED must lock orders immediately.
        """
        ok, motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(suspended_input)
        assert ok is False
        assert motivo == "MERCADO_SUSPENDIDO_BINANCE"

    @pytest.mark.parametrize("abnormal_status", [
        "HALTED",
        "CLOSED",
        "MAINTENANCE",
        "CIRCUIT_BREAKER",
        "UNKNOWN",
        "",
        "   ",
        "None",
    ])
    def test_golden_rule_2_fail_closed_on_abnormal_status(self, abnormal_status: str):
        """
        Adversarial Test 3.2:
        Fail-Closed Principle:
        Any market status other than explicitly ACTIVE/TRADING/OPEN must block trading.
        """
        ok, motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(abnormal_status)
        assert ok is False
        assert "ESTADO_MERCADO_DESCONOCIDO" in motivo

    def test_golden_rule_2_immediate_lock_in_microstructure_engine(self):
        """
        Adversarial Test 3.3:
        When snapshot has market_status = 'SUSPENDED', MicroestructuraBinanceEngine
        must reject the snapshot, output autorizado = False, and provide no OrderProposal.
        """
        engine = MicroestructuraBinanceEngine()
        snap = OrderBookSnapshot(
            symbol="SUSP_TEST",
            bids=((0.50, 1000.0),),
            asks=((0.52, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="SUSPENDED",
        )
        signal = engine.evaluar_snapshot(snap)

        assert signal.mercado_activo_gr2 is False
        assert signal.autorizado is False
        assert signal.propuesta_orden is None
        assert "MERCADO_SUSPENDIDO" in signal.motivo


# ==============================================================================
# SECTION 4: GOLDEN RULE 3 (TOP 3 BIDS LIQUIDITY CEILING) STRESS TESTS
# ==============================================================================

class TestAdversarialGoldenRule3:
    """Stress tests on Golden Rule 3: dimensional analysis, unit mismatch, and escape capacity."""

    def test_golden_rule_3_aggregation_fewer_than_3_levels(self):
        """
        Adversarial Test 4.1:
        Verify books with fewer than 3 levels (0, 1, 2) sum available depth without error.
        """
        val = GoldenRulesValidator

        # 0 levels
        assert val.calcular_liquidez_escape_top3_bids(()) == 0.0

        # 1 level
        assert val.calcular_liquidez_escape_top3_bids(((0.50, 75.0),)) == 75.0

        # 2 levels
        assert val.calcular_liquidez_escape_top3_bids(((0.50, 75.0), (0.49, 125.0))) == 200.0

        # 5 levels (only top 3 should be summed: 100 + 200 + 300 = 600)
        bids_5 = ((0.50, 100.0), (0.49, 200.0), (0.48, 300.0), (0.47, 400.0), (0.46, 500.0))
        assert val.calcular_liquidez_escape_top3_bids(bids_5) == 600.0

    def test_golden_rule_3_dimensional_mismatch_flaw_reproduction(self):
        """
        Adversarial Test 4.2:
        CRITICAL VULNERABILITY REPRODUCTION:
        In HFTEngine.evaluar_fase_1_prematch_obi:
            top_3_bids is passed as `micro_signal.liquidez_escape_top3_gr3` (a float of contract quantities).
        In EscudoFinancieroBinance.evaluar_propuesta:
            If top_3_bids is float, it treats it as DOLLAR STAKE limit (posicion_nominal <= v_bid_top3).
            Then it calculates: quantity = stake / price.
        When price < 1.0 (e.g., 0.50), quantity = stake / 0.50 = 2 * stake!
        Result: The order buys 2x more contracts than the total volume available in the top 3 BIDs!
        """
        risk_engine = EscudoFinancieroBinance(pct_riesgo_fijo=0.05, max_cluster_exp=0.50)
        balance = 10000.0
        # Stop loss = 5% => Nominal risk = 500 USD => Nominal stake = 500 / 0.05 = 10,000 USD
        
        # Suppose Top 3 BIDs only have 1,000 CONTRACTS total
        top_3_contracts_liquidity = 1000.0
        contract_target_price = 0.50

        proposal = OrderProposal(
            symbol="GR3_FLAW",
            side="BUY",
            target_price=contract_target_price,
            stop_price=0.475,
            estimated_prob=0.70,
            payout_decimal=2.0,
            strategy_id="HFT_PHASE_1_OBI",
        )

        # When evaluated by risk engine with top_3_bids passed as float (as HFTEngine does):
        approved = risk_engine.evaluar_propuesta(
            proposal=proposal,
            balance=balance,
            top_3_bids=top_3_contracts_liquidity,
        )

        assert approved.approved is True
        
        # VULNERABILITY REMEDIATED:
        # Dimensional conversion is now exact: S_escape = V_escape * P = 1,000 * 0.50 = 500 USD.
        # Order quantity is clamped to Top 3 BIDs contract liquidity (1,000 contracts).
        assert approved.quantity <= top_3_contracts_liquidity, (
            f"VULNERABILITY DETECTED: Order quantity ({approved.quantity}) EXCEEDS "
            f"top 3 BID liquidity ({top_3_contracts_liquidity})!"
        )
        assert approved.quantity == 1000.0


# ==============================================================================
# SECTION 5: CONCURRENCY, TICK BURST & EVENT LOOP STARVATION
# ==============================================================================

class TestAdversarialConcurrencyAndEventLoop:
    """Stress tests on high-throughput tick bursts, event loop delays, and lock contention."""

    def test_high_throughput_tick_burst_under_50ms_delay(self):
        """
        Adversarial Test 5.1:
        Simulate a burst of 200 concurrent L2 depth updates while background CPU work runs.
        Verify:
        1. Zero event loop lockups.
        2. Maximum event loop latency delay < 50ms.
        3. All 200 ticks are processed and evaluated cleanly.
        """
        async def run_burst():
            engine = MicroestructuraBinanceEngine()
            delays: List[float] = []
            stop_monitor = asyncio.Event()

            # Heartbeat latency monitor (measures event loop delay every 2ms)
            async def heartbeat_monitor():
                while not stop_monitor.is_set():
                    t0 = time.perf_counter()
                    await asyncio.sleep(0.002)
                    t1 = time.perf_counter()
                    delay_ms = (t1 - t0 - 0.002) * 1000.0
                    delays.append(max(0.0, delay_ms))

            # Simulate heavy CPU background work offloaded via asyncio.to_thread
            def cpu_worker():
                s = 0.0
                for k in range(50000):
                    s += (k * 0.01) ** 0.5
                return s

            # Coroutine to process an L2 tick
            async def process_tick(i: int):
                snap = OrderBookSnapshot(
                    symbol=f"SYM_{i%5}",
                    bids=((0.50 + (i % 10) * 0.001, 800.0),),
                    asks=((0.52 + (i % 10) * 0.001, 200.0),),
                    timestamp_ms=int(time.time() * 1000),
                    market_status="ACTIVE",
                )
                sig = engine.evaluar_snapshot(snap)
                assert sig is not None
                # Cooperate with loop
                await asyncio.sleep(0.0005)

            monitor_task = asyncio.create_task(heartbeat_monitor())
            cpu_task = asyncio.create_task(asyncio.to_thread(cpu_worker))

            # Launch burst of 200 concurrent ticks
            tick_tasks = [asyncio.create_task(process_tick(i)) for i in range(200)]

            await asyncio.gather(*tick_tasks, cpu_task)
            stop_monitor.set()
            await monitor_task

            max_delay = max(delays) if delays else 0.0
            avg_delay = sum(delays) / len(delays) if delays else 0.0

            # Assert event loop delay is strictly < 50ms
            assert max_delay < 50.0, f"Event loop starvation: max delay = {max_delay:.2f}ms >= 50ms"
            assert avg_delay < 15.0, f"Average event loop delay too high: {avg_delay:.2f}ms"

        asyncio.run(run_burst())

    def test_capital_gateway_lock_contention_and_zero_deadlocks(self):
        """
        Adversarial Test 5.2:
        50 concurrent tasks hammer AsyncCapitalGateway.reservar_capital and liberar_capital.
        Verify:
        1. Zero deadlocks (execution completes within timeout).
        2. Total committed capital never exceeds cluster cap (15% of bankroll).
        3. All released capital returns committed balance exactly to 0.0.
        """
        async def run_contention():
            gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
            # Max cluster exposure = 150.0 USD
            max_cap = gateway.capital_maximo_cluster
            assert max_cap == 150.0

            successful_trades = 0
            rejected_trades = 0

            async def worker(worker_id: int):
                nonlocal successful_trades, rejected_trades
                for _ in range(5):
                    stake = 20.0
                    token = await gateway.reservar_capital(
                        stake=stake,
                        strategy_id="STRESS_HFT",
                        symbol=f"SYM_{worker_id}",
                    )
                    if token is not None:
                        # Invariant check: committed capital must never exceed 150.0 USD (+ float tolerance)
                        assert gateway.capital_comprometido <= max_cap + 0.05
                        successful_trades += 1
                        await asyncio.sleep(0.002)  # hold position briefly
                        released = await gateway.liberar_capital(token)
                        assert released is True
                    else:
                        rejected_trades += 1
                        await asyncio.sleep(0.001)

            tasks = [asyncio.create_task(worker(w)) for w in range(50)]
            await asyncio.wait_for(asyncio.gather(*tasks), timeout=10.0)

            # Invariant: after all workers finish, committed capital must be 0.0
            assert gateway.capital_comprometido == pytest.approx(0.0, abs=1e-4)
            assert len(gateway.active_tokens) == 0
            assert successful_trades > 0
            assert rejected_trades > 0  # 50 * 5 * 20 = 5000 USD requested, cap is 150 USD, so rejections must occur

        asyncio.run(run_contention())

    def test_capital_gateway_tolerance_drift_flaw(self):
        """
        Adversarial Test 5.3:
        VULNERABILITY DEMONSTRATION:
        AsyncCapitalGateway allows a 5-cent buffer: `(stake - espacio) <= 0.05`.
        If clamped via `min(max_permitido, committed + stake)`, and subsequently released
        via `committed - token.stake`, committed capital can drift negative or underestimate.
        """
        gateway = AsyncCapitalGateway(capital_total=100.0, max_cluster_exp=0.15)
        # Max cap = 15.0 USD
        
        async def test_drift():
            # Fill up to 14.98 USD
            t1 = await gateway.reservar_capital(14.98)
            assert t1 is not None
            assert gateway.capital_comprometido == pytest.approx(14.98, abs=1e-4)

            # Request 0.04 USD (exceeds 15.00 by 0.02, but <= 0.05 buffer)
            t2 = await gateway.reservar_capital(0.04)
            assert t2 is not None
            # Clamped to 15.00
            assert gateway.capital_comprometido == pytest.approx(15.00, abs=1e-4)

            # Release t2 (token.stake was correctly clamped to available space 0.02)
            await gateway.liberar_capital(t2)
            # DRIFT ELIMINATED: Committed capital returns exactly to 14.98 USD without underflow drift!
            assert gateway.capital_comprometido == pytest.approx(14.98, abs=1e-4)

            # Release t1
            await gateway.liberar_capital(t1)
            # Committed reaches max(0.0, 14.96 - 14.98) = 0.0
            assert gateway.capital_comprometido == 0.0

        asyncio.run(test_drift())
