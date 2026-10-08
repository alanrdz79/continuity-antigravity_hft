(Get-Content conectores\binance_prediction.py) -replace 'from .base import ConectorBase, OrderBookSnapshot', 'from .base import ConectorBase
from dataclasses import dataclass
@dataclass
class OrderBookSnapshot:
    symbol: str
    bids: Tuple[Tuple[float, float], ...]
    asks: Tuple[Tuple[float, float], ...]
    timestamp_ms: int
    market_status: str = "ACTIVE"' | Set-Content conectores\binance_prediction.py
