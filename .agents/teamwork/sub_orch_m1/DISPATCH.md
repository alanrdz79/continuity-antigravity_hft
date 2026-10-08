# Dispatch: Milestone 1 Sub-Orchestrator

Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Scope: Milestone 1 — Ingestion, Connectors & Microstructure Core
Files owned exclusively:
- `conectores/binance_async.py`
- `continuitis/microestructura_binance.py`

Deliverables:
1. `conectores/binance_async.py`:
   - Async WebSocket connection to Binance Spot L2 depth feed with auto-reconnect and ping/pong heartbeat.
   - In-RAM $\mathcal{O}(1)$ top 5-10 bids/asks depth maintainer.
   - Binance Spot REST execution client (order placement, cancellation, account info).
   - Mocking capability / offline test mode for automated test suites.
2. `continuitis/microestructura_binance.py`:
   - Order Book Imbalance calculation: $I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$.
   - Exact 80% buy dominance detection ($I \ge 0.60$).
   - Golden Rule 1: Max spread $\le \$0.03$; reject if spread $> \$0.03$.
   - Golden Rule 2: Automatic lock on new orders if MarketStatus == 'SUSPENDED'.
   - Golden Rule 3 support: Volume aggregation across top 3 BID levels for exit liquidity.
   - Latency calculation and circuit breaker (<800ms threshold).
   - Price calculation: Best Bid + 1 tick for Limit Buy, Best Ask + 2 ticks for Limit Sell exit.
3. Unit verification tests for M1 components ensuring 100% build and test pass.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\sub_orch_m1
Follow standard orchestrator iteration loop (Explorer -> Worker -> Reviewer -> Challenger -> Auditor -> Gate) and report back with handoff.md.
