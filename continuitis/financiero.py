# -*- coding: utf-8 -*-
"""
==================================================================================
continuitis.financiero | CONTINUITY
==================================================================================
Capa 8 â Escudo Financiero (Kelly fraccionado).

Clases:
    EscudoFinanciero â gestiÃ³n financiera con Kelly fraccionado, evaluaciÃ³n
                       triple 1X2, evaluaciÃ³n binaria O/U, y penalizaciÃ³n
                       por racha adversa.
"""

from .constantes import (
    _safe_float, _safe_int,
    EV_THRESHOLD, KELLY_FRACTION, MIN_EDGE_REQUERIDO,
    KELLY_FRACTION_PREMIUM, KELLY_FRACTION_CONSERVADOR,
    P_VALUE_UMBRAL, YIELD_MIN_PREMIUM, MUESTRA_MIN_CONFIANZA,
    CLUSTER_EXPOSICION_MAX, CLUSTER_VENTANA_HORAS,
    DATABASE_URL,
    MB_COMMISSION_RATE,
)


#-----------------------------AREA 4 = FINANCIERA Y DE EVALUACION DE RENDIMIENTO----------------------------------------------
#
# ==============================================================================
# CAPA 8 â ESCUDO FINANCIERO (Kelly fraccionado)
# ==============================================================================
class EscudoFinanciero:
    """
    Capa 8 â GestiÃ³n financiera Kelly fraccionado.
 
    Historial de versiones:
      [v4.1]      evaluar()                           â Kelly fraccionado, mercado 1.
      [v4.2-GAP2] normalizar_probabilidades_mercado() â Strip de overround.
      [v4.2-GAP1] evaluar_triple()                    â EvaluaciÃ³n 3 mercados 1X2.
 
    Compatibilidad regresiva:
      evaluar() mantiene firma y comportamiento idÃ©nticos a v4.1.
      PACIFICO1.evaluar_con_racha() y ARGUS.GestorPortafolioKelly no requieren cambios.
    """
 
    # ââ ORIGINAL â FIRMA Y COMPORTAMIENTO IDÃNTICOS A v4.1 âââââââââââââââââ
    @staticmethod
    def evaluar(prob: float, cuota: float, bankroll: float) -> tuple:
        """
        [v4.1 ORIGINAL â INTOCADO]
        EvalÃºa EV y stake Kelly fraccionado para el mercado de victoria local.
        Retorna (operar: bool, ev: float, stake: float).
        Llamado por: AEGIST.modulo_inferencia (modo legacy), PACIFICO1, main() CLI.
        """
        prob     = _safe_float(prob)     or 0.0
        cuota    = _safe_float(cuota)    or 1.0
        bankroll = _safe_float(bankroll) or 1000.0
        if cuota <= 1.0:
            return False, 0.0, 0.0
        ev = prob * cuota - 1.0
        if ev > EV_THRESHOLD:
            kelly_puro = ev / (cuota - 1.0)
            stake_frac = kelly_puro * KELLY_FRACTION
            return True, round(ev, 4), round(bankroll * stake_frac, 2)
        return False, round(ev, 4), 0.0
 
    # ââ NUEVO â [v4.2-GAP2] ââââââââââââââââââââââââââââââââââââââââââââââââ
    @staticmethod
    def normalizar_probabilidades_mercado(
        c1: float, cx: float, c2: float
    ) -> tuple:
        """
        [v4.2-GAP2] Elimina el overround (margen de casa) de las cuotas brutas
        y devuelve las probabilidades implÃ­citas limpias del mercado.
 
        PROBLEMA QUE RESUELVE:
          La fÃ³rmula original ev = prob*cuota - 1 asume que la cuota refleja el
          precio justo. Las casas incorporan un margen del 4-8% (overround) que
          infla las cuotas implÃ­citas sobre 1.0. Sin descontarlo, el sistema
          sobreestima el EV real ~4-8 puntos porcentuales y puede:
            a) Rechazar apuestas con EV real positivo (EV calculado parece negativo).
            b) Aprobar apuestas con EV real negativo (EV calculado parece positivo).
 
        MATEMÃTICA:
          pi_i_bruta  = 1 / cuota_i
          suma        = pi1 + pix + pi2   (> 1.0 porque incluye el overround)
          overround   = suma - 1.0         (0.04â0.08 en mercados tÃ­picos 1X2)
          pi_i_limpia = pi_i_bruta / suma  (normalizado a sumar exactamente 1.0)
 
        NOTA: El EV en evaluar_triple() se calcula con la cuota BRUTA real
        (lo que efectivamente paga la casa). Las probabilidades limpias del mercado
        se exponen en el detalle SOLO como referencia de edge, no entran en el EV.
 
        ParÃ¡metros
        ----------
        c1, cx, c2 : cuotas brutas 1X2 tal como las ofrece la casa de apuestas.
 
        Retorna
        -------
        (pi1, pix, pi2, overround)
          pi1, pix, pi2 : probabilidades implÃ­citas limpias â suman exactamente 1.0.
          overround     : margen de la casa detectado (float positivo).
          Devuelve (None, None, None, None) si alguna cuota es <= 1.0 o invÃ¡lida.
        """
        c1 = _safe_float(c1)
        cx = _safe_float(cx)
        c2 = _safe_float(c2)
        if c1 is None or cx is None or c2 is None:
            return None, None, None, None
        if c1 <= 1.0 or cx <= 1.0 or c2 <= 1.0:
            return None, None, None, None
 
        pi1_bruta = 1.0 / c1
        pix_bruta = 1.0 / cx
        pi2_bruta = 1.0 / c2
        suma      = pi1_bruta + pix_bruta + pi2_bruta
        overround = suma - 1.0
 
        pi1 = pi1_bruta / suma
        pix = pix_bruta / suma
        pi2 = pi2_bruta / suma
 
        return round(pi1, 4), round(pix, 4), round(pi2, 4), round(overround, 4)
 
    # ââ NUEVO â [v4.2-GAP1] ââââââââââââââââââââââââââââââââââââââââââââââââ
    @staticmethod
    def evaluar_triple(
        p1: float, px: float, p2: float,
        c1: float, cx: float, c2: float,
        bankroll: float,
    ) -> tuple:
        """
        [v4.2-GAP1] EvalÃºa los tres mercados 1X2 con las probabilidades propias
        del motor y las cuotas brutas del mercado. Elige el mercado con mayor EV
        positivo por encima del umbral global EV_THRESHOLD.
        """
        # ââ Sanitizar entradas ââ
        p1       = _safe_float(p1)
        px       = _safe_float(px)
        p2       = _safe_float(p2)
        c1       = _safe_float(c1)
        cx       = _safe_float(cx)
        c2       = _safe_float(c2)
        bankroll = _safe_float(bankroll)
 
        if p1 is None: p1 = 0.0
        if px is None: px = 0.0
        if p2 is None: p2 = 0.0
        if c1 is None: c1 = 0.0
        if cx is None: cx = 0.0
        if c2 is None: c2 = 0.0
        if bankroll is None: bankroll = 1000.0
 
        # ââ Validaciones de negocio ââ
        if c1 <= 1.0 or cx <= 1.0 or c2 <= 1.0:
            return False, None, 0.0, 0.0, {}
 
        if bankroll <= 0.0:
            return False, None, 0.0, 0.0, {}
 
        # ââ Probabilidades implÃ­citas de mercado (referencia de edge) ââ
        pi1, pix, pi2, overround = EscudoFinanciero.normalizar_probabilidades_mercado(
            c1, cx, c2
        )
        if pi1 is None:
            return False, None, 0.0, 0.0, {}
 
        # ââ EV por mercado: prob propia Ã cuota bruta â 1 ââ
        ev1 = p1 * c1 - 1.0
        evx = px * cx - 1.0
        ev2 = p2 * c2 - 1.0
 
        detalle = {
            "ev_1":      round(ev1, 4),
            "ev_x":      round(evx, 4),
            "ev_2":      round(ev2, 4),
            "pi1_mkt":   pi1,
            "pix_mkt":   pix,
            "pi2_mkt":   pi2,
            "overround": overround,
            "edge_1":    round(p1 - pi1, 4),
            "edge_x":    round(px - pix, 4),
            "edge_2":    round(p2 - pi2, 4),
        }
 
        # ââ Candidatos con EV superior al umbral Y edge superior al mÃ­nimo ââ
        candidatos = []
        for mkt, ev_calc, edge_calc, cuota in [
            ("1", ev1, detalle["edge_1"], c1),
            ("X", evx, detalle["edge_x"], cx),
            ("2", ev2, detalle["edge_2"], c2),
        ]:
            if ev_calc > EV_THRESHOLD and edge_calc > MIN_EDGE_REQUERIDO:
                candidatos.append((mkt, ev_calc, cuota))
 
        if not candidatos:
            ev_max = max(ev1, evx, ev2)
            return False, None, round(ev_max, 4), 0.0, detalle
 
        # ââ Elegir el mercado de mayor EV ââ
        candidatos.sort(key=lambda x: x[1], reverse=True)
        mejor_mercado, mejor_ev, mejor_cuota = candidatos[0]
 
        kelly_puro  = mejor_ev / (mejor_cuota - 1.0)
        stake_frac  = kelly_puro * KELLY_FRACTION
        stake_final = round(bankroll * stake_frac, 2)
 
        detalle["mercado_elegido"] = mejor_mercado
        detalle["kelly_puro"]      = round(kelly_puro, 4)
        detalle["stake_pct_bk"]    = round(stake_frac * 100, 2)
 
        return True, mejor_mercado, round(mejor_ev, 4), stake_final, detalle

    # ââ NUEVO â [v4.4-GAP7] ââââââââââââââââââââââââââââââââââââââââââââââââ
    @staticmethod
    def evaluar_binario(
        p_a: float, p_b: float,
        c_a: float, c_b: float,
        bankroll: float,
        etiquetas: tuple = ("OVER", "UNDER"),
    ) -> tuple:
        """
        [v4.4-GAP7] EvalÃºa un mercado binario genÃ©rico (2 resultados
        mutuamente excluyentes) con la MISMA disciplina de EV + edge + Kelly
        que evaluar_triple() aplica a 1X2.
        """
        p_a = _safe_float(p_a); p_b = _safe_float(p_b)
        c_a = _safe_float(c_a); c_b = _safe_float(c_b)
        bankroll = _safe_float(bankroll)

        if p_a is None: p_a = 0.0
        if p_b is None: p_b = 0.0
        if c_a is None: c_a = 0.0
        if c_b is None: c_b = 0.0
        if bankroll is None: bankroll = 1000.0

        if c_a <= 1.0 or c_b <= 1.0:
            return False, None, 0.0, 0.0, {}
        if bankroll <= 0.0:
            return False, None, 0.0, 0.0, {}

        pi_a_bruta, pi_b_bruta = 1.0 / c_a, 1.0 / c_b
        suma      = pi_a_bruta + pi_b_bruta
        overround = suma - 1.0
        pi_a, pi_b = pi_a_bruta / suma, pi_b_bruta / suma

        ev_a = p_a * c_a - 1.0
        ev_b = p_b * c_b - 1.0
        edge_a = p_a - pi_a
        edge_b = p_b - pi_b

        lbl_a, lbl_b = etiquetas[0].lower(), etiquetas[1].lower()
        detalle = {
            f"ev_{lbl_a}":      round(ev_a, 4),
            f"ev_{lbl_b}":      round(ev_b, 4),
            f"pi_{lbl_a}_mkt":  round(pi_a, 4),
            f"pi_{lbl_b}_mkt":  round(pi_b, 4),
            "overround":        round(overround, 4),
            f"edge_{lbl_a}":    round(edge_a, 4),
            f"edge_{lbl_b}":    round(edge_b, 4),
        }

        # Mismo doble filtro que Gap4 aplica a evaluar_triple: EV y edge
        candidatos = []
        for label, ev_calc, edge_calc, cuota in [
            (etiquetas[0], ev_a, edge_a, c_a),
            (etiquetas[1], ev_b, edge_b, c_b),
        ]:
            if ev_calc > EV_THRESHOLD and edge_calc > MIN_EDGE_REQUERIDO:
                candidatos.append((label, ev_calc, cuota))

        if not candidatos:
            return False, None, round(max(ev_a, ev_b), 4), 0.0, detalle

        candidatos.sort(key=lambda x: x[1], reverse=True)
        mejor_label, mejor_ev, mejor_cuota = candidatos[0]

        kelly_puro  = mejor_ev / (mejor_cuota - 1.0)
        stake_frac  = kelly_puro * KELLY_FRACTION
        stake_final = round(bankroll * stake_frac, 2)

        detalle["mercado_elegido"] = mejor_label
        detalle["kelly_puro"]      = round(kelly_puro, 4)
        detalle["stake_pct_bk"]    = round(stake_frac * 100, 2)

        return True, mejor_label, round(mejor_ev, 4), stake_final, detalle

    # ââ NUEVO â [v4.5-GAP9] ââââââââââââââââââââââââââââââââââââââââââââââââ
    ALPHA_RACHA      = 0.15   # penalizaciÃ³n por cada derrota consecutiva
    FACTOR_RACHA_MIN = 0.30   # tope inferior: nunca reduce el stake a menos del 30%

    @staticmethod
    def factor_penalizacion_racha(racha: int) -> float:
        """
        [v4.5-GAP9] Multiplicador de stake basado en la racha de derrotas
        consecutivas mÃ¡s recientes.
        """
        racha = max(0, _safe_int(racha) or 0)
        factor = 1.0 - EscudoFinanciero.ALPHA_RACHA * racha
        return max(EscudoFinanciero.FACTOR_RACHA_MIN, factor)

    @staticmethod
    def evaluar_con_racha(
        p1: float, px: float, p2: float,
        c1: float, cx: float, c2: float,
        bankroll: float,
        racha: int = 0,
    ) -> tuple:
        """
        [v4.5-GAP9] Envuelve evaluar_triple() aplicando penalizaciÃ³n de stake
        por racha adversa reciente.
        """
        operar, mercado, ev, stake, detalle = EscudoFinanciero.evaluar_triple(
            p1, px, p2, c1, cx, c2, bankroll
        )
        factor = EscudoFinanciero.factor_penalizacion_racha(racha)
        stake_ajustado = round(stake * factor, 2)

        detalle["racha_actual"]        = racha
        detalle["factor_racha"]        = round(factor, 4)
        detalle["stake_sin_penalizar"] = stake

        return operar, mercado, ev, stake_ajustado, detalle

    # ââ NUEVO â [v6.0-FASE1] ââââââââââââââââââââââââââââââââââââââââââââââââ
    @staticmethod
    def evaluar_premium(
        p1: float, px: float, p2: float,
        c1: float, cx: float, c2: float,
        bankroll: float,
        racha: int = 0,
        liga_id: str = "",
        auditor = None,
        db_path: str = DATABASE_URL,
        hora_partido: str = None,
    ) -> tuple:
        """
        [v6.0-FASE1] EvaluaciÃ³n integral: Kelly + Racha + P-Value + Regla 300
        + Control de ClÃºster.

        Orquesta las 3 capas de protecciÃ³n financiera del Plan Maestro 2027:
          1. ModulaciÃ³n de Kelly Fraction por confianza estadÃ­stica:
             - PREMIUM (Ã1.5)  si yield > 5%, p-value < 0.05, n >= 300
             - CONSERVADOR (Ã0.5) si n >= 300 pero sin significancia
             - ESTÃNDAR (Ã1.0) si datos insuficientes (fallback seguro)
          2. PenalizaciÃ³n por racha adversa (existente, delegada)
          3. Factor de clÃºster para exposiciÃ³n simultÃ¡nea

        ParÃ¡metros
        ----------
        p1, px, p2       : probabilidades propias del motor (1X2)
        c1, cx, c2       : cuotas brutas del mercado (1X2)
        bankroll         : bankroll actual
        racha            : derrotas consecutivas recientes
        liga_id          : identificador canÃ³nico de la liga
        auditor          : instancia de AuditorRentabilidad (o None)
        db_path          : ruta a cerebrillum.db
        hora_partido     : timestamp ISO del partido para control de clÃºster

        Retorna
        -------
        (operar, mercado, ev, stake_final, detalle)
          detalle incluye claves adicionales:
            confianza_liga, kelly_fraction_usada, factor_cluster,
            p_value, n_apuestas_liga, stake_pre_cluster
        """
        # ââ Paso 1: Determinar fracciÃ³n Kelly por confianza estadÃ­stica ââ
        kelly_frac = KELLY_FRACTION  # default estÃ¡ndar (0.25)
        confianza = "ESTANDAR"
        p_val = 1.0
        n_apuestas = 0

        if auditor is not None and liga_id:
            try:
                stats = auditor.resumen_estadistico_liga(liga_id)
                confianza   = stats.get("confianza", "INSUFICIENTE")
                p_val       = stats.get("p_value", 1.0)
                n_apuestas  = stats.get("n_apuestas", 0)

                if confianza == "PREMIUM":
                    kelly_frac = KELLY_FRACTION_PREMIUM
                elif confianza == "CONSERVADOR":
                    kelly_frac = KELLY_FRACTION_CONSERVADOR
                # INSUFICIENTE o ESTANDAR â mantener KELLY_FRACTION default
            except Exception:
                pass  # fail-safe: usar fracciÃ³n estÃ¡ndar

        # ââ Paso 2: EvaluaciÃ³n Kelly con racha (lÃ³gica existente) ââ
        # Temporalmente sobrescribir KELLY_FRACTION para este cÃ¡lculo
        # Usamos evaluar_triple directamente y aplicamos la fracciÃ³n manualmente
        operar, mercado, ev, stake_base, detalle = EscudoFinanciero.evaluar_triple(
            p1, px, p2, c1, cx, c2, bankroll
        )

        if not operar:
            detalle["confianza_liga"]       = confianza
            detalle["kelly_fraction_usada"] = kelly_frac
            detalle["factor_cluster"]       = 1.0
            detalle["p_value"]              = p_val
            detalle["n_apuestas_liga"]      = n_apuestas
            detalle["stake_pre_cluster"]    = 0.0
            return operar, mercado, ev, 0.0, detalle

        # Recalcular stake con la fracciÃ³n Kelly ajustada
        kelly_puro = detalle.get("kelly_puro", 0.0)
        stake_frac = kelly_puro * kelly_frac
        stake_ajustado = round(bankroll * stake_frac, 2)

        # Aplicar penalizaciÃ³n por racha
        factor_racha = EscudoFinanciero.factor_penalizacion_racha(racha)
        stake_post_racha = round(stake_ajustado * factor_racha, 2)

        # ââ Paso 3: Control de clÃºster ââ
        factor_cl = ControladorCluster.factor_cluster(
            db_path, bankroll, stake_post_racha, hora_partido
        )
        stake_final = round(stake_post_racha * factor_cl, 2)

        # ââ Enriquecer detalle ââ
        detalle["confianza_liga"]       = confianza
        detalle["kelly_fraction_usada"] = round(kelly_frac, 4)
        detalle["factor_cluster"]       = round(factor_cl, 4)
        detalle["p_value"]              = p_val
        detalle["n_apuestas_liga"]      = n_apuestas
        detalle["stake_pre_cluster"]    = stake_post_racha
        detalle["racha_actual"]         = racha
        detalle["factor_racha"]         = round(factor_racha, 4)
        detalle["stake_sin_penalizar"]  = stake_ajustado
        detalle["stake_pct_bk"]         = round(stake_frac * 100, 2)

        return operar, mercado, ev, stake_final, detalle

    # ââ NUEVO â [v7.1-MICRO] ââââââââââââââââââââââââââââââââââââââââââââââââ
    @staticmethod
    def evaluar_triple_neto(
        p1: float, px: float, p2: float,
        c1: float, cx: float, c2: float,
        bankroll: float,
        comision: float = MB_COMMISSION_RATE,
    ) -> tuple:
        """
        [v7.1-MICRO] Igual que evaluar_triple() pero con cuotas ajustadas
        por comisiÃ³n del exchange.

        La cuota efectiva para calcular EV es:
            cuota_neta = 1 + (cuota_bruta - 1) Ã (1 - comisiÃ³n)

        Esto refleja que Matchbook cobra el 2% SOLO sobre la ganancia neta,
        no sobre el stake devuelto. El bankroll es siempre el balance real
        de la cuenta al momento de evaluar â nunca una constante.

        Ejemplo numÃ©rico:
            cuota bruta = 3.00 â ganancia bruta = 2.00 Ã stake
            comisiÃ³n 2% sobre ganancia = 0.04 Ã stake
            cuota neta efectiva = 1 + 2.00 Ã 0.98 = 2.96
            Si prob=0.40 â EV bruto = 0.40Ã3.00 - 1 = +20%
                          â EV neto  = 0.40Ã2.96 - 1 = +18.4%

        ParÃ¡metros
        ----------
        p1, px, p2    : probabilidades propias del motor (1X2)
        c1, cx, c2    : cuotas brutas del mercado (1X2)
        bankroll      : balance REAL de la cuenta (dinÃ¡mico, no constante)
        comision      : tasa de comisiÃ³n del exchange (default MB_COMMISSION_RATE=0.02)

        Retorna
        -------
        (operar, mercado, ev_neto, stake, detalle)
          detalle incluye claves adicionales:
            ev_1_bruto, ev_x_bruto, ev_2_bruto,
            ev_1_neto, ev_x_neto, ev_2_neto,
            comision_aplicada
        """
        # Calcular cuotas netas (descontando comisiÃ³n sobre ganancia)
        def _cuota_neta(c_bruta):
            c_bruta = _safe_float(c_bruta) or 0.0
            if c_bruta <= 1.0:
                return c_bruta
            return 1.0 + (c_bruta - 1.0) * (1.0 - comision)

        c1_neta = _cuota_neta(c1)
        cx_neta = _cuota_neta(cx)
        c2_neta = _cuota_neta(c2)

        # Evaluar con las cuotas netas â el Kelly se calcula sobre el EV real
        operar, mercado, ev_neto, stake, detalle = EscudoFinanciero.evaluar_triple(
            p1, px, p2, c1_neta, cx_neta, c2_neta, bankroll
        )

        # Enriquecer detalle con comparativa bruto vs neto
        p1_f = _safe_float(p1) or 0.0
        px_f = _safe_float(px) or 0.0
        p2_f = _safe_float(p2) or 0.0
        c1_f = _safe_float(c1) or 0.0
        cx_f = _safe_float(cx) or 0.0
        c2_f = _safe_float(c2) or 0.0

        detalle["ev_1_bruto"] = round(p1_f * c1_f - 1.0, 4) if c1_f > 1.0 else 0.0
        detalle["ev_x_bruto"] = round(px_f * cx_f - 1.0, 4) if cx_f > 1.0 else 0.0
        detalle["ev_2_bruto"] = round(p2_f * c2_f - 1.0, 4) if c2_f > 1.0 else 0.0
        detalle["ev_1_neto"]  = round(p1_f * c1_neta - 1.0, 4) if c1_neta > 1.0 else 0.0
        detalle["ev_x_neto"]  = round(px_f * cx_neta - 1.0, 4) if cx_neta > 1.0 else 0.0
        detalle["ev_2_neto"]  = round(p2_f * c2_neta - 1.0, 4) if c2_neta > 1.0 else 0.0
        detalle["comision_aplicada"] = comision
        detalle["cuota_1_neta"] = round(c1_neta, 4)
        detalle["cuota_x_neta"] = round(cx_neta, 4)
        detalle["cuota_2_neta"] = round(c2_neta, 4)

        return operar, mercado, ev_neto, stake, detalle


