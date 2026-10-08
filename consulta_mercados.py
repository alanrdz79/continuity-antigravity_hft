import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from conectores.matchbook_async import MatchbookClientAsync
from collections import defaultdict

async def run():
    mb = MatchbookClientAsync()
    await mb.init_session()
    eventos = await mb.obtener_eventos_hft(sport_ids='')

    resumen = defaultdict(lambda: {'runners': 0, 'min_gap': 99.0, 'mejor_evento': ''})

    for ev in eventos:
        sport = str(ev.get('sport-id', '?'))
        nombre = ev.get('name', '?')
        for mkt in ev.get('markets', []):
            for runner in mkt.get('runners', []):
                prices = runner.get('prices', [])
                back_prices = [p for p in prices if p.get('side') == 'back']
                lay_prices  = [p for p in prices if p.get('side') == 'lay']
                if not back_prices or not lay_prices:
                    continue
                best_back = max(back_prices, key=lambda p: p.get('odds', 0))
                best_lay  = min(lay_prices,  key=lambda p: p.get('odds', 999))
                b = best_back.get('odds', 1)
                l = best_lay.get('odds', 1)
                if b > 1.01 and l > 1.01:
                    gap = (1.0/b) - (1.0/l)
                    resumen[sport]['runners'] += 1
                    if gap < resumen[sport]['min_gap']:
                        resumen[sport]['min_gap'] = gap
                        resumen[sport]['mejor_evento'] = nombre

    print('SPORT_ID | RUNNERS | MIN_GAP  | MEJOR_EVENTO')
    print('-' * 80)
    for sid, data in sorted(resumen.items(), key=lambda x: x[1]['min_gap']):
        print('{} | {:4d} | {:7.3f}% | {}'.format(
            sid, data['runners'], data['min_gap']*100, data['mejor_evento']))

    await mb.cerrar_sesion()

asyncio.run(run())
