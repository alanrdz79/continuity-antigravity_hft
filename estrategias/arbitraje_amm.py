# -*- coding: utf-8 -*-
"""
estrategias.arbitraje_amm
=========================
Estrategia V: Dynamic Cross-Venue Arbitrage & AMM Bonding-Curve Sniping.

Módulo de micro-arbitraje y captura de ineficiencias de paridad binaria
para Binance Predict y AMMs de contratos deportivos (YES / NO).

Pilares Técnicos:
1. Paridad Binaria Determinista (Dual-Purchase Arbitrage):
   - Si Best Ask(YES) + Best Ask(NO) < 1.00 - comisiones_totales,
     ejecuta compra dual simultánea atómica bloqueando ganancia libre de riesgo
     garantizada en la redención final (1.00 - sum(Asks) - fees > 0).
2. Arbitraje de Desviación de Curva frente a P_fair externa:
   - Compara probabilidades implícitas en libro (YES/NO) frente a precio justo / benchmark (P_fair).
   - Si |implied - P_fair| > umbral (e.g. 3-5%), adquiere el contrato infravalorado
     y programa salida tipo scalp en el rebote dentro de un horizonte de 2 a 15 segundos.
3. Integración Estricta de Riesgo y Latencia:
   - Límite de exposición de clúster estricto del 15% coordinado vía AsyncCapitalGateway
     y/o EscudoFinancieroBinance con tokens atómicos de capital.
   - Guardián de Latencia Rígido (Hard Latency Timeout <= 2.5s): aborta y cancela inmediatamente
     cualquier ejecución en vuelo que supere los 2.5 segundos.
   - Bloqueo Inmediato por MarketStatus == 'SUSPENDED' (Regla de Oro 2):
     cancela y bloquea nuevas operaciones instantáneamente si el mercado se suspende.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import logging
import math
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import uuid

from continuitis.microestructura_binance import OrderBookSnapshot
from continuitis.riesgo_binance import EscudoFinancieroBinance
from estrategias.swing_engine import AsyncCapitalGateway, CapitalReservationToken

logger = logging.getLogger("CONTINUITY.ArbitrajeAMM")


# ==============================================================================
# 1. ENUMS Y ESTRUCTURAS DE DATOS DE ARBITRAJE
# ==============================================================================

class ArbitrageOpportunityType(str, Enum):
    """Tipo de oportunidad de arbitraje detectada."""
    BINARY_PARITY = "BINARY_PARITY"              # Paridad determinista YES + NO < 1.00 - fees
    CURVE_DEVIATION_YES = "CURVE_DEVIATION_YES"  # Contrato YES infravalorado frente a P_fair
    CURVE_DEVIATION_NO = "CURVE_DEVIATION_NO"    # Contrato NO infravalorado frente a P_fair


@dataclass(frozen=True)
class ArbitrageSignal:
    """
    Señal enriquecida de arbitraje que cuantifica la ineficiencia detectada.
    """
    signal_id: str
    event_id: str
    opportunity_type: ArbitrageOpportunityType
    symbol_yes: str
    symbol_no: str
    best_ask_yes: float
    best_ask_no: float
    best_bid_yes: Optional[float] = None
    best_bid_no: Optional[float] = None
    sum_asks: float = 0.0
    fees_total: float = 0.0
    net_edge: float = 0.0
    p_fair: Optional[float] = None
    p_implied: Optional[float] = None
    deviation: float = 0.0
    target_contract: str = ""                    # "BOTH", "YES", o "NO"
    target_price: float = 0.0
    max_volume: float = 0.0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_risk_free_parity(self) -> bool:
        return self.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY


@dataclass
class ScalpPosition:
    """
    Registro y seguimiento del ciclo de vida de una posición de arbitraje o scalp.
    """
    position_id: str
    signal_id: str
    event_id: str
    opportunity_type: ArbitrageOpportunityType
    contract_side: str                           # "DUAL", "YES", o "NO"
    symbols: Tuple[str, ...]
    entry_prices: Dict[str, float]
    quantities: Dict[str, float]
    total_stake: float
    entry_timestamp: float
    scalp_horizon_s: float                       # Horizonte de salida (2.0 a 15.0 segundos)
    target_exit_price: Optional[float] = None
    reservation_token: Optional[CapitalReservationToken] = None
    status: str = "OPEN"                         # "OPEN", "CLOSED", "ABORTED_LATENCY", "LOCKED_SUSPENDED"
    exit_timestamp: Optional[float] = None
    exit_prices: Dict[str, float] = field(default_factory=dict)
    realized_pnl: float = 0.0
    exit_reason: str = ""                        # "REDEMPTION_LOCKED", "SCALP_BOUNCE", "SCALP_TIMEOUT", "LATENCY_ABORT", "MARKET_SUSPENDED"

    @property
    def is_open(self) -> bool:
        return self.status == "OPEN"

    @property
    def is_closed(self) -> bool:
        return self.status in ("CLOSED", "ABORTED_LATENCY", "LOCKED_SUSPENDED")


@dataclass
class ArbitrageConfig:
    """Configuración paramétrica para la Estrategia V de Arbitraje AMM."""
    fee_rate: float = 0.0010                     # 0.10% Binance Spot regular
    bnb_discount_factor: float = 0.75            # 25% descuento con BNB -> 0.075% efectivo
    use_bnb_discount: bool = True
    deviation_threshold: float = 0.03            # Umbral mínimo de desviación P_fair (3%)
    min_parity_edge: float = 0.001               # Margen neto mínimo para disparar paridad (0.1%)
    scalp_horizon_min_s: float = 2.0             # Mínimo tiempo de scalp (2.0 s)
    scalp_horizon_max_s: float = 15.0            # Máximo tiempo de scalp (15.0 s)
    max_execution_latency_s: float = 2.5         # Límite rígido de latencia de ejecución (2.5 s)
    max_cluster_exposure: float = 0.15           # Techo de clúster estricto (15% del bankroll)
    default_stake_per_trade: float = 20.0        # Stake nominal base por operación
    max_stake_per_trade: float = 150.0           # Stake máximo permitido por trade
    min_volume: float = 0.001                    # Volumen mínimo ejecutable


# ==============================================================================
# 2. MOTOR PRINCIPAL: EstrategiaVArbitrajeAMM
# ==============================================================================

class EstrategiaVArbitrajeAMM:
    """
    Estrategia V: Arbitraje dinámico cross-venue y sniping de curvas AMM.
    
    Implementa:
    - Regla 1: Desviación de curva frente a probabilidad justa externa P_fair.
    - Regla 2: Paridad binaria determinista (Ask(YES) + Ask(NO) < 1.00 - fees).
    - Regla 3: Techo de clúster 15%, guardián de latencia 2.5s y congelamiento inmediato
      si MarketStatus == 'SUSPENDED'.
    """

    def __init__(
        self,
        config: Optional[ArbitrageConfig] = None,
        capital_gateway: Optional[AsyncCapitalGateway] = None,
        escudo_riesgo: Optional[EscudoFinancieroBinance] = None,
        connector: Optional[Any] = None,
        total_capital: float = 1000.0,
    ):
        self.config = config or ArbitrageConfig()
        self.capital_gateway = capital_gateway
        self.escudo_riesgo = escudo_riesgo
        self.connector = connector
        self.total_capital = max(0.0, float(total_capital))
        
        # Estado interno de seguridad y posiciones
        self.mercado_suspendido: bool = False
        self.active_positions: Dict[str, ScalpPosition] = {}
        self.completed_positions: List[ScalpPosition] = []
        self.total_profit_locked: float = 0.0
        self.total_redemption_profit_locked: float = 0.0
        self.total_aborted_trades: int = 0
        self.total_successful_trades: int = 0
        self._lock = asyncio.Lock()

    # --------------------------------------------------------------------------
    # Propiedades de comisiones y límites
    # --------------------------------------------------------------------------

    @property
    def effective_fee_rate(self) -> float:
        """Tasa neta de comisión por operación."""
        if self.config.use_bnb_discount:
            return round(self.config.fee_rate * self.config.bnb_discount_factor, 6)
        return round(self.config.fee_rate, 6)

    @property
    def cluster_cap_amount(self) -> float:
        """Monto máximo en USD asignable a este clúster (15% del capital total)."""
        return round(self.total_capital * self.config.max_cluster_exposure, 4)

    @property
    def current_cluster_exposure(self) -> float:
        """Capital actualmente comprometido en posiciones abiertas del clúster."""
        return round(
            sum(pos.total_stake for pos in self.active_positions.values() if pos.is_open),
            4,
        )

    @property
    def cluster_available_amount(self) -> float:
        """Capital libre restante en el clúster antes de alcanzar el techo del 15%."""
        return max(0.0, round(self.cluster_cap_amount - self.current_cluster_exposure, 4))

    def calcular_comisiones(self, precio_total: float) -> float:
        """Calcula el costo monetario de comisión sobre un valor transaccionado."""
        return round(precio_total * self.effective_fee_rate, 6)

    # --------------------------------------------------------------------------
    # Control de Estado de Mercado (Regla de Oro 2)
    # --------------------------------------------------------------------------

    def actualizar_estado_mercado(self, status: str) -> None:
        """
        Actualiza el interruptor global de estado de mercado.
        Si status == 'SUSPENDED', se activa el bloqueo inmediato.
        """
        self.mercado_suspendido = (status.strip().upper() == "SUSPENDED")
        if self.mercado_suspendido:
            logger.warning("[ArbitrajeAMM] Mercado marcado como SUSPENDED. Operaciones bloqueadas.")

    def verificar_estado_mercado(
        self,
        snapshot_yes: OrderBookSnapshot,
        snapshot_no: OrderBookSnapshot,
    ) -> Tuple[bool, str]:
        """
        Verifica si los libros están activos y son válidos para operar.
        Bloquea de inmediato si cualquiera se encuentra SUSPENDED.
        """
        if self.mercado_suspendido:
            return False, "MERCADO_SUSPENDIDO_ESTRATEGIA"

        status_yes = getattr(snapshot_yes, "market_status", "ACTIVE")
        status_no = getattr(snapshot_no, "market_status", "ACTIVE")

        if str(status_yes).upper() == "SUSPENDED":
            return False, "MERCADO_SUSPENDIDO_YES"
        if str(status_no).upper() == "SUSPENDED":
            return False, "MERCADO_SUSPENDIDO_NO"

        if not getattr(snapshot_yes, "is_valid", bool(snapshot_yes.bids and snapshot_yes.asks)):
            return False, "LIBRO_INVALIDO_YES"
        if not getattr(snapshot_no, "is_valid", bool(snapshot_no.bids and snapshot_no.asks)):
            return False, "LIBRO_INVALIDO_NO"

        return True, "ACTIVO"

    # --------------------------------------------------------------------------
    # Regla 2: Detección de Paridad Binaria Determinista
    # --------------------------------------------------------------------------

    def detectar_paridad_binaria(
        self,
        snapshot_yes: OrderBookSnapshot,
        snapshot_no: OrderBookSnapshot,
        event_id: str = "",
    ) -> Optional[ArbitrageSignal]:
        """
        Evalúa la condición matemática de arbitraje de paridad binaria:
            Best Ask(YES) + Best Ask(NO) < 1.00 - comisiones_totales

        Si se cumple, la compra dual simultánea garantiza un valor de redención
        exacto de 1.00 USDT, produciendo una ganancia neta libre de riesgo:
            Beneficio = 1.00 - sum(Asks) - fees > 0.
        """
        valido, motivo = self.verificar_estado_mercado(snapshot_yes, snapshot_no)
        if not valido:
            logger.debug(f"[ArbitrajeAMM] Paridad rechazada por estado de mercado: {motivo}")
            return None

        ask_yes = snapshot_yes.best_ask
        ask_no = snapshot_no.best_ask

        # Validar existencia de posturas de venta
        if ask_yes is None or ask_no is None:
            return None
        if ask_yes <= 0.0 or ask_no <= 0.0:
            return None

        # Validar volúmenes disponibles en el primer nivel
        if not snapshot_yes.asks or not snapshot_no.asks:
            return None

        vol_yes = float(snapshot_yes.asks[0][1])
        vol_no = float(snapshot_no.asks[0][1])
        max_vol = min(vol_yes, vol_no)
        if max_vol <= 0.0:
            return None

        sum_asks = round(ask_yes + ask_no, 6)
        fees_total = self.calcular_comisiones(sum_asks)
        costo_total = round(sum_asks + fees_total, 6)

        # Regla estricta: Costo total debe ser estrictamente menor a 1.00
        net_edge = round(1.00 - costo_total, 6)
        if net_edge <= 0.0 or net_edge < self.config.min_parity_edge:
            return None

        bid_yes = snapshot_yes.best_bid
        bid_no = snapshot_no.best_bid
        eid = event_id or snapshot_yes.symbol.split("_")[0]
        sig_id = f"SIG_PARITY_{uuid.uuid4().hex[:8]}_{int(time.time()*1000)}"

        signal = ArbitrageSignal(
            signal_id=sig_id,
            event_id=eid,
            opportunity_type=ArbitrageOpportunityType.BINARY_PARITY,
            symbol_yes=snapshot_yes.symbol,
            symbol_no=snapshot_no.symbol,
            best_ask_yes=ask_yes,
            best_ask_no=ask_no,
            best_bid_yes=bid_yes,
            best_bid_no=bid_no,
            sum_asks=sum_asks,
            fees_total=fees_total,
            net_edge=net_edge,
            target_contract="BOTH",
            target_price=sum_asks,
            max_volume=round(max_vol, 4),
            timestamp=time.time(),
        )

        logger.info(
            f"[ArbitrajeAMM] Paridad binaria detectada en {eid}: "
            f"Ask(YES)={ask_yes:.4f} + Ask(NO)={ask_no:.4f} = {sum_asks:.4f} | "
            f"Edge={net_edge:.4f} | Vol={max_vol:.2f}"
        )
        return signal

    # --------------------------------------------------------------------------
    # Regla 1: Desviación de Curva frente a P_fair
    # --------------------------------------------------------------------------

    def detectar_desviacion_curva(
        self,
        snapshot_yes: OrderBookSnapshot,
        snapshot_no: OrderBookSnapshot,
        p_fair: float,
        event_id: str = "",
    ) -> Optional[ArbitrageSignal]:
        """
        Compara las probabilidades implícitas de mercado contra el precio
        justo externo P_fair (para YES) y (1 - P_fair) (para NO).

        Si |implied - P_fair| > umbral:
        - Si Ask(YES) < P_fair - umbral: YES está infravalorado -> Comprar YES.
        - Si Ask(NO) < (1.0 - P_fair) - umbral: NO está infravalorado -> Comprar NO.
        Programa salida scalp entre 2 y 15 segundos al rebote hacia P_fair.
        """
        valido, motivo = self.verificar_estado_mercado(snapshot_yes, snapshot_no)
        if not valido:
            return None

        if not (0.0 < p_fair < 1.0):
            return None

        ask_yes = snapshot_yes.best_ask
        ask_no = snapshot_no.best_ask
        if ask_yes is None or ask_no is None or ask_yes <= 0.0 or ask_no <= 0.0:
            return None

        if not snapshot_yes.asks or not snapshot_no.asks:
            return None

        vol_yes = float(snapshot_yes.asks[0][1])
        vol_no = float(snapshot_no.asks[0][1])

        p_fair_yes = float(p_fair)
        p_fair_no = round(1.0 - p_fair_yes, 6)
        umbral = self.config.deviation_threshold

        eid = event_id or snapshot_yes.symbol.split("_")[0]
        sig_id = f"SIG_CURVE_{uuid.uuid4().hex[:8]}_{int(time.time()*1000)}"

        # 1. Evaluar si YES está infravalorado
        dev_yes = round(p_fair_yes - ask_yes, 6)
        fee_yes = self.calcular_comisiones(ask_yes)
        net_edge_yes = round(dev_yes - fee_yes, 6)

        if dev_yes >= umbral and net_edge_yes > 0.0 and vol_yes > 0.0:
            return ArbitrageSignal(
                signal_id=sig_id,
                event_id=eid,
                opportunity_type=ArbitrageOpportunityType.CURVE_DEVIATION_YES,
                symbol_yes=snapshot_yes.symbol,
                symbol_no=snapshot_no.symbol,
                best_ask_yes=ask_yes,
                best_ask_no=ask_no,
                best_bid_yes=snapshot_yes.best_bid,
                best_bid_no=snapshot_no.best_bid,
                fees_total=fee_yes,
                net_edge=net_edge_yes,
                p_fair=p_fair_yes,
                p_implied=ask_yes,
                deviation=dev_yes,
                target_contract="YES",
                target_price=ask_yes,
                max_volume=round(vol_yes, 4),
                timestamp=time.time(),
            )

        # 2. Evaluar si NO está infravalorado
        dev_no = round(p_fair_no - ask_no, 6)
        fee_no = self.calcular_comisiones(ask_no)
        net_edge_no = round(dev_no - fee_no, 6)

        if dev_no >= umbral and net_edge_no > 0.0 and vol_no > 0.0:
            return ArbitrageSignal(
                signal_id=sig_id,
                event_id=eid,
                opportunity_type=ArbitrageOpportunityType.CURVE_DEVIATION_NO,
                symbol_yes=snapshot_yes.symbol,
                symbol_no=snapshot_no.symbol,
                best_ask_yes=ask_yes,
                best_ask_no=ask_no,
                best_bid_yes=snapshot_yes.best_bid,
                best_bid_no=snapshot_no.best_bid,
                fees_total=fee_no,
                net_edge=net_edge_no,
                p_fair=p_fair_no,
                p_implied=ask_no,
                deviation=dev_no,
                target_contract="NO",
                target_price=ask_no,
                max_volume=round(vol_no, 4),
                timestamp=time.time(),
            )

        return None

    # --------------------------------------------------------------------------
    # Evaluación Compuesta de Oportunidades
    # --------------------------------------------------------------------------

    def evaluar_oportunidades(
        self,
        snapshot_yes: OrderBookSnapshot,
        snapshot_no: OrderBookSnapshot,
        p_fair: Optional[float] = None,
        event_id: str = "",
    ) -> List[ArbitrageSignal]:
        """
        Evalúa concurrentemente paridad determinista y desviación de curva.
        Prioriza la paridad determinista (riesgo cero de redención).
        """
        senales: List[ArbitrageSignal] = []

        # Prioridad 1: Paridad binaria dual
        sig_paridad = self.detectar_paridad_binaria(snapshot_yes, snapshot_no, event_id=event_id)
        if sig_paridad is not None:
            senales.append(sig_paridad)
            return senales

        # Prioridad 2: Desviación de curva frente a P_fair
        if p_fair is not None:
            sig_curva = self.detectar_desviacion_curva(snapshot_yes, snapshot_no, p_fair, event_id=event_id)
            if sig_curva is not None:
                senales.append(sig_curva)

        return senales

    # --------------------------------------------------------------------------
    # Regla 3: Gestión de Riesgo, Clúster 15% y Guardián de Latencia
    # --------------------------------------------------------------------------

    async def _reservar_capital_cluster(
        self,
        stake: float,
        strategy_id: str = "ARBITRAJE_AMM",
        symbol: str = "PRED_AMM",
    ) -> Tuple[bool, float, Optional[CapitalReservationToken], str]:
        """
        Verifica y reserva atómicamente capital respetando estrictamente el techo del 15%.
        Coordina con AsyncCapitalGateway si está disponible o con el estado interno.
        """
        if stake <= 0.0:
            return False, 0.0, None, "STAKE_INVALIDO"

        # 1. Si existe AsyncCapitalGateway, usar su reserva atómica basada en token
        if self.capital_gateway is not None:
            token = await self.capital_gateway.reservar_capital(
                stake=stake,
                strategy_id=strategy_id,
                symbol=symbol,
            )
            if token is None:
                return False, 0.0, None, "TECHO_CLUSTER_15_EXCEDIDO_GATEWAY"
            return True, token.stake, token, "APROBADO_GATEWAY"

        # 2. Validación interna respecto al capital total y techo del 15%
        espacio = self.cluster_available_amount
        if espacio <= 0.0:
            return False, 0.0, None, "TECHO_CLUSTER_15_EXCEDIDO"

        allocated = min(stake, espacio)
        if allocated <= 0.0:
            return False, 0.0, None, "ESPACIO_INSUFICIENTE_CLUSTER"

        token_id = f"TOK_AMM_{uuid.uuid4().hex[:8]}_{int(time.time()*1000)}"
        token = CapitalReservationToken(
            token_id=token_id,
            strategy_id=strategy_id,
            symbol=symbol,
            stake=round(allocated, 4),
            reserved_at=time.time(),
            is_released=False,
        )
        return True, round(allocated, 4), token, "APROBADO_LOCAL"

    async def _liberar_capital_cluster(self, token: Optional[CapitalReservationToken]) -> bool:
        """Libera el capital reservado garantizando que no haya memory leaks."""
        if token is None or token.is_released:
            return False

        if self.capital_gateway is not None:
            return await self.capital_gateway.liberar_capital(token)

        token.is_released = True
        return True

    # --------------------------------------------------------------------------
    # Ejecución Asíncrona: Arbitraje de Paridad Binaria
    # --------------------------------------------------------------------------

    async def ejecutar_arbitraje_paridad(
        self,
        signal: ArbitrageSignal,
        requested_stake: Optional[float] = None,
        mock_delay_s: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Ejecuta la compra dual atómica simultánea para bloquear el arbitraje de paridad.
        Aplica:
        - Bloqueo inmediato si MarketStatus == 'SUSPENDED'.
        - Verificación estricta del techo del 15% del clúster.
        - Guardián de Latencia: aborta si la ejecución supera 2.5 segundos.
        """
        async with self._lock:
            # 1. Comprobación de seguridad de mercado
            if self.mercado_suspendido:
                return {
                    "success": False,
                    "reason": "MERCADO_SUSPENDIDO",
                    "position_id": None,
                }

            start_time = time.time()
            stake_solicitado = requested_stake or self.config.default_stake_per_trade
            sum_asks = signal.sum_asks

            # Acotar al volumen máximo antes de reservar para mantener coherencia contable
            max_stake_book = round(signal.max_volume * sum_asks, 4)
            stake_a_solicitar = min(stake_solicitado, max_stake_book) if max_stake_book > 0 else stake_solicitado

            # 2. Reserva atómica en el clúster (15%)
            aprobado, stake_asignado, token, motivo_riesgo = await self._reservar_capital_cluster(
                stake=stake_a_solicitar,
                strategy_id="ARBITRAJE_PARIDAD",
                symbol=f"{signal.symbol_yes}+{signal.symbol_no}",
            )
            if not aprobado or token is None:
                logger.warning(f"[ArbitrajeAMM] Paridad rechazada por riesgo: {motivo_riesgo}")
                return {
                    "success": False,
                    "reason": motivo_riesgo,
                    "position_id": None,
                }

            # 3. Guardián de Latencia Rígido (<= 2.5s)
            # Simular o esperar la latencia de red si aplica
            if mock_delay_s > 0.0:
                await asyncio.sleep(mock_delay_s)

            elapsed_latency = time.time() - start_time
            if elapsed_latency > self.config.max_execution_latency_s:
                await self._liberar_capital_cluster(token)
                self.total_aborted_trades += 1
                logger.error(
                    f"[ArbitrajeAMM] LatencyGuard ABORT: {elapsed_latency:.3f}s > "
                    f"{self.config.max_execution_latency_s}s límite."
                )
                return {
                    "success": False,
                    "reason": "LATENCY_ABORT",
                    "latency_s": round(elapsed_latency, 4),
                    "position_id": None,
                }

            # 4. Cálculo de asignación y cantidades duales
            qty_pair = min(signal.max_volume, round(stake_asignado / sum_asks, 4))
            costo_base = round(qty_pair * sum_asks, 4)

            # Si el costo base es menor que lo reservado, liberar el exceso atómicamente
            exceso = round(token.stake - costo_base, 4)
            if exceso > 0.0:
                if self.capital_gateway is not None:
                    async with self.capital_gateway.lock:
                        self.capital_gateway.capital_comprometido = max(
                            0.0, round(self.capital_gateway.capital_comprometido - exceso, 4)
                        )
                token.stake = costo_base
                stake_asignado = costo_base

            payout_garantizado = round(qty_pair * 1.00, 4)
            comision_total = round(self.calcular_comisiones(costo_base), 4)
            costo_neto = round(costo_base + comision_total, 4)
            ganancia_libre_riesgo = round(payout_garantizado - costo_neto, 4)

            pos_id = f"POS_PARITY_{uuid.uuid4().hex[:8]}_{int(time.time()*1000)}"
            posicion = ScalpPosition(
                position_id=pos_id,
                signal_id=signal.signal_id,
                event_id=signal.event_id,
                opportunity_type=ArbitrageOpportunityType.BINARY_PARITY,
                contract_side="DUAL",
                symbols=(signal.symbol_yes, signal.symbol_no),
                entry_prices={
                    signal.symbol_yes: signal.best_ask_yes,
                    signal.symbol_no: signal.best_ask_no,
                },
                quantities={
                    signal.symbol_yes: qty_pair,
                    signal.symbol_no: qty_pair,
                },
                total_stake=stake_asignado,
                entry_timestamp=time.time(),
                scalp_horizon_s=0.0,  # Retención hasta redención garantizada
                target_exit_price=1.00,
                reservation_token=token,
                status="OPEN",
                realized_pnl=ganancia_libre_riesgo,
                exit_reason="REDEMPTION_LOCKED",
            )

            self.active_positions[pos_id] = posicion
            self.total_profit_locked = round(self.total_profit_locked + ganancia_libre_riesgo, 4)
            self.total_redemption_profit_locked = round(
                self.total_redemption_profit_locked + ganancia_libre_riesgo, 4
            )
            self.total_successful_trades += 1

            logger.info(
                f"[ArbitrajeAMM] Paridad ejecutada con éxito | PosID={pos_id} | "
                f"Stake={stake_asignado:.2f} USD | Ganancia asegurada={ganancia_libre_riesgo:.4f} USD | "
                f"Latencia={elapsed_latency*1000:.1f}ms"
            )

            return {
                "success": True,
                "position_id": pos_id,
                "stake": stake_asignado,
                "quantity": qty_pair,
                "profit_locked": ganancia_libre_riesgo,
                "net_edge": signal.net_edge,
                "latency_s": round(elapsed_latency, 4),
                "reason": "EJECUTADO_EXITOSO",
            }

    # --------------------------------------------------------------------------
    # Ejecución Asíncrona: Arbitraje de Desviación de Curva con Salida Scalp
    # --------------------------------------------------------------------------

    async def ejecutar_arbitraje_desviacion(
        self,
        signal: ArbitrageSignal,
        requested_stake: Optional[float] = None,
        mock_delay_s: float = 0.0,
        scalp_horizon_s: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Adquiere el contrato infravalorado y programa salida tipo scalp en 2 a 15s.
        Aplica:
        - Techo del 15% del clúster.
        - Guardián de latencia <= 2.5s.
        - Programación de ventana de scalp [2.0, 15.0] segundos.
        """
        async with self._lock:
            if self.mercado_suspendido:
                return {
                    "success": False,
                    "reason": "MERCADO_SUSPENDIDO",
                    "position_id": None,
                }

            start_time = time.time()
            stake_solicitado = requested_stake or self.config.default_stake_per_trade
            target_symbol = signal.symbol_yes if signal.target_contract == "YES" else signal.symbol_no
            entry_price = signal.target_price

            # Acotar al volumen máximo antes de reservar para mantener coherencia contable
            max_stake_book = round(signal.max_volume * entry_price, 4)
            stake_a_solicitar = min(stake_solicitado, max_stake_book) if max_stake_book > 0 else stake_solicitado

            # 1. Reserva atómica de capital en clúster (15%)
            aprobado, stake_asignado, token, motivo_riesgo = await self._reservar_capital_cluster(
                stake=stake_a_solicitar,
                strategy_id="ARBITRAJE_CURVA",
                symbol=target_symbol,
            )
            if not aprobado or token is None:
                return {
                    "success": False,
                    "reason": motivo_riesgo,
                    "position_id": None,
                }

            # 2. Guardián de Latencia Rígido (<= 2.5s)
            if mock_delay_s > 0.0:
                await asyncio.sleep(mock_delay_s)

            elapsed_latency = time.time() - start_time
            if elapsed_latency > self.config.max_execution_latency_s:
                await self._liberar_capital_cluster(token)
                self.total_aborted_trades += 1
                return {
                    "success": False,
                    "reason": "LATENCY_ABORT",
                    "latency_s": round(elapsed_latency, 4),
                    "position_id": None,
                }

            # 3. Horizon de scalp estricto entre 2 y 15 segundos
            horizon = scalp_horizon_s or 5.0
            horizon = max(
                self.config.scalp_horizon_min_s,
                min(self.config.scalp_horizon_max_s, float(horizon)),
            )

            qty = min(signal.max_volume, round(stake_asignado / entry_price, 4))
            costo_base = round(qty * entry_price, 4)

            # Si el costo base es menor que lo reservado, liberar el exceso atómicamente
            exceso = round(token.stake - costo_base, 4)
            if exceso > 0.0:
                if self.capital_gateway is not None:
                    async with self.capital_gateway.lock:
                        self.capital_gateway.capital_comprometido = max(
                            0.0, round(self.capital_gateway.capital_comprometido - exceso, 4)
                        )
                token.stake = costo_base
                stake_asignado = costo_base

            # Precio objetivo de salida en rebote hacia P_fair
            p_fair_target = signal.p_fair or (entry_price + signal.deviation)
            target_exit = round(entry_price + (p_fair_target - entry_price) * 0.70, 4)

            pos_id = f"POS_CURVE_{uuid.uuid4().hex[:8]}_{int(time.time()*1000)}"
            posicion = ScalpPosition(
                position_id=pos_id,
                signal_id=signal.signal_id,
                event_id=signal.event_id,
                opportunity_type=signal.opportunity_type,
                contract_side=signal.target_contract,
                symbols=(target_symbol,),
                entry_prices={target_symbol: entry_price},
                quantities={target_symbol: qty},
                total_stake=stake_asignado,
                entry_timestamp=time.time(),
                scalp_horizon_s=horizon,
                target_exit_price=target_exit,
                reservation_token=token,
                status="OPEN",
            )

            self.active_positions[pos_id] = posicion
            self.total_successful_trades += 1

            logger.info(
                f"[ArbitrajeAMM] Entrada de curva en {target_symbol} | "
                f"Entry={entry_price:.4f} | TargetExit={target_exit:.4f} | "
                f"Horizonte={horizon:.1f}s | Stake={stake_asignado:.2f} USD"
            )

            return {
                "success": True,
                "position_id": pos_id,
                "symbol": target_symbol,
                "entry_price": entry_price,
                "target_exit_price": target_exit,
                "stake": stake_asignado,
                "quantity": qty,
                "scalp_horizon_s": horizon,
                "latency_s": round(elapsed_latency, 4),
                "reason": "EJECUTADO_EXITOSO",
            }

    # --------------------------------------------------------------------------
    # Gestión del Ciclo de Vida de Posiciones Scalp (Salida a 2-15s o Rebote)
    # --------------------------------------------------------------------------

    async def gestionar_posiciones_scalp(
        self,
        current_snapshots: Dict[str, OrderBookSnapshot],
        now: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Monitorea posiciones abiertas y ejecuta salidas de scalp:
        1. Si MarketStatus == 'SUSPENDED': Bloqueo y liquidación de emergencia inmediata.
        2. Si precio de mercado toca o supera target_exit_price: Toma de beneficios en rebote.
        3. Si tiempo transcurrido >= scalp_horizon_s (2 a 15 s): Salida por expiración de tiempo.
        """
        async with self._lock:
            current_time = now if now is not None else time.time()
            reportes_cierre: List[Dict[str, Any]] = []

            for pos_id, pos in list(self.active_positions.items()):
                if not pos.is_open:
                    continue

                # Caso Paridad Binaria: Se mantiene abierta hasta redención final o cierre explícito
                if pos.opportunity_type == ArbitrageOpportunityType.BINARY_PARITY:
                    continue

                target_symbol = pos.symbols[0]
                snapshot = current_snapshots.get(target_symbol)

                # 1. Regla de Oro 2: Mercado suspendido durante la posición
                if self.mercado_suspendido or (
                    snapshot and str(getattr(snapshot, "market_status", "ACTIVE")).upper() == "SUSPENDED"
                ):
                    pos.status = "LOCKED_SUSPENDED"
                    pos.exit_timestamp = current_time
                    pos.exit_reason = "MARKET_SUSPENDED"
                    await self._liberar_capital_cluster(pos.reservation_token)
                    reportes_cierre.append({
                        "position_id": pos_id,
                        "status": pos.status,
                        "reason": pos.exit_reason,
                        "pnl": pos.realized_pnl,
                    })
                    continue

                if snapshot is None or not snapshot.bids:
                    continue

                best_bid = snapshot.best_bid or 0.0
                elapsed_s = current_time - pos.entry_timestamp
                qty = pos.quantities.get(target_symbol, 0.0)
                entry_px = pos.entry_prices.get(target_symbol, 0.0)

                debe_cerrar = False
                motivo_cierre = ""

                # 2. Salida por Rebote (Take Profit)
                if pos.target_exit_price and best_bid >= pos.target_exit_price:
                    debe_cerrar = True
                    motivo_cierre = "SCALP_BOUNCE"

                # 3. Salida por Expiración de Horizonte de Scalp (2 a 15 segundos)
                elif elapsed_s >= pos.scalp_horizon_s:
                    debe_cerrar = True
                    motivo_cierre = "SCALP_TIMEOUT"

                if debe_cerrar:
                    exit_price = best_bid
                    pnl_bruto = (exit_price - entry_px) * qty
                    fees = self.calcular_comisiones(exit_price * qty)
                    pnl_neto = round(pnl_bruto - fees, 4)

                    pos.status = "CLOSED"
                    pos.exit_timestamp = current_time
                    pos.exit_prices = {target_symbol: exit_price}
                    pos.realized_pnl = pnl_neto
                    pos.exit_reason = motivo_cierre

                    await self._liberar_capital_cluster(pos.reservation_token)
                    self.total_profit_locked = round(self.total_profit_locked + pnl_neto, 4)
                    self.completed_positions.append(pos)
                    del self.active_positions[pos_id]

                    logger.info(
                        f"[ArbitrajeAMM] Posición {pos_id} cerrada ({motivo_cierre}) | "
                        f"PnL={pnl_neto:.4f} USD | Tiempo={elapsed_s:.2f}s | "
                        f"ExitPx={exit_price:.4f}"
                    )

                    reportes_cierre.append({
                        "position_id": pos_id,
                        "status": pos.status,
                        "reason": motivo_cierre,
                        "pnl": pnl_neto,
                        "exit_price": exit_price,
                        "elapsed_s": round(elapsed_s, 2),
                    })

            return reportes_cierre

    # --------------------------------------------------------------------------
    # Cancelación / Aborto Forzoso por Disyuntor
    # --------------------------------------------------------------------------

    async def abortar_todas_las_posiciones(self, motivo: str = "EMERGENCIA") -> int:
        """Cancela y libera de inmediato todas las reservas activas del clúster."""
        async with self._lock:
            cerradas = 0
            for pos_id, pos in list(self.active_positions.items()):
                if pos.is_open:
                    pos.status = "ABORTED_LATENCY" if "LATENCY" in motivo.upper() else "LOCKED_SUSPENDED"
                    pos.exit_reason = motivo
                    pos.exit_timestamp = time.time()
                    await self._liberar_capital_cluster(pos.reservation_token)
                    self.completed_positions.append(pos)
                    cerradas += 1
            self.active_positions.clear()
            return cerradas