import numpy as np

class AlmgrenChriss:
    """Modelo de Impacto de Mercado Almgren-Chriss."""
    @staticmethod
    def ajustar_impacto(stake_propuesto: float, liquidez_estimada: float = 10000.0, aversion_riesgo: float = 0.05) -> float:
        """
        Reduce el stake si la orden devorarÃ­a la liquidez (impacto temporal/permanente).
        """
        if liquidez_estimada <= 0: return stake_propuesto
        costo_impacto = (stake_propuesto / liquidez_estimada) ** 1.5
        stake_optimizado = stake_propuesto * np.exp(-aversion_riesgo * costo_impacto)
        return round(stake_optimizado, 2)

class WassersteinDRO:
    """OptimizaciÃ³n Robusta de DistribuciÃ³n de Wasserstein."""
    @staticmethod
    def kelly_robusto(ev: float, cuota: float, fraccion_base: float, incertidumbre: float = 0.05) -> float:
        """
        Modula la fracciÃ³n de Kelly asumiendo una 'bola de ambigÃ¼edad' en la distribuciÃ³n predictiva.
        """
        if cuota <= 1.0 or ev <= 0: return 0.0
        kelly_puro = ev / (cuota - 1.0)
        # PenalizaciÃ³n convexa basada en la incertidumbre del modelo (e.g. MAE, GARCH vol)
        dro_fraction = fraccion_base * np.exp(-incertidumbre * 5.0) # calibraciÃ³n heurÃ­stica
        return round(kelly_puro * dro_fraction, 4)

