# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_r3_hft_amm_ev
====================================
Suite de Pruebas Unitarias y de Integración para el Requisito R3 / Milestone M3:
- Orquestación de las 4 Fases HFT
- Salidas por Valor Esperado (EV) antes y durante el partido en Deportes y ESports
- Fase 2 T-5m limpiar_mesa con 0% de exposición verificada
- Fase 3 In-Play Latency Sniping ante eventos oraculares
- Fase 4 Time Decay Scalping
- Estrategia V: DualBuyProposal y Paridad Binaria Atómica
- Estrategia V: Desviación de Curva AMM y Scalp de Rebote
- Ejecución en Orquestador Continuo (step_hft_cycle, step_amm_cycle, step_swing_cycle)
"""

import asyncio
import time
import pytest
from typing import Dict, Any, List

from conectores.binance_prediction import (
    BinancePredictionConnector,
    OrderBookSnapshot,
)
from continuitis.microestructura_binance import (
    MicroestructuraBinanceEngine,
    OrderProposal,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance
from continuitis.tesoreria import GestorTesoreria
from continuitis.auditor_metricas import AuditorMetricas, TradeResult

from estrategias.hft_engine import (
    HFTEngine,
    HftSignal,
    HftPosition,
    MatchLiveState,
    SportType,
    SPORT_CONFIGS,
)
from estrategias.arbitraje_amm import (
    EstrategiaVArbitrajeAMM,
    ArbitrageAMMEngine,
    ArbitrageOpportunityType,
    ArbitrageSignal,
    DualBuyProposal,
    ArbitrageConfig,
)
from estrategias.swing_engine import AsyncCapitalGateway
from orquestadores_principales.HFT_BINANCE import (
    ContinuityHFTBinanceOrchestrator,
)


def make_snapshot(
    symbol: str,
    bid_px: float = 0.50,
    bid_qty: float = 500.0,
    ask_px: float = 0.52,
    ask_qty: float = 300.0,
    market_status: str = "ACTIVE",
    timestamp_ms: int = 0,
) -> OrderBookSnapshot:
    """Genera un OrderBookSnapshot inmutable para pruebas."""
    ts = timestamp_ms or int(time.time() * 1000)
    return OrderBookSnapshot(
        symbol=symbol,
        bids=((bid_px, bid_qty), (round(bid_px - 0.01, 4), bid_qty * 0.5)),
        asks=((ask_px, ask_qty), (round(ask_px + 0.01, 4), ask_qty * 0.5)),
        timestamp_ms=ts,
        market_status=market_status,
    )


# ==============================================================================
# SECCIÓN 1: SALIDAS POR VALOR ESPERADO (EV) ANTES Y DURANTE EN DEPORTES Y ESPORTS
# ==============================================================================

class TestTargetEVEarlyExitsSportsAndESports:
    """
    Verifica que las posiciones se abran y cierren ANTES ("pre-match") y
    DURANTE ("in-play") el evento al cumplirse el valor esperado (EV)
    o el timeout de exposición, sin esperar a que concluya el evento.
    Aplica tanto a deportes tradicionales como a ESports.
    """

    @pytest.mark.asyncio
    async def test_ev_exit_prematch_soccer_before_kickoff(self):
        """
        Pre-Match ('antes'): Posición abierta en Fase 1 (fútbol) a T-45m.
        Entrada en 0.51, target_exit_price = 0.54.
        Cuando el Best Bid del libro sube a 0.54 (cumplimiento de EV),
        _vigilar_y_cerrar_posiciones_abiertas cierra la posición inmediatamente
        con beneficio, sin esperar al inicio del partido ni al final.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        # Estado del partido a 45 minutos del inicio (Pre-match)
        orch.live_matches["SOCCER_PRED_USDT"] = MatchLiveState(
            match_id="M_SOCCER_PRE",
            symbol="SOCCER_PRED_USDT",
            sport=SportType.SOCCER,
            time_to_kickoff_minutes=45.0,
            is_live=False,
        )

        # Simular posición abierta en Fase 1
        pos = orch.hft_engine.registrar_orden_ejecutada(
            signal=HftSignal(
                symbol="SOCCER_PRED_USDT",
                action="LIMIT_BUY",
                strategy_id="HFT_PHASE_1_OBI",
                phase="FASE_1_PREMATCH",
                price=0.51,
                quantity=20.0,
                estimated_prob=0.85,
                payout_decimal=1.96,
                reason="Pre-match Maker OBI",
                authorized=True,
                metadata={"target_exit_price": 0.54, "timeout_s": 10.0},
            ),
            order_id="ORD_PRE_001",
            executed_price=0.51,
            executed_qty=20.0,
        )
        pos.target_exit_price = 0.54
        assert pos.position_id in orch.hft_engine.active_positions
        assert pos.status == "OPEN"

        # Libro en el mercado se mueve: Best Bid alcanza 0.54 (EV cumplido)
        snap_ev = make_snapshot("SOCCER_PRED_USDT", bid_px=0.54, ask_px=0.55)

        # Ejecutar vigilancia de posiciones
        trades = await orch._vigilar_y_cerrar_posiciones_abiertas("SOCCER_PRED_USDT", snap_ev)

        assert len(trades) == 1
        trade = trades[0]
        assert trade.symbol == "SOCCER_PRED_USDT"
        assert trade.is_win is True
        assert trade.pnl == pytest.approx((0.54 - 0.51) * 20.0, abs=1e-4) # +0.60 USD
        assert pos.position_id not in orch.hft_engine.active_positions
        assert orch.auditor.total_trades >= 1
        assert orch.tesoreria.balance > 100.0

    @pytest.mark.asyncio
    async def test_ev_exit_inplay_esports_during_match(self):
        """
        In-Play ('durante'): Posición abierta en ESports (LoL / CS2) en minuto 29.
        Duración estándar 35 min. Entrada en 0.50, target_exit_price = 0.52.
        Al minuto 30, el Best Bid sube a 0.52 (EV cumplido).
        _vigilar_y_cerrar_posiciones_abiertas cierra la posición inmediatamente
        capturando el beneficio, sin esperar a que la partida termine en min 35.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["ESPORTS_LOL_USDT"],
            capital_inicial=200.0,
            mock_mode=True,
        )

        # Estado del partido en vivo en ESports (minuto 29 de 35)
        orch.live_matches["ESPORTS_LOL_USDT"] = MatchLiveState(
            match_id="M_LOL_FINALS",
            symbol="ESPORTS_LOL_USDT",
            sport=SportType.ESPORTS,
            minute=29.0,
            is_live=True,
            time_to_kickoff_minutes=None,
        )

        pos = orch.hft_engine.registrar_orden_ejecutada(
            signal=HftSignal(
                symbol="ESPORTS_LOL_USDT",
                action="LIMIT_BUY",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=0.50,
                quantity=30.0,
                estimated_prob=0.80,
                payout_decimal=2.00,
                reason="ESports Time Decay Scalp",
                authorized=True,
                metadata={"target_exit_price": 0.52, "timeout_s": 60.0},
            ),
            order_id="ORD_LOL_002",
            executed_price=0.50,
            executed_qty=30.0,
        )
        pos.target_exit_price = 0.52
        assert pos.position_id in orch.hft_engine.active_positions

        # Libro en vivo refleja salto de precio a 0.52 en min 30 (partido sigue en vivo)
        snap_ev = make_snapshot("ESPORTS_LOL_USDT", bid_px=0.52, ask_px=0.53)

        trades = await orch._vigilar_y_cerrar_posiciones_abiertas("ESPORTS_LOL_USDT", snap_ev)

        assert len(trades) == 1
        t = trades[0]
        assert t.is_win is True
        assert t.pnl == pytest.approx((0.52 - 0.50) * 30.0, abs=1e-4) # +0.60 USD
        assert pos.position_id not in orch.hft_engine.active_positions
        assert orch.live_matches["ESPORTS_LOL_USDT"].is_live is True # Sigue en juego sin esperar término

    @pytest.mark.asyncio
    async def test_timeout_exit_prematch_and_inplay(self):
        """
        Verifica que si no se alcanza el target_exit_price antes del timeout de exposición,
        la posición se liquida a mercado de forma inmediata sin quedarse atrapada.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["BASKET_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        # Crear posición con timeout expirado
        pos = orch.hft_engine.registrar_orden_ejecutada(
            signal=HftSignal(
                symbol="BASKET_PRED_USDT",
                action="LIMIT_BUY",
                strategy_id="HFT_PHASE_1_OBI",
                phase="FASE_1_PREMATCH",
                price=0.51,
                quantity=10.0,
                estimated_prob=0.80,
                payout_decimal=1.96,
                reason="Pre-match timeout test",
                authorized=True,
                metadata={"target_exit_price": 0.55, "timeout_s": 5.0},
            ),
            order_id="ORD_BASKET_TIMEOUT",
            executed_price=0.51,
            executed_qty=10.0,
        )
        pos.entry_time = time.time() - 10.0 # Expiró hace 5s
        pos.timeout_seconds = 5.0

        snap = make_snapshot("BASKET_PRED_USDT", bid_px=0.50, ask_px=0.52)
        trades = await orch._vigilar_y_cerrar_posiciones_abiertas("BASKET_PRED_USDT", snap)

        assert len(trades) == 1
        assert pos.position_id not in orch.hft_engine.active_positions
        assert trades[0].symbol == "BASKET_PRED_USDT"


# ==============================================================================
# SECCIÓN 2: FASE 2 T-5m `limpiar_mesa` CON 0% DE EXPOSICIÓN VERIFICADA
# ==============================================================================

class TestHFTPhase2LimpiarMesaZeroExposure:
    """
    Verifica que al faltar 5 minutos para el inicio del evento (T-5m),
    el orquestador y HFTEngine ejecuten limpiar_mesa():
    1. Cancelen atómicamente todas las órdenes pendientes.
    2. Liquiden cualquier saldo abierto a mercado.
    3. Verifiquen 0% exposición y 100% liquidez en USDT.
    """

    @pytest.mark.asyncio
    async def test_t5m_cleanup_cancels_all_orders_and_liquidates_to_zero(self):
        """
        A T-5m (`time_to_kickoff_minutes <= 5.0`), step_hft_cycle dispara
        la acción CLEANUP, cancela órdenes en exchange y garantiza 0% exposición.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        # Configurar partido exactamente a 4.5 minutos del inicio (Fase 2 T-5m)
        orch.live_matches["SOCCER_PRED_USDT"] = MatchLiveState(
            match_id="M_SOCCER_T5M",
            symbol="SOCCER_PRED_USDT",
            sport=SportType.SOCCER,
            time_to_kickoff_minutes=4.5,
            is_live=False,
        )

        # Crear una orden pendiente y una posición abierta previa
        orch.hft_engine.pending_orders["ORD_PEND_1"] = None # Placeholder handled by cleanup
        pos = orch.hft_engine.registrar_orden_ejecutada(
            signal=HftSignal(
                symbol="SOCCER_PRED_USDT",
                action="LIMIT_BUY",
                strategy_id="HFT_PHASE_1_OBI",
                phase="FASE_1_PREMATCH",
                price=0.50,
                quantity=20.0,
                estimated_prob=0.80,
                payout_decimal=2.0,
                reason="Pre-cleanup fill",
                authorized=True,
            ),
            order_id="ORD_FILL_1",
            executed_price=0.50,
            executed_qty=20.0,
        )

        snap = make_snapshot("SOCCER_PRED_USDT", bid_px=0.49, ask_px=0.51)
        orch.binance_client.actualizar_libro(
            symbol="SOCCER_PRED_USDT",
            bids=((0.49, 100.0),),
            asks=((0.51, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )

        # Ejecutar ciclo HFT
        signal = await orch.step_hft_cycle("SOCCER_PRED_USDT")

        assert signal is not None
        assert signal.action == "CLEANUP"
        assert signal.phase == "FASE_2_LIMPIAR_MESA"
        assert signal.authorized is True
        assert signal.metadata["exposicion_final_pct"] == 0.0
        assert signal.metadata["liquidez_usdt_pct"] == 100.0
        assert signal.metadata["regla_innegociable_cumplida"] is True

        # Verificar que no quedan posiciones activas para este símbolo
        assert len([p for p in orch.hft_engine.active_positions.values() if p.symbol == "SOCCER_PRED_USDT"]) == 0


# ==============================================================================
# SECCIÓN 3: FASE 3 (IN-PLAY LATENCY SNIPING) Y FASE 4 (TIME DECAY SCALP)
# ==============================================================================

class TestHFTPhases3And4Execution:
    """
    Verifica:
    - Fase 3: Sniping de latencia ante evento oracular antes de suspensión.
    - Fase 4: Time decay en minutos 75-90 (Soccer) y 28-35 (ESports).
    """

    def test_phase_3_oracle_latency_sniping_dispatched_in_live_cycle(self):
        """
        Si un gol ocurre hace menos de 3.0s y el libro de Binance sigue ACTIVE,
        procesar_mercado despacha Fase 3 snipe_desfase_oraculo y coloca orden agresiva.
        """
        engine = HFTEngine()
        now = time.time()

        match = MatchLiveState(
            match_id="M_INPLAY_GOAL",
            symbol="SOCCER_PRED_USDT",
            sport=SportType.SOCCER,
            minute=35.0,
            is_live=True,
            last_event="GOAL",
            last_event_timestamp=now - 0.5, # Gol hace 500 ms
        )

        snap = make_snapshot("SOCCER_PRED_USDT", bid_px=0.50, ask_px=0.52, market_status="ACTIVE")

        sig = engine.procesar_mercado(
            snapshot=snap,
            match_state=match,
            balance=100.0,
            operaciones_activas=0,
            exposicion_cluster=0.0,
        )

        assert sig.authorized is True
        assert sig.phase == "FASE_3_SNIPING"
        assert sig.strategy_id == "HFT_PHASE_3_SNIPING"
        assert sig.price == 0.52 # Compra el ask desactualizado
        assert sig.action == "LIMIT_BUY"

    def test_phase_3_aborts_immediately_if_binance_is_suspended(self):
        """
        Si Binance suspende el mercado (MarketStatus: SUSPENDED),
        la Regla de Oro 2 bloquea inmediatamente el sniping.
        """
        engine = HFTEngine()
        now = time.time()

        match = MatchLiveState(
            match_id="M_INPLAY_SUSP",
            symbol="SOCCER_PRED_USDT",
            sport=SportType.SOCCER,
            minute=35.0,
            is_live=True,
            last_event="GOAL",
            last_event_timestamp=now - 0.5,
        )

        snap_susp = make_snapshot("SOCCER_PRED_USDT", bid_px=0.50, ask_px=0.52, market_status="SUSPENDED")

        sig = engine.procesar_mercado(
            snapshot=snap_susp,
            match_state=match,
            balance=100.0,
            operaciones_activas=0,
            exposicion_cluster=0.0,
        )

        assert sig.authorized is False
        assert "SUSPENDIDO" in sig.reason

    def test_phase_4_time_decay_scalp_soccer_and_esports(self):
        """
        Fase 4: Compra empate en minutos finales con bajo peligro (<=0.20/0.25).
        - Fútbol: min 75-90
        - ESports: min 28-35
        """
        engine = HFTEngine()

        # Caso Fútbol: min 80, empate 1-1, peligro 0.10
        match_soccer = MatchLiveState(
            match_id="M_SOCCER_P4",
            symbol="SOCCER_DRAW_USDT",
            sport=SportType.SOCCER,
            minute=80.0,
            score_home=1,
            score_away=1,
            danger_attacks_per_min=0.10,
            is_live=True,
        )
        snap = make_snapshot("SOCCER_DRAW_USDT", bid_px=0.48, ask_px=0.50)

        sig_soccer = engine.procesar_mercado(snap, match_soccer, balance=100.0)
        assert sig_soccer.authorized is True
        assert sig_soccer.phase == "FASE_4_TIME_DECAY"

        # Caso ESports: min 30, peligro 0.15
        match_esports = MatchLiveState(
            match_id="M_ESPORTS_P4",
            symbol="ESPORTS_DRAW_USDT",
            sport=SportType.ESPORTS,
            minute=30.0,
            score_home=1,
            score_away=1,
            danger_attacks_per_min=0.15,
            is_live=True,
        )
        sig_esports = engine.procesar_mercado(snap, match_esports, balance=100.0)
        assert sig_esports.authorized is True
        assert sig_esports.phase == "FASE_4_TIME_DECAY"


# ==============================================================================
# SECCIÓN 4: ESTRATEGIA V (AMM SNIPING & PARIDAD BINARIA ATÓMICA)
# ==============================================================================

class TestStrategyVAMMArbitrageAndDualBuyProposal:
    """
    Verifica:
    - Generación explícita de `DualBuyProposal` cuando Ask(YES) + Ask(NO) < 1.00 - fees.
    - Ejecución atómica dual bloqueando ganancia libre de riesgo.
    - Detección de desviación de curva AMM frente a P_fair.
    - Coordinación con el ciclo `step_amm_cycle` del orquestador.
    """

    def test_dual_buy_proposal_generation_on_binary_parity(self):
        """
        Regla 2 (Acceptance Criterion):
        Detecta Ask(YES) + Ask(NO) < 1.00 - fees y adjunta atómicamente DualBuyProposal
        con órdenes de compra simultáneas, cantidades idénticas y net_edge > 0.
        """
        amm = ArbitrageAMMEngine(total_capital=1000.0)

        snap_yes = make_snapshot("EVENT_YES", bid_px=0.46, ask_px=0.47, ask_qty=200.0)
        snap_no = make_snapshot("EVENT_NO", bid_px=0.48, ask_px=0.49, ask_qty=150.0)

        sig = amm.detectar_paridad_binaria(snap_yes, snap_no, event_id="EVENT_100")

        assert sig is not None
        assert sig.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY
        assert sig.sum_asks == 0.96 # 0.47 + 0.49
        assert sig.net_edge > 0.03
        assert sig.max_volume == 150.0

        # Verificación explícita de la propuesta atómica DualBuyProposal
        prop = sig.dual_proposal
        assert prop is not None
        assert isinstance(prop, DualBuyProposal)
        assert prop.event_id == "EVENT_100"
        assert prop.symbol_yes == "EVENT_YES"
        assert prop.symbol_no == "EVENT_NO"
        assert prop.price_yes == 0.47
        assert prop.price_no == 0.49
        assert prop.quantity == 150.0
        assert prop.sum_asks == 0.96
        assert prop.net_edge == sig.net_edge

        # Órdenes atómicas enlazadas
        assert prop.order_yes.side == "BUY"
        assert prop.order_yes.target_price == 0.47
        assert prop.order_no.side == "BUY"
        assert prop.order_no.target_price == 0.49

    @pytest.mark.asyncio
    async def test_step_amm_cycle_orchestrator_integration(self):
        """
        Verifica que el orquestador principal ejecute step_amm_cycle()
        satisfaciendo la detección y ejecución de paridad y desviación.
        """
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_YES", "SOCCER_NO"],
            capital_inicial=500.0,
            mock_mode=True,
        )

        # Preparar libros con oportunidad de paridad
        ts = int(time.time() * 1000)
        orch.binance_client.actualizar_libro(
            symbol="SOCCER_YES",
            bids=((0.46, 100.0),),
            asks=((0.47, 100.0),),
            timestamp_ms=ts,
            market_status="ACTIVE",
        )
        orch.binance_client.actualizar_libro(
            symbol="SOCCER_NO",
            bids=((0.48, 100.0),),
            asks=((0.49, 100.0),),
            timestamp_ms=ts,
            market_status="ACTIVE",
        )

        sig = await orch.step_amm_cycle("SOCCER")
        assert sig is not None
        assert sig.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY
        assert sig.dual_proposal is not None
        assert orch.amm_engine.total_successful_trades >= 1
