import time
from typing import Dict, List, Optional, Any
import logging

logger = logging.getLogger(__name__)

class HFTMemoryStore:
    """
    Almacén de datos en memoria (RAM) de latencia ultra-baja para órdenes HFT.
    
    Refactorizado para arquitectura Cloud GCP:
    - Estado en RAM de latencia ultra-baja (<1ms) para órdenes activas e histórico rápido.
    - Delegación de respaldo y métricas a StateRegistry (Cloud Memorystore Redis y Cloud Bigtable),
      eliminando cualquier dependencia local de SQLite (metricas_hft.sqlite).
    """
    def __init__(self, db_path: str = "continuitis/db_metrics/metricas_hft.sqlite", state_registry: Optional[Any] = None):
        # Mantenido por compatibilidad de firma (ignorado; no se interactúa con disco)
        self.db_path = db_path
        
        # RAM principal para operaciones HFT
        self.ordenes_activas: Dict[str, dict] = {}
        self.historico_rapido: List[dict] = []
        
        self.racha_perdidas: int = 0
        self.max_bankroll_diario: float = 0.0
        self.dia_actual: str = ""
        
        self.state_registry = state_registry
        self._init_registry()
        self._restaurar_estado()

    def _init_registry(self) -> None:
        if self.state_registry is None:
            try:
                from .state_registry import StateRegistry
                self.state_registry = StateRegistry()
            except Exception as e:
                logger.warning(f"[HFT-Memoria] No se pudo inicializar StateRegistry: {e}")
                self.state_registry = None

    def _init_db(self) -> None:
        """Método de compatibilidad con código heredado (No-op; SQLite eliminado)."""
        pass

    def _restaurar_estado(self) -> None:
        """Restaura racha y bankroll diario desde StateRegistry (Redis o mock en memoria)."""
        try:
            if self.state_registry is not None:
                racha_str = self.state_registry.get_state("racha_perdidas", "")
                if racha_str:
                    try:
                        self.racha_perdidas = int(racha_str)
                    except ValueError:
                        pass
                max_bk_str = self.state_registry.get_state("max_bankroll_diario", "")
                if max_bk_str:
                    try:
                        self.max_bankroll_diario = float(max_bk_str)
                        self.dia_actual = time.strftime("%Y-%m-%d")
                    except ValueError:
                        pass
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

        if self.state_registry is not None:
            try:
                self.state_registry.set_state("max_bankroll_diario", str(self.max_bankroll_diario))
            except Exception:
                pass

        return self.max_bankroll_diario

    def registrar_orden_activa(self, offer_id: str, data: dict) -> None:
        """Ocurre en RAM en microsegundos (< 1ms)."""
        data_copy = dict(data)
        data_copy["timestamp_inicio"] = time.time()
        self.ordenes_activas[offer_id] = data_copy

    def remover_orden_activa(self, offer_id: str) -> None:
        """Ocurre en RAM en microsegundos (< 1ms)."""
        if offer_id in self.ordenes_activas:
            del self.ordenes_activas[offer_id]

    def resolver_orden_hft(self, offer_id: str, resultado: str, ganancia_real: float, bankroll_actual: float) -> None:
        """Cierra la orden en RAM y delega su archivo histórico a StateRegistry (Redis/Bigtable)."""
        resultado_upper = resultado.upper()
        if resultado_upper in ["LOSS", "LOSE", "LOST", "PERDIDA", "PERDIDO"]:
            self.racha_perdidas += 1
        elif resultado_upper in ["WIN", "WON", "GANANCIA", "GANADA", "GANADO"]:
            self.racha_perdidas = 0

        if self.state_registry is not None:
            try:
                self.state_registry.set_state("racha_perdidas", str(self.racha_perdidas))
                self.state_registry.set_state("balance", str(bankroll_actual))
            except Exception:
                pass

        if offer_id in self.ordenes_activas:
            orden = self.ordenes_activas.pop(offer_id)
            metrica = {
                "timestamp": time.time(),
                "evento": orden.get("uid", orden.get("symbol", "Desconocido")),
                "deporte": orden.get("deporte", "Desconocido"),
                "mercado": orden.get("mercado", "N/A"),
                "stake": orden.get("stake", 0.0),
                "cuota_ofrecida": orden.get("cuota_elegida", orden.get("cuota", 1.0)),
                "ev_neto": orden.get("ev_neto", 0.0),
                "roi_esperado": orden.get("ev_neto", 0.0) * orden.get("stake", 0.0),
                "resultado": resultado,
                "ganancia_real": ganancia_real,
                "bankroll_momento": bankroll_actual
            }
            self.historico_rapido.append(metrica)
            if len(self.historico_rapido) > 10000:
                self.historico_rapido.pop(0)

            # Persistencia en StateRegistry (Redis recent_trades y Cloud Bigtable)
            if self.state_registry is not None:
                try:
                    is_win = (self.racha_perdidas == 0) and (ganancia_real > 0)
                    self.state_registry.record_trade(
                        trade_id=offer_id,
                        symbol=str(metrica["evento"]),
                        pnl=float(ganancia_real),
                        is_win=is_win,
                        timestamp=float(metrica["timestamp"]),
                        stake=float(metrica["stake"])
                    )
                except Exception as exc:
                    logger.warning(f"[HFT-Memoria] Error guardando trade en StateRegistry: {exc}")

    async def _escribir_sqlite_async(self) -> None:
        """Compatibilidad con código heredado (No-op asíncrono)."""
        pass

    def _escribir_lote_sync(self, lote: list) -> None:
        """Compatibilidad con código heredado (No-op síncrono)."""
        pass
