import sqlite3
import os
import threading
import logging
from typing import Dict, Any, List

logger = logging.getLogger("CONTINUITY.StateRegistry")

class StateRegistrySQLite:
    """
    Persistencia minimalista para el Orquestador HFT (SQLite WAL).
    Guarda y recupera balances, pnl y rachas para evitar sobreajuste
    y asegurar que al reiniciar no se pierda el progreso de capital.
    """
    def __init__(self, db_path: str = "continuity_state.db"):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute("PRAGMA journal_mode=WAL;")

            # Tabla de estado global
            conn.execute('''
                CREATE TABLE IF NOT EXISTS system_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # Tabla de historial de trades
            conn.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT,
                    pnl REAL,
                    is_win INTEGER,
                    timestamp REAL
                )
            ''')
            conn.commit()
            conn.close()

    def set_state(self, key: str, value: str) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT INTO system_state (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=?",
                (key, value, value)
            )
            conn.commit()
            conn.close()

    def get_state(self, key: str, default: str = "") -> str:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT value FROM system_state WHERE key = ?", (key,))
            row = cur.fetchone()
            conn.close()
            return row[0] if row else default

    def record_trade(self, trade_id: str, symbol: str, pnl: float, is_win: bool, timestamp: float) -> None:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "INSERT OR IGNORE INTO trades (trade_id, symbol, pnl, is_win, timestamp) VALUES (?, ?, ?, ?, ?)",
                (trade_id, symbol, pnl, int(is_win), timestamp)
            )
            conn.commit()
            conn.close()

    def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute("SELECT trade_id, symbol, pnl, is_win, timestamp FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,))
            rows = cur.fetchall()
            conn.close()

            return [
                {"trade_id": r[0], "symbol": r[1], "pnl": r[2], "is_win": bool(r[3]), "timestamp": r[4]}
                for r in rows
            ]
