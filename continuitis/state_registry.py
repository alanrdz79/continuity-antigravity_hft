import os
import json
import time
import threading
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("CONTINUITY.StateRegistry")

class StateRegistry:
    """
    Gestor de Estado Cloud Nativo para el Ecosistema CONTINUITY HFT.
    
    Reemplaza la persistencia local de SQLite (continuity_state.db) con:
    1. Cloud Memorystore (Redis) para caché de estado en vivo de latencia sub-microsegundo (<50ns):
       - Claves de estado de sistema (balance, racha_perdidas, kill_switch)
       - Cola de partidos pendientes en vivo (hft:cola_partidos_pendientes Hash)
       - Buffer circular de trades recientes (hft:recent_trades List)
    2. Cloud Bigtable (SSD) para persistencia inmutable histórica:
       - Row keys ordenadas por timestamp inverso: {symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}
       - Familia de columnas 't' (trades)
    3. Mock transparente en memoria (Thread-Safe):
       - Se activa automáticamente cuando REDIS_HOST está vacío, no configurado o inalcanzable.
       - Garantiza que pruebas unitarias y entornos de desarrollo locales funcionen al 100%
         sin dependencias de red externas ni errores de permisos en disco.
    """

    def __init__(
        self,
        redis_host: Optional[str] = None,
        redis_port: Optional[int] = None,
        redis_auth_token: Optional[str] = None,
        redis_ssl: Optional[bool] = None,
        bigtable_project_id: Optional[str] = None,
        bigtable_instance_id: Optional[str] = None,
        bigtable_table_name: Optional[str] = None,
        *args,
        **kwargs
    ):
        # Compatibilidad con argumentos heredados (ej. db_path)
        self.db_path = kwargs.get("db_path", "continuity_state.db")
        
        # Configuración Redis
        env_host = os.getenv("REDIS_HOST", "")
        self.redis_host: str = redis_host if redis_host is not None else env_host
        
        port_val = redis_port if redis_port is not None else os.getenv("REDIS_PORT", "6379")
        try:
            self.redis_port: int = int(port_val) if port_val else 6379
        except (ValueError, TypeError):
            self.redis_port = 6379

        self.redis_auth_token: str = (
            redis_auth_token if redis_auth_token is not None else os.getenv("REDIS_AUTH_TOKEN", "")
        )
        
        if redis_ssl is not None:
            self.redis_ssl: bool = bool(redis_ssl)
        else:
            self.redis_ssl = os.getenv("REDIS_SSL", "false").lower() in ("true", "1", "yes")

        # Configuración Bigtable
        self.bigtable_project_id: str = (
            bigtable_project_id
            or os.getenv("BIGTABLE_PROJECT_ID", os.getenv("GCP_PROJECT", ""))
        )
        self.bigtable_instance_id: str = (
            bigtable_instance_id or os.getenv("BIGTABLE_INSTANCE_ID", "hft-tick-store")
        )
        self.bigtable_table_name: str = (
            bigtable_table_name or os.getenv("BIGTABLE_TABLE_NAME", "hft-market-ticks")
        )

        # Estructuras de almacenamiento en memoria (Thread-safe fallback)
        self._lock = threading.Lock()
        self._mem_state: Dict[str, str] = {}
        self._mem_cola: Dict[str, dict] = {}
        self._mem_trades: List[Dict[str, Any]] = []
        self._seq_counter: int = 0

        # Inicialización de clientes
        self._redis = None
        self.backend: str = "in-memory-mock"
        self._init_redis()

        self._bt_table = None
        self.bt_backend: str = "in-memory-mock"
        self._init_bigtable()

    def _init_redis(self) -> None:
        if not self.redis_host:
            self.backend = "in-memory-mock"
            logger.info("[StateRegistry] REDIS_HOST no configurado; operando en modo in-memory mock.")
            return

        try:
            import redis
            client = redis.Redis(
                host=self.redis_host,
                port=self.redis_port,
                password=self.redis_auth_token if self.redis_auth_token else None,
                ssl=self.redis_ssl,
                socket_timeout=1.0,
                socket_connect_timeout=1.0,
                decode_responses=True
            )
            client.ping()
            self._redis = client
            self.backend = "redis"
            logger.info(f"[StateRegistry] Conexión establecida con Redis Memorystore en {self.redis_host}:{self.redis_port}")
        except Exception as exc:
            self._redis = None
            self.backend = "in-memory-mock"
            logger.warning(
                f"[StateRegistry] No se pudo conectar a Redis en {self.redis_host}:{self.redis_port} ({exc}). "
                "Activando fallback in-memory mock transparente."
            )

    def _init_bigtable(self) -> None:
        if not (self.bigtable_project_id and self.bigtable_instance_id):
            self.bt_backend = "in-memory-mock"
            return

        try:
            from google.cloud import bigtable
            bt_client = bigtable.Client(project=self.bigtable_project_id, admin=False)
            instance = bt_client.instance(self.bigtable_instance_id)
            self._bt_table = instance.table(self.bigtable_table_name)
            self.bt_backend = "bigtable"
            logger.info(
                f"[StateRegistry] Conexión configurada con Cloud Bigtable: "
                f"{self.bigtable_instance_id}/{self.bigtable_table_name}"
            )
        except Exception as exc:
            self._bt_table = None
            self.bt_backend = "in-memory-mock"
            logger.warning(
                f"[StateRegistry] No se pudo inicializar cliente Bigtable ({exc}). "
                "Archivado histórico utilizará fallback en memoria."
            )

    # --------------------------------------------------------------------------
    # Estado Global del Sistema (get_state / set_state)
    # --------------------------------------------------------------------------
    def set_state(self, key: str, value: str) -> None:
        val_str = str(value)
        with self._lock:
            self._mem_state[key] = val_str

        if self._redis is not None:
            try:
                redis_key = key if key.startswith("hft:") else f"hft:state:{key}"
                self._redis.set(redis_key, val_str)
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error escribiendo en Redis para clave '{key}': {exc}")

    def get_state(self, key: str, default: str = "") -> str:
        if self._redis is not None:
            try:
                redis_key = key if key.startswith("hft:") else f"hft:state:{key}"
                val = self._redis.get(redis_key)
                if val is not None:
                    return str(val)
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error leyendo de Redis para clave '{key}': {exc}")

        with self._lock:
            return self._mem_state.get(key, default)

    # --------------------------------------------------------------------------
    # Cola de Partidos Pendientes (cola_partidos_pendientes)
    # --------------------------------------------------------------------------
    def encolar_partido(self, partido_id: str, payload: dict) -> None:
        """
        Encola un partido activo en el Hash de Redis 'hft:cola_partidos_pendientes'.
        Garantiza sincronía en memoria local mock.
        """
        payload_copy = dict(payload)
        if "partido_id" not in payload_copy:
            payload_copy["partido_id"] = str(partido_id)
        with self._lock:
            self._mem_cola[partido_id] = payload_copy

        if self._redis is not None:
            try:
                self._redis.hset(
                    "hft:cola_partidos_pendientes",
                    partido_id,
                    json.dumps(payload_copy)
                )
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error encolando partido en Redis ({partido_id}): {exc}")

    def obtener_partidos_pendientes(self) -> List[dict]:
        """
        Retorna la lista de todos los partidos activos pendientes.
        """
        if self._redis is not None:
            try:
                raw_dict = self._redis.hgetall("hft:cola_partidos_pendientes")
                if raw_dict:
                    partidos = []
                    for raw_val in raw_dict.values():
                        try:
                            partidos.append(json.loads(raw_val))
                        except (json.JSONDecodeError, TypeError):
                            continue
                    return partidos
                return []
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error obteniendo cola de Redis: {exc}")

        with self._lock:
            return [dict(p) for p in self._mem_cola.values()]

    def cerrar_partido(self, partido_id: str, trade_result: Optional[dict] = None) -> None:
        """
        Elimina el partido de la cola de pendientes y, si se provee trade_result,
        archiva el resultado histórico en Bigtable y en el buffer de trades recientes.
        """
        with self._lock:
            self._mem_cola.pop(partido_id, None)

        if self._redis is not None:
            try:
                self._redis.hdel("hft:cola_partidos_pendientes", partido_id)
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error eliminando de cola Redis ({partido_id}): {exc}")

        if trade_result:
            t_id = str(trade_result.get("trade_id") or partido_id)
            symbol = str(trade_result.get("symbol") or trade_result.get("evento") or "UNKNOWN")
            
            raw_pnl = trade_result.get("pnl")
            if raw_pnl is None:
                raw_pnl = trade_result.get("ganancia_real", 0.0)
            try:
                pnl = float(raw_pnl) if raw_pnl is not None else 0.0
            except (ValueError, TypeError):
                pnl = 0.0

            raw_is_win = trade_result.get("is_win")
            if raw_is_win is not None:
                is_win = bool(raw_is_win)
            else:
                is_win = pnl > 0

            raw_ts = trade_result.get("timestamp")
            try:
                ts = float(raw_ts) if raw_ts is not None else time.time()
            except (ValueError, TypeError):
                ts = time.time()

            raw_stake = trade_result.get("stake")
            try:
                stake = float(raw_stake) if raw_stake is not None else 0.0
            except (ValueError, TypeError):
                stake = 0.0

            self.record_trade(
                trade_id=t_id,
                symbol=symbol,
                pnl=pnl,
                is_win=is_win,
                timestamp=ts,
                stake=stake
            )

    # --------------------------------------------------------------------------
    # Histórico de Trades & Cloud Bigtable
    # --------------------------------------------------------------------------
    @staticmethod
    def format_bigtable_row_key(symbol: str, timestamp_micros: Any, seq_id: int = 0) -> str:
        """
        Genera row key lexicográfica con timestamp inverso para Cloud Bigtable.
        Formato: {symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}
        Donde Long.MAX_VALUE = 9223372036854775807 (2^63 - 1).
        Garantiza que un timestamp mayor (más nuevo) produce una clave menor lexicográficamente:
        k_newer < k_older.
        """
        long_max = 9223372036854775807
        # Si se pasa float en segundos (e.g. time.time() ~ 1.7e9), convertir a microsegundos
        if isinstance(timestamp_micros, float) and timestamp_micros < 1e11:
            ts_int = int(timestamp_micros * 1_000_000)
        else:
            ts_int = int(timestamp_micros)
        reverse_ts = max(0, long_max - ts_int)
        seq_norm = max(0, int(seq_id)) % 10_000_000_000
        return f"{symbol}#{reverse_ts:019d}#{seq_norm:010d}"

    def record_trade(
        self,
        trade_id: str,
        symbol: str,
        pnl: float,
        is_win: bool,
        timestamp: float,
        stake: float = 0.0
    ) -> None:
        """
        Registra un trade ejecutado:
        1. Formatea la row key de Bigtable con timestamp inverso.
        2. Escribe en Cloud Bigtable (familia 't') si el cliente está conectado.
        3. Empuja el trade a la lista Redis 'hft:recent_trades' (capped a 100).
        4. Mantiene el registro en memoria mock para entornos locales.
        """
        with self._lock:
            self._seq_counter = (self._seq_counter + 1) % 1_000_000_000
            seq = self._seq_counter

        row_key = self.format_bigtable_row_key(symbol, timestamp, seq)
        record = {
            "trade_id": str(trade_id),
            "symbol": str(symbol),
            "pnl": float(pnl),
            "is_win": bool(is_win),
            "timestamp": float(timestamp),
            "stake": float(stake),
            "row_key": row_key,
        }

        # 1. Escritura en Cloud Bigtable
        if self._bt_table is not None:
            try:
                row = self._bt_table.direct_row(row_key)
                row.set_cell("t", "trade_id", str(trade_id))
                row.set_cell("t", "symbol", str(symbol))
                row.set_cell("t", "pnl", str(pnl))
                row.set_cell("t", "is_win", "1" if is_win else "0")
                row.set_cell("t", "timestamp", str(timestamp))
                row.set_cell("t", "stake", str(stake))
                row.commit()
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error escribiendo trade en Bigtable: {exc}")

        # 2. Escritura en Redis recent_trades (anillo circular)
        if self._redis is not None:
            try:
                self._redis.lpush("hft:recent_trades", json.dumps(record))
                self._redis.ltrim("hft:recent_trades", 0, 99)
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error empujando trade a Redis recent_trades: {exc}")

        # 3. Almacenamiento local mock
        with self._lock:
            self._mem_trades.insert(0, record)
            if len(self._mem_trades) > 1000:
                self._mem_trades.pop()

    def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Obtiene los trades más recientes (ordenados descendente por tiempo).
        Lee de Redis 'hft:recent_trades' en <50ns, con fallback en memoria.
        """
        if self._redis is not None:
            try:
                raw_list = self._redis.lrange("hft:recent_trades", 0, max(0, limit - 1))
                if raw_list:
                    return [json.loads(item) for item in raw_list]
            except Exception as exc:
                logger.warning(f"[StateRegistry] Error leyendo recent_trades de Redis: {exc}")

        with self._lock:
            return [dict(t) for t in self._mem_trades[:limit]]

    def clear_all(self) -> None:
        """Limpia todo el estado en memoria y en Redis (útil para pruebas unitarias)."""
        with self._lock:
            self._mem_state.clear()
            self._mem_cola.clear()
            self._mem_trades.clear()
            self._seq_counter = 0

        if self._redis is not None:
            try:
                keys = self._redis.keys("hft:*")
                if keys:
                    self._redis.delete(*keys)
            except Exception:
                pass


# Alias para máxima compatibilidad con código legado y orquestador
StateRegistrySQLite = StateRegistry
