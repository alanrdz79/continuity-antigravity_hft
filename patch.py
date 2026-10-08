import re
content = open('conectores/binance_prediction.py', 'r', encoding='utf-8').read()
old_text = '''        params = {
            "marketId": symbol,
            "orderType": order_type,
            "side": side,
            "quantity": quantity,
        }
        if price:'''
new_text = '''        params = {
            "marketId": symbol,
            "orderType": order_type,
            "side": side,
            "quantity": quantity,
            "walletAddress": "0x1efd0496e1836d3ff0950b14412aa1b3a8356dad",
            "fundingSource": "CEX",
        }
        if order_type.upper() == "MARKET":
            params["timeInForce"] = "FOK"
        else:
            params["timeInForce"] = "GTC"

        if price:'''
content = content.replace(old_text, new_text)
open('conectores/binance_prediction.py', 'w', encoding='utf-8').write(content)
