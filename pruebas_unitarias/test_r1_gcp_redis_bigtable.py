# -*- coding: utf-8 -*-
"""
==================================================================================
Pruebas Unitarias M1: Migración de Estado a GCP (Redis & Bigtable) y Eliminación de SQLite
==================================================================================
Suite de verificación exhaustiva para el Hito M1 (Requerimiento R1):
1. StateRegistry en modo In-Memory Mock (fallback transparente sin dependencias externas).
2. Operaciones de Estado en Vivo (balance, racha_perdidas, kill_switch).
3. Cola de Partidos Pendientes (encolar_partido, obtener_partidos_pendientes, cerrar_partido).
4. Generación y ordenamiento lexicográfico de Row Keys de Cloud Bigtable (reverse-timestamp).
5. Registro y consulta de histórico de trades (record_trade, get_recent_trades).
6. Integración con ControladorCluster.factor_cluster en continuitis/financiero.py sin SQLite.
7. Integración con HFTMemoryStore en continuitis/memoria_hft.py sin SQLite.
8. Verificación estricta de CERO generación de archivos .db / .sqlite / -wal / -shm en disco.
9. Simulación de cliente Redis activo y tolerancia a fallos de red.
10. Simulación de cliente Cloud Bigtable activo y tolerancia a excepciones de commit.
11. Concurrencia multi-hilo segura en StateRegistry.
"""

import os
import glob
import time
import json
import threading
from unittest.mock import MagicMock, patch
import pytest

from continuitis.state_registry import StateRegistry, StateRegistrySQLite
from continuitis.financiero import ControladorCluster, EscudoFinanciero
from continuitis.memoria_hft import HFTMemoryStore


# ==============================================================================
# TIER 1: StateRegistry en In-Memory Mock & Estado en Vivo
# ==============================================================================
class TestStateRegistryInMemoryState:
    """Valida operaciones de estado del sistema sobre StateRegistry."""

    def test_default_backend_is_in_memory(self):
        """StateRegistry arranca en modo in-memory mock cuando REDIS_HOST no está configurado."""
        with patch.dict(os.environ, {"REDIS_HOST": ""}, clear=False):
            registry = StateRegistry(redis_host="")
            assert registry.backend == "in-memory-mock"
            assert registry.bt_backend == "in-memory-mock"

    def test_state_set_and_get_balance(self):
        """Guarda y recupera balance del sistema con valor por defecto."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        assert registry.get_state("balance", "1000.0") == "1000.0"
        registry.set_state("balance", "1250.75")
        assert registry.get_state("balance") == "1250.75"

    def test_state_loss_streak_and_circuit_breaker(self):
        """Maneja racha de pérdidas y bandera de kill switch de emergencia."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        registry.set_state("racha_perdidas", "3")
        assert int(registry.get_state("racha_perdidas")) == 3

        registry.set_state("kill_switch", "1")
        assert registry.get_state("kill_switch") == "1"

        # Soporte para clave de emergencia con prefijo completo
        registry.set_state("hft:emergency:kill_switch_active", "true")
        assert registry.get_state("hft:emergency:kill_switch_active") == "true"


