import sys
import os
import time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
import logging
from datetime import datetime, timedelta
from typing import Dict

from conectores.telegram_bot import TelegramNotifier
from conectores.matchbook_async import MatchbookClientAsync
from continuitis.financiero import MotorInteresCompuesto
from continuitis.microestructura import AjustadorComisiones, EstrategiaMakerTaker, CalculadorVWAP
from continuitis.memoria_hft import HFTMemoryStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

telegram = TelegramNotifier(bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""), chat_id=os.getenv("TELEGRAM_CHAT_ID", ""))
memoria_hft = HFTMemoryStore()

# ---------------------------------------------------------
# VARIABLES DE ENTORNO Y LÍMITES HFT
# ---------------------------------------------------------
INTERVALO_ESCANEO_SEG = 5
COMISION_MATCHBOOK = 0.03
DEPORTES_HFT = ""  # Vacío = todos los deportes
TIEMPO_ENFRIAMIENTO_SEG = 300    # Cooldown por defecto (A): 5 min
TIEMPO_ENFRIAMIENTO_VWAP = 120   # Cooldown Estrategia B (VWAP): 2 min
TIEMPO_ENFRIAMIENTO_DRAIN = 300  # Cooldown Estrategia C (Drain): 5 min
MAX_PROB_GAP = 0.05              # Margen máximo de prob en el spread (5% — calibrado con datos reales)
MARGEN_MINIMO_NETO = 0.005       # EV Neto mínimo 0.5% (ya cobrada la comisión del 4%)
VWAP_MISPRICE_THRESHOLD = 0.02   # Estrategia B: 2% por encima del VWAP = señal
MIN_PROB_GAP_DRAIN = 0.01        # Estrategia C: límite inferior del spread (1%)

# Orden de prioridad de deportes por liquidez real (Matchbook Sport IDs)
# El ciclo escanea primero los eventos de mayor liquidez para maximizar disparos
# en las ventanas de pico europeo (12:00-20:00 BST = 06:00-14:00 CDMX)
PRIORIDAD_DEPORTES = [15, 9, 1, 2, 3, 4]  # Fútbol, Tenis, otros
# 15=Fútbol, 9=Tenis, 1=Fútbol UK, 2=Rugby, 3=Cricket, 4=Béisbol
# ---------------------------------------------------------


# ---------------------------------------------------------
# CONFIGURACIÓN DE ESTRATEGIAS ACTIVAS
# ---------------------------------------------------------
ESTRATEGIA_ACTIVA = {
    "A_MARKET_MAKER": True,   # Pure Market Maker (1 tick inside spread)
    "B_VWAP_SCALP":   True,   # VWAP Momentum Scalp (in-play mispricings)
    "C_DRAIN_SCALP":  True,   # Liquidity Drain Scalp (2 ticks, confirmed runners)
}
# ---------------------------------------------------------

BALANCE_INICIO_DIA = 0.0
cooldowns_mercado: Dict[str, float] = {}
ofertas_pendientes: Dict[str, float] = {}

# Tracking de runners vistos en ciclos consecutivos para Estrategia C.
# Key: runner uid, value: timestamp del primer avistamiento en el ciclo actual.
runners_vistos: Dict[str, float] = {}


# ==============================================================================
# HELPERS: ESTRATEGIA SEMANAL Y HORARIO PICO BST
# ==============================================================================
def get_estrategias_semana() -> dict:
    """
    Devuelve el dict de estrategias activas según la semana del mes actual (zona BST).
    Semana 1 → solo A.  Semana 2 → A+B.  Semana 3+ → A+B+C.
    """
    try:
        import pytz
        bst = pytz.timezone("Europe/London")
        ahora_bst = datetime.now(bst)
    except Exception:
        ahora_bst = datetime.utcnow()

    # Semana del mes: día 1-7 = semana 1, 8-14 = semana 2, 15+ = semana 3+
    dia = ahora_bst.day
    if dia <= 7:
        return {"A_MARKET_MAKER": True, "B_VWAP_SCALP": False, "C_DRAIN_SCALP": False}
    elif dia <= 14:
        return {"A_MARKET_MAKER": True, "B_VWAP_SCALP": True,  "C_DRAIN_SCALP": False}
    else:
        return {"A_MARKET_MAKER": True, "B_VWAP_SCALP": True,  "C_DRAIN_SCALP": True}


