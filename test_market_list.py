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
url = 'https://api.binance.com/sapi/v1/w3w/wallet/prediction/market/list'
timestamp = int(time.time() * 1000)
query_string = f'timestamp={timestamp}&limit=5'
signature = hmac.new(api_secret.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()
resp = requests.get(f'{url}?{query_string}&signature={signature}', headers=headers)
print(resp.text)