# ==============================================================================
# TIER 2: Cola de Partidos Pendientes (cola_partidos_pendientes)
# ==============================================================================
class TestColaPartidosPendientes:
    """Valida el ciclo de vida de la cola de partidos pendientes."""

    def test_encolar_y_obtener_partidos(self):
        """Encolar partidos y listarlos correctamente."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        payload_1 = {
            "partido_id": "P_001",
            "evento": "Real Madrid vs Barcelona",
            "stake": 75.50,
            "timestamp": "2026-10-10T15:00:00"
        }
        registry.encolar_partido("P_001", payload_1)

        pendientes = registry.obtener_partidos_pendientes()
        assert len(pendientes) == 1
        assert pendientes[0]["partido_id"] == "P_001"
        assert float(pendientes[0]["stake"]) == 75.50

        # Encolar segundo partido
        payload_2 = {
            "partido_id": "P_002",
            "evento": "Manchester City vs Arsenal",
            "stake": 120.00,
            "timestamp": "2026-10-10T16:00:00"
        }
        registry.encolar_partido("P_002", payload_2)

        pendientes_2 = registry.obtener_partidos_pendientes()
        assert len(pendientes_2) == 2
        ids = {p["partido_id"] for p in pendientes_2}
        assert ids == {"P_001", "P_002"}

    def test_cerrar_partido_sin_resultado(self):
        """Cerrar partido sin trade result lo remueve de la cola."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        registry.encolar_partido("P_003", {"stake": 50.0})
        assert len(registry.obtener_partidos_pendientes()) == 1

        registry.cerrar_partido("P_003")
        assert len(registry.obtener_partidos_pendientes()) == 0

    def test_cerrar_partido_con_trade_result(self):
        """Cerrar partido con trade result lo elimina de la cola y archiva el trade."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        registry.encolar_partido("P_004", {"stake": 100.0, "symbol": "BTCUSDT"})
        assert len(registry.obtener_partidos_pendientes()) == 1

        trade_result = {
            "trade_id": "T_999",
            "symbol": "BTCUSDT",
            "pnl": 24.50,
            "is_win": True,
            "timestamp": time.time(),
            "stake": 100.0
        }
        registry.cerrar_partido("P_004", trade_result=trade_result)

        # Cola vacía
        assert len(registry.obtener_partidos_pendientes()) == 0

        # Trade archivado
        trades = registry.get_recent_trades(limit=10)
        assert len(trades) >= 1
        assert trades[0]["trade_id"] == "T_999"
        assert trades[0]["pnl"] == 24.50
        assert trades[0]["is_win"] is True


# ==============================================================================
# TIER 3: Cloud Bigtable Row Key & Histórico de Trades
# ==============================================================================
class TestCloudBigtableRowKey:
    """Valida la especificación de row key lexicográfica con timestamp inverso."""

    def test_row_key_structure(self):
        """La clave tiene formato {symbol}#{reverse_ts:019d}#{seq_id:010d}."""
        symbol = "BTCUSDT"
        ts_micros = 1700000000000000
        seq_id = 42
        row_key = StateRegistry.format_bigtable_row_key(symbol, ts_micros, seq_id)

        partes = row_key.split("#")
        assert len(partes) == 3
        assert partes[0] == symbol
        assert len(partes[1]) == 19  # Inverted timestamp 19 dígitos
        assert len(partes[2]) == 10  # Seq ID 10 dígitos
        assert int(partes[2]) == 42

    def test_reverse_timestamp_lexicographical_ordering(self):
        """
        Garantiza que un timestamp mayor (más nuevo) produce una clave menor
        lexicográficamente en range scans de Bigtable: k_newer < k_older.
        """
        symbol = "ETHUSDT"
        t1 = 1700000000000000  # Más viejo
        t2 = 1700000001000000  # Medio
        t3 = 1700000002000000  # Más nuevo

        k1 = StateRegistry.format_bigtable_row_key(symbol, t1, 1)
        k2 = StateRegistry.format_bigtable_row_key(symbol, t2, 2)
        k3 = StateRegistry.format_bigtable_row_key(symbol, t3, 3)

        # En Bigtable scans, los datos más recientes deben aparecer primero
        assert k3 < k2 < k1, f"Error de ordenamiento: k3={k3}, k2={k2}, k1={k1}"

    def test_multi_timestamp_strictly_decreasing(self):
        """Serie creciente de timestamps genera serie estrictamente decreciente de claves."""
        timestamps = [1000, 2000, 5000, 10000, 999999, 1728500000000000]
        keys = [StateRegistry.format_bigtable_row_key("SOLUSDT", ts, idx) for idx, ts in enumerate(timestamps)]
        for i in range(len(keys) - 1):
            assert keys[i] > keys[i + 1]

    def test_float_seconds_timestamp_support(self):
        """Soporta floats en segundos (e.g. time.time()) convirtiendo a microsegundos."""
        now_1 = 1728500000.100
        now_2 = 1728500000.200
        k_old = StateRegistry.format_bigtable_row_key("BNBUSDT", now_1, 1)
        k_new = StateRegistry.format_bigtable_row_key("BNBUSDT", now_2, 2)
        assert k_new < k_old

    def test_record_and_get_recent_trades_chronological_limit(self):
        """record_trade almacena y get_recent_trades devuelve los más recientes primero."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        t_base = time.time()
        for i in range(15):
            registry.record_trade(
                trade_id=f"T_{i:03d}",
                symbol="BTCUSDT",
                pnl=float(i * 10 - 50),
                is_win=(i % 2 == 0),
                timestamp=t_base + i,
                stake=25.0
            )

        ultimos_5 = registry.get_recent_trades(limit=5)
        assert len(ultimos_5) == 5
        # El más nuevo es T_014
        assert ultimos_5[0]["trade_id"] == "T_014"
        assert ultimos_5[1]["trade_id"] == "T_013"


# ==============================================================================
# TIER 4: Eliminación Total de SQLite (Zero .db file generation)
# ==============================================================================
class TestZeroSQLiteFileGeneration:
    """Verifica que ninguna operación de M1 genere archivos SQLite en disco."""

    def test_zero_db_files_created_by_state_registry(self, tmp_path):
        """StateRegistry no crea ningún archivo .db o -wal aunque se le pase db_path."""
        db_file = tmp_path / "continuity_state.db"
        registry = StateRegistry(db_path=str(db_file), redis_host="")
        registry.set_state("balance", "1500.0")
        registry.encolar_partido("P_TEST", {"stake": 10.0})
        registry.record_trade("T_TEST", "BTCUSDT", 5.0, True, time.time())

        # Verificar que el archivo sqlite NO existe en disco
        assert not db_file.exists(), "StateRegistry no debe crear archivos .db locales"
        assert not (tmp_path / "continuity_state.db-wal").exists()
        assert not (tmp_path / "continuity_state.db-shm").exists()

    def test_zero_db_files_created_by_state_registry_sqlite_alias(self, tmp_path):
        """El alias StateRegistrySQLite tampoco genera archivos en disco."""
        db_file = tmp_path / "legacy.db"
        registry = StateRegistrySQLite(db_path=str(db_file))
        registry.set_state("racha_perdidas", "0")
        assert not db_file.exists()

    def test_zero_db_files_created_by_memoria_hft(self, tmp_path):
        """HFTMemoryStore no crea base de datos SQLite."""
        db_file = tmp_path / "metricas_hft.sqlite"
        store = HFTMemoryStore(db_path=str(db_file))
        store.registrar_orden_activa("ORD_1", {"stake": 20.0, "uid": "BTC_YES"})
        store.resolver_orden_hft("ORD_1", "WIN", 15.0, 1015.0)
        store.actualizar_estado_diario(1015.0)

        assert not db_file.exists(), "HFTMemoryStore no debe crear metricas_hft.sqlite"

    def test_zero_db_files_created_by_factor_cluster(self, tmp_path):
        """ControladorCluster.factor_cluster no interactúa con disco SQLite."""
        db_file = tmp_path / "cerebrillum.db"
        factor = ControladorCluster.factor_cluster(
            db_path=str(db_file),
            bankroll=1000.0,
            stake_propuesto=50.0
        )
        assert factor == 1.0
        assert not db_file.exists(), "factor_cluster no debe crear cerebrillum.db"


# ==============================================================================
# TIER 5: Integración con ControladorCluster (continuitis/financiero.py)
# ==============================================================================
class TestClusterControllerIntegration:
    """Valida que ControladorCluster.factor_cluster use StateRegistry sin SQLite."""

    def test_factor_cluster_attenuation_with_pending_queue(self):
        """factor_cluster calcula exposición actual leyendo de StateRegistry."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        bankroll = 1000.0
        # Techo = 1000 * 0.15 = 150.0
        # Encolamos partidos con 120.0 de stake total
        registry.encolar_partido("P1", {"stake": 60.0, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})
        registry.encolar_partido("P2", {"stake": 60.0, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})

        # Proponemos stake de 50.0. Total = 120 + 50 = 170 > 150.
        # Espacio disponible = 150 - 120 = 30.0
        # Factor = 30.0 / 50.0 = 0.60
        factor = ControladorCluster.factor_cluster(
            bankroll=bankroll,
            stake_propuesto=50.0,
            state_registry=registry
        )
        assert factor == 0.60

    def test_factor_cluster_saturado_returns_zero(self):
        """Cuando la exposición actual ya iguala o supera el techo, factor es 0.0."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        bankroll = 1000.0
        registry.encolar_partido("P_BIG", {"stake": 160.0, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})

        factor = ControladorCluster.factor_cluster(
            bankroll=bankroll,
            stake_propuesto=20.0,
            state_registry=registry
        )
        assert factor == 0.0

    def test_factor_cluster_libera_espacio_al_cerrar_partido(self):
        """Al cerrar partido, la exposición disminuye y el factor se restablece."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        bankroll = 1000.0
        registry.encolar_partido("P_TEMP", {"stake": 120.0, "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S")})
        assert ControladorCluster.factor_cluster(bankroll=bankroll, stake_propuesto=50.0, state_registry=registry) == 0.60

        # Cerrar el partido
        registry.cerrar_partido("P_TEMP")
        assert ControladorCluster.factor_cluster(bankroll=bankroll, stake_propuesto=50.0, state_registry=registry) == 1.0


