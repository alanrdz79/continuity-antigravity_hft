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

        # Bóvedas de custodia contable de cosecha autónoma
        self.capital_aislado_cosecha_usd: float = 0.0
        self.capital_aislado_cosecha_mxn: float = 0.0
        self.fondo_gastos_operacion_usd: float = 0.0
        self.fondo_reinversion_total_usd: float = 0.0
        self.capital_base_post_cosecha: float = float(balance_inicial)
        self.cosechas_ejecutadas: List[Dict[str, Any]] = []
        self.auto_cosechar_en_hitos: bool = False

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
        auto_cosechar: Optional[bool] = None,
    ) -> Dict[str, Any]:
        """
        Verifica el cruce de umbrales ($100 y $1,000 USD).

        Regla de Inyección $10 -> $100 USD (+100 USD event):
        - Solo se autoriza si balance >= 100.0 USD, no ha sido inyectado previamente,
          y se cumple la compuerta de validación empírica:
          N >= 300 trades, p-value < 0.05 (Z > 1.645), EV / Yield neto > 0.

        Regla de Cosecha Autónoma (>= $1,000 USD):
        - Si auto_cosechar es True, ejecuta autónomamente el protocolo de cosecha del 35% a MXN.
        """
        acciones: List[str] = []
        validacion_info: Optional[Dict[str, Any]] = None
        detalle_cosecha: Optional[Dict[str, Any]] = None

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
                acciones.append("MODO_COSECHA_AUTONOMA_DISPONIBLE")

            debe_cosechar = self.auto_cosechar_en_hitos if auto_cosechar is None else bool(auto_cosechar)
            if debe_cosechar:
                detalle_cosecha = self.ejecutar_cosecha_autonoma()
                if detalle_cosecha.get("cosecha_ejecutada"):
                    acciones.append("COSECHA_AUTONOMA_EJECUTADA")
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
            "balance_actual": round(self.balance, 4),
            "hito_100_inyectado": self.hito_100_inyectado,
            "meta_1000_activada": self.meta_1000_activada,
            "acciones": acciones,
            "detalle_validacion": validacion_info,
            "detalle_cosecha": detalle_cosecha,
            "capital_aislado_cosecha_usd": round(self.capital_aislado_cosecha_usd, 4),
            "capital_aislado_cosecha_mxn": round(self.capital_aislado_cosecha_mxn, 4),
        }

    def auditar_progreso(self) -> Dict[str, Any]:
        """Alias para compatibilidad con PLANnew.md §4."""
        return self.verificar_hitos()

    # --------------------------------------------------------------------------
    # 3. PROTOCOLO DE COSECHA AUTÓNOMA (>= $1,000 USD)
    # --------------------------------------------------------------------------
    def ejecutar_cosecha_autonoma(
        self,
        ganancia_neta: Optional[float] = None,
        tipo_cambio_mxn: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Ejecuta el protocolo autónomo de Harvesting al cruzar >= $1,000 USD (DISPATCH.md §5 & PROJECT.md):
        - Cuando balance >= 1,000 USD, calcula ganancia neta (balance - capital_base_post_cosecha o valor provisto).
        - Aisla exactamente 35% de ganancia neta a MXN (capital_aislado_cosecha_usd y capital_aislado_cosecha_mxn).
        - Enruta 40% del remanente (26% total) a gastos de operación (fondo_gastos_operacion_usd).
        - Retiene 60% del remanente (39% total) en reinversión compuesta (fondo_reinversion_total_usd).
        - Actualiza el balance operativo: (balance - ganancia_neta) + reinversion_60.
        - Garantiza precisión estricta a 4 decimales.
        """
        fx = float(tipo_cambio_mxn) if tipo_cambio_mxn is not None else self.tipo_cambio_mxn

        if ganancia_neta is None:
            base = getattr(self, "capital_base_post_cosecha", self.balance_inicial)
            ganancia_neta = max(0.0, self.balance - base)

        if ganancia_neta <= 0.0 or self.balance < UMBRAL_COSECHA_1000:
            return {
                "cosecha_ejecutada": False,
                "motivo": "Condiciones no cumplidas (balance < 1000 o sin ganancia neta)",
                "balance_actual": round(self.balance, 4),
                "capital_aislado_cosecha_usd": round(self.capital_aislado_cosecha_usd, 4),
                "capital_aislado_cosecha_mxn": round(self.capital_aislado_cosecha_mxn, 4),
                "fondo_gastos_operacion_usd": round(self.fondo_gastos_operacion_usd, 4),
                "fondo_reinversion_total_usd": round(self.fondo_reinversion_total_usd, 4),
            }

        self.meta_1000_activada = True
        retiro_35 = round(ganancia_neta * PCT_COSECHA_AUTONOMA, 4)
        retiro_mxn = round(retiro_35 * fx, 4)
        utilidad_restante = round(ganancia_neta - retiro_35, 4)
        operacion_40 = round(utilidad_restante * PCT_GASTOS_OPERACION, 4)
        reinversion_60 = round(utilidad_restante * PCT_REINVERSION_COMPUESTA, 4)

        # Aislamiento formal de fondos en bóvedas de custodia contable
        self.capital_aislado_cosecha_usd = round(self.capital_aislado_cosecha_usd + retiro_35, 4)
        self.capital_aislado_cosecha_mxn = round(self.capital_aislado_cosecha_mxn + retiro_mxn, 4)
        self.fondo_gastos_operacion_usd = round(self.fondo_gastos_operacion_usd + operacion_40, 4)
        self.fondo_reinversion_total_usd = round(self.fondo_reinversion_total_usd + reinversion_60, 4)

        # Actualización del balance de trading
        self.balance = round((self.balance - ganancia_neta) + reinversion_60, 4)
        self.capital_base_post_cosecha = self.balance

        resultado = {
            "cosecha_ejecutada": True,
            "ganancia_neta": round(ganancia_neta, 4),
            "retiro_autonomo_35_usd": retiro_35,
            "retiro_autonomo_mxn": retiro_mxn,
            "gastos_operacion_40_usd": operacion_40,
            "reinversion_compuesta_60_usd": reinversion_60,
            "nuevo_balance_operativo": round(self.balance, 4),
            "total_aislado_historico_usd": round(self.capital_aislado_cosecha_usd, 4),
            "total_aislado_historico_mxn": round(self.capital_aislado_cosecha_mxn, 4),
        }

        self.cosechas_ejecutadas.append(resultado)
        self.log_eventos.append({"evento": "COSECHA_AUTONOMA_EJECUTADA", "detalle": resultado})
        return resultado

    # --------------------------------------------------------------------------
    # 4. CORTE MENSUAL Y PROTOCOLO DE DISTRIBUCIÓN
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
                "nuevo_balance": round(self.balance, 4),
            }

        if self.balance >= UMBRAL_COSECHA_1000 or self.meta_1000_activada:
            self.meta_1000_activada = True
            # Fase >= 1,000 USD: Cosecha del 35% a MXN
            retiro_35 = round(ganancia_mensual * PCT_COSECHA_AUTONOMA, 4)
            retiro_mxn = round(retiro_35 * fx, 4)
            utilidad_restante = round(ganancia_mensual - retiro_35, 4)
            operacion_40 = round(utilidad_restante * PCT_GASTOS_OPERACION, 4)
            reinversion_60 = round(utilidad_restante * PCT_REINVERSION_COMPUESTA, 4)

            # Acumular en bóvedas contables
            self.capital_aislado_cosecha_usd = round(self.capital_aislado_cosecha_usd + retiro_35, 4)
            self.capital_aislado_cosecha_mxn = round(self.capital_aislado_cosecha_mxn + retiro_mxn, 4)
            self.fondo_gastos_operacion_usd = round(self.fondo_gastos_operacion_usd + operacion_40, 4)
            self.fondo_reinversion_total_usd = round(self.fondo_reinversion_total_usd + reinversion_60, 4)

            # El balance retiene únicamente la porción de reinversión compuesta
            self.balance = round((self.balance - ganancia_mensual) + reinversion_60, 4)
            self.capital_base_post_cosecha = self.balance

            resultado = {
                "retiro_autonomo_35": round(retiro_35, 4),
                "retiro_autonomo_mxn": round(retiro_mxn, 4),
                "gastos_operacion_40": round(operacion_40, 4),
                "reinversion_compuesta_60": round(reinversion_60, 4),
                "nuevo_balance": round(self.balance, 4),
                "total_aislado_historico_usd": round(self.capital_aislado_cosecha_usd, 4),
                "total_aislado_historico_mxn": round(self.capital_aislado_cosecha_mxn, 4),
            }
        else:
            self.meta_1000_activada = False
            # Fase de aceleración (< 1,000 USD): 40% gastos / 60% reinversión
            operacion_40 = round(ganancia_mensual * PCT_GASTOS_OPERACION, 4)
            reinversion_60 = round(ganancia_mensual * PCT_REINVERSION_COMPUESTA, 4)

            self.fondo_gastos_operacion_usd = round(self.fondo_gastos_operacion_usd + operacion_40, 4)
            self.fondo_reinversion_total_usd = round(self.fondo_reinversion_total_usd + reinversion_60, 4)

            self.balance = round((self.balance - ganancia_mensual) + reinversion_60, 4)
            self.capital_base_post_cosecha = self.balance

            resultado = {
                "retiro_autonomo_35": 0.0,
                "retiro_autonomo_mxn": 0.0,
                "gastos_operacion_40": round(operacion_40, 4),
                "reinversion_compuesta_60": round(reinversion_60, 4),
                "nuevo_balance": round(self.balance, 4),
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
