# -*- coding: utf-8 -*-
"""
conectores.telegram_bot
=======================
Notificador a Telegram para el sistema CONTINUITY.
Envía reportes cada 6 horas con estadísticas del sistema.
"""

import logging
from typing import Optional, Dict
from datetime import datetime
from .base import ConectorBase

logger = logging.getLogger("CONTINUITY.Telegram")

class TelegramNotifier(ConectorBase):
    """
    Envía mensajes y reportes periódicos al chat de Telegram configurado.
    """

    BASE_URL = "https://api.telegram.org/bot"

    def __init__(self, bot_token: str, chat_id: str):
        super().__init__(api_key=bot_token, calls_per_sec=1.0)
        self.bot_token = bot_token
        self.chat_id = chat_id

    # ------------------------------------------------------------------
    # Notificación de INICIO del sistema
    # ------------------------------------------------------------------
    def notificar_inicio(self, version: str = "ASYNC REAL", balance_inicial: float = 0.0):
        """Notifica que el sistema arrancó correctamente."""
        ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
        texto = (
            f"🟢 <b>CONTINUITY INICIADO</b> 🟢\n\n"
            f"🕐 Hora: {ahora}\n"
            f"⚙️ Modo: {version}\n"
            f"💰 Balance inicial: ${balance_inicial:.2f} MXN\n"
            f"📡 Sistema activo — reportes cada 6 horas."
        )
        return self.enviar_mensaje(texto)

    # ------------------------------------------------------------------
    # Notificación de CIERRE del sistema
    # ------------------------------------------------------------------
    def notificar_cierre(self, balance_final: float = 0.0, balance_inicial: float = 0.0,
                         total_apuestas: int = 0, ganancia_dia: float = 0.0):
        """Notifica que el sistema se apagó."""
        ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
        diferencia = balance_final - balance_inicial
        signo = "+" if diferencia >= 0 else ""
        texto = (
            f"🔴 <b>CONTINUITY APAGADO</b> 🔴\n\n"
            f"🕐 Hora cierre: {ahora}\n"
            f"💰 Balance final: ${balance_final:.2f} MXN\n"
            f"📈 Diferencia sesión: {signo}${diferencia:.2f} MXN\n"
            f"🎯 Apuestas en sesión: {total_apuestas}\n"
            f"📊 Ganancia del día: {'+' if ganancia_dia >= 0 else ''}${ganancia_dia:.2f} MXN"
        )
        return self.enviar_mensaje(texto)

    # ------------------------------------------------------------------
    # Reporte de resumen cada 6 horas
    # ------------------------------------------------------------------
    def enviar_resumen_6h(self, stats: Dict, balance_actual: float, balance_inicial_dia: float):
        """
        Envía un resumen completo del período de 6 horas.

        stats debe contener:
          - total_apuestas: int
          - apuestas_por_deporte: dict {deporte: count}
          - apuestas_por_liga: dict {liga: count}
          - apuestas_por_mercado: dict {"1"|"X"|"2": count}
          - stakes_total: float (total apostado en MXN)
          - ordenes_activas: int
        """
        ahora = datetime.now().strftime("%d/%m/%Y %H:%M")
        total = stats.get("total_apuestas", 0)
        ganancia_dia = balance_actual - balance_inicial_dia
        signo_dia = "+" if ganancia_dia >= 0 else ""

        # Deportes
        dep_str = ""
        for dep, cnt in stats.get("apuestas_por_deporte", {}).items():
            dep_str += f"  • {dep.capitalize()}: {cnt}\n"
        if not dep_str:
            dep_str = "  • Sin apuestas aún\n"

        # Ligas (top 5)
        ligas = sorted(stats.get("apuestas_por_liga", {}).items(), key=lambda x: x[1], reverse=True)[:5]
        liga_str = ""
        for liga, cnt in ligas:
            liga_str += f"  • {liga}: {cnt}\n"
        if not liga_str:
            liga_str = "  • Sin apuestas aún\n"

        # Tipos de mercado
        mercados = stats.get("apuestas_por_mercado", {})
        mkt_str = ""
        for mkt, cnt in mercados.items():
            nombre = {"1": "Local (1)", "X": "Empate (X)", "2": "Visitante (2)"}.get(mkt, mkt)
            mkt_str += f"  • {nombre}: {cnt}\n"
        if not mkt_str:
            mkt_str = "  • Sin apuestas aún\n"

        texto = (
            f"📊 <b>REPORTE 6H — CONTINUITY</b> 📊\n"
            f"🕐 {ahora}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 <b>Balance actual:</b> ${balance_actual:.2f} MXN\n"
            f"📈 <b>Ganancia del día:</b> {signo_dia}${ganancia_dia:.2f} MXN\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🎯 <b>Apuestas (últimas 6h):</b> {total}\n"
            f"🔄 <b>Órdenes activas ahora:</b> {stats.get('ordenes_activas', 0)}\n"
            f"💵 <b>Total apostado (6h):</b> ${stats.get('stakes_total', 0.0):.2f} MXN\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"⚽ <b>Por deporte:</b>\n{dep_str}"
            f"🏆 <b>Por liga (top 5):</b>\n{liga_str}"
            f"📋 <b>Por tipo de mercado:</b>\n{mkt_str}"
        )
        return self.enviar_mensaje(texto)

    # ------------------------------------------------------------------
    # Envío base de mensaje genérico
    # ------------------------------------------------------------------
    def enviar_mensaje(self, texto: str) -> bool:
        """Envía un mensaje de texto al chat configurado."""
        if not self.bot_token or not self.chat_id:
            logger.warning("[Telegram] Token o Chat ID no configurados.")
            return False

        url = f"{self.BASE_URL}{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": texto,
            "parse_mode": "HTML"
        }

        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                resp = self.session.post(url, json=payload, timeout=10)
                resp.raise_for_status()
                return True
            except Exception as e:
                logger.error(f"[Telegram] Error enviando mensaje (intento {attempt+1}): {e}")

        return False