# ==============================================================================
# TIER 6: Integración con HFTMemoryStore (continuitis/memoria_hft.py)
# ==============================================================================
class TestHFTMemoryStoreIntegration:
    """Valida la memoria HFT ultra-rápida y delegación a StateRegistry."""

    def test_memoria_hft_lifecycle_and_loss_streak(self):
        """HFTMemoryStore gestiona órdenes en RAM y actualiza racha en StateRegistry."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        store = HFTMemoryStore(state_registry=registry)
        store.registrar_orden_activa("OFFER_1", {"uid": "BTC_YES", "stake": 30.0, "cuota_elegida": 1.85})
        assert "OFFER_1" in store.ordenes_activas

        # Resolver como LOSS
        store.resolver_orden_hft("OFFER_1", "LOSS", -30.0, 970.0)
        assert store.racha_perdidas == 1
        assert registry.get_state("racha_perdidas") == "1"
        assert registry.get_state("balance") == "970.0"

        # Resolver siguiente como WIN restablece racha a 0
        store.registrar_orden_activa("OFFER_2", {"uid": "BTC_YES", "stake": 25.0, "cuota_elegida": 1.90})
        store.resolver_orden_hft("OFFER_2", "WIN", 22.5, 992.5)
        assert store.racha_perdidas == 0
        assert registry.get_state("racha_perdidas") == "0"
        assert registry.get_state("balance") == "992.5"

    def test_memoria_hft_actualizar_estado_diario(self):
        """actualiza bankroll diario máximo sin tocar SQLite."""
        registry = StateRegistry(redis_host="")
        store = HFTMemoryStore(state_registry=registry)

        max_bk = store.actualizar_estado_diario(1500.0)
        assert max_bk == 1500.0
        assert registry.get_state("max_bankroll_diario") == "1500.0"


# ==============================================================================
# TIER 7: Simulación de Cliente Redis Activo & Tolerancia a Fallos
# ==============================================================================
class TestRedisClientSimulation:
    """Valida llamadas a Redis cuando el cliente está activo y tolerancia a fallos."""

    def test_redis_methods_invoked_when_connected(self):
        """StateRegistry invoca primitivas de Redis (set, get, hset, hgetall, hdel, lpush)."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = "999.0"
        mock_redis.hgetall.return_value = {
            "P_REDIS": json.dumps({"partido_id": "P_REDIS", "stake": 40.0})
        }

        with patch("redis.Redis", return_value=mock_redis):
            registry = StateRegistry(redis_host="10.10.23.68", redis_port=6379)
            assert registry.backend == "redis"

            # set_state
            registry.set_state("balance", "1200.0")
            mock_redis.set.assert_called_with("hft:state:balance", "1200.0")

            # get_state
            val = registry.get_state("balance")
            mock_redis.get.assert_called_with("hft:state:balance")
            assert val == "999.0"

            # encolar_partido
            registry.encolar_partido("P_NEW", {"stake": 55.0})
            mock_redis.hset.assert_called()

            # obtener_partidos_pendientes
            pendientes = registry.obtener_partidos_pendientes()
            mock_redis.hgetall.assert_called_with("hft:cola_partidos_pendientes")
            assert len(pendientes) == 1
            assert pendientes[0]["partido_id"] == "P_REDIS"

            # cerrar_partido
            registry.cerrar_partido("P_REDIS")
            mock_redis.hdel.assert_called_with("hft:cola_partidos_pendientes", "P_REDIS")

    def test_redis_network_failure_fallback_transparent(self):
        """Excepciones de red en Redis no rompen la operativa; StateRegistry usa memoria."""
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.set.side_effect = Exception("Connection reset by peer")
        mock_redis.get.side_effect = Exception("Connection timeout")

        with patch("redis.Redis", return_value=mock_redis):
            registry = StateRegistry(redis_host="10.10.23.68")
            assert registry.backend == "redis"

            # No debe propagar la excepción
            registry.set_state("balance", "2500.0")
            # Debe recuperar de la memoria local
            assert registry.get_state("balance") == "2500.0"


