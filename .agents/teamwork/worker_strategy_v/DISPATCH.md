# Dispatch: Worker Strategy V — Dynamic Cross-Venue Arbitrage & AMM Bonding-Curve Sniping

Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md (specifically directive 2026-10-07T08:38:51Z)
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Files you own exclusively:
- `estrategias/arbitraje_amm.py`
- `pruebas_unitarias/test_arbitraje_amm.py`

Deliverables:
1. `estrategias/arbitraje_amm.py`:
   - Implement `EstrategiaVArbitrajeAMM`:
     * Rule 1: Dynamic cross-venue curve deviation arbitrage comparing Binance Predict (YES/NO) implied probabilities against external fair probability / benchmark ($P_{\text{fair}}$). When deviation $|\text{implied} - P_{\text{fair}}| > \text{umbral}$ (e.g. 3-5%), buys undervalued contract and programs exit on bounce within 2 to 15 seconds.
     * Rule 2: Deterministic binary parity dual-purchase arbitrage: If `Best Ask(YES) + Best Ask(NO) < 1.00 - comisiones_totales`, triggers atomic simultaneous dual-buy to lock guaranteed risk-free redemption profit ($1.00 - \sum \text{Asks} - \text{fees} > 0$).
     * Rule 3: Risk & Latency integration: Strictly respects the 15% cluster exposure cap via `AsyncCapitalGateway` or `EscudoFinancieroBinance`. Enforces hard execution timeout (aborts/liquidates if in-flight > 2.5 seconds) and halts immediately if `MarketStatus == 'SUSPENDED'`.
     * Clean modular export that integrates smoothly without breaking existing modules.
2. `pruebas_unitarias/test_arbitraje_amm.py`:
   - 4-Tier test suite:
     * Tier 1: Binary parity trigger condition (`Best Ask(YES) + Best Ask(NO) < 0.98`), fair price deviation entry and 2-15s scalp exit.
     * Tier 2: Boundary conditions (sum of asks = 1.0000, 1.0001, 0.9999; zero-volume books).
     * Tier 3: 15% cluster cap compliance and 2.5s latency abort.
     * Tier 4: MarketStatus SUSPENDED immediate lock and multi-event arbitrage run.
3. Run pytest (`.venv\Scripts\python.exe -m pytest pruebas_unitarias/test_arbitraje_amm.py`) and verify 100% tests pass.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_strategy_v
Write report.md and deliver handoff.md in your working directory. Send a message to parent when complete.


## 2026-10-07T08:41:05Z
[Message] timestamp=2026-10-07T08:41:05Z sender=f2f51f43-3860-4c33-b19f-c0b7ef73f3b6 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_preview_worker (Worker Strategy V).
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_strategy_v
Your task assignment is in: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_strategy_v\DISPATCH.md
