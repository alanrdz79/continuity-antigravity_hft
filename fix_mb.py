import re

with open('conectores/matchbook_async.py', 'r', encoding='utf-8') as f:
    text = f.read()

# Buscamos la asignación de params en obtener_eventos_hft
# Le inyectaremos un if not sport_ids: del params['sport-ids']
codigo_viejo = '''        params = {
            "sport-ids": sport_ids, "states": "open,suspended", "per-page": 100,
            "include-markets": "true", "include-runners": "true",
            "minimum-liquidity": 10, "price-depth": 3, "price-mode": "aggregated",
            "after": int(ahora.timestamp()), "before": int(limite.timestamp())
        }'''

codigo_nuevo = '''        params = {
            "states": "open,suspended", "per-page": 100,
            "include-markets": "true", "include-runners": "true",
            "minimum-liquidity": 10, "price-depth": 3, "price-mode": "aggregated",
            "after": int(ahora.timestamp()), "before": int(limite.timestamp())
        }
        if sport_ids:
            params["sport-ids"] = sport_ids
'''

text = text.replace(codigo_viejo, codigo_nuevo)

with open('conectores/matchbook_async.py', 'w', encoding='utf-8') as f:
    f.write(text)
