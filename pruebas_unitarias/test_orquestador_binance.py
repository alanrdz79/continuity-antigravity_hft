# -*- coding: utf-8 -*-
"""
pruebas_unitarias.test_orquestador_binance
==========================================
Suite Integral de Verificación del Orquestador Continuo HFT_BINANCE.py
y Control Bidireccional de Telegram.

Estructura de 4 Niveles (4-Tier Test Architecture):
- Tier 1: Cobertura de Características y Contratos de Interfaces (Orquestación, Tareas, Comandos).
- Tier 2: Casos Límite y Esquinas (Latencia excesiva, Mercado Suspendido, Spread dilatado, Techo Clúster).
- Tier 3: Interacciones Cruzadas entre Módulos (Telegram Kill Switch -> Guardia Microestructura -> Cancelación de Órdenes).
- Tier 4: Simulación de Sesión Completa en Entorno Real.
"""

import asyncio
import time
import pytest
from typing import Dict, Any, List

from orquestadores_principales.HFT_BINANCE import (
    ContinuityHFTBinanceOrchestrator,
    BinanceAsyncConnector,
    TesoreriaBinance,
)
from conectores.telegram_bidireccional import MockTelegramClient
from continuitis.microestructura_binance import OrderBookSnapshot
from continuitis.auditor_metricas import TradeResult


# ==============================================================================
# TIER 1: FEATURE COVERAGE & CONTRACT TESTS
# ==============================================================================

