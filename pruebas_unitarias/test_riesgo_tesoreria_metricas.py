# -*- coding: utf-8 -*-
"""
Pruebas unitarias para Milestone M2:
- continuitis.riesgo_binance (EV neto BNB, real position sizing, atenuación racha, clúster cap, Golden Rule 3)
- continuitis.tesoreria (Ordeño e Inyección $10->$100->$1000, validación gate N>=300, 40/60 split, 35% MXN harvest)
- continuitis.auditor_metricas (Win Rate, Capital Acumulado B_N, ROI, Yield, Total Trades, Z-score, p-value)
"""

import pytest
import math
import time

from continuitis.riesgo_binance import (
    EscudoFinancieroBinance,
    OrderProposal,
    RiskApprovedOrder,
    BINANCE_BNB_FEE_RATE,
    DEFAULT_EV_MINIMO,
)
from continuitis.tesoreria import (
    GestorTesoreria,
    TradeResult,
    TreasuryAndHarvestingManager,
)
from continuitis.auditor_metricas import (
    AuditorMetricas,
)


class TestRiesgoBinance:
    def test_ev_calculo_con_descuento_bnb(self):
        motor = EscudoFinancieroBinance()
        # Con cuota bruta = 2.0 y BNB discount (0.075%)
        # Cuota neta = 1.0 + (2.0 - 1.0) * (1.0 - 0.00075) = 1.99925
        cuota_neta = motor.calcular_cuota_neta(2.0)
        assert abs(cuota_neta - 1.99925) < 1e-5

        # EV = (p * cuota_neta) - 1.0
        p = 0.52
        ev = motor.calcular_ev(p, cuota_neta)
        assert abs(ev - (0.52 * 1.99925 - 1.0)) < 1e-6
        assert ev >= DEFAULT_EV_MINIMO

    def test_ev_insuficiente_rechaza(self):
        motor = EscudoFinancieroBinance()
        # Sin edge: p = 0.50, cuota = 2.00 -> EV ligeramente negativo por comisiones
        res = motor.calcular_posicion(
            balance_actual=100.0,
            p_estimada=0.50,
            cuota=2.00,
            pct_stop_loss=0.05
        )
        assert res["operar"] is False
        assert "EV insuficiente" in res["motivo"]
        assert res["stake"] == 0.0

    def test_real_position_sizing_formula(self):
        # S_nominal = (B * pct_riesgo_fijo * factor_racha) / max(pct_stop_loss, 0.01)
        motor = EscudoFinancieroBinance(pct_riesgo_fijo=0.015, max_cluster_exp=0.50)
        # B = 200, pct_riesgo_fijo = 0.015, factor_racha = 1.0, pct_stop_loss = 0.03
        # S_nominal = (200 * 0.015 * 1.0) / 0.03 = 3.0 / 0.03 = 100.0
        res = motor.calcular_posicion(
            balance_actual=200.0,
            p_estimada=0.60,
            cuota=2.00,
            pct_stop_loss=0.03,
        )
        assert res["operar"] is True
        assert abs(res["stake"] - 100.0) < 1e-2
        assert abs(res["riesgo_monetario"] - 3.0) < 1e-2

    def test_stop_loss_clamped_a_minimo_un_porciento(self):
        # max(pct_stop_loss, 0.01)
        motor = EscudoFinancieroBinance(pct_riesgo_fijo=0.01, max_cluster_exp=1.0)
        # pct_stop_loss = 0.002 (0.2%) debe ser limitado a 0.01 (1.0%)
        # S_nominal = (100 * 0.01 * 1.0) / 0.01 = 100.0
        res = motor.calcular_posicion(
            balance_actual=100.0,
            p_estimada=0.60,
            cuota=2.00,
            pct_stop_loss=0.002,
        )
        assert abs(res["stake"] - 100.0) < 1e-2

    def test_losing_streak_attenuation(self):
        # factor_racha = 0.85^streak, reset a 1.0 en win
        motor = EscudoFinancieroBinance()
        assert motor.factor_racha == 1.0

        motor.registrar_resultado(False)
        assert motor.consecutive_losses == 1
        assert abs(motor.factor_racha - 0.85) < 1e-6

        motor.registrar_resultado(False)
        assert motor.consecutive_losses == 2
        assert abs(motor.factor_racha - (0.85 ** 2)) < 1e-6

        motor.registrar_resultado(False)
        assert motor.consecutive_losses == 3
        assert abs(motor.factor_racha - (0.85 ** 3)) < 1e-6

        # Victoria resetea a 1.0
        motor.registrar_resultado(True)
        assert motor.consecutive_losses == 0
        assert motor.factor_racha == 1.0

    def test_cluster_exposure_cap(self):
        # Techo del 15% del bankroll
        motor = EscudoFinancieroBinance(pct_riesgo_fijo=0.015, max_cluster_exp=0.15)
        # Balance = 1000. Techo clúster = 150.
        # Con stop loss = 0.02, S_nominal = (1000 * 0.015) / 0.02 = 750.
        # Debe ser acotado a 150.
        res = motor.calcular_posicion(
            balance_actual=1000.0,
            p_estimada=0.60,
            cuota=2.00,
            pct_stop_loss=0.02,
        )
        assert res["stake"] == 150.0
        assert res["clamped_by_cluster"] is True

        # Si ya hay 140 comprometidos en el clúster:
        res2 = motor.calcular_posicion(
            balance_actual=1000.0,
            p_estimada=0.60,
            cuota=2.00,
            pct_stop_loss=0.02,
            exposicion_cluster_actual=140.0,
        )
        assert res2["stake"] == 10.0

        # Si el clúster está lleno (150 de 150):
        res3 = motor.calcular_posicion(
            balance_actual=1000.0,
            p_estimada=0.60,
            cuota=2.00,
            pct_stop_loss=0.02,
            exposicion_cluster_actual=150.0,
        )
        assert res3["operar"] is False
        assert "Exposición máxima" in res3["motivo"]

    def test_golden_rule_3_top_3_bids_liquidity(self):
        motor = EscudoFinancieroBinance(pct_riesgo_fijo=0.015, max_cluster_exp=0.15)
        # S_nominal acotado por clúster es 15.0
        # Pero si top 3 BIDs tiene solo 8.0 de volumen:
        res = motor.calcular_posicion(
            balance_actual=100.0,
            p_estimada=0.60,
            cuota=2.00,
            pct_stop_loss=0.05,
            top_3_bid_volumen=8.0,
        )
        assert res["stake"] == 8.0
        assert res["clamped_by_liquidity"] is True

        # Si top 3 BIDs tiene 0 liquidez:
        res_cero = motor.calcular_posicion(
            balance_actual=100.0,
            p_estimada=0.60,
            cuota=2.00,
            pct_stop_loss=0.05,
            top_3_bid_volumen=0.0,
        )
        assert res_cero["operar"] is False
        assert "Regla de Oro 3" in res_cero["motivo"]

    def test_evaluar_propuesta_interface_contract(self):
        motor = EscudoFinancieroBinance()
        propuesta = OrderProposal(
            symbol="BTC_PRED_YES",
            side="BUY",
            target_price=0.50,
            stop_price=0.475,  # 5% stop
            estimated_prob=0.60,
            payout_decimal=2.0,
            strategy_id="HFT_PHASE1"
        )
        orden = motor.evaluar_propuesta(
            proposal=propuesta,
            balance=100.0,
            top_3_bids=50.0
        )
        assert isinstance(orden, RiskApprovedOrder)
        assert orden.approved is True
        assert orden.symbol == "BTC_PRED_YES"
        assert orden.price == 0.50
        assert orden.quantity == 30.0  # stake 15.0 / 0.50 = 30.0 unidades


