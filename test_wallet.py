import time
import hmac
import hashlib
import requests
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')
headers = {'X-MBX-APIKEY': api_key}

endpoints = [
    '/sapi/v1/w3w/wallet/account',
    '/sapi/v1/w3w/account',
    '/sapi/v1/w3w/wallet/prediction/account',
    '/sapi/v1/capital/config/getall'
]
for ep in endpoints:
    url = f'https://api.binance.com{ep}'
    timestamp = int(time.time() * 1000)
    query_string = f'timestamp={timestamp}'
    signature = hmac.new(api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
    resp = requests.get(f'{url}?{query_string}&signature={signature}', headers=headers)
    print(f'{ep}: {resp.status_code}')

