# -*- coding: utf-8 -*-
"""
conectores.binance_async
========================
Cliente Asíncrono de Binance Spot para CONTINUITY HFT.

Componentes:
1. Conexión WebSocket para profundidad Level-2 (L2 Depth) con auto-reconexión,
   backoff exponencial y heartbeat ping/pong.
2. Mantenimiento en memoria RAM O(1) de las mejores 5 a 10 posturas de compra
   y venta con timestamps y estado de mercado ("ACTIVE" / "SUSPENDED").
3. Cliente REST asíncrono para ejecución de órdenes (Market / Limit, Buy / Sell,
   Cancel, Cancel All, Query Status, Balances).
4. Modo Mock / Simulación Offline completa para testing unitario y de integración
   sin requerir credenciales activas ni conexión de red externa.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
)

logger = logging.getLogger("CONTINUITY.BinanceAsync")


# ==============================================================================
# 1. INTERFACES Y CONTRATOS DE DATOS
# ==============================================================================

@dataclass(frozen=True)
class OrderBookSnapshot:
    """
    Fotograma inmutable del libro de órdenes Level-2.
    - bids: Tupla de (precio, volumen) ordenados descendentemente (mejor precio primero).
    - asks: Tupla de (precio, volumen) ordenados ascendentemente (mejor precio primero).
    """
    symbol: str
    bids: Tuple[Tuple[float, float], ...]
    asks: Tuple[Tuple[float, float], ...]
    timestamp_ms: int
    market_status: str = "ACTIVE"  # "ACTIVE" o "SUSPENDED"

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        if self.bids and self.asks:
            return round(self.asks[0][0] - self.bids[0][0], 6)
        return None

    @property
    def is_valid(self) -> bool:
        return bool(self.bids and self.asks)


class BinanceConnectorProtocol(Protocol):
    """Protocolo formal del conector de Binance exigido por PROJECT.md."""
    async def get_orderbook_snapshot(self, symbol: str) -> OrderBookSnapshot: ...
    async def place_order(
        self, symbol: str, side: str, order_type: str, price: Optional[float], quantity: float
    ) -> Dict[str, Any]: ...
    async def cancel_order(self, symbol: str, order_id: Union[str, int]) -> Dict[str, Any]: ...
    async def cancel_all_orders(self, symbol: str) -> List[Dict[str, Any]]: ...


# ==============================================================================
# 2. MOTOR DE SIMULACIÓN Y MOCKING (OFFLINE / UNIT TESTING)
# ==============================================================================

class MockOrderBookState:
    """Mantiene el estado simulado para un símbolo en modo mock."""
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self.bids: List[Tuple[float, float]] = []
        self.asks: List[Tuple[float, float]] = []
        self.market_status: str = "ACTIVE"
        self.last_update_ms: int = int(time.time() * 1000)

    def set_levels(
        self,
        bids: Sequence[Tuple[float, float]],
        asks: Sequence[Tuple[float, float]],
        market_status: Optional[str] = None,
        timestamp_ms: Optional[int] = None,
    ):
        self.bids = sorted([(float(p), float(v)) for p, v in bids if v > 0], key=lambda x: x[0], reverse=True)
        self.asks = sorted([(float(p), float(v)) for p, v in asks if v > 0], key=lambda x: x[0])
        if market_status is not None:
            self.market_status = market_status.upper()
        self.last_update_ms = timestamp_ms or int(time.time() * 1000)

    def snapshot(self, max_depth: int = 10) -> OrderBookSnapshot:
        return OrderBookSnapshot(
            symbol=self.symbol,
            bids=tuple(self.bids[:max_depth]),
            asks=tuple(self.asks[:max_depth]),
            timestamp_ms=self.last_update_ms,
            market_status=self.market_status,
        )


# ==============================================================================
# 3. CLIENTE ASÍNCRONO DE BINANCE SPOT
# ==============================================================================

class BinanceAsyncClient:
    """
    Cliente Asíncrono de alto rendimiento para Binance Spot y Mercados de Predicción.
    
    Características:
    - O(1) in-RAM snapshots mediante diccionario sincronizado.
    - Soporte nativo para modo real (WebSocket / REST) y modo Mock / Offline.
    - Manejo resiliente de desconexiones y reconexión exponencial.
    - Ping / Pong heartbeat continuo.
    """

    DEFAULT_REST_URL = "https://api.binance.com"
    DEFAULT_WS_URL = "wss://stream.binance.com:9443/ws"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        ws_url: Optional[str] = None,
        mock_mode: bool = False,
        depth_limit: int = 10,
        recv_window: int = 5000,
    ):
        self.api_key = api_key or ""
        self.api_secret = api_secret or ""
        self.base_url = (base_url or self.DEFAULT_REST_URL).rstrip("/")
        self.ws_url = (ws_url or self.DEFAULT_WS_URL).rstrip("/")
        self.mock_mode = mock_mode
        self.depth_limit = max(5, min(depth_limit, 20))
        self.recv_window = recv_window

        # Memoria O(1) en RAM para snapshots del libro de órdenes
        self._orderbooks_ram: Dict[str, OrderBookSnapshot] = {}
        self._ram_lock = asyncio.Lock()

        # Telemetría de conectividad y heartbeat
        self.ultimo_ping_enviado: float = 0.0
        self.ultimo_pong_recibido: float = time.time()
        self.latencia_feed_ms: float = 0.0
        self.conectado: bool = False
        self._running: bool = False

        # Tareas en segundo plano
        self._ws_tasks: List[asyncio.Task] = []
        self._heartbeat_task: Optional[asyncio.Task] = None

        # Callbacks opcionales para oyentes de profundidad
        self._depth_callbacks: List[Callable[[OrderBookSnapshot], Coroutine[Any, Any, None]]] = []

        # Estado del simulador mock
        self._mock_orderbooks: Dict[str, MockOrderBookState] = {}
        self._mock_orders: Dict[str, Dict[str, Any]] = {}
        self._mock_order_id_counter: int = 100000
        self._mock_balances: Dict[str, float] = {"USDT": 10000.0, "BNB": 10.0, "BTC": 1.0}

        logger.info(
            f"[BinanceAsync] Inicializado (mock_mode={self.mock_mode}, depth_limit={self.depth_limit})"
        )

    # --------------------------------------------------------------------------
    # GESTIÓN DEL LIBRO EN RAM O(1)
    # --------------------------------------------------------------------------

    def actualizar_libro(
        self,
        symbol: str,
        bids: Sequence[Tuple[float, float]],
        asks: Sequence[Tuple[float, float]],
        timestamp_ms: Optional[int] = None,
        market_status: str = "ACTIVE",
    ) -> OrderBookSnapshot:
        """
        Actualiza en RAM O(1) el libro de órdenes del símbolo indicado.
        Ordena y recorta a las mejores `depth_limit` posturas (bids descendente, asks ascendente).
        """
        symbol_clean = symbol.upper().replace("/", "").replace("-", "")
        ts = int(timestamp_ms) if timestamp_ms is not None else int(time.time() * 1000)

        # Sanitizar y ordenar
        clean_bids = sorted(
            [(float(p), float(v)) for p, v in bids if float(v) > 0 and float(p) > 0],
            key=lambda x: x[0],
            reverse=True,
        )[:self.depth_limit]

        clean_asks = sorted(
            [(float(p), float(v)) for p, v in asks if float(v) > 0 and float(p) > 0],
            key=lambda x: x[0],
        )[:self.depth_limit]

        snapshot = OrderBookSnapshot(
            symbol=symbol_clean,
            bids=tuple(clean_bids),
            asks=tuple(clean_asks),
            timestamp_ms=ts,
            market_status=market_status.upper(),
        )

        # Escritura O(1) en diccionario principal de memoria
        self._orderbooks_ram[symbol_clean] = snapshot

        # Actualizar telemetría de latencia si el timestamp viene del exchange
        ahora_ms = time.time() * 1000
        if ts > 0:
            self.latencia_feed_ms = max(0.0, ahora_ms - ts)
        self.ultimo_pong_recibido = time.time()

        return snapshot

    async def get_orderbook_snapshot(self, symbol: str) -> OrderBookSnapshot:
        """
        Lectura O(1) en RAM de las mejores posturas del símbolo.
        """
        symbol_clean = symbol.upper().replace("/", "").replace("-", "")
        if symbol_clean in self._orderbooks_ram:
            return self._orderbooks_ram[symbol_clean]

        # Si estamos en mock y existe un mock configurado
        if self.mock_mode and symbol_clean in self._mock_orderbooks:
            snap = self._mock_orderbooks[symbol_clean].snapshot(self.depth_limit)
            self._orderbooks_ram[symbol_clean] = snap
            return snap

        # Retorna snapshot vacío pero válido
        empty_snap = OrderBookSnapshot(
            symbol=symbol_clean,
            bids=(),
            asks=(),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        return empty_snap

    def actualizar_estado_mercado(self, symbol: str, status: str) -> None:
        """Modifica el estado de mercado ("ACTIVE" o "SUSPENDED") en el snapshot en RAM."""
        symbol_clean = symbol.upper().replace("/", "").replace("-", "")
        status_clean = status.upper()
        if symbol_clean in self._orderbooks_ram:
            current = self._orderbooks_ram[symbol_clean]
            updated = OrderBookSnapshot(
                symbol=current.symbol,
                bids=current.bids,
                asks=current.asks,
                timestamp_ms=int(time.time() * 1000),
                market_status=status_clean,
            )
            self._orderbooks_ram[symbol_clean] = updated
        elif self.mock_mode and symbol_clean in self._mock_orderbooks:
            self._mock_orderbooks[symbol_clean].market_status = status_clean

    def registrar_depth_callback(
        self, callback: Callable[[OrderBookSnapshot], Coroutine[Any, Any, None]]
    ) -> None:
        """Registra un callback asíncrono para notificaciones de profundidad."""
        self._depth_callbacks.append(callback)

    # --------------------------------------------------------------------------
    # WEBSOCKET L2 DEPTH CON RECONEXIÓN Y HEARTBEAT
    # --------------------------------------------------------------------------

    async def conectar_orderbook_ws(
        self, symbols: Union[str, List[str]], interval_ms: int = 100
    ) -> None:
        """
        Establece suscripción asíncrona al stream de profundidad Level-2 de Binance.
        En modo Mock, arranca un bucle simulado que alimenta datos sin conexión de red.
        """
        if isinstance(symbols, str):
            symbol_list = [symbols]
        else:
            symbol_list = list(symbols)

        self._running = True
        self.conectado = True

        # Iniciar monitoreo de heartbeat
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.create_task(self._ciclo_heartbeat())

        for sym in symbol_list:
            sym_clean = sym.upper().replace("/", "").replace("-", "")
            if self.mock_mode:
                task = asyncio.create_task(self._bucle_mock_ws(sym_clean))
            else:
                task = asyncio.create_task(self._bucle_ws_depth(sym_clean, interval_ms))
            self._ws_tasks.append(task)

        logger.info(f"[BinanceAsync] Suscripción WS iniciada para: {symbol_list}")

    async def _bucle_ws_depth(self, symbol: str, interval_ms: int = 100) -> None:
        """Bucle de conexión persistente con auto-reconexión y backoff exponencial."""
        backoff_delay = 1.0
        stream_name = f"{symbol.lower()}@depth{self.depth_limit}@{interval_ms}ms"
        stream_url = f"{self.ws_url}/{stream_name}"

        while self._running:
            try:
                # Importar websockets bajo demanda
                import websockets  # type: ignore

                logger.info(f"[BinanceWS] Conectando a {stream_url}...")
                async with websockets.connect(
                    stream_url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self.conectado = True
                    backoff_delay = 1.0  # Reset backoff tras conexión exitosa
                    logger.info(f"[BinanceWS] Conectado a stream {stream_name}")

                    while self._running:
                        try:
                            msg_raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                            data = json.loads(msg_raw)
                            self._procesar_mensaje_depth(symbol, data)
                        except asyncio.TimeoutError:
                            logger.warning(f"[BinanceWS] Timeout de recepción en {symbol}, enviando ping...")
                            pong_waiter = await ws.ping()
                            await asyncio.wait_for(pong_waiter, timeout=5.0)
                            self.ultimo_pong_recibido = time.time()

            except asyncio.CancelledError:
                logger.info(f"[BinanceWS] Tarea cancelada para {symbol}.")
                break
            except Exception as e:
                self.conectado = False
                logger.error(
                    f"[BinanceWS] Error en stream {symbol}: {e}. Reconectando en {backoff_delay:.1f}s..."
                )
                await asyncio.sleep(backoff_delay)
                backoff_delay = min(backoff_delay * 1.5, 30.0)

    def _procesar_mensaje_depth(self, symbol: str, data: Dict[str, Any]) -> None:
        """Decodifica el mensaje de profundidad de Binance y actualiza la RAM."""
        try:
            bids_raw = data.get("bids", []) or data.get("b", [])
            asks_raw = data.get("asks", []) or data.get("a", [])
            ts = data.get("E") or data.get("T") or int(time.time() * 1000)

            parsed_bids = [(float(b[0]), float(b[1])) for b in bids_raw]
            parsed_asks = [(float(a[0]), float(a[1])) for a in asks_raw]

            snapshot = self.actualizar_libro(
                symbol=symbol,
                bids=parsed_bids,
                asks=parsed_asks,
                timestamp_ms=ts,
            )

            # Notificar callbacks si existen
            for cb in self._depth_callbacks:
                asyncio.create_task(cb(snapshot))

        except Exception as e:
            logger.error(f"[BinanceWS] Error procesando payload de profundidad: {e}")

    async def _bucle_mock_ws(self, symbol: str) -> None:
        """Bucle de emisión de profundidad en modo offline simulado."""
        if symbol not in self._mock_orderbooks:
            # Crear un libro por defecto razonable si no fue precargado
            self.feed_mock_orderbook(
                symbol=symbol,
                bids=[(0.50, 100.0), (0.49, 150.0), (0.48, 200.0)],
                asks=[(0.52, 80.0), (0.53, 120.0), (0.54, 160.0)],
            )

        while self._running:
            try:
                await asyncio.sleep(0.1)  # Simula stream a 100ms
                mock_ob = self._mock_orderbooks[symbol]
                snap = mock_ob.snapshot(self.depth_limit)
                self._orderbooks_ram[symbol] = snap
                self.ultimo_pong_recibido = time.time()
                for cb in self._depth_callbacks:
                    asyncio.create_task(cb(snap))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[MockWS] Error en bucle simulado: {e}")
                await asyncio.sleep(0.5)

    async def _ciclo_heartbeat(self) -> None:
        """Ciclo continuo de verificación de salud del feed y conexión."""
        while self._running:
            try:
                await asyncio.sleep(5.0)
                ahora = time.time()
                delta_pong = ahora - self.ultimo_pong_recibido
                if delta_pong > 15.0:
                    logger.warning(
                        f"[BinanceHeartbeat] Alerta de latencia: no se recibe pong/datos hace {delta_pong:.1f}s"
                    )
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[BinanceHeartbeat] Error en ciclo heartbeat: {e}")

    # --------------------------------------------------------------------------
    # CLIENTE REST: FIRMAS Y EJECUCIÓN DE ÓRDENES
    # --------------------------------------------------------------------------

    def _generar_firma(self, query_string: str) -> str:
        """Calcula la firma HMAC SHA256 obligatoria para endpoints firmados de Binance."""
        if not self.api_secret:
            return ""
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        price: Optional[float] = None,
        quantity: float = 0.0,
        time_in_force: str = "GTC",
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Envía una orden de compra o venta a Binance Spot.
        Soporta 'LIMIT' y 'MARKET', lados 'BUY' y 'SELL'.
        """
        sym_clean = symbol.upper().replace("/", "").replace("-", "")
        side_clean = side.upper()
        type_clean = order_type.upper()

        if side_clean not in ("BUY", "SELL"):
            raise ValueError(f"Lado inválido '{side}'. Debe ser BUY o SELL.")
        if type_clean not in ("LIMIT", "MARKET"):
            raise ValueError(f"Tipo de orden inválido '{order_type}'. Debe ser LIMIT o MARKET.")
        if quantity <= 0:
            raise ValueError(f"Cantidad debe ser > 0, recibido {quantity}")
        if type_clean == "LIMIT" and (price is None or price <= 0):
            raise ValueError(f"Órdenes LIMIT requieren un precio > 0, recibido {price}")

        # Enrutamiento al simulador en modo mock
        if self.mock_mode:
            return self._mock_place_order(
                symbol=sym_clean,
                side=side_clean,
                order_type=type_clean,
                price=price,
                quantity=quantity,
                time_in_force=time_in_force,
                client_order_id=client_order_id,
            )

        # Modo de producción REST real
        endpoint = "/api/v3/order"
        params: Dict[str, Any] = {
            "symbol": sym_clean,
            "side": side_clean,
            "type": type_clean,
            "quantity": f"{quantity:.6f}".rstrip("0").rstrip("."),
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.recv_window,
        }
        if type_clean == "LIMIT":
            params["price"] = f"{price:.6f}".rstrip("0").rstrip(".")
            params["timeInForce"] = time_in_force
        if client_order_id:
            params["newClientOrderId"] = client_order_id

        return await self._request_rest("POST", endpoint, params, signed=True)

    async def cancel_order(
        self, symbol: str, order_id: Union[str, int]
    ) -> Dict[str, Any]:
        """Cancela una orden activa específica por su ID."""
        sym_clean = symbol.upper().replace("/", "").replace("-", "")
        if self.mock_mode:
            return self._mock_cancel_order(sym_clean, str(order_id))

        endpoint = "/api/v3/order"
        params = {
            "symbol": sym_clean,
            "orderId": order_id,
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.recv_window,
        }
        return await self._request_rest("DELETE", endpoint, params, signed=True)

    async def cancel_all_orders(self, symbol: str) -> List[Dict[str, Any]]:
        """Cancela atómicamente todas las órdenes abiertas para el símbolo dado."""
        sym_clean = symbol.upper().replace("/", "").replace("-", "")
        if self.mock_mode:
            return self._mock_cancel_all_orders(sym_clean)

        endpoint = "/api/v3/openOrders"
        params = {
            "symbol": sym_clean,
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.recv_window,
        }
        res = await self._request_rest("DELETE", endpoint, params, signed=True)
        if isinstance(res, list):
            return res
        return [res] if res else []

    async def get_order_status(
        self, symbol: str, order_id: Union[str, int]
    ) -> Dict[str, Any]:
        """Consulta el estado actual de una orden (NEW, FILLED, CANCELED, etc.)."""
        sym_clean = symbol.upper().replace("/", "").replace("-", "")
        if self.mock_mode:
            order_key = f"{sym_clean}_{order_id}"
            if order_key in self._mock_orders:
                return dict(self._mock_orders[order_key])
            return {"symbol": sym_clean, "orderId": int(order_id), "status": "UNKNOWN"}

        endpoint = "/api/v3/order"
        params = {
            "symbol": sym_clean,
            "orderId": order_id,
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.recv_window,
        }
        return await self._request_rest("GET", endpoint, params, signed=True)

    async def get_account_balance(self, asset: str = "USDT") -> float:
        """Devuelve el balance disponible del activo especificado."""
        asset_clean = asset.upper()
        if self.mock_mode:
            return float(self._mock_balances.get(asset_clean, 0.0))

        endpoint = "/api/v3/account"
        params = {
            "timestamp": int(time.time() * 1000),
            "recvWindow": self.recv_window,
        }
        data = await self._request_rest("GET", endpoint, params, signed=True)
        balances = data.get("balances", [])
        for b in balances:
            if b.get("asset") == asset_clean:
                return float(b.get("free", 0.0))
        return 0.0

    async def _request_rest(
        self, method: str, endpoint: str, params: Dict[str, Any], signed: bool = False
    ) -> Any:
        """Ejecuta una petición HTTP asíncrona segura con aiohttp o fallback."""
        url = f"{self.base_url}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key}

        if signed:
            query_string = urllib.parse.urlencode(params)
            signature = self._generar_firma(query_string)
            query_string += f"&signature={signature}"
        else:
            query_string = urllib.parse.urlencode(params)

        try:
            import aiohttp  # type: ignore

            async with aiohttp.ClientSession() as session:
                if method == "GET":
                    target_url = f"{url}?{query_string}" if query_string else url
                    async with session.get(target_url, headers=headers, timeout=10) as resp:
                        res_json = await resp.json()
                        resp.raise_for_status()
                        return res_json
                elif method == "POST":
                    target_url = f"{url}?{query_string}" if query_string else url
                    async with session.post(target_url, headers=headers, timeout=10) as resp:
                        res_json = await resp.json()
                        resp.raise_for_status()
                        return res_json
                elif method == "DELETE":
                    target_url = f"{url}?{query_string}" if query_string else url
                    async with session.delete(target_url, headers=headers, timeout=10) as resp:
                        res_json = await resp.json()
                        resp.raise_for_status()
                        return res_json
                else:
                    raise ValueError(f"Método HTTP no soportado: {method}")

        except ImportError:
            # Fallback síncrono si aiohttp no estuviera presente
            import requests  # type: ignore

            loop = asyncio.get_event_loop()

            def _sync_req():
                target_url = f"{url}?{query_string}" if query_string else url
                r = requests.request(method, target_url, headers=headers, timeout=10)
                r.raise_for_status()
                return r.json()

            return await loop.run_in_executor(None, _sync_req)

    # --------------------------------------------------------------------------
    # MOCK ENGINE IMPLEMENTATION
    # --------------------------------------------------------------------------

    def feed_mock_orderbook(
        self,
        symbol: str,
        bids: Sequence[Tuple[float, float]],
        asks: Sequence[Tuple[float, float]],
        market_status: str = "ACTIVE",
        timestamp_ms: Optional[int] = None,
    ) -> OrderBookSnapshot:
        """
        Método de conveniencia para inyectar datos de prueba en el simulador mock.
        Permite a los tests construir cualquier estado de libro deseado de forma determinista.
        """
        sym_clean = symbol.upper().replace("/", "").replace("-", "")
        if sym_clean not in self._mock_orderbooks:
            self._mock_orderbooks[sym_clean] = MockOrderBookState(sym_clean)

        self._mock_orderbooks[sym_clean].set_levels(
            bids=bids,
            asks=asks,
            market_status=market_status,
            timestamp_ms=timestamp_ms,
        )

        # Actualiza simultáneamente la memoria RAM O(1)
        snap = self.actualizar_libro(
            symbol=sym_clean,
            bids=bids,
            asks=asks,
            timestamp_ms=timestamp_ms,
            market_status=market_status,
        )
        return snap

    def set_mock_balance(self, asset: str, balance: float) -> None:
        """Establece balance simulado en el entorno mock."""
        self._mock_balances[asset.upper()] = float(balance)

    def _mock_place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        price: Optional[float],
        quantity: float,
        time_in_force: str,
        client_order_id: Optional[str],
    ) -> Dict[str, Any]:
        self._mock_order_id_counter += 1
        order_id = self._mock_order_id_counter
        cid = client_order_id or f"mock_{order_id}"
        now_ms = int(time.time() * 1000)

        # Órdenes MARKET se llenan inmediatamente; LIMIT quedan como NEW
        status = "FILLED" if order_type == "MARKET" else "NEW"
        executed_qty = quantity if status == "FILLED" else 0.0

        order_data = {
            "symbol": symbol,
            "orderId": order_id,
            "clientOrderId": cid,
            "transactTime": now_ms,
            "price": f"{price:.4f}" if price else "0.0000",
            "origQty": f"{quantity:.4f}",
            "executedQty": f"{executed_qty:.4f}",
            "cummulativeQuoteQty": f"{((price or 0.0) * executed_qty):.4f}",
            "status": status,
            "timeInForce": time_in_force,
            "type": order_type,
            "side": side,
        }

        order_key = f"{symbol}_{order_id}"
        self._mock_orders[order_key] = order_data
        logger.info(f"[MockBinance] Orden simulada creada: {order_data}")
        return dict(order_data)

    def _mock_cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        order_key = f"{symbol}_{order_id}"
        if order_key in self._mock_orders:
            self._mock_orders[order_key]["status"] = "CANCELED"
            return {
                "symbol": symbol,
                "orderId": int(order_id),
                "clientOrderId": self._mock_orders[order_key]["clientOrderId"],
                "status": "CANCELED",
            }
        return {"symbol": symbol, "orderId": int(order_id), "status": "CANCELED"}

    def _mock_cancel_all_orders(self, symbol: str) -> List[Dict[str, Any]]:
        canceled = []
        for key, order in self._mock_orders.items():
            if order["symbol"] == symbol and order["status"] == "NEW":
                order["status"] = "CANCELED"
                canceled.append({
                    "symbol": symbol,
                    "orderId": order["orderId"],
                    "clientOrderId": order["clientOrderId"],
                    "status": "CANCELED",
                })
        return canceled

    def simulate_order_fill(self, symbol: str, order_id: Union[str, int]) -> Optional[Dict[str, Any]]:
        """Permite a las pruebas simular el llenado (FILL) de una orden límite pendiente."""
        sym_clean = symbol.upper().replace("/", "").replace("-", "")
        order_key = f"{sym_clean}_{order_id}"
        if order_key in self._mock_orders:
            order = self._mock_orders[order_key]
            order["status"] = "FILLED"
            order["executedQty"] = order["origQty"]
            return dict(order)
        return None

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Lista las órdenes abiertas actualmente (simuladas en mock)."""
        sym_clean = symbol.upper().replace("/", "").replace("-", "") if symbol else None
        open_orders = []
        for order in self._mock_orders.values():
            if order["status"] == "NEW":
                if sym_clean is None or order["symbol"] == sym_clean:
                    open_orders.append(dict(order))
        return open_orders

    async def close(self) -> None:
        """Detiene todas las tareas asíncronas y limpia recursos."""
        self._running = False
        self.conectado = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
        for t in self._ws_tasks:
            if not t.done():
                t.cancel()
        logger.info("[BinanceAsync] Cliente cerrado y tareas canceladas.")
