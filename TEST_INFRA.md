# Test Infrastructure & Verification Architecture: CONTINUITY HFT Binance

## 1. Overview & Test Philosophy
This document specifies the requirement-driven, opaque-box test infrastructure for **CONTINUITY HFT Binance**, operating across Sports and ESports prediction markets on Binance Spot with Google Cloud Platform (GCP) primitives (Cloud Memorystore Redis and Cloud Bigtable).

### Test Methodology
- **Opaque-Box & Requirement-Driven**: Tests derive pass/fail conditions strictly from `ORIGINAL_REQUEST.md` and `PROJECT.md` contracts, with zero reliance on private implementation shortcuts.
- **4-Tier Verification**:
  - **Tier 1 (Feature Coverage)**: Individual features verified in isolation with $\ge 5$ test cases each.
  - **Tier 2 (Boundary & Corner Cases)**: Mathematical limits, rounding thresholds, 4-decimal precision limits, extreme drawdowns, zero depths, and boundary timestamps.
  - **Tier 3 (Cross-Feature Combinations)**: Cross-module interactions (e.g., Redis state sync with risk gateway, Phase 2 cancellation with exchange client, EV take-profit triggers with treasury).
  - **Tier 4 (Real-World Application Scenarios)**: End-to-end full life-cycle simulation across Sports and ESports, autonomous harvesting triggers at $1,000 USD balance, and crash-loop resilience.

---

## 2. Feature Inventory Mapping to Test Tiers

| # | Feature | Tier 1 | Tier 2 | Tier 3 | Tier 4 | Acceptance Criteria Verification Target |
|---|---------|:------:|:------:|:------:|:------:|---|
| 1 | `StateRegistry` Redis Memorystore (<50ns) | 5 | 5 | ✓ | ✓ | Orchestrator connects to Redis via `REDIS_HOST`/`REDIS_PORT` env vars |
| 2 | `cola_partidos_pendientes` in Redis | 5 | 5 | ✓ | ✓ | Enqueue, dequeue, close match without file locks |
| 3 | Cloud Bigtable Historical Archival | 5 | 5 | ✓ | ✓ | Reverse-timestamp row keys (`{symbol}#{MAX-ts}#{seq}`) |
| 4 | Elimination of Local `sqlite3` | 5 | 5 | ✓ | ✓ | Zero `.db` or `-wal` file generation |
| 5 | Docker Crash Loop Resolution | 5 | 5 | ✓ | ✓ | Container boots stably without `sqlite3.OperationalError` |
| 6 | Kelly Criterion (`calcular_criterio_kelly`) | 5 | 5 | ✓ | ✓ | Exact formula $f^*$ with bounded fractions and 4-decimal output |
| 7 | Real Position Sizing ($S_{\text{nominal}}$) | 5 | 5 | ✓ | ✓ | Modulated by $0.85^n$, 15% cluster cap, Top-3 BIDs liquidity |
| 8 | 4-Decimal Precision (`0.0001`) | 5 | 5 | ✓ | ✓ | Precision verified on WR, EV, ROI, Yield, Stake, Capital |
| 9 | Acceleration Milestones ($10 \to 100 \to 1000$) | 5 | 5 | ✓ | ✓ | Growth gates and statistical check ($N \ge 300, p < 0.05$) |
| 10 | Autonomous Harvesting Protocol | 5 | 5 | ✓ | ✓ | At $\ge \$1,000$, isolates 35% net profit to MXN, 40% exp, 60% reinv |
| 11 | R2 Exactitud Financiera Suite | 5 | 5 | ✓ | ✓ | Dedicated script `test_r2_exactitud_financiera.py` |
| 12 | HFT Phase 1: Pre-Match OBI Scalping | 5 | 5 | ✓ | ✓ | $I \ge 0.60$, spread $\le \$0.03$, Best Bid + 1 tick, 2-10s exit |
| 13 | HFT Phase 2: T-5m `limpiar_mesa` | 5 | 5 | ✓ | ✓ | Programmatically verifies order cancellation and 0% exposure |
| 14 | HFT Phase 3: In-Play Latency Sniping | 5 | 5 | ✓ | ✓ | Fast oracle event entry prior to `MarketStatus: SUSPENDED` |
| 15 | HFT Phase 4: Time Decay Scalp | 5 | 5 | ✓ | ✓ | Draw contract scalp min 75-90 with 60-90s exit |
| 16 | Pre-Match & In-Play EV Exits | 5 | 5 | ✓ | ✓ | `_vigilar_y_cerrar_posiciones_abiertas` closes at target EV (Sports/ESports) |
| 17 | Strategy V: Binary Parity Arbitrage | 5 | 5 | ✓ | ✓ | $Ask(YES)+Ask(NO) < 1.00-fees$ triggers `DualBuyProposal` |
| 18 | Strategy V: AMM Curve Inefficiencies | 5 | 5 | ✓ | ✓ | Curve deviation against $P_{\text{fair}}$ with 2-15s scalp |
| 19 | Orchestrator Concurrency & Integration | 5 | 5 | ✓ | ✓ | Multi-loop async integration in `HFT_BINANCE.py` |

---

## 3. Dedicated Acceptance Criteria Test Suites

### Criterion 1: Docker Container Run & SQLite Elimination
- **Test Target**: Dockerfile boot, environment variables, absence of sqlite3 writes.
- **Verification**: Container starts with non-root UID 10001, reads `REDIS_HOST`, does not raise `sqlite3.OperationalError`.

### Criterion 2: Orchestrator Redis Connection
- **Test Target**: `StateRegistry(redis_host=os.getenv("REDIS_HOST"))`.
- **Verification**: Successfully instantiates Redis client with host from environment variable; uses transparent in-memory mock when host is offline.

### Criterion 3: Autonomous Harvesting at $1,000 USD Balance
- **Test Target**: `continuitis/tesoreria.py` and `pruebas_unitarias/test_r2_exactitud_financiera.py`.
- **Verification**: Balance crossing $\$1,000$ USD automatically calculates net profit ($B - B_0$), isolates exactly 35% to MXN (`capital_aislado_cosecha_usd`/`mxn`), routes 40% of remainder to operating expenses, and retains 60% in compound reinvestment.

### Criterion 4: Unit Tests for Financial Formulas (4-Decimal Precision)
- **Test Target**: Win Rate, EV, ROI, Position Size (Stake), Yield, and Kelly Criterion in `pruebas_unitarias/test_r2_exactitud_financiera.py`.
- **Verification**: Math assertions assert with tolerance `abs=1e-4` (0.0001 precision).

### Criterion 5: Phase 2 Cancellation at T-5m with 0% Exposure
- **Test Target**: `HFTEngine.ejecutar_fase_2_limpiar_mesa` and `HFT_BINANCE.py:step_hft_cycle`.
- **Verification**: At 5 minutes before kickoff, all open orders are cancelled, open positions liquidated at market, and `exposicion_final_pct == 0.0`.

### Criterion 6: Strategy V Dual Buy Atomic Proposal
- **Test Target**: `estrategias/arbitraje_amm.py:detectar_paridad_binaria`.
- **Verification**: When `Best Ask(YES) + Best Ask(NO) < 1.00 - fees`, returns `ArbitrageSignal` containing `DualBuyProposal` with BUY proposals for both contracts.

### Criterion 7: Pre-Match and In-Play EV Early Exits (Sports & ESports)
- **Test Target**: `_vigilar_y_cerrar_posiciones_abiertas` in `HFT_BINANCE.py`.
- **Verification**: Positions close immediately when best bid reaches `target_exit_price` (EV fulfilled) both pre-match and in-play across regular Sports and ESports.
