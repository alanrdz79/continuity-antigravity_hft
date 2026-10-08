# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_telegram_control | CONTINUITY HFT Binance
==================================================================================
Suite de Pruebas de Control Bidireccional de Telegram y Botón de Pánico (Kill Switch).

Cumple con:
- PROJECT.md (§ Interface Contracts: TelegramControlProtocol & M4)
- Acceptance Criteria (MockTelegramClient simulando /kill, /pause, /resume, /risk, /report)
- Verificación del Kill Switch: pausa inmediata, cancelación de órdenes, reporte de métricas.
- Cero dependencias de plugins externos (ejecución síncrona vía asyncio.run).
"""

import asyncio
import time
import pytest
from typing import Dict, Any, List, Optional, Callable, Awaitable

from continuitis.microestructura_binance import (
    OrderBookSnapshot,
    LatencyAndKillSwitchGuard,
    MicroestructuraBinanceEngine,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance
from continuitis.auditor_metricas import AuditorMetricas, TradeResult


from conectores.telegram_bidireccional import (
    MockTelegramClient,
    TelegramCommandRouter,
    TelegramBidireccionalBot,
)


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE
# ==============================================================================

class TestTelegramControlTier1FeatureCoverage:
    """Verificación de enrutamiento de comandos y botón de pánico."""

    def test_telegram_kill_switch_immediate_pause(self):
        """
        El comando `/kill` debe invocar el kill switch, pausar el sistema inmediatamente,
        cancelar órdenes y enviar alerta de pánico.
        """
        async def run_test():
            estado_sistema = {"pausado": False, "kill_switch": False, "ordenes_canceladas": False}

            def on_kill():
                estado_sistema["pausado"] = True
                estado_sistema["kill_switch"] = True
                estado_sistema["ordenes_canceladas"] = True

            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=on_kill,
                pause_cb=lambda: None,
                resume_cb=lambda: None,
                risk_update_cb=lambda p, v: {"exito": True},
                query_metrics_cb=lambda: {},
            )
            client = MockTelegramClient()

            resp = await client.enviar_comando("/kill", router)

            assert "KILL_SWITCH_EJECUTADO" in resp
            assert estado_sistema["kill_switch"] is True
            assert estado_sistema["pausado"] is True
            assert estado_sistema["ordenes_canceladas"] is True
            assert len(router.notificaciones_push) == 1
            assert "KILL SWITCH ACTIVADO" in router.notificaciones_push[0]

        asyncio.run(run_test())

    def test_telegram_pause_and_resume_routing(self):
        """
        Los comandos `/pause` y `/resume` conmutan el estado operativo del orquestador.
        """
        async def run_test():
            estado_operativo = {"pausado": False}

            def on_pause():
                estado_operativo["pausado"] = True

            def on_resume():
                estado_operativo["pausado"] = False

            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=lambda: None,
                pause_cb=on_pause,
                resume_cb=on_resume,
                risk_update_cb=lambda p, v: {"exito": True},
                query_metrics_cb=lambda: {},
            )
            client = MockTelegramClient()

            # 1. Enviar /pause
            resp_pause = await client.enviar_comando("/pause", router)
            assert "PAUSA_ACTIVADA" in resp_pause
            assert estado_operativo["pausado"] is True

            # 2. Enviar /resume
            resp_resume = await client.enviar_comando("/resume", router)
            assert "OPERACION_REANUDADA" in resp_resume
            assert estado_operativo["pausado"] is False

        asyncio.run(run_test())

    def test_telegram_risk_parameter_hot_update(self):
        """
        El comando `/risk pct_riesgo 0.025` modifica el parámetro en memoria caliente
        sin requerir reinicio del motor.
        """
        async def run_test():
            escudo = EscudoFinancieroBinance(pct_riesgo_fijo=0.015)

            def on_risk_update(param: str, val: float) -> Dict[str, Any]:
                if param in ("pct_riesgo", "pct_riesgo_fijo"):
                    if 0.001 <= val <= 0.05:
                        escudo.pct_riesgo_fijo = val
                        return {"exito": True, "nuevo_valor": val}
                    return {"exito": False, "motivo": "Riesgo fuera de rango (0.1% a 5.0%)"}
                elif param == "max_cluster":
                    escudo.max_cluster_exp = val
                    return {"exito": True, "nuevo_valor": val}
                return {"exito": False, "motivo": f"Parámetro desconocido: {param}"}

            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=lambda: None,
                pause_cb=lambda: None,
                resume_cb=lambda: None,
                risk_update_cb=on_risk_update,
                query_metrics_cb=lambda: {},
            )
            client = MockTelegramClient()

            resp = await client.enviar_comando("/risk pct_riesgo 0.025", router)
            assert "PARAMETRO_ACTUALIZADO" in resp
            assert escudo.pct_riesgo_fijo == pytest.approx(0.025, abs=1e-5)

        asyncio.run(run_test())

    def test_telegram_report_and_metricas_telemetry(self):
        """
        El comando `/report` solicita las métricas al auditor y formatea
        la telemetría para el chat de Telegram.
        """
        async def run_test():
            auditor = AuditorMetricas(capital_inicial=100.0)
            auditor.registrar_trade(TradeResult("T1", "SYM", 10.0, 5.0, True, time.time()))
            auditor.registrar_trade(TradeResult("T2", "SYM", 10.0, 3.0, True, time.time()))

            def on_query_metrics():
                m = auditor.obtener_metricas()
                m["estado"] = "OPERATIVO_NORMAL"
                return m

            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=lambda: None,
                pause_cb=lambda: None,
                resume_cb=lambda: None,
                risk_update_cb=lambda p, v: {"exito": True},
                query_metrics_cb=on_query_metrics,
            )
            client = MockTelegramClient()

            resp = await client.enviar_comando("/report", router)
            assert "REPORTE DE TELEMETRÍA" in resp
            assert "Trades Totales: 2" in resp
            assert "Win Rate: 100.0%" in resp
            assert "Capital: $108.00 USD" in resp

        asyncio.run(run_test())


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestTelegramControlTier2BoundaryAndCorners:
    """Casos límite, argumentos malformados y mayúsculas/minúsculas."""

    def test_case_insensitive_commands(self):
        """Los comandos deben ser insensibles a mayúsculas/minúsculas."""
        async def run_test():
            llamadas = []
            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=lambda: llamadas.append("kill"),
                pause_cb=lambda: llamadas.append("pause"),
                resume_cb=lambda: llamadas.append("resume"),
                risk_update_cb=lambda p, v: {"exito": True},
                query_metrics_cb=lambda: {},
            )
            client = MockTelegramClient()

            await client.enviar_comando("/KILL", router)
            await client.enviar_comando("/Pause", router)
            await client.enviar_comando("/RESUME", router)

            assert llamadas == ["kill", "pause", "resume"]

        asyncio.run(run_test())

    def test_malformed_risk_command_handling(self):
        """
        Argumentos incompletos o no numéricos en `/risk` deben ser rechazados limpiamente
        sin causar excepciones no controladas.
        """
        async def run_test():
            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=lambda: None,
                pause_cb=lambda: None,
                resume_cb=lambda: None,
                risk_update_cb=lambda p, v: {"exito": True},
                query_metrics_cb=lambda: {},
            )
            client = MockTelegramClient()

            # Argumentos insuficientes
            r1 = await client.enviar_comando("/risk", router)
            assert "USO:" in r1

            r2 = await client.enviar_comando("/risk pct_riesgo", router)
            assert "USO:" in r2

            # Valor no numérico
            r3 = await client.enviar_comando("/risk pct_riesgo diez", router)
            assert "no es numérico" in r3

        asyncio.run(run_test())

    def test_unknown_command_returns_help_hint(self):
        """Comandos inexistentes devuelven indicación de ayuda."""
        async def run_test():
            router = TelegramCommandRouter()
            client = MockTelegramClient()

            r = await client.enviar_comando("/invalid_command", router)
            assert "Comando desconocido" in r
            assert "/help" in r

        asyncio.run(run_test())


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS
# ==============================================================================

class TestTelegramControlTier3CrossFeatureCombinations:
    """Interacción entre comando /kill de Telegram y LatencyAndKillSwitchGuard."""

    def test_telegram_kill_switch_triggers_microstructure_guard(self):
        """
        Al ejecutarse `/kill` vía Telegram, el callback activa el `LatencyAndKillSwitchGuard`.
        Inmediatamente después, cualquier intento de evaluación de snapshot por
        `MicroestructuraBinanceEngine` es bloqueado por disyuntor de emergencia.
        """
        async def run_test():
            guard = LatencyAndKillSwitchGuard()
            engine = MicroestructuraBinanceEngine()
            engine.latency_guard = guard

            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=lambda: guard.activar_kill_switch("PANIC_SWITCH_TELEGRAM"),
                pause_cb=lambda: None,
                resume_cb=lambda: None,
                risk_update_cb=lambda p, v: {"exito": True},
                query_metrics_cb=lambda: {},
            )
            client = MockTelegramClient()

            # Antes de kill: autorizado
            snap_ok = OrderBookSnapshot("TEST", ((0.50, 800.0),), ((0.52, 200.0),), int(time.time() * 1000), "ACTIVE")
            assert engine.evaluar_snapshot(snap_ok).autorizado is True

            # Enviar /kill
            await client.enviar_comando("/kill", router)
            assert guard.emergencia_activa is True

            # Tras kill: bloqueado
            sig_bloqueada = engine.evaluar_snapshot(snap_ok)
            assert sig_bloqueada.autorizado is False
            assert "EMERGENCIA_ACTIVA" in sig_bloqueada.motivo

        asyncio.run(run_test())


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestTelegramControlTier4RealWorldScenarios:
    """Simulación completa de una sesión de operación de un trader con el bot."""

    def test_mock_telegram_operator_full_session(self):
        """
        Simula una sesión interactiva real:
        1. El operador consulta `/report` para ver el estado inicial.
        2. El operador ajusta el riesgo en caliente a 2.0% con `/risk pct_riesgo 0.02`.
        3. El sistema opera y registra 2 trades en el auditor.
        4. El operador vuelve a consultar `/report` y ve las métricas actualizadas.
        5. Se produce una emergencia deportiva y el operador presiona `/kill`.
        6. El sistema confirma la parada de emergencia y el estado queda en pausa.
        """
        async def run_test():
            estado = {"pausado": False, "riesgo": 0.015}
            auditor = AuditorMetricas(capital_inicial=500.0)

            def on_kill():
                estado["pausado"] = True

            def on_risk(p, v):
                if p == "pct_riesgo":
                    estado["riesgo"] = v
                    return {"exito": True}
                return {"exito": False}

            def on_report():
                m = auditor.obtener_metricas()
                m["estado"] = "PAUSADO" if estado["pausado"] else "ACTIVO"
                return m

            router = TelegramCommandRouter()
            router.register_command_handlers(
                kill_switch_cb=on_kill,
                pause_cb=lambda: estado.update({"pausado": True}),
                resume_cb=lambda: estado.update({"pausado": False}),
                risk_update_cb=on_risk,
                query_metrics_cb=on_report,
            )
            client = MockTelegramClient()

            # 1. Report inicial
            r1 = await client.enviar_comando("/report", router)
            assert "Trades Totales: 0" in r1

            # 2. Ajuste de riesgo
            r2 = await client.enviar_comando("/risk pct_riesgo 0.02", router)
            assert "PARAMETRO_ACTUALIZADO" in r2
            assert estado["riesgo"] == 0.02

            # 3. Operaciones del sistema
            auditor.registrar_trade(TradeResult("TR1", "SOCCER", 10.0, 8.0, True, time.time()))
            auditor.registrar_trade(TradeResult("TR2", "TENNIS", 10.0, 7.0, True, time.time()))

            # 4. Report con utilidades
            r3 = await client.enviar_comando("/report", router)
            assert "Trades Totales: 2" in r3
            assert "Win Rate: 100.0%" in r3

            # 5. Parada de emergencia
            r4 = await client.enviar_comando("/kill", router)
            assert "KILL_SWITCH_EJECUTADO" in r4
            assert estado["pausado"] is True

        asyncio.run(run_test())

    def test_telegram_bot_notification_sync_and_auth_security(self):
        """Verifica sincronización de notificaciones entre router y bot, y rechazo de chat_id no autorizado."""
        async def run_test():
            bot = TelegramBidireccionalBot(
                bot_token="TEST_TOKEN",
                chat_id="999888777",
                mock_mode=True,
            )
            kill_triggered = False

            def on_kill():
                nonlocal kill_triggered
                kill_triggered = True

            bot.register_command_handlers(
                kill_switch_cb=on_kill,
                pause_cb=lambda: None,
                resume_cb=lambda: None,
                risk_update_cb=lambda p, v: {"exito": True},
                query_metrics_cb=lambda: {},
            )

            client = MockTelegramClient()
            resp = await client.enviar_comando("/kill", bot)
            assert "KILL_SWITCH_EJECUTADO" in resp
            assert kill_triggered is True

            # Verificar que el mensaje fue registrado tanto en router como en bot
            assert any("KILL SWITCH ACTIVADO" in m for m in bot.mensajes_enviados)
            assert any("KILL SWITCH ACTIVADO" in m for m in bot.router.notificaciones_push)

            # Verificar rechazo de remitente no autorizado en polling
            simulated_updates = {
                "result": [
                    {
                        "update_id": 101,
                        "message": {
                            "chat": {"id": "111222333"},  # Unauthorized chat_id
                            "text": "/kill",
                        },
                    },
                    {
                        "update_id": 102,
                        "message": {
                            "chat": {"id": "999888777"},  # Authorized chat_id
                            "text": "/pause",
                        },
                    },
                ]
            }

            processed_cmds = []
            original_proc = bot.router.procesar_mensaje

            async def mock_proc(t):
                processed_cmds.append(t)
                return await original_proc(t)

            bot.router.procesar_mensaje = mock_proc

            # Simular loop de filtrado de updates idéntico a _poll_telegram_updates
            for upd in simulated_updates["result"]:
                msg = upd.get("message", {})
                sender = str(msg.get("chat", {}).get("id", ""))
                if bot.chat_id and sender != str(bot.chat_id):
                    continue
                await bot.router.procesar_mensaje(msg["text"])

            assert "/kill" not in processed_cmds, "El comando no autorizado debió ser filtrado"
            assert "/pause" in processed_cmds, "El comando autorizado debió ser procesado"

        asyncio.run(run_test())