# ==============================================================================
# [v6.0-FASE1] CONTROL DE EXPOSICIÃN POR CLÃSTER
# ==============================================================================
class ControladorCluster:
    """
    [v6.0-FASE1] Controla la exposiciÃ³n mÃ¡xima por ventana temporal.

    PROBLEMA QUE RESUELVE:
      Al escalar a 200+ apuestas/mes, mÃºltiples partidos ocurren en la misma
      franja horaria. Si cada uno recibe stake Kelly independiente al 2%,
      15 partidos simultÃ¡neos comprometen el 30% del bankroll â violando
      cualquier criterio de riesgo institucional.

    SOLUCIÃN:
      Consulta la tabla cola_partidos_pendientes para detectar apuestas
      activas dentro de una ventana temporal de CLUSTER_VENTANA_HORAS.
      Si la suma de stakes asignados supera CLUSTER_EXPOSICION_MAX del
      bankroll, reduce orgÃ¡nicamente el stake propuesto mediante un factor
      multiplicador â (0.0, 1.0].

    CALIBRACIÃN:
      CLUSTER_EXPOSICION_MAX = 0.15 (15% del bankroll) y
      CLUSTER_VENTANA_HORAS = 3 horas son valores iniciales conservadores.
      Ajustar cuando AuditorRentabilidad acumule >= 300 operaciones con
      datos de clÃºster etiquetados.
    """

    @staticmethod
    def factor_cluster(
        db_path: str,
        bankroll: float,
        stake_propuesto: float,
        hora_partido: str = None,
    ) -> float:
        """
        Calcula factor multiplicador â (0.0, 1.0] para reducir orgÃ¡nicamente
        el stake cuando la exposiciÃ³n simultÃ¡nea supera el techo.

        MATEMÃTICA:
          techo = bankroll Ã CLUSTER_EXPOSICION_MAX
          exposicion_actual = Î£ stakes de partidos pendientes en ventana
          Si (exposicion_actual + stake_propuesto) > techo:
              factor = max(0.0, (techo - exposicion_actual) / stake_propuesto)
          Else:
              factor = 1.0

        ParÃ¡metros
        ----------
        db_path          : ruta a cerebrillum.db
        bankroll         : bankroll actual total
        stake_propuesto  : stake que el Kelly fraccionado sugiere para este partido
        hora_partido     : timestamp ISO del partido (si None, usa datetime.now())

        Retorna
        -------
        float â [0.0, 1.0] â multiplicador sobre el stake.
        1.0 = sin reducciÃ³n, 0.0 = no apostar (techo ya saturado).
        """
        import sqlite3
        import json
        from datetime import datetime, timedelta

        bankroll = _safe_float(bankroll) or 1000.0
        stake_propuesto = _safe_float(stake_propuesto) or 0.0
        if stake_propuesto <= 0:
            return 1.0

        techo = bankroll * CLUSTER_EXPOSICION_MAX

        # Determinar ventana temporal
        try:
            if hora_partido:
                centro = datetime.fromisoformat(hora_partido)
            else:
                centro = datetime.now()
        except (ValueError, TypeError):
            centro = datetime.now()

        ventana_inicio = centro - timedelta(hours=CLUSTER_VENTANA_HORAS / 2)
        ventana_fin    = centro + timedelta(hours=CLUSTER_VENTANA_HORAS / 2)

        # Consultar partidos pendientes no cerrados
        exposicion_actual = 0.0
        try:
            conn = sqlite3.connect(db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT payload_json FROM cola_partidos_pendientes WHERE cerrado = 0"
            )
            for (payload_raw,) in cur.fetchall():
                try:
                    payload = json.loads(payload_raw)
                    stake_pendiente = _safe_float(payload.get("stake", 0.0)) or 0.0
                    fecha_str = payload.get("timestamp", "")
                    if fecha_str:
                        try:
                            fecha_partido = datetime.fromisoformat(fecha_str)
                            if ventana_inicio <= fecha_partido <= ventana_fin:
                                exposicion_actual += stake_pendiente
                        except (ValueError, TypeError):
                            # Sin fecha parseable, asumimos que estÃ¡ en ventana
                            # (principio de precauciÃ³n)
                            exposicion_actual += stake_pendiente
                    else:
                        exposicion_actual += stake_pendiente
                except (json.JSONDecodeError, TypeError):
                    continue
            conn.close()
        except sqlite3.Error:
            # Si no se puede leer la DB, no reducir (fail-open conservador)
            return 1.0

        # Calcular factor de reducciÃ³n
        if (exposicion_actual + stake_propuesto) > techo:
            espacio_disponible = techo - exposicion_actual
            if espacio_disponible <= 0:
                return 0.0
            return round(max(0.0, espacio_disponible / stake_propuesto), 4)

        return 1.0

