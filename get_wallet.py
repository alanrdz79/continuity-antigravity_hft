import os
import time
import hmac
import hashlib
import requests
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv('BINANCE_API_KEY')
api_secret = os.getenv('BINANCE_SECRET_KEY')

url = 'https://api.binance.com/sapi/v1/w3w/wallet/prediction/wallet/list'
timestamp = int(time.time() * 1000)
query = f'timestamp={timestamp}'
signature = hmac.new(api_secret.encode(), query.encode(), hashlib.sha256).hexdigest()
full_url = f'{url}?{query}&signature={signature}'
headers = {'X-MBX-APIKEY': api_key}

resp = requests.get(full_url, headers=headers)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text}')
