# -*- coding: utf-8 -*-
"""
==================================================================================
continuitis.constantes | CONTINUITY
==================================================================================
Constantes globales y funciones helper compartidas por todos los módulos
de CONTINUITY v4.6.

Este módulo es la HOJA del grafo de dependencias — no importa nada de
continuitis. Todos los demás módulos importan de aquí.
"""

import os
import sqlite3
import numpy as np


# ==============================================================================
# CONSTANTES GLOBALES
# ==============================================================================
DATABASE_URL         = "cerebrillum.db"
STATE_FILE           = "state.json"
MODELOS_DIR          = "modelos_rf"
MOTOR_DISPONIBLE     = False
KELLY_FRACTION       = 0.25
EV_THRESHOLD         = 0.05
N_CORES              = os.cpu_count() or 6
CORES_POR_MODELO     = max(1, N_CORES // 2)
MIN_REGISTROS_LIGA   = 50
MIN_REGISTROS_GLOBAL = 30
PARON_FIFA_MESES     = {3, 6, 9, 10, 11}

# [v4.2-CONST] Etiquetas legibles de mercados 1X2 para UI y auditoría
MERCADOS_LABELS = {
    "1": "Victoria Local",
    "X": "Empate",
    "2": "Victoria Visitante",
}

# [v4.3-GAP4] Edge mínimo requerido entre probabilidad propia y probabilidad
# implícita de mercado (ya limpia de overround) para autorizar una apuesta.
# Un EV positivo por sí solo puede originarse en sobreconfianza del modelo;
# exigir edge adicional reduce falsos positivos cuando el mercado ya es
# eficiente. Calibrable empíricamente junto con EV_THRESHOLD cuando haya
# suficientes apuestas cerradas en AuditorRentabilidad (Capa 9b).
MIN_EDGE_REQUERIDO = 0.02

# [v6.0-FASE1] Gestión de riesgo avanzada — P-Value, Regla de los 300, Control de Clúster
KELLY_FRACTION_PREMIUM     = 0.375   # Kelly × 1.5 para ligas estadísticamente validadas
KELLY_FRACTION_CONSERVADOR = 0.125   # Kelly × 0.5 para ligas con muestra insuficiente
P_VALUE_UMBRAL             = 0.05    # significancia estadística requerida
YIELD_MIN_PREMIUM          = 0.05    # 5% yield mínimo para activar stake premium
MUESTRA_MIN_CONFIANZA      = 300     # Regla de los 300: operaciones mínimas para confiar en yield
CLUSTER_EXPOSICION_MAX     = 0.15    # 15% bankroll máximo en riesgo simultáneo
CLUSTER_VENTANA_HORAS      = 3       # ventana temporal de simultaneidad en horas

# ==============================================================================
# [v7.1-MICRO] MICROESTRUCTURA DE MERCADO — Ratios y Parámetros Técnicos
# ==============================================================================
# NOTA: Ninguna constante aquí es un monto absoluto de capital.
# Todo lo relacionado con capital se deriva dinámicamente del balance real
# de la cuenta vía Kelly fraccionado (EscudoFinanciero).
# ==============================================================================
MB_COMMISSION_RATE         = 0.02     # 2% comisión Matchbook sobre ganancias netas
MB_VWAP_SLIPPAGE_MAX       = 0.03     # 3% deslizamiento máximo aceptable (VWAP vs best price)
MB_LIQUIDITY_RATIO_MIN     = 2.0      # Liquidez mínima = 2× el stake Kelly calculado
MB_HEARTBEAT_INTERVAL_SEC  = 15       # Ping cada 15s al servidor
MB_HEARTBEAT_TIMEOUT_SEC   = 30       # Si no hay heartbeat en 30s → servidor purga órdenes
MB_TAKER_DELAY_INPLAY_SEC  = 7        # Retardo medio de Matchbook a Takers en-vivo
MB_BASE_URL_API            = "https://api.matchbook.com/edge/rest"
MB_AUTH_URL                = "https://api.matchbook.com/bpapi/rest/security/session"

# ==============================================================================
# CONSTANTES TACDE — Teoría de la Adaptación Competitiva Dinámica Evolutiva
# [v4.6-T2] Parámetros de presión adaptativa, intensidad y efecto de confianza.
# Todos acotados conservadoramente: el multiplicador resultante sobre lambda
# nunca supera ±25% (rango [0.75, 1.25]), evitando distorsiones ante muestras
# pequeñas en ligas con poco historial acumulado.
# Calibración futura: ajustar TACDE_ALPHA_IA y TACDE_ALPHA_EC cuando
# AuditorRentabilidad acumule ≥100 apuestas etiquetadas con señal TACDE activa.
# ==============================================================================
TACDE_ALPHA_IA       = 0.08   # boost máximo de lambda por intensidad adaptativa alta
TACDE_ALPHA_EC       = 0.05   # penalización de lambda por exceso de confianza
TACDE_ALPHA_RHO_IA   = 0.015  # sensibilidad de rho a IA bilateral (T-5, futuro)
TACDE_FACTOR_MIN     = 0.75   # tope inferior del multiplicador TACDE sobre lambda
TACDE_FACTOR_MAX     = 1.25   # tope superior del multiplicador TACDE sobre lambda
TACDE_MIN_PJ         = 3      # partidos jugados mínimos para que PA/RC sean confiables

# [v4.6-T2] Número de equipos que descienden por liga.
# Configurable por liga en dim_ligas (columna n_descensos, pendiente de
# migración de schema). Este dict es el fallback mientras no exista esa columna.
# MLS usa 0 porque no tiene descenso directo (usa playoffs de expansión).
# Liga MX usa 0 porque el descenso se determina por cociente histórico, no
# por tabla de temporada — el sistema lo trata como liga sin zona crítica inferior
# hasta que se implemente el cálculo de cociente.
TACDE_N_DESCENSOS = {
    "premier_league":   3,
    "la_liga":          3,
    "serie_a":          3,
    "bundesliga":       3,
    "ligue_1":          3,
    "eredivisie":       3,
    "champions_league": 0,   # eliminatoria — no hay descenso de liga
    "league_one":       4,
    "liga_mx_clausura": 0,   # descenso por cociente, no por tabla de temporada
    "liga_mx_apertura": 0,
    "concacaf_cl":      0,   # torneo corto eliminatorio
    "mls":              0,
}

FEATURE_STORE_DIR    = "feature_store"
FEATURE_TTL_HORAS    = 24
LAMBDA_CACHE_TTL_MIN = 60

# [v4.1-RHO-1] Rango seguro de rho para Dixon-Coles.
# La literatura reporta -0.03 (Bundesliga) a -0.07 (Serie A) como rango típico.
# Extendemos a -0.22 para escenarios de muy alta fricción (ej. partido cerrado
# entre equipos en mal momento, MAE elevado), pero nunca positivo.
# Un rho positivo rompería la corrección tau en celdas (0,0): 1 - ll*lv*rho
# podría ser negativo con lambdas altas, dando probabilidades inválidas.
RHO_MIN = -0.22
RHO_MAX = -0.02

FEATURE_BASE = [
    "numero_jornada", "es_inicio_temporada", "es_clasico",
    "dias_descanso_local", "dias_descanso_vis",
    "factor_presion", "dif_prestigio", "dif_altitud",
]
FEATURE_DINAMICAS = [
    "dif_elo", "forma_pts_local_5", "forma_pts_visita_5",
    "xg_ratio_local_5", "xg_ratio_visita_5", "h2h_win_rate_local",
    "es_eliminatoria", "es_partido_vuelta", "tsr_local",
    "factor_arbitro", "temperatura",
]
FEATURE_COLUMNS = FEATURE_BASE + FEATURE_DINAMICAS

# [v7.0-F7] Generalización Multideporte
MAPA_OBJETIVOS_DEPORTE = {
    "futbol": ("goles_local", "goles_visitante"),
    "baloncesto": ("puntos_local", "puntos_visitante"),
    "beisbol": ("carreras_local", "carreras_visitante"),
    "tenis": ("sets_local", "sets_visitante"),
}

def obtener_objetivos_liga(liga_id: str) -> tuple:
    """Devuelve las columnas objetivo según el deporte de la liga."""
    # Por ahora inferimos por string, en el futuro vendrá de la BD
    if "nba" in liga_id or "baloncesto" in liga_id:
        return MAPA_OBJETIVOS_DEPORTE["baloncesto"]
    elif "mlb" in liga_id or "beisbol" in liga_id:
        return MAPA_OBJETIVOS_DEPORTE["beisbol"]
    elif "atp" in liga_id or "wta" in liga_id or "tenis" in liga_id:
        return MAPA_OBJETIVOS_DEPORTE["tenis"]
    else:
        return MAPA_OBJETIVOS_DEPORTE["futbol"]

FASE_1_NAFTA = {
    "liga_mx_clausura": {"nombre": "Liga MX (Clausura) ",    "rango": [1,  5], "region": "NAFTA", "avg_goles": 2.4, "rho_dc": -0.05},
    "liga_mx_apertura": {"nombre": "Liga MX (Apertura)",     "rango": [7, 12], "region": "NAFTA", "avg_goles": 2.4, "rho_dc": -0.05},
    "concacaf_cl":      {"nombre": "CONCACAF Champions Cup", "rango": [2,  4], "region": "NAFTA", "avg_goles": 2.6, "rho_dc": -0.04},
    "mls":              {"nombre": "MLS",                    "rango": [3, 12], "region": "NAFTA", "avg_goles": 2.9, "rho_dc": -0.03},
}
FASE_2_EUROPA = {
    "premier_league":   {"nombre": "Premier League",    "rango": [8, 5], "region": "UEFA", "avg_goles": 2.7, "rho_dc": -0.04},
    "la_liga":          {"nombre": "LaLiga",            "rango": [8, 5], "region": "UEFA", "avg_goles": 2.5, "rho_dc": -0.04},
    "serie_a":          {"nombre": "Serie A",           "rango": [8, 5], "region": "UEFA", "avg_goles": 2.6, "rho_dc": -0.07},
    "eredivisie":       {"nombre": "Eredivisie",        "rango": [8, 5], "region": "UEFA", "avg_goles": 3.2, "rho_dc": -0.02},
    "bundesliga":       {"nombre": "Bundesliga",        "rango": [8, 5], "region": "UEFA", "avg_goles": 3.1, "rho_dc": -0.03},
    "ligue_1":          {"nombre": "Ligue 1",           "rango": [8, 5], "region": "UEFA", "avg_goles": 2.6, "rho_dc": -0.04},
    "champions_league": {"nombre": "Champions League",  "rango": [9, 5], "region": "UEFA", "avg_goles": 2.8, "rho_dc": -0.04},
    "league_one":       {"nombre": "League One",        "rango": [8, 5], "region": "UEFA", "avg_goles": 2.5, "rho_dc": -0.04},
}
FASE_3_MULTIDEPORTE = {
    "nba":              {"nombre": "NBA",               "rango": [10, 6], "region": "USA", "avg_puntos": 225.0, "varianza_base": 12.5},
    "mlb":              {"nombre": "MLB",               "rango": [4, 10], "region": "USA", "avg_carreras": 9.0, "rho_dc": 0.0},
    "atp_tour":         {"nombre": "ATP Tour",          "rango": [1, 11], "region": "GLOBAL", "prob_saque_avg": 0.65},
    "wta_tour":         {"nombre": "WTA Tour",          "rango": [1, 11], "region": "GLOBAL", "prob_saque_avg": 0.58},
}
FASE_4_VOLUMEN_GLOBAL = {
    # Fútbol Tier 2 y Global
    "championship":     {"nombre": "EFL Championship",  "rango": [8, 5], "region": "UEFA", "avg_goles": 2.5, "rho_dc": -0.05},
    "serie_b":          {"nombre": "Serie B",           "rango": [8, 5], "region": "UEFA", "avg_goles": 2.4, "rho_dc": -0.06},
    "segunda_division": {"nombre": "LaLiga 2",          "rango": [8, 6], "region": "UEFA", "avg_goles": 2.2, "rho_dc": -0.07},
    "primeira_liga":    {"nombre": "Primeira Liga",     "rango": [8, 5], "region": "UEFA", "avg_goles": 2.6, "rho_dc": -0.04},
    "brasileirao":      {"nombre": "Brasileirão",       "rango": [4, 12], "region": "LATAM", "avg_goles": 2.4, "rho_dc": -0.05},
    "primera_arg":      {"nombre": "Liga Profesional",  "rango": [1, 12], "region": "LATAM", "avg_goles": 2.2, "rho_dc": -0.06},
    "j_league":         {"nombre": "J1 League",         "rango": [2, 11], "region": "ASIA", "avg_goles": 2.6, "rho_dc": -0.04},
    # Baloncesto Adicional (Gran volumen)
    "ncaa_basket":      {"nombre": "NCAA Basketball",   "rango": [11, 4], "region": "USA", "avg_puntos": 140.0, "varianza_base": 11.0},
    "euroleague":       {"nombre": "Euroleague",        "rango": [10, 5], "region": "UEFA", "avg_puntos": 160.0, "varianza_base": 10.5},
    # Hockey y Fútbol Americano
    "nhl":              {"nombre": "NHL",               "rango": [10, 6], "region": "USA", "avg_goles": 6.0, "rho_dc": 0.0},
    "nfl":              {"nombre": "NFL",               "rango": [9, 2], "region": "USA", "avg_puntos": 45.0, "varianza_base": 14.0},
    # Tenis Volumen Masivo
    "atp_challenger":   {"nombre": "ATP Challenger",    "rango": [1, 12], "region": "GLOBAL", "prob_saque_avg": 0.62},
    "itf_mens":         {"nombre": "ITF Men",           "rango": [1, 12], "region": "GLOBAL", "prob_saque_avg": 0.60},
    "itf_womens":       {"nombre": "ITF Women",         "rango": [1, 12], "region": "GLOBAL", "prob_saque_avg": 0.55},
}
ALL_LIGAS = {**FASE_1_NAFTA, **FASE_2_EUROPA, **FASE_3_MULTIDEPORTE, **FASE_4_VOLUMEN_GLOBAL}


# ==============================================================================
# HELPERS
# ==============================================================================
def _safe_float(val) -> float:
    try:
        return float(str(val).strip())
    except (ValueError, TypeError, AttributeError):
        return None

def _safe_int(val) -> int:
    try:
        return int(float(str(val).strip()))
    except (ValueError, TypeError, AttributeError):
        return None

def _mes_de_fecha(fecha_str: str) -> int:
    try:
        partes = fecha_str.split("-")
        if len(partes) < 2:
            return 0
        return int(partes[1])
    except (ValueError, TypeError, AttributeError):
        return 0

def _normalizar_temporada(raw: str) -> str:
    raw = str(raw).strip()
    if not raw or raw == "desconocida":
        return raw
    if "/" in raw:
        partes = raw.split("/")
        try:
            a1, a2 = int(partes[0]), int(partes[1])
            if a1 < 100: a1 += 2000
            return f"{a1}-{str(a2):0>2}" if a2 < 100 else f"{a1}-{str(a2)[2:]}"
        except ValueError:
            pass
    if "-" in raw and len(raw) == 5:
        return f"20{raw}"
    if raw.isdigit() and len(raw) == 4:
        a = int(raw)
        return f"{a}-{str(a+1)[2:]}"
    return raw

def _sql_exec(cur, sql: str, label: str = "") -> bool:
    try:
        cur.execute(sql)
        return True
    except sqlite3.OperationalError as e:
        if "already exists" not in str(e).lower() and "duplicate column" not in str(e).lower():
            print(f"  [DB-WARN] {label}: {e}")
        return False


def slug_canonico(liga_id: str, team_name: str) -> str:
    """
    Única fuente de verdad para construir un equipo_id canónico.
    Normaliza 5 caracteres [" ", "-", ".", "'", "/"] → "_".

    Usado por:
      - CEREBELLIUM.py (ETL: al importar CSV)
      - pacificokyj.py (_normalizar_equipo_id: UI Streamlit)
      - CONTINUITY.py  (_normalizar_equipo_id_cli: CLI)

    Un equipo con apóstrofe o punto en el nombre (St. Etienne, O'Higgins)
    genera el mismo slug sin importar qué módulo lo procese.
    """
    s = team_name.lower().strip()
    for ch in (" ", "-", ".", "'", "/"):
        s = s.replace(ch, "_")
    return f"{liga_id}:{s}"
