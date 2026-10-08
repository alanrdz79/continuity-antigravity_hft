# Test Infrastructure & Verification Architecture: CONTINUITY HFT Binance

## 1. Overview & Testing Philosophy
This document formalizes the 4-tier testing infrastructure for **CONTINUITY HFT Binance**, an autonomous algorithmic trading engine operating on Binance prediction markets across 7 sports disciplines.

The test infrastructure enforces strict opaque-box verification:
- Expected outputs are derived mathematically from authoritative specifications in `PROJECT.md`, `PLANnew.md`, and business directives in `ORIGINAL_REQUEST.md`.
- No facade or tautological tests: all tests assert against concrete numerical thresholds, invariant state transitions, and asynchronous concurrency non-starvation guarantees.
- Tests are co-located in `pruebas_unitarias/`, executed seamlessly via `pytest` configured by `pytest.ini` with `pythonpath = .`.

---

## 2. 4-Tier Test Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                        TIER 4: REAL-WORLD SCENARIOS                    │
│      Simulated full match life-cycles (soccer/tennis), drawdown runs,  │
│      multi-phase transitions, emergency suspensions & recovery         │
├────────────────────────────────────────────────────────────────────────┤
│                     TIER 3: CROSS-FEATURE PAIRWISE                     │
│      Imbalance + Latency Guard, Streak Attenuation + Cluster Cap,      │
│      Telegram Kill Switch + Async Concurrency, Harvest + Reinvestment   │
├────────────────────────────────────────────────────────────────────────┤
│                   TIER 2: BOUNDARY & CORNER CASES                      │
│      Spread = $0.0300 vs $0.0301, Imbalance = 0.6000 vs 0.5999,        │
│      Zero depth book, N=0 trades, Extreme loss streaks (n=10)           │
├────────────────────────────────────────────────────────────────────────┤
│                     TIER 1: FEATURE CONTRACT COVERAGE                  │
│      >=5 tests per core feature: OBI, Spread, Suspended, Top-3 BIDs,   │
│      EV, Sizing, Streak Factor, Harvest, Metrics, Telegram Dispatch    │
└────────────────────────────────────────────────────────────────────────┘
```

### Tier 1: Feature Contract Coverage
Verifies that each modular component behaves correctly according to its specification under standard nominal conditions. Each feature possesses $\ge 5$ distinct unit tests covering inputs, logic, and outputs.

### Tier 2: Boundary, Edge & Corner Cases
Subjects each component to extreme mathematical boundaries:
- Order Book Imbalance precisely at $I = 0.6000$ (80% buy dominance) vs $I = 0.5999$.
- Spread precisely at $\$0.0300$ vs $\$0.0301$ (Golden Rule 1 cutoff).
- Top 3 BIDs liquidity saturation: order size exactly equal to, 1 unit below, or 1 unit above available volume.
- Zero liquidity depth / empty books / inverted spreads.
- Zero-trade initial states ($N=0$) avoiding division by zero in metrics ($WR, ROI, \text{Yield}, Z$).
- Consecutive loss streaks ($n=0, 1, 2, 5, 10$) verifying asymptotic attenuation $0.85^n$.

### Tier 3: Cross-Feature Pairwise Combinations
Verifies interaction between orthogonal modules:
- Microstructure + Risk: High OBI ($I \ge 0.60$) with Golden Rule 1 passing, but rejected by Risk Engine due to negative EV ($EV < 0.015$) or cluster cap saturation ($>15\%$).
- Concurrency + Microstructure: High-throughput async L2 ticks processed concurrently with heavy swing calculations without starving the event loop.
- Telegram Control + Active Loops: Immediate `/kill` command execution stopping active order routing within sub-millisecond latency.
- Treasury + Auditor: Crossing $\$100$ and $\$1,000$ triggers capital injection and autonomous harvest while metrics reflect cumulative compounding.

### Tier 4: Real-World Application Scenarios
Simulates realistic end-to-end operational conditions:
- Full soccer match transition: Pre-match Phase 1 scalping $\to$ T-5m table cleaning $\to$ In-play latency monitoring $\to$ Min 75-90 time decay scalping.
- Sudden goal/VAR event: Binance transitions to `SUSPENDED`, triggering immediate lock on new orders, followed by post-suspension market resumption.
- Multi-game portfolio under drawdown: Multiple simultaneous trades across Soccer, Tennis, Basketball, and eSports respecting the 15% cluster ceiling.

---

## 3. Test Suites & File Ownership

All test files are owned exclusively by `test_writer_e2e`:

| Test File | Test Targets / Scope | Assigned Features |
|---|---|---|
| `pruebas_unitarias/test_hft.py` | Order Book Imbalance ($I \ge 0.60$), Limit Buy at Best Bid + 1 tick, Limit Sell at Best Ask + 2 ticks, TIF timeout, Phase transitions | Features 4, 17, 18, 20, 21, 22, 23 |
| `pruebas_unitarias/test_golden_rules.py` | Golden Rule 1 (Spread $\le \$0.03$), Golden Rule 2 (Suspended lock), Golden Rule 3 (Top 3 BIDs liquidity ceiling) | Features 3, 5, 11 |
| `pruebas_unitarias/test_concurrencia.py` | Concurrent non-blocking execution of HFT micro-ticks and Swing engine, zero event loop starvation, thread safety | Features 1, 9, 24, 31 |
| `pruebas_unitarias/test_tesoreria.py` | Real position sizing, streak attenuation ($0.85^n$), 15% cluster cap, Top-3 BIDs liquidity clamping, $10 \to 100 \to 1,000$ USD milestones | Features 7, 8, 9, 10, 11, 12, 13, 14 |
| `pruebas_unitarias/test_metricas.py` | Win Rate ($WR$), Accumulated Capital ($B_N$), ROI, Yield on turnover, Total Trades ($N$), $Z$-score and $p$-value gate ($N \ge 300, p < 0.05$) | Features 15, 16 |
| `pruebas_unitarias/test_telegram_control.py` | `MockTelegramClient`, command router, `/kill` panic switch, `/pause`, `/resume`, `/risk <param> <val>`, `/report`, telemetry queries | Features 25, 26, 27, 28, 29, 30 |

---

## 4. Test Matrix & Feature Mapping

| Feature ID | Feature Name | Test Function | Tier | Expected Outcome |
|---|---|---|---|---|
| F4 | Order Book Imbalance | `test_obi_exact_80_percent_buy_dominance` | Tier 1 | $I = (800-200)/(800+200) = 0.60 \implies$ Trigger entry |
| F4 | Order Book Imbalance | `test_obi_below_threshold_no_entry` | Tier 1 | $I = 0.59 \implies$ No entry |
| F4 | Order Book Imbalance | `test_obi_boundary_and_zero_volume` | Tier 2 | Zero depth returns $I = 0.0$ without ZeroDivisionError |
| F17 | HFT Limit Entry/Exit | `test_hft_limit_order_pricing_tick_offsets` | Tier 1 | Limit Buy = Best Bid + 1 tick, Limit Sell = Best Ask + 2 ticks |
| F17 | HFT Time-In-Force | `test_hft_exposure_timeout_fast_exit` | Tier 1 | Exposure duration bounded between 2s and 10s |
| F18 | Phase 2 Cleaning | `test_hft_phase2_limpiar_mesa_pre_match` | Tier 1 | Pending orders cancelled, trapped fills converted via Market Sell |
| F5 | Golden Rule 1 | `test_golden_rule_1_spread_lte_003_allowed` | Tier 1 | Spread $\$0.01, \$0.02, \$0.03 \implies$ Allowed |
| F5 | Golden Rule 1 | `test_golden_rule_1_spread_gt_003_rejected` | Tier 1 | Spread $\$0.0301, \$0.04 \implies$ Rejected |
| F5 | Golden Rule 1 | `test_golden_rule_1_inverted_and_zero_spread` | Tier 2 | Crossed book (Ask < Bid) $\implies$ Rejected |
| F3 | Golden Rule 2 | `test_golden_rule_2_suspended_locks_orders` | Tier 1 | `market_status == 'SUSPENDED'` $\implies$ Immediate lock |
| F3 | Golden Rule 2 | `test_golden_rule_2_active_allows_orders` | Tier 1 | `market_status == 'ACTIVE'` $\implies$ Order allowed |
| F3 | Golden Rule 2 | `test_golden_rule_2_state_transitions` | Tier 2 | Rapid transitions Active $\leftrightarrow$ Suspended correctly update state |
| F11 | Golden Rule 3 | `test_golden_rule_3_top3_bids_clamping` | Tier 1 | Requested size clamped to $\sum_{k=1}^3 V_{\text{Bid}}^{(k)}$ |
| F11 | Golden Rule 3 | `test_golden_rule_3_fewer_than_3_levels` | Tier 2 | 1 or 2 levels summed properly; 0 levels clamps to 0 |
| F8 | Real Position Sizing | `test_sizing_nominal_formula_exact` | Tier 1 | $S = (B \times \text{pct\_riesgo}) / \text{pct\_stop\_loss}$ |
| F9 | Streak Attenuation | `test_streak_attenuation_decay_curve` | Tier 1 | Factors: $1.0, 0.85, 0.7225, 0.6141$ for $n=0,1,2,3$ |
| F9 | Streak Attenuation | `test_streak_attenuation_reset_on_win` | Tier 1 | Win resets streak to 0 and factor to 1.0 |
| F10 | Cluster Exposure Cap | `test_cluster_exposure_cap_15_percent` | Tier 1 | Total simultaneous cluster exposure capped at 15% |
| F7 | Expected Value ($EV$) | `test_ev_calculation_net_of_bnb_discount` | Tier 1 | $EV = (P \times \text{Cuota}_{\text{neta}}) - 1.0 \ge 0.015$ |
| F12 | $10 \to 100$ Injection | `test_treasury_injection_event_at_100_usd` | Tier 1 | Crossing $\$100 \implies +100\text{ USD}$ injection event fired once |
| F13 | Acceleration Phase | `test_treasury_monthly_split_40_60` | Tier 1 | Profit split 40% operating, 60% compound reinvestment |
| F14 | $1,000$ USD Harvest | `test_treasury_autonomous_harvest_at_1000_usd`| Tier 1 | Balance $\ge \$1000 \implies 35\%$ harvested to MXN, remainder 40/60 |
| F15 | Analytical Metrics | `test_metrics_wr_roi_yield_total_trades` | Tier 1 | Mathematical accuracy of $WR$, ROI, Yield, Total Trades |
| F15 | Accumulated Capital | `test_metrics_accumulated_capital_compounding` | Tier 1 | $B_N = B_0 \prod(1 + f_i R_i)$ exact compounding |
| F16 | Statistical Gate | `test_statistical_gate_z_score_and_p_value` | Tier 1 | $N \ge 300, Z > 1.645, p < 0.05$ authorization gate |
| F24 | Async Concurrency | `test_concurrent_hft_and_swing_execution` | Tier 1 | Both loops execute concurrently without event loop starvation |
| F6 | Latency Circuit Breaker | `test_concurrency_heartbeat_latency_guard` | Tier 2 | Event loop heartbeat latency stays $< 100\text{ ms} \ll 800\text{ ms}$ |
| F26 | Telegram Kill Switch | `test_telegram_kill_switch_immediate_pause` | Tier 1 | `/kill` sets paused=True, cancels pending orders immediately |
| F27 | Telegram Pause/Resume| `test_telegram_pause_and_resume_routing` | Tier 1 | `/pause` and `/resume` update operational state |
| F28 | Telegram Hot Risk | `test_telegram_risk_parameter_hot_update` | Tier 1 | `/risk` modifies risk parameter in memory without restart |
| F29 | Telegram Telemetry | `test_telegram_report_and_metricas_telemetry` | Tier 1 | `/report` returns formatted telemetry string |
| F30 | MockTelegramClient | `test_mock_telegram_client_end_to_end` | Tier 3 | Simulates full operator session interacting with running bot |

---

## 5. Test Runner & Execution Protocol

### Pytest Configuration (`pytest.ini`)
```ini
[pytest]
pythonpath = .
testpaths = pruebas_unitarias
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -v --tb=short
```

### Execution Commands
- Run all test suites:
  ```powershell
  .venv\Scripts\python.exe -m pytest
  ```
- Run a specific test suite:
  ```powershell
  .venv\Scripts\python.exe -m pytest pruebas_unitarias/test_hft.py
  .venv\Scripts\python.exe -m pytest pruebas_unitarias/test_golden_rules.py
  .venv\Scripts\python.exe -m pytest pruebas_unitarias/test_concurrencia.py
  .venv\Scripts\python.exe -m pytest pruebas_unitarias/test_tesoreria.py
  .venv\Scripts\python.exe -m pytest pruebas_unitarias/test_metricas.py
  .venv\Scripts\python.exe -m pytest pruebas_unitarias/test_telegram_control.py
  ```
- Run with detailed assertions and stdout:
  ```powershell
  .venv\Scripts\python.exe -m pytest -s -v
  ```
