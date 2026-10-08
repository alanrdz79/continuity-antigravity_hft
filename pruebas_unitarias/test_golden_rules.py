# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_golden_rules | CONTINUITY HFT Binance
==================================================================================
Suite de Pruebas de las 3 Reglas de Oro de CONTINUITY:
- Regla de Oro 1 (Spread y Volumen): Spread MÁXIMO permitido <= $0.03.
- Regla de Oro 2 (Monitoreo de Bloqueo): Si MarketStatus == 'SUSPENDED', bloquear órdenes.
- Regla de Oro 3 (Dynamic Sizing con Liquidez): Techo en los primeros 3 niveles de BID.

Cubre exhaustivamente:
- Tier 1: Cobertura de Características (>=5 casos por regla)
- Tier 2: Casos Límite y Esquinas (fronteras de $0.03, libros invertidos, 0-3 niveles)
- Tier 3: Combinaciones Cruzadas (GR1 + GR2 + GR3 en Escudo y Microestructura)
- Tier 4: Escenarios de Aplicación Real (Eventos de Gol/VAR, dilatación de spread)
"""

import time
import pytest
from typing import Tuple, List

from continuitis.microestructura_binance import (
    OrderBookSnapshot,
    OrderProposal,
    GoldenRulesValidator,
    MicroestructuraBinanceEngine,
    MAX_SPREAD_PERMITIDO,
    TOP_BIDS_ESCAPE_LEVELS,
)
from continuitis.riesgo_binance import (
    EscudoFinancieroBinance,
    OrderProposal as RiskOrderProposal,
)


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE
# ==============================================================================

class TestGoldenRulesTier1FeatureCoverage:
    """Verificación de contratos nominales para las Reglas de Oro 1, 2 y 3."""

    # --- REGLA DE ORO 1: SPREAD MÁXIMO $0.03 ---

    @pytest.mark.parametrize("best_bid,best_ask,expected_spread", [
        (0.50, 0.51, 0.01),
        (0.50, 0.52, 0.02),
        (0.50, 0.53, 0.03),
        (0.10, 0.12, 0.02),
        (0.95, 0.98, 0.03),
    ])
    def test_golden_rule_1_spread_lte_003_allowed(self, best_bid: float, best_ask: float, expected_spread: float):
        """Spreads menores o iguales a $0.03 son válidos y autorizados."""
        ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(best_bid, best_ask)
        assert ok is True
        assert spread == pytest.approx(expected_spread, abs=1e-5)
        assert motivo == "SPREAD_VALIDO"

    @pytest.mark.parametrize("best_bid,best_ask,expected_spread", [
        (0.50, 0.54, 0.04),
        (0.50, 0.55, 0.05),
        (0.50, 0.60, 0.10),
        (0.20, 0.25, 0.05),
        (0.80, 0.90, 0.10),
    ])
    def test_golden_rule_1_spread_gt_003_rejected(self, best_bid: float, best_ask: float, expected_spread: float):
        """Spreads mayores a $0.03 son estrictamente rechazados."""
        ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(best_bid, best_ask)
        assert ok is False
        assert spread == pytest.approx(expected_spread, abs=1e-5)
        assert "SPREAD_EXCESIVO" in motivo

    # --- REGLA DE ORO 2: MONITOREO DE SUSPENSIÓN ---

    @pytest.mark.parametrize("status", ["SUSPENDED", "suspended", "Suspended", " SUSPENDED "])
    def test_golden_rule_2_suspended_locks_orders(self, status: str):
        """Cualquier estado SUSPENDED bloquea inmediatamente la entrada."""
        ok, motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(status)
        assert ok is False
        assert motivo == "MERCADO_SUSPENDIDO_BINANCE"

    @pytest.mark.parametrize("status", ["ACTIVE", "active", "TRADING", "OPEN"])
    def test_golden_rule_2_active_allows_orders(self, status: str):
        """Estados activos permiten la operativa de trading."""
        ok, motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(status)
        assert ok is True
        assert motivo == "MERCADO_ACTIVO"

    # --- REGLA DE ORO 3: LIQUIDEZ TOP 3 BIDS ---

    def test_golden_rule_3_top3_bids_aggregation(self):
        """
        Derivación matemática:
        Nivel 1: (0.55, 100.0)
        Nivel 2: (0.54, 150.0)
        Nivel 3: (0.53, 250.0)
        Nivel 4: (0.52, 900.0) -> No debe incluirse en top 3
        Total top 3 = 100 + 150 + 250 = 500.0
        """
        bids = ((0.55, 100.0), (0.54, 150.0), (0.53, 250.0), (0.52, 900.0))
        liquidez = GoldenRulesValidator.calcular_liquidez_escape_top3_bids(bids, levels=3)
        assert liquidez == pytest.approx(500.0, abs=1e-4)

    def test_golden_rule_3_proposed_quantity_validation(self):
        """
        Si la cantidad propuesta <= liquidez top 3, la regla aprueba.
        Si la cantidad propuesta > liquidez top 3, la regla rechaza.
        """
        bids = ((0.50, 100.0), (0.49, 100.0), (0.48, 100.0))  # Total = 300.0
        validator = GoldenRulesValidator

        ok1, liq1, mot1 = validator.verificar_regla_oro_3_liquidez(250.0, bids)
        assert ok1 is True
        assert liq1 == 300.0
        assert mot1 == "LIQUIDEZ_ESCAPE_SUFICIENTE"

        ok2, liq2, mot2 = validator.verificar_regla_oro_3_liquidez(350.0, bids)
        assert ok2 is False
        assert liq2 == 300.0
        assert "LIQUIDEZ_INSUFICIENTE_TOP3" in mot2


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestGoldenRulesTier2BoundaryAndCorners:
    """Casos de frontera matemática y situaciones de libro anómalas."""

    def test_golden_rule_1_exact_boundary_0_0300_vs_0_0301(self):
        """
        Frontera de precisión flotante:
        Spread = 0.03000000 -> permitido.
        Spread = 0.03010000 -> rechazado.
        """
        ok_exact, _, _ = GoldenRulesValidator.verificar_regla_oro_1_spread(0.50, 0.5300)
        assert ok_exact is True

        ok_over, _, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(0.50, 0.5301)
        assert ok_over is False
        assert "SPREAD_EXCESIVO" in motivo

    def test_golden_rule_1_inverted_and_crossed_book(self):
        """
        Libro cruzado/invertido (Best Ask < Best Bid).
        Debe ser detectado y rechazado como anomalía severa de mercado.
        """
        ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(best_bid=0.55, best_ask=0.53)
        assert ok is False
        assert spread < 0
        assert "LIBRO_INVERTIDO" in motivo

    def test_golden_rule_1_zero_and_negative_prices(self):
        """Precios 0 o negativos no deben causar excepciones no controladas."""
        ok1, _, mot1 = GoldenRulesValidator.verificar_regla_oro_1_spread(0.0, 0.50)
        assert ok1 is False
        assert "PRECIOS_INVALIDOS" in mot1

        ok2, _, mot2 = GoldenRulesValidator.verificar_regla_oro_1_spread(-0.10, 0.20)
        assert ok2 is False
        assert "PRECIOS_INVALIDOS" in mot2

    def test_golden_rule_2_unknown_market_status_safety_lock(self):
        """Cualquier estado inesperado (ej. 'HALTED', 'CLOSED', '') debe bloquear por seguridad."""
        ok1, mot1 = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado("HALTED")
        assert ok1 is False
        assert "ESTADO_MERCADO_DESCONOCIDO" in mot1

        ok2, mot2 = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado("")
        assert ok2 is False

    def test_golden_rule_3_fewer_than_3_bid_levels(self):
        """
        Casos donde el libro tiene solo 1 o 2 niveles disponibles:
        - 1 nivel: suma ese único nivel.
        - 0 niveles (libro vacío): retorna 0.0 sin fallar.
        """
        validator = GoldenRulesValidator

        bids_2 = ((0.50, 120.0), (0.49, 80.0))
        assert validator.calcular_liquidez_escape_top3_bids(bids_2) == 200.0

        bids_1 = ((0.50, 75.0),)
        assert validator.calcular_liquidez_escape_top3_bids(bids_1) == 75.0

        bids_0 = ()
        assert validator.calcular_liquidez_escape_top3_bids(bids_0) == 0.0

    def test_golden_rule_3_clamping_in_risk_engine(self):
        """
        En el Escudo Financiero:
        Si el sizing nominal arroja 200.0 USD de stake, pero el top 3 de BIDs
        solo tiene 120.0 USD de liquidez, la orden DEBE ser recortada a 120.0 USD.
        """
        risk_engine = EscudoFinancieroBinance(pct_riesgo_fijo=0.02)
        # Balance = 10,000 USD, Stop Loss = 5% -> Riesgo nominal = 200 USD -> Stake nominal = 200 / 0.05 = 4000 USD
        # Top 3 BIDs solo tienen 150.0 USD disponibles
        top_3_bids_liq = 150.0

        eval_res = risk_engine.calcular_posicion(
            balance_actual=10000.0,
            p_estimada=0.70,
            cuota=1.80,
            pct_stop_loss=0.05,
            top_3_bid_volumen=top_3_bids_liq,
        )

        assert eval_res["operar"] is True
        assert eval_res["stake"] == pytest.approx(150.0, abs=1e-2)
        assert eval_res["clamped_by_liquidity"] is True


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS
# ==============================================================================

class TestGoldenRulesTier3CrossFeatureCombinations:
    """Interacción simultánea entre las 3 reglas y el orquestador de microestructura."""

    def test_gr1_and_gr2_simultaneous_rejection(self):
        """
        Libro con spread excesivo ($0.08) Y mercado suspendido.
        El motor debe rechazar sin contradicciones y registrar la causa.
        """
        snapshot = OrderBookSnapshot(
            symbol="MULTI_REJECT",
            bids=((0.40, 800.0),),
            asks=((0.48, 200.0),),  # Spread = 0.08 > 0.03
            timestamp_ms=int(time.time() * 1000),
            market_status="SUSPENDED",
        )
        engine = MicroestructuraBinanceEngine()
        signal = engine.evaluar_snapshot(snapshot)

        assert signal.spread_valido_gr1 is False
        assert signal.mercado_activo_gr2 is False
        assert signal.autorizado is False

    def test_gr3_liquidity_gate_in_microstructure_engine(self):
        """
        En `MicroestructuraBinanceEngine.evaluar_snapshot`:
        Si se pasa `cantidad_propuesta = 500.0`, pero la suma de los primeros
        3 niveles de BID es 300.0, la evaluación debe denegar autorización por GR3.
        """
        snapshot = OrderBookSnapshot(
            symbol="THIN_BOOK",
            bids=((0.50, 100.0), (0.49, 100.0), (0.48, 100.0)),  # Top 3 = 300.0
            asks=((0.52, 50.0),),  # Total ask = 50.0 -> I = (300-50)/350 = 0.714 >= 0.60
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        engine = MicroestructuraBinanceEngine()

        # Con cantidad de 200 -> Autorizado
        sig_ok = engine.evaluar_snapshot(snapshot, cantidad_propuesta=200.0)
        assert sig_ok.autorizado is True

        # Con cantidad de 400 -> Rechazado por falta de liquidez en top 3 BIDs
        sig_reject = engine.evaluar_snapshot(snapshot, cantidad_propuesta=400.0)
        assert sig_reject.autorizado is False
        assert "LIQUIDEZ_INSUFICIENTE_TOP3" in sig_reject.motivo


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestGoldenRulesTier4RealWorldScenarios:
    """Escenarios de producción: VAR, suspensión temporal y flash spreads."""

    def test_live_goal_var_suspension_and_resumption_sequence(self):
        """
        Simula secuencia temporal exacta durante un partido en vivo:
        T0: Partido normal 0-0, activo, spread $0.02 -> Trading activo.
        T1: Gol anotado / incidente, Binance conmuta a SUSPENDED -> Bloqueo instantáneo.
        T2: Revisión de VAR en curso (60 seg) -> Bloqueo estricto continuo.
        T3: Gol validado, Binance reactiva mercado a ACTIVE con nuevo spread $0.02 -> Reanudación.
        """
        engine = MicroestructuraBinanceEngine()

        # T0: Activo
        snap_t0 = OrderBookSnapshot(
            symbol="LIV_MCI",
            bids=((0.50, 900.0),),
            asks=((0.52, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        sig_t0 = engine.evaluar_snapshot(snap_t0)
        assert sig_t0.autorizado is True

        # T1 & T2: Suspendido por VAR
        snap_t1 = OrderBookSnapshot(
            symbol="LIV_MCI",
            bids=((0.50, 900.0),),
            asks=((0.52, 100.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="SUSPENDED",
        )
        sig_t1 = engine.evaluar_snapshot(snap_t1)
        assert sig_t1.autorizado is False
        assert "MERCADO_SUSPENDIDO" in sig_t1.motivo

        # T3: Reanudación post-VAR
        snap_t3 = OrderBookSnapshot(
            symbol="LIV_MCI",
            bids=((0.75, 850.0),),
            asks=((0.77, 150.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        sig_t3 = engine.evaluar_snapshot(snap_t3)
        assert sig_t3.autorizado is True
        assert sig_t3.spread == pytest.approx(0.02, abs=1e-4)

    def test_flash_spread_dilation_and_recovery(self):
        """
        Simulación de shock de liquidez (flash spread dilation):
        - Acontecimiento causa que el spread se abra de $0.02 a $0.07.
        - GR1 congela entradas inmediatamente.
        - 15 segundos después entran creadores de mercado y el spread baja a $0.025.
        - GR1 autoriza operativas nuevamente.
        """
        engine = MicroestructuraBinanceEngine()

        # Spread dilatado $0.07
        snap_wide = OrderBookSnapshot(
            symbol="FLASH_CRASH",
            bids=((0.45, 900.0),),
            asks=((0.52, 100.0),),  # Spread = 0.07
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        sig_wide = engine.evaluar_snapshot(snap_wide)
        assert sig_wide.spread_valido_gr1 is False
        assert sig_wide.autorizado is False

        # Spread comprimido a $0.025
        snap_tight = OrderBookSnapshot(
            symbol="FLASH_CRASH",
            bids=((0.495, 900.0),),
            asks=((0.520, 100.0),),  # Spread = 0.025 <= 0.03
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        sig_tight = engine.evaluar_snapshot(snap_tight)
        assert sig_tight.spread_valido_gr1 is True
        assert sig_tight.autorizado is True
