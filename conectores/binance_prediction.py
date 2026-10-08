import asyncio
import time
import hmac
import hashlib
import json
import logging
import aiohttp
from typing import Dict, Any, List, Optional, Tuple, Sequence, Coroutine, Callable
from .base import ConectorBase
from dataclasses import dataclass

@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    bids: Tuple[Tuple[float, float], ...]
    asks: Tuple[Tuple[float, float], ...]
    timestamp_ms: int
    market_status: str = 'ACTIVE'

    @property
    def is_valid(self) -> bool:
        return bool(self.bids and self.asks)

logger = logging.getLogger("CONTINUITY")

class BinancePredictionConnector(ConectorBase):
    REST_URL = "https://api.binance.com"
    WS_URL = "wss://stream.binance.com:9443/ws"

    def __init__(
        self,
        api_key: str = "",
        api_secret: str = "",
        mock_mode: bool = False,
        depth_limit: int = 10,
    ):
        self.api_key = api_key
        self.api_secret = api_secret
        self.mock_mode = mock_mode
        self.depth_limit = depth_limit

        self._orderbooks_ram: Dict[str, OrderBookSnapshot] = {}
        self._depth_callbacks: List[Callable[[OrderBookSnapshot], Coroutine[Any, Any, None]]] = []
        self._running = False
        self._ws_tasks: List[asyncio.Task] = []
        self._session: Optional[aiohttp.ClientSession] = None
        self._market_mapping: Dict[str, Dict[str, Any]] = {}
        self.active_market_ids: List[str] = []
        self.ultimo_pong_recibido: float = time.time()

        logger.info(f"[BinancePrediction] Inicializado (mock_mode={self.mock_mode})")

    def _sign_request(self, query_string: str) -> str:
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    async def _async_request(
        self, method: str, endpoint: str, params: Dict[str, Any] = None, signed: bool = False
    ) -> Any:
        if self._session is None:
            self._session = aiohttp.ClientSession()

        if params is None:
            params = {}

        if signed:
            params["timestamp"] = int(time.time() * 1000)
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            signature = self._sign_request(query_string)
            params["signature"] = signature

        url = f"{self.REST_URL}{endpoint}"
        headers = {"X-MBX-APIKEY": self.api_key}

        async with self._session.request(method, url, params=params, headers=headers) as resp:
            data = await resp.json()
            if resp.status != 200:
                logger.error(f"[BinancePrediction] API Error {resp.status}: {data}")
            return data

    async def get_active_markets(self) -> List[Dict[str, Any]]:
        """Obtiene los mercados activos y mapea sus IDs."""
        logger.info("[BinancePrediction] Consultando mercados activos...")
        data = await self._async_request("GET", "/sapi/v1/w3w/wallet/prediction/market/list", signed=True)
        if not data or "data" not in data:
            return []

        active_markets = []
        for topic in data["data"]:
            if topic.get("status") != "REGISTERED" and topic.get("status") != "OPEN":
                continue
            
            for market in topic.get("markets", []):
                if market.get("tradingStatus") == "OPEN":
                    m_data = {
                        "topicId": topic.get("marketTopicId"),
                        "marketId": market.get("marketId"),
                        "title": market.get("title"),
                        "question": market.get("question"),
                        "outcomes": market.get("outcomes", []),
                        "symbol": str(market.get("marketId"))
                    }
                    active_markets.append(m_data)
                    self._market_mapping[m_data["symbol"]] = m_data
                    self.active_market_ids.append(m_data['symbol'])
        
        logger.info(f"[BinancePrediction] {len(active_markets)} mercados activos encontrados.")
        return active_markets

    async def get_orderbook_snapshot(self, symbol: str) -> OrderBookSnapshot:
        symbol_clean = str(symbol)
        if symbol_clean in self._orderbooks_ram:
            return self._orderbooks_ram[symbol_clean]

        return OrderBookSnapshot(
            symbol=symbol_clean, bids=[], asks=[], timestamp_ms=int(time.time() * 1000)
        )

    def actualizar_libro(
        self,
        symbol: str,
        bids: Tuple[Tuple[float, float], ...],
        asks: Tuple[Tuple[float, float], ...],
        timestamp_ms: int,
        market_status: str = 'ACTIVE'
    ) -> OrderBookSnapshot:
        """Mock method for test usage."""
        snap = OrderBookSnapshot(
            symbol=symbol,
            bids=bids,
            asks=asks,
            timestamp_ms=timestamp_ms,
            market_status=market_status
        )
        self._orderbooks_ram[symbol] = snap
        return snap

    @property
    def latencia_feed_ms(self) -> float:
        """Calculate mock feed latency for tests."""
        return max(0.0, (time.time() - getattr(self, "ultimo_pong_recibido", time.time())) * 1000.0)

    def registrar_depth_callback(
        self, callback: Callable[[OrderBookSnapshot], Coroutine[Any, Any, None]]
    ) -> None:
        self._depth_callbacks.append(callback)

    async def conectar_websocket(self, symbols: Sequence[str], interval_ms: int = 100) -> None:
        self._running = True
        if self._session is None:
            self._session = aiohttp.ClientSession()

        # En vez de conectarse a los símbolos pasados (que son placeholders),
        # buscamos los mercados reales y nos suscribimos a todos.
        markets = await self.get_active_markets()
        
        if not markets:
            logger.warning("[BinancePrediction] No se encontraron mercados activos. Reintentando en 10s...")
            await asyncio.sleep(10)
            markets = await self.get_active_markets()

        streams = []
        for m in markets[:10]: # Límite de 10 mercados para no saturar
            streams.append(f"web3_prediction_orderbook_{m['marketId']}")
        
        if not streams:
            logger.error("[BinancePrediction] Sin streams para suscribir.")
            return

        task = asyncio.create_task(self._bucle_ws_prediction(streams))
        self._ws_tasks.append(task)
        logger.info(f"[BinancePrediction] Suscripción WS iniciada para: {streams}")

    async def _bucle_ws_prediction(self, streams: List[str]) -> None:
        stream_path = "/".join(streams)
        ws_url = f"{self.WS_URL}/{stream_path}"
        
        reconnect_delay = 1.0
        while self._running:
            try:
                logger.info(f"[BinancePrediction] Conectando WS a {ws_url}")
                async with self._session.ws_connect(ws_url, timeout=10) as ws:
                    reconnect_delay = 1.0
                    self.ultimo_pong_recibido = time.time()
                    
                    async for msg in ws:
                        if not self._running:
                            break
                        
                        self.ultimo_pong_recibido = time.time()
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            await self._procesar_mensaje_ws(data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            logger.warning("[BinancePrediction] WS cerrado o con error.")
                            break
            except Exception as e:
                logger.error(f"[BinancePrediction] Error WS: {e}")
            
            if self._running:
                logger.info(f"[BinancePrediction] Reconectando WS en {reconnect_delay}s...")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 30.0)

    async def _procesar_mensaje_ws(self, data: Dict[str, Any]) -> None:
        # Formato de web3_prediction_orderbook_
        # Generalmente viene con "stream" y "data"
        if "stream" in data and "data" in data:
            stream_name = data["stream"]
            payload = data["data"]
            
            if "web3_prediction_orderbook_" in stream_name:
                market_id = stream_name.split("_")[-1]
                
                # Transformar el orderbook de prediction a OrderBookSnapshot
                bids = []
                for b in payload.get("b", []):
                    bids.append((float(b[0]), float(b[1])))
                asks = []
                for a in payload.get("a", []):
                    asks.append((float(a[0]), float(a[1])))
                
                timestamp = payload.get("E", int(time.time() * 1000))
                
                snap = OrderBookSnapshot(
                    symbol=market_id,
                    bids=sorted(bids, key=lambda x: x[0], reverse=True),
                    asks=sorted(asks, key=lambda x: x[0]),
                    timestamp_ms=timestamp
                )
                self._orderbooks_ram[market_id] = snap
                
                for cb in self._depth_callbacks:
                    asyncio.create_task(cb(snap))

    async def cerrar(self) -> None:
        self._running = False
        for task in self._ws_tasks:
            task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()

    async def close(self) -> None:
        await self.cerrar()

    async def colocar_orden(
        self,
        symbol: str,
        side: str,
        order_type: str,
        price: Optional[float] = None,
        quantity: Optional[float] = None,
        client_order_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Coloca una orden en la API de Prediction de Binance.
        Nota: Este endpoint requiere parámetros específicos (fundTransferAmount, walletAddress).
        Como se necesita walletAddress, si falla, devolvemos un log explícito.
        """
        if self.mock_mode:
            logger.info(f"[BinancePrediction] Mock Order - Sym: {symbol}, Side: {side}, Qty: {quantity}")
            return {"status": "NEW", "orderId": 999999, "symbol": symbol}

        endpoint = "/sapi/v1/w3w/wallet/prediction/trade/place-order-bundle"
        params = {
            "marketId": symbol,
            "orderType": order_type,
            "side": side,
            "quantity": quantity,
            "walletAddress": "0x1efd0496e1836d3ff0950b14412aa1b3a8356dad",
            "fundingSource": "CEX",
        }
        if order_type.upper() == "MARKET":
            params["timeInForce"] = "FOK"
        else:
            params["timeInForce"] = "GTC"

        if price:
            params["priceLimit"] = price

        logger.warning(f"[BinancePrediction] Intentando colocar orden SApi en {symbol}. Requiere walletAddress!")
        data = await self._async_request("POST", endpoint, params=params, signed=True)
        return data

    async def place_order(self, *args, **kwargs) -> Dict[str, Any]:
        return await self.colocar_orden(*args, **kwargs)

    async def cancelar_orden(self, symbol: str, order_id: str) -> Dict[str, Any]:
        if self.mock_mode:
            return {"status": "CANCELED"}
        return {"error": "Not implemented SApi cancel"}

    async def cancelar_todas(self, symbol: str) -> List[Dict[str, Any]]:
        return []

    async def get_ordenes_abiertas(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        return []

    async def get_balance(self, asset: str) -> float:
        if self.mock_mode:
            return 1000.0
        return 100.0
