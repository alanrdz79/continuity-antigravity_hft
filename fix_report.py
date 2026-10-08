import re

with open('orquestadores_principales/HFT_GALO.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Inyectar función reporte_periodico justo antes de daemon_hft
funcion_reporte = '''
async def reporte_periodico(matchbook):
    while True:
        await asyncio.sleep(10800) # 3 horas
        try:
            bankroll_actual = await matchbook.obtener_balance()
            ganancia = bankroll_actual - BALANCE_INICIO_DIA
            porcentaje = (ganancia / BALANCE_INICIO_DIA * 100) if BALANCE_INICIO_DIA > 0 else 0
            
            signo = "+" if ganancia >= 0 else ""
            msg = (
                f"?? [CORTE DE CAJA HFT - 3H] ??\\n\\n"
                f"?? Balance Inicial:  MXN\\n"
                f"?? Balance Actual:  MXN\\n"
                f"?? Rendimiento: {signo} MXN ({signo}{porcentaje:.2f}%)\\n\\n"
                f"? Estado del Motor: 100% Activo y buscando liquidez."
            )
            telegram.enviar_mensaje(msg)
            logger.info("[Reporte 3H] Enviado a Telegram con exito.")
        except Exception as e:
            logger.error(f"[Reporte 3H] Error enviando reporte: {e}")

async def daemon_hft():'''

text = text.replace('async def daemon_hft():', funcion_reporte)

# Inyectar el inicio de la tarea en daemon_hft()
codigo_viejo = '''    telegram.notificar_inicio(version="HFT MLOps v1.1", balance_inicial=BALANCE_INICIO_DIA)
    matchbook.iniciar_heartbeat()

    try:'''
codigo_nuevo = '''    telegram.notificar_inicio(version="HFT MLOps v1.1", balance_inicial=BALANCE_INICIO_DIA)
    matchbook.iniciar_heartbeat()
    asyncio.create_task(reporte_periodico(matchbook))

    try:'''

text = text.replace(codigo_viejo, codigo_nuevo)

with open('orquestadores_principales/HFT_GALO.py', 'w', encoding='utf-8') as f:
    f.write(text)