# ==============================================================================
# TIER 8: Simulación de Cliente Cloud Bigtable & Tolerancia a Fallos
# ==============================================================================
class TestBigtableClientSimulation:
    """Valida llamadas a Cloud Bigtable cuando el cliente está activo."""

    def test_bigtable_direct_row_commit_invoked(self):
        """record_trade invoca DirectRow, set_cell y commit en Bigtable."""
        mock_table = MagicMock()
        mock_row = MagicMock()
        mock_table.direct_row.return_value = mock_row

        registry = StateRegistry(redis_host="")
        registry._bt_table = mock_table
        registry.bt_backend = "bigtable"

        registry.record_trade(
            trade_id="BT_001",
            symbol="BTCUSDT",
            pnl=50.0,
            is_win=True,
            timestamp=1700000000.0,
            stake=100.0
        )

        mock_table.direct_row.assert_called_once()
        mock_row.set_cell.assert_any_call("t", "trade_id", "BT_001")
        mock_row.set_cell.assert_any_call("t", "symbol", "BTCUSDT")
        mock_row.set_cell.assert_any_call("t", "pnl", "50.0")
        mock_row.commit.assert_called_once()

    def test_bigtable_commit_failure_tolerance(self):
        """Fallas en Bigtable commit no bloquean la ejecución del trading."""
        mock_table = MagicMock()
        mock_row = MagicMock()
        mock_row.commit.side_effect = Exception("Bigtable unavailable")
        mock_table.direct_row.return_value = mock_row

        registry = StateRegistry(redis_host="")
        registry._bt_table = mock_table

        # No debe lanzar excepción
        registry.record_trade("BT_002", "ETHUSDT", -10.0, False, time.time())
        # Trade debe quedar registrado en memoria
        recent = registry.get_recent_trades(limit=1)
        assert len(recent) == 1
        assert recent[0]["trade_id"] == "BT_002"


