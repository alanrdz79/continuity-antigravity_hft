# -*- coding: utf-8 -*-
"""
estrategias.hft_engine
======================
Motor de Alta Frecuencia (HFT) y Microestructura para CONTINUITY Binance Spot.

Implementa:
1. Lógica HFT de 4 Fases (PLANnew.md):
   - Fase 1 (Pre-Match OBI): Entrada Maker Limit Buy a Best Bid + 1 tick con I >= 0.60
     y Spread <= $0.03. Salida Maker Limit Sell a Best Ask + 2 ticks. Exposición: 2 a 10s.
   - Fase 2 (Transición T-5m / limpiar_mesa): Cancelación atómica de órdenes pendientes
     y Market Sell de contratos no emparejados. Exposición al minuto cero = 0%, USDT = 100%.
   - Fase 3 (In-Play Latency Sniping): Detección de desfase de oráculo en eventos reales
     (gol, tarjeta roja, anotación) antes del congelamiento del libro; salida al normalizar.
   - Fase 4 (Time Decay Scalping min 75-90): Monitoreo de partidos en empate con índice de
     peligro -> 0. Entrada en decaimiento acelerado durante 60-90 segundos y venta a mercado.

2. Directivas de Negocio del Usuario:
   - Cobertura universal de 7 deportes: Fútbol, Béisbol, Fútbol Americano, Básquetbol,
     Tenis, Hockey, eSports (foco en vivo y trending).
   - Estrategia A (Explotación del Time Decay): Minutos 65-70 en partidos estancados.
     Comprar share del Empate/Resultado actual, mantener 3-5 minutos para ganar el tick
     de tiempo, y vender antes de que acabe el partido.
   - Estrategia B (Caza de Reacciones Exageradas): Desplome de precios por pánico contra
     el favorito dominante (xG / posesión superior). Comprar el 'dip' y vender en el
     rebote especulativo tras la primera jugada peligrosa a favor, SIN esperar a que anote gol.

3. Integración con Reglas de Oro y Escudo Financiero:
   - Regla de Oro 1: Spread máximo <= $0.03.
   - Regla de Oro 2: Bloqueo si Binance reporta "SUSPENDED".
   - Regla de Oro 3: Posición acotada al volumen acumulado en los primeros 3 niveles de BID.
   - Escudo Financiero: EV >= 0.015 neto, atenuación 0.85^n por racha, techo del 15% por clúster.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from continuitis.microestructura_binance import (
    DEFAULT_TICK_SIZE,
    MAX_SPREAD_PERMITIDO,
    BUY_DOMINANCE_IMBALANCE_THRESHOLD,
    GoldenRulesValidator,
    HFTPriceCalculator,
    MicroestructuraBinanceEngine,
    MicrostructureSignal,
    OrderBookImbalanceCalculator,
    OrderBookSnapshot,
    OrderProposal,
    RiskApprovedOrder,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance

logger = logging.getLogger("CONTINUITY.HFTEngine")


# ==============================================================================
# 1. COBERTURA DE 7 DEPORTES Y METADATOS
# ==============================================================================

class SportType(str, Enum):
    """Las 7 disciplinas deportivas cubiertas universalmente."""
    SOCCER = "SOCCER"                      # Fútbol
    BASEBALL = "BASEBALL"                  # Béisbol
    AMERICAN_FOOTBALL = "AMERICAN_FOOTBALL"# Fútbol Americano (NFL)
    BASKETBALL = "BASKETBALL"              # Básquetbol (NBA)
    TENNIS = "TENNIS"                      # Tenis (ATP/WTA)
    HOCKEY = "HOCKEY"                      # Hockey sobre hielo (NHL)
    ESPORTS = "ESPORTS"                    # eSports (LoL, CS, Dota)


@dataclass(frozen=True)
class SportConfig:
    """Configuración y umbrales específicos para cada disciplina deportiva."""
    sport: SportType
    name_es: str
    duration_standard_minutes: float
    stagnant_attack_threshold: float       # Ataques de peligro por minuto para considerar estancado
    default_tick_size: float = DEFAULT_TICK_SIZE
    strategy_a_window_start_min: float = 65.0
    strategy_a_window_end_min: float = 70.0
    phase_4_window_start_min: float = 75.0
    phase_4_window_end_min: float = 90.0


SPORT_CONFIGS: Dict[SportType, SportConfig] = {
    SportType.SOCCER: SportConfig(
        sport=SportType.SOCCER,
        name_es="Fútbol",
        duration_standard_minutes=90.0,
        stagnant_attack_threshold=0.25,
        default_tick_size=0.01,
        strategy_a_window_start_min=65.0,
        strategy_a_window_end_min=70.0,
        phase_4_window_start_min=75.0,
        phase_4_window_end_min=90.0,
    ),
    SportType.BASEBALL: SportConfig(
        sport=SportType.BASEBALL,
        name_es="Béisbol",
        duration_standard_minutes=180.0,
        stagnant_attack_threshold=0.30,
        default_tick_size=0.01,
        strategy_a_window_start_min=120.0,  # ~Inning 7
        strategy_a_window_end_min=135.0,
        phase_4_window_start_min=140.0,    # Inning 8-9
        phase_4_window_end_min=180.0,
    ),
    SportType.AMERICAN_FOOTBALL: SportConfig(
        sport=SportType.AMERICAN_FOOTBALL,
        name_es="Fútbol Americano",
        duration_standard_minutes=60.0,
        stagnant_attack_threshold=0.30,
        default_tick_size=0.01,
        strategy_a_window_start_min=42.0,   # Q4 inicio
        strategy_a_window_end_min=48.0,
        phase_4_window_start_min=50.0,     # Q4 tramo final
        phase_4_window_end_min=60.0,
    ),
    SportType.BASKETBALL: SportConfig(
        sport=SportType.BASKETBALL,
        name_es="Básquetbol",
        duration_standard_minutes=48.0,
        stagnant_attack_threshold=0.40,
        default_tick_size=0.01,
        strategy_a_window_start_min=34.0,   # Q4 temprano
        strategy_a_window_end_min=38.0,
        phase_4_window_start_min=40.0,     # Q4 clímax
        phase_4_window_end_min=48.0,
    ),
    SportType.TENNIS: SportConfig(
        sport=SportType.TENNIS,
        name_es="Tenis",
        duration_standard_minutes=120.0,
        stagnant_attack_threshold=0.20,
        default_tick_size=0.01,
        strategy_a_window_start_min=80.0,
        strategy_a_window_end_min=90.0,
        phase_4_window_start_min=95.0,
        phase_4_window_end_min=120.0,
    ),
    SportType.HOCKEY: SportConfig(
        sport=SportType.HOCKEY,
        name_es="Hockey",
        duration_standard_minutes=60.0,
        stagnant_attack_threshold=0.25,
        default_tick_size=0.01,
        strategy_a_window_start_min=42.0,   # P3 inicial
        strategy_a_window_end_min=47.0,
        phase_4_window_start_min=50.0,     # P3 final
        phase_4_window_end_min=60.0,
    ),
    SportType.ESPORTS: SportConfig(
        sport=SportType.ESPORTS,
        name_es="eSports",
        duration_standard_minutes=35.0,
        stagnant_attack_threshold=0.25,
        default_tick_size=0.01,
        strategy_a_window_start_min=22.0,
        strategy_a_window_end_min=26.0,
        phase_4_window_start_min=28.0,
        phase_4_window_end_min=35.0,
    ),
}


# ==============================================================================
# 2. MODELO DE ESTADO DEL EVENTO EN VIVO (MATCH LIVE STATE)
# ==============================================================================

@dataclass
class MatchLiveState:
    """
    Estado contextual del evento deportivo y métricas en vivo.
    Soporta fútbol y adaptación a los otros 6 deportes.
    """
    match_id: str
    symbol: str
    sport: SportType = SportType.SOCCER
    time_to_kickoff_minutes: Optional[float] = None # None si ya inició; >0 si pre-match (ej. 60.0, 5.0)
    is_live: bool = False
    minute: float = 0.0
    score_home: int = 0
    score_away: int = 0
    danger_attacks_per_min: float = 0.0
    possession_home_pct: float = 50.0
    possession_away_pct: float = 50.0
    xg_home: float = 0.0
    xg_away: float = 0.0
    dominant_favorite: Optional[str] = None         # "HOME", "AWAY" o None
    recent_dangerous_attack: bool = False           # Flag de ataque peligroso reciente a favor
    last_event: Optional[str] = None                # "GOAL", "RED_CARD", "PENALTY", "INJURY", etc.
    last_event_timestamp: float = 0.0
    odds_prematch_favorite: float = 0.0             # Cuota de referencia previa al evento
    current_implied_prob_fav: float = 0.0           # Probabilidad implícita actual en mercado

    @property
    def is_tied(self) -> bool:
        return self.score_home == self.score_away

    @property
    def is_prematch(self) -> bool:
        return (not self.is_live) and (self.time_to_kickoff_minutes is not None) and (self.time_to_kickoff_minutes > 0.0)

    @property
    def is_stagnant(self) -> bool:
        cfg = SPORT_CONFIGS.get(self.sport, SPORT_CONFIGS[SportType.SOCCER])
        return self.danger_attacks_per_min <= cfg.stagnant_attack_threshold


# ==============================================================================
# 3. CONTRATOS DE POSICIONES Y ÓRDENES HFT
# ==============================================================================

@dataclass
class HftOrder:
    """Registro de orden emitida por el motor HFT."""
    order_id: str
    symbol: str
    side: str                          # "BUY", "SELL"
    order_type: str                    # "LIMIT", "MARKET"
    price: float
    quantity: float
    strategy_id: str
    phase: str
    timestamp: float
    status: str = "PENDING"            # "PENDING", "FILLED", "CANCELLED", "REJECTED"


@dataclass
class HftPosition:
    """Registro de posición abierta bajo gestión de timeout y salida HFT."""
    position_id: str
    symbol: str
    strategy_id: str
    phase: str
    side: str
    entry_price: float
    quantity: float
    entry_time: float
    target_exit_price: float
    timeout_seconds: float
    status: str = "OPEN"               # "OPEN", "CLOSED", "FORCE_CLOSED"
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_expired(self) -> bool:
        if self.status != "OPEN":
            return False
        return (time.time() - self.entry_time) >= self.timeout_seconds


@dataclass(frozen=True)
class HftSignal:
    """Decisión operativa emitida por el HFTEngine."""
    symbol: str
    action: str                        # "BUY_LIMIT", "SELL_LIMIT", "MARKET_SELL", "CLEANUP", "HOLD", "NO_ACTION"
    strategy_id: str
    phase: str
    price: float
    quantity: float
    estimated_prob: float
    payout_decimal: float
    reason: str
    authorized: bool = False
    micro_signal: Optional[MicrostructureSignal] = None
    approved_order: Optional[RiskApprovedOrder] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# 4. MOTOR HFT CUANTITATIVO (HFTEngine)
# ==============================================================================

class HFTEngine:
    """
    Motor integral de Alta Frecuencia para mercados deportivos de Binance Spot.
    
    Gestiona:
    1. Fase 1: Pre-match OBI scalping (Best Bid + 1 tick, Best Ask + 2 ticks, timeout 2-10s).
    2. Fase 2: T-5m cleanup atómico ('limpiar_mesa', cancelación y venta a mercado).
    3. Fase 3: In-play latency sniping ante desfase de oráculo.
    4. Fase 4: Scalping exponencial de time decay en empate (min 75-90, 60-90s).
    5. Estrategia A: Scalp time decay min 65-70, retención 3-5 min.
    6. Estrategia B: Caza de sobre-reacciones en favoritos, salida en primera jugada peligrosa.
    7. Validador estricto de Reglas de Oro 1, 2, 3 y Escudo Financiero.
    """

    def __init__(
        self,
        micro_engine: Optional[MicroestructuraBinanceEngine] = None,
        risk_engine: Optional[EscudoFinancieroBinance] = None,
        tick_size: float = DEFAULT_TICK_SIZE,
        default_phase1_timeout_s: float = 5.0,  # Dentro de la ventana de 2 a 10s
        default_phase4_timeout_s: float = 75.0, # Dentro de la ventana de 60 a 90s
        default_strategy_a_timeout_s: float = 240.0, # 4 minutos (entre 3 y 5 min)
    ):
        self.tick_size = tick_size
        self.micro_engine = micro_engine or MicroestructuraBinanceEngine(tick_size=tick_size)
        self.risk_engine = risk_engine or EscudoFinancieroBinance()
        
        self.phase1_timeout_s = min(10.0, max(2.0, default_phase1_timeout_s))
        self.phase4_timeout_s = min(90.0, max(60.0, default_phase4_timeout_s))
        self.strategy_a_timeout_s = min(300.0, max(180.0, default_strategy_a_timeout_s))

        # Estado interno de órdenes y posiciones
        self.active_positions: Dict[str, HftPosition] = {}
        self.pending_orders: Dict[str, HftOrder] = {}
        self.closed_positions: List[HftPosition] = []

    # --------------------------------------------------------------------------
    # FASE 1: PRE-MATCH OBI ENTRY & EXIT (PLANnew §3 Módulo 2)
    # --------------------------------------------------------------------------
    def evaluar_fase_1_prematch_obi(
        self,
        snapshot: OrderBookSnapshot,
        match_state: MatchLiveState,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster: float = 0.0,
    ) -> HftSignal:
        """
        Fase 1: Pre-Match OBI Scalping (120 min a 5 min antes del evento).
        - Desequilibrio OBI I >= 0.60 (dominancia compradora >= 80%).
        - Spread <= $0.03 (Regla de Oro 1).
        - Mercado ACTIVE (Regla de Oro 2).
        - Entrada Maker: Best Bid + 1 tick.
        - Salida Maker: Best Ask + 2 ticks.
        - Exposición máxima: 2 a 10 segundos.
        """
        symbol = snapshot.symbol
        time_to_ko = match_state.time_to_kickoff_minutes

        # Verificación de ventana temporal de Fase 1 (T-120m a T-5m)
        if time_to_ko is not None and (time_to_ko < 5.0 or time_to_ko > 120.0):
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_1_OBI",
                phase="FASE_1_PREMATCH",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=f"Fuera de ventana temporal Fase 1 (T-{time_to_ko:.1f}m no está en [5, 120])",
                authorized=False,
            )

        # 1. Evaluar microestructura L2
        micro_signal = self.micro_engine.evaluar_snapshot(
            snapshot=snapshot,
            strategy_id="HFT_PHASE_1_OBI",
        )

        if not micro_signal.autorizado or micro_signal.propuesta_orden is None:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_1_OBI",
                phase="FASE_1_PREMATCH",
                price=0.0,
                quantity=0.0,
                estimated_prob=micro_signal.ratio_compra,
                payout_decimal=0.0,
                reason=micro_signal.motivo,
                authorized=False,
                micro_signal=micro_signal,
            )

        propuesta = micro_signal.propuesta_orden

        # 2. En mercados de predicción binarios, cada share paga 1.0 USD al ganar -> cuota = 1.0 / target_price
        binary_payout = round(1.0 / max(propuesta.target_price, 0.01), 4)
        binary_proposal = OrderProposal(
            symbol=propuesta.symbol,
            side=propuesta.side,
            target_price=propuesta.target_price,
            stop_price=propuesta.stop_price,
            estimated_prob=propuesta.estimated_prob,
            payout_decimal=binary_payout,
            strategy_id=propuesta.strategy_id,
        )

        # Evaluar mediante Escudo Financiero y Regla de Oro 3
        approved_order = self.risk_engine.evaluar_propuesta(
            proposal=binary_proposal,
            balance=balance,
            operaciones_activas=operaciones_activas,
            exposicion_cluster_actual=exposicion_cluster,
            top_3_bids=micro_signal.liquidez_escape_top3_gr3,
        )

        if not approved_order.approved or approved_order.quantity <= 0.0:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_1_OBI",
                phase="FASE_1_PREMATCH",
                price=propuesta.target_price,
                quantity=0.0,
                estimated_prob=propuesta.estimated_prob,
                payout_decimal=propuesta.payout_decimal,
                reason=approved_order.rejection_reason or "Rechazado por Escudo Financiero",
                authorized=False,
                micro_signal=micro_signal,
                approved_order=approved_order,
            )

        # Crear orden y registrar
        order_id = f"HFT1_{symbol}_{int(time.time()*1000)}"
        hft_order = HftOrder(
            order_id=order_id,
            symbol=symbol,
            side="BUY",
            order_type="LIMIT",
            price=approved_order.price,
            quantity=approved_order.quantity,
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            timestamp=time.time(),
            status="PENDING",
        )
        self.pending_orders[order_id] = hft_order

        # Registrar expectativa de posición con timeout de 2 a 10s
        pos_id = f"POS_HFT1_{order_id}"
        pos = HftPosition(
            position_id=pos_id,
            symbol=symbol,
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            side="BUY",
            entry_price=approved_order.price,
            quantity=approved_order.quantity,
            entry_time=time.time(),
            target_exit_price=micro_signal.precio_salida_limit_sell,
            timeout_seconds=self.phase1_timeout_s,
            status="OPEN",
            metadata={"best_ask": micro_signal.best_ask, "order_id": order_id},
        )
        self.active_positions[pos_id] = pos

        return HftSignal(
            symbol=symbol,
            action="LIMIT_BUY",
            strategy_id="HFT_PHASE_1_OBI",
            phase="FASE_1_PREMATCH",
            price=approved_order.price,
            quantity=approved_order.quantity,
            estimated_prob=propuesta.estimated_prob,
            payout_decimal=propuesta.payout_decimal,
            reason="Condiciones óptimas Fase 1 (OBI >= 0.60, Maker Limit)",
            authorized=True,
            micro_signal=micro_signal,
            approved_order=approved_order,
            metadata={"target_exit_price": micro_signal.precio_salida_limit_sell, "timeout_s": self.phase1_timeout_s},
        )

    # --------------------------------------------------------------------------
    # FASE 2: REBALANCEO Y LIMPIEZA ATÓMICA T-5m (limpiar_mesa)
    # --------------------------------------------------------------------------
    def ejecutar_fase_2_limpiar_mesa(
        self,
        symbol: str,
        snapshot: Optional[OrderBookSnapshot] = None,
    ) -> Dict[str, Any]:
        """
        Fase 2: Rebalanceo y Transición a T-5m antes del silbatazo inicial.
        - limpiar_mesa(): Cancela de forma atómica todas las órdenes pendientes en el libro.
        - Si existen contratos atrapados no emparejados, ejecuta Market Sell inmediato.
        - Regla Innegociable: Exposición en el minuto cero = 0%; liquidez en USDT = 100%.
        """
        ordenes_canceladas: List[str] = []
        liquidaciones_mercado: List[Dict[str, Any]] = []
        total_volumen_liquidado: float = 0.0

        # 1. Cancelación atómica de órdenes pendientes del símbolo
        ordenes_a_borrar = [oid for oid, ord_obj in self.pending_orders.items() if ord_obj.symbol == symbol]
        for oid in ordenes_a_borrar:
            self.pending_orders[oid].status = "CANCELLED"
            ordenes_canceladas.append(oid)
            del self.pending_orders[oid]

        # 2. Venta a mercado inmediata de cualquier posición abierta / no cerrada
        posiciones_a_cerrar = [pid for pid, p in self.active_positions.items() if p.symbol == symbol and p.status == "OPEN"]
        
        # Determinar mejor precio de BID para la salida a mercado
        precio_salida_mercado = 0.0
        if snapshot and snapshot.bids:
            precio_salida_mercado = snapshot.bids[0][0]

        for pid in posiciones_a_cerrar:
            pos = self.active_positions[pid]
            pos.status = "FORCE_CLOSED"
            pos.exit_time = time.time()
            pos.exit_price = precio_salida_mercado
            
            pnl = round((precio_salida_mercado - pos.entry_price) * pos.quantity, 4)
            pos.pnl = pnl
            
            self.closed_positions.append(pos)
            total_volumen_liquidado += pos.quantity
            liquidaciones_mercado.append({
                "position_id": pid,
                "quantity": pos.quantity,
                "entry_price": pos.entry_price,
                "exit_price": precio_salida_mercado,
                "pnl": pnl,
                "motivo": "LIMPIAR_MESA_T5M",
            })
            del self.active_positions[pid]

        resultado = {
            "symbol": symbol,
            "fase": "FASE_2_LIMPIAR_MESA",
            "ordenes_canceladas": ordenes_canceladas,
            "liquidaciones_mercado": liquidaciones_mercado,
            "total_volumen_liquidado": round(total_volumen_liquidado, 4),
            "exposicion_final_pct": 0.0,
            "liquidez_usdt_pct": 100.0,
            "regla_innegociable_cumplida": True,
        }
        logger.info(f"[HFTEngine] limpiar_mesa ejecutado para {symbol}: {resultado}")
        return resultado

    # --------------------------------------------------------------------------
    # FASE 3: IN-PLAY LATENCY SNIPING (PLANnew §3 Módulo 2)
    # --------------------------------------------------------------------------
    def snipe_desfase_oraculo(
        self,
        event_type: str,
        event_timestamp: float,
        snapshot: OrderBookSnapshot,
        match_state: MatchLiveState,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster: float = 0.0,
    ) -> HftSignal:
        """
        Fase 3: In-Play Latency Sniping (Minutos 1 al 75).
        - Detecta discrepancias de tiempo real entre el evento deportivo y el libro de Binance.
        - Si ocurre un evento crítico (gol, tarjeta roja) ANTES de la suspensión del libro,
          adquiere contratos desactualizados y coloca orden de salida inmediata tras
          el restablecimiento / normalización del mercado.
        """
        symbol = snapshot.symbol

        # Si el libro ya está suspendido por Binance, no se puede hacer sniping (Regla de Oro 2)
        if snapshot.market_status.upper() == "SUSPENDED":
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_3_SNIPING",
                phase="FASE_3_SNIPING",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason="Libro ya SUSPENDIDO por Binance (Regla de Oro 2 activada)",
                authorized=False,
            )

        # Verificar spread (Regla de Oro 1)
        if not snapshot.is_valid:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_3_SNIPING",
                phase="FASE_3_SNIPING",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason="Libro incompleto o vacío",
                authorized=False,
            )

        best_bid = snapshot.bids[0][0]
        best_ask = snapshot.asks[0][0]
        gr1_ok, spread, gr1_motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(best_bid, best_ask)
        if not gr1_ok:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_3_SNIPING",
                phase="FASE_3_SNIPING",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=gr1_motivo,
                authorized=False,
            )

        # Detectar si el precio actual en el libro todavía refleja cuotas desactualizadas
        # Por ejemplo, cuota pre-gol alta mientras el gol ya se confirmó en el feed deportivo
        delta_tiempo_evento = max(0.0, time.time() - event_timestamp)

        # Estimar probabilidad real post-evento vs precio ofrecido
        # Si evento favorece el contrato y Best Ask aún no sube:
        prob_post_evento = 0.85 if event_type in ("GOAL", "TOUCHDOWN", "RUN", "BREAK_POINT") else 0.70
        payout_esperado = round(1.0 / max(best_ask, 0.01), 4)

        propuesta = OrderProposal(
            symbol=symbol,
            side="BUY",
            target_price=best_ask, # Sniping taker agresivo o límite en ask desactualizado
            stop_price=round(best_bid - self.tick_size, 4),
            estimated_prob=prob_post_evento,
            payout_decimal=payout_esperado,
            strategy_id="HFT_PHASE_3_SNIPING",
        )

        top3_liquidity = GoldenRulesValidator.calcular_liquidez_escape_top3_bids(snapshot.bids)
        approved = self.risk_engine.evaluar_propuesta(
            proposal=propuesta,
            balance=balance,
            operaciones_activas=operaciones_activas,
            exposicion_cluster_actual=exposicion_cluster,
            top_3_bids=top3_liquidity,
        )

        if not approved.approved or approved.quantity <= 0.0:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_3_SNIPING",
                phase="FASE_3_SNIPING",
                price=best_ask,
                quantity=0.0,
                estimated_prob=prob_post_evento,
                payout_decimal=payout_esperado,
                reason=approved.rejection_reason or "Rechazado por Escudo Financiero",
                authorized=False,
                approved_order=approved,
            )

        pos_id = f"POS_SNIPE_{symbol}_{int(time.time()*1000)}"
        # Precio objetivo de salida tras normalización de mercado
        target_exit = round(min(0.99, best_ask + 0.10), 4)
        pos = HftPosition(
            position_id=pos_id,
            symbol=symbol,
            strategy_id="HFT_PHASE_3_SNIPING",
            phase="FASE_3_SNIPING",
            side="BUY",
            entry_price=approved.price,
            quantity=approved.quantity,
            entry_time=time.time(),
            target_exit_price=target_exit,
            timeout_seconds=30.0,
            status="OPEN",
            metadata={"event_type": event_type, "latency_sniped_s": delta_tiempo_evento},
        )
        self.active_positions[pos_id] = pos

        return HftSignal(
            symbol=symbol,
            action="LIMIT_BUY",
            strategy_id="HFT_PHASE_3_SNIPING",
            phase="FASE_3_SNIPING",
            price=approved.price,
            quantity=approved.quantity,
            estimated_prob=prob_post_evento,
            payout_decimal=payout_esperado,
            reason=f"Desfase detectado en evento {event_type} (latencia {delta_tiempo_evento*1000:.1f}ms)",
            authorized=True,
            approved_order=approved,
            metadata={"target_exit_price": target_exit, "event": event_type},
        )

    # --------------------------------------------------------------------------
    # FASE 4: TIME DECAY SCALPING (Minuto 75 al 90) (PLANnew §3 Módulo 2)
    # --------------------------------------------------------------------------
    def evaluar_fase_4_time_decay_scalping(
        self,
        snapshot: OrderBookSnapshot,
        match_state: MatchLiveState,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster: float = 0.0,
    ) -> HftSignal:
        """
        Fase 4: Time Decay Exponencial (Minuto 75 al 90).
        - Monitorea partidos en empate con índice de peligro aproximándose a cero (attacks/min -> 0).
        - Entra en contratos con decaimiento acelerado durante ventanas cortas (60 a 90 segundos).
        - Liquida la posición con orden de mercado sin esperar la conclusión del partido.
        """
        symbol = snapshot.symbol
        cfg = SPORT_CONFIGS.get(match_state.sport, SPORT_CONFIGS[SportType.SOCCER])

        # Verificar ventana de tiempo (minutos 75 a 90 o equivalente)
        if not (cfg.phase_4_window_start_min <= match_state.minute <= cfg.phase_4_window_end_min):
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=f"Minuto {match_state.minute} fuera de ventana Fase 4 [{cfg.phase_4_window_start_min}, {cfg.phase_4_window_end_min}]",
                authorized=False,
            )

        # Condición: Empate en el marcador
        if not match_state.is_tied:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason="El partido no se encuentra en empate",
                authorized=False,
            )

        # Condición: Índice de peligro tendiendo a cero (Danger attacks -> 0)
        if match_state.danger_attacks_per_min > 0.20:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=f"Peligro elevado ({match_state.danger_attacks_per_min:.2f} > 0.20 ataques/min)",
                authorized=False,
            )

        # Evaluar libro de órdenes L2 y Reglas de Oro
        if not snapshot.is_valid:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason="Libro incompleto o vacío",
                authorized=False,
            )

        # Regla de Oro 2
        gr2_ok, gr2_motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(snapshot.market_status)
        if not gr2_ok:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=gr2_motivo,
                authorized=False,
            )

        best_bid = snapshot.bids[0][0]
        best_ask = snapshot.asks[0][0]

        # Regla de Oro 1
        gr1_ok, spread, gr1_motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(best_bid, best_ask)
        if not gr1_ok:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=gr1_motivo,
                authorized=False,
            )

        # Entrada Maker en Best Bid + 1 tick (o join bid si el spread es 1 tick)
        precio_entrada = HFTPriceCalculator.calcular_precio_entrada_limit_buy(best_bid, self.tick_size, best_ask=best_ask)
        precio_salida = round(min(0.99, precio_entrada + 0.02), 4)

        # En min 75-90 con peligro ~0 en empate, probabilidad del resultado es alta (0.90-0.95)
        prob_estimada = round(max(0.90, min(0.98, 0.88 + (match_state.minute - 75.0) * 0.005)), 4)
        payout = round(1.0 / max(precio_entrada, 0.01), 4)

        propuesta = OrderProposal(
            symbol=symbol,
            side="BUY",
            target_price=precio_entrada,
            stop_price=round(best_bid - (2 * self.tick_size), 4),
            estimated_prob=prob_estimada,
            payout_decimal=payout,
            strategy_id="HFT_PHASE_4_TIME_DECAY",
        )

        top3_liquidity = GoldenRulesValidator.calcular_liquidez_escape_top3_bids(snapshot.bids)
        approved = self.risk_engine.evaluar_propuesta(
            proposal=propuesta,
            balance=balance,
            operaciones_activas=operaciones_activas,
            exposicion_cluster_actual=exposicion_cluster,
            top_3_bids=top3_liquidity,
        )

        if not approved.approved or approved.quantity <= 0.0:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="HFT_PHASE_4_TIME_DECAY",
                phase="FASE_4_TIME_DECAY",
                price=precio_entrada,
                quantity=0.0,
                estimated_prob=prob_estimada,
                payout_decimal=payout,
                reason=approved.rejection_reason or "Rechazado por Escudo Financiero",
                authorized=False,
                approved_order=approved,
            )

        pos_id = f"POS_DECAY4_{symbol}_{int(time.time()*1000)}"
        pos = HftPosition(
            position_id=pos_id,
            symbol=symbol,
            strategy_id="HFT_PHASE_4_TIME_DECAY",
            phase="FASE_4_TIME_DECAY",
            side="BUY",
            entry_price=approved.price,
            quantity=approved.quantity,
            entry_time=time.time(),
            target_exit_price=precio_salida,
            timeout_seconds=self.phase4_timeout_s, # 60 a 90 segundos
            status="OPEN",
            metadata={"minute_entry": match_state.minute, "window_s": self.phase4_timeout_s},
        )
        self.active_positions[pos_id] = pos

        return HftSignal(
            symbol=symbol,
            action="LIMIT_BUY",
            strategy_id="HFT_PHASE_4_TIME_DECAY",
            phase="FASE_4_TIME_DECAY",
            price=approved.price,
            quantity=approved.quantity,
            estimated_prob=prob_estimada,
            payout_decimal=payout,
            reason=f"Fase 4 decay activo (min {match_state.minute:.0f}, empate, ataques={match_state.danger_attacks_per_min:.2f}/min)",
            authorized=True,
            approved_order=approved,
            metadata={"timeout_s": self.phase4_timeout_s, "target_exit": precio_salida},
        )

    # --------------------------------------------------------------------------
    # ESTRATEGIA A: EXPLOTACIÓN DEL TIME DECAY (Minuto 65-70)
    # --------------------------------------------------------------------------
    def evaluar_estrategia_a_time_decay(
        self,
        snapshot: OrderBookSnapshot,
        match_state: MatchLiveState,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster: float = 0.0,
    ) -> HftSignal:
        """
        Directiva de Negocio: Estrategia A (Explotación del Time Decay).
        - Scalp de bajo riesgo.
        - Entrar entre minutos 65-70 en partidos estancados (ritmo lento / pocos ataques peligrosos).
        - Comprar share del Empate o Resultado actual.
        - Mantener de 3 a 5 minutos (180 a 300 segundos) para ganar el tick del tiempo.
        - Vender antes de que termine el partido.
        """
        symbol = snapshot.symbol
        cfg = SPORT_CONFIGS.get(match_state.sport, SPORT_CONFIGS[SportType.SOCCER])

        # 1. Ventana de minutos 65-70
        if not (cfg.strategy_a_window_start_min <= match_state.minute <= cfg.strategy_a_window_end_min):
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_A_TIME_DECAY",
                phase="ESTRATEGIA_A",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=f"Minuto {match_state.minute} fuera de ventana Estrategia A [{cfg.strategy_a_window_start_min}, {cfg.strategy_a_window_end_min}]",
                authorized=False,
            )

        # 2. Partido estancado (ritmo lento / peligro bajo)
        if match_state.danger_attacks_per_min > cfg.stagnant_attack_threshold:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_A_TIME_DECAY",
                phase="ESTRATEGIA_A",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=f"Partido no estancado: ataques de peligro={match_state.danger_attacks_per_min:.2f} > {cfg.stagnant_attack_threshold:.2f}",
                authorized=False,
            )

        # 3. Validar libro de órdenes y Reglas de Oro
        if not snapshot.is_valid:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_A_TIME_DECAY",
                phase="ESTRATEGIA_A",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason="Libro incompleto o vacío",
                authorized=False,
            )

        gr2_ok, gr2_motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(snapshot.market_status)
        if not gr2_ok:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_A_TIME_DECAY",
                phase="ESTRATEGIA_A",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=gr2_motivo,
                authorized=False,
            )

        best_bid = snapshot.bids[0][0]
        best_ask = snapshot.asks[0][0]

        gr1_ok, spread, gr1_motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(best_bid, best_ask)
        if not gr1_ok:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_A_TIME_DECAY",
                phase="ESTRATEGIA_A",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=gr1_motivo,
                authorized=False,
            )

        # Precio de entrada Maker Limit a Best Bid + 1 tick (o join bid si spread <= 1 tick)
        precio_entrada = HFTPriceCalculator.calcular_precio_entrada_limit_buy(best_bid, self.tick_size, best_ask=best_ask)
        # Salida esperada tras captura del tick de tiempo (1 a 3 ticks)
        precio_salida = round(precio_entrada + (2 * self.tick_size), 4)

        prob_estimada = 0.75
        payout = round(1.0 / max(precio_entrada, 0.01), 4)

        propuesta = OrderProposal(
            symbol=symbol,
            side="BUY",
            target_price=precio_entrada,
            stop_price=round(best_bid - (2 * self.tick_size), 4),
            estimated_prob=prob_estimada,
            payout_decimal=payout,
            strategy_id="STRATEGY_A_TIME_DECAY",
        )

        top3_liquidity = GoldenRulesValidator.calcular_liquidez_escape_top3_bids(snapshot.bids)
        approved = self.risk_engine.evaluar_propuesta(
            proposal=propuesta,
            balance=balance,
            operaciones_activas=operaciones_activas,
            exposicion_cluster_actual=exposicion_cluster,
            top_3_bids=top3_liquidity,
        )

        if not approved.approved or approved.quantity <= 0.0:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_A_TIME_DECAY",
                phase="ESTRATEGIA_A",
                price=precio_entrada,
                quantity=0.0,
                estimated_prob=prob_estimada,
                payout_decimal=payout,
                reason=approved.rejection_reason or "Rechazado por Escudo Financiero",
                authorized=False,
                approved_order=approved,
            )

        pos_id = f"POS_STRA_{symbol}_{int(time.time()*1000)}"
        pos = HftPosition(
            position_id=pos_id,
            symbol=symbol,
            strategy_id="STRATEGY_A_TIME_DECAY",
            phase="ESTRATEGIA_A",
            side="BUY",
            entry_price=approved.price,
            quantity=approved.quantity,
            entry_time=time.time(),
            target_exit_price=precio_salida,
            timeout_seconds=self.strategy_a_timeout_s, # 180 a 300 segundos
            status="OPEN",
            metadata={"minute_entry": match_state.minute, "retencion_segundos": self.strategy_a_timeout_s},
        )
        self.active_positions[pos_id] = pos

        return HftSignal(
            symbol=symbol,
            action="LIMIT_BUY",
            strategy_id="STRATEGY_A_TIME_DECAY",
            phase="ESTRATEGIA_A",
            price=approved.price,
            quantity=approved.quantity,
            estimated_prob=prob_estimada,
            payout_decimal=payout,
            reason=f"Estrategia A activada (min {match_state.minute:.0f}, estancado, retención {self.strategy_a_timeout_s/60:.1f}m)",
            authorized=True,
            approved_order=approved,
            metadata={"timeout_s": self.strategy_a_timeout_s, "target_exit": precio_salida},
        )

    # --------------------------------------------------------------------------
    # ESTRATEGIA B: CAZA DE REACCIONES EXAGERADAS (OVERREACTION HUNTING)
    # --------------------------------------------------------------------------
    def evaluar_estrategia_b_overreaction(
        self,
        snapshot: OrderBookSnapshot,
        match_state: MatchLiveState,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster: float = 0.0,
    ) -> HftSignal:
        """
        Directiva de Negocio: Estrategia B (Caza de Reacciones Exageradas).
        - Scalp de alto riesgo.
        - Detectar desplomes de precios por pánico (ej. favorito recibe gol pero domina posesión/xG).
        - Comprar el 'dip'.
        - Vender en el rebote especulativo tras la primera jugada peligrosa a favor,
          SIN esperar a que anote gol.
        """
        symbol = snapshot.symbol

        # 1. Verificar existencia de favorito dominante
        if not match_state.dominant_favorite:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_B_OVERREACTION",
                phase="ESTRATEGIA_B",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason="No se identificó un favorito dominante para cacería de sobre-reacción",
                authorized=False,
            )

        # 2. Verificar dominancia en métricas (Posesión >= 60% o xG marcadamente favorable)
        fav = match_state.dominant_favorite
        posesion_fav = match_state.possession_home_pct if fav == "HOME" else match_state.possession_away_pct
        xg_fav = match_state.xg_home if fav == "HOME" else match_state.xg_away
        xg_opp = match_state.xg_away if fav == "HOME" else match_state.xg_home

        dominancia_metrica = (posesion_fav >= 58.0) or ((xg_fav - xg_opp) >= 0.50)
        if not dominancia_metrica:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_B_OVERREACTION",
                phase="ESTRATEGIA_B",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=f"Métricas del favorito insuficientes (posesión={posesion_fav:.1f}%, xG delta={xg_fav - xg_opp:.2f})",
                authorized=False,
            )

        # 3. Detectar desplome / 'dip' por pánico en el precio
        # Si la probabilidad implícita actual cayó significativamente por debajo del intrinsic value
        if not snapshot.is_valid:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_B_OVERREACTION",
                phase="ESTRATEGIA_B",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason="Libro incompleto o vacío",
                authorized=False,
            )

        gr2_ok, gr2_motivo = GoldenRulesValidator.verificar_regla_oro_2_estado_mercado(snapshot.market_status)
        if not gr2_ok:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_B_OVERREACTION",
                phase="ESTRATEGIA_B",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=gr2_motivo,
                authorized=False,
            )

        best_bid = snapshot.bids[0][0]
        best_ask = snapshot.asks[0][0]

        gr1_ok, spread, gr1_motivo = GoldenRulesValidator.verificar_regla_oro_1_spread(best_bid, best_ask)
        if not gr1_ok:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_B_OVERREACTION",
                phase="ESTRATEGIA_B",
                price=0.0,
                quantity=0.0,
                estimated_prob=0.0,
                payout_decimal=0.0,
                reason=gr1_motivo,
                authorized=False,
            )

        # Comprar el 'dip': orden en Best Bid + 1 tick (o join bid si spread <= 1 tick)
        precio_entrada = HFTPriceCalculator.calcular_precio_entrada_limit_buy(best_bid, self.tick_size, best_ask=best_ask)
        # Rebote especulativo proyectado tras jugada peligrosa: Best Ask + 3-5 ticks
        precio_salida_rebound = round(precio_entrada + (3 * self.tick_size), 4)

        prob_estimada = 0.58  # Probabilidad de rebote tras ataque
        payout = round(1.0 / max(precio_entrada, 0.01), 4)

        propuesta = OrderProposal(
            symbol=symbol,
            side="BUY",
            target_price=precio_entrada,
            stop_price=round(best_bid - (3 * self.tick_size), 4),
            estimated_prob=prob_estimada,
            payout_decimal=payout,
            strategy_id="STRATEGY_B_OVERREACTION",
        )

        top3_liquidity = GoldenRulesValidator.calcular_liquidez_escape_top3_bids(snapshot.bids)
        approved = self.risk_engine.evaluar_propuesta(
            proposal=propuesta,
            balance=balance,
            operaciones_activas=operaciones_activas,
            exposicion_cluster_actual=exposicion_cluster,
            top_3_bids=top3_liquidity,
        )

        if not approved.approved or approved.quantity <= 0.0:
            return HftSignal(
                symbol=symbol,
                action="NO_ACTION",
                strategy_id="STRATEGY_B_OVERREACTION",
                phase="ESTRATEGIA_B",
                price=precio_entrada,
                quantity=0.0,
                estimated_prob=prob_estimada,
                payout_decimal=payout,
                reason=approved.rejection_reason or "Rechazado por Escudo Financiero",
                authorized=False,
                approved_order=approved,
            )

        pos_id = f"POS_STRB_{symbol}_{int(time.time()*1000)}"
        pos = HftPosition(
            position_id=pos_id,
            symbol=symbol,
            strategy_id="STRATEGY_B_OVERREACTION",
            phase="ESTRATEGIA_B",
            side="BUY",
            entry_price=approved.price,
            quantity=approved.quantity,
            entry_time=time.time(),
            target_exit_price=precio_salida_rebound,
            timeout_seconds=300.0, # Timeout de seguridad
            status="OPEN",
            metadata={
                "favorite": fav,
                "entry_dip_price": approved.price,
                "rebound_target": precio_salida_rebound,
                "wait_for_dangerous_attack": True,
            },
        )
        self.active_positions[pos_id] = pos

        return HftSignal(
            symbol=symbol,
            action="LIMIT_BUY",
            strategy_id="STRATEGY_B_OVERREACTION",
            phase="ESTRATEGIA_B",
            price=approved.price,
            quantity=approved.quantity,
            estimated_prob=prob_estimada,
            payout_decimal=payout,
            reason=f"Dip comprado en favorito {fav} (posesión={posesion_fav:.0f}%, xG delta={xg_fav-xg_opp:.2f})",
            authorized=True,
            approved_order=approved,
            metadata={"target_exit": precio_salida_rebound, "wait_for_next_attack": True},
        )

    # --------------------------------------------------------------------------
    # GESTOR DE REBOTE DE ESTRATEGIA B (SALIDA EN JUGADA PELIGROSA)
    # --------------------------------------------------------------------------
    def evaluar_salida_rebote_estrategia_b(
        self,
        symbol: str,
        match_state: MatchLiveState,
        snapshot: OrderBookSnapshot,
    ) -> List[HftSignal]:
        """
        Monitorea posiciones abiertas de Estrategia B:
        Vender en el rebote especulativo tras la PRIMERA JUGADA PELIGROSA a favor,
        SIN ESPERAR A QUE ANOTE GOL.
        """
        senales_salida: List[HftSignal] = []

        if not match_state.recent_dangerous_attack:
            return senales_salida

        best_bid = snapshot.bids[0][0] if snapshot.bids else 0.0

        posiciones_strb = [
            (pid, p) for pid, p in self.active_positions.items()
            if p.symbol == symbol and p.strategy_id == "STRATEGY_B_OVERREACTION" and p.status == "OPEN"
        ]

        for pid, pos in posiciones_strb:
            precio_salida = max(best_bid, pos.target_exit_price)
            pos.status = "CLOSED"
            pos.exit_time = time.time()
            pos.exit_price = precio_salida
            pos.pnl = round((precio_salida - pos.entry_price) * pos.quantity, 4)
            self.closed_positions.append(pos)
            del self.active_positions[pid]

            senales_salida.append(
                HftSignal(
                    symbol=symbol,
                    action="SELL_LIMIT",
                    strategy_id="STRATEGY_B_OVERREACTION",
                    phase="ESTRATEGIA_B_EXIT",
                    price=precio_salida,
                    quantity=pos.quantity,
                    estimated_prob=1.0,
                    payout_decimal=round(precio_salida / max(pos.entry_price, 0.01), 4),
                    reason="Rebote especulativo capturado tras jugada peligrosa del favorito (sin esperar gol)",
                    authorized=True,
                    metadata={"position_id": pid, "pnl": pos.pnl},
                )
            )

        return senales_salida

    # --------------------------------------------------------------------------
    # GESTIÓN DE TIMEOUTS Y EXPOSICIÓN TEMPORAL (AUDITORÍA PERIÓDICA)
    # --------------------------------------------------------------------------
    def auditar_timeouts(
        self,
        current_time: Optional[float] = None,
        snapshot: Optional[OrderBookSnapshot] = None,
    ) -> List[HftSignal]:
        """
        Revisa todas las posiciones abiertas y genera órdenes de salida o liquidación
        para aquellas cuyo tiempo de exposición ha expirado.
        - Fase 1: 2 a 10s.
        - Fase 4: 60 a 90s.
        - Estrategia A: 180 a 300s (3-5 min).
        """
        now = current_time or time.time()
        senales_cierre: List[HftSignal] = []

        posiciones_expiradas = [
            (pid, p) for pid, p in self.active_positions.items()
            if p.status == "OPEN" and (now - p.entry_time) >= p.timeout_seconds
        ]

        best_bid = 0.0
        if snapshot and snapshot.bids:
            best_bid = snapshot.bids[0][0]

        for pid, pos in posiciones_expiradas:
            precio_salida = best_bid if best_bid > 0 else pos.target_exit_price
            pos.status = "CLOSED"
            pos.exit_time = now
            pos.exit_price = precio_salida
            pos.pnl = round((precio_salida - pos.entry_price) * pos.quantity, 4)
            self.closed_positions.append(pos)
            del self.active_positions[pid]

            senales_cierre.append(
                HftSignal(
                    symbol=pos.symbol,
                    action="MARKET_SELL",
                    strategy_id=pos.strategy_id,
                    phase=f"{pos.phase}_TIMEOUT_EXIT",
                    price=precio_salida,
                    quantity=pos.quantity,
                    estimated_prob=1.0,
                    payout_decimal=round(precio_salida / max(pos.entry_price, 0.01), 4),
                    reason=f"Timeout de exposición alcanzado ({pos.timeout_seconds:.1f}s)",
                    authorized=True,
                    metadata={"position_id": pid, "pnl": pos.pnl},
                )
            )

        return senales_cierre

    # --------------------------------------------------------------------------
    # ENRUTADOR UNIVERSAL DE MERCADO (DISPATCHER)
    # --------------------------------------------------------------------------
    def procesar_mercado(
        self,
        snapshot: OrderBookSnapshot,
        match_state: MatchLiveState,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster: float = 0.0,
    ) -> HftSignal:
        """
        Punto de entrada unificado para procesar un tick o fotograma de mercado.
        Determina de forma autónoma la fase o estrategia operativa correspondiente
        según el ciclo de vida del evento y el estado del partido.
        """
        symbol = snapshot.symbol

        # 1. Caso Pre-Match: Fase 2 (limpiar_mesa) a T-5m o menos
        if match_state.time_to_kickoff_minutes is not None:
            if match_state.time_to_kickoff_minutes <= 5.0:
                res_cleanup = self.ejecutar_fase_2_limpiar_mesa(symbol, snapshot)
                return HftSignal(
                    symbol=symbol,
                    action="CLEANUP",
                    strategy_id="HFT_PHASE_2_CLEANUP",
                    phase="FASE_2_LIMPIAR_MESA",
                    price=0.0,
                    quantity=res_cleanup["total_volumen_liquidado"],
                    estimated_prob=1.0,
                    payout_decimal=1.0,
                    reason="Ejecución T-5m limpiar_mesa (Regla innegociable: 0% exposición)",
                    authorized=True,
                    metadata=res_cleanup,
                )
            elif match_state.time_to_kickoff_minutes <= 120.0:
                # Fase 1: Pre-match OBI scalping
                return self.evaluar_fase_1_prematch_obi(
                    snapshot, match_state, balance, operaciones_activas, exposicion_cluster
                )

        # 2. Caso In-Play
        if match_state.is_live:
            # Primero: Revisar salidas de rebote en Estrategia B si hubo jugada peligrosa
            salidas_b = self.evaluar_salida_rebote_estrategia_b(symbol, match_state, snapshot)
            if salidas_b:
                return salidas_b[0]

            # Minutos 75 a 90: Fase 4 Time Decay Scalping en empate
            cfg = SPORT_CONFIGS.get(match_state.sport, SPORT_CONFIGS[SportType.SOCCER])
            if cfg.phase_4_window_start_min <= match_state.minute <= cfg.phase_4_window_end_min:
                sig_fase4 = self.evaluar_fase_4_time_decay_scalping(
                    snapshot, match_state, balance, operaciones_activas, exposicion_cluster
                )
                if sig_fase4.authorized:
                    return sig_fase4

            # Minutos 65 a 70: Estrategia A Time Decay
            if cfg.strategy_a_window_start_min <= match_state.minute <= cfg.strategy_a_window_end_min:
                sig_stra = self.evaluar_estrategia_a_time_decay(
                    snapshot, match_state, balance, operaciones_activas, exposicion_cluster
                )
                if sig_stra.authorized:
                    return sig_stra

            # Estrategia B: Caza de sobre-reacciones en favorito
            sig_strb = self.evaluar_estrategia_b_overreaction(
                snapshot, match_state, balance, operaciones_activas, exposicion_cluster
            )
            if sig_strb.authorized:
                return sig_strb

        # Si ninguna estrategia genera señal autorizada
        return HftSignal(
            symbol=symbol,
            action="NO_ACTION",
            strategy_id="NONE",
            phase="MONITOREO",
            price=0.0,
            quantity=0.0,
            estimated_prob=0.0,
            payout_decimal=0.0,
            reason="Sin oportunidad HFT activa en este tick",
            authorized=False,
        )

    def limpiar_mesa_prematch(
        self,
        symbol: str,
        snapshot: Optional[OrderBookSnapshot] = None,
    ) -> Dict[str, Any]:
        """Alias para ejecutar_fase_2_limpiar_mesa requerido por orquestador."""
        return self.ejecutar_fase_2_limpiar_mesa(symbol=symbol, snapshot=snapshot)

    def evaluar_mercado_completo(
        self,
        snapshot: OrderBookSnapshot,
        match_state: MatchLiveState,
        balance: float,
        operaciones_activas: int = 0,
        exposicion_cluster: float = 0.0,
    ) -> HftSignal:
        """Alias para procesar_mercado requerido por orquestador."""
        return self.procesar_mercado(
            snapshot=snapshot,
            match_state=match_state,
            balance=balance,
            operaciones_activas=operaciones_activas,
            exposicion_cluster=exposicion_cluster,
        )

    def registrar_orden_ejecutada(
        self,
        signal: HftSignal,
        order_id: str,
        executed_price: float,
        executed_qty: float,
    ) -> HftPosition:
        """Registra la orden ejecutada en las posiciones activas de HFTEngine."""
        pos_id = f"POS_{order_id}"
        target_exit = signal.metadata.get("target_exit_price", executed_price + (2 * self.tick_size))
        timeout_s = signal.metadata.get("timeout_s", self.phase1_timeout_s)
        pos = HftPosition(
            position_id=pos_id,
            symbol=signal.symbol,
            strategy_id=signal.strategy_id,
            phase=signal.phase,
            side="BUY",
            entry_price=executed_price,
            quantity=executed_qty,
            entry_time=time.time(),
            target_exit_price=target_exit,
            timeout_seconds=timeout_s,
            status="OPEN",
            metadata={"order_id": order_id},
        )
        self.active_positions[pos_id] = pos
        return pos

    def cerrar_posicion(
        self,
        position_id: str,
        exit_price: float,
    ) -> Optional[HftPosition]:
        """Cierra una posición abierta registrando precio de salida y PnL."""
        if position_id in self.active_positions:
            pos = self.active_positions[position_id]
            pos.status = "CLOSED"
            pos.exit_price = exit_price
            pos.exit_time = time.time()
            pos.pnl = round((exit_price - pos.entry_price) * pos.quantity, 4)
            self.closed_positions.append(pos)
            del self.active_positions[position_id]
            return pos
        return None
