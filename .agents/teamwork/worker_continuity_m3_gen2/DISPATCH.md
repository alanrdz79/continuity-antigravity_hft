# Task Assignment — Worker M3 (4 HFT Phases, Strategy V & Pre-Match/In-Play EV Exits)

## Identity
- Role: teamwork_preview_worker
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m3_gen2
- Parent: orchestrator_continuity_gen2
- Milestone: M3 — 4 HFT Phases, Strategy V & Pre-Match/In-Play EV Exits (Requirement R3)

## Mandatory Reading Before Starting Work
You MUST read the following files before writing any code:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r3\handoff.md`

## Write Ownership Boundaries
You have exclusive write access ONLY to the following files:
- `orquestadores_principales/HFT_BINANCE.py`
- `estrategias/hft_engine.py`
- `estrategias/arbitraje_amm.py`
- `pruebas_unitarias/test_r3_hft_amm_ev.py` (or auxiliary unit test suite for M3)
DO NOT write to or modify any other files (e.g., `continuitis/state_registry.py`, `continuitis/financiero.py`, `continuitis/riesgo_binance.py`, `continuitis/tesoreria.py`).

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Detailed Requirements to Implement
1. **Pre-Match & In-Play Target EV Early Exits (`_vigilar_y_cerrar_posiciones_abiertas`)**:
   - In `orquestadores_principales/HFT_BINANCE.py`, implement the missing method `async def _vigilar_y_cerrar_posiciones_abiertas(self, symbol: str, snapshot: OrderBookSnapshot) -> List[TradeResult]`:
     - Inspect active positions from `hft_engine`.
     - Evaluate if `snapshot.best_bid >= pos.target_exit_price` (EV fulfilled) OR if `time.time() - pos.entry_time >= pos.timeout_seconds`.
     - When condition is met, close position immediately with take-profit/timeout order on exchange, record trade in `state_registry`, update treasury, and log exit.
     - Operates seamlessly across regular Sports and ESports both pre-match ("antes") and in-play ("durante") without waiting for match end.
2. **Phase 2 T-5m `limpiar_mesa` with Verified 0% Exposure**:
   - In `orquestadores_principales/HFT_BINANCE.py`:
     - Wire `ejecutar_fase_2_limpiar_mesa` when `match_state.time_to_kickoff_minutes <= 5.0`.
     - At T-5m, call `await self.binance_client.cancel_all_orders(symbol)` to atomically cancel all open limit orders.
     - Liquidate any open positions to verify `exposicion_final_pct == 0.0` and `liquidez_usdt_pct == 100.0`.
3. **Phase 1, 3, and 4 HFT Orchestration**:
   - Phase 1: Pre-match OBI scalping ($I \ge 0.60$, spread $\le \$0.03$, Maker limit entry at Best Bid + 1 tick, 2-10s exit).
   - Phase 3: Oracle latency sniping on key match events before market suspension (`MarketStatus: SUSPENDED`). Connect `snipe_desfase_oraculo` into live cycle in `hft_engine.py`.
   - Phase 4: Time decay scalp buying YES on Draw min 75-90 with 60-90s holding time.
4. **Strategy V (AMM Curve Sniping & Binary Parity Arbitrage)**:
   - In `estrategias/arbitraje_amm.py`:
     - Define and attach explicit dataclass `DualBuyProposal` to `ArbitrageSignal` when `Ask(YES) + Ask(NO) < 1.00 - fees`.
     - The proposal must contain atomic BUY proposals for YES and NO contracts with equal quantities, prices, fees, and expected net edge.
     - AMM curve deviation arbitrage against $P_{\text{fair}}$ with 2-15s scalp horizon and 15% cluster cap.
   - In `orquestadores_principales/HFT_BINANCE.py`:
     - Wire `ArbitrageAMMEngine` and `step_amm_cycle(event_id)` into orchestrator loops.
5. **Restore Orchestrator Concurrency & Test Compatibility**:
   - Restore `capital_gateway`, `swing_engine`, `step_swing_cycle`, and `_tasks` in `ContinuityHFTBinanceOrchestrator` so that all 16 tests in `test_orquestador_binance.py` pass cleanly.
6. **Verification and Unit Tests**:
   - Author/run unit tests to verify:
     - `_vigilar_y_cerrar_posiciones_abiertas` closes at target EV across Sports & ESports pre-match and in-play
     - T-5m cancellation and 0% exposure
     - Strategy V `DualBuyProposal` generation
     - Multi-loop orchestrator execution
   - Run pytest across all affected test suites.
   - Write `handoff.md` in your working directory and notify parent via `send_message`.


## 2026-10-10T20:04:07Z
You are Worker M3 for the CONTINUITY HFT Binance project.
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m3_gen2
Read your assignment in DISPATCH.md in your working directory, and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md and c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r3\handoff.md.

Your mission: Implement M3 (4 HFT Phases, Strategy V & Pre-Match/In-Play EV Exits) in accordance with PROJECT.md and DISPATCH.md.
Write ownership:
- orquestadores_principales/HFT_BINANCE.py
- estrategias/hft_engine.py
- estrategias/arbitraje_amm.py
- pruebas_unitarias/test_r3_hft_amm_ev.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Run build and test verification using pytest. Write handoff.md in your working directory and notify the parent orchestrator via send_message when complete.
