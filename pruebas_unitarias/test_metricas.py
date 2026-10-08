# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_metricas | CONTINUITY HFT Binance
==================================================================================
Suite de Pruebas de Métricas Analíticas y Validación Estadística (Z-score & p-value).

Cubre exhaustivamente:
- Win Rate (WR = Ganadas / N).
- Retorno sobre la Inversión (ROI = sum PnL / B_0).
- Yield sobre volumen transaccionado (Yield = sum PnL / Turnover).
- Capital Acumulado según interés compuesto: B_N = B_0 * prod(1 + f_i * R_i).
- Total de Operaciones (N).
- Compuerta de Validación Estadística fuera de muestra (N >= 300, Z > 1.645, p < 0.05).
"""

import math
import time
import pytest
from typing import List

from continuitis.auditor_metricas import (
    TradeResult,
    AuditorMetricas,
)


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE
# ==============================================================================

class TestMetricasTier1FeatureCoverage:
    """Verificación de exactitud matemática de las métricas clave."""

    def test_win_rate_mathematical_precision(self):
        """
        Derivación:
        100 operaciones: 58 ganadas, 42 perdidas.
        WR = 58 / 100 = 0.5800.
        """
        auditor = AuditorMetricas(capital_inicial=100.0)
        for i in range(58):
            auditor.registrar_trade(TradeResult(f"W_{i}", "SYM", stake=10.0, pnl=2.0, is_win=True, timestamp=time.time()))
        for i in range(42):
            auditor.registrar_trade(TradeResult(f"L_{i}", "SYM", stake=10.0, pnl=-2.0, is_win=False, timestamp=time.time()))

        assert auditor.total_trades == 100
        assert auditor.calcular_win_rate() == pytest.approx(0.58, abs=1e-5)

    def test_accumulated_capital_compounding_formula(self):
        """
        Derivación matemática exacta de PLANnew.md §3 Módulo 5:
        B_N = B_0 * prod_{i=1}^N (1 + f_i * R_i)
        
        B_0 = 100.0 USD.
        Trade 1: S_1 = 10.0, PnL_1 = +5.0 -> f_1 = 10/100 = 0.10, R_1 = 5/10 = 0.50.
                 1 + f_1*R_1 = 1 + 0.05 = 1.05 -> B_1 = 105.0 USD.
        Trade 2: S_2 = 10.5, PnL_2 = -5.25 -> f_2 = 10.5/105 = 0.10, R_2 = -0.50.
                 1 + f_2*R_2 = 1 - 0.05 = 0.95 -> B_2 = 105.0 * 0.95 = 99.75 USD.
        """
        auditor = AuditorMetricas(capital_inicial=100.0)
        t1 = TradeResult("T1", "SYM", stake=10.0, pnl=5.0, is_win=True, timestamp=time.time())
        t2 = TradeResult("T2", "SYM", stake=10.5, pnl=-5.25, is_win=False, timestamp=time.time())

        auditor.registrar_trade(t1)
        assert auditor.calcular_capital_acumulado() == pytest.approx(105.0, abs=1e-4)

        auditor.registrar_trade(t2)
        assert auditor.calcular_capital_acumulado() == pytest.approx(99.75, abs=1e-4)

    def test_roi_calculation_exact(self):
        """
        Derivación:
        B_0 = 50.0 USD.
        Trades con PnLs: +10.0, +5.0, -3.0 -> sum(PnL) = +12.0 USD.
        ROI = 12.0 / 50.0 = 0.2400 (24.0%).
        """
        auditor = AuditorMetricas(capital_inicial=50.0)
        auditor.registrar_trade(TradeResult("T1", "SYM", 5.0, 10.0, True, time.time()))
        auditor.registrar_trade(TradeResult("T2", "SYM", 5.0, 5.0, True, time.time()))
        auditor.registrar_trade(TradeResult("T3", "SYM", 5.0, -3.0, False, time.time()))

        assert auditor.calcular_roi() == pytest.approx(0.24, abs=1e-5)

    def test_yield_turnover_calculation_exact(self):
        """
        Derivación:
        Turnover total = sum(Stakes) = 20.0 + 30.0 + 50.0 = 100.0 USD.
        Ganancia neta total = sum(PnL) = 4.0 + 6.0 - 2.0 = 8.0 USD.
        Yield = 8.0 / 100.0 = 0.0800 (8.0% sobre turnover).
        """
        auditor = AuditorMetricas(capital_inicial=200.0)
        auditor.registrar_trade(TradeResult("T1", "SYM", stake=20.0, pnl=4.0, is_win=True, timestamp=time.time()))
        auditor.registrar_trade(TradeResult("T2", "SYM", stake=30.0, pnl=6.0, is_win=True, timestamp=time.time()))
        auditor.registrar_trade(TradeResult("T3", "SYM", stake=50.0, pnl=-2.0, is_win=False, timestamp=time.time()))

        assert auditor.calcular_yield() == pytest.approx(0.08, abs=1e-5)

    def test_statistical_z_score_and_p_value_formula(self):
        """
        Derivación matemática de la prueba de hipótesis:
        H0: WR <= 0.50 (azar)
        Z = (WR - 0.50) / (0.50 / sqrt(N))
        
        Para N = 400 y WR = 0.55 (220 ganadas):
        sigma = 0.50 / sqrt(400) = 0.50 / 20 = 0.025.
        Z = (0.55 - 0.50) / 0.025 = 0.05 / 0.025 = 2.000.
        p-value = 1 - Phi(2.0) = 0.02275 (< 0.05).
        """
        auditor = AuditorMetricas(capital_inicial=100.0)
        for i in range(220):
            auditor.registrar_trade(TradeResult(f"W_{i}", "SYM", 5.0, 1.0, True, time.time()))
        for i in range(180):
            auditor.registrar_trade(TradeResult(f"L_{i}", "SYM", 5.0, -1.0, False, time.time()))

        z, p_val = auditor.calcular_estadistica_z()
        assert z == pytest.approx(2.0, abs=1e-2)
        assert p_val == pytest.approx(0.02275, abs=1e-3)
        assert p_val < 0.05


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestMetricasTier2BoundaryAndCorners:
    """Casos de frontera: estado vacío (N=0), 100% rachas, stakes cero."""

    def test_zero_trades_initial_state(self):
        """Estado inicial sin operaciones: no debe provocar división por cero."""
        auditor = AuditorMetricas(capital_inicial=10.0)
        assert auditor.total_trades == 0
        assert auditor.calcular_win_rate() == 0.0
        assert auditor.calcular_capital_acumulado() == 10.0
        assert auditor.calcular_roi() == 0.0
        assert auditor.calcular_yield() == 0.0

        z, p_val = auditor.calcular_estadistica_z()
        assert z == 0.0
        assert p_val == 1.0

    def test_all_consecutive_losses_decay(self):
        """Serie de 10 pérdidas consecutivas: WR = 0.0, Z negativo y p-value ~ 1.0."""
        auditor = AuditorMetricas(capital_inicial=100.0)
        for i in range(10):
            auditor.registrar_trade(TradeResult(f"L_{i}", "SYM", stake=5.0, pnl=-5.0, is_win=False, timestamp=time.time()))

        assert auditor.calcular_win_rate() == 0.0
        assert auditor.calcular_roi() == pytest.approx(-0.50, abs=1e-4)
        z, p_val = auditor.calcular_estadistica_z()
        assert z < 0
        assert p_val > 0.99

    def test_all_wins_metrics(self):
        """Serie de 10 victorias consecutivas: WR = 1.0."""
        auditor = AuditorMetricas(capital_inicial=100.0)
        for i in range(10):
            auditor.registrar_trade(TradeResult(f"W_{i}", "SYM", stake=5.0, pnl=5.0, is_win=True, timestamp=time.time()))

        assert auditor.calcular_win_rate() == 1.0
        assert auditor.calcular_roi() == pytest.approx(0.50, abs=1e-4)

    def test_exact_z_threshold_1_645_boundary(self):
        """
        Frontera de corte alfa = 0.05 (unilateral):
        Z = 1.644853 -> p-value = 0.05.
        """
        # Función matemática estándar: Phi(-1.644853) = 0.05
        p_exact = 0.5 * math.erfc(1.6448536 / math.sqrt(2.0))
        assert p_exact == pytest.approx(0.05, abs=1e-4)


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS
# ==============================================================================

class TestMetricasTier3CrossFeatureCombinations:
    """Interacción entre AuditorMetricas, el protocolo de telemetría y SQLite WAL."""

    def test_obtener_metricas_telemetry_dict(self):
        """
        Verifica el contrato de `obtener_metricas()` exigido por `PROJECT.md`:
        Debe devolver un dict con claves exactas:
        {"win_rate": float, "capital_acumulado": float, "roi": float, "yield": float, "total_trades": int}
        """
        auditor = AuditorMetricas(capital_inicial=100.0)
        auditor.registrar_trade(TradeResult("T1", "SYM", 10.0, 5.0, True, time.time()))
        auditor.registrar_trade(TradeResult("T2", "SYM", 10.0, -5.0, False, time.time()))

        metricas = auditor.obtener_metricas()
        assert isinstance(metricas, dict)
        assert "win_rate" in metricas
        assert "capital_acumulado" in metricas
        assert "roi" in metricas
        assert "yield" in metricas
        assert "total_trades" in metricas
        assert metricas["total_trades"] == 2
        assert metricas["win_rate"] == 0.50

    def test_sqlite_wal_persistence_and_recovery(self, tmp_path):
        """
        Verifica la persistencia segura de trades en SQLite con modo WAL.
        """
        import sqlite3
        db_file = str(tmp_path / "test_trades.sqlite")
        auditor = AuditorMetricas(capital_inicial=100.0, db_path=db_file, auto_commit_db=True)

        t1 = TradeResult("TR_SQL_1", "SOCCER", 15.0, 7.5, True, time.time())
        auditor.registrar_trade(t1)

        # Verificar que el registro fue escrito en SQLite
        with sqlite3.connect(db_file) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT trade_id, symbol, stake, pnl, is_win FROM auditor_trades")
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == "TR_SQL_1"
        assert row[1] == "SOCCER"
        assert row[2] == 15.0
        assert row[3] == 7.5
        assert row[4] == 1


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestMetricasTier4RealWorldScenarios:
    """Validación empírica fuera de muestra (N = 300) per PLANnew.md §5."""

    def test_empirical_validation_gate_300_trades_pass(self):
        """
        Prueba de la Regla de Superación (PLANnew §5):
        Con N = 300 operaciones simuladas y un Win Rate de 55.0% (165 ganadas, 135 perdidas):
        sigma = 0.50 / sqrt(300) = 0.0288675.
        Z = (0.55 - 0.50) / 0.0288675 = 1.73205.
        Dado que Z = 1.732 > 1.645 y p-value = 0.0416 < 0.05,
        la compuerta de validación empírica aprueba la inyección de capital.
        """
        auditor = AuditorMetricas(capital_inicial=10.0)

        for i in range(165):
            auditor.registrar_trade(TradeResult(f"W_{i}", "SYM", stake=2.0, pnl=1.0, is_win=True, timestamp=time.time()))
        for i in range(135):
            auditor.registrar_trade(TradeResult(f"L_{i}", "SYM", stake=2.0, pnl=-1.0, is_win=False, timestamp=time.time()))

        validacion = auditor.validar_compuerta(n_min=300, p_umbral=0.05)
        assert validacion["aprobado"] is True
        assert validacion["n"] == 300
        assert validacion["z_score"] > 1.645
        assert validacion["p_value"] < 0.05
        assert "VALIDACION_APROBADA" in validacion["motivo"]

    def test_empirical_validation_gate_insufficient_sample_blocks(self):
        """
        Si el Win Rate es excelente (ej. 70%), pero N = 100 (< 300 mínimo),
        la compuerta bloquea por muestra insuficiente.
        """
        auditor = AuditorMetricas(capital_inicial=10.0)
        for i in range(70):
            auditor.registrar_trade(TradeResult(f"W_{i}", "SYM", 2.0, 1.0, True, time.time()))
        for i in range(30):
            auditor.registrar_trade(TradeResult(f"L_{i}", "SYM", 2.0, -1.0, False, time.time()))

        validacion = auditor.validar_compuerta(n_min=300, p_umbral=0.05)
        assert validacion["aprobado"] is False
        assert "Muestra insuficiente" in validacion["motivo"]
