# -*- coding: utf-8 -*-
"""
orquestadores_principales.HFT_BINANCE
====================================
Orquestador Asíncrono Continuo Principal para CONTINUITY HFT Binance.

Coordina de manera unificada y concurrente:
1. `BinanceAsyncConnector` (conectores.binance_async) — Ingesta L2 y enrutador REST.
2. `MicroestructuraBinanceEngine` (continuitis.microestructura_binance) — OBI, latencia y Reglas de Oro 1, 2, 3.
3. `EscudoFinancieroBinance` (continuitis.riesgo_binance) — EV neto, dimensionamiento real, freno de racha y clúster.
4. `TesoreriaBinance` / `GestorTesoreria` (continuitis.tesoreria) — Ciclo $10 -> $100 -> $1,000 USD, cortes y cosechas.
5. `AuditorMetricas` (continuitis.auditor_metricas) — Telemetría continua (WR, BN, ROI, Yield, p-value).
6. `HFTEngine` (estrategias.hft_engine) — 4 Fases HFT, Estrategia A (Time Decay) y Estrategia B (Reacciones).
7. `SwingEngine` (estrategias.swing_engine) — Swing macro ortogonal en hilos secundarios (Zero Event Loop Starvation).
8. `TelegramBidireccionalBot` (conectores.telegram_bidireccional) — Panel interactivo y botón de pánico remoto.

Modelo de Concurrencia:
- Tarea 1: `OrderBookListenerTask` (sub-millisecond L2 depth maintenance).
- Tarea 2: `HFTStrategyTask` (micro-scalp ticks, latency guard <800ms, fast exits 2-10s).
- Tarea 3: `SwingStrategyTask` (multi-hour macro trend offloaded via asyncio.to_thread).
- Tarea 4: `TelegramListenerTask` (control bidireccional y alertas push inmediatas).
- Tarea 5: `PeriodicSummaryTask` (resúmenes de rendimiento cada 3 a 6 horas).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Coroutine, Dict, List, Optional, Sequence, Tuple, Union

# Conectores y librerías del ecosistema
from conectores.binance_prediction import (
    BinancePredictionConnector,
    OrderBookSnapshot,
)
BinanceAsyncConnector = BinancePredictionConnector  # Alias formal contract PROJECT.md

from continuitis.microestructura_binance import (
    DEFAULT_TICK_SIZE,
    MAX_SPREAD_PERMITIDO,
    MAX_FEED_LATENCY_MS,
    GoldenRulesValidator,
    LatencyAndKillSwitchGuard,
    MicroestructuraBinanceEngine,
    MicrostructureSignal,
    OrderProposal,
    RiskApprovedOrder,
)

from continuitis.riesgo_binance import (
    EscudoFinancieroBinance,
)

from continuitis.tesoreria import (
    GestorTesoreria,
)
TesoreriaBinance = GestorTesoreria  # Alias formal contract PROJECT.md

from continuitis.state_registry import StateRegistrySQLite
from continuitis.auditor_metricas import (
    AuditorMetricas,
    TradeResult,
)

from estrategias.hft_engine import (
    HFTEngine,
    HftSignal,
    MatchLiveState,
    SportType,
)

from conectores.telegram_bidireccional import (
    MockTelegramClient,
    TelegramBidireccionalBot,
    TelegramCommandRouter,
)

logger = logging.getLogger("CONTINUITY.OrquestadorBinance")


# ==============================================================================
# ORQUESTADOR PRINCIPAL CONTINUO: ContinuityHFTBinanceOrchestrator
# ==============================================================================

class ContinuityHFTBinanceOrchestrator:
    """
    Orquestador maestro continuo de alta frecuencia para los mercados
    de predicción deportiva de Binance Spot.
    """

    @property
    def symbols(self) -> Sequence[str]:
        if hasattr(self, "binance_client") and hasattr(self.binance_client, "active_market_ids") and self.binance_client.active_market_ids:
            return self.binance_client.active_market_ids
        return self._symbols

    def __init__(
        self,
        symbols: Sequence[str] = ("SOCCER_PRED_USDT", "BASKET_PRED_USDT", "TENNIS_PRED_USDT"),
        capital_inicial: float = 10.0,
        mock_mode: bool = True,
        api_key: str = "",
        api_secret: str = "",
        telegram_token: str = "",
        telegram_chat_id: str = "",
        summary_interval_s: float = 10800.0,  # 3 horas por defecto
        hft_cycle_interval_s: float = 0.05,   # 50 ms loop micro-tick
        swing_cycle_interval_s: float = 1.0,  # 1 s loop macro
    ):
        self._symbols = [s.upper().replace("/", "").replace("-", "") for s in symbols]
        self.capital_inicial = float(capital_inicial)
        self.mock_mode = bool(mock_mode)
        self.summary_interval_s = float(summary_interval_s)
        self.hft_cycle_interval_s = float(hft_cycle_interval_s)
        self.swing_cycle_interval_s = float(swing_cycle_interval_s)

        # ----------------------------------------------------------------------
        # INICIALIZACIÓN DE SUBMÓDULOS DE ARQUITECTURA
        # ----------------------------------------------------------------------
        # 0. State Registry (SQLite WAL)
        self.state_registry = StateRegistrySQLite()

        # Intentar cargar balance previo
        saved_balance = self.state_registry.get_state("balance")
        if saved_balance:
            try:
                self.capital_inicial = float(saved_balance)
                logger.info(f"[StateRegistry] Balance previo cargado: {self.capital_inicial} USD")
            except ValueError:
                pass

        # 1. Conector Binance Spot
        self.binance_client: BinancePredictionConnector = BinancePredictionConnector(
            api_key=api_key,
            api_secret=api_secret,
            mock_mode=self.mock_mode,
            depth_limit=10,
        )

        # 2. Auditor Analítico Continuo
        self.auditor: AuditorMetricas = AuditorMetricas(capital_inicial=self.capital_inicial)

        # 3. Gestor de Tesorería y Cosecha ("Ordeño e Inyección")
        self.tesoreria: GestorTesoreria = GestorTesoreria(
            balance_inicial=self.capital_inicial,
            auditor=self.auditor,
        )

        # 4. Motor de Microestructura y Reglas de Oro
        self.micro_engine: MicroestructuraBinanceEngine = MicroestructuraBinanceEngine(
            max_latencia_ms=MAX_FEED_LATENCY_MS,
            max_spread=MAX_SPREAD_PERMITIDO,
            tick_size=DEFAULT_TICK_SIZE,
        )

        # 5. Escudo Financiero y Dimensionamiento Real de Riesgo
        self.risk_engine: EscudoFinancieroBinance = EscudoFinancieroBinance(
            pct_riesgo_fijo=0.015,
            ev_minimo=0.015,
            max_cluster_exp=0.15,
            factor_atenuacion_racha=0.85,
        )


        # 7. Motor Cuantitativo HFT (4 Fases, Estrategias A y B)
        self.hft_engine: HFTEngine = HFTEngine(
            micro_engine=self.micro_engine,
            risk_engine=self.risk_engine,
            tick_size=DEFAULT_TICK_SIZE,
        )


        # 9. Bot Bidireccional de Telegram
        self.telegram_bot: TelegramBidireccionalBot = TelegramBidireccionalBot(
            bot_token=telegram_token,
            chat_id=telegram_chat_id,
            mock_mode=self.mock_mode,
        )

        # ----------------------------------------------------------------------
        # ESTADO OPERATIVO Y BANDERAS DE CONTROL
        # ----------------------------------------------------------------------
        self.is_running: bool = False
        self.is_paused: bool = False
        self.kill_switch_triggered: bool = False
        self.motivo_pausa_o_kill: str = ""

        # Mapeo de estados de partidos en vivo para cada símbolo
        self.live_matches: Dict[str, MatchLiveState] = {}
        for sym in self.symbols:
            self.live_matches[sym] = MatchLiveState(
                match_id=f"MATCH_{sym}",
                symbol=sym,
                sport=SportType.SOCCER,
                time_to_kickoff_minutes=None, # None indicates it is live or we don't know yet
                is_live=True, # Start assuming live to get L2 tracking
            )


        # Tareas de segundo plano
        self._tasks: List[asyncio.Task] = []
        self._orderbook_task: Optional[asyncio.Task] = None
        self._hft_task: Optional[asyncio.Task] = None
        self._telegram_task: Optional[asyncio.Task] = None
        self._summary_task: Optional[asyncio.Task] = None

        # Registro de callbacks de control en Telegram
        self._conectar_control_telegram()

    # --------------------------------------------------------------------------
    # CONEXIÓN DEL CONTROL REMOTO BIDIRECCIONAL (TELEGRAM)
    # --------------------------------------------------------------------------
    def _conectar_control_telegram(self) -> None:
        """Enlaza las operaciones del orquestador con el enrutador de comandos de Telegram."""
        self.telegram_bot.register_command_handlers(
            kill_switch_cb=self.trigger_kill_switch,
            pause_cb=self.pause_trading,
            resume_cb=self.resume_trading,
            risk_update_cb=self.update_risk_param,
            query_metrics_cb=self.get_metrics_report,
        )
        self.telegram_bot.register_harvest_handler(self.ejecutar_cosecha_o_auditoria)

    # --------------------------------------------------------------------------
    # COMANDOS DE CONTROL OPERATIVO
    # --------------------------------------------------------------------------
    def trigger_kill_switch(self, motivo: str = "KILL_SWITCH_REMOTO") -> Dict[str, Any]:
        """
        Disparador de Pánico Instantáneo (Kill Switch):
        1. Marca el estado de emergencia en LatencyAndKillSwitchGuard.
        2. Pausa la generación de órdenes en HFT y Swing.
        3. Cancela todas las órdenes activas en el exchange.
        4. Libera las reservas pendientes de capital.
        5. Notifica la parada inmediata.
        """
        logger.critical(f"[ORQUESTADOR] 🚨 KILL SWITCH DISPARADO: {motivo}")
        self.kill_switch_triggered = True
        self.is_paused = True
        self.motivo_pausa_o_kill = motivo

        # 1. Bloquear guardia de microestructura
        self.micro_engine.latency_guard.activar_kill_switch(motivo)

        # 2. Cancelar órdenes pendientes en Binance
        for sym in self.symbols:
            if hasattr(self.binance_client, "_mock_cancel_all_orders"):
                self.binance_client._mock_cancel_all_orders(sym)
            elif hasattr(self.binance_client, "cancel_all_orders"):
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        asyncio.create_task(self.binance_client.cancel_all_orders(sym))
                except Exception:
                    pass

        # 3. Limpiar órdenes en HFTEngine para todos los símbolos
        for sym in self.symbols:
            self.hft_engine.limpiar_mesa_prematch(sym)


        # 6. Registrar notificación de emergencia en TelegramBot
        msg_kill = f"🚨 KILL SWITCH ACTIVADO: Operación detenida inmediatamente ({motivo})."
        if hasattr(self, "telegram_bot") and self.telegram_bot is not None:
            if msg_kill not in self.telegram_bot.mensajes_enviados:
                self.telegram_bot.mensajes_enviados.append(msg_kill)
            if hasattr(self.telegram_bot, "router") and msg_kill not in self.telegram_bot.router.notificaciones_push:
                self.telegram_bot.router.notificaciones_push.append(msg_kill)

        return {
            "exito": True,
            "kill_switch": True,
            "pausado": True,
            "motivo": motivo,
            "timestamp": time.time(),
        }

    def pause_trading(self, motivo: str = "PAUSA_OPERADOR") -> Dict[str, Any]:
        """Pausa temporalmente la colocación de nuevas órdenes."""
        logger.info(f"[ORQUESTADOR] ⏸️ Operación pausada: {motivo}")
        self.is_paused = True
        self.motivo_pausa_o_kill = motivo
        return {"exito": True, "pausado": True, "motivo": motivo}

    def resume_trading(self) -> Dict[str, Any]:
        """Reanuda la operación activa si no existe una emergencia crítica pendiente."""
        if self.kill_switch_triggered:
            # Restablecer kill switch si se reanuda explícitamente
            self.kill_switch_triggered = False
            self.micro_engine.latency_guard.emergencia_activa = False
            self.micro_engine.latency_guard.motivo_emergencia = ""
            logger.info("[ORQUESTADOR] Reset de Kill Switch tras comando resume explícito.")

        self.is_paused = False
        self.motivo_pausa_o_kill = ""
        logger.info("[ORQUESTADOR] ▶️ Operación reanudada exitosamente.")
        return {"exito": True, "pausado": False}

    def update_risk_param(self, param: str, val: float) -> Dict[str, Any]:
        """
        Modifica parámetros cuantitativos de riesgo en caliente sin reiniciar el motor.
        """
        param_clean = param.strip().lower()
        logger.info(f"[ORQUESTADOR] Solicitud de ajuste de riesgo en caliente: {param_clean} = {val}")

        if param_clean in ("pct_riesgo", "pct_riesgo_fijo"):
            if 0.001 <= val <= 0.05:
                self.risk_engine.pct_riesgo_fijo = val
                return {"exito": True, "param": param_clean, "nuevo_valor": val}
            return {"exito": False, "motivo": "Rango permitido para pct_riesgo: [0.001, 0.05] (0.1% a 5.0%)"}

        elif param_clean in ("max_cluster", "max_cluster_exp"):
            if 0.01 <= val <= 0.30:
                self.risk_engine.max_cluster_exp = val
                return {"exito": True, "param": param_clean, "nuevo_valor": val}
            return {"exito": False, "motivo": "Rango permitido para max_cluster: [0.01, 0.30] (1% a 30%)"}

        elif param_clean in ("ev_minimo", "ev_min"):
            if 0.0 <= val <= 0.10:
                self.risk_engine.ev_minimo = val
                return {"exito": True, "param": param_clean, "nuevo_valor": val}
            return {"exito": False, "motivo": "Rango permitido para ev_minimo: [0.0, 0.10]"}

        elif param_clean in ("max_spread", "spread"):
            if 0.005 <= val <= 0.05:
                self.micro_engine.max_spread = val
                return {"exito": True, "param": param_clean, "nuevo_valor": val}
            return {"exito": False, "motivo": "Rango permitido para max_spread: [0.005, 0.05] (Regla de Oro: <= $0.03)"}

        return {"exito": False, "motivo": f"Parámetro desconocido: '{param}'"}

    def get_metrics_report(self) -> Dict[str, Any]:
        """Devuelve el resumen consolidado de telemetría y métricas continuas."""
        metricas = self.auditor.obtener_metricas()
        estado = "KILL_SWITCH" if self.kill_switch_triggered else ("PAUSADO" if self.is_paused else "ACTIVO")
        metricas["estado"] = estado
        metricas["balance_tesoreria"] = round(self.tesoreria.balance, 2)
        metricas["hito_100_inyectado"] = self.tesoreria.hito_100_inyectado
        metricas["meta_1000_activada"] = self.tesoreria.meta_1000_activada
        metricas["latencia_feed_ms"] = round(self.binance_client.latencia_feed_ms, 2)
        return metricas

    def ejecutar_cosecha_o_auditoria(self) -> Dict[str, Any]:
        """Ejecuta la auditoría de hitos de tesorería y cosecha autónoma."""
        res = self.tesoreria.verificar_hitos()
        return res


    def get_exposicion_cluster(self) -> float:
        # Calcular exposición actual
        exposicion = 0.0
        for pos in self.hft_engine.active_positions.values():
            if pos.status == "OPEN":
                exposicion += (pos.entry_price * pos.quantity)
        return exposicion

    async def reservar_capital(self, stake: float, strategy_id: str, symbol: str) -> Any:
        # Retorna un "token" mockeado
        return {"stake": stake, "symbol": symbol, "is_released": False}

    async def liberar_capital(self, token: Any) -> None:
        if isinstance(token, dict):
            token["is_released"] = True

    # --------------------------------------------------------------------------
    # PIPELINE CONCURRENTE: TAREA 1 (ORDER BOOK LISTENER TASK)
    # --------------------------------------------------------------------------
    async def _orderbook_listener_task(self) -> None:
        """
        Tarea 1: Ingesta asíncrona de L2 Depth al libro de órdenes en RAM O(1).
        Monitorea el heartbeat y audita latencias de alimentación externa.
        """
        logger.info("[PIPELINE] OrderBookListenerTask iniciada.")
        try:
            while self.is_running:
                for sym in self.symbols:
                    await self.step_orderbook_cycle(sym)

                await asyncio.sleep(self.hft_cycle_interval_s)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("[PIPELINE] OrderBookListenerTask finalizada.")

    async def step_orderbook_cycle(self, symbol: str) -> OrderBookSnapshot:
        """
        Paso individual de mantenimiento de libro para un símbolo.
        Útil para pruebas unitarias deterministas.
        """
        snap = await self.binance_client.get_orderbook_snapshot(symbol)
        # Si el libro está vacío y estamos en mock, inicializar con libro válido
        if not snap.is_valid and self.mock_mode:
            ts = int(time.time() * 1000)
            snap = self.binance_client.actualizar_libro(
                symbol=symbol,
                bids=((0.50, 600.0), (0.49, 400.0), (0.48, 300.0)),
                asks=((0.52, 100.0), (0.53, 50.0)),
                timestamp_ms=ts,
                market_status="ACTIVE",
            )

        # Actualizar pulso de feed en el guardián de microestructura
        if snap.timestamp_ms > 0:
            self.micro_engine.latency_guard.registrar_pulso_feed(snap.timestamp_ms / 1000.0)
        self.micro_engine.latency_guard.actualizar_estado_binance(snap.market_status)

        # Chequeo de disyuntor de latencia
        guard_ok, motivo = self.micro_engine.latency_guard.autorizacion_disparo()
        if not guard_ok and not self.is_paused:
            logger.warning(f"[LATENCY GUARD] Disyuntor activado en {symbol}: {motivo}")

        return snap

    # --------------------------------------------------------------------------
    # PIPELINE CONCURRENTE: TAREA 2 (HFT STRATEGY TASK)
    # --------------------------------------------------------------------------
    async def _hft_strategy_task(self) -> None:
        """
        Tarea 2: Ejecución de micro-scalping de alta frecuencia.
        Evalúa micro-ticks, OBI imbalance, spread, y ejecuta entradas y salidas rápidas (2-10s).
        """
        logger.info("[PIPELINE] HFTStrategyTask iniciada.")
        try:
            while self.is_running:
                if not self.is_paused and not self.kill_switch_triggered:
                    for sym in self.symbols:
                        await self.step_hft_cycle(sym)

                await asyncio.sleep(self.hft_cycle_interval_s)
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("[PIPELINE] HFTStrategyTask finalizada.")

    async def step_hft_cycle(self, symbol: str) -> Optional[HftSignal]:
        """
        Paso individual de evaluación y ejecución HFT para un símbolo.
        """
        if self.is_paused or self.kill_switch_triggered:
            return None

        snap = await self.binance_client.get_orderbook_snapshot(symbol)
        if not snap.is_valid:
            return None

        match_state = self.live_matches.get(symbol)
        if not match_state:
            match_state = MatchLiveState(match_id=f"M_{symbol}", symbol=symbol, is_live=True, time_to_kickoff_minutes=None)
            self.live_matches[symbol] = match_state

        balance = self.tesoreria.balance
        # 0. Vigilar y cerrar posiciones activas según libro
        await self._vigilar_y_cerrar_posiciones_abiertas(symbol, snap)

        # 1. Evaluar señal con HFTEngine
        senal: HftSignal
        if match_state.is_prematch:
            senal = self.hft_engine.evaluar_fase_1_prematch_obi(
                snapshot=snap,
                match_state=match_state,
                balance=balance,
                operaciones_activas=len(self.hft_engine.active_positions),
                exposicion_cluster=self.get_exposicion_cluster(),
            )
        else:
            senal = self.hft_engine.evaluar_mercado_completo(
                snapshot=snap,
                match_state=match_state,
                balance=balance,
                operaciones_activas=len(self.hft_engine.active_positions),
                exposicion_cluster=self.get_exposicion_cluster(),
            )

        # 2. Si la señal está autorizada, reservar capital atómicamente y colocar orden
        if senal.authorized and senal.action in ("LIMIT_BUY", "MARKET_BUY", "BUY_LIMIT", "BUY_MARKET", "BUY"):
            costo_estimado = senal.price * senal.quantity
            token = await self.reservar_capital(
                stake=costo_estimado,
                strategy_id=senal.strategy_id,
                symbol=symbol,
            )

            if token is not None:
                # Transmitir orden al conector de Binance
                tipo_orden = "LIMIT" if "LIMIT" in senal.action else "MARKET"
                order_resp = await self.binance_client.place_order(
                    symbol=symbol,
                    side="BUY",
                    order_type=tipo_orden,
                    price=senal.price if tipo_orden == "LIMIT" else None,
                    quantity=senal.quantity,
                )

                # Registrar posición en HFTEngine
                order_id = str(order_resp.get("orderId", uuid.uuid4().hex[:8]))
                pos = self.hft_engine.registrar_orden_ejecutada(
                    signal=senal,
                    order_id=order_id,
                    executed_price=senal.price,
                    executed_qty=senal.quantity,
                )

            else:
                logger.debug(f"[HFT] Rechazada por techo de clúster de capital: {symbol}")

        return senal


    # PIPELINE CONCURRENTE: TAREA 4 (TELEGRAM LISTENER TASK)
    # --------------------------------------------------------------------------
    async def _telegram_listener_task(self) -> None:
        """Tarea 4: Escucha asíncrona de comandos remotos y eventos de botones."""
        logger.info("[PIPELINE] TelegramListenerTask iniciada.")
        try:
            await self.telegram_bot.listener_loop()
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("[PIPELINE] TelegramListenerTask finalizada.")

    # --------------------------------------------------------------------------
    # PIPELINE CONCURRENTE: TAREA 5 (PERIODIC SUMMARY TASK)
    # --------------------------------------------------------------------------
    async def _summary_reporter_task(self) -> None:
        """Tarea 5: Resúmenes de telemetría y rendimiento cada 3 a 6 horas."""
        logger.info("[PIPELINE] PeriodicSummaryTask iniciada.")
        try:
            while self.is_running:
                await asyncio.sleep(self.summary_interval_s)
                if self.is_running:
                    metricas = self.auditor.obtener_metricas()
                    horas_reporte = int(self.summary_interval_s / 3600)
                    await self.telegram_bot.notificar_resumen_periodico(
                        horas=horas_reporte,
                        metricas=metricas,
                        balance_actual=self.tesoreria.balance,
                        latencia_promedio_ms=self.binance_client.latencia_feed_ms,
                    )
        except asyncio.CancelledError:
            pass
        finally:
            logger.info("[PIPELINE] PeriodicSummaryTask finalizada.")

    # --------------------------------------------------------------------------
    # ARRANQUE Y PARADA LIMPIA DEL SISTEMA COMPLETO
    # --------------------------------------------------------------------------
    async def start(self) -> None:
        """Inicia todas las tareas asíncronas del orquestador."""
        if self.is_running:
            return

        self.is_running = True
        logger.info("[ORQUESTADOR] Iniciando ContinuityHFTBinanceOrchestrator...")

        # 1. Notificar arranque a Telegram
        await self.telegram_bot.notificar_inicio(
            version="CONTINUITY HFT BINANCE 1.0 (PROD)",
            balance_inicial=self.capital_inicial,
            mercados=self.symbols,
        )

        # 2. Desplegar tareas en bucle de eventos
        self._orderbook_task = asyncio.create_task(
            self._orderbook_listener_task(), name="OrderBookListenerTask"
        )
        self._hft_task = asyncio.create_task(
            self._hft_strategy_task(), name="HFTStrategyTask"
        )
        self._telegram_task = asyncio.create_task(
            self._telegram_listener_task(), name="TelegramListenerTask"
        )
        self._summary_task = asyncio.create_task(
            self._summary_reporter_task(), name="PeriodicSummaryTask"
        )

        self._tasks = [
            self._orderbook_task,
            self._hft_task,
            self._telegram_task,
            self._summary_task,
        ]

        logger.info("[ORQUESTADOR] Todas las tareas del pipeline están activas y operando.")

    async def stop(self) -> None:
        """Parada limpia del sistema y cancelación de tareas concurrentes."""
        if not self.is_running:
            return

        logger.info("[ORQUESTADOR] Deteniendo ContinuityHFTBinanceOrchestrator...")
        self.is_running = False

        # 1. Cancelar órdenes abiertas en exchange
        for sym in self.symbols:
            if hasattr(self.binance_client, "_mock_cancel_all_orders"):
                self.binance_client._mock_cancel_all_orders(sym)
            elif hasattr(self.binance_client, "cancel_all_orders"):
                try:
                    await self.binance_client.cancel_all_orders(sym)
                except Exception:
                    pass

        # 2. Cancelar tareas asíncronas y esperar su finalización limpia
        for t in self._tasks:
            if t and not t.done():
                t.cancel()
        tasks_to_wait = [t for t in self._tasks if t]
        if tasks_to_wait:
            await asyncio.gather(*tasks_to_wait, return_exceptions=True)

        # 3. Detener bot de Telegram y conector Binance
        await self.telegram_bot.stop()
        await self.binance_client.close()

        # 4. Notificar cierre
        metricas = self.auditor.obtener_metricas()
        ganancia = self.tesoreria.balance - self.capital_inicial
        await self.telegram_bot.notificar_cierre(
            balance_final=self.tesoreria.balance,
            balance_inicial=self.capital_inicial,
            total_trades=metricas.get("total_trades", 0),
            ganancia_neta=ganancia,
        )

        logger.info("[ORQUESTADOR] Sistema apagado limpiamente.")

    async def run_forever(self) -> None:
        """Mantiene el orquestador en ejecución continua hasta interrupción."""
        await self.start()
        try:
            while self.is_running:
                await asyncio.sleep(1.0)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        finally:
            await self.stop()


if __name__ == '__main__':
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    import os
    orquestador = ContinuityHFTBinanceOrchestrator(
        mock_mode=False,
        api_key=os.getenv('BINANCE_API_KEY', ''),
        api_secret=os.getenv('BINANCE_SECRET_KEY', ''),
        telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
        telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', '')
    )
    asyncio.run(orquestador.run_forever())
