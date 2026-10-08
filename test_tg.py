import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
import aiohttp
async def send():
    url=f'https://api.telegram.org/bot{os.getenv("TELEGRAM_BOT_TOKEN")}/sendMessage'
    data={'chat_id': os.getenv("TELEGRAM_CHAT_ID"), 'text': 'Mensaje directo de prueba desde el servidor de Tokio.'}
    async with aiohttp.ClientSession() as s:
        await s.post(url, json=data)
    print('Sent')
asyncio.run(send())
