import re

with open('orquestadores_principales/HFT_GALO.py', 'r', encoding='utf-8') as f:
    text = f.read()

codigo_nuevo = '''
                # Control de Varianza y Liquidez
                spread = lay_odds - back_odds
                if spread > MAX_SPREAD_PERMITIDO:
                    if spread <= 0.35:
                        logger.info(f"[Filtro Spread] {runner_name[:15]} | {spread:.2f} > {MAX_SPREAD_PERMITIDO}")
                    continue
'''

text = re.sub(r'# Control de Varianza y Liquidez\s+spread = lay_odds - back_odds\s+if spread > MAX_SPREAD_PERMITIDO:\s+.*?\s+continue', codigo_nuevo.strip(), text, flags=re.DOTALL)

with open('orquestadores_principales/HFT_GALO.py', 'w', encoding='utf-8') as f:
    f.write(text)