def en_horario_pico_bst() -> bool:
    """
    Retorna True si la hora actual en BST está entre 12:00 y 19:59 (pico de liquidez europea).
    """
    try:
        import pytz
        bst = pytz.timezone("Europe/London")
        hora_bst = datetime.now(bst).hour
    except Exception:
        hora_bst = datetime.utcnow().hour

    return 12 <= hora_bst < 20




# ==============================================================================
# RECOLECTOR DE ÓRDENES HUÉRFANAS (Kill-or-Fill GC)
# ==============================================================================
async def recolector_ordenes_huerfanas(matchbook):
    while True:
        try:
            await asyncio.sleep(15)
            ahora = time.time()
            for offer_id, timestamp in list(ofertas_pendientes.items()):
                if ahora - timestamp > 45:
                    logger.info(f"[GC] Cancelando orden huerfana {offer_id} (>45s) para rotar capital.")
                    try:
                        await matchbook.cancelar_oferta(offer_id)
                    except Exception as e:
                        logger.error(f"[GC] Error cancelando orden {offer_id}: {e}")
                    finally:
                        if offer_id in ofertas_pendientes:
                            del ofertas_pendientes[offer_id]
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[GC] Error en ciclo general: {e}")


# ==============================================================================
# ESTRATEGIA A — PURE MARKET MAKER
# ==============================================================================
def evaluar_estrategia_a(
    runner_id, runner_name, event_id, nombre_partido, in_play,
    back_odds, lay_odds, prob_back, prob_lay, prob_gap,
    bankroll_actual, max_bankroll_dia, ahora
):
    """
    Coloca una limit order 1 tick inside el spread (maker_odds).
    Entra sólo si prob_gap < 3%.
    Cooldown: 300s con prefijo MKR_.
    """
    if not ESTRATEGIA_ACTIVA["A_MARKET_MAKER"]:
        return None

    uid = f"MKR_{event_id}-{runner_id}"
    if ahora - cooldowns_mercado.get(uid, 0) < TIEMPO_ENFRIAMIENTO_SEG:
        return None

    if prob_gap >= MAX_PROB_GAP:
        return None

    prob_justa = (prob_back + prob_lay) / 2.0
    maker_odds = EstrategiaMakerTaker._mejorar_cuota_maker(back_odds, side="back")
    if maker_odds >= lay_odds:
        maker_odds = lay_odds

    ev_neto = AjustadorComisiones.ev_neto(prob_justa, maker_odds, comision=COMISION_MATCHBOOK)
    if ev_neto < MARGEN_MINIMO_NETO:
        return None

    stake = MotorInteresCompuesto.calcular_stake_hft(
        bankroll_actual, ev_neto, maker_odds,
        max_kelly=0.25,
        racha_perdidas=memoria_hft.racha_perdidas,
        max_bankroll_diario=max_bankroll_dia
    )
    if stake < 2.0:
        return None

    status_tag = "🔴 EN VIVO" if in_play else "⏳ PREMATCH"
    return {
        "estrategia": "A",
        "label": "MARKET MAKER",
        "uid": uid,
        "runner_id": runner_id,
        "runner_name": runner_name,
        "stake": stake,
        "odds": maker_odds,
        "ev_neto": ev_neto,
        "prob_gap": prob_gap,
        "status_tag": status_tag,
        "nombre_partido": nombre_partido,
        "modo": "maker",
    }


