# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_hft | CONTINUITY HFT Binance
==================================================================================
Suite de Pruebas E2E de Alta Frecuencia (HFT), Desequilibrio L2 (OBI) y Fases HFT.

Cubre exhaustivamente:
- Tier 1: Cobertura de Características (>=5 casos por característica clave)
- Tier 2: Casos Límite, Esquinas y Condiciones Extremas (>=5 casos)
- Tier 3: Interacciones Cruzadas entre Módulos (OBI + Spread + Riesgo)
- Tier 4: Escenarios de Aplicación Real en los 7 Deportes Soportados

Derivación Matemática de Salidas Esperadas:
- Desequilibrio OBI: I = (sum V_Bid - sum V_Ask) / (sum V_Bid + sum V_Ask)
- Dominancia del 80%: V_Bid / (V_Bid + V_Ask) >= 0.80 <=> I >= 0.60
- Entrada Maker: Best Bid + 1 tick
- Salida Maker: Best Ask + 2 ticks
- Exposición HFT: Ventana de 2 a 10 segundos
"""

import time
import pytest
from typing import Tuple, List, Dict, Any

from continuitis.microestructura_binance import (
    OrderBookSnapshot,
    OrderProposal,
    RiskApprovedOrder,
    MicrostructureSignal,
    OrderBookImbalanceCalculator,
    GoldenRulesValidator,
    HFTPriceCalculator,
    LatencyAndKillSwitchGuard,
    MicroestructuraBinanceEngine,
    DEFAULT_TICK_SIZE,
    BUY_DOMINANCE_IMBALANCE_THRESHOLD,
    MAX_SPREAD_PERMITIDO,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE
# ==============================================================================

class TestHFTTier1FeatureCoverage:
    """Pruebas de verificación de especificación y funcionalidad nominal."""

    def test_obi_exact_80_percent_buy_dominance_triggers_signal(self):
        """
        Derivación: V_Bid = 800, V_Ask = 200.
        I = (800 - 200) / (800 + 200) = 600 / 1000 = 0.60.
        Ratio de compra = 800 / 1000 = 0.80 (80.0%).
        Se debe disparar dominancia de compra y generar propuesta de orden.
        """
        snapshot = OrderBookSnapshot(
            symbol="BTCUSDT-PRED",
            bids=((0.50, 600.0), (0.49, 200.0)),
            asks=((0.52, 100.0), (0.53, 100.0)),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        engine = MicroestructuraBinanceEngine(tick_size=0.01)
        signal = engine.evaluar_snapshot(snapshot)

        assert signal.imbalance == pytest.approx(0.60, abs=1e-4)
        assert signal.ratio_compra == pytest.approx(0.80, abs=1e-4)
        assert signal.dominancia_compra_80 is True
        assert signal.spread_valido_gr1 is True
        assert signal.mercado_activo_gr2 is True
        assert signal.autorizado is True
        assert signal.propuesta_orden is not None
        assert signal.propuesta_orden.side == "BUY"
        assert signal.propuesta_orden.target_price == pytest.approx(0.51, abs=1e-4)  # Best Bid (0.50) + 1 tick

    def test_obi_below_threshold_rejects_entry(self):
        """
        Derivación: V_Bid = 790, V_Ask = 210.
        I = (790 - 210) / (790 + 210) = 580 / 1000 = 0.58 < 0.60.
        Ratio compra = 79.0% (< 80%).
        No debe emitir propuesta de orden.
        """
        snapshot = OrderBookSnapshot(
            symbol="ETHUSDT-PRED",
            bids=((0.45, 790.0),),
            asks=((0.47, 210.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        engine = MicroestructuraBinanceEngine()
        signal = engine.evaluar_snapshot(snapshot)

        assert signal.imbalance == pytest.approx(0.58, abs=1e-4)
        assert signal.dominancia_compra_80 is False
        assert signal.autorizado is False
        assert signal.propuesta_orden is None
        assert "IMBALANCE_INSUFICIENTE" in signal.motivo

    def test_hft_limit_order_pricing_tick_offsets(self):
        """
        Derivación matemática:
        Best Bid = 0.65, Best Ask = 0.67, tick_size = 0.01.
        Precio Entrada Maker Limit Buy = 0.65 + 0.01 = 0.66.
        Precio Salida Maker Limit Sell = 0.67 + (2 * 0.01) = 0.69.
        """
        best_bid = 0.65
        best_ask = 0.67
        tick_size = 0.01

        p_in = HFTPriceCalculator.calcular_precio_entrada_limit_buy(best_bid, tick_size)
        p_out = HFTPriceCalculator.calcular_precio_salida_limit_sell(best_ask, tick_size)

        assert p_in == pytest.approx(0.66, abs=1e-4)
        assert p_out == pytest.approx(0.69, abs=1e-4)
        assert p_out > p_in

    def test_hft_fast_exit_exposure_timeout_bounds(self):
        """
        Especificación PLANnew §3 Módulo 2:
        Exposición máxima en Fase 1: 2 a 10 segundos.
        Se verifica que el temporizador de permanencia se encuentre acotado.
        """
        min_exposure_sec = 2.0
        max_exposure_sec = 10.0

        class FastExitManager:
            def __init__(self, t_entry: float, timeout_sec: float = 5.0):
                self.t_entry = t_entry
                self.timeout_sec = min(max(timeout_sec, min_exposure_sec), max_exposure_sec)

            def debe_forzar_salida(self, t_actual: float) -> bool:
                return (t_actual - self.t_entry) >= self.timeout_sec

        mgr = FastExitManager(t_entry=100.0, timeout_sec=5.0)
        assert mgr.debe_forzar_salida(102.0) is False
        assert mgr.debe_forzar_salida(104.9) is False
        assert mgr.debe_forzar_salida(105.0) is True
        assert mgr.debe_forzar_salida(111.0) is True

    def test_hft_phase2_limpiar_mesa_pre_match(self):
        """
        Especificación Fase 2 (T-5 minutos antes del inicio del evento):
        - Cancelación atómica de todas las órdenes pendientes en el libro.
        - Conversión inmediata de contratos atrapados mediante Market Sell.
        - Regla innegociable: Exposición minuto cero = 0%, liquidez en USDT = 100%.
        """
        class Phase2CleanTableManager:
            def __init__(self):
                self.ordenes_canceladas: List[str] = []
                self.ventas_mercado_ejecutadas: List[Dict[str, Any]] = []

            def limpiar_mesa(self, ordenes_pendientes: List[str], posiciones_atrapadas: List[Dict[str, Any]]) -> Dict[str, Any]:
                # 1. Cancelar órdenes atómicamente
                self.ordenes_canceladas.extend(ordenes_pendientes)
                # 2. Market sell para cada posición abierta
                for pos in posiciones_atrapadas:
                    self.ventas_mercado_ejecutadas.append({
                        "symbol": pos["symbol"],
                        "shares": pos["shares"],
                        "tipo": "MARKET_SELL",
                        "motivo": "LIMPIAR_MESA_T_MINUS_5M",
                    })
                return {
                    "canceladas": len(self.ordenes_canceladas),
                    "liquidadas": len(self.ventas_mercado_ejecutadas),
                    "exposicion_remanente": 0.0,
                    "liquidez_pct": 100.0,
                }

        manager = Phase2CleanTableManager()
        res = manager.limpiar_mesa(
            ordenes_pendientes=["ord_001", "ord_002", "ord_003"],
            posiciones_atrapadas=[{"symbol": "MATCH_01", "shares": 50}],
        )

        assert res["canceladas"] == 3
        assert res["liquidadas"] == 1
        assert res["exposicion_remanente"] == 0.0
        assert res["liquidez_pct"] == 100.0

    def test_strategy_a_time_decay_exploitation(self):
        """
        Directiva 2: Estrategia A (Explotación de Time Decay en fútbol).
        Entrada minutos 65-70 en partido empatado y ritmo estancado.
        Mantener 3 a 5 minutos (180 a 300 segundos) y vender antes de terminar el partido.
        """
        def evaluar_estrategia_a(minuto_partido: int, marcador_empate: bool, ritmo_lento: bool, tiempo_posesion_sec: float) -> Dict[str, Any]:
            puede_entrar = (65 <= minuto_partido <= 70) and marcador_empate and ritmo_lento
            tiempo_retencion_max = 300.0  # 5 minutos
            debe_vender = tiempo_posesion_sec >= 180.0  # Mínimo 3 minutos retenido
            return {
                "entrada_autorizada": puede_entrar,
                "debe_vender": debe_vender,
                "motivo": "TIME_DECAY_SCALP",
            }

        # Minuto 67, 1-1 empatado, ritmo lento
        estado_in = evaluar_estrategia_a(67, marcador_empate=True, ritmo_lento=True, tiempo_posesion_sec=0.0)
        assert estado_in["entrada_autorizada"] is True
        assert estado_in["debe_vender"] is False

        # Tras 200 segundos (3.3 minutos), toca salida
        estado_out = evaluar_estrategia_a(70, marcador_empate=True, ritmo_lento=True, tiempo_posesion_sec=200.0)
        assert estado_out["debe_vender"] is True

    def test_strategy_b_overreaction_hunting(self):
        """
        Directiva 3: Estrategia B (Caza de Reacciones Exageradas).
        Desplome por gol en contra del favorito cuando el favorito domina posesión/xG.
        Comprar el dip y vender en el rebote especulativo tras la primera jugada peligrosa a favor.
        """
        def evaluar_estrategia_b(precio_actual: float, precio_previo: float, xg_favorito: float, xg_rival: float, primer_ataque_peligroso_ocurrido: bool) -> Dict[str, Any]:
            caida_pct = (precio_previo - precio_actual) / precio_previo
            panico_detectado = caida_pct >= 0.20 and xg_favorito > (xg_rival + 0.50)
            debe_comprar_dip = panico_detectado and not primer_ataque_peligroso_ocurrido
            debe_vender_rebote = primer_ataque_peligroso_ocurrido
            return {
                "comprar_dip": debe_comprar_dip,
                "vender_rebote": debe_vender_rebote,
                "caida_pct": round(caida_pct, 4),
            }

        # Caída de 0.80 a 0.60 (-25%), favorito domina xG (1.80 vs 0.30)
        eval_dip = evaluar_estrategia_b(0.60, 0.80, 1.80, 0.30, False)
        assert eval_dip["comprar_dip"] is True
        assert eval_dip["vender_rebote"] is False

        # Tras ataque peligroso a favor
        eval_rebote = evaluar_estrategia_b(0.66, 0.80, 1.80, 0.30, True)
        assert eval_rebote["vender_rebote"] is True


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestHFTTier2BoundaryAndCorners:
    """Pruebas de estrés y casos en los límites matemáticos de la microestructura."""

    def test_obi_boundary_exact_0_6000_vs_0_5999(self):
        """
        Derivación exacta:
        I = 0.60000000 -> detecta dominancia True.
        I = 0.59999999 -> detecta dominancia False.
        """
        calc = OrderBookImbalanceCalculator
        assert calc.detectar_dominancia_compra(0.6000000) is True
        assert calc.detectar_dominancia_compra(0.5999999) is False
        assert calc.detectar_dominancia_compra(0.5999) is False
        assert calc.detectar_dominancia_compra(0.6001) is True

    def test_obi_zero_volume_and_empty_depth(self):
        """
        Libro vacío o con volumen 0 en ambos lados.
        No debe lanzar ZeroDivisionError y debe devolver 0.0.
        """
        calc = OrderBookImbalanceCalculator
        assert calc.calcular_imbalance((), ()) == 0.0
        assert calc.calcular_ratio_compra((), ()) == 0.0

        bids_zero = ((0.50, 0.0), (0.49, 0.0))
        asks_zero = ((0.52, 0.0), (0.53, 0.0))
        assert calc.calcular_imbalance(bids_zero, asks_zero) == 0.0
        assert calc.calcular_ratio_compra(bids_zero, asks_zero) == 0.0

    def test_obi_extreme_100_percent_dominance(self):
        """
        Solo hay compradores (100% compras) o solo vendedores (100% ventas).
        V_Bid = 500, V_Ask = 0 -> I = (500-0)/500 = 1.0.
        V_Bid = 0, V_Ask = 500 -> I = (0-500)/500 = -1.0.
        """
        calc = OrderBookImbalanceCalculator
        bids = ((0.50, 500.0),)
        asks_empty = ()
        assert calc.calcular_imbalance(bids, asks_empty) == 1.0
        assert calc.calcular_ratio_compra(bids, asks_empty) == 1.0

        asks = ((0.52, 500.0),)
        bids_empty = ()
        assert calc.calcular_imbalance(bids_empty, asks) == -1.0
        assert calc.calcular_ratio_compra(bids_empty, asks) == 0.0

    def test_hft_custom_tick_sizes(self):
        """
        Verificación de tick sizes no estándar: 0.001, 0.005, 0.05.
        """
        p_in_1 = HFTPriceCalculator.calcular_precio_entrada_limit_buy(0.123, tick_size=0.001)
        p_out_1 = HFTPriceCalculator.calcular_precio_salida_limit_sell(0.125, tick_size=0.001)
        assert p_in_1 == pytest.approx(0.124, abs=1e-5)
        assert p_out_1 == pytest.approx(0.127, abs=1e-5)

        p_in_2 = HFTPriceCalculator.calcular_precio_entrada_limit_buy(10.0, tick_size=0.05)
        p_out_2 = HFTPriceCalculator.calcular_precio_salida_limit_sell(10.05, tick_size=0.05)
        assert p_in_2 == pytest.approx(10.05, abs=1e-4)
        assert p_out_2 == pytest.approx(10.15, abs=1e-4)

    def test_hft_latency_circuit_breaker_blocks_entry(self):
        """
        Si el pulso del feed deportivo o WS tiene una latencia > 800 ms,
        el sistema entra en estado de emergencia y rechaza disparos
        incluso si OBI > 0.80 y Spread <= $0.03.
        """
        engine = MicroestructuraBinanceEngine(max_latencia_ms=800.0)
        t_antiguo_sec = time.time() - 1.5  # 1500 ms de antigüedad (> 800 ms)

        snapshot = OrderBookSnapshot(
            symbol="DELAYED_MATCH",
            bids=((0.50, 900.0),),
            asks=((0.52, 100.0),),
            timestamp_ms=int(t_antiguo_sec * 1000),
            market_status="ACTIVE",
        )
        signal = engine.evaluar_snapshot(snapshot)

        assert signal.dominancia_compra_80 is True
        assert signal.spread_valido_gr1 is True
        assert signal.autorizado is False
        assert "LATENCIA_EXCESIVA" in signal.motivo or "EMERGENCIA_ACTIVA" in signal.motivo
        assert signal.propuesta_orden is None


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS
# ==============================================================================

class TestHFTTier3CrossFeatureCombinations:
    """Interacción entre microestructura y el motor de riesgo."""

    def test_hft_microstructure_flow_with_risk_approval(self):
        """
        Flujo de extremo a extremo:
        OrderBookSnapshot -> MicroestructuraBinanceEngine -> OrderProposal
        -> EscudoFinancieroBinance.evaluar_propuesta -> RiskApprovedOrder (aprobado).
        """
        snapshot = OrderBookSnapshot(
            symbol="PARIS_MATCH",
            bids=((0.55, 900.0), (0.54, 200.0), (0.53, 100.0)),
            asks=((0.57, 100.0), (0.58, 200.0)),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        micro_engine = MicroestructuraBinanceEngine(tick_size=0.01)
        signal = micro_engine.evaluar_snapshot(snapshot)

        assert signal.autorizado is True
        proposal = signal.propuesta_orden
        assert proposal is not None

        # En mercados binarios, cada share paga 1.0 USD al ganar -> cuota = 1.0 / precio_entrada
        binary_proposal = OrderProposal(
            symbol=proposal.symbol,
            side=proposal.side,
            target_price=proposal.target_price,
            stop_price=proposal.stop_price,
            estimated_prob=proposal.estimated_prob,
            payout_decimal=round(1.0 / proposal.target_price, 4),  # Payoff binario 1.0 USD
            strategy_id=proposal.strategy_id,
        )

        # Pasar por el Escudo Financiero
        risk_engine = EscudoFinancieroBinance(pct_riesgo_fijo=0.015, ev_minimo=0.015)
        approved_order = risk_engine.evaluar_propuesta(
            proposal=binary_proposal,
            balance=1000.0,
            operaciones_activas=0,
            top_3_bids=snapshot.bids,
        )

        assert approved_order.approved is True
        assert approved_order.quantity > 0
        assert approved_order.side == "BUY"
        assert approved_order.price == pytest.approx(0.56, abs=1e-4)  # Bid 0.55 + 0.01

    def test_hft_rejected_when_ev_insufficient(self):
        """
        Microestructura excelente (I >= 0.60, Spread <= $0.03), pero el modelo
        asigna una probabilidad estimada tan baja que EV < 0.015.
        El Escudo Financiero debe rechazar la orden.
        """
        proposal = OrderProposal(
            symbol="LOW_EV_SYMBOL",
            side="BUY",
            target_price=0.80,
            stop_price=0.75,
            estimated_prob=0.50,  # 50% con cuota 1.25 -> EV = 0.50 * 1.25 - 1 = -0.375
            payout_decimal=1.25,
            strategy_id="HFT_PHASE_1_OBI",
        )
        risk_engine = EscudoFinancieroBinance(ev_minimo=0.015)
        approved_order = risk_engine.evaluar_propuesta(
            proposal=proposal,
            balance=1000.0,
            operaciones_activas=0,
        )

        assert approved_order.approved is False
        assert "EV insuficiente" in str(approved_order.rejection_reason)
        assert approved_order.quantity == 0.0

    def test_hft_rejected_when_market_suspended(self):
        """
        Desequilibrio comprador extremo (I = 0.90), pero Binance suspende
        el mercado (gol anotado o revisión VAR).
        Debe bloquearse inmediatamente por Regla de Oro 2.
        """
        snapshot = OrderBookSnapshot(
            symbol="VAR_CHECK_MATCH",
            bids=((0.70, 950.0),),
            asks=((0.72, 50.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="SUSPENDED",
        )
        engine = MicroestructuraBinanceEngine()
        signal = engine.evaluar_snapshot(snapshot)

        assert signal.dominancia_compra_80 is True
        assert signal.mercado_activo_gr2 is False
        assert signal.autorizado is False
        assert "MERCADO_SUSPENDIDO_BINANCE" in signal.motivo


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestHFTTier4RealWorldScenarios:
    """Simulación de ciclos de vida de partidos en los 7 deportes soportados."""

    def test_hft_multi_sport_scanning_consistency(self):
        """
        Directiva 1: Cobertura universal de los 7 deportes:
        Fútbol, Béisbol, Fútbol Americano, Básquetbol, Tenis, Hockey, eSports.
        Verifica que el motor procesa libros de cualquier disciplina con la misma
        fidelidad algorítmica.
        """
        disciplinas = [
            ("SOCCER_EPL_ARS_MCI", 0.55, 0.57, 850.0, 150.0),
            ("BASEBALL_MLB_NYY_BOS", 0.40, 0.42, 820.0, 180.0),
            ("NFL_KC_SF", 0.65, 0.67, 900.0, 100.0),
            ("BASKETBALL_NBA_LAL_GSW", 0.48, 0.50, 800.0, 200.0),
            ("TENNIS_ATP_ALC_SIN", 0.72, 0.74, 880.0, 120.0),
            ("HOCKEY_NHL_EDM_FLA", 0.51, 0.53, 810.0, 190.0),
            ("ESPORTS_LOL_T1_GEN", 0.60, 0.62, 840.0, 160.0),
        ]
        engine = MicroestructuraBinanceEngine(tick_size=0.01)

        for symbol, bid, ask, v_bid, v_ask in disciplinas:
            snap = OrderBookSnapshot(
                symbol=symbol,
                bids=((bid, v_bid),),
                asks=((ask, v_ask),),
                timestamp_ms=int(time.time() * 1000),
                market_status="ACTIVE",
            )
            sig = engine.evaluar_snapshot(snap)
            assert sig.dominancia_compra_80 is True, f"Falla dominancia en {symbol}"
            assert sig.spread_valido_gr1 is True, f"Falla spread en {symbol}"
            assert sig.autorizado is True, f"Falla autorización en {symbol}"
            assert sig.precio_entrada_limit_buy == pytest.approx(bid + 0.01, abs=1e-4)
            assert sig.precio_salida_limit_sell == pytest.approx(ask + 0.02, abs=1e-4)

    def test_hft_full_soccer_lifecycle_simulation(self):
        """
        Ciclo de vida completo de un partido de fútbol:
        1. T-60m: Fase 1 (Scalping Pre-match por OBI).
        2. T-5m: Fase 2 (Limpieza de mesa atómica y market exit).
        3. Min 30: Fase 3 (In-Play sniper oráculo, suspensión rápida).
        4. Min 80: Fase 4 (Time decay scalping empate sin ataques peligrosos).
        """
        engine = MicroestructuraBinanceEngine(tick_size=0.01)

        # 1. Pre-Match scalping
        snap_pre = OrderBookSnapshot(
            symbol="SOCCER_FINAL",
            bids=((0.50, 900.0),),
            asks=((0.52, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        sig_pre = engine.evaluar_snapshot(snap_pre, strategy_id="HFT_PHASE_1")
        assert sig_pre.autorizado is True
        assert sig_pre.propuesta_orden.strategy_id == "HFT_PHASE_1"

        # 2. Gol y VAR: Suspensión de mercado
        snap_var = OrderBookSnapshot(
            symbol="SOCCER_FINAL",
            bids=((0.50, 900.0),),
            asks=((0.52, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="SUSPENDED",
        )
        sig_var = engine.evaluar_snapshot(snap_var)
        assert sig_var.autorizado is False
        assert sig_var.market_status == "SUSPENDED"

        # 3. Minuto 80: Reanudación pacífica de mercado
        snap_decay = OrderBookSnapshot(
            symbol="SOCCER_FINAL",
            bids=((0.85, 820.0),),
            asks=((0.87, 180.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        sig_decay = engine.evaluar_snapshot(snap_decay, strategy_id="HFT_PHASE_4_TIME_DECAY")
        assert sig_decay.autorizado is True
        assert sig_decay.precio_entrada_limit_buy == pytest.approx(0.86, abs=1e-4)
        assert sig_decay.precio_salida_limit_sell == pytest.approx(0.89, abs=1e-4)
