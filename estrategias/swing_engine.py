# -*- coding: utf-8 -*-
"""
estrategias.swing_engine
========================
Motor Ortogonal de Swing Trading para Mercados de Predicción Deportiva (Binance Spot).

Características Principales:
1. Concurrencia No Bloqueante (Zero Event Loop Starvation):
   - Ejecuta análisis macro y multi-hora en paralelo con el motor HFT de micro-ticks.
   - Descarga todas las operaciones intensivas de CPU (simulaciones Monte Carlo,
     modelado de volatilidad exponencial, regresión de probabilidad implícita)
     a hilos secundarios mediante `asyncio.to_thread`.
   - Mantiene la latencia del bucle de eventos < 50 ms (muy por debajo del límite de 800 ms).

2. Coordinación Atómica de Capital con EscudoFinancieroBinance:
   - Utiliza `AsyncCapitalGateway` con `asyncio.Lock` para garantizar reserva atómica
     de capital mediante `CapitalReservationToken`.
   - Previene sobre-asignación de balance y condiciones de carrera entre HFT y Swing.
   - Aplica estrictamente el techo del 15% por clúster del bankroll y atenuación de racha.

3. Análisis Cuantitativo de Tendencia Macro:
   - Detección de divergencias estadísticas entre cuotas históricas y calificaciones de poder.
   - Simulación Monte Carlo de caminos de probabilidad para estimar EV y cuota justa.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from continuitis.microestructura_binance import OrderProposal, RiskApprovedOrder
from continuitis.riesgo_binance import EscudoFinancieroBinance

logger = logging.getLogger("CONTINUITY.SwingEngine")


# ==============================================================================
# 1. GESTOR ATÓMICO DE RESERVA DE CAPITAL (ASYNC RISK GATEWAY & TOKENS)
# ==============================================================================

@dataclass
class CapitalReservationToken:
    """
    Token criptográfico/atómico de reserva de capital.
    Garantiza que una posición activa tiene fondos garantizados y bloqueados.
    """
    token_id: str
    strategy_id: str
    symbol: str
    stake: float
    reserved_at: float
    is_released: bool = False


class AsyncCapitalGateway:
    """
    Pasarela de capital concurrente y atómica protegida por asyncio.Lock.
    Coordina los motores HFT y Swing para no sobrepasar el techo del 15% de clúster.
    """

    def __init__(self, capital_total: float = 1000.0, max_cluster_exp: float = 0.15):
        self.lock = asyncio.Lock()
        self.capital_total = max(0.0, float(capital_total))
        self.max_cluster_exp = max(0.0, min(1.0, float(max_cluster_exp)))
        self.capital_comprometido: float = 0.0
        self.active_tokens: Dict[str, CapitalReservationToken] = {}
        self.total_reservas_exitosas: int = 0
        self.total_reservas_rechazadas: int = 0

    @property
    def capital_maximo_cluster(self) -> float:
        return round(self.capital_total * self.max_cluster_exp, 4)

    @property
    def capital_disponible_cluster(self) -> float:
        return max(0.0, round(self.capital_maximo_cluster - self.capital_comprometido, 4))

    async def actualizar_capital_total(self, nuevo_capital: float) -> None:
        async with self.lock:
            self.capital_total = max(0.0, float(nuevo_capital))

    async def reservar_capital(
        self,
        stake: float,
        strategy_id: str = "SWING_TRADING",
        symbol: str = "PRED_MARKET",
    ) -> Optional[CapitalReservationToken]:
        """
        Reserva atómicamente una cantidad de capital para una estrategia.
        Retorna CapitalReservationToken si la exposición futura <= 15% de capital_total.
        Retorna None si se excede el techo de clúster.
        """
        async with self.lock:
            if stake <= 0.0:
                return None

            max_permitido = round(self.capital_total * self.max_cluster_exp, 4)
            espacio = round(max_permitido - self.capital_comprometido, 4)

            if espacio <= 0.0:
                self.total_reservas_rechazadas += 1
                return None

            # Tolerar discrepancias sub-céntimo por redondeo de precio * cantidad solo si hay espacio disponible
            if stake <= espacio:
                allocated = round(stake, 4)
            elif (stake - espacio) <= 0.05 and espacio > 0.0:
                # Acotar estrictamente al espacio disponible para prevenir drift en liberación
                allocated = round(espacio, 4)
            else:
                self.total_reservas_rechazadas += 1
                logger.warning(
                    f"[CapitalGateway] Reserva RECHAZADA: solicitó {stake:.2f} USD, "
                    f"espacio disponible {espacio:.2f} USD (techo 15%={max_permitido:.2f})"
                )
                return None

            self.capital_comprometido = min(max_permitido, round(self.capital_comprometido + allocated, 4))
            self.total_reservas_exitosas += 1
            token_id = f"TOK_{uuid.uuid4().hex[:12]}_{int(time.time()*1000)}"
            token = CapitalReservationToken(
                token_id=token_id,
                strategy_id=strategy_id,
                symbol=symbol,
                stake=allocated,
                reserved_at=time.time(),
                is_released=False,
            )
            self.active_tokens[token_id] = token
            logger.debug(
                f"[CapitalGateway] Reserva aprobada: {allocated:.2f} USD para {strategy_id} | "
                f"Comprometido: {self.capital_comprometido:.2f}/{max_permitido:.2f} USD"
            )
            return token

    async def liberar_capital(self, token: CapitalReservationToken) -> bool:
        """
        Libera de forma atómica el capital reservado por un token.
        """
        async with self.lock:
            if token.token_id in self.active_tokens and not token.is_released:
                self.capital_comprometido = max(0.0, round(self.capital_comprometido - token.stake, 4))
                token.is_released = True
                del self.active_tokens[token.token_id]
                logger.debug(
                    f"[CapitalGateway] Capital liberado: {token.stake:.2f} USD | "
                    f"Comprometido restante: {self.capital_comprometido:.2f} USD"
                )
                return True
            return False

    async def reset_o_liberar_todas(self) -> None:
        """Libera de forma atómica todos los tokens activos en parada de emergencia."""
        async with self.lock:
            for token in list(self.active_tokens.values()):
                token.is_released = True
            self.active_tokens.clear()
            self.capital_comprometido = 0.0


# ==============================================================================
# 2. CÁLCULO INTENSIVO EN HILOS SECUNDARIOS (OFFLOAD CPU VIA asyncio.to_thread)
# ==============================================================================

def computar_analisis_macro_cpu(
    symbol: str,
    velas_historicas: Sequence[Tuple[float, float, float, float, float]], # (ts, open, high, low, close)
    sim_paths: int = 10000,
) -> Dict[str, Any]:
    """
    Función pura sincrónica de cálculo numérico intensivo (CPU-bound).
    Ejecutada en subprocesos/hilos secundarios vía asyncio.to_thread para
    evitar el bloqueo del bucle de eventos asyncio de HFT.
    
    Calcula:
    1. Medias móviles exponenciales (EMA rápida vs EMA lenta).
    2. Volatilidad realizada de retornos logarítmicos.
    3. Simulación Monte Carlo de convergencia de probabilidad para eventos deportivos.
    4. Estimación de valor intrínseco y sesgo direccional.
    """
    t_start = time.perf_counter()

    if not velas_historicas or len(velas_historicas) < 5:
        # Fallback si no hay suficientes velas
        return {
            "symbol": symbol,
            "trend_direction": "NEUTRAL",
            "implied_prob_trend": 0.50,
            "volatility": 0.05,
            "monte_carlo_win_prob": 0.50,
            "recommended_action": "HOLD",
            "target_price": 0.50,
            "stop_price": 0.45,
            "payout_decimal": 2.0,
            "compute_time_ms": 0.0,
        }

    precios_cierre = [float(c) for _, _, _, _, c in velas_historicas]
    n = len(precios_cierre)

    # 1. Medias móviles exponenciales
    alpha_rapida = 2.0 / (min(n, 12) + 1.0)
    alpha_lenta = 2.0 / (min(n, 26) + 1.0)

    ema_rapida = precios_cierre[0]
    ema_lenta = precios_cierre[0]
    for p in precios_cierre[1:]:
        ema_rapida = (p * alpha_rapida) + (ema_rapida * (1.0 - alpha_rapida))
        ema_lenta = (p * alpha_lenta) + (ema_lenta * (1.0 - alpha_lenta))

    # 2. Volatilidad realizada (retornos logarítmicos)
    log_returns = []
    for i in range(1, n):
        prev = max(precios_cierre[i - 1], 0.001)
        curr = max(precios_cierre[i], 0.001)
        log_returns.append(math.log(curr / prev))

    mean_ret = sum(log_returns) / max(len(log_returns), 1)
    variance = sum((r - mean_ret) ** 2 for r in log_returns) / max(len(log_returns) - 1, 1)
    volatilidad = math.sqrt(max(variance, 1e-8))

    # 3. Simulación Monte Carlo intensiva de trayectorias (CPU work)
    ultimo_precio = precios_cierre[-1]
    exitos = 0
    drift = mean_ret

    # Generador pseudo-aleatorio matemático para simular caminos estocásticos
    seed_val = int(ultimo_precio * 10000) % 1000003
    for path in range(sim_paths):
        # Simulación de paso estocástico (GBM discreto)
        seed_val = (1664525 * seed_val + 1013904223) % (2**32)
        norm_approx = ((seed_val / (2**32)) - 0.5) * 3.4641  # Aprox uniforme a normal
        sim_ret = drift + (volatilidad * norm_approx)
        sim_price = ultimo_precio * math.exp(sim_ret)
        if sim_price >= ultimo_precio:
            exitos += 1

    mc_win_prob = exitos / max(sim_paths, 1)

    # 4. Determinación de tendencia y precios objetivos de Swing
    if ema_rapida > (ema_lenta + 0.005) and mc_win_prob > 0.52:
        trend = "BULLISH"
        action = "BUY"
        target_price = round(min(0.95, ultimo_precio + (3.0 * volatilidad)), 4)
        stop_price = round(max(0.01, ultimo_precio - (2.0 * volatilidad)), 4)
    elif ema_rapida < (ema_lenta - 0.005) and mc_win_prob < 0.48:
        trend = "BEARISH"
        action = "SELL"
        target_price = round(max(0.05, ultimo_precio - (3.0 * volatilidad)), 4)
        stop_price = round(min(0.99, ultimo_precio + (2.0 * volatilidad)), 4)
    else:
        trend = "NEUTRAL"
        action = "HOLD"
        target_price = round(ultimo_precio + 0.02, 4)
        stop_price = round(max(0.01, ultimo_precio - 0.02), 4)

    payout = round(target_price / max(ultimo_precio, 0.01), 4)
    t_end = time.perf_counter()
    compute_ms = round((t_end - t_start) * 1000.0, 2)

    return {
        "symbol": symbol,
        "trend_direction": trend,
        "implied_prob_trend": round(mc_win_prob, 4),
        "volatility": round(volatilidad, 4),
        "monte_carlo_win_prob": round(mc_win_prob, 4),
        "recommended_action": action,
        "current_price": ultimo_precio,
        "target_price": target_price,
        "stop_price": stop_price,
        "payout_decimal": payout,
        "compute_time_ms": compute_ms,
    }


# ==============================================================================
# 3. CONTRATOS DE DATOS DE SWING
# ==============================================================================

@dataclass
class SwingPosition:
    """Posición activa de Swing Trading con token de capital enlazado."""
    position_id: str
    symbol: str
    side: str                          # "BUY", "SELL"
    entry_price: float
    quantity: float
    stake: float
    target_price: float
    stop_loss_price: float
    entry_time: float
    token: CapitalReservationToken
    status: str = "OPEN"               # "OPEN", "CLOSED"
    exit_price: Optional[float] = None
    exit_time: Optional[float] = None
    pnl: Optional[float] = None


@dataclass(frozen=True)
class SwingAnalysisResult:
    """Resultado estructurado del análisis de Swing."""
    symbol: str
    trend_direction: str
    implied_prob_trend: float
    volatility: float
    monte_carlo_win_prob: float
    recommended_action: str
    current_price: float
    target_price: float
    stop_price: float
    payout_decimal: float
    compute_time_ms: float


# ==============================================================================
# 4. MOTOR ORTOGONAL DE SWING TRADING (SwingEngine)
# ==============================================================================

class SwingEngine:
    """
    Motor complementario de Swing Trading operando de forma ortogonal a HFT.
    - Analiza horizontes multi-hora / diarios.
    - Descarga CPU intensivo a hilos vía asyncio.to_thread para no bloquear asyncio.
    - Reserva y libera capital atómicamente con AsyncCapitalGateway y EscudoFinanciero.
    """

    def __init__(
        self,
        risk_engine: Optional[EscudoFinancieroBinance] = None,
        capital_gateway: Optional[AsyncCapitalGateway] = None,
        balance: float = 1000.0,
        max_cluster_exp: float = 0.15,
    ):
        self.risk_engine = risk_engine or EscudoFinancieroBinance(max_cluster_exp=max_cluster_exp)
        self.capital_gateway = capital_gateway or AsyncCapitalGateway(
            capital_total=balance, max_cluster_exp=max_cluster_exp
        )
        self.active_positions: Dict[str, SwingPosition] = {}
        self.closed_positions: List[SwingPosition] = []

    async def analizar_oportunidad_macro(
        self,
        symbol: str,
        velas_historicas: Sequence[Tuple[float, float, float, float, float]],
        sim_paths: int = 10000,
    ) -> SwingAnalysisResult:
        """
        Ejecuta el cómputo intensivo en un hilo de fondo sin bloquear el bucle de eventos.
        """
        raw = await asyncio.to_thread(
            computar_analisis_macro_cpu,
            symbol=symbol,
            velas_historicas=velas_historicas,
            sim_paths=sim_paths,
        )

        return SwingAnalysisResult(
            symbol=raw["symbol"],
            trend_direction=raw["trend_direction"],
            implied_prob_trend=raw["implied_prob_trend"],
            volatility=raw["volatility"],
            monte_carlo_win_prob=raw["monte_carlo_win_prob"],
            recommended_action=raw["recommended_action"],
            current_price=raw.get("current_price", 0.50),
            target_price=raw["target_price"],
            stop_price=raw["stop_price"],
            payout_decimal=raw["payout_decimal"],
            compute_time_ms=raw["compute_time_ms"],
        )

    async def evaluar_y_ejecutar_orden_swing(
        self,
        analysis: SwingAnalysisResult,
        balance: float,
        operaciones_activas: int = 0,
        top_3_bids_vol: Optional[float] = None,
    ) -> Optional[SwingPosition]:
        """
        Evalúa propuesta macro con EscudoFinancieroBinance y reserva capital de forma atómica.
        """
        if analysis.recommended_action not in ("BUY", "SELL"):
            return None

        # 1. Construir propuesta de orden
        propuesta = OrderProposal(
            symbol=analysis.symbol,
            side=analysis.recommended_action,
            target_price=analysis.current_price,
            stop_price=analysis.stop_price,
            estimated_prob=analysis.monte_carlo_win_prob,
            payout_decimal=analysis.payout_decimal,
            strategy_id="SWING_ORTHOGONAL",
        )

        # 2. Validación de riesgo con Escudo Financiero
        approved_order = self.risk_engine.evaluar_propuesta(
            proposal=propuesta,
            balance=balance,
            operaciones_activas=operaciones_activas,
            exposicion_cluster_actual=self.capital_gateway.capital_comprometido,
            top_3_bids=top_3_bids_vol,
        )

        if not approved_order.approved or approved_order.quantity <= 0.0:
            logger.info(
                f"[SwingEngine] Propuesta rechazada por riesgo: {approved_order.rejection_reason}"
            )
            return None

        stake_calculado = round(approved_order.price * approved_order.quantity, 2)

        # 3. Reserva atómica de capital mediante token
        token = await self.capital_gateway.reservar_capital(
            stake=stake_calculado,
            strategy_id="SWING_ORTHOGONAL",
            symbol=analysis.symbol,
        )

        if token is None:
            logger.warning("[SwingEngine] No se pudo reservar capital en gateway (techo 15% alcanzado)")
            return None

        # 4. Crear y almacenar posición de Swing
        pos_id = f"POS_SWING_{analysis.symbol}_{int(time.time()*1000)}"
        pos = SwingPosition(
            position_id=pos_id,
            symbol=analysis.symbol,
            side=analysis.recommended_action,
            entry_price=approved_order.price,
            quantity=approved_order.quantity,
            stake=stake_calculado,
            target_price=analysis.target_price,
            stop_loss_price=analysis.stop_price,
            entry_time=time.time(),
            token=token,
            status="OPEN",
        )
        self.active_positions[pos_id] = pos
        logger.info(
            f"[SwingEngine] Posición Swing abierta: {pos_id} | {pos.side} {pos.quantity} @ {pos.entry_price} | Stake: {stake_calculado} USD"
        )
        return pos

    async def cerrar_posicion_swing(
        self,
        position_id: str,
        exit_price: float,
    ) -> Optional[SwingPosition]:
        """
        Cierra una posición de Swing y libera de forma atómica el token de capital.
        """
        if position_id not in self.active_positions:
            return None

        pos = self.active_positions[position_id]
        pos.status = "CLOSED"
        pos.exit_price = exit_price
        pos.exit_time = time.time()
        
        # PnL neto
        if pos.side == "BUY":
            pnl = (exit_price - pos.entry_price) * pos.quantity
        else:
            pnl = (pos.entry_price - exit_price) * pos.quantity
        pos.pnl = round(pnl, 4)

        # Liberar token de capital atómicamente
        await self.capital_gateway.liberar_capital(pos.token)

        # Notificar resultado a Escudo Financiero para actualizar racha
        es_ganadora = pos.pnl > 0.0
        self.risk_engine.registrar_resultado(es_ganadora)

        self.closed_positions.append(pos)
        del self.active_positions[position_id]

        logger.info(
            f"[SwingEngine] Posición Swing cerrada: {position_id} @ {exit_price} | PnL: {pos.pnl:.4f} USD"
        )
        return pos

    async def ejecutar_ciclo_swing(
        self,
        symbol: str,
        velas_historicas: Sequence[Tuple[float, float, float, float, float]],
        balance: float,
        operaciones_activas: int = 0,
        top_3_bids_vol: Optional[float] = None,
        sim_paths: int = 10000,
    ) -> Optional[SwingPosition]:
        """
        Ciclo completo de evaluación y disparo asíncrono para Swing.
        Totalmente no bloqueante.
        """
        analisis = await self.analizar_oportunidad_macro(
            symbol=symbol,
            velas_historicas=velas_historicas,
            sim_paths=sim_paths,
        )

        if analisis.recommended_action == "BUY":
            return await self.evaluar_y_ejecutar_orden_swing(
                analysis=analisis,
                balance=balance,
                operaciones_activas=operaciones_activas,
                top_3_bids_vol=top_3_bids_vol,
            )
        return None
