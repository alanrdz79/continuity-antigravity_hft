# -*- coding: utf-8 -*-
"""
==================================================================================
continuitis.tesoreria | CONTINUITY HFT Binance
==================================================================================
Módulo de Gestión de Tesorería, "Ordeño e Inyección", y Cosecha Autónoma.

Cumple con las especificaciones de:
- PROJECT.md (Milestone M2 & TreasuryProtocol)
- PLANnew.md (§3 Módulo 6: Tesorería, Ordeño e Inyección & §4 Implementación Core)

Reglas Operativas:
1. Progresión de Capital ("Ordeño e Inyección"): $10 -> $100 -> $1,000 USD.
2. Compuerta de Inyección $10 -> $100 USD (+100 USD event):
   Requiere validación estadística previa:
   - N >= 300 transacciones.
   - p-value < 0.05 (Z > 1.645).
   - EV / Rendimiento neto positivo > 0.
3. Fase de Aceleración (< $1,000 USD):
   Corte mensual de utilidades:
   - 40% a gastos operativos / administración.
   - 60% a reinversión compuesta (remanente en trading).
   - 0% a retiro.
4. Cosecha Autónoma (>= $1,000 USD):
   Corte mensual de utilidades:
   - 35% de beneficio mensual cosechado autónomamente y liquidado a MXN.
   - 65% restante dividido: 40% operación (26% total) y 60% reinversión (39% total).
"""

from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Union
import logging

from continuitis.auditor_metricas import TradeResult, AuditorMetricas

logger = logging.getLogger("CONTINUITY.Tesoreria")

# ==============================================================================
# CONSTANTES DE TESORERÍA
# ==============================================================================
CAPITAL_BASE_INICIAL: float = 10.0
UMBRAL_INYECCION_100: float = 100.0
MONTO_INYECCION_100: float = 100.0
UMBRAL_COSECHA_1000: float = 1000.0

PCT_COSECHA_AUTONOMA: float = 0.35      # 35% de ganancia mensual a cosecha MXN
PCT_GASTOS_OPERACION: float = 0.40      # 40% de utilidad a gastos operativos
PCT_REINVERSION_COMPUESTA: float = 0.60  # 60% de utilidad a reinversión compuesta
TIPO_CAMBIO_MXN_DEFAULT: float = 20.0   # Tipo de cambio referencial USD/MXN


