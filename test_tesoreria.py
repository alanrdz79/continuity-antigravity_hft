# -*- coding: utf-8 -*-
"""
==================================================================================
test_tesoreria.py | Verificación de Riesgo, Métricas y Tesorería
==================================================================================
Script de simulación y validación formal de aceptación para:
1. Simulación de caja con racha de pérdidas y ganancias:
   - Verificación del factor de atenuación (factor_racha = 0.85^streak).
   - Verificación del tamaño de posición real (Position Sizing).
   - Control de techo de clúster (<= 15%).
   - Regla de Oro 3 (Acotación por volumen Top 3 BIDs).
2. Simulación de cruce de umbrales financieros:
   - Disparo condicionado del evento de inyección (+100 USD) bloqueado con N < 300.
   - Activación de inyección autorizada tras superar validación (N >= 300, p < 0.05, EV > 0).
   - Activación de umbral de cosecha autónoma ($1,000 USD).
   - Verificación de corte mensual en aceleración (40/60) y cosecha (35% MXN + remanente 40/60).
3. Prueba analítica de fórmulas continuas:
   - Win Rate (WR).
   - Capital Acumulado (B_N = B_0 * prod(1 + f_i * R_i)).
   - ROI (sum(PnL) / B_0).
   - Yield on turnover (sum(PnL) / sum(S_i)).
   - Total trades (N), Z-Score y p-value.
"""

import time
import math
from continuitis.riesgo_binance import (
    EscudoFinancieroBinance,
    OrderProposal,
    RiskApprovedOrder,
    BINANCE_BNB_FEE_RATE,
)
from continuitis.tesoreria import (
    GestorTesoreria,
    TradeResult,
    TreasuryAndHarvestingManager,
)
from continuitis.auditor_metricas import AuditorMetricas