# ==============================================================================
# ESTRATEGIA B — VWAP MOMENTUM SCALP
# ==============================================================================
def evaluar_estrategia_b(
    runner_id, runner_name, event_id, nombre_partido, in_play,
    back_odds, prices_back,
    bankroll_actual, max_bankroll_dia, ahora
):
    """
    Sólo para eventos in-play.
    Calcula VWAP del libro back. Si back_odds > VWAP × (1 + 2%), el top-of-book
    ofrece mejor precio que el valor ponderado — entra como Taker inmediato (EV positivo).
    Cooldown: 120s con prefijo VWAP_.
    """
    if not ESTRATEGIA_ACTIVA["B_VWAP_SCALP"]:
        return None

    if not in_play:
        return None

    uid = f"VWAP_{event_id}-{runner_id}"
    if ahora - cooldowns_mercado.get(uid, 0) < TIEMPO_ENFRIAMIENTO_VWAP:
        return None

    # Necesitamos algo de liquidez para el VWAP
    if not prices_back or len(prices_back) < 1:
        return None

    # Estimamos el stake que usaríamos para el VWAP (usamos el mínimo viable)
    stake_estimado = max(bankroll_actual * 0.05, 2.0)

    vwap, slippage_pct, liquidez_total, niveles = CalculadorVWAP.calcular(
        prices_back, stake_estimado
    )
    if vwap <= 1.0 or liquidez_total <= 0:
        return None

    # Condición: back_odds más de 2% POR ENCIMA del precio justo VWAP
    # (el top-of-book ofrece más que el precio ponderado = EV positivo para back taker)
    # Si back_odds <= vwap * (1 + threshold), la cuota no supera el umbral de mispricing → skip
    if back_odds <= vwap * (1.0 + VWAP_MISPRICE_THRESHOLD):
        return None

    # EV usando el VWAP como precio justo y back_odds como cuota de entrada
    prob_justa_vwap = 1.0 / vwap
    ev_neto = AjustadorComisiones.ev_neto(prob_justa_vwap, back_odds, comision=COMISION_MATCHBOOK)
    if ev_neto < MARGEN_MINIMO_NETO:
        return None

    stake = MotorInteresCompuesto.calcular_stake_hft(
        bankroll_actual, ev_neto, back_odds,
        max_kelly=0.25,
        racha_perdidas=memoria_hft.racha_perdidas,
        max_bankroll_diario=max_bankroll_dia
    )
    # Ajustar stake por liquidez disponible
    stake = CalculadorVWAP.ajustar_stake_por_liquidez(stake, liquidez_total)
    if stake < 2.0:
        return None

    return {
        "estrategia": "B",
        "label": "VWAP SCALP",
        "uid": uid,
        "runner_id": runner_id,
        "runner_name": runner_name,
        "stake": stake,
        "odds": back_odds,
        "ev_neto": ev_neto,
        "vwap": vwap,
        "slippage_pct": slippage_pct,
        "status_tag": "🔴 EN VIVO",
        "nombre_partido": nombre_partido,
        "modo": "taker",
    }


# ==============================================================================
# ESTRATEGIA C — LIQUIDITY DRAIN SCALP
# ==============================================================================
def evaluar_estrategia_c(
    runner_id, runner_name, event_id, nombre_partido, in_play,
    back_odds, lay_odds, prob_back, prob_lay, prob_gap,
    bankroll_actual, max_bankroll_dia, ahora
):
    """
    Target: runners con prob_gap entre 1.5% y 3% (mercados líquidos).
    Requiere que el runner haya sido visto en al menos 1 ciclo previo.
    Entra con maker_odds = back_odds + 2 ticks (ultra-agresivo en cola).
    Cooldown: 300s con prefijo DRN_.
    """
    if not ESTRATEGIA_ACTIVA["C_DRAIN_SCALP"]:
        return None

    uid_base = f"{event_id}-{runner_id}"
    uid = f"DRN_{uid_base}"
    if ahora - cooldowns_mercado.get(uid, 0) < TIEMPO_ENFRIAMIENTO_DRAIN:
        return None

    # Filtro de spread: solo mercados "tight" (1.5% ≤ prob_gap < 3%)
    if prob_gap < MIN_PROB_GAP_DRAIN or prob_gap >= MAX_PROB_GAP:
        return None

    # Requiere presencia en ciclo anterior (al menos 1 ciclo previo)
    primer_avistamiento = runners_vistos.get(uid_base)
    if primer_avistamiento is None:
        # Primer avistamiento: registrar pero no operar aún
        runners_vistos[uid_base] = ahora
        return None

    # Verificar que hay al menos 1 ciclo (INTERVALO_ESCANEO_SEG segundos) de antigüedad
    if ahora - primer_avistamiento < INTERVALO_ESCANEO_SEG:
        return None

    prob_justa = (prob_back + prob_lay) / 2.0

    # 2 ticks dentro del spread (más agresivo que Strategy A de 1 tick)
    tick1 = EstrategiaMakerTaker._tick_size(back_odds)
    maker_odds_drain = round(back_odds + 2 * tick1, 2)
    if maker_odds_drain >= lay_odds:
        maker_odds_drain = lay_odds

    ev_neto = AjustadorComisiones.ev_neto(prob_justa, maker_odds_drain, comision=COMISION_MATCHBOOK)
    if ev_neto < MARGEN_MINIMO_NETO:
        return None

    stake = MotorInteresCompuesto.calcular_stake_hft(
        bankroll_actual, ev_neto, maker_odds_drain,
        max_kelly=0.25,
        racha_perdidas=memoria_hft.racha_perdidas,
        max_bankroll_diario=max_bankroll_dia
    )
    if stake < 2.0:
        return None

    status_tag = "🔴 EN VIVO" if in_play else "⏳ PREMATCH"
    return {
        "estrategia": "C",
        "label": "DRAIN SCALP",
        "uid": uid,
        "runner_id": runner_id,
        "runner_name": runner_name,
        "stake": stake,
        "odds": maker_odds_drain,
        "ev_neto": ev_neto,
        "prob_gap": prob_gap,
        "status_tag": status_tag,
        "nombre_partido": nombre_partido,
        "modo": "maker",
    }


