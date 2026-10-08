# -*- coding: utf-8 -*-
"""
==================================================================================
continuitis.microestructura | CONTINUITY
==================================================================================
[v7.1-MICRO] Capa de Microestructura de Mercado.

Calcula VWAP (Precio Medio Ponderado por Volumen), descuenta comisiones
reales del exchange del EV, y determina la estrategia Maker/Taker
óptima según el contexto de ejecución (pre-match vs in-play).

Principio de diseño:
  Todo parámetro relacionado con capital se calcula del balance real
  de la cuenta vía Kelly fraccionado. Cero constantes absolutas de capital.
"""

from .constantes import (
    MB_COMMISSION_RATE,
    MB_VWAP_SLIPPAGE_MAX,
    MB_LIQUIDITY_RATIO_MIN,
    MB_TAKER_DELAY_INPLAY_SEC,
    _safe_float,
)
import logging
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("CONTINUITY.Microestructura")


# ==============================================================================
# CALCULADOR VWAP — Precio Medio Ponderado por Volumen
# ==============================================================================
class CalculadorVWAP:
    """
    Recibe el libro de órdenes expandido (price-mode=expanded) y calcula
    el precio real que pagaríamos al barrer un stake determinado.

    PROBLEMA QUE RESUELVE:
      El 'best price' visible (primer nivel del libro) solo representa
      una fracción de la liquidez disponible. Si el stake Kelly supera
      ese volumen, la orden consume niveles sucesivos a precios peores.
      Sin VWAP, el bot sobreestima el EV real porque asume que todo el
      stake se ejecuta al best price.

    MATEMÁTICA:
      VWAP = Σ(odds_i × volumen_consumido_i) / Σ(volumen_consumido_i)
      slippage = |VWAP - best_price| / best_price
    """

    @staticmethod
    def calcular(
        libro_precios: List[Dict], stake_kelly: float
    ) -> Tuple[float, float, float, int]:
        """
        Recorre los niveles de profundidad del libro y calcula cuánto
        pagaríamos realmente si barriéramos 'stake_kelly' de liquidez.

        Parámetros
        ----------
        libro_precios : lista de dicts con claves 'odds' y 'available-amount'
                        ordenados por mejor cuota primero.
                        Ejemplo: [{"odds": 2.50, "available-amount": 100.0}, ...]
        stake_kelly   : monto que el Kelly fraccionado determinó apostar.

        Retorna
        -------
        (vwap, slippage_pct, liquidez_total, niveles_consumidos)
          vwap              : precio medio ponderado real
          slippage_pct      : diferencia porcentual vs best price
          liquidez_total    : suma de liquidez disponible en el lado
          niveles_consumidos: cuántos escalones del libro se barren
        """
        stake_kelly = _safe_float(stake_kelly) or 0.0
        if stake_kelly <= 0 or not libro_precios:
            return 0.0, 0.0, 0.0, 0

        liquidez_total = sum(
            _safe_float(p.get("available-amount", 0)) or 0.0
            for p in libro_precios
        )

        if liquidez_total <= 0:
            return 0.0, 1.0, 0.0, 0  # slippage = 100% si no hay liquidez

        # Best price = primer nivel
        best_price = _safe_float(libro_precios[0].get("odds", 0)) or 0.0
        if best_price <= 1.0:
            return 0.0, 1.0, liquidez_total, 0

        # Recorrer niveles consumiendo liquidez
        restante = stake_kelly
        suma_ponderada = 0.0
        volumen_total_consumido = 0.0
        niveles = 0

        for nivel in libro_precios:
            odds_nivel = _safe_float(nivel.get("odds", 0)) or 0.0
            vol_nivel = _safe_float(nivel.get("available-amount", 0)) or 0.0

            if odds_nivel <= 1.0 or vol_nivel <= 0:
                continue

            consumido = min(restante, vol_nivel)
            suma_ponderada += odds_nivel * consumido
            volumen_total_consumido += consumido
            restante -= consumido
            niveles += 1

            if restante <= 0:
                break

        if volumen_total_consumido <= 0:
            return 0.0, 1.0, liquidez_total, 0

        vwap = suma_ponderada / volumen_total_consumido

        # Slippage: diferencia porcentual entre VWAP y best price
        # Para BACK: VWAP < best_price es peor (cuota menor)
        # Para LAY: VWAP > best_price es peor (cuota mayor)
        # Usamos valor absoluto para generalizar
        slippage_pct = abs(vwap - best_price) / best_price

        return (
            round(vwap, 4),
            round(slippage_pct, 6),
            round(liquidez_total, 2),
            niveles,
        )

    @staticmethod
    def ajustar_stake_por_liquidez(
        stake_kelly: float, liquidez_total: float
    ) -> float:
        """
        Reduce el stake si la liquidez del mercado es insuficiente.

        Regla: liquidez mínima = MB_LIQUIDITY_RATIO_MIN × stake.
        Si no se cumple, reduce el stake proporcionalmente.

        Retorna 0.0 si la liquidez es tan baja que el stake resultante
        sería menor que el 10% del stake original (no vale la pena).
        """
        stake_kelly = _safe_float(stake_kelly) or 0.0
        liquidez_total = _safe_float(liquidez_total) or 0.0

        if stake_kelly <= 0:
            return 0.0

        if liquidez_total <= 0:
            return 0.0

        # ¿Hay suficiente liquidez?
        if liquidez_total >= stake_kelly * MB_LIQUIDITY_RATIO_MIN:
            return stake_kelly  # Sin reducción

        # Reducir proporcionalmente
        stake_ajustado = liquidez_total / MB_LIQUIDITY_RATIO_MIN

        # Si el ajuste reduce el stake a menos del 10% del original, rechazar
        if stake_ajustado < stake_kelly * 0.10:
            return 0.0

        return round(stake_ajustado, 2)