def test_riesgo_y_racha():
    print("=" * 70)
    print("TEST 1: Simulación de Motor de Riesgo, Atenuación de Racha y Liquidez")
    print("=" * 70)

    riesgo = EscudoFinancieroBinance(
        pct_riesgo_fijo=0.015,
        ev_minimo=0.015,
        max_cluster_exp=0.15,
        factor_atenuacion_racha=0.85,
    )

    # 1.1 Validación de EV con descuento BNB
    # Prob = 0.55, Cuota = 2.00
    cuota_neta = riesgo.calcular_cuota_neta(2.00)
    ev_calculado = riesgo.calcular_ev(0.55, cuota_neta)
    expected_cuota_neta = 1.0 + 1.0 * (1.0 - BINANCE_BNB_FEE_RATE)
    assert abs(cuota_neta - expected_cuota_neta) < 1e-6, f"Error cuota neta: {cuota_neta}"
    assert ev_calculado >= 0.015, f"EV debió ser aprobado: {ev_calculado}"
    print(f"✓ Cuota neta con BNB ({cuota_neta:.6f}) y EV ({ev_calculado:.4f}) correctos")

    # Rechazo por EV insuficiente
    pos_baja = riesgo.calcular_posicion(balance_actual=100.0, p_estimada=0.50, cuota=1.90, pct_stop_loss=0.05)
    assert not pos_baja["operar"], "Operación con EV negativo debió ser rechazada"
    assert "EV insuficiente" in pos_baja["motivo"]
    print("✓ Filtro de EV mínimo (< 0.015) rechaza correctamente propuestas sin edge")

    # 1.2 Atenuación por Racha Perdedora (0.85^streak)
    balance = 100.0
    pct_stop = 0.05  # 5%

    # Racha = 0
    res0 = riesgo.calcular_posicion(balance_actual=balance, p_estimada=0.60, cuota=2.00, pct_stop_loss=pct_stop)
    assert res0["factor_racha"] == 1.0
    # S_nominal = (100 * 0.015 * 1.0) / 0.05 = 30.0. Clamped by cluster 15%: min(30, 15) = 15.0
    assert res0["stake"] == 15.0
    print(f"✓ Racha=0: factor_racha=1.0, stake={res0['stake']} (acotado por clúster 15%)")

    # Simulamos pérdida 1
    riesgo.registrar_resultado(es_ganadora=False)
    assert riesgo.consecutive_losses == 1
    assert abs(riesgo.factor_racha - 0.85) < 1e-6

    # Simulamos pérdida 2
    riesgo.registrar_resultado(es_ganadora=False)
    assert riesgo.consecutive_losses == 2
    assert abs(riesgo.factor_racha - (0.85 ** 2)) < 1e-6

    # Simulamos pérdida 3
    riesgo.registrar_resultado(es_ganadora=False)
    assert riesgo.consecutive_losses == 3
    factor_esperado = 0.85 ** 3
    assert abs(riesgo.factor_racha - factor_esperado) < 1e-6

    # Verificamos que el stake se reduce proporcionalmente
    # Riesgo objetivo = 100 * 0.015 * 0.614125 = 0.9211875
    # S_nominal = 0.9211875 / 0.05 = 18.42375. Clamped by cluster 15% (15.00)
    # Si probamos con balance=500:
    res3 = riesgo.calcular_posicion(balance_actual=100.0, p_estimada=0.60, cuota=2.00, pct_stop_loss=0.10)
    # Con stop loss 10%: S = (100 * 0.015 * 0.614125) / 0.10 = 9.21
    assert abs(res3["stake"] - 9.21) < 0.02
    print(f"✓ Racha=3: factor_racha={riesgo.factor_racha:.4f}, stake reducido correctamente a {res3['stake']}")

    # Reseteo en victoria
    riesgo.registrar_resultado(es_ganadora=True)
    assert riesgo.consecutive_losses == 0
    assert riesgo.factor_racha == 1.0
    print("✓ Reseteo de racha perdedora tras victoria: factor_racha vuelve a 1.0")

    # 1.3 Regla de Oro 3: Acotación dinámica por Top 3 BIDs
    # Proponemos una orden con stake nominal 15.0, pero con sólo 6.50 de volumen en top 3 BIDs
    res_liq = riesgo.calcular_posicion(
        balance_actual=100.0,
        p_estimada=0.60,
        cuota=2.00,
        pct_stop_loss=0.05,
        top_3_bid_volumen=6.50
    )
    assert res_liq["stake"] == 6.50
    assert res_liq["clamped_by_liquidity"] is True
    print(f"✓ Regla de Oro 3: Stake acotado exitosamente por liquidez Top 3 BIDs (15.00 -> {res_liq['stake']})")

    # Si liquidez es 0 -> Rechazo por falta de liquidez de escape
    res_sin_liq = riesgo.calcular_posicion(
        balance_actual=100.0,
        p_estimada=0.60,
        cuota=2.00,
        pct_stop_loss=0.05,
        top_3_bid_volumen=0.0
    )
    assert not res_sin_liq["operar"]
    assert "Regla de Oro 3 violada" in res_sin_liq["motivo"]
    print("✓ Regla de Oro 3: Rechazo confirmado ante 0 liquidez de escape")