# ==============================================================================
# CICLO PRINCIPAL DE ESCANEO HFT (Multi-Estrategia)
# ==============================================================================
async def ciclo_escaneo_hft(matchbook: MatchbookClientAsync):
    global ESTRATEGIA_ACTIVA

    # [2A] Actualizar estrategias activas según semana del mes (BST)
    ESTRATEGIA_ACTIVA = get_estrategias_semana()

    # [2B] Ajustar umbral de spread según horario pico/fuera-de-pico BST
    MAX_PROB_GAP_ACTUAL = MAX_PROB_GAP  # 5% uniforme — calibrado con datos reales del mercado

    # Evicción de memoria: limpiar runners no vistos en +10 minutos
    ahora_gc = time.time()
    stale = [k for k, ts in list(runners_vistos.items()) if ahora_gc - ts > 600]
    for k in stale:
        del runners_vistos[k]

    eventos = await matchbook.obtener_eventos_hft(sport_ids=DEPORTES_HFT)

    bankroll_actual = await matchbook.obtener_balance()
    if bankroll_actual <= 0:
        return

    max_bankroll_dia = memoria_hft.actualizar_estado_diario(bankroll_actual)


    alerta_cb = MotorInteresCompuesto.verificar_circuit_breakers(bankroll_actual, max_bankroll_dia)
    if alerta_cb:
        if alerta_cb == "HARD_STOP":
            if not getattr(telegram, "alerta_hard_stop_enviada", False):
                msg = f"🚨 CRITICO: Hard Stop activado. Bankroll cayo a {bankroll_actual:.2f} MXN (<= 30 MXN). HFT Detenido."
                telegram.enviar_mensaje(msg)
                logger.error(msg)
                telegram.alerta_hard_stop_enviada = True
        elif alerta_cb == "TRAILING_STOP":
            hoy = memoria_hft.dia_actual
            if getattr(telegram, "alerta_trailing_stop_dia", "") != hoy:
                msg = f"🚨 ALERTA: Daily Trailing Stop activado. Bankroll {bankroll_actual:.2f} cayo 20% bajo el pico de hoy {max_bankroll_dia:.2f}. HFT Detenido por hoy."
                telegram.enviar_mensaje(msg)
                logger.error(msg)
                telegram.alerta_trailing_stop_dia = hoy
        return  # HFT Detenido

    if bankroll_actual > 30.0:
        telegram.alerta_hard_stop_enviada = False

    logger.info(f"[Scanner] Procesando {len(eventos)} eventos HFT. Bankroll: {bankroll_actual} | Pico BST: {en_horario_pico_bst()} | GAP máx: {MAX_PROB_GAP_ACTUAL*100:.2f}%")

    # [2C] Ordenar eventos: primero in-play, luego por prioridad de deporte
    def _sport_priority(evento):
        sport_id = evento.get("sport-id")
        try:
            return PRIORIDAD_DEPORTES.index(sport_id)
        except ValueError:
            return len(PRIORIDAD_DEPORTES)

    eventos = sorted(
        eventos,
        key=lambda e: (not e.get("in-running-flag", False), _sport_priority(e))
    )
    ahora = time.time()

    for evento in eventos:
        event_id = evento.get("id")
        nombre_partido = evento.get("name")
        in_play = evento.get("in-running-flag", False)
        mercados = evento.get("markets", [])

        for mercado in mercados:
            market_id = mercado.get("id")
            market_name = mercado.get("name")
            runners = mercado.get("runners", [])

            for runner in runners:
                runner_id = runner.get("id")
                runner_name = runner.get("name")

                prices = runner.get("prices", [])
                best_back, best_lay = None, None
                prices_back_sorted = []

                for price in prices:
                    side = price.get("side")
                    if side == "back":
                        if not best_back or price.get("odds", 0) > best_back.get("odds", 0):
                            best_back = price
                        prices_back_sorted.append(price)
                    elif side == "lay":
                        if not best_lay or price.get("odds", 0) < best_lay.get("odds", 999):
                            best_lay = price

                if not best_back or not best_lay:
                    continue

                # Ordenar el libro back de mayor a menor cuota para VWAP
                prices_back_sorted.sort(key=lambda p: p.get("odds", 0), reverse=True)

                back_odds = best_back.get("odds")
                lay_odds = best_lay.get("odds")

                if back_odds <= 1.01 or lay_odds <= 1.01:
                    continue

                prob_back = 1.0 / back_odds
                prob_lay = 1.0 / lay_odds
                prob_gap = prob_back - prob_lay

                # Actualizar tracking de runners vistos (para Estrategia C)
                uid_base = f"{event_id}-{runner_id}"
                if uid_base not in runners_vistos:
                    runners_vistos[uid_base] = ahora

                # Filtro de log: solo mostrar spreads moderados (no ruido total)
                if prob_gap > MAX_PROB_GAP_ACTUAL:
                    if prob_gap <= 0.06:
                        logger.info(f"[Filtro Spread] {runner_name[:15]} | Prob Gap {prob_gap*100:.2f}% > {MAX_PROB_GAP_ACTUAL*100:.2f}%")
                    # Estrategia B puede operar incluso con prob_gap amplio (solo filtra por in_play y VWAP)
                    # Estrategia A y C son filtradas dentro de su función
                    pass


                # ── Evaluar las 3 estrategias en paralelo ──
                señal_a = evaluar_estrategia_a(
                    runner_id, runner_name, event_id, nombre_partido, in_play,
                    back_odds, lay_odds, prob_back, prob_lay, prob_gap,
                    bankroll_actual, max_bankroll_dia, ahora
                )
                señal_b = evaluar_estrategia_b(
                    runner_id, runner_name, event_id, nombre_partido, in_play,
                    back_odds, prices_back_sorted,
                    bankroll_actual, max_bankroll_dia, ahora
                )
                señal_c = evaluar_estrategia_c(
                    runner_id, runner_name, event_id, nombre_partido, in_play,
                    back_odds, lay_odds, prob_back, prob_lay, prob_gap,
                    bankroll_actual, max_bankroll_dia, ahora
                )

                for señal in [señal_a, señal_b, señal_c]:
                    if señal is None:
                        continue

                    uid = señal["uid"]
                    label = señal["label"]
                    status_tag = señal["status_tag"]

                    extra = ""
                    if señal["estrategia"] == "B":
                        extra = f"\n📊 VWAP: {señal.get('vwap', 0):.3f} | Slippage: {señal.get('slippage_pct', 0)*100:.2f}%"
                    elif señal["estrategia"] in ("A", "C"):
                        extra = f"\n✂️ Prob Gap: {señal.get('prob_gap', 0)*100:.2f}%"

                    msg = (
                        f"⚡ [HFT {label}] ⚡\n\n"
                        f"⚽ Partido: {status_tag} {señal['nombre_partido']}\n"
                        f"🎯 Selección: {señal['runner_name']}\n"
                        f"📈 Cuota: {señal['odds']}\n"
                        f"🧠 EV Neto: {señal['ev_neto']*100:.2f}%\n"
                        f"💰 Stake: ${señal['stake']:.2f} MXN"
                        f"{extra}"
                    )
                    logger.info(
                        f"[MLOps/{label}] {status_tag} | {señal['nombre_partido']} | "
                        f"{señal['runner_name']} @ {señal['odds']} | "
                        f"EV Neto: {señal['ev_neto']*100:.2f}% | Stake: ${señal['stake']:.2f}"
                    )
                    telegram.enviar_mensaje(msg)

                    cooldowns_mercado[uid] = ahora
                    memoria_hft.registrar_orden_activa(uid, {
                        "uid": uid,
                        "deporte": evento.get("sport-id"),
                        "mercado": market_name,
                        "stake": señal["stake"],
                        "cuota_elegida": señal["odds"],
                        "ev_neto": señal["ev_neto"],
                        "varianza_spread": señal.get("prob_gap", señal.get("slippage_pct", 0)),
                    })

                    asyncio.create_task(
                        ejecutar_orden(matchbook, señal["runner_id"], señal["stake"], señal["odds"], uid, señal["modo"])
                    )


