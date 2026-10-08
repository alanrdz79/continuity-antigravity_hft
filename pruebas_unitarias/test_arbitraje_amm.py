# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_arbitraje_amm
====================================
Suite de Pruebas Unitarias de 4 Niveles para Estrategia V:
Dynamic Cross-Venue Arbitrage & AMM Bonding-Curve Sniping.

Niveles de Prueba:
- Tier 1: Cobertura de Características y Contratos:
  * Disparador de paridad binaria determinista (Best Ask(YES) + Best Ask(NO) < 0.98).
  * Ejecución de compra dual simultánea con ganancia de redención libre de riesgo.
  * Entrada por desviación de curva frente a P_fair externa.
  * Gestión y salida de scalp en horizonte de 2 a 15 segundos y rebote take profit.
- Tier 2: Casos Límite y Esquinas (Boundary & Corners):
  * Suma de Asks = 1.0000 (sin margen, sin arbitraje).
  * Suma de Asks = 1.0001 (margen negativo).
  * Suma de Asks = 0.9999 (consumido por comisiones, sin arbitraje).
  * Libros con volumen cero o profundidad vacía.
  * Fronteras del umbral de desviación (0.03) y precios extremos.
- Tier 3: Integración de Riesgo y Latencia:
  * Cumplimiento estricto del techo del 15% de clúster con AsyncCapitalGateway.
  * Liberación de capital y prevención de memory leaks tras cierre de posiciones.
  * Guardián de latencia rígido: aborto a > 2.5 segundos con liberación de tokens.
  * Concurrencia masiva sin condición de carrera contra el techo de clúster.
- Tier 4: Escenarios de Aplicación Real y Mercados Múltiples:
  * Bloqueo inmediato por MarketStatus == 'SUSPENDED' en detección y ejecución.
  * Transición de mercado activo a suspendido durante posición scalp abierta.
  * Ciclo de arbitraje concurrente multi-evento a través de 5 disciplinas deportivas.