class TestAuditorMetricas:
    def test_metricas_continuas_exactas(self):
        auditor = AuditorMetricas(capital_inicial=10.0)

        # Trade 1: Stake 2.0, PnL +1.0, Win
        auditor.registrar_trade(TradeResult("t1", "S1", 2.0, 1.0, True, 1000.0))
        # Trade 2: Stake 2.0, PnL -1.0, Loss
        auditor.registrar_trade(TradeResult("t2", "S1", 2.0, -1.0, False, 1001.0))
        # Trade 3: Stake 3.0, PnL +1.5, Win
        auditor.registrar_trade(TradeResult("t3", "S1", 3.0, 1.5, True, 1002.0))

        metricas = auditor.obtener_metricas()
        assert metricas["total_trades"] == 3
        # WR = 2/3 = 0.6667
        assert abs(metricas["win_rate"] - (2 / 3)) < 1e-3

        # PnL total = 1.0 - 1.0 + 1.5 = +1.5
        assert abs(metricas["pnl_total"] - 1.5) < 1e-3

        # Turnover = 2.0 + 2.0 + 3.0 = 7.0
        assert abs(metricas["turnover_total"] - 7.0) < 1e-3

        # ROI = 1.5 / 10.0 = 0.15 (15%)
        assert abs(metricas["roi"] - 0.15) < 1e-3

        # Yield = 1.5 / 7.0 = 0.2143 (21.43%)
        assert abs(metricas["yield"] - (1.5 / 7.0)) < 1e-3

    def test_capital_acumulado_formula_compuesta(self):
        # B_N = B_0 * prod(1 + f_i * R_i)
        auditor = AuditorMetricas(capital_inicial=10.0)
        # B0 = 10.0
        # Trade 1: stake 2.0 (f1 = 2/10 = 0.2), pnl +2.0 (R1 = 2/2 = 1.0).
        # 1 + f1*R1 = 1 + 0.2 = 1.2 => B1 = 12.0
        auditor.registrar_trade(TradeResult("t1", "S1", 2.0, 2.0, True, 1.0))

        # Trade 2: stake 3.0 (f2 = 3/12 = 0.25), pnl -1.5 (R2 = -1.5/3 = -0.5).
        # 1 + f2*R2 = 1 - 0.125 = 0.875 => B2 = 12 * 0.875 = 10.5
        auditor.registrar_trade(TradeResult("t2", "S1", 3.0, -1.5, False, 2.0))

        cap = auditor.calcular_capital_acumulado()
        assert abs(cap - 10.5) < 1e-4

    def test_compuerta_estadistica_z_score_y_p_value(self):
        auditor = AuditorMetricas(capital_inicial=10.0)

        # Con N = 300 y WR = 0.58:
        # Z = 2 * sqrt(300) * (0.58 - 0.50) = 2.771 > 1.645
        # p < 0.05
        for i in range(174):
            auditor.registrar_trade(TradeResult(f"w_{i}", "S", 1.0, 0.8, True, 1.0))
        for i in range(126):
            auditor.registrar_trade(TradeResult(f"l_{i}", "S", 1.0, -1.0, False, 1.0))

        val = auditor.validar_compuerta(n_min=300, p_umbral=0.05)
        assert val["aprobado"] is True
        assert val["z_score"] > 1.645
        assert val["p_value"] < 0.05
        assert val["criterios"]["n_suficiente"] is True
        assert val["criterios"]["p_value_valido"] is True
        assert val["criterios"]["rendimiento_positivo"] is True


