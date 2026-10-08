import asyncio
import os
from dotenv import load_dotenv
from conectores.matchbook_async import MatchbookClientAsync
from conectores.telegram_bot import TelegramNotifier

load_dotenv()
telegram = TelegramNotifier(bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""), chat_id=os.getenv("TELEGRAM_CHAT_ID", ""))

async def run_demo():
    matchbook = MatchbookClientAsync()
    await matchbook.init_session()
    
    eventos = await matchbook.obtener_eventos_hft(sport_ids="")
    if not eventos:
        print("No hay eventos activos para la demo.")
        return

    # Buscar el primer partido con mercados válidos
    evento = eventos[0]
    mercado = evento["markets"][0]
    runner = mercado["runners"][0]
    runner_id = runner["id"]
    
    print(f"Colocando orden DEMO en {evento['name']} -> {runner['name']}")
    
    # Stake mínimo (2.0) y cuota altísima (100.0) para que NUNCA se ejecute y no pierdas ni 1 centavo.
    res = await matchbook.colocar_apuesta(runner_id, stake=2.0, odds=100.0, side="back", modo="maker")
    
    msg = (
        f"?? [HFT MUESTRA DE CONEXIÓN] ??\n\n"
        f"? Partido: {evento['name']}\n"
        f"?? Selección: {runner['name']}\n"
        f"?? Cuota Maker: 100.0 (Seguridad Activa)\n"
        f"?? Stake: .00 MXN\n\n"
        f"?? Entra a tu cuenta de Matchbook en la sección 'Unmatched / Órdenes Abiertas'. Ahí verás este billete de  pesos esperando. Puedes cancelarlo manualmente."
    )
    telegram.enviar_mensaje(msg)
    print("Demo completada. Revisa tu Telegram y tu cuenta de Matchbook.")
    
    await matchbook.cerrar_sesion()

if __name__ == "__main__":
    asyncio.run(run_demo())
