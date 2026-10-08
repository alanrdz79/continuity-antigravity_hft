# -*- coding: utf-8 -*-
"""
==================================================================================
continuitis.riesgo_binance | CONTINUITY HFT Binance
==================================================================================
Módulo de Gestión de Riesgo, Cálculo de EV Neto, Dimensionamiento Real de Posición
y Control de Liquidez (Regla de Oro 3).

Cumple con las especificaciones de:
- PROJECT.md (Milestone M2 & Interfaces)
- PLANnew.md (§3 Módulo 3: EscudoFinanciero & RiskEngine)
- Directivas de Negocio: Regla de Oro 3 (Top 3 BIDs liquidity ceiling)
"""

from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, Union, List
import math
import logging

logger = logging.getLogger("CONTINUITY.RiesgoBinance")

# ==============================================================================
# CONSTANTES DE RIESGO Y COMISIONES BINANCE SPOT
# ==============================================================================
BINANCE_SPOT_BASE_FEE: float = 0.0010       # 0.10% comisión base regular Maker/Taker
BNB_DISCOUNT_FACTOR: float = 0.75           # 25% descuento pagando con BNB (1 - 0.25 = 0.75)
BINANCE_BNB_FEE_RATE: float = 0.00075       # 0.075% comisión efectiva neta con BNB

DEFAULT_PCT_RIESGO_FIJO: float = 0.015      # 1.5% de riesgo fijo base sobre bankroll
DEFAULT_EV_MINIMO: float = 0.015            # EV mínimo requerido = 1.5% neto
DEFAULT_MAX_CLUSTER_EXP: float = 0.15       # 15% techo de exposición simultánea por clúster
DEFAULT_ATENUACION_RACHA: float = 0.85      # Factor de atenuación por pérdida consecutiva
MIN_PCT_STOP_LOSS: float = 0.01             # 1.0% stop loss mínimo para evitar división por cero


# ==============================================================================
# INTERFACE CONTRACTS (PROJECT.md)
# ==============================================================================
@dataclass(frozen=True)
class OrderProposal:
    """
    Propuesta de orden generada por una estrategia (HFT o Swing).
    """
    symbol: str
    side: str
    target_price: float
    stop_price: float
    estimated_prob: float
    payout_decimal: float
    strategy_id: str


@dataclass(frozen=True)
class RiskApprovedOrder:
    """
    Decisión de aprobación/rechazo emitida por el motor de riesgo.
    """
    symbol: str
    side: str
    price: float
    quantity: float
    ev_net: float
    approved: bool
    rejection_reason: Optional[str] = None


