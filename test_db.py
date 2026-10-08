import sqlite3
import time

db_path = "test_metrics.sqlite"
with sqlite3.connect(db_path) as conn:
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
    # Insert some data
    now = time.time()
    cursor.execute('INSERT INTO hft_metrics (timestamp, resultado, bankroll_momento) VALUES (?, ?, ?)', (now - 10, 'LOSS', 95))
    cursor.execute('INSERT INTO hft_metrics (timestamp, resultado, bankroll_momento) VALUES (?, ?, ?)', (now - 5, 'LOSS', 90))
    cursor.execute('INSERT INTO hft_metrics (timestamp, resultado, bankroll_momento) VALUES (?, ?, ?)', (now, 'LOSS', 80))
    conn.commit()

from continuitis.memoria_hft import HFTMemoryStore

class TestHFTMemoryStore(HFTMemoryStore):
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
            print(f"[HFT-Memoria] Error restaurando estado: {e}")

mem = TestHFTMemoryStore(db_path=db_path)
mem._restaurar_estado()
print("Racha:", mem.racha_perdidas)
print("Max bankroll:", mem.max_bankroll_diario)
