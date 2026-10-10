# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_r2_exactitud_financiera | CONTINUITY HFT Binance
==================================================================================
Suite de Verificación Formal de Exactitud Financiera (Requisito R2).

Valida de forma determinista y exhaustiva:
1. Criterio de Kelly (f* = fraccion * (p*(b+1)-1)/b) y límites estrictos [0.0, 0.25].
2. Dimensionamiento Real de Posición (S_nominal) modulado por racha (0.85^n),
   techo de clúster (15%) y Regla de Oro 3 (Top 3 BIDs).
3. Modo de dimensionamiento por Kelly Criterion.
4. Salida temprana por Target EV pre-match e in-play para Deportes y ESports.
5. Precisión matemática estricta a 4 decimales (0.0001) en todas las métricas.
6. Ciclo de aceleración $10 -> $100 -> $1,000 USD con compuerta empírica (N >= 300, p < 0.05, Z > 1.645).
7. Protocolo de Cosecha Autónoma al superar $1,000 USD:
   - Aislamiento exacto del 35% de ganancia neta a MXN.
   - Enrutamiento del 40% del remanente a gastos operativos.
   - Retención del 60% del remanente en reinversión compuesta.
"""

import math
import time
import pytest
from typing import Dict, Any

from continuitis.riesgo_binance import (
    EscudoFinancieroBinance,
    calcular_criterio_kelly,
    OrderProposal,
    RiskApprovedOrder,
    DEFAULT_EV_MINIMO,
    DEFAULT_MAX_CLUSTER_EXP,
    BINANCE_BNB_FEE_RATE,
)
from continuitis.tesoreria import (
    GestorTesoreria,
    UMBRAL_COSECHA_1000,
    UMBRAL_INYECCION_100,
    PCT_COSECHA_AUTONOMA,
    PCT_GASTOS_OPERACION,
    PCT_REINVERSION_COMPUESTA,
)
from continuitis.auditor_metricas import (
    AuditorMetricas,
    TradeResult,
)


class TestCriterioKelly:
    """Verificación de la fórmula del Criterio de Kelly y acotamiento a [0.0, 0.25]."""

    def test_criterio_kelly_formula_exacta(self):
        """
        f* = fraccion * ((p * (b + 1) - 1) / b), donde b = cuota_neta - 1.0.
        Para p = 0.55, cuota_neta = 2.0 (b = 1.0), fraccion = 0.25:
          ev = (0.55 * 2.0) - 1.0 = 0.10.
          kelly_puro = 0.10 / 1.0 = 0.10.
          f* = 0.25 * 0.10 = 0.0250.
        """
        f_star = calcular_criterio_kelly(p_estimada=0.55, cuota_neta=2.0, fraccion_kelly=0.25)
        assert f_star == 0.0250

        motor = EscudoFinancieroBinance()
        f_star_motor = motor.calcular_criterio_kelly(p_estimada=0.55, cuota_neta=2.0, fraccion_kelly=0.25)
        assert f_star_motor == 0.0250

    def test_criterio_kelly_con_comision_bnb(self):
        """
        Calcula cuota neta descontando comisión BNB (0.075%) y verifica Kelly:
        Cuota bruta = 2.0.
        Cuota neta = 1.0 + 1.0 * (1 - 0.00075) = 1.99925.
        b = 0.99925.
        p = 0.60.
        ev = (0.60 * 1.99925) - 1.0 = 0.19955.
        kelly_puro = 0.19955 / 0.99925 = 0.1997.
        f* = 0.25 * 0.1997 = 0.0499.
        """
        motor = EscudoFinancieroBinance()
        cuota_neta = motor.calcular_cuota_neta(2.0)
        assert abs(cuota_neta - 1.99925) < 1e-5

        f_star = motor.calcular_criterio_kelly(0.60, cuota_neta, fraccion_kelly=0.25)
        assert f_star == 0.0499

    def test_criterio_kelly_limites_y_acotamiento(self):
        """La fracción f* debe estar estrictamente acotada en [0.0, 0.25]."""
        motor = EscudoFinancieroBinance()

        # 1. Sin edge (EV <= 0): debe retornar 0.0
        assert motor.calcular_criterio_kelly(0.50, 2.0, 0.25) == 0.0
        assert motor.calcular_criterio_kelly(0.40, 2.0, 0.25) == 0.0

        # 2. Cuota inválida (<= 1.0): debe retornar 0.0
        assert motor.calcular_criterio_kelly(0.80, 1.0, 0.25) == 0.0
        assert motor.calcular_criterio_kelly(0.80, 0.95, 0.25) == 0.0

        # 3. Probabilidad inválida (<= 0): debe retornar 0.0
        assert motor.calcular_criterio_kelly(0.0, 2.0, 0.25) == 0.0
        assert motor.calcular_criterio_kelly(-0.1, 2.0, 0.25) == 0.0

        # 4. Edge extremo: no debe superar 0.2500
        assert motor.calcular_criterio_kelly(1.0, 10.0, 0.25) == 0.2500
        assert motor.calcular_criterio_kelly(0.99, 100.0, 0.50) == 0.2500


class TestDimensionamientoRealYReglasDeOro:
    """Verificación de dimensionamiento de posición, atenuación 0.85^n y techos."""

    def test_atenuacion_por_racha_0_85_potencia_n(self):
        """El factor de atenuación debe decrecer como 0.85^n y resetearse a 1.0 en victoria."""
        motor = EscudoFinancieroBinance()
        assert motor.factor_racha == 1.0

        for n in range(1, 6):
            motor.registrar_resultado(False)
            factor_esperado = round(0.85 ** n, 4)
            assert motor.consecutive_losses == n
            assert round(motor.factor_racha, 4) == factor_esperado

        # Victoria resetea inmediatamente a 1.0
        motor.registrar_resultado(True)
        assert motor.consecutive_losses == 0
        assert motor.factor_racha == 1.0

    def test_techo_de_cluster_estricto_15_porciento(self):
        """La exposición nunca debe exceder el 15% del bankroll."""
        motor = EscudoFinancieroBinance(pct_riesgo_fijo=0.015, max_cluster_exp=0.15)
        balance = 1000.0
        # Techo = 150.0 USD
        # Con stop loss de 2% (0.02), nominal teórico = (1000 * 0.015) / 0.02 = 750.0 USD
        res = motor.calcular_posicion(
            balance_actual=balance,
            p_estimada=0.60,
            cuota=2.0,
            pct_stop_loss=0.02,
        )
        assert res["operar"] is True
        assert res["stake"] == 150.0000
        assert res["clamped_by_cluster"] is True

        # Con exposición previa de 120.0 USD:
        res_parcial = motor.calcular_posicion(
            balance_actual=balance,
            p_estimada=0.60,
            cuota=2.0,
            pct_stop_loss=0.02,
            exposicion_cluster_actual=120.0,
        )
        assert res_parcial["stake"] == 30.0000

        # Con exposición completa (150.0 USD):
        res_lleno = motor.calcular_posicion(
            balance_actual=balance,
            p_estimada=0.60,
            cuota=2.0,
            pct_stop_loss=0.02,
            exposicion_cluster_actual=150.0,
        )
        assert res_lleno["operar"] is False
        assert "Exposición máxima" in res_lleno["motivo"]

    def test_regla_de_oro_3_techo_liquidez_top_3_bids(self):
        """El stake debe estar acotado por la liquidez en los primeros 3 niveles de BID."""
        motor = EscudoFinancieroBinance(pct_riesgo_fijo=0.015, max_cluster_exp=0.15)
        balance = 1000.0
        # Nominal acotado por clúster es 150.0. Si Top 3 BIDs solo tiene 42.5000:
        res = motor.calcular_posicion(
            balance_actual=balance,
            p_estimada=0.60,
            cuota=2.0,
            pct_stop_loss=0.05,
            top_3_bid_volumen=42.5,
        )
        assert res["operar"] is True
        assert res["stake"] == 42.5000
        assert res["clamped_by_liquidity"] is True

        # Si Top 3 BIDs no tiene volumen:
        res_vacio = motor.calcular_posicion(
            balance_actual=balance,
            p_estimada=0.60,
            cuota=2.0,
            pct_stop_loss=0.05,
            top_3_bid_volumen=0.0,
        )
        assert res_vacio["operar"] is False
        assert "Regla de Oro 3" in res_vacio["motivo"]

    def test_dimensionamiento_con_modo_kelly(self):
        """Evalúa dimensionamiento real usando Criterio de Kelly (usar_kelly=True)."""
        motor = EscudoFinancieroBinance(max_cluster_exp=0.15)
        balance = 1000.0
        # p = 0.60, cuota = 2.0 -> f* = 0.0499 (4.99% del capital) = 49.90 USD
        res = motor.calcular_posicion(
            balance_actual=balance,
            p_estimada=0.60,
            cuota=2.0,
            pct_stop_loss=0.05,
            usar_kelly=True,
            fraccion_kelly=0.25,
        )
        assert res["operar"] is True
        assert res["stake"] == 49.9000
        assert res["f_star_kelly"] == 0.0499
        assert res["clamped_by_cluster"] is False


class TestTargetEVSalidaAnticipada:
    """Verificación de salida anticipada por Target EV para Deportes y ESports."""

    def test_salida_temprana_deportes_tradicionales(self):
        """En deportes tradicionales (fútbol, etc.), audita target EV de +2.0% neto."""
        motor = EscudoFinancieroBinance()
        precio_entrada = 0.50
        # Con precio actual de BID 0.525:
        # retorno_neto = ((0.525 * (1 - 0.00075)) - 0.50) / 0.50 = (0.5246 - 0.50) / 0.50 = +0.0492 (+4.92%)
        evaluacion = motor.evaluar_target_ev_salida(
            precio_entrada=precio_entrada,
            precio_actual_bid=0.525,
            ev_objetivo_minimo=0.02,
        )
        assert evaluacion["cerrar_posicion"] is True
        assert evaluacion["motivo"] == "TARGET_EV_ALCANZADO"
        assert evaluacion["retorno_neto"] == 0.0492

    def test_salida_temprana_esports(self):
        """En ESports, evalúa target EV antes y después de cumplir el umbral."""
        motor = EscudoFinancieroBinance()
        precio_entrada = 0.48
        # Precio actual insuficiente: 0.485 (retorno ~ +0.97% < 2%)
        eval_pendiente = motor.evaluar_target_ev_salida(
            precio_entrada=precio_entrada,
            precio_actual_bid=0.485,
            ev_objetivo_minimo=0.02,
        )
        assert eval_pendiente["cerrar_posicion"] is False
        assert eval_pendiente["motivo"] == "EV_PENDIENTE"

        # Precio actual suficiente: 0.50 (retorno ~ +4.09% >= 2%)
        eval_cumplido = motor.evaluar_target_ev_salida(
            precio_entrada=precio_entrada,
            precio_actual_bid=0.50,
            ev_objetivo_minimo=0.02,
        )
        assert eval_cumplido["cerrar_posicion"] is True
        assert eval_cumplido["motivo"] == "TARGET_EV_ALCANZADO"


class TestExactitudCuatroDecimales:
    """Garantiza precisión estricta a 4 decimales (0.0001) en todas las métricas."""

    def test_precision_cuatro_decimales_metricas_analiticas(self):
        auditor = AuditorMetricas(capital_inicial=10.0)

        # Inyectar trades con valores fraccionarios
        auditor.registrar_trade(TradeResult("T1", "SYM", stake=2.3456, pnl=0.7891, is_win=True, timestamp=time.time()))
        auditor.registrar_trade(TradeResult("T2", "SYM", stake=1.9876, pnl=-0.5432, is_win=False, timestamp=time.time()))
        auditor.registrar_trade(TradeResult("T3", "SYM", stake=3.1415, pnl=1.4142, is_win=True, timestamp=time.time()))

        metricas = auditor.obtener_metricas()

        for clave in ["win_rate", "capital_acumulado", "roi", "yield", "pnl_total", "turnover_total"]:
            val = metricas[clave]
            assert isinstance(val, (int, float))
            # Comprobar que no tiene más de 4 decimales significativos
            assert val == round(val, 4), f"Métrica {clave}={val} no respeta 4 decimales"

        # Métricas individuales directas
        assert auditor.calcular_win_rate() == round(auditor.calcular_win_rate(), 4)
        assert auditor.calcular_capital_acumulado() == round(auditor.calcular_capital_acumulado(), 4)
        assert auditor.calcular_roi() == round(auditor.calcular_roi(), 4)
        assert auditor.calcular_yield() == round(auditor.calcular_yield(), 4)

    def test_precision_cuatro_decimales_dimensionamiento_riesgo(self):
        motor = EscudoFinancieroBinance()
        res = motor.calcular_posicion(
            balance_actual=123.4567,
            p_estimada=0.5876,
            cuota=1.9876,
            pct_stop_loss=0.0345,
            top_3_bid_volumen=78.9123,
        )
        for clave in ["ev", "cuota_neta", "stake", "riesgo_monetario", "factor_racha", "f_star_kelly"]:
            val = res[clave]
            assert val == round(val, 4), f"Campo de riesgo {clave}={val} no respeta 4 decimales"


class TestAceleracionYCosechaAutonoma:
    """Verificación de compuerta estadística ($10->$100) y Cosecha Autónoma (>= $1,000 USD)."""

    def test_compuerta_estadistica_gating_inyeccion_100_usd(self):
        """
        Inyección de +100 USD condicionada por:
        N >= 300 trades, p < 0.05 (Z > 1.645), Yield > 0.
        """
        tesoreria = GestorTesoreria(balance_inicial=10.0)
        tesoreria.balance = 100.0

        # Intento con N = 0: debe bloquearse
        hitos_bloqueados = tesoreria.verificar_hitos()
        assert hitos_bloqueados["hito_100_inyectado"] is False
        assert "INYECCION_BLOQUEADA_POR_VALIDACION" in hitos_bloqueados["acciones"]
        assert tesoreria.balance == 100.0

        # Llenar auditor con 300 trades con WR = 58% (Z = 2.771 > 1.645, p < 0.05)
        for i in range(174):
            tesoreria.auditor.registrar_trade(TradeResult(f"W_{i}", "S", 1.0, 0.5, True, time.time()))
        for i in range(126):
            tesoreria.auditor.registrar_trade(TradeResult(f"L_{i}", "S", 1.0, -0.5, False, time.time()))

        hitos_aprobados = tesoreria.verificar_hitos(n_min=300)
        assert hitos_aprobados["hito_100_inyectado"] is True
        assert "INYECCION_100_USD_APLICADA" in hitos_aprobados["acciones"]
        assert tesoreria.balance == 200.0  # 100 + 100 inyectados

    def test_protocolo_cosecha_autonoma_al_cruzar_1000_usd(self):
        """
        Simulación completa de balance alcanzando >= $1,000 USD:
        - Balance inicial: 1000.0 USD.
        - Ganancia neta: 500.0 USD (Balance = 1500.0 USD).
        - Tipo de cambio: 20.0 MXN/USD.
        - 35% de ganancia neta aislado a MXN:
          500 * 0.35 = 175.0000 USD (3,500.0000 MXN).
        - Remanente: 325.0000 USD.
        - 40% a gastos de operación: 325 * 0.40 = 130.0000 USD.
        - 60% a reinversión compuesta: 325 * 0.60 = 195.0000 USD.
        - Nuevo balance de trading: (1500 - 500) + 195 = 1195.0000 USD.
        """
        tesoreria = GestorTesoreria(balance_inicial=1000.0, tipo_cambio_mxn=20.0)
        tesoreria.balance = 1500.0

        resultado = tesoreria.ejecutar_cosecha_autonoma()
        assert resultado["cosecha_ejecutada"] is True
        assert resultado["ganancia_neta"] == 500.0000
        assert resultado["retiro_autonomo_35_usd"] == 175.0000
        assert resultado["retiro_autonomo_mxn"] == 3500.0000
        assert resultado["gastos_operacion_40_usd"] == 130.0000
        assert resultado["reinversion_compuesta_60_usd"] == 195.0000
        assert resultado["nuevo_balance_operativo"] == 1195.0000

        # Verificación de las bóvedas contables
        assert tesoreria.capital_aislado_cosecha_usd == 175.0000
        assert tesoreria.capital_aislado_cosecha_mxn == 3500.0000
        assert tesoreria.fondo_gastos_operacion_usd == 130.0000
        assert tesoreria.fondo_reinversion_total_usd == 195.0000
        assert tesoreria.balance == 1195.0000

    def test_verificar_hitos_auto_cosechar_en_cruzar_1000(self):
        """
        Verifica que verificar_hitos(auto_cosechar=True) dispare autónomamente
        la cosecha al cruzar el umbral de $1,000 USD.
        """
        tesoreria = GestorTesoreria(balance_inicial=10.0, tipo_cambio_mxn=20.0)
        # Crecimiento orgánico hasta 1200 USD (ganancia neta = 1190 USD)
        tesoreria.balance = 1200.0

        hitos = tesoreria.verificar_hitos(auto_cosechar=True)
        assert hitos["meta_1000_activada"] is True
        assert "COSECHA_AUTONOMA_EJECUTADA" in hitos["acciones"]

        # 35% de 1190 = 416.5 USD (8,330 MXN)
        assert hitos["capital_aislado_cosecha_usd"] == 416.5000
        assert hitos["capital_aislado_cosecha_mxn"] == 8330.0000
        assert tesoreria.capital_aislado_cosecha_usd == 416.5000
        assert tesoreria.capital_aislado_cosecha_mxn == 8330.0000
