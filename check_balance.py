import os
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')

url = 'https://api.binance.com/api/v3/account'
timestamp = int(time.time() * 1000)
query = f'timestamp={timestamp}'
signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
full_url = f'{url}?{query}&signature={signature}'
headers = {'X-MBX-APIKEY': api_key}

resp = requests.get(full_url, headers=headers)
if resp.status_code == 200:
    data = resp.json()
    balances = [b for b in data['balances'] if float(b['free']) > 0 or float(b['locked']) > 0]
    for b in balances:
        print(f"Asset: {b['asset']}, Free: {b['free']}, Locked: {b['locked']}")
else:
    print(f'Error: {resp.status_code} {resp.text}')
