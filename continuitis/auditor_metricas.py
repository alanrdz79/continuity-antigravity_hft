# -*- coding: utf-8 -*-
"""
==================================================================================
continuitis.auditor_metricas | CONTINUITY HFT Binance
==================================================================================
Auditor Analítico Continuo de Métricas y Validación Estadística.

Responsabilidades:
1. Registro inmutable de operaciones (TradeResult).
2. Cálculo analítico continuo de métricas clave:
   - Win Rate (WR = Ganadas / N).
   - Capital Acumulado mediante fórmula de interés compuesto exacto:
     B_N = B_0 * prod(1 + f_i * R_i).
   - Retorno sobre la Inversión: ROI = sum(PnL) / B_0.
   - Rendimiento sobre volumen transaccionado: Yield = sum(PnL) / sum(S_i).
   - Total de operaciones (N).
3. Compuerta de Validación Estadística fuera de muestra (Regla de los 300):
   - Z = (WR - 0.50) / (0.50 / sqrt(N)).
   - p-value < 0.05 <=> Z > 1.645.
   - Validación requerida para autorizar la inyección de capital (+100 USD).
4. Persistencia opcional transaccional en SQLite (modo WAL).
"""

from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
import math
import sqlite3
import time
import logging

logger = logging.getLogger("CONTINUITY.AuditorMetricas")


# ==============================================================================
# INTERFACE CONTRACT (PROJECT.md)
# ==============================================================================
@dataclass
class TradeResult:
    """
    Resultado de una operación cerrada.
    """
    trade_id: str
    symbol: str
    stake: float
    pnl: float
    is_win: bool
    timestamp: float


