# -*- coding: utf-8 -*-
"""
continuitis.microestructura_binance
===================================
Motor Cuantitativo de Microestructura para Binance Spot y Mercados de Predicción.

Implementa los pilares de microestructura exigidos por el plan CONTINUITY HFT:
1. Cálculo de Desequilibrio del Libro de Órdenes (Order Book Imbalance - OBI):
      I = (sum V_Bid - sum V_Ask) / (sum V_Bid + sum V_Ask)
2. Detección exacta de dominancia compradora al 80% (I >= 0.60).
3. Regla de Oro 1: Spread MÁXIMO permitido <= $0.03; rechazo inmediato si spread > $0.03.
4. Regla de Oro 2: Bloqueo automático e inmediato de órdenes si MarketStatus == 'SUSPENDED'.
5. Regla de Oro 3: Agregación de volumen en los primeros 3 niveles del BID para garantizar
   liquidez de escape ante liquidaciones de emergencia a mercado.
6. Guardián de Latencia y Disyuntor de Emergencia (Latency Circuit Breaker < 800 ms).
7. Cálculo algorítmico de precios de entrada y salida:
      Entrada Maker: Best Bid + 1 tick
      Salida Maker:  Best Ask + 2 ticks
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple, Union

logger = logging.getLogger("CONTINUITY.MicroestructuraBinance")


# ==============================================================================
# 1. CONSTANTES TÉCNICAS Y REGLAS DE NEGOCIO
# ==============================================================================

MAX_SPREAD_PERMITIDO: float = 0.03            # Regla de Oro 1: Spread máximo $0.03
BUY_DOMINANCE_IMBALANCE_THRESHOLD: float = 0.60 # Dominancia de compra del 80% (I >= 0.60)
BUY_DOMINANCE_RATIO_THRESHOLD: float = 0.80     # Proporción directa de volumen Bid / Total
MAX_FEED_LATENCY_MS: float = 800.0             # Límite crítico de latencia de feed (< 800 ms)
DEFAULT_TICK_SIZE: float = 0.01                # Tick size base para mercados de predicción
DEFAULT_DECIMAL_PLACES: int = 4                # Precisión de redondeo para precios de contratos
TOP_BIDS_ESCAPE_LEVELS: int = 3                # Regla de Oro 3: Primeros 3 niveles del BID


# ==============================================================================
# 2. CONTRATOS DE DATOS (DATA TRANSFER OBJECTS)
# ==============================================================================

@dataclass(frozen=True)
class OrderBookSnapshot:
    """
    Fotograma inmutable del libro de órdenes Level-2.
    - bids: Tupla de (precio, volumen) ordenados descendentemente (mejor precio primero).
    - asks: Tupla de (precio, volumen) ordenados ascendentemente (mejor precio primero).
    """
    symbol: str
    bids: Tuple[Tuple[float, float], ...]
    asks: Tuple[Tuple[float, float], ...]
    timestamp_ms: int
    market_status: str = "ACTIVE"  # "ACTIVE" o "SUSPENDED"

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    @property
    def spread(self) -> Optional[float]:
        if self.bids and self.asks:
            return round(self.asks[0][0] - self.bids[0][0], 6)
        return None

    @property
    def is_valid(self) -> bool:
        return bool(self.bids and self.asks)


@dataclass(frozen=True)
class OrderProposal:
    """Propuesta de orden lista para validación en RiskEngine y enrutamiento."""
    symbol: str
    side: str
    target_price: float
    stop_price: float
    estimated_prob: float
    payout_decimal: float
    strategy_id: str


@dataclass(frozen=True)
class RiskApprovedOrder:
    """Orden evaluada y aprobada por el Escudo Financiero."""
    symbol: str
    side: str
    price: float
    quantity: float
    ev_net: float
    approved: bool
    rejection_reason: Optional[str] = None


@dataclass(frozen=True)
class MicrostructureSignal:
    """
    Señal enriquecida de microestructura que sintetiza el análisis L2,
    estado de reglas de oro y parámetros de precios sugeridos.
    """
    symbol: str
    imbalance: float
    dominancia_compra_80: bool
    ratio_compra: float
    volumen_bids: float
    volumen_asks: float
    best_bid: float
    best_ask: float
    spread: float
    spread_valido_gr1: bool
    market_status: str
    mercado_activo_gr2: bool
    liquidez_escape_top3_gr3: float
    precio_entrada_limit_buy: float
    precio_salida_limit_sell: float
    latencia_ms: float
    autorizado: bool
    motivo: str
    timestamp_ms: int
    propuesta_orden: Optional[OrderProposal] = None


# ==============================================================================
# 3. CÁLCULO DE ORDER BOOK IMBALANCE (OBI) & DOMINANCIA
# ==============================================================================

class OrderBookImbalanceCalculator:
    """
    Calculador matemático del desequilibrio de volumen en el libro Level-2.
    
    Fórmula de desequilibrio (Order Book Imbalance):
        I = (sum V_Bid - sum V_Ask) / (sum V_Bid + sum V_Ask)
    
    Equivalencia con dominancia del 80%:
        Si V_Bid / (V_Bid + V_Ask) >= 0.80, entonces:
        I = (0.80 - 0.20) / (0.80 + 0.20) = 0.60 / 1.0 = 0.60.
        Por tanto, dominancia >= 80% es exactamente I >= 0.60.
    """

    @staticmethod
    def calcular_imbalance(
        bids: Sequence[Tuple[float, float]],
        asks: Sequence[Tuple[float, float]],
        niveles: Optional[int] = None,
    ) -> float:
        """
        Calcula el OBI normalizado en el intervalo [-1.0, 1.0].
        Si no hay volumen total, retorna 0.0 de forma segura.
        """
        if not bids and not asks:
            return 0.0

        bids_eval = bids[:niveles] if niveles is not None else bids
        asks_eval = asks[:niveles] if niveles is not None else asks

        sum_v_bid = sum(float(v) for _, v in bids_eval if float(v) > 0)
        sum_v_ask = sum(float(v) for _, v in asks_eval if float(v) > 0)

        volumen_total = sum_v_bid + sum_v_ask
        if volumen_total <= 0.0:
            return 0.0

        imbalance = (sum_v_bid - sum_v_ask) / volumen_total
        # Acotar matemáticamente por seguridad ante imprecisión flotante
        return max(-1.0, min(1.0, round(imbalance, 6)))

    @staticmethod
    def calcular_ratio_compra(
        bids: Sequence[Tuple[float, float]],
        asks: Sequence[Tuple[float, float]],
        niveles: Optional[int] = None,
    ) -> float:
        """
        Calcula la proporción directa de volumen comprador: sum(V_Bid) / sum(V_Total).
        Retorna valor en el intervalo [0.0, 1.0].
        """
        bids_eval = bids[:niveles] if niveles is not None else bids
        asks_eval = asks[:niveles] if niveles is not None else asks

        sum_v_bid = sum(float(v) for _, v in bids_eval if float(v) > 0)
        sum_v_ask = sum(float(v) for _, v in asks_eval if float(v) > 0)

        volumen_total = sum_v_bid + sum_v_ask
        if volumen_total <= 0.0:
            return 0.0

        return max(0.0, min(1.0, round(sum_v_bid / volumen_total, 6)))

    @classmethod
    def detectar_dominancia_compra(
        cls,
        imbalance: float,
        threshold: float = BUY_DOMINANCE_IMBALANCE_THRESHOLD,
    ) -> bool:
        """
        Verifica si el desequilibrio supera el umbral de dominancia compradora.
        Por defecto umbral 0.60 (correspondiente a 80% de volumen comprador).
        """
        return imbalance >= (threshold - 1e-9)


# ==============================================================================
# 4. REGLAS DE ORO (GOLDEN RULES 1, 2 Y 3)
# ==============================================================================

class GoldenRulesValidator:
    """Validador estricto de las 3 Reglas de Oro de CONTINUITY."""

    @staticmethod
    def verificar_regla_oro_1_spread(
        best_bid: float,
        best_ask: float,
        max_spread: float = MAX_SPREAD_PERMITIDO,
    ) -> Tuple[bool, float, str]:
        """
        Regla de Oro 1: Spread MÁXIMO permitido <= $0.03.
        Si el spread es mayor a $0.03 o el libro está invertido/vacío, se rechaza la operación.
        """
        if (
            not isinstance(best_bid, (int, float))
            or not isinstance(best_ask, (int, float))
            or math.isnan(best_bid)
            or math.isnan(best_ask)
            or math.isinf(best_bid)
            or math.isinf(best_ask)
            or best_bid <= 0
            or best_ask <= 0
        ):
            return False, 0.0, "PRECIOS_INVALIDOS_O_VACIOS: SPREAD_INVALIDO"

        spread = round(best_ask - best_bid, 6)

        if math.isnan(spread) or math.isinf(spread):
            return False, 0.0, "PRECIOS_INVALIDOS_O_VACIOS: SPREAD_INVALIDO"

        if spread < 0:
            return False, spread, f"LIBRO_INVERTIDO (Ask={best_ask} < Bid={best_bid})"

        if spread > (max_spread + 1e-9):
            return False, spread, f"SPREAD_EXCESIVO ({spread:.4f} > {max_spread:.2f})"

        return True, spread, "SPREAD_VALIDO"

    @staticmethod
    def verificar_regla_oro_2_estado_mercado(market_status: str) -> Tuple[bool, str]:
        """
        Regla de Oro 2: Monitoreo de Bloqueo por Mercado Suspendido.
        Si Binance o el oráculo transiciona a 'SUSPENDED' (por gol, VAR o incidente),
        se bloquea inmediatamente la entrada de cualquier orden nueva.
        """
        status_clean = str(market_status).strip().upper()
        if status_clean == "SUSPENDED":
            return False, "MERCADO_SUSPENDIDO_BINANCE"
        if status_clean in ("ACTIVE", "TRADING", "OPEN"):
            return True, "MERCADO_ACTIVO"
        return False, f"ESTADO_MERCADO_DESCONOCIDO ({status_clean})"

    @staticmethod
    def calcular_liquidez_escape_top3_bids(
        bids: Sequence[Tuple[float, float]],
        levels: int = TOP_BIDS_ESCAPE_LEVELS,
    ) -> float:
        """
        Regla de Oro 3: Suma el volumen disponible en los primeros 3 niveles del BID.
        Garantiza la existencia de liquidez inmediata para una salida de emergencia a mercado.
        """
        top_levels = bids[:levels]
        liquidez = sum(float(v) for _, v in top_levels if float(v) > 0)
        return round(liquidez, 6)

    @classmethod
    def verificar_regla_oro_3_liquidez(
        cls,
        cantidad_propuesta: float,
        bids: Sequence[Tuple[float, float]],
        levels: int = TOP_BIDS_ESCAPE_LEVELS,
    ) -> Tuple[bool, float, str]:
        """
        Regla de Oro 3: Valida que la cantidad propuesta a comprar no exceda
        la liquidez acumulada en los primeros 3 niveles de BID.
        """
        liquidez_disponible = cls.calcular_liquidez_escape_top3_bids(bids, levels)
        if cantidad_propuesta <= 0:
            return False, liquidez_disponible, "CANTIDAD_PROPUESTA_INVALIDA"

        if cantidad_propuesta > (liquidez_disponible + 1e-9):
            return (
                False,
                liquidez_disponible,
                f"LIQUIDEZ_INSUFICIENTE_TOP3 ({cantidad_propuesta:.4f} > {liquidez_disponible:.4f})",
            )

        return True, liquidez_disponible, "LIQUIDEZ_ESCAPE_SUFICIENTE"


# ==============================================================================
# 5. CÁLCULO DE PRECIOS HFT (ENTRADA Y SALIDA MAKER)
# ==============================================================================

class HFTPriceCalculator:
    """
    Cálculo de posturas límite HFT:
    - Entrada Maker: Best Bid + 1 tick (capturar prioridad sin cruzar el spread).
    - Salida Maker:  Best Ask + 2 ticks (captura de micro-spread y decay).
    """

    @staticmethod
    def calcular_precio_entrada_limit_buy(
        best_bid: float,
        tick_size: float = DEFAULT_TICK_SIZE,
        decimals: int = DEFAULT_DECIMAL_PLACES,
        best_ask: Optional[float] = None,
    ) -> float:
        """
        Entrada Maker: Best Bid + 1 tick (capturar prioridad sin cruzar el spread).
        Si spread <= 1 tick (best_ask - best_bid <= tick_size), colocar orden en best_bid
        (join best bid) para garantizar ejecución Maker pasiva y evitar pagar tarifas Taker.
        """
        if best_bid <= 0:
            raise ValueError(f"Best Bid inválido: {best_bid}")
        if best_ask is not None:
            if round(best_ask - best_bid, decimals) <= round(tick_size, decimals) + 1e-9:
                return round(best_bid, decimals)
        precio = best_bid + tick_size
        return round(precio, decimals)

    @staticmethod
    def calcular_precio_salida_limit_sell(
        best_ask: float,
        tick_size: float = DEFAULT_TICK_SIZE,
        decimals: int = DEFAULT_DECIMAL_PLACES,
    ) -> float:
        """Salida: Best Ask + 2 ticks."""
        if best_ask <= 0:
            raise ValueError(f"Best Ask inválido: {best_ask}")
        precio = best_ask + (2 * tick_size)
        return round(precio, decimals)


# ==============================================================================
# 6. GUARDIÁN DE LATENCIA Y DISYUNTOR DE EMERGENCIA (CIRCUIT BREAKER)
# ==============================================================================

class LatencyAndKillSwitchGuard:
    """
    Monitorea la latencia de feed y estado de Binance.
    - Si el delta de tiempo supera 800 ms, activa estado de emergencia.
    - Si el mercado está suspendido, bloquea disparos.
    - Permite activación manual o externa de Kill Switch.
    """

    def __init__(self, max_latencia_ms: float = MAX_FEED_LATENCY_MS):
        self.max_latencia_ms = max_latencia_ms
        self.ultimo_heartbeat: float = time.time()
        self.mercado_suspendido: bool = False
        self.emergencia_activa: bool = False
        self.motivo_emergencia: str = ""

    def registrar_pulso_feed(self, timestamp: Optional[float] = None) -> None:
        """Registra pulso de datos frescos del feed. Si el sistema estaba en emergencia por latencia, se restablece."""
        self.ultimo_heartbeat = timestamp if timestamp is not None else time.time()
        if self.emergencia_activa and "LATENCIA_EXCESIVA" in self.motivo_emergencia:
            logger.info("[LatencyGuard] Feed re-estabilizado. Emergencia por latencia desactivada.")
            self.emergencia_activa = False
            self.motivo_emergencia = ""

    def actualizar_estado_binance(self, status: str) -> None:
        """Actualiza el estado de mercado reportado por Binance."""
        valido, motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(status)
        self.mercado_suspendido = not valido

    def activar_kill_switch(self, motivo: str = "KILL_SWITCH_MANUAL") -> None:
        """Dispara de forma irreversible o manual el disyuntor de emergencia."""
        self.emergencia_activa = True
        self.motivo_emergencia = motivo
        logger.warning(f"[LatencyGuard] DISYUNTOR ACTIVADO: {motivo}")

    def resetear_emergencia(self) -> None:
        """Restablece el estado operativo tras verificación de seguridad."""
        self.emergencia_activa = False
        self.motivo_emergencia = ""
        self.ultimo_heartbeat = time.time()
        logger.info("[LatencyGuard] Estado de emergencia restablecido manualmente.")

    def calcular_latencia_ms(self, timestamp_actual: Optional[float] = None) -> float:
        """Calcula el desfase de tiempo transcurrido desde el último pulso en milisegundos."""
        ahora = timestamp_actual if timestamp_actual is not None else time.time()
        delta_seg = ahora - self.ultimo_heartbeat
        return max(0.0, round(delta_seg * 1000.0, 2))

    def autorizacion_disparo(self) -> Tuple[bool, str]:
        """
        Verifica si el sistema está autorizado para emitir nuevas órdenes.
        Retorna (autorizado: bool, motivo: str).
        """
        if self.emergencia_activa:
            return False, f"EMERGENCIA_ACTIVA ({self.motivo_emergencia or 'BLOQUEADO'})"

        delta_ms = self.calcular_latencia_ms()
        if delta_ms > self.max_latencia_ms:
            self.emergencia_activa = True
            self.motivo_emergencia = f"LATENCIA_EXCESIVA ({delta_ms:.2f} ms > {self.max_latencia_ms} ms)"
            return False, self.motivo_emergencia

        if self.mercado_suspendido:
            return False, "MERCADO_SUSPENDIDO_BINANCE"

        return True, "AUTORIZADO"


# ==============================================================================
# 7. MOTOR INTEGRADO DE MICROESTRUCTURA BINANCE
# ==============================================================================

class MicroestructuraBinanceEngine:
    """
    Motor integral de Microestructura para CONTINUITY HFT.
    
    Evalúa de forma unificada:
    1. Guardián de latencia y estado de emergencia.
    2. Regla de Oro 2: Estado de mercado ("ACTIVE" vs "SUSPENDED").
    3. Regla de Oro 1: Spread máximo $0.03.
    4. Cálculo de Order Book Imbalance (OBI).
    5. Regla de Oro 3: Liquidez de escape en los 3 mejores niveles de BID.
    6. Detección de dominancia del 80% (I >= 0.60).
    7. Cálculo de precios límite de entrada (Bid + 1 tick) y salida (Ask + 2 ticks).
    """

    def __init__(
        self,
        max_latencia_ms: float = MAX_FEED_LATENCY_MS,
        max_spread: float = MAX_SPREAD_PERMITIDO,
        imbalance_umbral: float = BUY_DOMINANCE_IMBALANCE_THRESHOLD,
        tick_size: float = DEFAULT_TICK_SIZE,
    ):
        self.latency_guard = LatencyAndKillSwitchGuard(max_latencia_ms=max_latencia_ms)
        self.max_spread = max_spread
        self.imbalance_umbral = imbalance_umbral
        self.tick_size = tick_size

    def evaluar_snapshot(
        self,
        snapshot: OrderBookSnapshot,
        cantidad_propuesta: Optional[float] = None,
        strategy_id: str = "HFT_PHASE_1_OBI",
    ) -> MicrostructureSignal:
        """
        Evalúa un fotograma completo del libro de órdenes L2 y genera una señal estructurada.
        """
        ts_now_ms = int(time.time() * 1000)
        symbol = snapshot.symbol

        # 1. Actualizar latencia y estado en el guardián
        if snapshot.timestamp_ms > 0:
            ts_sec = snapshot.timestamp_ms / 1000.0
            self.latency_guard.registrar_pulso_feed(ts_sec)
        self.latency_guard.actualizar_estado_binance(snapshot.market_status)

        latencia_ms = self.latency_guard.calcular_latencia_ms()

        # Validación de libro no vacío
        if not snapshot.is_valid:
            return MicrostructureSignal(
                symbol=symbol,
                imbalance=0.0,
                dominancia_compra_80=False,
                ratio_compra=0.0,
                volumen_bids=0.0,
                volumen_asks=0.0,
                best_bid=0.0,
                best_ask=0.0,
                spread=0.0,
                spread_valido_gr1=False,
                market_status=snapshot.market_status,
                mercado_activo_gr2=False,
                liquidez_escape_top3_gr3=0.0,
                precio_entrada_limit_buy=0.0,
                precio_salida_limit_sell=0.0,
                latencia_ms=latencia_ms,
                autorizado=False,
                motivo="LIBRO_INCOMPLETO_O_VACIO",
                timestamp_ms=ts_now_ms,
            )

        best_bid = snapshot.bids[0][0]
        best_ask = snapshot.asks[0][0]

        # 2. Regla de Oro 2: Mercado activo / no suspendido
        gr2_ok, gr2_motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(
            snapshot.market_status
        )

        # 3. Regla de Oro 1: Spread máximo <= $0.03
        gr1_ok, spread, gr1_motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(
            best_bid, best_ask, max_spread=self.max_spread
        )

        # 4. Cálculo de volúmenes, OBI y ratio de compra
        sum_v_bid = sum(v for _, v in snapshot.bids)
        sum_v_ask = sum(v for _, v in snapshot.asks)
        imbalance = OrderBookImbalanceCalculator.calcular_imbalance(snapshot.bids, snapshot.asks)
        ratio_compra = OrderBookImbalanceCalculator.calcular_ratio_compra(snapshot.bids, snapshot.asks)
        dominancia_80 = OrderBookImbalanceCalculator.detectar_dominancia_compra(
            imbalance, threshold=self.imbalance_umbral
        )

        # 5. Regla de Oro 3: Liquidez de escape top 3 BIDs
        liquidez_top3 = GoldenRulesValidator.calcular_liquidez_escape_top3_bids(snapshot.bids)

        # 6. Cálculo de precios de entrada y salida
        precio_entrada = HFTPriceCalculator.calcular_precio_entrada_limit_buy(
            best_bid, tick_size=self.tick_size, best_ask=best_ask
        )
        precio_salida = HFTPriceCalculator.calcular_precio_salida_limit_sell(
            best_ask, tick_size=self.tick_size
        )

        # 7. Verificación de autorización de disparo
        guard_ok, guard_motivo = self.latency_guard.autorizacion_disparo()

        # Evaluación conjunta para autorizar
        autorizado = True
        motivo = "CONDICIONES_OPTIMAS_HFT"

        if not guard_ok:
            autorizado = False
            motivo = guard_motivo
        elif not gr2_ok:
            autorizado = False
            motivo = gr2_motivo
        elif not gr1_ok:
            autorizado = False
            motivo = gr1_motivo
        elif not dominancia_80:
            autorizado = False
            motivo = f"IMBALANCE_INSUFICIENTE ({imbalance:.4f} < {self.imbalance_umbral:.2f})"
        elif cantidad_propuesta is not None and cantidad_propuesta > 0:
            gr3_ok, _, gr3_motivo = GoldenRulesValidator.verificar_regla_oro_3_liquidez(
                cantidad_propuesta, snapshot.bids
            )
            if not gr3_ok:
                autorizado = False
                motivo = gr3_motivo

        # Construir propuesta de orden si está autorizado
        propuesta: Optional[OrderProposal] = None
        if autorizado:
            propuesta = OrderProposal(
                symbol=symbol,
                side="BUY",
                target_price=precio_entrada,
                stop_price=round(best_bid - self.tick_size, DEFAULT_DECIMAL_PLACES),
                estimated_prob=round(ratio_compra, 4),
                payout_decimal=round(precio_salida / max(precio_entrada, 0.0001), 4),
                strategy_id=strategy_id,
            )

        return MicrostructureSignal(
            symbol=symbol,
            imbalance=imbalance,
            dominancia_compra_80=dominancia_80,
            ratio_compra=ratio_compra,
            volumen_bids=round(sum_v_bid, 4),
            volumen_asks=round(sum_v_ask, 4),
            best_bid=round(best_bid, 4),
            best_ask=round(best_ask, 4),
            spread=round(spread, 4),
            spread_valido_gr1=gr1_ok,
            market_status=snapshot.market_status,
            mercado_activo_gr2=gr2_ok,
            liquidez_escape_top3_gr3=liquidez_top3,
            precio_entrada_limit_buy=precio_entrada,
            precio_salida_limit_sell=precio_salida,
            latencia_ms=latencia_ms,
            autorizado=autorizado,
            motivo=motivo,
            timestamp_ms=ts_now_ms,
            propuesta_orden=propuesta,
        )