# ==============================================================================
# [HFT] Motor de Interés Compuesto (Kelly Acelerado)
# ==============================================================================
class MotorInteresCompuesto:
    """
    Disenado para multiplicar micro-capitales.
    """
    
    META_CAPITAL = 100000.0  # Meta de 100,000 MXN
    
    @staticmethod
    def verificar_circuit_breakers(bankroll_actual: float, max_bankroll_diario: float) -> str:
        """
        Verifica los mecanismos de protección de drawdown.
        Retorna un código de alerta ('HARD_STOP', 'TRAILING_STOP', o None)
        """
        if bankroll_actual <= 30.0:
            return "HARD_STOP"
        
        if max_bankroll_diario > 0 and bankroll_actual <= (max_bankroll_diario * 0.80):
            return "TRAILING_STOP"
            
        return None

    @staticmethod
    def calcular_stake_hft(bankroll_actual: float, ev_neto: float, cuota: float, max_kelly: float = 0.25, racha_perdidas: int = 0, max_bankroll_diario: float = 0.0) -> float:
        """
        Calcula el tamaño de posición (Stake) para operaciones de Alta Frecuencia.
        :param bankroll_actual: Capital actual del usuario.
        :param ev_neto: Valor Esperado (ya deducido de la comisión del 4%).
        :param cuota: Cuota decimal (ej. 2.10).
        :param max_kelly: Porcentaje máximo del bankroll a arriesgar (Kelly fraction base).
        :param racha_perdidas: Número de derrotas consecutivas.
        :param max_bankroll_diario: Pico máximo diario del bankroll.
        """
        if ev_neto <= 0 or cuota <= 1.0:
            return 0.0
            
        cb_alert = MotorInteresCompuesto.verificar_circuit_breakers(bankroll_actual, max_bankroll_diario)
        if cb_alert:
            return 0.0
            
        # Fórmula Kelly Pura: f* = EV / (Cuota - 1)
        # ev_neto = p * cuota - 1 => p = (ev_neto + 1) / cuota
        p = (ev_neto + 1) / cuota
        q = 1 - p
        b = cuota - 1
        kelly_fraction = (b * p - q) / b
        
        # 2. Dynamic Risk Reduction
        if racha_perdidas >= 3:
            multiplicador = 1.0  # Modo defensivo
        else:
            # Apalancamiento Agresivo calibrado para meta $100→$10,000 MXN
            if bankroll_actual < 300:
                multiplicador = 4.0  # Arranque ultra-agresivo
            elif bankroll_actual < 1000:
                multiplicador = 3.0  # Fase de construcción temprana
            elif bankroll_actual < 10000:
                multiplicador = 2.0  # Fase de construcción media
            else:
                multiplicador = 1.0  # Protección de ganancias (fase final)
            
        kelly_ajustado = kelly_fraction * max_kelly * multiplicador
        
        # Limitar para no quebrar instantáneamente (Max 30% del bankroll real por trade)
        kelly_ajustado = min(kelly_ajustado, 0.30)
        
        stake = bankroll_actual * kelly_ajustado
        
        # Límite técnico de Matchbook: Asegurar un mínimo de ~2.00 MXN o su equivalente
        return max(stake, 2.0) if bankroll_actual >= 2.0 else bankroll_actual