# ==============================================================================
# CLASE PRINCIPAL: EscudoFinancieroBinance
# ==============================================================================
class EscudoFinancieroBinance:
    """
    Motor de Riesgo y Dimensionamiento de Posición para Binance Spot Prediction Markets.

    Responsabilidades:
    1. Cálculo de Cuota Neta y Valor Esperado (EV) descontando comisiones con BNB:
       EV = (P_estimada * Cuota_neta) - 1.0 >= 0.015.
    2. Dimensionamiento Real de Posición:
       S_nominal = (B * pct_riesgo_fijo * factor_racha) / max(pct_stop_loss, 0.01).
    3. Atenuación por Racha Perdedora:
       factor_racha = 0.85^streak, reseteado a 1.0 en victoria.
    4. Techo de Exposición por Clúster:
       Exposición simultánea total <= 15% del bankroll.
    5. Regla de Oro 3:
       Dimensionamiento acotado por liquidez disponible en los primeros 3 niveles de BID:
       S <= sum(V_Bid^(1..3)) para garantizar liquidez de salida inmediata a mercado.
    """

    def __init__(
        self,
        pct_riesgo_fijo: float = DEFAULT_PCT_RIESGO_FIJO,
        ev_minimo: float = DEFAULT_EV_MINIMO,
        max_cluster_exp: float = DEFAULT_MAX_CLUSTER_EXP,
        factor_atenuacion_racha: float = DEFAULT_ATENUACION_RACHA,
        tasa_comision_base: float = BINANCE_SPOT_BASE_FEE,
        descuento_bnb_activo: bool = True,
    ):
        self.pct_riesgo_fijo = float(pct_riesgo_fijo)
        self.ev_minimo = float(ev_minimo)
        self.max_cluster_exp = float(max_cluster_exp)
        self.factor_atenuacion_racha = float(factor_atenuacion_racha)
        self.tasa_comision_base = float(tasa_comision_base)
        self.descuento_bnb_activo = bool(descuento_bnb_activo)

        # Estado dinámico de racha
        self.consecutive_losses: int = 0

    @property
    def factor_racha(self) -> float:
        """
        Retorna el factor de atenuación actual: 0.85^consecutive_losses.
        """
        return float(self.factor_atenuacion_racha ** self.consecutive_losses)

    @property
    def tasa_comision_efectiva(self) -> float:
        """
        Retorna la comisión efectiva neta de Binance:
        Si descuento BNB está activo: base * 0.75 (0.075%).
        Si está inactivo: base (0.10%).
        """
        if self.descuento_bnb_activo:
            return self.tasa_comision_base * BNB_DISCOUNT_FACTOR
        return self.tasa_comision_base

    # --------------------------------------------------------------------------
    # 1. CÁLCULO DE CUOTA NETA Y EV
    # --------------------------------------------------------------------------
    def calcular_cuota_neta(
        self,
        cuota_bruta: float,
        tasa_comision: Optional[float] = None,
    ) -> float:
        """
        Calcula la cuota decimal efectiva descontando comisiones de Binance.

        Estructura de comisión:
          cuota_neta = 1.0 + (cuota_bruta - 1.0) * (1.0 - tasa_comision)

        Si cuota_bruta <= 1.0, retorna la cuota sin alteración.
        """
        if cuota_bruta <= 1.0:
            return float(cuota_bruta)

        fee = self.tasa_comision_efectiva if tasa_comision is None else float(tasa_comision)
        cuota_neta = 1.0 + (cuota_bruta - 1.0) * (1.0 - fee)
        return float(cuota_neta)

    def calcular_ev(
        self,
        p_estimada: float,
        cuota_neta: float,
    ) -> float:
        """
        Calcula el Valor Esperado (EV) neto:
          EV = (P_estimada * Cuota_neta) - 1.0
        """
        return float((p_estimada * cuota_neta) - 1.0)

    # --------------------------------------------------------------------------
    # 2. EVALUACIÓN Y DIMENSIONAMIENTO DIRECTO (COMPATIBLE CON PLANnew)
    # --------------------------------------------------------------------------
    def calcular_posicion(
        self,
        balance_actual: float,
        p_estimada: float,
        cuota: float,
        pct_stop_loss: float,
        operaciones_activas: int = 0,
        exposicion_cluster_actual: float = 0.0,
        top_3_bid_volumen: Optional[float] = None,
        precio_contrato: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Calcula el stake y evalúa la viabilidad de la operación según todas las reglas.

        Parámetros:
          balance_actual: Capital actual de la cuenta (B).
          p_estimada: Probabilidad estimada por el modelo / estrategia.
          cuota: Cuota decimal bruta o de pago de la predicción.
          pct_stop_loss: Porcentaje de distancia al stop loss (ej. 0.05 para 5%).
          operaciones_activas: Cantidad de operaciones activas en el clúster.
          exposicion_cluster_actual: Capital monetario actualmente comprometido en el clúster.
          top_3_bid_volumen: Volumen total disponible en los primeros 3 niveles de BID (Regla de Oro 3).

        Retorna:
          dict con {
             "operar": bool,
             "motivo": str,
             "ev": float,
             "cuota_neta": float,
             "stake": float,
             "riesgo_monetario": float,
             "factor_racha": float,
             "consecutive_losses": int,
             "clamped_by_cluster": bool,
             "clamped_by_liquidity": bool
          }
        """
        balance = max(0.0, float(balance_actual))
        if balance <= 0.0:
            return {
                "operar": False,
                "motivo": "Balance insuficiente (<= 0)",
                "ev": 0.0,
                "cuota_neta": 0.0,
                "stake": 0.0,
                "riesgo_monetario": 0.0,
                "factor_racha": self.factor_racha,
                "consecutive_losses": self.consecutive_losses,
                "clamped_by_cluster": False,
                "clamped_by_liquidity": False,
            }

        # 1. Validación de Valor Esperado (EV) con descuento de comisiones BNB
        cuota_neta = self.calcular_cuota_neta(cuota)
        ev = self.calcular_ev(p_estimada, cuota_neta)
        if ev < self.ev_minimo:
            return {
                "operar": False,
                "motivo": f"EV insuficiente ({ev:.4f} < {self.ev_minimo:.4f})",
                "ev": round(ev, 4),
                "cuota_neta": round(cuota_neta, 4),
                "stake": 0.0,
                "riesgo_monetario": 0.0,
                "factor_racha": round(self.factor_racha, 4),
                "consecutive_losses": self.consecutive_losses,
                "clamped_by_cluster": False,
                "clamped_by_liquidity": False,
            }

        # 2. Factor de atenuación por racha negativa (0.85^n)
        factor_racha = self.factor_racha

        # 3. Tamaño de posición real (Position Sizing) en función del Stop Loss
        # S_nominal = (B * pct_riesgo_fijo * factor_racha) / max(pct_stop_loss, 0.01)
        stop_loss_efectivo = max(float(pct_stop_loss), MIN_PCT_STOP_LOSS)
        riesgo_objetivo = balance * self.pct_riesgo_fijo * factor_racha
        posicion_nominal = riesgo_objetivo / stop_loss_efectivo

        # 4. Modulación por techo de clúster (<= 15% del bankroll)
        max_cluster_capital = balance * self.max_cluster_exp
        clamped_cluster = False

        if exposicion_cluster_actual > 0.0:
            espacio_disponible = max(0.0, max_cluster_capital - exposicion_cluster_actual)
            if posicion_nominal > espacio_disponible:
                posicion_nominal = espacio_disponible
                clamped_cluster = True
        elif operaciones_activas > 0:
            exposicion_futura = ((operaciones_activas + 1) * posicion_nominal) / balance
            if exposicion_futura > self.max_cluster_exp:
                compresion = (self.max_cluster_exp * balance) / ((operaciones_activas + 1) * posicion_nominal)
                posicion_nominal *= compresion
                clamped_cluster = True
        else:
            if posicion_nominal > max_cluster_capital:
                posicion_nominal = max_cluster_capital
                clamped_cluster = True

        if posicion_nominal <= 0.0:
            return {
                "operar": False,
                "motivo": "Exposición máxima de clúster (15%) alcanzada",
                "ev": round(ev, 4),
                "cuota_neta": round(cuota_neta, 4),
                "stake": 0.0,
                "riesgo_monetario": 0.0,
                "factor_racha": round(factor_racha, 4),
                "consecutive_losses": self.consecutive_losses,
                "clamped_by_cluster": True,
                "clamped_by_liquidity": False,
            }

        # 5. Regla de Oro 3: Acotación dinámica por liquidez en Top 3 BIDs
        clamped_liquidity = False
        if top_3_bid_volumen is not None:
            v_bid_top3 = float(top_3_bid_volumen)
            if precio_contrato is not None and precio_contrato > 0.0:
                v_bid_top3 = v_bid_top3 * precio_contrato
            if v_bid_top3 <= 0.0:
                return {
                    "operar": False,
                    "motivo": "Regla de Oro 3 violada: Sin liquidez disponible en top 3 BIDs para escape",
                    "ev": round(ev, 4),
                    "cuota_neta": round(cuota_neta, 4),
                    "stake": 0.0,
                    "riesgo_monetario": 0.0,
                    "factor_racha": round(factor_racha, 4),
                    "consecutive_losses": self.consecutive_losses,
                    "clamped_by_cluster": clamped_cluster,
                    "clamped_by_liquidity": True,
                }
            if posicion_nominal > v_bid_top3:
                posicion_nominal = v_bid_top3
                clamped_liquidity = True

        riesgo_real = posicion_nominal * stop_loss_efectivo

        return {
            "operar": True,
            "motivo": "AUTORIZADO",
            "ev": round(ev, 4),
            "cuota_neta": round(cuota_neta, 4),
            "stake": round(posicion_nominal, 2),
            "riesgo_monetario": round(riesgo_real, 2),
            "factor_racha": round(factor_racha, 4),
            "consecutive_losses": self.consecutive_losses,
            "clamped_by_cluster": clamped_cluster,
            "clamped_by_liquidity": clamped_liquidity,
        }

    # --------------------------------------------------------------------------
    # 3. INTERFAZ TIPADA DE ORDEN (PROJECT.md Interface Contract)
    # --------------------------------------------------------------------------
    def evaluar_propuesta(
        self,
        proposal: OrderProposal,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster_actual: float = 0.0,
        top_3_bids: Optional[Union[float, List[Tuple[float, float]], Tuple[Tuple[float, float], ...]]] = None,
    ) -> RiskApprovedOrder:
        """
        Evalúa una OrderProposal y devuelve RiskApprovedOrder según contratos de PROJECT.md.

        top_3_bids puede ser:
          - float: volumen total ya sumado en los top 3 niveles.
          - lista/tupla de (precio, volumen): suma el volumen o valor nominal de los primeros 3 niveles.
        """
        # Calcular cuota bruta a partir de payout_decimal o target_price
        cuota_bruta = proposal.payout_decimal
        if cuota_bruta <= 1.0 and proposal.target_price > 0.0:
            cuota_bruta = 1.0 / proposal.target_price

        # Calcular porcentaje de stop loss a partir de target_price y stop_price
        pct_stop_loss = 0.05
        if proposal.target_price > 0.0 and proposal.stop_price > 0.0:
            pct_stop_loss = abs(proposal.target_price - proposal.stop_price) / proposal.target_price
        pct_stop_loss = max(pct_stop_loss, MIN_PCT_STOP_LOSS)

        # Parsear top 3 bids: la liquidez disponible V_escape está expresada en contratos/shares
        v_escape_shares = None
        if top_3_bids is not None:
            if isinstance(top_3_bids, (int, float)):
                v_escape_shares = float(top_3_bids)
            elif isinstance(top_3_bids, (list, tuple)):
                suma_shares = 0.0
                for nivel in top_3_bids[:3]:
                    if isinstance(nivel, (tuple, list)) and len(nivel) >= 2:
                        v = float(nivel[1])
                        if v > 0.0:
                            suma_shares += v
                    elif isinstance(nivel, (int, float)):
                        if float(nivel) > 0.0:
                            suma_shares += float(nivel)
                v_escape_shares = suma_shares

        # Capacidad de escape en USDT a partir del precio del contrato: S_escape = V_escape * P
        contract_price = proposal.target_price
        top_3_vol_usdt = None
        if v_escape_shares is not None:
            if contract_price > 0.0:
                top_3_vol_usdt = v_escape_shares * contract_price
            else:
                top_3_vol_usdt = v_escape_shares

        resultado = self.calcular_posicion(
            balance_actual=balance,
            p_estimada=proposal.estimated_prob,
            cuota=cuota_bruta,
            pct_stop_loss=pct_stop_loss,
            operaciones_activas=operaciones_activas,
            exposicion_cluster_actual=exposicion_cluster_actual,
            top_3_bid_volumen=top_3_vol_usdt,
        )

        ev_net = resultado.get("ev", 0.0)

        if not resultado["operar"]:
            return RiskApprovedOrder(
                symbol=proposal.symbol,
                side=proposal.side,
                price=proposal.target_price,
                quantity=0.0,
                ev_net=ev_net,
                approved=False,
                rejection_reason=resultado.get("motivo", "Rechazado por riesgo"),
            )

        stake = resultado["stake"]
        price = proposal.target_price
        raw_quantity = (stake / price) if price > 0.0 else stake

        # Dimensional clamping exacto (Regla de Oro 3):
        # Q_ejecutable = min(Q, V_escape)
        # S_ejecutable = Q_ejecutable * P
        if v_escape_shares is not None:
            final_quantity = min(raw_quantity, v_escape_shares)
        else:
            final_quantity = raw_quantity

        quantity = round(max(0.0, final_quantity), 4)

        return RiskApprovedOrder(
            symbol=proposal.symbol,
            side=proposal.side,
            price=price,
            quantity=quantity,
            ev_net=ev_net,
            approved=True,
            rejection_reason=None,
        )

    # --------------------------------------------------------------------------
    # 4. GESTIÓN DE RACHAS (GANANCIA / PÉRDIDA)
    # --------------------------------------------------------------------------
    def registrar_resultado(self, es_ganadora: bool) -> None:
        """
        Registra el resultado de una operación cerrada.
        - Si es_ganadora == True: se resetea la racha de pérdidas a 0 (factor_racha = 1.0).
        - Si es_ganadora == False: se incrementa la racha perdedora (+1).
        """
        if es_ganadora:
            self.consecutive_losses = 0
            logger.info("Victoria registrada. Racha perdedora reseteada a 0. Factor racha: 1.0.")
        else:
            self.consecutive_losses += 1
            nuevo_factor = self.factor_racha
            logger.info(
                f"Pérdida registrada. Racha consecutiva: {self.consecutive_losses}. "
                f"Factor de atenuación: {nuevo_factor:.4f}."
            )

    def reset_racha(self) -> None:
        """Resetea manualmente el contador de pérdidas consecutivas."""
        self.consecutive_losses = 0


# Instancia o alias conveniente para compatibilidad
GestorRiesgoBinance = EscudoFinancieroBinance