# ==============================================================================
# EJECUCIÓN DE ÓRDENES
# ==============================================================================
async def ejecutar_orden(matchbook, runner_id, stake, odds, uid, modo="maker"):
    try:
        res = await matchbook.colocar_apuesta(runner_id, stake, odds, side="back", modo=modo)
        if res and res.get("offer_id"):
            offer_id = str(res.get("offer_id"))
            ofertas_pendientes[offer_id] = time.time()
            memoria_hft.resolver_orden_hft(uid, "OPEN", 0.0, 0.0)
    except Exception as e:
        logger.error(f"[HFT] Error colocando {uid}: {e}")
        memoria_hft.remover_orden_activa(uid)


# ==============================================================================
# REPORTE PERIÓDICO 3H (Telegram)
# ==============================================================================
async def reporte_periodico(matchbook):
    while True:
        await asyncio.sleep(10800)  # 3 horas
        try:
            bankroll_actual = await matchbook.obtener_balance()
            ganancia = bankroll_actual - BALANCE_INICIO_DIA
            porcentaje = (ganancia / BALANCE_INICIO_DIA * 100) if BALANCE_INICIO_DIA > 0 else 0

            estrategias_on = [k for k, v in ESTRATEGIA_ACTIVA.items() if v]
            signo = "+" if ganancia >= 0 else ""
            msg = (
                f"📊 [CORTE DE CAJA HFT - 3H] 📊\n\n"
                f"💰 Balance Inicial: ${BALANCE_INICIO_DIA:.2f} MXN\n"
                f"💸 Balance Actual: ${bankroll_actual:.2f} MXN\n"
                f"📈 Rendimiento: {signo}${ganancia:.2f} MXN ({signo}{porcentaje:.2f}%)\n\n"
                f"⚡ Estrategias activas: {', '.join(estrategias_on)}\n"
                f"⚡ Estado del Motor: 100% Activo y buscando liquidez."
            )
            telegram.enviar_mensaje(msg)
            logger.info("[Reporte 3H] Enviado a Telegram con exito.")
        except Exception as e:
            logger.error(f"[Reporte 3H] Error enviando reporte: {e}")