# ==============================================================================
# TIER 9: Concurrencia y Thread-Safety
# ==============================================================================
class TestThreadSafetyStateRegistry:
    """Valida que StateRegistry sea seguro ante concurrencia multi-hilo."""

    def test_concurrent_state_and_queue_operations(self):
        """Múltiples hilos concurrentes operan sobre StateRegistry sin condiciones de carrera."""
        registry = StateRegistry(redis_host="")
        registry.clear_all()

        n_threads = 8
        n_ops_per_thread = 50
        errors = []

        def worker_task(thread_id: int):
            try:
                for i in range(n_ops_per_thread):
                    match_id = f"T{thread_id}_M{i}"
                    registry.set_state(f"worker_{thread_id}", str(i))
                    registry.encolar_partido(match_id, {"stake": float(i + 1)})
                    _ = registry.obtener_partidos_pendientes()
                    registry.record_trade(f"TR_{thread_id}_{i}", "BTCUSDT", 1.0, True, time.time())
                    registry.cerrar_partido(match_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_task, args=(tid,)) for tid in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0, f"Errores en ejecución concurrente: {errors}"
        # Al finalizar, todos los partidos fueron cerrados
        assert len(registry.obtener_partidos_pendientes()) == 0
        assert len(registry.get_recent_trades(limit=1000)) == n_threads * n_ops_per_thread