def test_metricas_analiticas_y_compuerta():
    print("\n" + "=" * 70)
    print("TEST 2: Métricas Analíticas Continuas y Compuerta de Validación Z-Score")
    print("=" * 70)

    b0 = 10.0
    auditor = AuditorMetricas(capital_inicial=b0)

    # 2.1 Simulación analítica de 300 operaciones con edge genuino (Win Rate = 58%)
    # Para 300 trades con WR = 58%:
    # Ganadas = 174, Perdidas = 126
    # Z = 2 * sqrt(300) * (0.58 - 0.50) = 2 * 17.3205 * 0.08 = 2.771 > 1.645
    # p-value = 0.5 * erfc(2.771 / sqrt(2)) ~ 0.0028 < 0.05
    n_total = 300
    n_wins = 174
    n_losses = 126

    # Generamos trades secuenciales con stake = 1.0 USD
    # Win: pnl = +0.80 (cuota 1.80)
    # Loss: pnl = -1.00
    for i in range(n_wins):
        auditor.registrar_trade(TradeResult(
            trade_id=f"win_{i}",
            symbol="BTC_PREDICT",
            stake=1.0,
            pnl=0.80,
            is_win=True,
            timestamp=time.time()
        ))

    for i in range(n_losses):
        auditor.registrar_trade(TradeResult(
            trade_id=f"loss_{i}",
            symbol="BTC_PREDICT",
            stake=1.0,
            pnl=-1.00,
            is_win=False,
            timestamp=time.time()
        ))

    metricas = auditor.obtener_metricas()
    assert metricas["total_trades"] == 300
    assert abs(metricas["win_rate"] - 0.58) < 1e-4

    # PnL total = (174 * 0.80) - (126 * 1.00) = 139.2 - 126 = +13.20 USD
    assert abs(metricas["pnl_total"] - 13.20) < 1e-2

    # ROI = 13.20 / 10.0 = 1.32 (132%)
    assert abs(metricas["roi"] - 1.32) < 1e-2

    # Yield = 13.20 / 300.0 = 0.044 (4.4%)
    assert abs(metricas["yield"] - 0.044) < 1e-3

    # Capital Acumulado fórmula B_N = B_0 * prod(1 + f_i * R_i)
    cap_acumulado = auditor.calcular_capital_acumulado()
    assert cap_acumulado > 10.0
    print(f"✓ Win Rate: {metricas['win_rate']:.4f} (174/300)")
    print(f"✓ PnL Total: {metricas['pnl_total']:.2f} USD | ROI: {metricas['roi']:.2%} | Yield: {metricas['yield']:.2%}")
    print(f"✓ Capital Acumulado B_N: {cap_acumulado:.2f} USD")

    # 2.2 Validación de la Compuerta Z-Score & p-value
    validacion = auditor.validar_compuerta(n_min=300, p_umbral=0.05)
    assert validacion["aprobado"] is True
    assert validacion["z_score"] > 1.645
    assert validacion["p_value"] < 0.05
    print(f"✓ Compuerta de validación: Z={validacion['z_score']:.4f} > 1.645 | p-value={validacion['p_value']:.6f} < 0.05 -> APROBADO")

    # 2.3 Simulación de compuerta fallida por muestra insuficiente (N < 300)
    auditor_corto = AuditorMetricas(capital_inicial=10.0)
    for i in range(50):
        auditor_corto.registrar_trade(TradeResult(
            trade_id=f"short_{i}",
            symbol="BTC_PREDICT",
            stake=1.0,
            pnl=0.80,
            is_win=True,
            timestamp=time.time()
        ))
    val_corto = auditor_corto.validar_compuerta(n_min=300)
    assert val_corto["aprobado"] is False
    assert "Muestra insuficiente" in val_corto["motivo"]
    print("✓ Compuerta bloquea adecuadamente con N=50 < 300")


