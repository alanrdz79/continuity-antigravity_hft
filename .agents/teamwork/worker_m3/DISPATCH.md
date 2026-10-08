# Dispatch: Worker M3 — Trading Strategies (HFT + Swing) & Concurrency Pipeline

Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Files you own exclusively:
- `estrategias/hft_engine.py`
- `estrategias/swing_engine.py`
- `estrategias/__init__.py`
- `pruebas_unitarias/test_estrategias_hft_swing.py`

Deliverables:
1. `estrategias/hft_engine.py`:
   - 4-Phase HFT logic per PLANnew.md:
     * Phase 1: Pre-match OBI entry (Maker Limit Buy at Best Bid + 1 tick when $I \ge 0.60$ and Spread $\le \$0.03$), exit Limit Sell at Best Ask + 2 ticks with 2-10s timeout.
     * Phase 2: Transition `limpiar_mesa` at T-5m (cancel pending, market sell fills).
     * Phase 3: In-play latency sniping on live event updates.
     * Phase 4: Time decay scalping in draw matches min 75-90.
   - User Business Directives:
     * Universal 7-sport coverage: Soccer, Baseball, American Football, Basketball, Tennis, Hockey, eSports.
     * Strategy A (Time Decay Exploitation): Min 65-70 in stagnant games, buy Draw/Result share, hold 3-5 min to gain time tick, sell before final whistle.
     * Strategy B (Overreaction Hunting): Price crash due to panic against dominant favorite (xG/possession dominance); buy dip, sell on speculative rebound on next dangerous attack without waiting for goal.
   - Integration with `MicroestructuraBinanceEngine`, `EscudoFinancieroBinance`.
2. `estrategias/swing_engine.py`:
   - Complementary orthogonal swing trading strategy running concurrently without blocking the async event loop.
   - Analyzes macro trend / multi-hour statistics. Offloads CPU-intensive operations via `asyncio.to_thread`.
   - Coordinates with `EscudoFinancieroBinance` via atomic capital reservation tokens.
3. `pruebas_unitarias/test_estrategias_hft_swing.py`:
   - Verification suite validating Strategy A, Strategy B, 4-phase HFT, and non-blocking concurrent execution with Swing trading.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m3
Write your report to `report.md` and deliver `handoff.md` in your working directory. Send a message to parent when complete.

## 2026-10-07T04:16:31Z
[Message] timestamp=2026-10-07T04:16:31Z sender=f2f51f43-3860-4c33-b19f-c0b7ef73f3b6 priority=MESSAGE_PRIORITY_HIGH content=You are teamwork_preview_worker (Worker M3)...