# ==============================================================================
# REPORTE DE CIERRE DIARIO — 3:00 AM BST (21:00 CDMX)
# ==============================================================================
async def reporte_cierre_diario(matchbook):
    """
    Cada día espera hasta las 3:00 AM BST (equivalente a las 9 PM CDMX).
    Envía un reporte detallado por Telegram y actualiza BALANCE_INICIO_DIA.
    Meta mensual referencia: $300 MXN (3x el capital inicial de $100 MXN).
    """
    global BALANCE_INICIO_DIA
    META_MES_MXN = 300.0  # 3x el capital de arranque

    while True:
        try:
            import pytz
            bst = pytz.timezone("Europe/London")
            ahora_bst = datetime.now(bst)
        except Exception:
            ahora_bst = datetime.utcnow()

        # Calcular segundos hasta la siguiente 3:00 AM BST
        try:
            import pytz
            bst_tz = pytz.timezone("Europe/London")
            ahora_local = datetime.now(bst_tz)
            objetivo = ahora_local.replace(hour=3, minute=0, second=0, microsecond=0)
            if ahora_local >= objetivo:
                objetivo += timedelta(days=1)
            segundos_espera = (objetivo - ahora_local).total_seconds()
        except Exception:
            # Fallback: 24 horas
            segundos_espera = 86400

        logger.info(f"[CierreDiario] Próximo reporte en {segundos_espera/3600:.2f}h (3:00 AM BST).")
        await asyncio.sleep(segundos_espera)

        try:
            bankroll_actual = await matchbook.obtener_balance()
            ganancia_dia = bankroll_actual - BALANCE_INICIO_DIA
            signo = "+" if ganancia_dia >= 0 else ""
            pct_dia = (ganancia_dia / BALANCE_INICIO_DIA * 100) if BALANCE_INICIO_DIA > 0 else 0.0

            # Progreso hacia meta mensual
            progreso_meta_pct = (bankroll_actual / META_MES_MXN * 100) if META_MES_MXN > 0 else 0.0
            racha = memoria_hft.racha_perdidas
            pico = en_horario_pico_bst()
            horario_str = "🟢 PICO (12-20h BST)" if pico else "🔵 FUERA DE PICO"

            msg = (
                f"🌙 [CIERRE DIARIO HFT] 🌙\n\n"
                f"💰 Balance Inicio del Día: ${BALANCE_INICIO_DIA:.2f} MXN\n"
                f"💸 Balance Actual:         ${bankroll_actual:.2f} MXN\n"
                f"📈 P&L Hoy:                {signo}${ganancia_dia:.2f} MXN ({signo}{pct_dia:.2f}%)\n\n"
                f"📉 Racha de Pérdidas:      {racha} consecutivas\n"
                f"🎯 Progreso meta del mes:  ${bankroll_actual:.2f} / ${META_MES_MXN:.2f} ({progreso_meta_pct:.1f}%)\n"
                f"🕒 Horario BST:            {horario_str}\n\n"
                f"⚡ Motor: {'ON — continuando escaneo.' if bankroll_actual > 30 else '🛑 HARD STOP — bankroll crítico.'}"
            )
            telegram.enviar_mensaje(msg)
            logger.info(f"[CierreDiario] Reporte enviado. P&L={signo}${ganancia_dia:.2f}")

            # Actualizar baseline para el próximo día
            BALANCE_INICIO_DIA = bankroll_actual

        except Exception as e:
            logger.error(f"[CierreDiario] Error generando reporte: {e}")


