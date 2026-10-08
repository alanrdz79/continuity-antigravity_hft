# -*- coding: utf-8 -*-
"""
estrategias
===========
Paquete de Estrategias Cuantitativas para CONTINUITY HFT Binance:
- hft_engine: Motor HFT de 4 fases, 7 disciplinas deportivas, Estrategia A (Time Decay) y Estrategia B (Overreaction Hunting).
- swing_engine: Motor ortogonal de Swing Trading con cómputo CPU offloaded y gestión atómica de capital.
"""

from estrategias.hft_engine import (
    SportType,
    SportConfig,
    MatchLiveState,
    HftOrder,
    HftPosition,
    HftSignal,
    HFTEngine,
    SPORT_CONFIGS,
)
from estrategias.swing_engine import (
    SwingEngine,
    SwingPosition,
    CapitalReservationToken,
    AsyncCapitalGateway,
)

__all__ = [
    "SportType",
    "SportConfig",
    "MatchLiveState",
    "HftOrder",
    "HftPosition",
    "HftSignal",
    "HFTEngine",
    "SPORT_CONFIGS",
    "SwingEngine",
    "SwingPosition",
    "CapitalReservationToken",
    "AsyncCapitalGateway",
]
