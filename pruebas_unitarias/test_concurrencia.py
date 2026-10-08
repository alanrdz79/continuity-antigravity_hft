# -*- coding: utf-8 -*-
"""
==================================================================================
pruebas_unitarias.test_concurrencia | CONTINUITY HFT Binance
==================================================================================
Suite de Pruebas de Concurrencia Asíncrona sin Bloqueo ni Inanición de Bucle.

Verifica:
1. Ejecución no bloqueante concurrente entre el bucle HFT (micro-ticks de alta frecuencia)
   y el motor ortogonal de Swing Trading (análisis multi-hora / cálculo intensivo).
2. Garantía de Inanición Cero (Zero Event Loop Starvation):
   La latencia del latido del bucle de eventos (`asyncio`) se mantiene < 50 ms
   (muy por debajo del disyuntor de emergencia de 800 ms).
3. Thread-Safety y Atomicidad en la reserva de capital con `asyncio.Lock`.
4. Resiliencia ante cancelaciones y manejo de excepciones concurrentes.
"""

import asyncio
import time
import pytest
from typing import Dict, Any, List

from continuitis.microestructura_binance import (
    OrderBookSnapshot,
    MicroestructuraBinanceEngine,
    LatencyAndKillSwitchGuard,
)
from continuitis.riesgo_binance import EscudoFinancieroBinance


# ==============================================================================
# CLASES AUXILIARES DE SIMULACIÓN CONCURRENTE
# ==============================================================================

class MockAsyncRiskGateway:
    """Gateway de riesgo asíncrono seguro con bloqueo atómico."""
    def __init__(self, capital_inicial: float = 1000.0, max_cluster_exp: float = 0.15):
        self.lock = asyncio.Lock()
        self.balance = capital_inicial
        self.max_cluster_exp = max_cluster_exp
        self.capital_comprometido = 0.0
        self.trades_aprobados = 0

    async def reservar_capital(self, stake: float) -> bool:
        async with self.lock:
            # Evaluar techo de clúster del 15%
            max_permitido = self.balance * self.max_cluster_exp
            if (self.capital_comprometido + stake) <= max_permitido:
                self.capital_comprometido += stake
                self.trades_aprobados += 1
                return True
            return False

    async def liberar_capital(self, stake: float) -> None:
        async with self.lock:
            self.capital_comprometido = max(0.0, self.capital_comprometido - stake)


async def simular_hft_loop(
    engine: MicroestructuraBinanceEngine,
    gateway: MockAsyncRiskGateway,
    iteraciones: int,
    latencias_registradas: List[float],
    stop_event: asyncio.Event,
):
    """Bucle HFT de micro-ticks continuos."""
    for i in range(iteraciones):
        if stop_event.is_set():
            break

        t_start = time.perf_counter()
        snap = OrderBookSnapshot(
            symbol="HFT_TICK",
            bids=((0.50, 800.0),),
            asks=((0.52, 200.0),),
            timestamp_ms=int(time.time() * 1000),
            market_status="ACTIVE",
        )
        sig = engine.evaluar_snapshot(snap)
        if sig.autorizado:
            await gateway.reservar_capital(stake=10.0)
            await asyncio.sleep(0.002)  # 2 ms de espera cooperativa
            await gateway.liberar_capital(stake=10.0)

        t_end = time.perf_counter()
        latencias_registradas.append((t_end - t_start) * 1000.0)
        await asyncio.sleep(0.001)  # Ceder control al event loop


def calculo_pesado_swing_cpu(n: int) -> float:
    """Simula cálculo analítico de Swing en hilo separado."""
    total = 0.0
    for j in range(n):
        total += (j * 0.001) ** 0.5
    return total


async def simular_swing_loop(
    gateway: MockAsyncRiskGateway,
    iteraciones: int,
    swing_resultados: List[float],
    stop_event: asyncio.Event,
):
    """Bucle Swing ortogonal que ejecuta análisis pesado sin bloquear el event loop."""
    for _ in range(iteraciones):
        if stop_event.is_set():
            break

        # Descargar cómputo intensivo a un hilo de fondo vía asyncio.to_thread
        res = await asyncio.to_thread(calculo_pesado_swing_cpu, 50000)
        swing_resultados.append(res)

        # Reserva de capital para swing
        await gateway.reservar_capital(stake=25.0)
        await asyncio.sleep(0.01)  # Duración de posición swing
        await gateway.liberar_capital(stake=25.0)


# ==============================================================================
# TIER 1: FEATURE CONTRACT COVERAGE
# ==============================================================================

