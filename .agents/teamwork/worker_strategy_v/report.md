# Report: Worker Strategy V — Dynamic Cross-Venue Arbitrage & AMM Bonding-Curve Sniping

**Date:** 2026-10-07  
**Author:** Worker Strategy V (`teamwork_preview_worker`)  
**Scope:** Milestone 6 (`estrategias/arbitraje_amm.py`, `pruebas_unitarias/test_arbitraje_amm.py`)

---

## 1. Executive Summary

This deliverable implements **Estrategia V: Dynamic Cross-Venue Arbitrage & AMM Bonding-Curve Sniping** (`EstrategiaVArbitrajeAMM`) for the CONTINUITY HFT Binance prediction ecosystem, strictly fulfilling Directive 2026-10-07T08:38:51Z and DISPATCH requirements.

The module provides deterministic binary parity arbitrage, curve deviation micro-scalping against an external benchmark probability ($P_{\text{fair}}$), and tight risk & latency integration (15% cluster exposure cap, 2.5s hard execution timeout abort, and immediate market freeze on `MarketStatus == 'SUSPENDED'`).

---

## 2. Implemented Architecture & Business Rules

### Rule 1: Dynamic Curve Deviation Arbitrage vs External $P_{\text{fair}}$
- Evaluates implied contract pricing against an external reference probability $P_{\text{fair}} \in (0, 1)$ (for YES) and $1.0 - P_{\text{fair}}$ (for NO).
- Detects under-collateralized / undervalued contracts when deviation $|\text{implied} - P_{\text{fair}}| \ge \text{threshold}$ (default 0.03, 3%).
- Net edge calculation accounts for Binance Spot trading fee discounts (0.075% with BNB).
- Triggers purchase of the undervalued contract and programs a scalp exit within a strict horizon between 2.0 and 15.0 seconds.
- Positions are monitored by `gestionar_posiciones_scalp`:
  * **Take-Profit on Bounce:** Liquidates when Best Bid reaches or exceeds the bounce target price ($P_{\text{fair}}$ target).
  * **Timeout Exit:** Force-liquidates at current market bid if time elapsed reaches the programmed scalp horizon ($t \in [2.0, 15.0]\text{ s}$).

### Rule 2: Deterministic Binary Parity Dual-Purchase Arbitrage
- Evaluates the deterministic binary contract parity condition:
  $$\text{Best Ask}(\text{YES}) + \text{Best Ask}(\text{NO}) < 1.00 - \text{comisiones\_totales}$$
- When verified, triggers simultaneous dual-buy across both contracts to lock guaranteed risk-free redemption profit ($1.00 - \sum \text{Asks} - \text{fees} > 0$).
- Volume is capped to the minimum depth available in the top level of both books ($\min(V_{\text{Ask, YES}}, V_{\text{Ask, NO}})$) and reconciled against cluster capital.

### Rule 3: Risk & Latency Integration
- **15% Cluster Exposure Cap:**
  * Coordinates atomically with `AsyncCapitalGateway` using `CapitalReservationToken`s (or internal cluster exposure guard).
  * Enforces that total capital committed in the arbitrage cluster never exceeds 15% of bankroll.
  * Reconciles requested stake against book volume prior to reservation, ensuring zero trapped capital and clean release on exit.
- **2.5s Hard Execution Latency Abort:**
  * Strict latency guard enforces a maximum execution / in-flight timeout of 2.5 seconds.
  * If execution latency exceeds 2.5s, the system immediately aborts the trade (`LATENCY_ABORT`), cancels pending orders, and releases reserved capital tokens.
- **Immediate Market Freeze on SUSPENDED (Golden Rule 2):**
  * Immediate rejection of all signals if either book or global state reports `MarketStatus == 'SUSPENDED'`.
  * If a market suspension occurs during an active scalp position, the system immediately locks the position (`LOCKED_SUSPENDED`) and releases reserved capital tokens.

---

## 3. Test Suite Verification (4-Tier Architecture)

The test suite in `pruebas_unitarias/test_arbitraje_amm.py` covers 21 comprehensive test cases:

1. **Tier 1: Feature Contract Coverage (6 tests)**
   - `test_binary_parity_trigger_condition_under_098`: Parity trigger condition and edge calculation.
   - `test_binary_parity_execution_locks_redemption_profit`: Dual-purchase execution and redemption profit accounting.
   - `test_curve_deviation_yes_undervalued_entry`: Signal generation for undervalued YES contracts.
   - `test_curve_deviation_no_undervalued_entry`: Signal generation for undervalued NO contracts.
   - `test_curve_deviation_execution_and_scalp_bounce_exit`: Take-profit exit on price bounce.
   - `test_scalp_timeout_exit_within_2_to_15_seconds`: Scalp exit within 2-15s timeout window.

2. **Tier 2: Boundary and Corner Conditions (6 tests)**
   - `test_boundary_sum_asks_exact_1_0000_no_arbitrage`: Sum of asks = 1.0000 rejected.
   - `test_boundary_sum_asks_1_0001_negative_edge`: Sum of asks = 1.0001 rejected.
   - `test_boundary_sum_asks_0_9999_consumed_by_fees`: Sub-fee gaps consumed by commissions rejected.
   - `test_boundary_zero_volume_books_handled_safely`: Empty depth and zero volumes handled gracefully without errors.
   - `test_boundary_curve_deviation_threshold_edge`: Strict threshold edge (0.0299 vs 0.0305).
   - `test_boundary_extreme_prices`: Boundary prices near 0.01 and 0.99 verified.

3. **Tier 3: Risk and Latency Combinations (5 tests)**
   - `test_cluster_cap_15_percent_strict_enforcement`: Strict 15% cluster exposure limit.
   - `test_cluster_cap_released_properly_on_exit`: Atomic capital release upon position closure.
   - `test_latency_guard_2_5s_hard_timeout_abort`: Hard 2.5s execution abort with token release.
   - `test_latency_under_2_5s_executes_normally`: Fast executions under 2.5s pass.
   - `test_concurrent_tasks_no_race_condition_on_cluster_cap`: 10 concurrent tasks competing for capital cap without race conditions.

4. **Tier 4: Real-World Scenarios & Multi-Event Arbitrage (4 tests)**
   - `test_market_status_suspended_immediate_lock_on_detection`: Suspended market blocks signal generation.
   - `test_market_status_suspended_locks_active_execution`: Execution attempts during SUSPENDED status rejected.
   - `test_market_suspension_during_open_scalp_triggers_emergency_freeze`: Open positions frozen upon suspension.
   - `test_multi_event_arbitrage_run_across_5_sports`: Concurrent multi-market arbitrage cycle across Soccer, Basketball, Tennis, Hockey, and Baseball.

---

## 4. Verification Results

- Command: `.venv\Scripts\python.exe -m pytest pruebas_unitarias/test_arbitraje_amm.py -v`
- Result: **21 passed in 3.01s** (100% pass rate).
- Full suite verification: `230 passed` across all repository test suites, confirming zero regressions.
