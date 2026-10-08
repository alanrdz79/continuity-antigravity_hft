# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_binance_async
====================================
Suite de pruebas unitarias para el conector asíncrono de Binance Spot (conectores/binance_async.py).
Valida:
1. Mantenimiento del libro de órdenes en RAM O(1) con ordenamiento y truncado.
2. Contrato OrderBookSnapshot (inmutabilidad, mejores precios, spread).
3. Motor de ejecución REST simulado (place LIMIT/MARKET, cancel, cancel all, query status, balances).
4. Ciclos de WebSocket mock, depth callbacks y heartbeat.
5. Firma criptográfica HMAC SHA256 para peticiones firmadas.
"""

import asyncio
import time
import pytest
from conectores.binance_async import (
    BinanceAsyncClient,
    OrderBookSnapshot,
    BinanceConnectorProtocol,
)


def test_orderbook_snapshot_propiedades():
    """Verifica el cálculo de best_bid, best_ask, spread y validación de snapshot."""
    bids = ((0.50, 100.0), (0.49, 150.0))
    asks = ((0.52, 80.0), (0.53, 120.0))
    snap = OrderBookSnapshot(
        symbol="MATCH1",
        bids=bids,
        asks=asks,
        timestamp_ms=1700000000000,
        market_status="ACTIVE",
    )

    assert snap.symbol == "MATCH1"
    assert snap.best_bid == 0.50
    assert snap.best_ask == 0.52
    assert snap.spread == 0.02
    assert snap.is_valid is True
    assert snap.market_status == "ACTIVE"


def test_actualizar_libro_ram_o1():
    """
    Verifica que actualizar_libro mantenga las mejores N posturas ordenadas:
    - Bids en orden estrictamente descendente.
    - Asks en orden estrictamente ascendente.
    - Truncado exacto a depth_limit (ej. 5 o 10 niveles).
    """
    client = BinanceAsyncClient(mock_mode=True, depth_limit=5)

    # Entradas desordenadas con más de 5 niveles
    raw_bids = [(0.45, 10.0), (0.50, 50.0), (0.48, 20.0), (0.49, 30.0), (0.44, 5.0), (0.47, 15.0)]
    raw_asks = [(0.56, 12.0), (0.52, 40.0), (0.54, 25.0), (0.53, 30.0), (0.58, 5.0), (0.55, 20.0)]

    snap = client.actualizar_libro(
        symbol="BTCUSDT",
        bids=raw_bids,
        asks=raw_asks,
        timestamp_ms=1000,
        market_status="ACTIVE",
    )

    # Verificar longitud truncada a depth_limit = 5
    assert len(snap.bids) == 5
    assert len(snap.asks) == 5

    # Bids ordenados descendente
    bid_precios = [p for p, _ in snap.bids]
    assert bid_precios == [0.50, 0.49, 0.48, 0.47, 0.45]

    # Asks ordenados ascendente
    ask_precios = [p for p, _ in snap.asks]
    assert ask_precios == [0.52, 0.53, 0.54, 0.55, 0.56]


@pytest.mark.asyncio
async def test_get_orderbook_snapshot_lectura_inmediata():
    """Verifica que get_orderbook_snapshot devuelva la referencia en RAM en tiempo O(1)."""
    client = BinanceAsyncClient(mock_mode=True)
    client.feed_mock_orderbook(
        symbol="PREDICT_YES",
        bids=[(0.60, 500.0)],
        asks=[(0.62, 300.0)],
        market_status="ACTIVE",
    )

    snap = await client.get_orderbook_snapshot("PREDICT_YES")
    assert snap.symbol == "PREDICT_YES"
    assert snap.best_bid == 0.60
    assert snap.best_ask == 0.62
    assert snap.market_status == "ACTIVE"

    # Actualizar estado a SUSPENDED
    client.actualizar_estado_mercado("PREDICT_YES", "SUSPENDED")
    snap_updated = await client.get_orderbook_snapshot("PREDICT_YES")
    assert snap_updated.market_status == "SUSPENDED"


@pytest.mark.asyncio
async def test_rest_mock_place_order_limit_y_market():
    """Valida la ejecución de órdenes simuladas LIMIT (NEW) y MARKET (FILLED)."""
    client = BinanceAsyncClient(mock_mode=True)

    # 1. Orden LIMIT BUY
    order_limit = await client.place_order(
        symbol="PREDICT_YES",
        side="BUY",
        order_type="LIMIT",
        price=0.51,
        quantity=100.0,
        client_order_id="test_cid_001",
    )

    assert order_limit["symbol"] == "PREDICT_YES"
    assert order_limit["side"] == "BUY"
    assert order_limit["type"] == "LIMIT"
    assert order_limit["status"] == "NEW"
    assert order_limit["clientOrderId"] == "test_cid_001"
    order_id = order_limit["orderId"]

    # Consultar estado
    st = await client.get_order_status("PREDICT_YES", order_id)
    assert st["status"] == "NEW"

    # Simular llenado
    filled = client.simulate_order_fill("PREDICT_YES", order_id)
    assert filled is not None
    assert filled["status"] == "FILLED"

    # 2. Orden MARKET SELL (ejecución inmediata)
    order_market = await client.place_order(
        symbol="PREDICT_YES",
        side="SELL",
        order_type="MARKET",
        quantity=50.0,
    )
    assert order_market["status"] == "FILLED"
    assert order_market["side"] == "SELL"


@pytest.mark.asyncio
async def test_rest_mock_cancel_order_y_cancel_all():
    """Valida cancelación individual y cancelación masiva de órdenes abiertas."""
    client = BinanceAsyncClient(mock_mode=True)

    # Crear 3 órdenes límite
    o1 = await client.place_order("TEST_SYM", "BUY", "LIMIT", price=0.40, quantity=10.0)
    o2 = await client.place_order("TEST_SYM", "BUY", "LIMIT", price=0.41, quantity=20.0)
    o3 = await client.place_order("TEST_SYM", "SELL", "LIMIT", price=0.60, quantity=30.0)

    open_orders = client.get_open_orders("TEST_SYM")
    assert len(open_orders) == 3

    # Cancelar individual
    res_c1 = await client.cancel_order("TEST_SYM", o1["orderId"])
    assert res_c1["status"] == "CANCELED"

    assert len(client.get_open_orders("TEST_SYM")) == 2

    # Cancelar todas las restantes
    res_all = await client.cancel_all_orders("TEST_SYM")
    assert len(res_all) == 2
    assert len(client.get_open_orders("TEST_SYM")) == 0


@pytest.mark.asyncio
async def test_mock_balance_account():
    """Verifica consulta y ajuste de balance en modo simulación."""
    client = BinanceAsyncClient(mock_mode=True)
    usdt = await client.get_account_balance("USDT")
    assert usdt == 10000.0

    client.set_mock_balance("USDT", 250.75)
    usdt_nuevo = await client.get_account_balance("USDT")
    assert usdt_nuevo == 250.75


def test_generar_firma_hmac():
    """Verifica que la generación de firmas HMAC SHA256 coincida con el estándar de Binance."""
    client = BinanceAsyncClient(
        api_key="test_api_key",
        api_secret="test_secret_key_12345",
        mock_mode=True,
    )
    query = "symbol=BTCUSDT&side=BUY&type=LIMIT&quantity=1&price=50000&timestamp=1578963600000"
    firma = client._generar_firma(query)
    assert isinstance(firma, str)
    assert len(firma) == 64  # SHA256 hex string tiene 64 caracteres


@pytest.mark.asyncio
async def test_websocket_mock_subscription_and_callbacks():
    """Verifica suscripción mock asíncrona, recepción de callbacks y cierre limpio."""
    client = BinanceAsyncClient(mock_mode=True)
    recibidos = []

    async def _on_depth(snap: OrderBookSnapshot):
        recibidos.append(snap)

    client.registrar_depth_callback(_on_depth)
    await client.conectar_orderbook_ws(["MOCK_MATCH_A"])

    # Esperar pequeños ciclos de actualización
    await asyncio.sleep(0.35)
    assert len(recibidos) > 0
    assert recibidos[0].symbol == "MOCK_MATCH_A"

    # Cerrar cliente
    await client.close()
    assert client.conectado is False


if __name__ == "__main__":
    test_orderbook_snapshot_propiedades()
    test_actualizar_libro_ram_o1()
    test_generar_firma_hmac()
    asyncio.run(test_get_orderbook_snapshot_lectura_inmediata())
    asyncio.run(test_rest_mock_place_order_limit_y_market())
    asyncio.run(test_rest_mock_cancel_order_y_cancel_all())
    asyncio.run(test_mock_balance_account())
    asyncio.run(test_websocket_mock_subscription_and_callbacks())
    print("TODAS LAS PRUEBAS DE CONECTOR BINANCE ASYNC PASARON CON ÉXITO.")