class TestConcurrenciaTier1FeatureCoverage:
    """Verificación de no-bloqueo y concurrencia entre HFT y Swing."""

    def test_concurrent_hft_and_swing_execution_completion(self):
        """
        Ambos bucles (HFT y Swing) deben ejecutarse en paralelo y completar
        todas sus iteraciones sin bloquearse mutuamente.
        """
        async def run_test():
            engine = MicroestructuraBinanceEngine()
            gateway = MockAsyncRiskGateway(capital_inicial=1000.0)
            stop_event = asyncio.Event()

            hft_latencias: List[float] = []
            swing_resultados: List[float] = []

            # Lanzar tareas concurrentes
            t_hft = asyncio.create_task(
                simular_hft_loop(engine, gateway, iteraciones=30, latencias_registradas=hft_latencias, stop_event=stop_event)
            )
            t_swing = asyncio.create_task(
                simular_swing_loop(gateway, iteraciones=5, swing_resultados=swing_resultados, stop_event=stop_event)
            )

            await asyncio.gather(t_hft, t_swing)

            assert len(hft_latencias) == 30
            assert len(swing_resultados) == 5
            assert gateway.trades_aprobados > 0

        asyncio.run(run_test())

    def test_zero_event_loop_starvation_guarantee(self):
        """
        Verifica que el event loop no sufre inanición:
        Un monitor de latido (heartbeat) mide la demora de despertar cada 5 ms.
        Si la demora máxima supera 50 ms, se consideraría riesgo de inanición.
        """
        async def run_test():
            delays: List[float] = []
            stop_monitor = asyncio.Event()

            async def heartbeat_monitor():
                while not stop_monitor.is_set():
                    t0 = time.perf_counter()
                    await asyncio.sleep(0.005)
                    t1 = time.perf_counter()
                    delay_ms = (t1 - t0 - 0.005) * 1000.0
                    delays.append(max(0.0, delay_ms))

            engine = MicroestructuraBinanceEngine()
            gateway = MockAsyncRiskGateway()

            t_monitor = asyncio.create_task(heartbeat_monitor())
            t_hft = asyncio.create_task(
                simular_hft_loop(engine, gateway, iteraciones=25, latencias_registradas=[], stop_event=stop_monitor)
            )
            t_swing = asyncio.create_task(
                simular_swing_loop(gateway, iteraciones=4, swing_resultados=[], stop_event=stop_monitor)
            )

            await asyncio.gather(t_hft, t_swing)
            stop_monitor.set()
            await t_monitor

            # La demora máxima del monitor no debe superar 50 ms (muy por debajo de los 800 ms de LatencyGuard)
            max_delay = max(delays) if delays else 0.0
            assert max_delay < 50.0, f"Inanición detectada: delay máximo={max_delay:.2f} ms"

        asyncio.run(run_test())

    def test_atomic_risk_gateway_prevents_race_conditions(self):
        """
        Múltiples tareas concurrentes intentan reservar capital simultáneamente.
        `asyncio.Lock` garantiza que la exposición total nunca exceda el 15% (150 USD de 1000 USD).
        """
        async def run_test():
            gateway = MockAsyncRiskGateway(capital_inicial=1000.0, max_cluster_exp=0.15)
            rechazos = 0

            async def cliente_intento(stake: float):
                nonlocal rechazos
                ok = await gateway.reservar_capital(stake)
                if ok:
                    # Verificar invariantemente que el capital nunca excede 150 USD
                    assert gateway.capital_comprometido <= 150.0 + 1e-9
                    await asyncio.sleep(0.005)
                    await gateway.liberar_capital(stake)
                else:
                    rechazos += 1

            # Lanzar 20 intentos simultáneos de 30 USD cada uno (total solicitado = 600 USD > 150 USD cap)
            tareas = [asyncio.create_task(cliente_intento(30.0)) for _ in range(20)]
            await asyncio.gather(*tareas)

            assert gateway.capital_comprometido == 0.0  # Todo el capital liberado al final
            assert rechazos > 0  # El techo del 15% rechazó el exceso adecuadamente

        asyncio.run(run_test())


# ==============================================================================
# TIER 2: BOUNDARY & CORNER CASES
# ==============================================================================

