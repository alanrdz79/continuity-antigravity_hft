import os
from dotenv import load_dotenv
load_dotenv()
print('TOKEN:', repr(os.getenv('TELEGRAM_BOT_TOKEN')))
print('CHAT_ID:', repr(os.getenv('TELEGRAM_CHAT_ID')))