# ==============================================================================
# CLASE PRINCIPAL: AuditorMetricas
# ==============================================================================
class AuditorMetricas:
    """
    Auditor de métricas continuas y compuerta estadística para CONTINUITY HFT.
    """

    def __init__(
        self,
        capital_inicial: float = 10.0,
        db_path: Optional[str] = None,
        auto_commit_db: bool = False,
    ):
        self.capital_inicial = float(capital_inicial)
        self.db_path = db_path
        self.auto_commit_db = auto_commit_db

        # Historial en RAM para cómputo analítico O(1) y O(N)
        self.historial: List[TradeResult] = []

        # Acumuladores analíticos en tiempo real
        self.total_trades: int = 0
        self.operaciones_ganadoras: int = 0
        self.operaciones_perdedoras: int = 0
        self.suma_pnl: float = 0.0
        self.suma_turnover: float = 0.0

        if self.db_path:
            self._init_sqlite()

    def _init_sqlite(self) -> None:
        """Inicializa la tabla de SQLite en modo WAL para persistencia segura."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL;")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS auditor_trades (
                        trade_id TEXT PRIMARY KEY,
                        symbol TEXT,
                        stake REAL,
                        pnl REAL,
                        is_win INTEGER,
                        timestamp REAL
                    )
                """)
                conn.commit()
        except Exception as e:
            logger.warning(f"No se pudo inicializar SQLite en {self.db_path}: {e}")

    # --------------------------------------------------------------------------
    # 1. REGISTRO DE TRADES
    # --------------------------------------------------------------------------
    def registrar_trade(self, trade: TradeResult) -> None:
        """
        Registra una operación cerrada y actualiza los acumuladores continuos.
        """
        self.historial.append(trade)
        self.total_trades += 1

        if trade.is_win:
            self.operaciones_ganadoras += 1
        else:
            self.operaciones_perdedoras += 1

        self.suma_pnl += trade.pnl
        self.suma_turnover += trade.stake

        if self.db_path and self.auto_commit_db:
            self._guardar_trade_sqlite(trade)

    def _guardar_trade_sqlite(self, trade: TradeResult) -> None:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO auditor_trades 
                    (trade_id, symbol, stake, pnl, is_win, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    trade.trade_id,
                    trade.symbol,
                    trade.stake,
                    trade.pnl,
                    1 if trade.is_win else 0,
                    trade.timestamp
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"Error escribiendo trade en SQLite: {e}")

    # --------------------------------------------------------------------------
    # 2. CÁLCULO ANALÍTICO DE MÉTRICAS CONTINUAS
    # --------------------------------------------------------------------------
    def calcular_win_rate(self) -> float:
        """
        Win Rate (WR) = Operaciones Ganadoras / Total Trades (N).
        """
        if self.total_trades == 0:
            return 0.0
        return float(self.operaciones_ganadoras / self.total_trades)

    def calcular_capital_acumulado(self) -> float:
        """
        Calcula el Capital Acumulado según la fórmula exacta de PLANnew.md y DISPATCH:
          B_N = B_0 * prod_{i=1}^N (1 + f_i * R_i)

        Donde para cada operación i:
          B_{i-1} : capital antes de la operación i
          f_i     : fracción de capital apostada = S_i / B_{i-1}
          R_i     : retorno porcentual sobre el stake = PnL_i / S_i
          1 + f_i * R_i = 1 + (PnL_i / B_{i-1}) = (B_{i-1} + PnL_i) / B_{i-1}

        Multiplicando secuencialmente el producto acumulado:
          prod = prod * (1 + f_i * R_i)
          B_N = B_0 * prod
        """
        if not self.historial:
            return float(self.capital_inicial)

        b_actual = self.capital_inicial
        producto_compuesto = 1.0

        for trade in self.historial:
            if b_actual <= 0.0:
                # Quiebra o capital agotado
                b_actual = 0.0
                producto_compuesto = 0.0
                break

            stake = trade.stake
            pnl = trade.pnl

            if stake > 0.0:
                f_i = stake / b_actual
                r_i = pnl / stake
                factor_i = 1.0 + (f_i * r_i)
            else:
                # Si stake es 0 pero hubo PnL directo
                factor_i = 1.0 + (pnl / b_actual)

            producto_compuesto *= factor_i
            b_actual = b_actual * factor_i

        b_n = self.capital_inicial * producto_compuesto
        return float(b_n)

    def calcular_roi(self) -> float:
        """
        ROI = sum(PnL) / B_0.
        Retorno neto acumulado con respecto al capital inicial.
        """
        if self.capital_inicial <= 0.0:
            return 0.0
        return float(self.suma_pnl / self.capital_inicial)

    def calcular_yield(self) -> float:
        """
        Yield = sum(PnL) / sum(S_i) (Turnover total).
        Rentabilidad neta sobre el volumen total transaccionado.
        """
        if self.suma_turnover <= 0.0:
            return 0.0
        return float(self.suma_pnl / self.suma_turnover)

    # --------------------------------------------------------------------------
    # 3. COMPUERTA DE VALIDACIÓN ESTADÍSTICA (Z-SCORE & P-VALUE)
    # --------------------------------------------------------------------------
    def calcular_estadistica_z(self) -> Tuple[float, float]:
        """
        Calcula el Z-Score y el p-value para probar la hipótesis nula H0: WR <= 0.50
        (resultado aleatorio sin edge).

        Fórmula:
          Z = (WR - 0.50) / (0.50 / sqrt(N))
            = 2 * sqrt(N) * (WR - 0.50)

        p-value (unilateral hacia la derecha):
          p = 1 - Phi(Z) = 0.5 * erfc(Z / sqrt(2))

        Retorna:
          (z_score, p_value)
        """
        n = self.total_trades
        if n == 0:
            return 0.0, 1.0

        wr = self.calcular_win_rate()
        error_estandar = 0.50 / math.sqrt(n)
        if error_estandar == 0.0:
            return 0.0, 1.0

        z = (wr - 0.50) / error_estandar

        # Función de distribución acumulativa normal complementaria:
        # p = 1 - Phi(z) = 0.5 * erfc(z / sqrt(2))
        p_value = 0.5 * math.erfc(z / math.sqrt(2.0))

        return float(z), float(p_value)

    def validar_compuerta(
        self,
        n_min: int = 300,
        p_umbral: float = 0.05,
        ev_minimo: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Evalúa el cumplimiento de la compuerta de validación fuera de muestra:
        1. N >= 300 operaciones.
        2. p-value < 0.05 <=> Z > 1.645 (significancia estadística).
        3. EV / Yield neto > 0 (rendimiento positivo).

        Retorna:
          dict con {
            "aprobado": bool,
            "n": int,
            "n_min": int,
            "win_rate": float,
            "z_score": float,
            "p_value": float,
            "yield": float,
            "roi": float,
            "criterios": {
                "n_suficiente": bool,
                "p_value_valido": bool,
                "rendimiento_positivo": bool
            },
            "motivo": str
          }
        """
        n = self.total_trades
        wr = self.calcular_win_rate()
        z_score, p_value = self.calcular_estadistica_z()
        yield_neto = self.calcular_yield()

        criterio_n = n >= n_min
        # p < 0.05 equivale matemáticamente a Z > 1.64485...
        criterio_p = (p_value < p_umbral) and (z_score > 1.644853)
        criterio_ev = (yield_neto > ev_minimo) and (self.suma_pnl > 0.0)

        aprobado = criterio_n and criterio_p and criterio_ev

        motivos = []
        if not criterio_n:
            motivos.append(f"Muestra insuficiente: N={n} < {n_min}")
        if not criterio_p:
            motivos.append(f"Significancia estadística insuficiente: p={p_value:.4f} >= {p_umbral} (Z={z_score:.3f} <= 1.645)")
        if not criterio_ev:
            motivos.append(f"Rendimiento neto no positivo: Yield={yield_neto:.4f}, PnL={self.suma_pnl:.2f}")

        motivo_str = "VALIDACION_APROBADA" if aprobado else " | ".join(motivos)

        return {
            "aprobado": aprobado,
            "n": n,
            "n_min": n_min,
            "win_rate": round(wr, 4),
            "z_score": round(z_score, 4),
            "p_value": round(p_value, 6),
            "yield": round(yield_neto, 6),
            "roi": round(self.calcular_roi(), 6),
            "criterios": {
                "n_suficiente": criterio_n,
                "p_value_valido": criterio_p,
                "rendimiento_positivo": criterio_ev,
            },
            "motivo": motivo_str,
        }

    # --------------------------------------------------------------------------
    # 4. INTERFAZ FORMAL DE PROTOCOLO (PROJECT.md MetricsAuditorProtocol)
    # --------------------------------------------------------------------------
    def obtener_metricas(self) -> Dict[str, Any]:
        """
        Retorna el diccionario de métricas consolidado requerido por PROJECT.md:
        {"win_rate": float, "capital_acumulado": float, "roi": float, "yield": float, "total_trades": int}
        """
        wr = self.calcular_win_rate()
        cap_acumulado = self.calcular_capital_acumulado()
        roi = self.calcular_roi()
        rendimiento_yield = self.calcular_yield()
        z, p = self.calcular_estadistica_z()

        return {
            "win_rate": round(wr, 4),
            "capital_acumulado": round(cap_acumulado, 2),
            "roi": round(roi, 4),
            "yield": round(rendimiento_yield, 4),
            "total_trades": self.total_trades,
            # Métricas extendidas de auditoría continua
            "operaciones_ganadoras": self.operaciones_ganadoras,
            "operaciones_perdedoras": self.operaciones_perdedoras,
            "pnl_total": round(self.suma_pnl, 2),
            "turnover_total": round(self.suma_turnover, 2),
            "z_score": round(z, 4),
            "p_value": round(p, 6),
        }

    def reset(self) -> None:
        """Reinicia el historial y los acumuladores a estado base."""
        self.historial.clear()
        self.total_trades = 0
        self.operaciones_ganadoras = 0
        self.operaciones_perdedoras = 0
        self.suma_pnl = 0.0
        self.suma_turnover = 0.0
