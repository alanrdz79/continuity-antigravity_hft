import asyncio
import os
import time
import hmac
import hashlib
import aiohttp
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')

async def probe_endpoint(session, path):
    url = f'https://api.binance.com{path}'
    timestamp = int(time.time() * 1000)
    query = f'timestamp={timestamp}'
    signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
    full_url = f'{url}?{query}&signature={signature}'
    headers = {'X-MBX-APIKEY': api_key}
    async with session.get(full_url, headers=headers) as resp:
        text = await resp.text()
        print(f'{path} -> {resp.status} {text[:200]}')

async def main():
    async with aiohttp.ClientSession() as session:
        endpoints = [
            '/sapi/v1/w3w/wallet/prediction/account',
            '/sapi/v1/w3w/wallet/prediction/wallet',
            '/sapi/v1/w3w/wallet/prediction/position/filter',
            '/sapi/v1/w3w/account',
            '/sapi/v1/w3w/wallet/account',
            '/sapi/v1/w3w/wallet/prediction/balance',
            '/sapi/v1/w3w/wallet/prediction/address'
        ]
        for e in endpoints:
            await probe_endpoint(session, e)

asyncio.run(main())
