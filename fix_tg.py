import re

with open('orquestadores_principales/HFT_GALO.py', 'r', encoding='utf-8') as f:
    text = f.read()

codigo_viejo = '''                    if stake >= 2.0:
                        logger.info(f"[MLOps/HFT] Oportunidad | {nombre_partido} | {runner_name} @ {back_odds} | Spread: {spread:.2f} | EV Neto: {ev_neto*100:.2f}% | Stake: ")
                        
                        cooldowns_mercado[uid] = ahora'''

codigo_nuevo = '''                    if stake >= 2.0:
                        msg = f"? [HFT EJECUCIÓN] ?\\n\\n? Partido: {nombre_partido}\\n?? Selección: {runner_name}\\n?? Cuota: {back_odds}\\n?? Spread: {spread:.2f}\\n?? EV Neto: {ev_neto*100:.2f}%\\n?? Stake Inyectado:  MXN"
                        logger.info(f"[MLOps/HFT] Oportunidad | {nombre_partido} | {runner_name} @ {back_odds} | Spread: {spread:.2f} | EV Neto: {ev_neto*100:.2f}% | Stake: ")
                        telegram.enviar_mensaje(msg)
                        
                        cooldowns_mercado[uid] = ahora'''

text = text.replace(codigo_viejo, codigo_nuevo)

with open('orquestadores_principales/HFT_GALO.py', 'w', encoding='utf-8') as f:
    f.write(text)
