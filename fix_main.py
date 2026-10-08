import os; content = open('orquestadores_principales/HFT_BINANCE.py', encoding='utf-8').read(); content = content.split('if __name__')[0] + '''
if __name__ == '__main__':
    import asyncio
    from dotenv import load_dotenv
    load_dotenv()
    import os
    orquestador = ContinuityHFTBinanceOrchestrator(
        mock_mode=False,
        api_key=os.getenv('BINANCE_API_KEY', ''),
        api_secret=os.getenv('BINANCE_SECRET_KEY', ''),
        telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
        telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', '')
    )
    asyncio.run(orquestador.run_forever())'''; open('orquestadores_principales/HFT_BINANCE.py', 'w', encoding='utf-8').write(content)