class TestTesoreria:
    def test_progreso_capital_10_a_100_inyeccion_gated(self):
        tesoreria = GestorTesoreria(balance_inicial=10.0)
        tesoreria.balance = 100.0

        # Sin validación estadística (N = 0)
        hitos = tesoreria.verificar_hitos(n_min=300)
        assert hitos["hito_100_inyectado"] is False
        assert "INYECCION_BLOQUEADA_POR_VALIDACION" in hitos["acciones"]
        assert tesoreria.balance == 100.0

        # Con validación forzada o cumplida
        hitos_aprobados = tesoreria.verificar_hitos(forzar_validacion=True)
        assert hitos_aprobados["hito_100_inyectado"] is True
        assert "INYECCION_100_USD_APLICADA" in hitos_aprobados["acciones"]
        assert tesoreria.balance == 200.0  # 100 + 100 inyectados

    def test_corte_mensual_fase_aceleracion(self):
        # < 1,000 USD: 40% operación, 60% reinversión, 0 retiro MXN
        tesoreria = GestorTesoreria(balance_inicial=100.0)
        res = tesoreria.corte_mensual(ganancia_mensual=50.0)
        assert res["retiro_autonomo_35"] == 0.0
        assert res["gastos_operacion_40"] == 20.0  # 50 * 0.40
        assert res["reinversion_compuesta_60"] == 30.0  # 50 * 0.60
        # Balance inicial era 100.0 (ya incluía los 50 de ganancia acumulada)
        # Se descuentan los 20 de gastos operativos -> 80.0
        assert res["nuevo_balance"] == 80.0

    def test_corte_mensual_fase_cosecha_autonoma(self):
        # >= 1,000 USD: 35% retiro a MXN, remanente split 40/60
        tesoreria = GestorTesoreria(balance_inicial=1500.0, tipo_cambio_mxn=20.0)
        tesoreria.meta_1000_activada = True

        res = tesoreria.corte_mensual(ganancia_mensual=1000.0)
        # 35% de 1000 = 350 USD (7,000 MXN)
        assert res["retiro_autonomo_35"] == 350.0
        assert res["retiro_autonomo_mxn"] == 7000.0
        # Remanente = 650 USD:
        # Gastos 40% = 260 USD
        # Reinversión 60% = 390 USD
        assert res["gastos_operacion_40"] == 260.0
        assert res["reinversion_compuesta_60"] == 390.0
        # Balance retiene reinversión (390): (1500 - 1000) + 390 = 890.0
        assert res["nuevo_balance"] == 890.0