"""

from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Tuple
import pytest

from continuitis.microestructura_binance import OrderBookSnapshot
from estrategias.swing_engine import AsyncCapitalGateway
from estrategias.arbitraje_amm import (
    ArbitrageConfig,
    ArbitrageOpportunityType,
    ArbitrageSignal,
    EstrategiaVArbitrajeAMM,
    ScalpPosition,
)


# ==============================================================================
# HELPERS PARA GENERAR FOTOGRAMAS DE LIBRO DE ÓRDENES
# ==============================================================================

def make_snapshot(
    symbol: str,
    bid_price: float,
    bid_vol: float,
    ask_price: float,
    ask_vol: float,
    market_status: str = "ACTIVE",
    timestamp_ms: int = 1000,
) -> OrderBookSnapshot:
    """Crea un OrderBookSnapshot inmutable sintético para pruebas."""
    bids = ((round(bid_price, 4), round(bid_vol, 2)),) if bid_price > 0 else ()
    asks = ((round(ask_price, 4), round(ask_vol, 2)),) if ask_price > 0 else ()
    return OrderBookSnapshot(
        symbol=symbol,
        bids=bids,
        asks=asks,
        timestamp_ms=timestamp_ms,
        market_status=market_status,
    )


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE
# ==============================================================================

class TestArbitrajeTier1FeatureCoverage:
    """Verificación de contratos nominales para la Estrategia V de Arbitraje AMM."""

    def test_binary_parity_trigger_condition_under_098(self):
        """
        Regla 2: Detección determinista de paridad binaria.
        Best Ask(YES) = 0.48, Best Ask(NO) = 0.49. Suma = 0.97 (< 0.98).
        Debe generar ArbitrageSignal con net_edge > 0.02 y target_contract == 'BOTH'.
        """
        strat = EstrategiaVArbitrajeAMM(total_capital=1000.0)

        snap_yes = make_snapshot("MATCH_YES", bid_price=0.47, bid_vol=100.0, ask_price=0.48, ask_vol=200.0)
        snap_no = make_snapshot("MATCH_NO", bid_price=0.48, bid_vol=100.0, ask_price=0.49, ask_vol=150.0)

        signal = strat.detectar_paridad_binaria(snap_yes, snap_no, event_id="MATCH_1")
        assert signal is not None
        assert signal.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY
        assert signal.is_risk_free_parity is True
        assert signal.target_contract == "BOTH"
        assert signal.best_ask_yes == 0.48
        assert signal.best_ask_no == 0.49
        assert signal.sum_asks == 0.97
        assert signal.max_volume == 150.0  # min(200, 150)
        assert signal.net_edge > 0.02
        assert signal.fees_total > 0.0

    @pytest.mark.asyncio
    async def test_binary_parity_execution_locks_redemption_profit(self):
        """
        Regla 2: Ejecución simultánea dual de paridad binaria.
        Bloquea ganancia garantizada de redención libre de riesgo (1.00 - sum(asks) - fees > 0).
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("SOCCER_YES", bid_price=0.46, bid_vol=100.0, ask_price=0.47, ask_vol=100.0)
        snap_no = make_snapshot("SOCCER_NO", bid_price=0.48, bid_vol=100.0, ask_price=0.49, ask_vol=100.0)

        signal = strat.detectar_paridad_binaria(snap_yes, snap_no, event_id="SOCCER_01")
        assert signal is not None

        res = await strat.ejecutar_arbitraje_paridad(signal, requested_stake=50.0)
        assert res["success"] is True
        assert res["position_id"] is not None
        assert res["profit_locked"] > 0.0
        assert strat.total_redemption_profit_locked > 0.0
        assert strat.total_successful_trades == 1

        pos = strat.active_positions[res["position_id"]]
        assert pos.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY
        assert pos.contract_side == "DUAL"
        assert pos.quantities["SOCCER_YES"] == pos.quantities["SOCCER_NO"]
        assert pos.target_exit_price == 1.00

    def test_curve_deviation_yes_undervalued_entry(self):
        """
        Regla 1: Desviación frente a P_fair externa para contrato YES infravalorado.
        P_fair = 0.65, Ask(YES) = 0.58 -> Desviación = 0.07 >= 0.03.
        Debe generar señal CURVE_DEVIATION_YES para comprar YES.
        """
        strat = EstrategiaVArbitrajeAMM(total_capital=1000.0)

        snap_yes = make_snapshot("TENNIS_YES", bid_price=0.57, bid_vol=80.0, ask_price=0.58, ask_vol=120.0)
        snap_no = make_snapshot("TENNIS_NO", bid_price=0.41, bid_vol=80.0, ask_price=0.42, ask_vol=100.0)

        signal = strat.detectar_desviacion_curva(snap_yes, snap_no, p_fair=0.65, event_id="TENNIS_01")
        assert signal is not None
        assert signal.opportunity_type == ArbitrageOpportunityType.CURVE_DEVIATION_YES
        assert signal.target_contract == "YES"
        assert signal.target_price == 0.58
        assert signal.p_fair == 0.65
        assert signal.deviation == pytest.approx(0.07, abs=1e-5)
        assert signal.net_edge > 0.06

    def test_curve_deviation_no_undervalued_entry(self):
        """
        Regla 1: Desviación frente a P_fair externa para contrato NO infravalorado.
        P_fair(YES) = 0.28 -> P_fair(NO) = 0.72.
        Ask(NO) = 0.64 -> Desviación = 0.08 >= 0.03.
        Debe generar señal CURVE_DEVIATION_NO para comprar NO.
        """
        strat = EstrategiaVArbitrajeAMM(total_capital=1000.0)

        snap_yes = make_snapshot("BASKET_YES", bid_price=0.35, bid_vol=50.0, ask_price=0.36, ask_vol=80.0)
        snap_no = make_snapshot("BASKET_NO", bid_price=0.63, bid_vol=50.0, ask_price=0.64, ask_vol=90.0)

        signal = strat.detectar_desviacion_curva(snap_yes, snap_no, p_fair=0.28, event_id="BASKET_01")
        assert signal is not None
        assert signal.opportunity_type == ArbitrageOpportunityType.CURVE_DEVIATION_NO
        assert signal.target_contract == "NO"
        assert signal.target_price == 0.64
        assert signal.deviation == pytest.approx(0.08, abs=1e-5)

    @pytest.mark.asyncio
    async def test_curve_deviation_execution_and_scalp_bounce_exit(self):
        """
        Regla 1: Entrada y salida por rebote (Take Profit) hacia P_fair.
        Entrada en 0.55 con target exit en ~0.60.
        Al llegar nuevo libro con Bid >= 0.60, se liquida el scalp con ganancia neta.
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("FUTBOL_YES", bid_price=0.54, bid_vol=50.0, ask_price=0.55, ask_vol=100.0)
        snap_no = make_snapshot("FUTBOL_NO", bid_price=0.44, bid_vol=50.0, ask_price=0.45, ask_vol=100.0)

        signal = strat.detectar_desviacion_curva(snap_yes, snap_no, p_fair=0.65, event_id="FUTBOL_01")
        assert signal is not None

        # Ejecutar compra con horizonte scalp de 5 segundos
        res = await strat.ejecutar_arbitraje_desviacion(signal, requested_stake=30.0, scalp_horizon_s=5.0)
        assert res["success"] is True
        pos_id = res["position_id"]
        assert pos_id in strat.active_positions

        pos = strat.active_positions[pos_id]
        assert pos.scalp_horizon_s == 5.0
        target_exit = pos.target_exit_price
        assert target_exit is not None and target_exit > 0.55

        # Simular rebote de mercado: Best Bid sube por encima del target_exit
        snap_rebote = make_snapshot("FUTBOL_YES", bid_price=target_exit + 0.01, bid_vol=100.0, ask_price=target_exit + 0.02, ask_vol=100.0)
        cierres = await strat.gestionar_posiciones_scalp({"FUTBOL_YES": snap_rebote})

        assert len(cierres) == 1
        assert cierres[0]["position_id"] == pos_id
        assert cierres[0]["reason"] == "SCALP_BOUNCE"
        assert cierres[0]["pnl"] > 0.0
        assert pos_id not in strat.active_positions
        assert len(strat.completed_positions) == 1

    @pytest.mark.asyncio
    async def test_scalp_timeout_exit_within_2_to_15_seconds(self):
        """
        Regla 1: Salida estricta por expiración del horizonte scalp (entre 2 y 15 segundos).
        Si el precio no rebota pero expira el tiempo programado, se liquida a mercado.
        """
        strat = EstrategiaVArbitrajeAMM(total_capital=1000.0)
        snap_yes = make_snapshot("HOCKEY_YES", bid_price=0.50, bid_vol=50.0, ask_price=0.51, ask_vol=100.0)
        snap_no = make_snapshot("HOCKEY_NO", bid_price=0.48, bid_vol=50.0, ask_price=0.49, ask_vol=100.0)

        signal = strat.detectar_desviacion_curva(snap_yes, snap_no, p_fair=0.60, event_id="HOCKEY_01")
        assert signal is not None

        # Ejecutar con horizonte de 3.0 segundos
        res = await strat.ejecutar_arbitraje_desviacion(signal, requested_stake=25.0, scalp_horizon_s=3.0)
        assert res["success"] is True
        pos_id = res["position_id"]
        pos = strat.active_positions[pos_id]
        entry_t = pos.entry_timestamp

        # 1. Chequeo a t + 1.0s (no ha expirado aún)
        snap_flat = make_snapshot("HOCKEY_YES", bid_price=0.50, bid_vol=50.0, ask_price=0.51, ask_vol=100.0)
        cierres_1 = await strat.gestionar_posiciones_scalp({"HOCKEY_YES": snap_flat}, now=entry_t + 1.0)
        assert len(cierres_1) == 0
        assert pos_id in strat.active_positions

        # 2. Chequeo a t + 3.5s (expiró el horizonte de 3.0s)
        cierres_2 = await strat.gestionar_posiciones_scalp({"HOCKEY_YES": snap_flat}, now=entry_t + 3.5)
        assert len(cierres_2) == 1
        assert cierres_2[0]["reason"] == "SCALP_TIMEOUT"
        assert pos_id not in strat.active_positions


# ==============================================================================
# TIER 2: BOUNDARY AND CORNER CONDITIONS
# ==============================================================================

class TestArbitrajeTier2BoundaryAndCorners:
    """Verificación de condiciones de frontera, libros atípicos y extremos matemáticos."""

    def test_boundary_sum_asks_exact_1_0000_no_arbitrage(self):
        """
        Frontera: Suma de asks = 1.0000.
        Con comisiones > 0, el costo neto es > 1.0000. Debe retornar None.
        """
        strat = EstrategiaVArbitrajeAMM()
        snap_yes = make_snapshot("BOUND_YES", bid_price=0.49, bid_vol=50.0, ask_price=0.5000, ask_vol=100.0)
        snap_no = make_snapshot("BOUND_NO", bid_price=0.49, bid_vol=50.0, ask_price=0.5000, ask_vol=100.0)

        sig = strat.detectar_paridad_binaria(snap_yes, snap_no)
        assert sig is None

    def test_boundary_sum_asks_1_0001_negative_edge(self):
        """
        Frontera: Suma de asks = 1.0001. Margen negativo directo.
        Debe retornar None.
        """
        strat = EstrategiaVArbitrajeAMM()
        snap_yes = make_snapshot("BOUND_YES", bid_price=0.50, bid_vol=50.0, ask_price=0.5001, ask_vol=100.0)
        snap_no = make_snapshot("BOUND_NO", bid_price=0.49, bid_vol=50.0, ask_price=0.5000, ask_vol=100.0)

        sig = strat.detectar_paridad_binaria(snap_yes, snap_no)
        assert sig is None

    def test_boundary_sum_asks_0_9999_consumed_by_fees(self):
        """
        Frontera: Suma de asks = 0.9999.
        Aunque la suma bruta es < 1.00, la comisión efectiva (0.075%) consume
        la micro-ineficiencia ($0.9999 * (1 + 0.00075) = 1.000649 > 1.00).
        Debe retornar None para evitar pérdidas por fricción.
        """
        strat = EstrategiaVArbitrajeAMM()
        snap_yes = make_snapshot("BOUND_YES", bid_price=0.4990, bid_vol=50.0, ask_price=0.4999, ask_vol=100.0)
        snap_no = make_snapshot("BOUND_NO", bid_price=0.4990, bid_vol=50.0, ask_price=0.5000, ask_vol=100.0)

        sig = strat.detectar_paridad_binaria(snap_yes, snap_no)
        assert sig is None

    def test_boundary_zero_volume_books_handled_safely(self):
        """
        Esquinas: Libros con volumen cero o listas vacías en bids/asks.
        Debe manejar elegantemente sin lanzar IndexError ni ZeroDivisionError.
        """
        strat = EstrategiaVArbitrajeAMM()

        # Caso 1: Asks vacíos
        snap_vacio = OrderBookSnapshot("EMPTY_YES", bids=((0.50, 10.0),), asks=(), timestamp_ms=1000)
        snap_normal = make_snapshot("NORM_NO", 0.40, 10.0, 0.42, 10.0)
        assert strat.detectar_paridad_binaria(snap_vacio, snap_normal) is None
        assert strat.detectar_desviacion_curva(snap_vacio, snap_normal, p_fair=0.60) is None

        # Caso 2: Volumen 0.0 en el mejor ask
        snap_vol_cero = OrderBookSnapshot("ZERO_YES", bids=((0.40, 10.0),), asks=((0.42, 0.0),), timestamp_ms=1000)
        assert strat.detectar_paridad_binaria(snap_vol_cero, snap_normal) is None
        assert strat.detectar_desviacion_curva(snap_vol_cero, snap_normal, p_fair=0.60) is None

    def test_boundary_curve_deviation_threshold_edge(self):
        """
        Frontera: Umbral de desviación exacto (0.03).
        - Desviación de 0.0299: rechazada (< 0.03).
        - Desviación de 0.0305: aceptada (>= 0.03).
        """
        strat = EstrategiaVArbitrajeAMM()
        snap_no = make_snapshot("TEST_NO", 0.40, 50.0, 0.45, 50.0)

        # Caso por debajo del umbral: P_fair=0.60, Ask=0.5701 -> dev=0.0299
        snap_sub = make_snapshot("TEST_YES", 0.56, 50.0, 0.5701, 50.0)
        assert strat.detectar_desviacion_curva(snap_sub, snap_no, p_fair=0.60) is None

        # Caso por encima del umbral: P_fair=0.60, Ask=0.5695 -> dev=0.0305
        snap_sup = make_snapshot("TEST_YES", 0.56, 50.0, 0.5695, 50.0)
        sig = strat.detectar_desviacion_curva(snap_sup, snap_no, p_fair=0.60)
        assert sig is not None
        assert sig.target_contract == "YES"

    def test_boundary_extreme_prices(self):
        """Precios extremos en límites de probabilidad (0.01 y 0.99)."""
        strat = EstrategiaVArbitrajeAMM()
        snap_yes = make_snapshot("EXT_YES", 0.01, 10.0, 0.02, 100.0)
        snap_no = make_snapshot("EXT_NO", 0.96, 10.0, 0.97, 100.0)

        # Suma = 0.99 -> Costo total con fees ~ 0.9907 < 1.00 -> Edge ~ 0.0092 > 0.001
        sig = strat.detectar_paridad_binaria(snap_yes, snap_no)
        assert sig is not None
        assert sig.sum_asks == 0.99


# ==============================================================================
# TIER 3: RISK & LATENCY COMBINATIONS
# ==============================================================================

class TestArbitrajeTier3RiskAndLatency:
    """Verificación de integración de riesgo (techo 15%) y guardián de latencia (2.5s)."""

    @pytest.mark.asyncio
    async def test_cluster_cap_15_percent_strict_enforcement(self):
        """
        Regla 3: Techo estricto de exposición por clúster del 15%.
        Capital total = 1000.0 USD -> Techo de clúster = 150.0 USD.
        - Reserva 1: 100 USD (Aprobada, comprometido = 100).
        - Reserva 2: 60 USD (Rechazada porque 100 + 60 = 160 > 150).
        - Reserva 3: 50 USD (Aprobada, comprometido = 150).
        - Reserva 4: 10 USD (Rechazada, espacio disponible = 0).
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("M1_YES", 0.45, 500.0, 0.46, 500.0)
        snap_no = make_snapshot("M1_NO", 0.45, 500.0, 0.46, 500.0)
        signal = strat.detectar_paridad_binaria(snap_yes, snap_no, event_id="M1")
        assert signal is not None

        # 1. Asignar 100 USD -> Debe pasar
        res1 = await strat.ejecutar_arbitraje_paridad(signal, requested_stake=100.0)
        assert res1["success"] is True
        assert gateway.capital_comprometido == 100.0

        # 2. Solicitar 60 USD -> Debe rechazarse por exceder los 150 USD
        res2 = await strat.ejecutar_arbitraje_paridad(signal, requested_stake=60.0)
        assert res2["success"] is False
        assert "CLUSTER_15_EXCEDIDO" in res2["reason"]

        # 3. Solicitar 50 USD -> Debe aprobarse saturando exactamente los 150 USD
        res3 = await strat.ejecutar_arbitraje_paridad(signal, requested_stake=50.0)
        assert res3["success"] is True
        assert gateway.capital_comprometido == 150.0
        assert gateway.capital_disponible_cluster == 0.0

        # 4. Cualquier nueva orden debe ser rechazada
        res4 = await strat.ejecutar_arbitraje_paridad(signal, requested_stake=10.0)
        assert res4["success"] is False

    @pytest.mark.asyncio
    async def test_cluster_cap_released_properly_on_exit(self):
        """
        Regla 3: Al cerrar una posición, el capital se libera atómicamente
        restaurando la capacidad del clúster sin fugas de memoria.
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("DEV_YES", 0.50, 500.0, 0.51, 500.0)
        snap_no = make_snapshot("DEV_NO", 0.45, 500.0, 0.46, 500.0)
        signal = strat.detectar_desviacion_curva(snap_yes, snap_no, p_fair=0.62, event_id="DEV_01")
        assert signal is not None

        # Saturar con 150 USD
        res = await strat.ejecutar_arbitraje_desviacion(signal, requested_stake=150.0, scalp_horizon_s=2.0)
        assert res["success"] is True
        assert gateway.capital_disponible_cluster == 0.0
        pos_id = res["position_id"]

        # Simular rebote y cierre de posición
        snap_exit = make_snapshot("DEV_YES", 0.65, 100.0, 0.66, 100.0)
        cierres = await strat.gestionar_posiciones_scalp({"DEV_YES": snap_exit})
        assert len(cierres) == 1

        # El capital debe estar completamente liberado (150 USD disponibles de nuevo)
        assert gateway.capital_comprometido == 0.0
        assert gateway.capital_disponible_cluster == 150.0

    @pytest.mark.asyncio
    async def test_latency_guard_2_5s_hard_timeout_abort(self):
        """
        Regla 3: Guardián de Latencia Rígido (<= 2.5s).
        Si la ejecución en vuelo tarda más de 2.5 segundos, se aborta inmediatamente,
        se cancela la orden y se liberan las reservas de capital.
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("LAT_YES", 0.45, 100.0, 0.46, 100.0)
        snap_no = make_snapshot("LAT_NO", 0.45, 100.0, 0.46, 100.0)
        signal = strat.detectar_paridad_binaria(snap_yes, snap_no, event_id="LAT_01")
        assert signal is not None

        # Simular latencia de red excesiva de 2.6 segundos (> 2.5s)
        res = await strat.ejecutar_arbitraje_paridad(signal, requested_stake=50.0, mock_delay_s=2.6)

        assert res["success"] is False
        assert res["reason"] == "LATENCY_ABORT"
        assert res["latency_s"] >= 2.5
        assert strat.total_aborted_trades == 1
        # Verificar que el token fue liberado y no quedó comprometido
        assert gateway.capital_comprometido == 0.0

    @pytest.mark.asyncio
    async def test_latency_under_2_5s_executes_normally(self):
        """Ejecución rápida (< 2.5s) pasa el filtro del guardián sin problemas."""
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("FAST_YES", 0.45, 100.0, 0.46, 100.0)
        snap_no = make_snapshot("FAST_NO", 0.45, 100.0, 0.46, 100.0)
        signal = strat.detectar_paridad_binaria(snap_yes, snap_no)
        assert signal is not None

        # Retardo de 0.05 segundos (50 ms)
        res = await strat.ejecutar_arbitraje_paridad(signal, requested_stake=30.0, mock_delay_s=0.05)
        assert res["success"] is True
        assert res["reason"] == "EJECUTADO_EXITOSO"

    @pytest.mark.asyncio
    async def test_concurrent_tasks_no_race_condition_on_cluster_cap(self):
        """
        Concurrencia: 10 tareas concurrentes solicitando 30 USD cada una (300 USD total).
        Con un techo de 150 USD, exactamente 5 deben ser aprobadas (150 USD) y 5 rechazadas.
        No debe existir race condition ni excederse el límite.
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("RACE_YES", 0.45, 1000.0, 0.46, 1000.0)
        snap_no = make_snapshot("RACE_NO", 0.45, 1000.0, 0.46, 1000.0)
        signal = strat.detectar_paridad_binaria(snap_yes, snap_no)
        assert signal is not None

        async def worker():
            return await strat.ejecutar_arbitraje_paridad(signal, requested_stake=30.0)

        resultados = await asyncio.gather(*(worker() for _ in range(10)))
        exitosos = [r for r in resultados if r["success"]]
        fallidos = [r for r in resultados if not r["success"]]

        assert len(exitosos) == 5
        assert len(fallidos) == 5
        assert gateway.capital_comprometido == 150.0


# ==============================================================================
# TIER 4: REAL-WORLD SCENARIOS & MULTI-EVENT ARBITRAGE
# ==============================================================================

class TestArbitrajeTier4RealWorldScenarios:
    """Escenarios del mundo real: eventos de suspensión (gol/VAR) y arbitraje multi-mercado."""

    def test_market_status_suspended_immediate_lock_on_detection(self):
        """
        Regla de Oro 2: Si cualquiera de los libros tiene MarketStatus == 'SUSPENDED',
        se bloquea inmediatamente la detección y no se emite ninguna señal.
        """
        strat = EstrategiaVArbitrajeAMM()

        # Caso YES suspendido (ej. revisión de VAR en gol)
        snap_yes_susp = make_snapshot("VAR_YES", 0.45, 100.0, 0.46, 100.0, market_status="SUSPENDED")
        snap_no_act = make_snapshot("VAR_NO", 0.45, 100.0, 0.46, 100.0, market_status="ACTIVE")

        assert strat.detectar_paridad_binaria(snap_yes_susp, snap_no_act) is None
        assert strat.detectar_desviacion_curva(snap_yes_susp, snap_no_act, p_fair=0.60) is None
        assert strat.evaluar_oportunidades(snap_yes_susp, snap_no_act, p_fair=0.60) == []

    @pytest.mark.asyncio
    async def test_market_status_suspended_locks_active_execution(self):
        """
        Regla de Oro 2: Si el mercado entra en SUSPENDED, las llamadas de ejecución
        son rechazadas instantáneamente con motivo 'MERCADO_SUSPENDIDO'.
        """
        strat = EstrategiaVArbitrajeAMM()
        strat.actualizar_estado_mercado("SUSPENDED")

        snap_yes = make_snapshot("SUSP_YES", 0.45, 100.0, 0.46, 100.0)
        snap_no = make_snapshot("SUSP_NO", 0.45, 100.0, 0.46, 100.0)

        # Crear señal manual para forzar llamada de ejecución
        sig = ArbitrageSignal(
            signal_id="FORCED_SIG",
            event_id="FORCED_01",
            opportunity_type=ArbitrageOpportunityType.BINARY_PARITY,
            symbol_yes="SUSP_YES",
            symbol_no="SUSP_NO",
            best_ask_yes=0.46,
            best_ask_no=0.46,
            sum_asks=0.92,
            net_edge=0.07,
        )

        res = await strat.ejecutar_arbitraje_paridad(sig, requested_stake=30.0)
        assert res["success"] is False
        assert res["reason"] == "MERCADO_SUSPENDIDO"

        # Reanudar mercado a ACTIVE permite operar nuevamente
        strat.actualizar_estado_mercado("ACTIVE")
        res_active = await strat.ejecutar_arbitraje_paridad(sig, requested_stake=30.0)
        assert res_active["success"] is True

    @pytest.mark.asyncio
    async def test_market_suspension_during_open_scalp_triggers_emergency_freeze(self):
        """
        Regla de Oro 2: Si durante una posición abierta de scalp el mercado pasa a
        'SUSPENDED', se activa el congelamiento inmediato 'LOCKED_SUSPENDED' y se
        libera el capital para proteger el balance de contingencias no deseadas.
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        snap_yes = make_snapshot("MATCH_YES", 0.50, 100.0, 0.52, 100.0)
        snap_no = make_snapshot("MATCH_NO", 0.45, 100.0, 0.46, 100.0)

        signal = strat.detectar_desviacion_curva(snap_yes, snap_no, p_fair=0.62, event_id="MATCH_01")
        assert signal is not None

        res = await strat.ejecutar_arbitraje_desviacion(signal, requested_stake=40.0)
        assert res["success"] is True
        pos_id = res["position_id"]

        # Ocurre un gol: el feed marca el mercado como SUSPENDED
        snap_suspended = make_snapshot("MATCH_YES", 0.50, 100.0, 0.52, 100.0, market_status="SUSPENDED")
        cierres = await strat.gestionar_posiciones_scalp({"MATCH_YES": snap_suspended})

        assert len(cierres) == 1
        assert cierres[0]["position_id"] == pos_id
        assert cierres[0]["status"] == "LOCKED_SUSPENDED"
        assert cierres[0]["reason"] == "MARKET_SUSPENDED"
        assert gateway.capital_comprometido == 0.0

    @pytest.mark.asyncio
    async def test_multi_event_arbitrage_run_across_5_sports(self):
        """
        Simulación Completa Multi-Evento:
        Evalúa y opera concurrentemente a través de 5 eventos deportivos:
        1. Fútbol: Presenta paridad determinista (0.47 + 0.48 = 0.95).
        2. Baloncesto: Presenta infravaloración de curva en YES frente a P_fair (0.65 vs 0.55).
        3. Tenis: Eficiente (suma de asks = 1.02, sin arbitraje).
        4. Hockey: Mercado SUSPENDED (debe ignorarse de inmediato).
        5. Béisbol: Presenta paridad determinista (0.46 + 0.47 = 0.93).

        Verifica:
        - Ejecución concurrente limpia con asyncio.gather.
        - Respeto total al techo del 15% de clúster.
        - Cero interferencias entre deportes y registros contables precisos.
        """
        gateway = AsyncCapitalGateway(capital_total=1000.0, max_cluster_exp=0.15)
        strat = EstrategiaVArbitrajeAMM(capital_gateway=gateway, total_capital=1000.0)

        mercados = [
            {
                "deporte": "SOCCER",
                "snap_yes": make_snapshot("SOCCER_YES", 0.46, 100.0, 0.47, 100.0),
                "snap_no": make_snapshot("SOCCER_NO", 0.47, 100.0, 0.48, 100.0),
                "p_fair": 0.50,
            },
            {
                "deporte": "BASKET",
                "snap_yes": make_snapshot("BASKET_YES", 0.54, 80.0, 0.55, 80.0),
                "snap_no": make_snapshot("BASKET_NO", 0.44, 80.0, 0.45, 80.0),
                "p_fair": 0.65,
            },
            {
                "deporte": "TENNIS",
                "snap_yes": make_snapshot("TENNIS_YES", 0.50, 50.0, 0.51, 50.0),
                "snap_no": make_snapshot("TENNIS_NO", 0.50, 50.0, 0.51, 50.0),
                "p_fair": 0.50,
            },
            {
                "deporte": "HOCKEY",
                "snap_yes": make_snapshot("HOCKEY_YES", 0.45, 50.0, 0.46, 50.0, market_status="SUSPENDED"),
                "snap_no": make_snapshot("HOCKEY_NO", 0.45, 50.0, 0.46, 50.0, market_status="ACTIVE"),
                "p_fair": 0.50,
            },
            {
                "deporte": "BASEBALL",
                "snap_yes": make_snapshot("BASEBALL_YES", 0.45, 100.0, 0.46, 100.0),
                "snap_no": make_snapshot("BASEBALL_NO", 0.46, 100.0, 0.47, 100.0),
                "p_fair": 0.50,
            },
        ]

        async def procesar_mercado(m: Dict):
            senales = strat.evaluar_oportunidades(
                m["snap_yes"],
                m["snap_no"],
                p_fair=m["p_fair"],
                event_id=m["deporte"],
            )
            resultados = []
            for sig in senales:
                if sig.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY:
                    res = await strat.ejecutar_arbitraje_paridad(sig, requested_stake=40.0)
                else:
                    res = await strat.ejecutar_arbitraje_desviacion(sig, requested_stake=40.0)
                resultados.append(res)
            return m["deporte"], resultados

        ejecuciones = await asyncio.gather(*(procesar_mercado(m) for m in mercados))
        res_map = {dep: res for dep, res in ejecuciones}

        # 1. Fútbol: Paridad ejecutada
        assert len(res_map["SOCCER"]) == 1
        assert res_map["SOCCER"][0]["success"] is True

        # 2. Baloncesto: Curva ejecutada
        assert len(res_map["BASKET"]) == 1
        assert res_map["BASKET"][0]["success"] is True

        # 3. Tenis: Sin señales (eficiente)
        assert len(res_map["TENNIS"]) == 0

        # 4. Hockey: Suspendido, sin señales
        assert len(res_map["HOCKEY"]) == 0

        # 5. Béisbol: Paridad ejecutada (40 + 40 + 40 = 120 <= 150 cap)
        assert len(res_map["BASEBALL"]) == 1
        assert res_map["BASEBALL"][0]["success"] is True

        # Techo de clúster respetado (120 USD comprometidos <= 150 USD máximo)
        assert gateway.capital_comprometido == 120.0
        assert gateway.capital_comprometido <= gateway.capital_maximo_cluster
        assert strat.total_successful_trades == 3
        assert strat.total_profit_locked > 0.0
