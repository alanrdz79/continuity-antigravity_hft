# Dispatch: Worker M1 — Ingestion, Connectors & Microstructure Core

Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Files you own exclusively:
- `conectores/binance_async.py`
- `continuitis/microestructura_binance.py`

Deliverables:
1. `conectores/binance_async.py`:
   - Async Binance Spot WebSocket client subscribing to Level-2 order book depth with reconnect logic and ping/pong heartbeat.
   - Maintains in-RAM $\mathcal{O}(1)$ top 5-10 bids and asks with timestamps.
   - Binance Spot REST client for order execution (place limit/market order, cancel order, cancel all, query status).
   - Mocking mode / offline simulation support for unit and integration testing without live credentials.
2. `continuitis/microestructura_binance.py`:
   - Order Book Imbalance calculation: $I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$.
   - Exact 80% buy dominance detection ($I \ge 0.60$).
   - Golden Rule 1: Max spread $\le \$0.03$; reject trade if spread $> \$0.03$.
   - Golden Rule 2: Automatic lock on new orders if MarketStatus == 'SUSPENDED'.
   - Golden Rule 3 support: Volume aggregation across top 3 BID levels ($\sum_{k=1}^3 V_{\text{Bid}}^{(k)}$).
   - Latency monitor and circuit breaker (<800ms threshold, emergency flag if exceeded).
   - Price calculation: Best Bid + 1 tick for Limit Buy entry; Best Ask + 2 ticks for Limit Sell exit.
3. Verify your work by running Python syntax checks or unit tests using python in `.venv`.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m1
Write your implementation report to `report.md` and deliver `handoff.md` in your working directory. Send a message to parent when complete.


## 2026-10-07T03:59:10Z
[Message] timestamp=2026-10-07T03:59:10Z sender=f2f51f43-3860-4c33-b19f-c0b7ef73f3b6 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_preview_worker (Worker M1).
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m1
Your task assignment is in: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m1\DISPATCH.md

MANDATORY: Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Files you own exclusively:
- conectores/binance_async.py
- continuitis/microestructura_binance.py

Deliverables:
1. conectores/binance_async.py:
   - Async Binance Spot WebSocket client subscribing to Level-2 order book depth with reconnect logic and ping/pong heartbeat.
   - Maintains in-RAM O(1) top 5-10 bids and asks with timestamps.
   - Binance Spot REST client for order execution (place limit/market order, cancel order, cancel all, query status).
   - Mocking mode / offline simulation support for unit and integration testing without live credentials.
2. continuitis/microestructura_binance.py:
   - Order Book Imbalance calculation: I = (sum V_Bid - sum V_Ask) / (sum V_Bid + sum V_Ask).
   - Exact 80% buy dominance detection (I >= 0.60).
   - Golden Rule 1: Max spread <= $0.03; reject trade if spread > $0.03.
   - Golden Rule 2: Automatic lock on new orders if MarketStatus == 'SUSPENDED'.
   - Golden Rule 3 support: Volume aggregation across top 3 BID levels.
   - Latency monitor and circuit breaker (<800ms threshold, emergency flag if exceeded).
   - Price calculation: Best Bid + 1 tick for Limit Buy entry; Best Ask + 2 ticks for Limit Sell exit.
3. Verify your work by running Python syntax checks or unit tests.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write report.md and deliver handoff.md in your working directory. Send a message to parent when complete.
