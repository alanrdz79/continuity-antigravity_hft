import asyncio
import sqlite3
import time
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)

class HFTMemoryStore:
    """
    Almacén de datos en memoria (RAM) de latencia ultra-baja para órdenes HFT.
    Utiliza SQLite de fondo asíncrono exclusivamente para métricas (ROI, Yield, Compound Interest).
    """
    def __init__(self, db_path="continuitis/db_metrics/metricas_hft.sqlite"):
        self.db_path = db_path
        # RAM principal para operaciones HFT
        self.ordenes_activas: Dict[str, dict] = {}
        self.historico_rapido: List[dict] = []
        
        # Buffer para evitar saturación de I/O en BD
        self._buffer_sql: List[dict] = []
        
        self.racha_perdidas: int = 0
        self.max_bankroll_diario: float = 0.0
        self.dia_actual: str = ""
        
        self._init_db()
        self._restaurar_estado()

    def _restaurar_estado(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                
                # Restaurar racha
                cursor.execute('''
                    SELECT resultado FROM hft_metrics 
                    ORDER BY timestamp DESC LIMIT 50
                ''')
                filas = cursor.fetchall()
                racha = 0
                for fila in filas:
                    res = fila[0].upper() if fila[0] else ""
                    if res in ["LOSS", "LOSE", "LOST", "PERDIDA", "PERDIDO"]:
                        racha += 1
                    elif res in ["WIN", "WON", "GANANCIA", "GANADA", "GANADO"]:
                        break
                self.racha_perdidas = racha

                # Restaurar max bankroll de hoy
                hoy_inicio = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
                cursor.execute('''
                    SELECT MAX(bankroll_momento) FROM hft_metrics 
                    WHERE timestamp >= ?
                ''', (hoy_inicio,))
                max_bd = cursor.fetchone()[0]
                if max_bd:
                    self.max_bankroll_diario = float(max_bd)
                    self.dia_actual = time.strftime("%Y-%m-%d")
        except Exception as e:
            logger.error(f"[HFT-Memoria] Error restaurando estado: {e}")

    def actualizar_estado_diario(self, bankroll_actual: float) -> float:
        hoy = time.strftime("%Y-%m-%d")
        if hoy != self.dia_actual:
            self.dia_actual = hoy
            self.max_bankroll_diario = bankroll_actual
        else:
            if bankroll_actual > self.max_bankroll_diario:
                self.max_bankroll_diario = bankroll_actual
        return self.max_bankroll_diario

    def _init_db(self):
        """Inicializa la base de datos de métricas analíticas."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS hft_metrics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp REAL,
                        evento TEXT,
                        deporte TEXT,
                        mercado TEXT,
                        stake REAL,
                        cuota_ofrecida REAL,
                        ev_neto REAL,
                        roi_esperado REAL,
                        resultado TEXT,
                        ganancia_real REAL,
                        bankroll_momento REAL
                    )
                ''')
                conn.commit()
        except Exception as e:
            logger.error(f"[HFT-Memoria] Error inicializando DB de métricas: {e}")

    def registrar_orden_activa(self, offer_id: str, data: dict):
        """Ocurre en RAM en microsegundos (< 1ms)."""
        data["timestamp_inicio"] = time.time()
        self.ordenes_activas[offer_id] = data

    def remover_orden_activa(self, offer_id: str):
        """Ocurre en RAM en microsegundos (< 1ms)."""
        if offer_id in self.ordenes_activas:
            del self.ordenes_activas[offer_id]

    def resolver_orden_hft(self, offer_id: str, resultado: str, ganancia_real: float, bankroll_actual: float):
        """Cierra la orden en RAM y encola su envío a SQL para métricas de aceleramiento."""
        resultado_upper = resultado.upper()
        if resultado_upper in ["LOSS", "LOSE", "LOST", "PERDIDA", "PERDIDO"]:
            self.racha_perdidas += 1
        elif resultado_upper in ["WIN", "WON", "GANANCIA", "GANADA", "GANADO"]:
            self.racha_perdidas = 0

        if offer_id in self.ordenes_activas:
            orden = self.ordenes_activas.pop(offer_id)
            metrica = {
                "timestamp": time.time(),
                "evento": orden.get("uid", "Desconocido"),
                "deporte": orden.get("deporte", "Desconocido"),
                "mercado": orden.get("mercado", "N/A"),
                "stake": orden.get("stake", 0.0),
                "cuota_ofrecida": orden.get("cuota_elegida", 1.0),
                "ev_neto": orden.get("ev_neto", 0.0),
                "roi_esperado": orden.get("ev_neto", 0.0) * orden.get("stake", 0.0),
                "resultado": resultado,
                "ganancia_real": ganancia_real,
                "bankroll_momento": bankroll_actual
            }
            self.historico_rapido.append(metrica)
            # Limitar histórico rápido en RAM a 10,000 registros para no explotar la memoria
            if len(self.historico_rapido) > 10000:
                self.historico_rapido.pop(0)

            # Encolar para SQLite
            self._buffer_sql.append(metrica)
            
            # Ejecutar flush asíncrono sin bloquear el loop HFT
            asyncio.create_task(self._escribir_sqlite_async())

    async def _escribir_sqlite_async(self):
        """Procesa el buffer y escribe en disco (Solo lectura métrica)."""
        if not self._buffer_sql:
            return
            
        # Tomar snapshot del buffer actual y limpiarlo
        lote = self._buffer_sql[:]
        self._buffer_sql.clear()

        # Simulamos I/O async delegando a un thread (o simple bloque async si es sqlite3 con bajo vol)
        # SQLite estándar bloquea, pero delegamos al thread pool para no congelar HFT
        await asyncio.to_thread(self._escribir_lote_sync, lote)

    def _escribir_lote_sync(self, lote: list):
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                for metrica in lote:
                    cursor.execute('''
                        INSERT INTO hft_metrics 
                        (timestamp, evento, deporte, mercado, stake, cuota_ofrecida, ev_neto, roi_esperado, resultado, ganancia_real, bankroll_momento)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        metrica["timestamp"], metrica["evento"], metrica["deporte"], 
                        metrica["mercado"], metrica["stake"], metrica["cuota_ofrecida"], 
                        metrica["ev_neto"], metrica["roi_esperado"], metrica["resultado"], 
                        metrica["ganancia_real"], metrica["bankroll_momento"]
                    ))
                conn.commit()
        except Exception as e:
            logger.error(f"[HFT-Memoria] Error escribiendo lote en SQLite: {e}")