# ==============================================================================
# DAEMON PRINCIPAL
# ==============================================================================
async def daemon_hft():
    global BALANCE_INICIO_DIA
    matchbook = MatchbookClientAsync()
    await matchbook.init_session()
    BALANCE_INICIO_DIA = await matchbook.obtener_balance()

    logger.info("==================================================")
    logger.info("🚀 STARTING: CONTINUITY HFT MICRO-CAPITAL ENGINE v2.0")
    logger.info(f"💰 BALANCE: ${BALANCE_INICIO_DIA:.2f} | Multi-Strategy Mode")
    logger.info(f"📋 Estrategias: A={ESTRATEGIA_ACTIVA['A_MARKET_MAKER']} | B={ESTRATEGIA_ACTIVA['B_VWAP_SCALP']} | C={ESTRATEGIA_ACTIVA['C_DRAIN_SCALP']}")
    logger.info("==================================================")

    telegram.notificar_inicio(version="HFT MLOps v2.0-MultiStrat", balance_inicial=BALANCE_INICIO_DIA)
    matchbook.iniciar_heartbeat()
    asyncio.create_task(reporte_periodico(matchbook))
    asyncio.create_task(recolector_ordenes_huerfanas(matchbook))
    asyncio.create_task(reporte_cierre_diario(matchbook))

    try:
        while True:
            await ciclo_escaneo_hft(matchbook)
            await asyncio.sleep(INTERVALO_ESCANEO_SEG)
    except asyncio.CancelledError:
        pass
    finally:
        await matchbook.cerrar_sesion()


if __name__ == "__main__":
    asyncio.run(daemon_hft())
