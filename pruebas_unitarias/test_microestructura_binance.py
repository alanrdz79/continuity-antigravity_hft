# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_microestructura_binance
==============================================
Suite de pruebas unitarias exhaustivas para la Capa de Microestructura de Binance:
- Order Book Imbalance (OBI) y dominancia compradora exacta al 80% (I >= 0.60).
- Regla de Oro 1: Spread máximo <= $0.03 y rechazo si spread > $0.03.
- Regla de Oro 2: Bloqueo inmediato de órdenes si MarketStatus == 'SUSPENDED'.
- Regla de Oro 3: Agregación de volumen en los primeros 3 niveles de BID.
- Latency Circuit Breaker (< 800 ms) y Kill Switch.
- Precios límite HFT: Best Bid + 1 tick (Entrada) y Best Ask + 2 ticks (Salida).
- Motor integral MicroestructuraBinanceEngine.
"""

import time
import pytest
from continuitis.microestructura_binance import (
    OrderBookSnapshot,
    OrderProposal,
    MicrostructureSignal,
    OrderBookImbalanceCalculator,
    GoldenRulesValidator,
    HFTPriceCalculator,
    LatencyAndKillSwitchGuard,
    MicroestructuraBinanceEngine,
    MAX_SPREAD_PERMITIDO,
    BUY_DOMINANCE_IMBALANCE_THRESHOLD,
    MAX_FEED_LATENCY_MS,
)


# ==============================================================================
# 1. TEST ORDER BOOK IMBALANCE & 80% BUY DOMINANCE
# ==============================================================================

def test_imbalance_simetrico():
    """Libro simétrico debe tener imbalance I = 0.0 y dominancia False."""
    bids = ((0.50, 100.0), (0.49, 100.0))
    asks = ((0.52, 100.0), (0.53, 100.0))
    
    imbalance = OrderBookImbalanceCalculator.calcular_imbalance(bids, asks)
    ratio = OrderBookImbalanceCalculator.calcular_ratio_compra(bids, asks)
    dominancia = OrderBookImbalanceCalculator.detectar_dominancia_compra(imbalance)
    
    assert imbalance == 0.0
    assert ratio == 0.50
    assert dominancia is False


def test_imbalance_exacto_80_por_ciento():
    """
    80% volumen comprador y 20% vendedor debe resultar en:
    I = (800 - 200) / (800 + 200) = 600 / 1000 = 0.60 exacto.
    Dominancia compradora al 80% debe ser True.
    """
    bids = ((0.50, 500.0), (0.49, 300.0))  # Total Bids = 800.0
    asks = ((0.52, 150.0), (0.53, 50.0))   # Total Asks = 200.0
    
    imbalance = OrderBookImbalanceCalculator.calcular_imbalance(bids, asks)
    ratio = OrderBookImbalanceCalculator.calcular_ratio_compra(bids, asks)
    dominancia = OrderBookImbalanceCalculator.detectar_dominancia_compra(imbalance)
    
    assert abs(imbalance - 0.60) < 1e-6
    assert abs(ratio - 0.80) < 1e-6
    assert dominancia is True


def test_imbalance_frontera_inferior_a_80_por_ciento():
    """79% volumen comprador (I = 0.58) NO debe activar la dominancia del 80%."""
    bids = ((0.50, 790.0),)
    asks = ((0.52, 210.0),)  # 790 vs 210 -> I = 580/1000 = 0.58
    
    imbalance = OrderBookImbalanceCalculator.calcular_imbalance(bids, asks)
    ratio = OrderBookImbalanceCalculator.calcular_ratio_compra(bids, asks)
    dominancia = OrderBookImbalanceCalculator.detectar_dominancia_compra(imbalance)
    
    assert abs(imbalance - 0.58) < 1e-6
    assert abs(ratio - 0.79) < 1e-6
    assert dominancia is False


def test_imbalance_libro_vacio_o_cero():
    """Libros vacíos o sin volumen deben devolver 0.0 de forma segura."""
    assert OrderBookImbalanceCalculator.calcular_imbalance((), ()) == 0.0
    assert OrderBookImbalanceCalculator.calcular_ratio_compra((), ()) == 0.0
    assert OrderBookImbalanceCalculator.detectar_dominancia_compra(0.0) is False


# ==============================================================================
# 2. TEST REGLA DE ORO 1: SPREAD MÁXIMO <= $0.03
# ==============================================================================

def test_regla_oro_1_spread_valido():
    """Spread de $0.02 y $0.03 deben ser aceptados."""
    # Caso 1: Spread $0.02
    ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(0.50, 0.52)
    assert ok is True
    assert spread == 0.02
    assert motivo == "SPREAD_VALIDO"

    # Caso 2: Spread exacto $0.03 (límite superior permitido)
    ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(0.50, 0.53)
    assert ok is True
    assert spread == 0.03
    assert motivo == "SPREAD_VALIDO"


def test_regla_oro_1_spread_excesivo():
    """Spread de $0.031 y $0.05 deben ser rechazados sin excepción."""
    # Caso 1: $0.031
    ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(0.50, 0.531)
    assert ok is False
    assert "SPREAD_EXCESIVO" in motivo

    # Caso 2: $0.05
    ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(0.50, 0.55)
    assert ok is False
    assert "SPREAD_EXCESIVO" in motivo


def test_regla_oro_1_libro_invertido():
    """Si Best Ask < Best Bid, debe detectarse libro invertido e invalidarse."""
    ok, spread, motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(0.55, 0.50)
    assert ok is False
    assert "LIBRO_INVERTIDO" in motivo


# ==============================================================================
# 3. TEST REGLA DE ORO 2: BLOQUEO POR MERCADO SUSPENDIDO
# ==============================================================================

def test_regla_oro_2_mercado_activo():
    """Estados ACTIVE, TRADING y OPEN deben permitir la operativa."""
    for st in ["ACTIVE", "active", "TRADING", "OPEN"]:
        ok, motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(st)
        assert ok is True
        assert motivo == "MERCADO_ACTIVO"


def test_regla_oro_2_mercado_suspendido():
    """Estado SUSPENDED debe bloquear inmediatamente cualquier orden nueva."""
    for st in ["SUSPENDED", "suspended", "Suspended"]:
        ok, motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(st)
        assert ok is False
        assert motivo == "MERCADO_SUSPENDIDO_BINANCE"


# ==============================================================================
# 4. TEST REGLA DE ORO 3: AGREGACIÓN TOP 3 BIDS
# ==============================================================================

def test_regla_oro_3_agregacion_volumen():
    """Debe sumar estrictamente los primeros 3 niveles del BID ignorando niveles posteriores."""
    bids = (
        (0.50, 100.0),  # Nivel 1
        (0.49, 150.0),  # Nivel 2
        (0.48, 200.0),  # Nivel 3
        (0.47, 900.0),  # Nivel 4 (no debe sumarse)
        (0.46, 500.0),  # Nivel 5 (no debe sumarse)
    )
    
    liquidez_top3 = GoldenRulesValidator.calcular_liquidez_escape_top3_bids(bids)
    assert liquidez_top3 == 450.0  # 100 + 150 + 200 = 450

    # Orden con tamaño 400 <= 450 es válida
    ok, liq, motivo = GoldenRulesValidator.verificar_regla_oro_3_liquidez(400.0, bids)
    assert ok is True
    assert liq == 450.0

    # Orden con tamaño 500 > 450 es rechazada
    ok, liq, motivo = GoldenRulesValidator.verificar_regla_oro_3_liquidez(500.0, bids)
    assert ok is False
    assert "LIQUIDEZ_INSUFICIENTE_TOP3" in motivo


# ==============================================================================
# 5. TEST CÁLCULO DE PRECIOS HFT (ENTRADA Y SALIDA)
# ==============================================================================

def test_precios_hft_maker():
    """
    Entrada Maker: Best Bid + 1 tick
    Salida Maker:  Best Ask + 2 ticks
    """
    best_bid = 0.50
    best_ask = 0.52
    tick = 0.01

    entrada = HFTPriceCalculator.calcular_precio_entrada_limit_buy(best_bid, tick_size=tick)
    salida = HFTPriceCalculator.calcular_precio_salida_limit_sell(best_ask, tick_size=tick)

    assert entrada == 0.51  # 0.50 + 0.01
    assert salida == 0.54   # 0.52 + (2 * 0.01)


# ==============================================================================
# 6. TEST LATENCY GUARD Y CIRCUIT BREAKER
# ==============================================================================

def test_latency_guard_operacion_normal():
    """Con heartbeat fresco (< 800 ms) y mercado activo, el disparo debe autorizarse."""
    guard = LatencyAndKillSwitchGuard(max_latencia_ms=800.0)
    guard.registrar_pulso_feed(time.time())
    guard.actualizar_estado_binance("ACTIVE")

    ok, motivo = guard.autorizacion_disparo()
    assert ok is True
    assert motivo == "AUTORIZADO"


def test_latency_guard_disyuntor_por_retraso():
    """Si el delta de feed supera 800 ms, se activa disyuntor de emergencia."""
    guard = LatencyAndKillSwitchGuard(max_latencia_ms=800.0)
    # Simular pulso retrasado en 950 ms
    ahora = time.time()
    guard.registrar_pulso_feed(ahora - 0.95)

    ok, motivo = guard.autorizacion_disparo()
    assert ok is False
    assert "LATENCIA_EXCESIVA" in motivo
    assert guard.emergencia_activa is True

    # Al llegar un pulso nuevo y fresco, se re-estabiliza
    guard.registrar_pulso_feed(time.time())
    ok_nuevo, motivo_nuevo = guard.autorizacion_disparo()
    assert ok_nuevo is True
    assert motivo_nuevo == "AUTORIZADO"


def test_latency_guard_mercado_suspendido_y_kill_switch():
    """Comprobar bloqueo por suspensión de mercado y activación manual del kill switch."""
    guard = LatencyAndKillSwitchGuard()
    guard.registrar_pulso_feed(time.time())
    
    # Mercado suspendido
    guard.actualizar_estado_binance("SUSPENDED")
    ok, motivo = guard.autorizacion_disparo()
    assert ok is False
    assert motivo == "MERCADO_SUSPENDIDO_BINANCE"

    # Reset a activo
    guard.actualizar_estado_binance("ACTIVE")
    ok, _ = guard.autorizacion_disparo()
    assert ok is True

    # Kill switch manual
    guard.activar_kill_switch("PRUEBA_EMERGENCIA")
    ok, motivo = guard.autorizacion_disparo()
    assert ok is False
    assert "PRUEBA_EMERGENCIA" in motivo


# ==============================================================================
# 7. TEST INTEGRAL: MICROESTRUCTURA BINANCE ENGINE
# ==============================================================================

def test_engine_senal_optima_aprobada():
    """Un snapshot con todas las condiciones cumplidas genera señal autorizada y OrderProposal."""
    engine = MicroestructuraBinanceEngine(tick_size=0.01)

    snapshot = OrderBookSnapshot(
        symbol="MATCH_REAL_VS_BARCA",
        bids=((0.50, 400.0), (0.49, 300.0), (0.48, 100.0)),  # Sum = 800 (80%)
        asks=((0.52, 100.0), (0.53, 100.0)),                # Sum = 200 (20%)
        timestamp_ms=int(time.time() * 1000),
        market_status="ACTIVE",
    )

    senal = engine.evaluar_snapshot(snapshot, cantidad_propuesta=200.0)

    assert senal.autorizado is True
    assert senal.motivo == "CONDICIONES_OPTIMAS_HFT"
    assert senal.dominancia_compra_80 is True
    assert senal.spread_valido_gr1 is True
    assert senal.mercado_activo_gr2 is True
    assert senal.spread == 0.02
    assert senal.precio_entrada_limit_buy == 0.51
    assert senal.precio_salida_limit_sell == 0.54
    assert senal.propuesta_orden is not None
    assert senal.propuesta_orden.side == "BUY"
    assert senal.propuesta_orden.target_price == 0.51


def test_engine_rechazo_por_spread_alto():
    """Si el spread es $0.04 (> $0.03), el engine rechaza y no genera propuesta."""
    engine = MicroestructuraBinanceEngine()

    snapshot = OrderBookSnapshot(
        symbol="MATCH_CHELSEA_VS_ARSENAL",
        bids=((0.50, 800.0),),
        asks=((0.54, 200.0),),  # Spread = 0.04 > 0.03
        timestamp_ms=int(time.time() * 1000),
        market_status="ACTIVE",
    )

    senal = engine.evaluar_snapshot(snapshot)

    assert senal.autorizado is False
    assert "SPREAD_EXCESIVO" in senal.motivo
    assert senal.propuesta_orden is None


def test_engine_rechazo_por_mercado_suspendido():
    """Si el mercado está SUSPENDED, el engine bloquea la emisión de órdenes."""
    engine = MicroestructuraBinanceEngine()

    snapshot = OrderBookSnapshot(
        symbol="MATCH_LIVERPOOL_VS_CITY",
        bids=((0.50, 800.0),),
        asks=((0.52, 200.0),),
        timestamp_ms=int(time.time() * 1000),
        market_status="SUSPENDED",
    )

    senal = engine.evaluar_snapshot(snapshot)

    assert senal.autorizado is False
    assert "MERCADO_SUSPENDIDO_BINANCE" in senal.motivo
    assert senal.propuesta_orden is None


def test_engine_rechazo_por_falta_de_liquidez_escape():
    """Si la cantidad propuesta supera el volumen en los top 3 bids, rechaza por GR3."""
    engine = MicroestructuraBinanceEngine()

    snapshot = OrderBookSnapshot(
        symbol="MATCH_BAYERN_VS_DORTMUND",
        bids=((0.50, 50.0), (0.49, 50.0), (0.48, 50.0)),  # Top 3 BIDs = 150.0
        asks=((0.52, 20.0),),
        timestamp_ms=int(time.time() * 1000),
        market_status="ACTIVE",
    )

    # Cantidad propuesta = 300.0 > 150.0
    senal = engine.evaluar_snapshot(snapshot, cantidad_propuesta=300.0)

    assert senal.autorizado is False
    assert "LIQUIDEZ_INSUFICIENTE_TOP3" in senal.motivo
    assert senal.propuesta_orden is None


def test_regla_oro_1_nan_inf_rejection():
    """Valida que entradas NaN, Inf o -Inf en precios sean estrictamente rechazadas."""
    val = GoldenRulesValidator
    ok_nan1, _, mot_nan1 = val.verificar_regla_oro_1_spread(float("nan"), 0.52)
    assert ok_nan1 is False
    assert "SPREAD_INVALIDO" in mot_nan1

    ok_nan2, _, mot_nan2 = val.verificar_regla_oro_1_spread(0.50, float("nan"))
    assert ok_nan2 is False
    assert "SPREAD_INVALIDO" in mot_nan2

    ok_inf, _, mot_inf = val.verificar_regla_oro_1_spread(0.50, float("inf"))
    assert ok_inf is False
    assert "SPREAD_INVALIDO" in mot_inf


def test_hft_maker_price_one_tick_spread_joins_bid():
    """Valida que en spread de 1 tick la orden Maker se una al best bid en vez de cruzar el libro como Taker."""
    calc = HFTPriceCalculator
    # Spread = 0.01 == tick_size
    p_in = calc.calcular_precio_entrada_limit_buy(best_bid=0.50, tick_size=0.01, best_ask=0.51)
    assert p_in == 0.50, "Debe unirse a Best Bid (0.50) para no cruzar a Best Ask (0.51)"

    # Spread > 1 tick (0.02)
    p_in_wide = calc.calcular_precio_entrada_limit_buy(best_bid=0.50, tick_size=0.01, best_ask=0.52)
    assert p_in_wide == 0.51, "Con spread suficiente puede colocarse a Best Bid + 1 tick (0.51)"



if __name__ == "__main__":
    # Ejecución directa para verificación rápida
    test_imbalance_simetrico()
    test_imbalance_exacto_80_por_ciento()
    test_imbalance_frontera_inferior_a_80_por_ciento()
    test_imbalance_libro_vacio_o_cero()
    test_regla_oro_1_spread_valido()
    test_regla_oro_1_spread_excesivo()
    test_regla_oro_1_libro_invertido()
    test_regla_oro_2_mercado_activo()
    test_regla_oro_2_mercado_suspendido()
    test_regla_oro_3_agregacion_volumen()
    test_precios_hft_maker()
    test_latency_guard_operacion_normal()
    test_latency_guard_disyuntor_por_retraso()
    test_latency_guard_mercado_suspendido_y_kill_switch()
    test_engine_senal_optima_aprobada()
    test_engine_rechazo_por_spread_alto()
    test_engine_rechazo_por_mercado_suspendido()
    test_engine_rechazo_por_falta_de_liquidez_escape()
    print("TODAS LAS PRUEBAS DE MICROESTRUCTURA BINANCE PASARON CON ÉXITO.")
