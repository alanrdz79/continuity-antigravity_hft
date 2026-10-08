import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from orquestadores_principales.HFT_BINANCE import ContinuityHFTBinanceOrchestrator
orq = ContinuityHFTBinanceOrchestrator(
    mock_mode=False,
    api_key='a',
    api_secret='b',
    telegram_token=os.getenv('TELEGRAM_BOT_TOKEN'),
    telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID')
)
asyncio.run(orq.telegram_bot.notificar_inicio(version='TEST INICIO 123', balance_inicial=10.0))
