# Dispatch: E2E Testing Track Orchestrator

Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read Reference Architecture at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Scope: E2E Testing Track
You are the E2E Testing Orchestrator. Your mission is to design, create, and verify a comprehensive opaque-box test suite for CONTINUITY HFT Binance derived strictly from user requirements and specifications.

Tasks:
1. Create `TEST_INFRA.md` at project root following the 4-tier methodology (Tier 1: Feature Coverage >=5 per feature; Tier 2: Boundary & Corner >=5 per feature; Tier 3: Cross-Feature combinations; Tier 4: Real-World Application scenarios).
2. Create and execute test suites in `pruebas_unitarias/` and `tests/`:
   - `test_hft.py`: Injected L2 order book imbalance >80% ($I \ge 0.60$) -> verify correctly formatted Limit order at Best Bid + 1 tick, exit at Best Ask + 2 ticks.
   - `test_concurrencia.py`: Concurrent non-blocking execution of HFT and Swing Trading loops with zero event loop starvation.
   - `test_tesoreria.py`: Dynamic position sizing, losing streak attenuation ($0.85^n$), 15% cluster cap, Top 3 BIDs liquidity ceiling, financial threshold triggers ($10 \to 100 \text{ USD}$ injection event, $1000 \text{ USD}$ harvest), and mathematical accuracy of metrics (Win Rate, Accumulated Capital, ROI, Yield, Total Trades).
   - `test_telegram_control.py`: Mock test with `MockTelegramClient` verifying command routing, `/kill` panic switch immediate pause, `/pause`, `/resume`, `/risk`, and `/report`.
   - `test_golden_rules.py`: Verify Golden Rule 1 (Spread $\le \$0.03$), Golden Rule 2 (Suspended lock), Golden Rule 3 (Top 3 BIDs liquidity ceiling).
3. Ensure `pytest.ini` exists and all tests can be discovered and executed via `pytest`.
4. Publish `TEST_READY.md` at project root once the full test suite is complete and passing mock/contract runs.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\sub_orch_e2e_testing
Report back to parent orchestrator when complete with handoff.md.