def test_tesoreria_y_progresion_capital():
    print("\n" + "=" * 70)
    print("TEST 3: Tesorería, Inyección Condicionada (+100 USD) y Cosecha Autónoma")
    print("=" * 70)

    tesoreria = GestorTesoreria(balance_inicial=10.0, tipo_cambio_mxn=20.0)

    # 3.1 El balance llega a 105 USD pero SIN validación estadística (N = 50)
    tesoreria.balance = 105.0
    # Inyectamos 50 trades
    for i in range(50):
        tesoreria.auditor.registrar_trade(TradeResult(f"t_{i}", "SYM", 1.0, 0.5, True, time.time()))

    hitos = tesoreria.verificar_hitos()
    assert hitos["hito_100_inyectado"] is False
    assert "INYECCION_BLOQUEADA_POR_VALIDACION" in hitos["acciones"]
    assert tesoreria.balance == 105.0
    print("✓ Balance >= 100 USD detectado pero inyección BLOQUEADA por no cumplir N >= 300")

    # 3.2 Ahora completamos 300 trades con p < 0.05 y EV > 0
    # Reseteamos auditor e ingresamos 300 trades estadísticamente significativos
    tesoreria.auditor.reset()
    for i in range(180):  # WR = 60%
        tesoreria.auditor.registrar_trade(TradeResult(f"w_{i}", "SYM", 1.0, 0.8, True, time.time()))
    for i in range(120):
        tesoreria.auditor.registrar_trade(TradeResult(f"l_{i}", "SYM", 1.0, -1.0, False, time.time()))

    hitos_validado = tesoreria.verificar_hitos(n_min=300)
    assert hitos_validado["hito_100_inyectado"] is True
    assert "INYECCION_100_USD_APLICADA" in hitos_validado["acciones"]
    assert tesoreria.balance == 205.0  # 105 + 100 inyectados
    print(f"✓ Inyección de +100 USD APLICADA tras validación formal. Nuevo balance: {tesoreria.balance:.2f} USD")

    # No se debe duplicar la inyección
    hitos_dup = tesoreria.verificar_hitos()
    assert "INYECCION_100_USD_APLICADA" not in hitos_dup["acciones"]
    assert tesoreria.balance == 205.0
    print("✓ Inyección no se duplica en verificaciones subsecuentes")

    # 3.3 Corte mensual en Fase de Aceleración (< 1,000 USD)
    # Ganancia mensual = 200 USD
    # 40% operación = 80 USD, 60% reinversión = 120 USD, retiro MXN = 0
    balance_prev = tesoreria.balance
    corte_acel = tesoreria.corte_mensual(ganancia_mensual=200.0)
    assert corte_acel["retiro_autonomo_35"] == 0.0
    assert corte_acel["gastos_operacion_40"] == 80.0
    assert corte_acel["reinversion_compuesta_60"] == 120.0
    # Nuevo balance: balance_prev - 200 + 120 = balance_prev - 80
    assert abs(corte_acel["nuevo_balance"] - (balance_prev - 80.0)) < 1e-2
    print(f"✓ Corte mensual (<$1000): Gastos 40%={corte_acel['gastos_operacion_40']}, Reinversión 60%={corte_acel['reinversion_compuesta_60']}, Retiro=0")

    # 3.4 Cosecha Autónoma al superar 1,000 USD
    tesoreria.balance = 1200.0
    hitos_1000 = tesoreria.verificar_hitos()
    assert hitos_1000["meta_1000_activada"] is True
    assert "MODO_COSECHA_AUTONOMA_DISPONIBLE" in hitos_1000["acciones"]
    print(f"✓ Umbral >= $1,000 USD superado: Modo de Cosecha Autónoma ACTIVADO")

    # Corte mensual con cosecha autónoma:
    # Ganancia mensual = 500 USD
    # Retiro 35% = 175 USD (3,500 MXN @ 20.0 FX)
    # Remanente = 325 USD:
    # Gastos 40% de 325 = 130 USD
    # Reinversión 60% de 325 = 195 USD
    balance_antes_cosecha = tesoreria.balance
    corte_cosecha = tesoreria.corte_mensual(ganancia_mensual=500.0, tipo_cambio_mxn=20.0)
    assert corte_cosecha["retiro_autonomo_35"] == 175.0
    assert corte_cosecha["retiro_autonomo_mxn"] == 3500.0
    assert corte_cosecha["gastos_operacion_40"] == 130.0
    assert corte_cosecha["reinversion_compuesta_60"] == 195.0
    # Balance: (1200 - 500) + 195 = 895.0
    assert abs(corte_cosecha["nuevo_balance"] - 895.0) < 1e-2
    print(f"✓ Cosecha Autónoma (>= $1000): Retiro 35%={corte_cosecha['retiro_autonomo_35']} USD ({corte_cosecha['retiro_autonomo_mxn']} MXN)")
    print(f"  Remanente split: Gastos 40%={corte_cosecha['gastos_operacion_40']} USD, Reinversión 60%={corte_cosecha['reinversion_compuesta_60']} USD")


def run_all():
    test_riesgo_y_racha()
    test_metricas_analiticas_y_compuerta()
    test_tesoreria_y_progresion_capital()
    print("\n" + "=" * 70)
    print("¡TODAS LAS PRUEBAS DE M2 (RIESGO, TESORERÍA, MÉTRICAS) PASARON EXITOSAMENTE!")
    print("=" * 70)


if __name__ == "__main__":
    run_all()