class TestConcurrenciaTier2BoundaryAndCorners:
    """Casos de estrés, cancelaciones abruptas y manejo de errores concurrentes."""

    def test_rapid_task_cancellation_graceful_cleanup(self):
        """
        Cancelar el bucle HFT o Swing de manera abrupta debe ser capturado limpiamente
        sin dejar bloqueado el bucle de eventos.
        """
        async def run_test():
            stop_event = asyncio.Event()
            engine = MicroestructuraBinanceEngine()
            gateway = MockAsyncRiskGateway()

            t_hft = asyncio.create_task(
                simular_hft_loop(engine, gateway, iteraciones=1000, latencias_registradas=[], stop_event=stop_event)
            )
            await asyncio.sleep(0.01)
            t_hft.cancel()

            with pytest.raises(asyncio.CancelledError):
                await t_hft

            assert t_hft.done() is True

        asyncio.run(run_test())

    def test_exception_in_one_task_does_not_corrupt_other(self):
        """
        Si una tarea falla con una excepción, la otra tarea debe continuar
        ejecutándose normalmente.
        """
        async def run_test():
            completado_hft = False

            async def tarea_con_fallo():
                await asyncio.sleep(0.005)
                raise ValueError("ERROR_SIMULADO_EN_FEED")

            async def tarea_hft_estable():
                nonlocal completado_hft
                for _ in range(10):
                    await asyncio.sleep(0.002)
                completado_hft = True

            t1 = asyncio.create_task(tarea_con_fallo())
            t2 = asyncio.create_task(tarea_hft_estable())

            # t1 falla
            with pytest.raises(ValueError, match="ERROR_SIMULADO_EN_FEED"):
                await t1

            # t2 completa exitosamente
            await t2
            assert completado_hft is True

        asyncio.run(run_test())

    def test_high_concurrency_empty_snapshots(self):
        """
        Inyectar 100 snapshots vacíos concurrentemente no genera bloqueos ni fugas de memoria.
        """
        async def run_test():
            engine = MicroestructuraBinanceEngine()

            async def procesar_vacio():
                snap = OrderBookSnapshot("EMPTY", (), (), 0, "ACTIVE")
                return engine.evaluar_snapshot(snap)

            tareas = [asyncio.create_task(procesar_vacio()) for _ in range(100)]
            resultados = await asyncio.gather(*tareas)

            assert len(resultados) == 100
            for r in resultados:
                assert r.autorizado is False
                assert r.motivo == "LIBRO_INCOMPLETO_O_VACIO"

        asyncio.run(run_test())


# ==============================================================================
# TIER 3: CROSS-FEATURE PAIRWISE COMBINATIONS
# ==============================================================================

class TestConcurrenciaTier3CrossFeatureCombinations:
    """Interacción concurrente entre Telegram Stop Signal y los bucles de trading."""

    def test_telegram_pause_signal_stops_concurrent_loops(self):
        """
        Un comando `/pause` o `/kill` recibido vía Telegram activa `stop_event`,
        deteniendo inmediatamente ambos bucles concurrentes.
        """
        async def run_test():
            engine = MicroestructuraBinanceEngine()
            gateway = MockAsyncRiskGateway()
            stop_event = asyncio.Event()

            hft_latencias: List[float] = []
            swing_resultados: List[float] = []

            t_hft = asyncio.create_task(
                simular_hft_loop(engine, gateway, iteraciones=500, latencias_registradas=hft_latencias, stop_event=stop_event)
            )
            t_swing = asyncio.create_task(
                simular_swing_loop(gateway, iteraciones=100, swing_resultados=swing_resultados, stop_event=stop_event)
            )

            # Simular comando Telegram /kill tras 15 ms
            await asyncio.sleep(0.015)
            stop_event.set()

            await asyncio.gather(t_hft, t_swing)

            # Ambas tareas se detuvieron tempranamente sin llegar a 500 ni 100 iteraciones
            assert len(hft_latencias) < 500
            assert len(swing_resultados) < 100

        asyncio.run(run_test())


# ==============================================================================
# TIER 4: REAL-WORLD APPLICATION SCENARIOS
# ==============================================================================

class TestConcurrenciaTier4RealWorldScenarios:
    """Simulación en tiempo real de sesión operativa de 100 ms continuos."""

    def test_continuous_multi_sport_concurrency_session(self):
        """
        Simula una ventana operativa de 50 ms donde múltiples deportes
        son evaluados de forma simultánea sin provocar degradación en la latencia.
        """
        async def run_test():
            engine = MicroestructuraBinanceEngine()
            gateway = MockAsyncRiskGateway(capital_inicial=5000.0)
            stop_event = asyncio.Event()

            deportes = ["SOCCER_EPL", "TENNIS_ATP", "NBA_BASKET", "ESPORTS_LOL"]
            metricas_deporte: Dict[str, List[float]] = {d: [] for d in deportes}

            async def runner_deporte(sym: str):
                for _ in range(15):
                    if stop_event.is_set():
                        break
                    t0 = time.perf_counter()
                    snap = OrderBookSnapshot(
                        symbol=sym,
                        bids=((0.55, 850.0),),
                        asks=((0.57, 150.0),),
                        timestamp_ms=int(time.time() * 1000),
                        market_status="ACTIVE",
                    )
                    sig = engine.evaluar_snapshot(snap)
                    if sig.autorizado:
                        await gateway.reservar_capital(10.0)
                        await asyncio.sleep(0.001)
                        await gateway.liberar_capital(10.0)
                    t1 = time.perf_counter()
                    metricas_deporte[sym].append((t1 - t0) * 1000.0)

            tareas = [asyncio.create_task(runner_deporte(d)) for d in deportes]
            await asyncio.gather(*tareas)

            for d in deportes:
                assert len(metricas_deporte[d]) == 15
                max_lat = max(metricas_deporte[d])
                assert max_lat < 100.0, f"Latencia excesiva en deporte {d}: {max_lat:.2f} ms"

        asyncio.run(run_test())
