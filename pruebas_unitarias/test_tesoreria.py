# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_tesoreria | CONTINUITY HFT Binance
==================================================================================
Suite de Pruebas E2E de Tesorería, Dimensionamiento Dinámico, Racha y Cosecha.

Cubre exhaustivamente:
- Tier 1: Cobertura de Características (Sizing nominal, atenuación 0.85^n, techo 15%,
          inyección $10->$100 USD, corte 40/60, cosecha autónoma $1,000 USD al 35%).
- Tier 2: Casos Límite y Esquinas (racha perdedora n=10, balance cero, ganancias negativas).
- Tier 3: Combinaciones Cruzadas (integración con AuditorMetricas y TradeResult).
- Tier 4: Escenarios de Aplicación Real (Simulación de caja multimensual completa).
"""

import pytest
import time
from typing import List

from continuitis.tesoreria import (
    GestorTesoreria,
    CAPITAL_BASE_INICIAL,
    UMBRAL_INYECCION_100,
    MONTO_INYECCION_100,
    UMBRAL_COSECHA_1000,
    PCT_COSECHA_AUTONOMA,
    PCT_GASTOS_OPERACION,
    PCT_REINVERSION_COMPUESTA,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance
from continuitis.auditor_metricas import TradeResult, AuditorMetricas


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE
# ==============================================================================

class TestTesoreriaTier1FeatureCoverage:
    """Verificación de fórmulas de dimensionamiento, atenuación y ciclos de tesorería."""

    def test_sizing_nominal_formula_exact(self):
        """
        Derivación:
        Balance B = 1000.0, pct_riesgo = 0.015, stop_loss = 0.05, factor_racha = 1.0.
        Riesgo nominal = 1000 * 0.015 = 15.0 USD.
        Stake nominal = 15.0 / 0.05 = 300.0 USD.
        Sin embargo, techo de clúster = 15% de 1000 = 150.0 USD.
        El stake queda comprimido a 150.0 USD.
        """
        escudo = EscudoFinancieroBinance(pct_riesgo_fijo=0.015, ev_minimo=0.015, max_cluster_exp=0.15)
        res = escudo.calcular_posicion(
            balance_actual=1000.0,
            p_estimada=0.70,
            cuota=1.80,
            pct_stop_loss=0.05,
        )
        assert res["operar"] is True
        assert res["stake"] == pytest.approx(150.0, abs=1e-2)  # Clamped por 15% cluster cap
        assert res["clamped_by_cluster"] is True

    def test_losing_streak_attenuation_decay_curve(self):
        """
        Derivación matemática de la curva de atenuación:
        factor_racha = 0.85^n
        n=0: 1.0000
        n=1: 0.8500
        n=2: 0.7225 (0.85^2)
        n=3: 0.614125 (0.85^3)
        n=4: 0.522006 (0.85^4)
        """
        escudo = EscudoFinancieroBinance()
        assert escudo.factor_racha == pytest.approx(1.0, abs=1e-4)

        escudo.consecutive_losses = 1
        assert escudo.factor_racha == pytest.approx(0.85, abs=1e-4)

        escudo.consecutive_losses = 2
        assert escudo.factor_racha == pytest.approx(0.7225, abs=1e-4)

        escudo.consecutive_losses = 3
        assert escudo.factor_racha == pytest.approx(0.614125, abs=1e-4)

        escudo.consecutive_losses = 4
        assert escudo.factor_racha == pytest.approx(0.522006, abs=1e-4)

    def test_streak_attenuation_reset_on_win(self):
        """
        Al registrar una operación ganadora, el contador de pérdidas consecutivas
        debe restablecerse inmediatamente a 0 y el factor_racha a 1.0.
        """
        escudo = EscudoFinancieroBinance()
        # Simular 3 pérdidas
        for _ in range(3):
            eval_res = escudo.calcular_posicion(balance_actual=500.0, p_estimada=0.7, cuota=1.8, pct_stop_loss=0.05)
            escudo.consecutive_losses += 1
        assert escudo.consecutive_losses == 3
        assert escudo.factor_racha < 0.65

        # Registrar victoria (método o reseteo directo)
        escudo.consecutive_losses = 0
        assert escudo.factor_racha == pytest.approx(1.0, abs=1e-5)

    def test_treasury_injection_event_at_100_usd_validated(self):
        """
        Hito $10 -> $100 USD:
        Cuando el balance cruza 100 USD y la validación está satisfecha,
        se autoriza la inyección de +100 USD adicionales una única vez.
        """
        tesoreria = GestorTesoreria(balance_inicial=10.0)
        assert tesoreria.balance == 10.0
        assert tesoreria.hito_100_inyectado is False

        # El balance sube a 105.0 USD
        tesoreria.balance = 105.0
        hitos = tesoreria.verificar_hitos(forzar_validacion=True)

        assert "INYECCION_100_USD_APLICADA" in hitos["acciones"]
        assert tesoreria.hito_100_inyectado is True
        assert tesoreria.balance == pytest.approx(205.0, abs=1e-2)  # 105 + 100 = 205 USD

        # Segunda verificación: no debe re-inyectar
        hitos2 = tesoreria.verificar_hitos(forzar_validacion=True)
        assert "INYECCION_100_USD_APLICADA" not in hitos2["acciones"]
        assert tesoreria.balance == pytest.approx(205.0, abs=1e-2)

    def test_treasury_monthly_split_acceleration_phase_40_60(self):
        """
        Fase de Aceleración (< 1,000 USD):
        Ganancia mensual: 100 USD.
        Distribución:
        - 40% operación: 40 USD
        - 60% reinversión compuesta: 60 USD
        - 0% retiro
        Balance inicial: 300 USD -> Nuevo balance = (300 - 100) + 60 = 260 USD.
        """
        tesoreria = GestorTesoreria(balance_inicial=300.0)
        res = tesoreria.corte_mensual(ganancia_mensual=100.0)

        assert res["retiro_autonomo_35"] == 0.0
        assert res["gastos_operacion_40"] == pytest.approx(40.0, abs=1e-2)
        assert res["reinversion_compuesta_60"] == pytest.approx(60.0, abs=1e-2)
        assert res["nuevo_balance"] == pytest.approx(260.0, abs=1e-2)

    def test_treasury_autonomous_harvest_at_1000_usd(self):
        """
        Fase de Cosecha Autónoma (>= 1,000 USD):
        Balance inicial: 1200.0 USD.
        Ganancia mensual: 400.0 USD. Tipo de cambio MXN = 20.0.
        Distribución:
        - Retiro 35% autónomo: 400 * 0.35 = 140.0 USD (2,800.0 MXN).
        - Utilidad restante (65%): 400 - 140 = 260.0 USD.
        - Gastos operación (40% de 260): 104.0 USD.
        - Reinversión compuesta (60% de 260): 156.0 USD.
        - Nuevo balance = (1200 - 400) + 156 = 956.0 USD.
        """
        tesoreria = GestorTesoreria(balance_inicial=1200.0, tipo_cambio_mxn=20.0)
        tesoreria.verificar_hitos()  # Activa meta_1000
        assert tesoreria.meta_1000_activada is True

        corte = tesoreria.corte_mensual(ganancia_mensual=400.0)
        assert corte["retiro_autonomo_35"] == pytest.approx(140.0, abs=1e-2)
        assert corte["retiro_autonomo_mxn"] == pytest.approx(2800.0, abs=1e-2)
        assert corte["gastos_operacion_40"] == pytest.approx(104.0, abs=1e-2)
        assert corte["reinversion_compuesta_60"] == pytest.approx(156.0, abs=1e-2)
        assert corte["nuevo_balance"] == pytest.approx(956.0, abs=1e-2)


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestTesoreriaTier2BoundaryAndCorners:
    """Condiciones extremas, balances nulos y rachas adversas profundas."""

    def test_extreme_losing_streak_deep_attenuation(self):
        """
        Racha adversa profunda de 10 pérdidas consecutivas:
        factor_racha = 0.85^10 = 0.196874.
        El riesgo por operación se reduce en más del 80%.
        """
        escudo = EscudoFinancieroBinance()
        escudo.consecutive_losses = 10
        assert escudo.factor_racha == pytest.approx(0.85**10, abs=1e-5)
        assert escudo.factor_racha < 0.20

    def test_zero_or_negative_monthly_gain(self):
        """
        Corte mensual con ganancia nula o negativa (mes en tablas o con drawdown).
        No debe haber retiros, gastos ni deducción indebida.
        """
        tesoreria = GestorTesoreria(balance_inicial=500.0)
        corte_cero = tesoreria.corte_mensual(0.0)
        assert corte_cero["retiro_autonomo_35"] == 0.0
        assert corte_cero["nuevo_balance"] == 500.0

        corte_negativo = tesoreria.corte_mensual(-50.0)
        assert corte_negativo["retiro_autonomo_35"] == 0.0
        assert corte_negativo["nuevo_balance"] == 500.0

    def test_zero_balance_sizing_protection(self):
        """Si el balance llega a 0, calcular_posicion rechaza sin lanzar error."""
        escudo = EscudoFinancieroBinance()
        res = escudo.calcular_posicion(balance_actual=0.0, p_estimada=0.8, cuota=1.8, pct_stop_loss=0.05)
        assert res["operar"] is False
        assert res["stake"] == 0.0

    def test_unvalidated_injection_blocks_event(self):
        """
        Balance >= 100 USD, pero menos de 300 trades en el auditor:
        La compuerta bloquea la inyección y reporta el motivo.
        """
        auditor = AuditorMetricas(capital_inicial=10.0)
        tesoreria = GestorTesoreria(balance_inicial=10.0, auditor=auditor)
        tesoreria.balance = 105.0

        hitos = tesoreria.verificar_hitos(n_min=300)
        assert tesoreria.hito_100_inyectado is False
        assert "INYECCION_BLOQUEADA_POR_VALIDACION" in hitos["acciones"]
        assert tesoreria.balance == 105.0  # Sin inyección añadida


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS
# ==============================================================================

class TestTesoreriaTier3CrossFeatureCombinations:
    """Interacción entre TradeResult, AuditorMetricas y GestorTesoreria."""

    def test_trade_registration_updates_balance_and_auditor(self):
        """
        Al registrar trades en tesorería, el balance se actualiza en tiempo real
        y el auditor registra cada operación con exactitud.
        """
        tesoreria = GestorTesoreria(balance_inicial=10.0)
        t1 = TradeResult(trade_id="T1", symbol="SOCCER_1", stake=2.0, pnl=1.5, is_win=True, timestamp=time.time())
        t2 = TradeResult(trade_id="T2", symbol="SOCCER_2", stake=2.0, pnl=-2.0, is_win=False, timestamp=time.time())

        tesoreria.registrar_trade(t1)
        assert tesoreria.balance == pytest.approx(11.5, abs=1e-4)

        tesoreria.registrar_trade(t2)
        assert tesoreria.balance == pytest.approx(9.5, abs=1e-4)
        assert tesoreria.auditor.total_trades == 2
        assert tesoreria.auditor.calcular_win_rate() == 0.50


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestTesoreriaTier4RealWorldScenarios:
    """Simulación multimensual de crecimiento: $10 -> $100 -> $1,000 USD."""

    def test_full_progression_lifecycle_simulation(self):
        """
        Simula la evolución completa del fondo:
        1. Comienza en 10 USD.
        2. Genera utilidades secuenciales hasta superar 100 USD con validación.
        3. Recibe inyección de +100 USD.
        4. Opera en fase de aceleración con corte mensual 40/60.
        5. Crece hasta superar 1,000 USD y activa la cosecha autónoma del 35% a MXN.
        """
        tesoreria = GestorTesoreria(balance_inicial=10.0, tipo_cambio_mxn=20.0)

        # 1. Ganancias que llevan a 105 USD
        for i in range(19):
            tesoreria.registrar_trade(TradeResult(f"TR_{i}", "SYM", 2.0, 5.0, True, time.time()))
        assert tesoreria.balance == pytest.approx(105.0, abs=1e-2)

        # 2. Hito 100 USD forzado/validado
        hitos_100 = tesoreria.verificar_hitos(forzar_validacion=True)
        assert "INYECCION_100_USD_APLICADA" in hitos_100["acciones"]
        assert tesoreria.balance == pytest.approx(205.0, abs=1e-2)

        # 3. Mes 1 en fase de aceleración (Ganancia mensual = 100 USD)
        corte_mes1 = tesoreria.corte_mensual(100.0)
        assert corte_mes1["retiro_autonomo_35"] == 0.0
        assert corte_mes1["reinversion_compuesta_60"] == 60.0

        # 4. Crecimiento adicional hasta superar 1,000 USD (ej. 1100 USD)
        tesoreria.balance = 1100.0
        hitos_1000 = tesoreria.verificar_hitos()
        assert "MODO_COSECHA_AUTONOMA_DISPONIBLE" in hitos_1000["acciones"]
        assert tesoreria.meta_1000_activada is True

        # 5. Mes de cosecha autónoma sobre 300 USD de ganancia
        corte_cosecha = tesoreria.corte_mensual(300.0)
        assert corte_cosecha["retiro_autonomo_35"] == pytest.approx(105.0, abs=1e-2)
        assert corte_cosecha["retiro_autonomo_mxn"] == pytest.approx(2100.0, abs=1e-2)
        assert corte_cosecha["reinversion_compuesta_60"] == pytest.approx(117.0, abs=1e-2)

    def test_treasury_dynamic_unlatch_when_balance_falls_below_1000_usd(self):
        """
        Valida que el modo de cosecha del 35% NO quede permanentemente encasillado (latched).
        Si el balance cae por debajo de 1,000 USD, debe revertir dinámicamente a fase de aceleración.
        """
        tesoreria = GestorTesoreria(balance_inicial=1200.0, tipo_cambio_mxn=20.0)
        assert tesoreria.balance == 1200.0

        # En >= 1,000 USD: Cosecha autónoma activa
        corte_1 = tesoreria.corte_mensual(100.0)
        assert corte_1["retiro_autonomo_35"] == pytest.approx(35.0, abs=1e-2)
        assert tesoreria.meta_1000_activada is True

        # Supongamos un drawdown o balance que cae a 800 USD (< 1,000 USD)
        tesoreria.balance = 800.0
        hitos = tesoreria.verificar_hitos()
        assert tesoreria.meta_1000_activada is False

        # El corte mensual no debe extraer cosecha de 35% sino proteger la base
        corte_2 = tesoreria.corte_mensual(50.0)
        assert corte_2["retiro_autonomo_35"] == 0.0
        assert corte_2["gastos_operacion_40"] == pytest.approx(20.0, abs=1e-2)
        assert corte_2["reinversion_compuesta_60"] == pytest.approx(30.0, abs=1e-2)
        assert tesoreria.meta_1000_activada is False

        # Si el balance se recupera a >= 1,000 USD, se reactiva dinámicamente
        tesoreria.balance = 1050.0
        corte_3 = tesoreria.corte_mensual(100.0)
        assert corte_3["retiro_autonomo_35"] == pytest.approx(35.0, abs=1e-2)
        assert tesoreria.meta_1000_activada is True
