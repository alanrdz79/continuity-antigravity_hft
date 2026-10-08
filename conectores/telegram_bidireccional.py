# -*- coding: utf-8 -*-
"""
conectores.telegram_bidireccional
=================================
Bot de Telegram Bidireccional Interactivo para CONTINUITY HFT Binance.

Características:
1. Control bidireccional en tiempo real con enrutamiento de comandos:
   - /start, /help: Menú interactivo y teclado en línea (inline keyboard).
   - /status: Estado operativo actual y latencia de conexión.
   - /kill, /panico, /stop: Botón de pánico (Kill Switch) con pausa inmediata y cancelación total.
   - /pause: Pausa temporal de generación de órdenes.
   - /resume: Reanudación de operativa.
   - /risk <param> <val>: Modificación dinámica en caliente de parámetros de riesgo.
   - /report, /metricas: Reporte estructurado de telemetría y métricas analíticas.
   - /harvest, /tesoreria: Inspección y ejecución de cosechas autónomas de tesorería.
2. Teclado interactivo Inline Keyboard (Reanudar/Pausar, KILL SWITCH, Reporte Métricas,
   Gráfica, Parámetros, Tesorería).
3. Notificaciones push autónomas:
   - Notificación de inicio de sistema.
   - Resúmenes periódicos cada 3 a 6 horas.
   - Notificación de cierre diario / parada.
   - Disyuntor de emergencia y alertas de circuit breaker de latencia o spread.
   - Hitos de inyección ($100 USD) y cosechas de capital a MXN ($1,000 USD).
4. Simulador MockTelegramClient:
   - Para entornos headless y ejecución de suites de pruebas sin red ni credenciales externas.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
)

logger = logging.getLogger("CONTINUITY.TelegramBidireccional")


# ==============================================================================
# 1. PROTOCOLOS E INTERFACES DE CONTROL (PROJECT.md)
# ==============================================================================

class TelegramControlProtocol(Protocol):
    """Protocolo formal del bot de Telegram exigido por PROJECT.md."""
    async def notify(self, message: str) -> None: ...
    def register_command_handlers(
        self,
        kill_switch_cb: Callable[[], Any],
        pause_cb: Callable[[], Any],
        resume_cb: Callable[[], Any],
        risk_update_cb: Callable[[str, float], Dict[str, Any]],
        query_metrics_cb: Callable[[], Dict[str, Any]],
    ) -> None: ...


# ==============================================================================
# 2. DEFINICIÓN DEL TECLADO INLINE (INLINE KEYBOARD LAYOUT)
# ==============================================================================

def generar_teclado_inline_principal(pausado: bool = False) -> Dict[str, Any]:
    """
    Construye la estructura de botones en línea para el menú interactivo de Telegram.
    
    Botones incluidos:
    1. Reanudar / Pausar
    2. KILL SWITCH
    3. Reporte Métricas
    4. Gráfica de Rendimiento
    5. Parámetros de Riesgo
    6. Tesorería / Cosecha
    """
    toggle_text = "▶️ Reanudar Operación" if pausado else "⏸️ Pausar Operación"
    toggle_data = "cmd_resume" if pausado else "cmd_pause"

    return {
        "inline_keyboard": [
            [
                {"text": toggle_text, "callback_data": toggle_data},
                {"text": "🚨 KILL SWITCH", "callback_data": "cmd_kill"},
            ],
            [
                {"text": "📊 Reporte Métricas", "callback_data": "cmd_report"},
                {"text": "📈 Gráfica Rendimiento", "callback_data": "cmd_chart"},
            ],
            [
                {"text": "⚙️ Parámetros Riesgo", "callback_data": "cmd_params"},
                {"text": "🏦 Tesorería / Cosecha", "callback_data": "cmd_harvest"},
            ],
        ]
    }


# ==============================================================================
# 3. ENRUTADOR DE COMANDOS Y CALLBACKS (TelegramCommandRouter)
# ==============================================================================

class TelegramCommandRouter:
    """
    Enrutador bidireccional de comandos conforme a `TelegramControlProtocol`.
    Procesa tanto comandos de texto (/kill, /pause, /risk, etc.) como pulsaciones
    de botones del teclado en línea.
    """

    def __init__(self, bot: Optional[Any] = None):
        self.bot = bot
        self.kill_switch_cb: Optional[Callable[[], Any]] = None
        self.pause_cb: Optional[Callable[[], Any]] = None
        self.resume_cb: Optional[Callable[[], Any]] = None
        self.risk_update_cb: Optional[Callable[[str, float], Dict[str, Any]]] = None
        self.query_metrics_cb: Optional[Callable[[], Dict[str, Any]]] = None
        self.harvest_cb: Optional[Callable[[], Dict[str, Any]]] = None

        # Historial de notificaciones push emitidas
        self.notificaciones_push: List[str] = []
        self._pausado_local: bool = False

    def register_command_handlers(
        self,
        kill_switch_cb: Callable[[], Any],
        pause_cb: Callable[[], Any],
        resume_cb: Callable[[], Any],
        risk_update_cb: Callable[[str, float], Dict[str, Any]],
        query_metrics_cb: Callable[[], Dict[str, Any]],
    ) -> None:
        """Registra los manejadores de eventos y comandos del orquestador principal."""
        self.kill_switch_cb = kill_switch_cb
        self.pause_cb = pause_cb
        self.resume_cb = resume_cb
        self.risk_update_cb = risk_update_cb
        self.query_metrics_cb = query_metrics_cb

    def register_harvest_handler(self, harvest_cb: Callable[[], Dict[str, Any]]) -> None:
        """Registra manejador opcional de tesorería y cosecha."""
        self.harvest_cb = harvest_cb

    async def notify(self, message: str) -> None:
        """Envía una notificación push asíncrona."""
        self.notificaciones_push.append(message)
        if self.bot is not None:
            if hasattr(self.bot, "mensajes_enviados") and message not in self.bot.mensajes_enviados:
                self.bot.mensajes_enviados.append(message)
            if hasattr(self.bot, "mock_mode") and not self.bot.mock_mode:
                try:
                    await self.bot._enviar_api_telegram(message)
                except Exception:
                    pass
        logger.info(f"[Telegram Push]: {message.splitlines()[0]}")

    async def procesar_mensaje(self, texto: str) -> str:
        """
        Parsea y ejecuta comandos entrantes del operador.
        Soporta formato insensible a mayúsculas/minúsculas y múltiples aliases.
        """
        texto_limpio = texto.strip()
        if not texto_limpio:
            return "Comando vacío."

        partes = texto_limpio.split()
        cmd = partes[0].lower()

        # ----------------------------------------------------------------------
        # COMANDOS DE CONTROL DE EMERGENCIA Y PAUSA
        # ----------------------------------------------------------------------
        if cmd in ("/kill", "/panico", "/stop"):
            self._pausado_local = True
            if self.kill_switch_cb:
                res = self.kill_switch_cb()
                if asyncio.iscoroutine(res):
                    await res
            await self.notify("🚨 KILL SWITCH ACTIVADO: Operación detenida inmediatamente.")
            return "🚨 KILL_SWITCH_EJECUTADO: Sistema pausado y órdenes canceladas."

        elif cmd == "/pause":
            self._pausado_local = True
            if self.pause_cb:
                res = self.pause_cb()
                if asyncio.iscoroutine(res):
                    await res
            return "⏸️ PAUSA_ACTIVADA: Generación de órdenes suspendida temporalmente."

        elif cmd == "/resume":
            self._pausado_local = False
            if self.resume_cb:
                res = self.resume_cb()
                if asyncio.iscoroutine(res):
                    await res
            return "▶️ OPERACION_REANUDADA: Generación de órdenes activa."

        # ----------------------------------------------------------------------
        # COMANDO DE AJUSTE DE RIESGO EN CALIENTE
        # ----------------------------------------------------------------------
        elif cmd == "/risk":
            if len(partes) < 3:
                return "❌ USO: /risk <parametro> <valor> (ej. /risk pct_riesgo 0.02)"
            param = partes[1].lower()
            try:
                val = float(partes[2])
            except ValueError:
                return f"❌ ERROR: El valor '{partes[2]}' no es numérico."

            if self.risk_update_cb:
                resultado = self.risk_update_cb(param, val)
                if resultado.get("exito", False):
                    return f"✅ PARAMETRO_ACTUALIZADO: {param} = {val}"
                else:
                    return f"❌ RECHAZADO: {resultado.get('motivo', 'Parámetro inválido')}"
            return "❌ Handler de riesgo no configurado."

        # ----------------------------------------------------------------------
        # COMANDOS DE TELEMETRÍA Y MÉTRICAS
        # ----------------------------------------------------------------------
        elif cmd in ("/report", "/metricas", "/status"):
            if self.query_metrics_cb:
                m = self.query_metrics_cb()
                estado = m.get("estado", "PAUSADO" if self._pausado_local else "ACTIVO")
                return (
                    f"📊 REPORTE DE TELEMETRÍA CONTINUITY 📊\n"
                    f"• Trades Totales: {m.get('total_trades', 0)}\n"
                    f"• Win Rate: {m.get('win_rate', 0.0) * 100:.1f}%\n"
                    f"• Capital: ${m.get('capital_acumulado', 0.0):.2f} USD\n"
                    f"• ROI: {m.get('roi', 0.0) * 100:.2f}%\n"
                    f"• Yield: {m.get('yield', 0.0) * 100:.2f}%\n"
                    f"• Estado: {estado}"
                )
            return "❌ Handler de métricas no configurado."

        # ----------------------------------------------------------------------
        # COMANDO DE TESORERÍA / COSECHA
        # ----------------------------------------------------------------------
        elif cmd in ("/harvest", "/cosecha", "/tesoreria"):
            if self.harvest_cb:
                res = self.harvest_cb()
                return (
                    f"🏦 ESTADO DE TESORERÍA Y COSECHA 🏦\n"
                    f"• Balance Actual: ${res.get('balance_actual', 0.0):.2f} USD\n"
                    f"• Hito $100 Inyectado: {'SÍ' if res.get('hito_100_inyectado') else 'PENDIENTE'}\n"
                    f"• Cosecha $1,000 Activa: {'SÍ' if res.get('meta_1000_activada') else 'PENDIENTE'}\n"
                    f"• Acciones recientes: {', '.join(res.get('acciones', [])) or 'Ninguna'}"
                )
            return "🏦 MÓDULO DE TESORERÍA: Ciclo estándar activo ($10 -> $100 -> $1,000 USD)."

        # ----------------------------------------------------------------------
        # MENÚ INICIAL Y AYUDA
        # ----------------------------------------------------------------------
        elif cmd in ("/start", "/inicio"):
            teclado = generar_teclado_inline_principal(self._pausado_local)
            return (
                "🤖 *CONTINUITY HFT BINANCE — BOT DE CONTROL INTERACTIVO*\n\n"
                "Bienvenido al panel de control remoto de alta frecuencia.\n"
                "Seleccione una acción con los botones en línea o escriba un comando:\n\n"
                "• `/status` - Diagnóstico de latencia y estado\n"
                "• `/report` - Telemetría completa de métricas\n"
                "• `/pause`  - Suspender órdenes temporalmente\n"
                "• `/resume` - Reanudar trading algorítmico\n"
                "• `/risk <param> <val>` - Modificar parámetros en caliente\n"
                "• `/kill`   - Disyuntor de emergencia (Kill Switch)\n"
                "• `/harvest`- Estado de cosecha y tesorería"
            )

        elif cmd in ("/help", "/ayuda"):
            return (
                "🤖 COMANDOS DISPONIBLES:\n"
                "/kill - Parada de emergencia instantánea\n"
                "/pause - Pausa temporal de trading\n"
                "/resume - Reanudar trading\n"
                "/risk <param> <val> - Modificar riesgo en caliente\n"
                "/report - Métricas de rendimiento actuales"
            )

        return f"❓ Comando desconocido '{cmd}'. Use /help para ver la lista de comandos."

    async def procesar_callback_query(self, data: str) -> str:
        """
        Procesa el evento disparado al presionar un botón del teclado en línea.
        """
        data_clean = data.strip().lower()

        if data_clean == "cmd_kill":
            return await self.procesar_mensaje("/kill")
        elif data_clean == "cmd_pause":
            return await self.procesar_mensaje("/pause")
        elif data_clean == "cmd_resume":
            return await self.procesar_mensaje("/resume")
        elif data_clean in ("cmd_toggle_pause", "toggle_pause"):
            if self._pausado_local:
                return await self.procesar_mensaje("/resume")
            else:
                return await self.procesar_mensaje("/pause")
        elif data_clean in ("cmd_report", "report"):
            return await self.procesar_mensaje("/report")
        elif data_clean in ("cmd_harvest", "harvest"):
            return await self.procesar_mensaje("/harvest")
        elif data_clean in ("cmd_params", "params"):
            return (
                "⚙️ PARÁMETROS CONFIGURABLES EN CALIENTE:\n"
                "• `pct_riesgo` (ej. `/risk pct_riesgo 0.02`)\n"
                "• `max_cluster` (ej. `/risk max_cluster 0.15`)\n"
                "• `ev_minimo` (ej. `/risk ev_minimo 0.015`)\n"
                "• `max_spread` (ej. `/risk max_spread 0.03`)"
            )
        elif data_clean in ("cmd_chart", "chart"):
            if self.query_metrics_cb:
                m = self.query_metrics_cb()
                wr = m.get("win_rate", 0.0) * 100
                cap = m.get("capital_acumulado", 0.0)
                n = m.get("total_trades", 0)
                bar_len = min(20, int(wr / 5))
                bar = "█" * bar_len + "░" * (20 - bar_len)
                return (
                    f"📈 GRÁFICA DE RENDIMIENTO EN TIEMPO REAL\n"
                    f"Capital: ${cap:.2f} USD | N = {n} trades\n"
                    f"WR [{bar}] {wr:.1f}%"
                )
            return "📈 Sin datos históricos disponibles para graficar."

        return f"Botón no reconocido: {data}"


# ==============================================================================
# 4. BOT PRINCIPAL BIDIRECCIONAL (TelegramBidireccionalBot)
# ==============================================================================

class TelegramBidireccionalBot:
    """
    Cliente bidireccional autónomo de Telegram para CONTINUITY HFT.
    
    Gestiona:
    - Escucha asíncrona de comandos (polling o mock).
    - Despacho de notificaciones estructuradas:
      * Inicio / Cierre
      * Resúmenes 3h - 6h
      * Alarmas de circuit breaker
      * Hitos de tesorería e inyección
    """

    def __init__(
        self,
        bot_token: str = "",
        chat_id: str = "",
        mock_mode: bool = False,
        poll_interval_s: float = 1.0,
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.mock_mode = mock_mode or not bool(bot_token and chat_id)
        self.poll_interval_s = poll_interval_s

        self.router = TelegramCommandRouter(bot=self)
        self._running: bool = False
        self._listener_task: Optional[asyncio.Task] = None
        self._update_offset: int = 0

        # Historial de notificaciones emitidas
        self.mensajes_enviados: List[str] = []

    # --------------------------------------------------------------------------
    # REGISTRO DE HANDLERS (TELEGRAM CONTROL PROTOCOL)
    # --------------------------------------------------------------------------
    def register_command_handlers(
        self,
        kill_switch_cb: Callable[[], Any],
        pause_cb: Callable[[], Any],
        resume_cb: Callable[[], Any],
        risk_update_cb: Callable[[str, float], Dict[str, Any]],
        query_metrics_cb: Callable[[], Dict[str, Any]],
    ) -> None:
        """Registra los callbacks de control del orquestador en el router."""
        self.router.register_command_handlers(
            kill_switch_cb=kill_switch_cb,
            pause_cb=pause_cb,
            resume_cb=resume_cb,
            risk_update_cb=risk_update_cb,
            query_metrics_cb=query_metrics_cb,
        )

    def register_harvest_handler(self, harvest_cb: Callable[[], Dict[str, Any]]) -> None:
        """Registra handler de tesorería."""
        self.router.register_harvest_handler(harvest_cb)

    async def notify(self, message: str) -> None:
        """Envía notificación a Telegram (o la acumula en memoria si es mock)."""
        if message not in self.mensajes_enviados:
            self.mensajes_enviados.append(message)
        if message not in self.router.notificaciones_push:
            self.router.notificaciones_push.append(message)
        if not self.mock_mode:
            await self._enviar_api_telegram(message)

    # --------------------------------------------------------------------------
    # NOTIFICACIONES PUSH AUTÓNOMAS DE NEGOCIO
    # --------------------------------------------------------------------------
    async def notificar_inicio(
        self,
        version: str = "CONTINUITY HFT BINANCE 1.0",
        balance_inicial: float = 10.0,
        mercados: Sequence[str] = (),
    ) -> str:
        """Alerta de arranque del orquestador y calibración de microestructura."""
        ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        mercados_str = ", ".join(mercados) if mercados else "Escaneo Universal (7 deportes)"
        msg = (
            f"🟢 <b>CONTINUITY HFT INICIADO</b> 🟢\n\n"
            f"⏰ <b>Hora:</b> {ahora}\n"
            f"🚀 <b>Versión:</b> {version}\n"
            f"💰 <b>Capital Inicial:</b> ${balance_inicial:.2f} USD\n"
            f"🎯 <b>Cobertura:</b> {mercados_str}\n"
            f"⚡ <b>Guardián Latencia:</b> &lt; 800 ms activo\n"
            f"🛡️ <b>Reglas de Oro:</b> GR1 (Spread &le; 0.03), GR2 (Suspended), GR3 (Top3 BID)"
        )
        await self.notify(msg)
        return msg

    async def notificar_cierre(
        self,
        balance_final: float,
        balance_inicial: float,
        total_trades: int,
        ganancia_neta: float,
    ) -> str:
        """Alerta de parada del sistema o cierre de sesión."""
        ahora = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        signo = "+" if ganancia_neta >= 0 else ""
        msg = (
            f"🔴 <b>CONTINUITY HFT DETENIDO</b> 🔴\n\n"
            f"⏰ <b>Hora Cierre:</b> {ahora}\n"
            f"💰 <b>Balance Final:</b> ${balance_final:.2f} USD\n"
            f"📈 <b>PnL Sesión:</b> {signo}${ganancia_neta:.2f} USD\n"
            f"🎯 <b>Operaciones Realizadas:</b> {total_trades}\n"
            f"🔒 <b>Órdenes Canceladas:</b> 100% liquidez en USDT."
        )
        await self.notify(msg)
        return msg

    async def notificar_resumen_periodico(
        self,
        horas: int,
        metricas: Dict[str, Any],
        balance_actual: float,
        latencia_promedio_ms: float = 0.0,
    ) -> str:
        """Reporte periódico autónomo cada 3 a 6 horas."""
        ahora = datetime.now(timezone.utc).strftime("%H:%M UTC")
        wr = metricas.get("win_rate", 0.0) * 100.0
        roi = metricas.get("roi", 0.0) * 100.0
        yield_pct = metricas.get("yield", 0.0) * 100.0
        trades = metricas.get("total_trades", 0)

        msg = (
            f"⏱️ <b>RESUMEN PERIÓDICO ({horas} HORAS)</b> [{ahora}]\n\n"
            f"💰 <b>Capital Acumulado:</b> ${balance_actual:.2f} USD\n"
            f"🎯 <b>Win Rate:</b> {wr:.1f}%\n"
            f"📊 <b>Total Trades:</b> {trades}\n"
            f"📈 <b>ROI:</b> {roi:.2f}% | <b>Yield:</b> {yield_pct:.2f}%\n"
            f"⚡ <b>Latencia Feed:</b> {latencia_promedio_ms:.1f} ms\n"
            f"🛡️ <b>Estado Disyuntor:</b> OPERATIVO NORMAL"
        )
        await self.notify(msg)
        return msg

    async def notificar_emergencia_circuit_breaker(
        self,
        motivo: str,
        detalles: Dict[str, Any],
    ) -> str:
        """Alerta crítica de activación del disyuntor de emergencia."""
        ahora = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        msg = (
            f"🚨 <b>DISYUNTOR DE EMERGENCIA DISPARADO</b> 🚨\n\n"
            f"⏰ <b>Hora:</b> {ahora}\n"
            f"⚠️ <b>Motivo:</b> {motivo}\n"
            f"🔍 <b>Detalles:</b> {json.dumps(detalles, default=str)}\n"
            f"🛑 <b>Acción:</b> Generación de órdenes bloqueada. Posiciones aseguradas."
        )
        await self.notify(msg)
        return msg

    async def notificar_inyeccion_capital(
        self,
        monto: float,
        nuevo_balance: float,
        info_validacion: Dict[str, Any],
    ) -> str:
        """Notificación de hito superado y capital inyectado."""
        msg = (
            f"🚀 <b>¡HITO DE CAPITAL SUPERADO!</b> 🚀\n\n"
            f"💵 <b>Inyección Autorizada:</b> +${monto:.2f} USD\n"
            f"💰 <b>Nuevo Balance:</b> ${nuevo_balance:.2f} USD\n"
            f"📊 <b>Validación Estadística:</b> N={info_validacion.get('n_trades')}, "
            f"p={info_validacion.get('p_value', 0.0):.4f}, Z={info_validacion.get('z_score', 0.0):.2f}"
        )
        await self.notify(msg)
        return msg

    async def notificar_cosecha_mxn(
        self,
        retiro_usd: float,
        retiro_mxn: float,
        reinversion_usd: float,
        nuevo_balance: float,
    ) -> str:
        """Notificación de cosecha mensual del 35% a MXN."""
        msg = (
            f"🌾 <b>COSECHA AUTÓNOMA A MXN EJECUTADA</b> 🌾\n\n"
            f"🇲🇽 <b>Liquidado a MXN (35%):</b> ${retiro_mxn:.2f} MXN (${retiro_usd:.2f} USD)\n"
            f"🔄 <b>Reinversión Compuesta:</b> ${reinversion_usd:.2f} USD\n"
            f"💰 <b>Balance Operativo Restante:</b> ${nuevo_balance:.2f} USD"
        )
        await self.notify(msg)
        return msg

    # --------------------------------------------------------------------------
    # CICLO DE VIDA Y TAREA ASÍNCRONA DE ESCUCHA (LISTENER TASK)
    # --------------------------------------------------------------------------
    async def start(self) -> None:
        """Inicia el ciclo asíncrono de escucha de comandos."""
        if self._running:
            return
        self._running = True
        logger.info("[TelegramBot] Listener iniciado.")

    async def stop(self) -> None:
        """Detiene el ciclo de escucha."""
        self._running = False
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
        logger.info("[TelegramBot] Listener detenido.")

    async def listener_loop(self) -> None:
        """
        Bucle asíncrono continuo de escucha de comandos.
        En producción consulta getUpdates de Telegram; en mock descansa sin consumir CPU.
        """
        await self.start()
        try:
            while self._running:
                if self.mock_mode:
                    await asyncio.sleep(self.poll_interval_s)
                    continue

                await self._poll_telegram_updates()
                await asyncio.sleep(self.poll_interval_s)
        except asyncio.CancelledError:
            pass
        finally:
            self._running = False

    # --------------------------------------------------------------------------
    # COMUNICACIÓN DE RED CON TELEGRAM BOT API (MODO PRODUCCIÓN)
    # --------------------------------------------------------------------------
    async def _enviar_api_telegram(self, texto: str) -> None:
        """Envío HTTP hacia la API oficial de Telegram."""
        if not (self.bot_token and self.chat_id):
            return
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": texto,
                "parse_mode": "HTML",
            }
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=5) as resp:
                    if resp.status != 200:
                        logger.warning(f"Error enviando mensaje Telegram: {resp.status}")
        except Exception as e:
            logger.debug(f"Excepción en envío de Telegram: {e}")

    async def _poll_telegram_updates(self) -> None:
        """Consulta actualizaciones pendientes en Telegram y las despacha al router."""
        if not (self.bot_token and self.chat_id):
            return
        try:
            import aiohttp
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {"offset": self._update_offset, "timeout": 2}
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        for update in data.get("result", []):
                            self._update_offset = max(self._update_offset, update["update_id"] + 1)
                            # Procesar mensaje de texto con validación de seguridad de chat_id
                            if "message" in update and "text" in update["message"]:
                                msg = update["message"]
                                sender_chat_id = str(msg.get("chat", {}).get("id", ""))
                                if self.chat_id and str(self.chat_id) and sender_chat_id != str(self.chat_id):
                                    logger.warning(
                                        f"Comando rechazado de remitente no autorizado: {sender_chat_id} (esperado: {self.chat_id})"
                                    )
                                    continue
                                txt = msg["text"]
                                resp_text = await self.router.procesar_mensaje(txt)
                                await self._enviar_api_telegram(resp_text)
                            # Procesar callback query de botón con validación de seguridad de chat_id
                            elif "callback_query" in update and "data" in update["callback_query"]:
                                cb = update["callback_query"]
                                sender_chat_id = str(cb.get("message", {}).get("chat", {}).get("id", ""))
                                if self.chat_id and str(self.chat_id) and sender_chat_id != str(self.chat_id):
                                    logger.warning(
                                        f"Callback rechazado de remitente no autorizado: {sender_chat_id} (esperado: {self.chat_id})"
                                    )
                                    continue
                                cb_data = cb["data"]
                                resp_text = await self.router.procesar_callback_query(cb_data)
                                await self._enviar_api_telegram(resp_text)
        except Exception as e:
            logger.debug(f"Error polling getUpdates: {e}")


# ==============================================================================
# 5. SIMULADOR HEADLESS PARA TESTS (MockTelegramClient)
# ==============================================================================

class MockTelegramClient:
    """
    Simulador de cliente Telegram para pruebas automatizadas e integración.
    Permite a los tests emitir comandos y clics de botones sin red ni credenciales.
    """

    def __init__(self):
        self.mensajes_enviados: List[str] = []
        self.alertas_recibidas: List[str] = []

    async def enviar_comando(
        self,
        comando: str,
        destinatario: Union[TelegramCommandRouter, TelegramBidireccionalBot],
    ) -> str:
        """Simula al operador enviando un comando al bot de Telegram."""
        self.mensajes_enviados.append(comando)
        router = (
            destinatario.router
            if isinstance(destinatario, TelegramBidireccionalBot)
            else destinatario
        )
        respuesta = await router.procesar_mensaje(comando)
        self.alertas_recibidas.append(respuesta)
        return respuesta

    async def pulsar_boton(
        self,
        callback_data: str,
        destinatario: Union[TelegramCommandRouter, TelegramBidireccionalBot],
    ) -> str:
        """Simula al operador pulsando un botón del Inline Keyboard."""
        router = (
            destinatario.router
            if isinstance(destinatario, TelegramBidireccionalBot)
            else destinatario
        )
        respuesta = await router.procesar_callback_query(callback_data)
        self.alertas_recibidas.append(respuesta)
        return respuesta

    async def simular_sesion_operador(
        self,
        comandos: Sequence[str],
        destinatario: Union[TelegramCommandRouter, TelegramBidireccionalBot],
    ) -> List[str]:
        """Ejecuta una secuencia ordenada de comandos de operador."""
        respuestas = []
        for cmd in comandos:
            resp = await self.enviar_comando(cmd, destinatario)
            respuestas.append(resp)
        return respuestas