# ==============================================================================
# CLASE PRINCIPAL: GestorTesoreria / TreasuryAndHarvestingManager
# ==============================================================================
class GestorTesoreria:
    """
    Gobierno de balance, inyección de capital condicionada y cosechas programadas.
    """

    def __init__(
        self,
        balance_inicial: float = CAPITAL_BASE_INICIAL,
        tipo_cambio_mxn: float = TIPO_CAMBIO_MXN_DEFAULT,
        auditor: Optional[AuditorMetricas] = None,
    ):
        self.balance_inicial = float(balance_inicial)
        self.balance = float(balance_inicial)
        self.tipo_cambio_mxn = float(tipo_cambio_mxn)

        # Banderas de hitos de capital
        self.hito_100_inyectado: bool = False
        self.meta_1000_activada: bool = False

        # Auditor analítico integrado o inyectado
        self.auditor: AuditorMetricas = auditor if auditor is not None else AuditorMetricas(capital_inicial=self.balance_inicial)

        # Historial de trades registrados en tesorería
        self.historial_trades: List[TradeResult] = []

        # Registro de eventos de inyección y cosecha
        self.log_eventos: List[Dict[str, Any]] = []

    # --------------------------------------------------------------------------
    # 1. REGISTRO DE TRADES
    # --------------------------------------------------------------------------
    def registrar_trade(self, trade: TradeResult) -> None:
        """
        Registra el resultado de una operación, actualizando el balance y el auditor.
        """
        self.historial_trades.append(trade)
        self.balance += trade.pnl
        self.auditor.registrar_trade(trade)

    # --------------------------------------------------------------------------
    # 2. VERIFICACIÓN DE HITOS E INYECCIÓN GATED
    # --------------------------------------------------------------------------
    def verificar_hitos(
        self,
        n_min: int = 300,
        p_umbral: float = 0.05,
        forzar_validacion: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Verifica el cruce de umbrales ($100 y $1,000 USD).

        Regla de Inyección $10 -> $100 USD (+100 USD event):
        - Solo se autoriza si balance >= 100.0 USD, no ha sido inyectado previamente,
          y se cumple la compuerta de validación empírica:
          N >= 300 trades, p-value < 0.05, EV / Yield neto > 0.
        """
        acciones: List[str] = []
        validacion_info: Optional[Dict[str, Any]] = None

        # Evaluación dinámica de umbral de $1,000 USD
        if self.balance >= UMBRAL_COSECHA_1000:
            if not self.meta_1000_activada:
                self.meta_1000_activada = True
                acciones.append("MODO_COSECHA_AUTONOMA_DISPONIBLE")
                self.log_eventos.append({
                    "evento": "MODO_COSECHA_AUTONOMA_DISPONIBLE",
                    "balance": self.balance,
                })
        else:
            self.meta_1000_activada = False

        # Evaluación de umbral de inyección ($100 USD)
        if self.balance >= UMBRAL_INYECCION_100 and not self.hito_100_inyectado:
            # Evaluar compuerta estadística
            if forzar_validacion is not None:
                aprobado = bool(forzar_validacion)
                validacion_info = {"aprobado": aprobado, "motivo": "FORZADO_MANUAL"}
            else:
                validacion_info = self.auditor.validar_compuerta(n_min=n_min, p_umbral=p_umbral)
                aprobado = validacion_info["aprobado"]

            if aprobado:
                self.balance += MONTO_INYECCION_100
                self.hito_100_inyectado = True
                acciones.append("INYECCION_100_USD_APLICADA")
                self.log_eventos.append({
                    "evento": "INYECCION_100_USD_APLICADA",
                    "monto_inyectado": MONTO_INYECCION_100,
                    "nuevo_balance": self.balance,
                    "validacion": validacion_info,
                })
                logger.info(f"¡Hito $100 superado y validado! Inyección de +{MONTO_INYECCION_100} USD aplicada. Balance: {self.balance:.2f} USD")
            else:
                acciones.append("INYECCION_BLOQUEADA_POR_VALIDACION")
                logger.warning(
                    f"Balance >= 100 USD alcanzado ({self.balance:.2f}), pero inyección bloqueada: "
                    f"{validacion_info.get('motivo', 'Validación pendiente')}"
                )

        return {
            "balance_actual": round(self.balance, 2),
            "hito_100_inyectado": self.hito_100_inyectado,
            "meta_1000_activada": self.meta_1000_activada,
            "acciones": acciones,
            "detalle_validacion": validacion_info,
        }

    def auditar_progreso(self) -> Dict[str, Any]:
        """Alias para compatibilidad con PLANnew.md §4."""
        return self.verificar_hitos()

    # --------------------------------------------------------------------------
    # 3. CORTE MENSUAL Y PROTOCOLO DE COSECHA / REINVERSIÓN
    # --------------------------------------------------------------------------
    def corte_mensual(
        self,
        ganancia_mensual: float,
        tipo_cambio_mxn: Optional[float] = None,
    ) -> Dict[str, float]:
        """
        Aplica las reglas de distribución de utilidades en cierres mensuales:

        Si balance >= 1,000 USD (Meta 1,000 activada):
          - Retiro Autónomo a MXN: 35% de ganancia_mensual.
          - Utilidad restante (65%):
            * 40% a Gastos Operativos (26% total).
            * 60% a Reinversión Compuesta (39% total).
          - Nuevo Balance: (Balance - ganancia_mensual) + Reinversión Compuesta.

        Si balance < 1,000 USD (Fase de Aceleración):
          - Retiro Autónomo: 0.0 USD.
          - 40% a Gastos Operativos.
          - 60% a Reinversión Compuesta.
          - Nuevo Balance: (Balance - ganancia_mensual) + Reinversión Compuesta.
        """
        fx = float(tipo_cambio_mxn) if tipo_cambio_mxn is not None else self.tipo_cambio_mxn

        if ganancia_mensual <= 0.0:
            return {
                "retiro_autonomo_35": 0.0,
                "retiro_autonomo_mxn": 0.0,
                "gastos_operacion_40": 0.0,
                "reinversion_compuesta_60": 0.0,
                "nuevo_balance": round(self.balance, 2),
            }

        if self.balance >= UMBRAL_COSECHA_1000:
            self.meta_1000_activada = True
            # Fase >= 1,000 USD: Cosecha del 35% a MXN
            retiro_35 = ganancia_mensual * PCT_COSECHA_AUTONOMA
            retiro_mxn = retiro_35 * fx
            utilidad_restante = ganancia_mensual - retiro_35
            operacion_40 = utilidad_restante * PCT_GASTOS_OPERACION
            reinversion_60 = utilidad_restante * PCT_REINVERSION_COMPUESTA

            # El balance retiene únicamente la porción de reinversión compuesta
            self.balance = (self.balance - ganancia_mensual) + reinversion_60

            resultado = {
                "retiro_autonomo_35": round(retiro_35, 2),
                "retiro_autonomo_mxn": round(retiro_mxn, 2),
                "gastos_operacion_40": round(operacion_40, 2),
                "reinversion_compuesta_60": round(reinversion_60, 2),
                "nuevo_balance": round(self.balance, 2),
            }
        else:
            self.meta_1000_activada = False
            # Fase de aceleración (< 1,000 USD): 40% gastos / 60% reinversión
            operacion_40 = ganancia_mensual * PCT_GASTOS_OPERACION
            reinversion_60 = ganancia_mensual * PCT_REINVERSION_COMPUESTA

            self.balance = (self.balance - ganancia_mensual) + reinversion_60

            resultado = {
                "retiro_autonomo_35": 0.0,
                "retiro_autonomo_mxn": 0.0,
                "gastos_operacion_40": round(operacion_40, 2),
                "reinversion_compuesta_60": round(reinversion_60, 2),
                "nuevo_balance": round(self.balance, 2),
            }

        self.log_eventos.append({
            "evento": "CORTE_MENSUAL",
            "ganancia_mensual": ganancia_mensual,
            "distribucion": resultado,
        })

        return resultado

    def procesar_cierre_mensual(self, ganancia_mensual: float) -> Dict[str, float]:
        """Alias para compatibilidad con PLANnew.md §4."""
        return self.corte_mensual(ganancia_mensual)


# Alias para coincidir con la nomenclatura histórica de PLANnew.md
TreasuryAndHarvestingManager = GestorTesoreria