# ==============================================================================
# AJUSTADOR DE COMISIONES — EV Neto Post-Exchange
# ==============================================================================
class AjustadorComisiones:
    """
    Descuenta la comisión real de Matchbook Exchange del cálculo de EV.

    PROBLEMA QUE RESUELVE:
      Matchbook cobra el 2% (MB_COMMISSION_RATE) sobre las GANANCIAS NETAS,
      no sobre el stake. Sin descontarlo, el bot puede aprobar apuestas
      donde el EV bruto es +3% pero el EV neto (post-comisión) es +1%
      o incluso negativo con cuotas bajas.

    ESTRUCTURA DE COMISIÓN:
      - Si ganas: pagas comisión sobre (pago - stake) = (cuota - 1) × stake
      - Si pierdes: no pagas comisión
      - Cuota neta efectiva = 1 + (cuota_bruta - 1) × (1 - comisión)
    """

    @staticmethod
    def cuota_neta(cuota_bruta: float, comision: float = MB_COMMISSION_RATE) -> float:
        """
        Calcula la cuota efectiva después de descontar la comisión del exchange.

        cuota_neta = 1 + (cuota_bruta - 1) × (1 - comisión)

        Ejemplo:
          cuota_bruta = 3.00, comisión = 0.02
          cuota_neta = 1 + 2.00 × 0.98 = 2.96
        """
        cuota_bruta = _safe_float(cuota_bruta) or 0.0
        if cuota_bruta <= 1.0:
            return cuota_bruta
        return 1.0 + (cuota_bruta - 1.0) * (1.0 - comision)

    @staticmethod
    def ev_neto(
        prob: float, cuota_bruta: float, comision: float = MB_COMMISSION_RATE
    ) -> float:
        """
        Calcula el Expected Value neto descontando la comisión del exchange.

        EV_neto = prob × cuota_neta - 1
               = prob × [1 + (cuota_bruta - 1) × (1 - comisión)] - 1

        Retorna float (positivo = valor esperado positivo post-comisión).
        """
        prob = _safe_float(prob) or 0.0
        c_neta = AjustadorComisiones.cuota_neta(cuota_bruta, comision)
        return round(prob * c_neta - 1.0, 6)

    @staticmethod
    def ev_bruto_vs_neto(
        prob: float, cuota_bruta: float, comision: float = MB_COMMISSION_RATE
    ) -> Dict:
        """
        Retorna un diccionario comparativo de EV bruto vs neto para logging.
        """
        prob = _safe_float(prob) or 0.0
        cuota_bruta = _safe_float(cuota_bruta) or 0.0
        ev_bruto = prob * cuota_bruta - 1.0 if cuota_bruta > 1.0 else 0.0
        ev_net = AjustadorComisiones.ev_neto(prob, cuota_bruta, comision)
        return {
            "ev_bruto": round(ev_bruto, 6),
            "ev_neto": round(ev_net, 6),
            "comision_aplicada": comision,
            "cuota_bruta": cuota_bruta,
            "cuota_neta": round(AjustadorComisiones.cuota_neta(cuota_bruta, comision), 4),
            "diferencia_ev": round(ev_bruto - ev_net, 6),
        }