class TestOrchestratorTier1FeatureCoverage:
    """Verificación de inicialización, componentes y ciclo de vida de tareas."""

    def test_orchestrator_initialization_and_component_wiring(self):
        """Verifica que todos los submódulos estén instanciados y coordinados."""
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT", "TENNIS_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        assert orch.capital_inicial == 100.0
        assert orch.mock_mode is True
        assert len(orch.symbols) == 2
        assert "SOCCER_PRED_USDT" in orch.symbols

        # Submódulos conectados
        assert orch.binance_client is not None
        assert orch.micro_engine is not None
        assert orch.risk_engine is not None
        assert orch.tesoreria is not None
        assert orch.auditor is not None
        assert orch.hft_engine is not None
        assert orch.swing_engine is not None
        assert orch.telegram_bot is not None
        assert orch.capital_gateway is not None

        # Estado inicial
        assert orch.is_running is False
        assert orch.is_paused is False
        assert orch.kill_switch_triggered is False

    def test_orchestrator_start_and_clean_stop_lifecycle(self):
        """Verifica el arranque concurrente de las tareas y su detención limpia."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=50.0,
                mock_mode=True,
                hft_cycle_interval_s=0.01,
                swing_cycle_interval_s=0.02,
                summary_interval_s=0.05,
            )

            # Iniciar orquestador
            await orch.start()
            assert orch.is_running is True
            assert len(orch._tasks) == 5
            for t in orch._tasks:
                assert not t.done()

            # Permitir unos ciclos de ejecución
            await asyncio.sleep(0.08)

            # Detener orquestador limpiamente
            await orch.stop()
            assert orch.is_running is False
            for t in orch._tasks:
                assert t.done()

        asyncio.run(run_test())

    def test_step_orderbook_cycle_depth_and_latency_guard(self):
        """Verifica que el ciclo de order book actualice el libro en RAM y el guardián de latencia."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )

            snap = await orch.step_orderbook_cycle("SOCCER_PRED_USDT")
            assert snap.is_valid is True
            assert snap.symbol == "SOCCER_PRED_USDT"
            assert snap.market_status == "ACTIVE"

            # Verificar que el guardián de latencia registra pulso
            guard_ok, motivo = orch.micro_engine.latency_guard.autorizacion_disparo()
            assert guard_ok is True
            assert motivo == "AUTORIZADO"

        asyncio.run(run_test())

    def test_step_hft_cycle_execution_and_treasury_accounting(self):
        """Verifica la ejecución de micro-scalp HFT, reserva de capital y registro de trade."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )

            # Preparar libro con desequilibrio > 80% (I >= 0.60) y spread <= 0.03
            ts = int(time.time() * 1000)
            orch.binance_client.actualizar_libro(
                symbol="SOCCER_PRED_USDT",
                bids=((0.50, 900.0), (0.49, 300.0), (0.48, 200.0)),
                asks=((0.52, 100.0), (0.53, 50.0)),
                timestamp_ms=ts,
                market_status="ACTIVE",
            )

            balance_previo = orch.tesoreria.balance
            trades_previos = orch.auditor.total_trades

            senal = await orch.step_hft_cycle("SOCCER_PRED_USDT")
            assert senal is not None
            assert senal.authorized is True
            assert senal.action in ("LIMIT_BUY", "MARKET_BUY", "BUY_LIMIT", "BUY_MARKET", "BUY")

            # Trade registrado y balance incrementado por el micro-tick capturado
            assert orch.auditor.total_trades == trades_previos + 1
            assert orch.tesoreria.balance > balance_previo

        asyncio.run(run_test())

    def test_step_swing_cycle_non_blocking_execution(self):
        """Verifica que el ciclo Swing ejecute análisis Monte Carlo sin bloquear."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=200.0,
                mock_mode=True,
            )

            # Ejecutar paso de swing
            analysis = await orch.step_swing_cycle("SOCCER_PRED_USDT")
            assert analysis is not None
            assert analysis.symbol == "SOCCER_PRED_USDT"
            assert analysis.trend_direction in ("BULLISH", "BEARISH", "NEUTRAL")
            assert 0.0 <= analysis.monte_carlo_win_prob <= 1.0

        asyncio.run(run_test())

    def test_telegram_control_report_and_status_commands(self):
        """Verifica respuestas de los comandos /status, /report y /harvest vía MockTelegramClient."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )
            client = MockTelegramClient()

            # 1. Comando /report
            resp_report = await client.enviar_comando("/report", orch.telegram_bot)
            assert "REPORTE DE TELEMETRÍA" in resp_report
            assert "Trades Totales: 0" in resp_report
            assert "Capital: $100.00 USD" in resp_report
            assert "Estado: ACTIVO" in resp_report

            # 2. Comando /harvest
            resp_harvest = await client.enviar_comando("/harvest", orch.telegram_bot)
            assert "ESTADO DE TESORERÍA" in resp_harvest
            assert "Balance Actual: $100.00 USD" in resp_harvest

        asyncio.run(run_test())

    def test_telegram_control_pause_and_resume_commands(self):
        """Verifica que /pause y /resume suspendan y reactiven la generación de órdenes."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )
            client = MockTelegramClient()

            # Enviar /pause
            resp_pause = await client.enviar_comando("/pause", orch.telegram_bot)
            assert "PAUSA_ACTIVADA" in resp_pause
            assert orch.is_paused is True

            # Con el orquestador pausado, step_hft_cycle debe retornar None
            res = await orch.step_hft_cycle("SOCCER_PRED_USDT")
            assert res is None

            # Enviar /resume
            resp_resume = await client.enviar_comando("/resume", orch.telegram_bot)
            assert "OPERACION_REANUDADA" in resp_resume
            assert orch.is_paused is False

        asyncio.run(run_test())

    def test_telegram_inline_buttons_handling(self):
        """Verifica la interacción mediante pulsación de botones en el teclado en línea."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )
            client = MockTelegramClient()

            # Pulsar botón cmd_pause
            r1 = await client.pulsar_boton("cmd_pause", orch.telegram_bot)
            assert "PAUSA_ACTIVADA" in r1
            assert orch.is_paused is True

            # Pulsar botón cmd_resume
            r2 = await client.pulsar_boton("cmd_resume", orch.telegram_bot)
            assert "OPERACION_REANUDADA" in r2
            assert orch.is_paused is False

            # Pulsar botón cmd_report
            r3 = await client.pulsar_boton("cmd_report", orch.telegram_bot)
            assert "REPORTE DE TELEMETRÍA" in r3

            # Pulsar botón cmd_params
            r4 = await client.pulsar_boton("cmd_params", orch.telegram_bot)
            assert "PARÁMETROS CONFIGURABLES" in r4

            # Pulsar botón cmd_chart
            r5 = await client.pulsar_boton("cmd_chart", orch.telegram_bot)
            assert "GRÁFICA DE RENDIMIENTO" in r5

        asyncio.run(run_test())


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestOrchestratorTier2BoundaryAndCorners:
    """Condiciones límite, bloqueos por reglas de oro y saturación de clúster."""

    def test_high_feed_latency_triggers_circuit_breaker(self):
        """Si la latencia del feed supera 800 ms, el disyuntor bloquea el disparo de órdenes."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )

            # Inyectar snapshot con timestamp desactualizado (>800 ms de antigüedad)
            ts_antiguo = int((time.time() - 2.0) * 1000)
            orch.binance_client.actualizar_libro(
                symbol="SOCCER_PRED_USDT",
                bids=((0.50, 900.0),),
                asks=((0.52, 100.0),),
                timestamp_ms=ts_antiguo,
                market_status="ACTIVE",
            )

            await orch.step_orderbook_cycle("SOCCER_PRED_USDT")

            # El guardián debe haber entrado en estado de emergencia
            guard_ok, motivo = orch.micro_engine.latency_guard.autorizacion_disparo()
            assert guard_ok is False
            assert "LATENCIA_EXCESIVA" in motivo

            # step_hft_cycle no debe emitir orden aprobada
            senal = await orch.step_hft_cycle("SOCCER_PRED_USDT")
            assert senal is not None
            assert senal.authorized is False
            assert "LATENCIA_EXCESIVA" in senal.reason

        asyncio.run(run_test())

    def test_market_status_suspended_golden_rule_2(self):
        """Si Binance reporta estado 'SUSPENDED', se bloquean órdenes de inmediato (Regla de Oro 2)."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )

            ts = int(time.time() * 1000)
            orch.binance_client.actualizar_libro(
                symbol="SOCCER_PRED_USDT",
                bids=((0.50, 900.0),),
                asks=((0.52, 100.0),),
                timestamp_ms=ts,
                market_status="SUSPENDED",
            )

            await orch.step_orderbook_cycle("SOCCER_PRED_USDT")

            senal = await orch.step_hft_cycle("SOCCER_PRED_USDT")
            assert senal is not None
            assert senal.authorized is False
            assert "MERCADO_SUSPENDIDO" in senal.reason

        asyncio.run(run_test())

    def test_excessive_spread_golden_rule_1_rejection(self):
        """Spread > $0.03 debe rechazar la orden por Regla de Oro 1."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )

            ts = int(time.time() * 1000)
            # Spread = 0.55 - 0.50 = 0.05 > 0.03
            orch.binance_client.actualizar_libro(
                symbol="SOCCER_PRED_USDT",
                bids=((0.50, 900.0),),
                asks=((0.55, 100.0),),
                timestamp_ms=ts,
                market_status="ACTIVE",
            )

            senal = await orch.step_hft_cycle("SOCCER_PRED_USDT")
            assert senal is not None
            assert senal.authorized is False
            assert "SPREAD_EXCESIVO" in senal.reason

        asyncio.run(run_test())

    def test_cluster_cap_15_percent_saturation(self):
        """Bloqueo de nuevas órdenes cuando el capital comprometido alcanza el 15% del total."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )

            # Saturar la pasarela de capital al 15% ($15.00)
            token = await orch.capital_gateway.reservar_capital(
                stake=15.0,
                strategy_id="EXTERNAL_ALLOCATION",
                symbol="SOCCER_PRED_USDT",
            )
            assert token is not None
            assert orch.capital_gateway.capital_disponible_cluster == 0.0

            # Intentar reservar cualquier capital adicional debe ser rechazado
            token2 = await orch.capital_gateway.reservar_capital(
                stake=1.0,
                strategy_id="HFT_PHASE_1_OBI",
                symbol="SOCCER_PRED_USDT",
            )
            assert token2 is None

        asyncio.run(run_test())


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS
# ==============================================================================

class TestOrchestratorTier3CrossFeatureCombinations:
    """Interacción entre Telegram, Microestructura, Riesgo y Tesorería."""

    def test_telegram_kill_switch_triggers_full_orchestrator_freeze(self):
        """
        Al enviar `/kill` por Telegram:
        1. Se activa el disyuntor de emergencia en Microestructura.
        2. El orquestador entra en estado de pausa y kill switch.
        3. Se cancelan las órdenes en el exchange.
        4. Toda llamada posterior a step_hft_cycle retorna None.
        """
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )
            client = MockTelegramClient()

            resp = await client.enviar_comando("/kill", orch.telegram_bot)
            assert "KILL_SWITCH_EJECUTADO" in resp
            assert orch.kill_switch_triggered is True
            assert orch.is_paused is True
            assert orch.micro_engine.latency_guard.emergencia_activa is True

            # Ciclo HFT congelado
            res = await orch.step_hft_cycle("SOCCER_PRED_USDT")
            assert res is None

            # Notificación push emitida
            assert any("KILL SWITCH ACTIVADO" in m for m in orch.telegram_bot.mensajes_enviados)

        asyncio.run(run_test())

    def test_hot_risk_update_modifies_live_parameters(self):
        """El comando `/risk pct_riesgo 0.02` actualiza los parámetros en caliente en el motor."""
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )
            client = MockTelegramClient()

            assert orch.risk_engine.pct_riesgo_fijo == 0.015

            resp = await client.enviar_comando("/risk pct_riesgo 0.025", orch.telegram_bot)
            assert "PARAMETRO_ACTUALIZADO" in resp
            assert orch.risk_engine.pct_riesgo_fijo == 0.025

            # Modificar max_cluster
            resp_cluster = await client.enviar_comando("/risk max_cluster 0.20", orch.telegram_bot)
            assert "PARAMETRO_ACTUALIZADO" in resp_cluster
            assert orch.risk_engine.max_cluster_exp == 0.20
            assert orch.capital_gateway.max_cluster_exp == 0.20

        asyncio.run(run_test())

    def test_losing_streak_attenuation_applied_in_orchestrator(self):
        """Verifica que rachas de pérdidas consecutivas atenúen el tamaño de posición (0.85^n)."""
        orch = ContinuityHFTBinanceOrchestrator(
            symbols=["SOCCER_PRED_USDT"],
            capital_inicial=100.0,
            mock_mode=True,
        )

        assert orch.risk_engine.factor_racha == 1.0

        # Registrar 2 pérdidas consecutivas
        orch.risk_engine.registrar_resultado(False)
        orch.risk_engine.registrar_resultado(False)

        assert orch.risk_engine.consecutive_losses == 2
        assert orch.risk_engine.factor_racha == pytest.approx(0.85 ** 2, abs=1e-5)

        # Victoria resetea a 1.0
        orch.risk_engine.registrar_resultado(True)
        assert orch.risk_engine.factor_racha == 1.0


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestOrchestratorTier4RealWorldScenarios:
    """Simulación integral de una sesión de operación de trading."""

    def test_full_trading_session_workflow(self):
        """
        Simula una sesión de operación completa:
        1. Inicialización y notificación de inicio en Telegram.
        2. Configuración de libros de órdenes activos.
        3. Ejecución de varios ciclos HFT y Swing.
        4. Consulta de telemetría /report vía Telegram.
        5. Ajuste de riesgo en caliente.
        6. Ejecución de corte o auditoría de tesorería.
        7. Cierre limpio con notificación final.
        """
        async def run_test():
            orch = ContinuityHFTBinanceOrchestrator(
                symbols=["SOCCER_PRED_USDT", "TENNIS_PRED_USDT"],
                capital_inicial=100.0,
                mock_mode=True,
            )
            client = MockTelegramClient()

            # 1. Arranque
            await orch.start()
            assert orch.is_running is True

            # 2. Configurar libros favorables
            ts = int(time.time() * 1000)
            orch.binance_client.actualizar_libro(
                symbol="SOCCER_PRED_USDT",
                bids=((0.50, 850.0), (0.49, 200.0)),
                asks=((0.52, 120.0),),
                timestamp_ms=ts,
            )
            orch.binance_client.actualizar_libro(
                symbol="TENNIS_PRED_USDT",
                bids=((0.60, 700.0), (0.59, 200.0)),
                asks=((0.62, 100.0),),
                timestamp_ms=ts,
            )

            # 3. Ejecutar 3 ciclos HFT
            for _ in range(3):
                await orch.step_hft_cycle("SOCCER_PRED_USDT")
                await orch.step_hft_cycle("TENNIS_PRED_USDT")

            # 4. Consulta de métricas
            r_rep = await client.enviar_comando("/report", orch.telegram_bot)
            assert "REPORTE DE TELEMETRÍA" in r_rep
            assert orch.auditor.total_trades >= 2

            # 5. Ajuste de riesgo
            r_risk = await client.enviar_comando("/risk pct_riesgo 0.02", orch.telegram_bot)
            assert "PARAMETRO_ACTUALIZADO" in r_risk
            assert orch.risk_engine.pct_riesgo_fijo == 0.02

            # 6. Parada limpia del sistema
            await orch.stop()
            assert orch.is_running is False

            # Verificar que se emitió notificación de cierre
            assert any("CONTINUITY HFT DETENIDO" in m for m in orch.telegram_bot.mensajes_enviados)

        asyncio.run(run_test())
