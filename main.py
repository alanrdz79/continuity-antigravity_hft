import asyncio
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from dotenv import load_dotenv

from orquestadores_principales.HFT_BINANCE import ContinuityHFTBinanceOrchestrator

load_dotenv()

logger = logging.getLogger('CONTINUITY')

orquestador = ContinuityHFTBinanceOrchestrator(
    mock_mode=False,
    api_key=os.getenv('BINANCE_API_KEY', ''),
    api_secret=os.getenv('BINANCE_SECRET_KEY', ''),
    telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
    telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', '')
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info('Arrancando CONTINUITY HFT en segundo plano...')
    task = asyncio.create_task(orquestador.run_forever())
    yield
    logger.info('Apagando CONTINUITY HFT...')
    await orquestador.stop()
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(title='CONTINUITY HFT Binance', lifespan=lifespan)

@app.get('/health')
def health_check():
    return {'status': 'ok'}

@app.get('/')
def read_root():
    return {'message': 'CONTINUITY HFT En linea', 'running': orquestador.is_running}