# ==============================================================================
# ESTRATEGIA MAKER/TAKER — Ejecución Inteligente In-Play
# ==============================================================================
class EstrategiaMakerTaker:
    """
    Decide si colocar una orden como Maker (pasiva) o Taker (agresiva)
    según el contexto de ejecución.

    PROBLEMA QUE RESUELVE:
      Matchbook aplica un retardo de 5-10 segundos (delayed) a los
      Takers durante partidos en-vivo (in-play). Esto permite que
      algoritmos más rápidos hagan front-running. Usar órdenes Maker
      durante juego activo evita este delay porque las posturas pasivas
      se colocan instantáneamente en el libro.

    TABLA DE DECISIÓN:
      ┌──────────────────┬─────────────┬────────────────────────────────┐
      │ Contexto         │ Estrategia  │ Razón                          │
      ├──────────────────┼─────────────┼────────────────────────────────┤
      │ Pre-match        │ Taker       │ Sin delay, ejecución inmediata │
      │ In-play activo   │ Maker       │ Evita delay de 5-10s (snipe)   │
      │ In-play pausa    │ Taker       │ Delay desactivado en pausas    │
      │ Baja liquidez    │ Maker       │ Colocar y esperar llenado      │
      └──────────────────┴─────────────┴────────────────────────────────┘

    Maker: Coloca la orden 1-2 ticks MEJOR que el best price actual.
           No paga el spread. Mayor probabilidad de ejecución favorable.
           Riesgo: puede no ejecutarse si el mercado se mueve.

    Taker: Toma el best price disponible. Ejecución garantizada.
           Paga el spread completo. Sujeto a delay en-vivo.
    """

    # Incrementos de tick en cuotas decimales de Matchbook
    # Matchbook usa incrementos variables según rango de cuota:
    #   1.01-2.00: 0.01 | 2.00-3.00: 0.02 | 3.00-4.00: 0.05
    #   4.00-6.00: 0.10 | 6.00-10.0: 0.20 | 10.0-20.0: 0.50
    #   20.0-30.0: 1.00 | 30.0-50.0: 2.00 | 50.0+: 5.00
    TICK_RANGES = [
        (2.00, 0.01),
        (3.00, 0.02),
        (4.00, 0.05),
        (6.00, 0.10),
        (10.0, 0.20),
        (20.0, 0.50),
        (30.0, 1.00),
        (50.0, 2.00),
        (float('inf'), 5.00),
    ]

    @classmethod
    def _tick_size(cls, odds: float) -> float:
        """Retorna el tamaño de tick para una cuota dada."""
        for limit, tick in cls.TICK_RANGES:
            if odds < limit:
                return tick
        return 5.00

    @classmethod
    def _mejorar_cuota_maker(cls, best_odds: float, side: str = "back") -> float:
        """
        Calcula la cuota Maker: 1 tick mejor que el best price.
        Para BACK: 1 tick MÁS ALTO (ofrecemos cuota más atractiva al Lay)
        Para LAY:  1 tick MÁS BAJO (ofrecemos cuota más atractiva al Back)
        """
        tick = cls._tick_size(best_odds)
        if side.lower() == "back":
            return round(best_odds + tick, 2)
        else:  # lay
            return round(max(1.01, best_odds - tick), 2)

    @classmethod
    def decidir(
        cls,
        in_running: bool,
        es_pausa: bool,
        ev_neto: float,
        stake_kelly: float,
        liquidez_back: float,
        best_odds: float = 0.0,
        side: str = "back",
    ) -> Dict:
        """
        Determina si colocar orden como Maker (pasiva) o Taker (agresiva).

        Parámetros
        ----------
        in_running     : True si el partido está en vivo
        es_pausa       : True si es HT, cambio de lado, etc.
        ev_neto        : Expected Value neto post-comisión
        stake_kelly    : Stake calculado por Kelly (dinámico, del balance real)
        liquidez_back  : Liquidez total disponible en el lado back
        best_odds      : Mejor cuota disponible actualmente
        side           : 'back' o 'lay'

        Retorna
        -------
        dict con claves:
            modo            : 'maker' o 'taker'
            odds_propuestas : float — para maker: best + 1 tick; para taker: best
            keep_in_play    : bool — mantener la orden cuando empiece in-play
            razon           : str — explicación de la decisión
        """
        best_odds = _safe_float(best_odds) or 0.0
        stake_kelly = _safe_float(stake_kelly) or 0.0
        liquidez_back = _safe_float(liquidez_back) or 0.0

        resultado = {
            "side": side,
            "modo": "taker",
            "odds_propuestas": best_odds,
            "keep_in_play": False,
            "razon": "",
        }

        # ── Caso 1: Pre-match → Taker (sin delay) ──
        if not in_running:
            resultado["modo"] = "taker"
            resultado["odds_propuestas"] = best_odds
            resultado["keep_in_play"] = False
            resultado["razon"] = "Pre-match: Taker sin delay, ejecución inmediata"
            return resultado

        # ── Caso 2: In-play pausa (HT, cambio lado) → Taker ──
        if in_running and es_pausa:
            resultado["modo"] = "taker"
            resultado["odds_propuestas"] = best_odds
            resultado["keep_in_play"] = True
            resultado["razon"] = "In-play pausa: delay desactivado, Taker seguro"
            return resultado

        # ── Caso 3: Baja liquidez → Maker (colocar y esperar) ──
        if liquidez_back < stake_kelly * MB_LIQUIDITY_RATIO_MIN:
            odds_maker = cls._mejorar_cuota_maker(best_odds, side)
            resultado["modo"] = "maker"
            resultado["odds_propuestas"] = odds_maker
            resultado["keep_in_play"] = True
            resultado["razon"] = (
                f"Baja liquidez ({liquidez_back:.0f} < {stake_kelly * MB_LIQUIDITY_RATIO_MIN:.0f}): "
                f"Maker a {odds_maker:.2f} (best: {best_odds:.2f})"
            )
            return resultado

        # ── Caso 4: In-play activo → Maker (evita delay 5-10s) ──
        if in_running and not es_pausa:
            odds_maker = cls._mejorar_cuota_maker(best_odds, side)
            resultado["modo"] = "maker"
            resultado["odds_propuestas"] = odds_maker
            resultado["keep_in_play"] = True
            resultado["razon"] = (
                f"In-play activo: Maker a {odds_maker:.2f} evita delay de "
                f"{MB_TAKER_DELAY_INPLAY_SEC}s (best: {best_odds:.2f})"
            )
            return resultado

        return resultado
