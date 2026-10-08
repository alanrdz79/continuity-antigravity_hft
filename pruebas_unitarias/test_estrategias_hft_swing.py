# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_estrategias_hft_swing
============================================
Suite de Pruebas Unitarias y de Concurrencia para los Motores HFT y Swing Trading:
1. Cobertura Universal de 7 Deportes (Fútbol, Béisbol, Fútbol Americano, Básquetbol, Tenis, Hockey, eSports).
2. Lógica HFT de 4 Fases (Fase 1 OBI, Fase 2 limpiar_mesa, Fase 3 Latency Sniping, Fase 4 Time Decay 75-90).
3. Directivas de Negocio:
   - Estrategia A (Time Decay 65-70 min, retención 3-5 min, venta antes de final).
   - Estrategia B (Caza de sobre-reacciones en favorito, venta en primera jugada peligrosa).
4. Integración estricta con Reglas de Oro 1, 2, 3 y EscudoFinancieroBinance.
5. Motor Ortogonal de Swing Trading:
   - Descarga de CPU a hilos mediante `asyncio.to_thread`.
   - Coordinación atómica de capital mediante tokens (techo de clúster del 15%).
6. Concurrencia HFT + Swing sin bloqueo de event loop (Heartbeat delay < 50 ms).
"""

import asyncio
import time
import pytest
from typing import Dict, List, Tuple

from continuitis.microestructura_binance import (
    DEFAULT_TICK_SIZE,
    MAX_SPREAD_PERMITIDO,
    MicroestructuraBinanceEngine,
    OrderBookSnapshot,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance
from estrategias.hft_engine import (
    HFTEngine,
    HftPosition,
    HftSignal,
    MatchLiveState,
    SPORT_CONFIGS,
    SportType,
)
from estrategias.swing_engine import (
    AsyncCapitalGateway,
    CapitalReservationToken,
    SwingEngine,
    SwingPosition,
    computar_analisis_macro_cpu,
)


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE — 7 DEPORTES & 4 FASES HFT
# ==============================================================================

class TestHFTTier1UniversalSportsAndPhases:
    """Verificación de especificación para las 7 disciplinas y las 4 fases HFT."""

    def test_universal_7_sports_configuration_and_coverage(self):
        """
        Directiva 1: Cobertura universal de 7 deportes.
        Verifica que SPORT_CONFIGS define los 7 deportes con sus metadatos y ventanas operativas.
        """
        deportes_esperados = [
            SportType.SOCCER,
            SportType.BASEBALL,
            SportType.AMERICAN_FOOTBALL,
            SportType.BASKETBALL,
            SportType.TENNIS,
            SportType.HOCKEY,
            SportType.ESPORTS,
        ]
        assert len(SPORT_CONFIGS) == 7
        for dep in deportes_esperados:
            assert dep in SPORT_CONFIGS
            cfg = SPORT_CONFIGS[dep]
            assert cfg.duration_standard_minutes > 0
            assert cfg.stagnant_attack_threshold > 0
            assert cfg.strategy_a_window_start_min < cfg.strategy_a_window_end_min
            assert cfg.phase_4_window_start_min < cfg.phase_4_window_end_min

    def test_hft_fase_1_prematch_obi_entry_and_exit_pricing(self):
        """
        Fase 1: Pre-match OBI scalping (T-120m a T-5m).
        - Desequilibrio comprador I >= 0.60 (dominancia >= 80%).
        - Entrada Maker: Best Bid + 1 tick.
        - Salida Maker: Best Ask + 2 ticks.
        - Exposición objetivo: 2 a 10s.
        """
        hft = HFTEngine(tick_size=0.01, default_phase1_timeout_s=5.0)
        match = MatchLiveState(
            match_id="M_SOCCER_PRE_1",
            symbol="SOCCER_PRE",
            sport=SportType.SOCCER,
            time_to_kickoff_minutes=45.0,  # T-45m (dentro de [5, 120])
            is_live=False,
        )
        snap = OrderBookSnapshot(
            symbol="SOCCER_PRE",
            bids=((0.50, 850.0), (0.49, 150.0)),
            asks=((0.52, 100.0), (0.53, 100.0)),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = hft.evaluar_fase_1_prematch_obi(snap, match, balance=1000.0)

        assert signal.authorized is True
        assert signal.action in ("LIMIT_BUY", "BUY_LIMIT")
        assert signal.phase == "FASE_1_PREMATCH"
        # Best Bid (0.50) + 1 tick (0.01) = 0.51
        assert signal.price == pytest.approx(0.51, abs=1e-4)
        # Best Ask (0.52) + 2 ticks (0.02) = 0.54
        assert signal.metadata["target_exit_price"] == pytest.approx(0.54, abs=1e-4)
        assert signal.metadata["timeout_s"] == 5.0
        assert len(hft.active_positions) == 1

    def test_hft_fase_2_limpiar_mesa_atomic_cleanup_at_t_minus_5m(self):
        """
        Fase 2: Transición a T-5m (limpiar_mesa).
        - Cancela de forma atómica todas las órdenes pendientes.
        - Liquida a mercado cualquier posición abierta en BIDs.
        - Regla Innegociable: Exposición en min 0 = 0%; USDT = 100%.
        """
        hft = HFTEngine(tick_size=0.01)
        sym = "NFL_PRE_CLEANUP"

        # Simular una posición abierta previa y una orden pendiente
        hft.pending_orders["ORD_T5_1"] = None  # Mock clave
        from estrategias.hft_engine import HftOrder
        hft.pending_orders["ORD_T5_1"] = HftOrder(
            order_id="ORD_T5_1",
            symbol=sym,
            side="BUY",
            order_type="LIMIT",
            price=0.60,
            quantity=50.0,
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            timestamp=time.time(),
            status="PENDING",
        )
        hft.active_positions["POS_T5_1"] = HftPosition(
            position_id="POS_T5_1",
            symbol=sym,
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=0.60,
            quantity=50.0,
            entry_time=time.time(),
            target_exit_price=0.63,
            timeout_seconds=5.0,
            status="OPEN",
        )

        snap = OrderBookSnapshot(
            symbol=sym,
            bids=((0.59, 500.0),),
            asks=((0.61, 500.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        resultado = hft.ejecutar_fase_2_limpiar_mesa(sym, snap)

        assert resultado["regla_innegociable_cumplida"] is True
        assert resultado["exposicion_final_pct"] == 0.0
        assert resultado["liquidez_usdt_pct"] == 100.0
        assert "ORD_T5_1" in resultado["ordenes_canceladas"]
        assert len(resultado["liquidaciones_mercado"]) == 1
        assert resultado["liquidaciones_mercado"][0]["exit_price"] == 0.59
        assert len(hft.active_positions) == 0
        assert len(hft.pending_orders) == 0

    def test_hft_fase_3_in_play_latency_sniping(self):
        """
        Fase 3: In-Play Latency Sniping (minutos 1 al 75).
        - Ocurre evento en tiempo real (ej. GOAL) antes de suspensión de Binance.
        - Sniping compra contrato en Ask desactualizado.
        """
        hft = HFTEngine(tick_size=0.01)
        match = MatchLiveState(
            match_id="M_LIVE_SNIPE",
            symbol="SOCCER_LIVE",
            sport=SportType.SOCCER,
            is_live=True,
            minute=35.0,
            score_home=1,
            score_away=0,
            last_event="GOAL",
            last_event_timestamp=time.time() - 0.200,  # Ocurrió hace 200 ms
        )
        snap = OrderBookSnapshot(
            symbol="SOCCER_LIVE",
            bids=((0.55, 300.0),),
            asks=((0.57, 200.0),),  # Ask desactualizado
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = hft.snipe_desfase_oraculo(
            event_type="GOAL",
            event_timestamp=match.last_event_timestamp,
            snapshot=snap,
            match_state=match,
            balance=1000.0,
        )

        assert signal.authorized is True
        assert signal.action in ("LIMIT_BUY", "BUY_LIMIT")
        assert signal.phase == "FASE_3_SNIPING"
        assert signal.price == pytest.approx(0.57, abs=1e-4)
        assert "GOAL" in signal.reason
        assert len(hft.active_positions) == 1

    def test_hft_fase_4_time_decay_scalping_draw_75_to_90(self):
        """
        Fase 4: Time Decay Exponencial (Minutos 75 al 90).
        - Marcador en empate.
        - Peligro tendiendo a cero (danger attacks <= 0.20/min).
        - Ventana de 60 a 90 segundos.
        """
        hft = HFTEngine(tick_size=0.01, default_phase4_timeout_s=75.0)
        match = MatchLiveState(
            match_id="M_DECAY_4",
            symbol="SOCCER_TIE_80M",
            sport=SportType.SOCCER,
            is_live=True,
            minute=80.0,  # Minuto 80 (dentro de [75, 90])
            score_home=1,
            score_away=1,  # Empate
            danger_attacks_per_min=0.10,  # Muy bajo peligro
        )
        snap = OrderBookSnapshot(
            symbol="SOCCER_TIE_80M",
            bids=((0.85, 900.0),),
            asks=((0.87, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = hft.evaluar_fase_4_time_decay_scalping(snap, match, balance=1000.0)

        assert signal.authorized is True
        assert signal.action in ("LIMIT_BUY", "BUY_LIMIT")
        assert signal.phase == "FASE_4_TIME_DECAY"
        assert signal.price == pytest.approx(0.86, abs=1e-4)  # Best Bid (0.85) + 1 tick
        assert signal.metadata["timeout_s"] == 75.0
        assert len(hft.active_positions) == 1


# ==============================================================================
# TIER 2: BUSINESS DIRECTIVES — STRATEGY A & STRATEGY B
# ==============================================================================

class TestHFTTier2BusinessDirectivesStrategyAandB:
    """Verificación de las Directivas de Negocio A y B."""

    def test_strategy_a_time_decay_65_to_70_stagnant_game(self):
        """
        Estrategia A: Explotación del Time Decay.
        - Minutos 65-70 en partido estancado (ataques <= 0.25).
        - Comprar share de resultado y retención de 3 a 5 min (180-300s).
        - Venta antes de finalizar.
        """
        hft = HFTEngine(tick_size=0.01, default_strategy_a_timeout_s=240.0)
        match = MatchLiveState(
            match_id="M_STRA_1",
            symbol="BASKETBALL_Q4",
            sport=SportType.BASKETBALL,
            is_live=True,
            minute=36.0,  # Minuto 36 en NBA (ventana [34, 38] según SPORT_CONFIGS)
            danger_attacks_per_min=0.20,  # Estancado
        )
        snap = OrderBookSnapshot(
            symbol="BASKETBALL_Q4",
            bids=((0.70, 600.0),),
            asks=((0.72, 400.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = hft.evaluar_estrategia_a_time_decay(snap, match, balance=1000.0)

        assert signal.authorized is True
        assert signal.action in ("LIMIT_BUY", "BUY_LIMIT")
        assert signal.strategy_id == "STRATEGY_A_TIME_DECAY"
        assert signal.price == pytest.approx(0.71, abs=1e-4)  # Best Bid + 1 tick
        assert signal.metadata["timeout_s"] == 240.0
        assert len(hft.active_positions) == 1

    def test_strategy_b_overreaction_hunting_entry_on_panic_dip(self):
        """
        Estrategia B: Caza de Reacciones Exageradas.
        - Favorito dominante (posesión >= 60% o xG favorable) sufre desplome de precio por pánico.
        - Comprar el dip con orden límite.
        """
        hft = HFTEngine(tick_size=0.01)
        match = MatchLiveState(
            match_id="M_STRB_1",
            symbol="SOCCER_FAV_DIP",
            sport=SportType.SOCCER,
            is_live=True,
            minute=30.0,
            score_home=0,
            score_away=1,  # Recibió gol
            dominant_favorite="HOME",
            possession_home_pct=65.0,  # Domina posesión
            xg_home=1.80,
            xg_away=0.20,              # Domina xG
            recent_dangerous_attack=False,
        )
        snap = OrderBookSnapshot(
            symbol="SOCCER_FAV_DIP",
            bids=((0.45, 500.0),),
            asks=((0.47, 500.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = hft.evaluar_estrategia_b_overreaction(snap, match, balance=1000.0)

        assert signal.authorized is True
        assert signal.strategy_id == "STRATEGY_B_OVERREACTION"
        assert signal.price == pytest.approx(0.46, abs=1e-4)
        assert signal.metadata["wait_for_next_attack"] is True
        assert len(hft.active_positions) == 1

    def test_strategy_b_exit_on_next_dangerous_attack_without_waiting_for_goal(self):
        """
        Estrategia B: Venta en el rebote especulativo tras la primera jugada peligrosa a favor,
        SIN esperar a que anote gol.
        """
        hft = HFTEngine(tick_size=0.01)
        sym = "SOCCER_FAV_REBOUND"

        # Simular posición abierta de Estrategia B
        pos = HftPosition(
            position_id="POS_STRB_EXIT",
            symbol=sym,
            strategy_id="STRATEGY_B_OVERREACTION",
            phase="ESTRATEGIA_B",
            side="BUY",
            entry_price=0.45,
            quantity=100.0,
            entry_time=time.time(),
            target_exit_price=0.48,
            timeout_seconds=300.0,
            status="OPEN",
        )
        hft.active_positions["POS_STRB_EXIT"] = pos

        # Ocurre ataque peligroso del favorito (sin gol)
        match = MatchLiveState(
            match_id="M_STRB_EXIT",
            symbol=sym,
            sport=SportType.SOCCER,
            is_live=True,
            minute=32.0,
            score_home=0,
            score_away=1,  # Marcador sigue 0-1 (¡NO hubo gol!)
            recent_dangerous_attack=True,  # ¡Ataque peligroso ocurrió!
        )
        snap = OrderBookSnapshot(
            symbol=sym,
            bids=((0.49, 800.0),),  # Precio rebotó en Bid
            asks=((0.51, 200.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        salidas = hft.evaluar_salida_rebote_estrategia_b(sym, match, snap)

        assert len(salidas) == 1
        salida = salidas[0]
        assert salida.action == "SELL_LIMIT"
        assert salida.price == pytest.approx(0.49, abs=1e-4)
        assert salida.metadata["pnl"] == pytest.approx((0.49 - 0.45) * 100.0, abs=1e-4)
        assert len(hft.active_positions) == 0
        assert len(hft.closed_positions) == 1


# ==============================================================================
# TIER 3: GOLDEN RULES & CROSS-MODULE RISK INTEGRATION
# ==============================================================================

class TestHFTTier3GoldenRulesAndRiskIntegration:
    """Verificación de las 3 Reglas de Oro y Escudo Financiero."""

    def test_golden_rule_1_spread_exceeds_0_03_rejects_any_hft_action(self):
        """Regla de Oro 1: Spread máximo <= $0.03. Si es mayor, no operar."""
        hft = HFTEngine()
        match = MatchLiveState(
            match_id="M_WIDE_SPREAD",
            symbol="WIDE_SPREAD",
            time_to_kickoff_minutes=30.0,
        )
        snap = OrderBookSnapshot(
            symbol="WIDE_SPREAD",
            bids=((0.50, 800.0),),
            asks=((0.54, 200.0),),  # Spread = 0.04 > 0.03
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = hft.evaluar_fase_1_prematch_obi(snap, match, balance=1000.0)
        assert signal.authorized is False
        assert "SPREAD_EXCESIVO" in signal.reason

    def test_golden_rule_2_suspended_market_locks_new_orders(self):
        """Regla de Oro 2: MarketStatus == 'SUSPENDED' bloquea cualquier nueva orden."""
        hft = HFTEngine()
        match = MatchLiveState(
            match_id="M_SUSPENDED",
            symbol="VAR_SUSPENDED",
            is_live=True,
            minute=50.0,
        )
        snap = OrderBookSnapshot(
            symbol="VAR_SUSPENDED",
            bids=((0.50, 900.0),),
            asks=((0.52, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="SUSPENDED",
        )

        signal = hft.snipe_desfase_oraculo("GOAL", time.time(), snap, match, balance=1000.0)
        assert signal.authorized is False
        assert "SUSPENDIDO" in signal.reason

    def test_golden_rule_3_top3_bids_liquidity_escape_constrains_position_size(self):
        """
        Regla de Oro 3: Posición acotada al volumen disponible en los primeros 3 niveles de BID.
        """
        risk = EscudoFinancieroBinance(max_cluster_exp=0.15)
        hft = HFTEngine(risk_engine=risk)
        match = MatchLiveState(
            match_id="M_LIQ_CLAMP",
            symbol="LOW_LIQ_BIDS",
            time_to_kickoff_minutes=60.0,
        )
        # BIDs con liquidez muy limitada (solo 15 unidades en top 3)
        snap = OrderBookSnapshot(
            symbol="LOW_LIQ_BIDS",
            bids=((0.50, 5.0), (0.49, 5.0), (0.48, 5.0)),
            asks=((0.52, 1.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        signal = hft.evaluar_fase_1_prematch_obi(snap, match, balance=5000.0)
        # La cantidad comprada debe estar acotada por la liquidez de escape
        assert signal.authorized is True
        assert signal.quantity <= (15.0 / 0.51) + 1.0


# ==============================================================================
# TIER 4: ORTHOGONAL SWING ENGINE & NON-BLOCKING CONCURRENCY PIPELINE
# ==============================================================================

class TestSwingAndConcurrencyTier4Pipeline:
    """Verificación del Motor Swing y pipeline de concurrencia no bloqueante."""

    def test_swing_heavy_cpu_computation_pure_function(self):
        """Verifica la función pura de cómputo intensivo Monte Carlo de Swing."""
        velas = [
            (i * 3600, 0.50 + (i * 0.005), 0.52 + (i * 0.005), 0.49 + (i * 0.005), 0.51 + (i * 0.005))
            for i in range(20)
        ]
        res = computar_analisis_macro_cpu("SWING_TEST", velas, sim_paths=2000)

        assert res["symbol"] == "SWING_TEST"
        assert res["trend_direction"] in ("BULLISH", "BEARISH", "NEUTRAL")
        assert 0.0 <= res["monte_carlo_win_prob"] <= 1.0
        assert res["compute_time_ms"] >= 0.0

    @pytest.mark.asyncio
    async def test_swing_engine_offloads_cpu_via_asyncio_to_thread(self):
        """
        Verifica que SwingEngine analiza oportunidades macro offloading a hilo
        mediante asyncio.to_thread sin bloquear el event loop.
        """
        swing = SwingEngine(balance=1000.0)
        velas = [
            (i * 3600, 0.40 + (i * 0.01), 0.42 + (i * 0.01), 0.39 + (i * 0.01), 0.41 + (i * 0.01))
            for i in range(25)
        ]

        analisis = await swing.analizar_oportunidad_macro("SWING_ASYNC", velas, sim_paths=5000)

        assert analisis.symbol == "SWING_ASYNC"
        assert analisis.trend_direction == "BULLISH"
        assert analisis.recommended_action == "BUY"
        assert analisis.compute_time_ms > 0.0

    @pytest.mark.asyncio
    async def test_swing_atomic_capital_reservation_and_cluster_cap_enforcement(self):
        """
        Verifica que SwingEngine reserva capital atómicamente respetando el techo del 15% (150 USD de 1000 USD).
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        swing = SwingEngine(capital_gateway=gateway, balance=1000.0)

        # 1. Primera reserva válida (50 USD <= 150 USD)
        tok1 = await gateway.reservar_capital(50.0, "SWING_1", "SYM_1")
        assert tok1 is not None
        assert gateway.capital_comprometido == pytest.approx(50.0, abs=1e-4)

        # 2. Segunda reserva válida (80 USD -> total 130 USD <= 150 USD)
        tok2 = await gateway.reservar_capital(80.0, "SWING_2", "SYM_2")
        assert tok2 is not None
        assert gateway.capital_comprometido == pytest.approx(130.0, abs=1e-4)

        # 3. Tercera reserva que excedería el techo de 150 USD (solicita 30 USD -> 160 USD > 150 USD)
        tok3 = await gateway.reservar_capital(30.0, "SWING_3", "SYM_3")
        assert tok3 is None  # Rechazada por techo de clúster

        # 4. Liberar primera reserva
        liberado = await gateway.liberar_capital(tok1)
        assert liberado is True
        assert gateway.capital_comprometido == pytest.approx(80.0, abs=1e-4)

        # 5. Ahora la reserva de 30 USD sí cabe (80 + 30 = 110 <= 150)
        tok3_retry = await gateway.reservar_capital(30.0, "SWING_3", "SYM_3")
        assert tok3_retry is not None
        assert gateway.capital_comprometido == pytest.approx(110.0, abs=1e-4)

    @pytest.mark.asyncio
    async def test_non_blocking_concurrency_hft_and_swing_zero_starvation(self):
        """
        Prueba maestra de concurrencia:
        Ejecuta simultáneamente:
        1. Bucle HFT de micro-ticks continuos evaluando OBI y spreads.
        2. Bucle Swing con simulaciones Monte Carlo pesadas descargadas a hilos vía asyncio.to_thread.
        3. Monitor de latido (heartbeat) midiendo demora del event loop.
        Garantía: Demora máxima del latido < 50 ms (cero inanición de bucle).
        """
        hft = HFTEngine()
        gateway = AsyncCapitalGateway(capital_total=2000.0, max_cluster_exp=0.15)
        swing = SwingEngine(capital_gateway=gateway, balance=2000.0)

        delays_latido: List[float] = []
        stop_event = asyncio.Event()

        # Monitor de latido del event loop (despierta cada 5 ms)
        async def heartbeat_monitor():
            while not stop_event.is_set():
                t0 = time.perf_counter()
                await asyncio.sleep(0.005)
                t1 = time.perf_counter()
                delay_ms = max(0.0, (t1 - t0 - 0.005) * 1000.0)
                delays_latido.append(delay_ms)

        # Tarea HFT rápida
        hft_ticks_procesados = 0
        async def tarea_hft_loop():
            nonlocal hft_ticks_procesados
            snap = OrderBookSnapshot(
                symbol="HFT_CONC",
                bids=((0.50, 850.0),),
                asks=((0.52, 150.0),),
                timestamp_ms=int(time.time() * 1000),
                market_status="ACTIVE",
            )
            match = MatchLiveState(match_id="M_HFT_CONC", symbol="HFT_CONC", time_to_kickoff_minutes=30.0)
            for _ in range(40):
                if stop_event.is_set():
                    break
                sig = hft.evaluar_fase_1_prematch_obi(snap, match, balance=1000.0)
                assert sig.authorized is True
                hft_ticks_procesados += 1
                await asyncio.sleep(0.002)

        # Tarea Swing con cómputo pesado Monte Carlo
        swing_ciclos_completados = 0
        async def tarea_swing_loop():
            nonlocal swing_ciclos_completados
            velas = [
                (i * 3600, 0.45 + (i * 0.005), 0.47 + (i * 0.005), 0.44 + (i * 0.005), 0.46 + (i * 0.005))
                for i in range(30)
            ]
            for _ in range(5):
                if stop_event.is_set():
                    break
                # Cómputo pesado Monte Carlo (10,000 caminos) offloaded a hilo
                analisis = await swing.analizar_oportunidad_macro("SWING_CONC", velas, sim_paths=10000)
                assert analisis.compute_time_ms >= 0.0
                swing_ciclos_completados += 1
                await asyncio.sleep(0.005)

        t_mon = asyncio.create_task(heartbeat_monitor())
        t_hft = asyncio.create_task(tarea_hft_loop())
        t_sw = asyncio.create_task(tarea_swing_loop())

        await asyncio.gather(t_hft, t_sw)
        stop_event.set()
        await t_mon

        assert hft_ticks_procesados == 40
        assert swing_ciclos_completados == 5

        max_delay = max(delays_latido) if delays_latido else 0.0
        # Demora máxima del latido debe ser < 50 ms (lejos de los 800 ms del disyuntor)
        assert max_delay < 50.0, f"Riesgo de inanición en event loop: max delay = {max_delay:.2f} ms"
