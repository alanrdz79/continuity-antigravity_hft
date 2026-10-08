# Project: CONTINUITY HFT Binance

## Architecture
CONTINUITY HFT Binance is an autonomous, high-frequency modular algorithmic trading engine for sports prediction markets on Binance Spot. It operates across 7 sporting disciplines (Soccer, Baseball, American Football, Basketball, Tennis, Hockey, eSports) with primary focus on live and trending matches.

### Concurrency Model
- Asynchronous event loop (`asyncio`) coordinating high-throughput L2 order book updates and strategy executions.
- `OrderBookListener`: Ingests L2 depth at sub-millisecond rates via WebSocket and maintains in-RAM snapshot.
- `HFTStrategyTask`: Micro-scalping execution evaluating order book imbalance, spread, latency, and fast exits with latency <5ms (feed latency <800ms).
- `SwingStrategyTask`: Multi-hour/daily orthogonal trend execution offloaded via `asyncio.to_thread` to prevent event loop blocking.
- `RiskGateway`: Thread-safe, atomic capital reservation with `asyncio.Lock` preventing double-allocation and enforcing the 15% cluster cap and Top-3 BID liquidity constraint.
- `TelegramController`: Interactive bidirectional command interface operating concurrently via async callbacks.

### Technology Stack
- Runtime: Python 3.14.2 (Windows 64-bit) in `.venv`
- Networking: `websockets`, `aiohttp`, `curl_cffi`
- Numerical: `numpy`, `scipy`
- Storage: In-RAM $\mathcal{O}(1)$ dictionaries with asynchronous SQLite WAL persistence
- Testing: `pytest`, `pytest-asyncio`

---

## Code Layout & Write Boundaries
To ensure strict isolation between concurrent subagents, file ownership is allocated as follows:

| Path / Module | Purpose | Owner Milestone |
|---|---|---|
| `conectores/binance_async.py` | Binance WebSocket L2 depth & REST execution client | M1 |
| `continuitis/microestructura_binance.py` | L2 Book Imbalance, Latency Guard, Golden Rules 1, 2, 3 | M1 |
| `continuitis/riesgo_binance.py` | EV calculation, Stop-loss sizing, $0.85^n$ streak attenuation, 15% cluster cap, Top-3 BIDs liquidity limit | M2 |
| `continuitis/tesoreria.py` | "Ordeño e Inyección" ($10 \to 100 \to 1,000$ USD), +$100 event, monthly 40/60 split, 35% MXN harvest | M2 |
| `continuitis/auditor_metricas.py` | Continuous metrics ($WR, B_N, ROI, \text{Yield}, N$) and $p$-value validation | M2 |
| `estrategias/hft_engine.py` | 4-Phase HFT logic, Strategy A (Time Decay), Strategy B (Overreaction Hunting) across 7 sports | M3 |
| `estrategias/swing_engine.py` | Complementary orthogonal swing trading engine | M3 |
| `conectores/telegram_bidireccional.py` | Interactive Telegram bot with `/kill`, `/pause`, `/resume`, `/risk`, `/report`, and `MockTelegramClient` | M4 |
| `orquestadores_principales/HFT_BINANCE.py` | Main continuous async orchestrator integrating all modules | M4 |
| `pruebas_unitarias/` & `tests/` | Comprehensive test suites (`test_hft.py`, `test_tesoreria.py`, `test_telegram_control.py`, `test_concurrencia.py`, `test_golden_rules.py`) | E2E Testing Track |

---

## Feature Inventory
Every feature identified during the Survey phase is mapped to an implementation milestone.

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | `conectar_orderbook_ws` | WebSocket client for Binance L2 depth channel with auto-reconnect | M1 | Survey / PLANnew §3 |
| 2 | `actualizar_libro` | In-RAM $\mathcal{O}(1)$ depth maintainer for top 5-10 bids/asks | M1 | Survey / PLANnew §3 |
| 3 | `detectar_estado_mercado` | Golden Rule 2: Lock new orders immediately when MarketStatus is SUSPENDED | M1 | Survey / GR2 |
| 4 | `OrderBookImbalance` calculation | $I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$, $80\%$ buy dominance $\iff I \ge 0.60$ | M1 | Survey / PLANnew §3 |
| 5 | Golden Rule 1: Max Spread Filter | Reject any order if Spread (Best Ask - Best Bid) $> \$0.03$ | M1 | Survey / GR1 |
| 6 | Latency Monitor & Circuit Breaker | Monitor feed heartbeat; trigger emergency state if latency $> 800\text{ ms}$ | M1 | Survey / PLANnew §3 |
| 7 | Expected Value ($EV > 0$) Calculation | $EV = (P_{\text{estimada}} \times \text{Cuota}_{\text{neta}}) - 1.0 \ge 0.015$ net of BNB fee discounts | M2 | Survey / PLANnew §3 |
| 8 | Real Position Sizing | $S_{\text{nominal}} = \frac{B \times \text{pct\_riesgo\_fijo} \times \text{factor\_racha}}{\max(\text{pct\_stop\_loss}, 0.01)}$ | M2 | Survey / PLANnew §3 |
| 9 | Losing Streak Attenuation Factor | $\text{factor\_racha} = 0.85^{\text{perdidas\_consecutivas}}$, reset to 1.0 on win | M2 | Survey / PLANnew §3 |
| 10 | Cluster Exposure Cap (15%) | Cap total simultaneously active cluster exposure to $\le 15\%$ of bankroll | M2 | Survey / PLANnew §3 |
| 11 | Golden Rule 3: Top-3 BID Liquidity Ceiling | Bound position size to $\le \sum_{k=1}^3 V_{\text{Bid}}^{(k)}$ to guarantee emergency market sell liquidity | M2 | Survey / GR3 |
| 12 | Treasury: $10 \to \$100$ Injection Gate | Authorize $+100\text{ USD}$ injection when balance crosses $\$100$, gated by paper trading validation | M2 | Survey / PLANnew §3, §5 |
| 13 | Treasury: Acceleration 40/60 Split | Monthly settlement: 40% operating expenses, 60% compound reinvestment | M2 | Survey / PLANnew §3 |
| 14 | Treasury: $\$1,000$ Autonomous Harvesting | At balance $\ge \$1,000$, harvest 35% monthly profit to MXN; remaining split 40/60 | M2 | Survey / PLANnew §3 |
| 15 | Continuous Analytical Metrics Auditor | Exact calculations for Win Rate ($WR$), Accumulated Capital ($B_N$), ROI, Yield on turnover, and Total Trades ($N$) | M2 | Survey / PLANnew §4 |
| 16 | Statistical Validation Gate | $Z$-score and $p$-value ($p < 0.05, Z > 1.645$) for trade validation before real capital injection | M2 | Survey / PLANnew §5 |
| 17 | HFT Phase 1 OBI Entry & Fast Exit | Maker Limit Buy at Best Bid + 1 tick when $I \ge 0.60$; exit Limit Sell at Best Ask + 2 ticks with 2-10s timeout | M3 | Survey / PLANnew §3 |
| 18 | HFT Phase 2 Pre-Match Transition | Atomic order cancellation (`limpiar_mesa`) at T-5m; convert trapped fills via Market Sell | M3 | Survey / PLANnew §3 |
| 19 | HFT Phase 3 In-Play Latency Sniping | Sniping real-world events before book suspension; immediate exit upon book resumption | M3 | Survey / PLANnew §3 |
| 20 | HFT Phase 4 Time Decay Scalping | Enter draw matches with zero dangerous attacks between min 75-90; hold 60-90s and market exit | M3 | Survey / PLANnew §3 |
| 21 | Strategy A: Time Decay Exploitation | Low-risk scalp min 65-70 in stagnant games; buy current Draw/Result share, hold 3-5 min, exit before end | M3 | Survey / Directive 2 |
| 22 | Strategy B: Overreaction Hunting | High-risk scalp on panic crash against dominant favorite (xG/possession dominance); buy dip, sell on speculative rebound | M3 | Survey / Directive 3 |
| 23 | Multi-Sport Market Coverage | Universal scanning across 7 sports (Soccer, Baseball, Football, Basketball, Tennis, Hockey, eSports) | M3 | Survey / Directive 1 |
| 24 | Parallel Orthogonal Swing Trading Engine | Concurrent multi-hour/daily swing execution running alongside HFT without event loop contention | M3 | Survey / R1 |
| 25 | Interactive Telegram Bot Client | Bidirectional Telegram bot with inline keyboard, command router, and push notifications | M4 | Survey / R3 |
| 26 | Telegram Kill Switch Remote Command | Instant `/kill` command triggering emergency stop, order cancellation, and loop pause | M4 | Survey / R3 |
| 27 | Telegram Pause / Resume Controls | Remote `/pause` and `/resume` controls for trading execution | M4 | Survey / R3 |
| 28 | Telegram Hot Risk Parameter Adjustment | Remote `/risk <param> <val>` updating parameters in hot memory | M4 | Survey / R3 |
| 29 | Telegram Telemetry Metrics Report | Remote `/report` and `/metricas` formatting real-time metrics | M4 | Survey / R3 |
| 30 | MockTelegramClient Test Interface | Mock client simulating user interactions for automated test verification | M4 | Survey / Acceptance Criteria |
| 31 | Continuous Main Orchestrator | Complete integration in `HFT_BINANCE.py` coordinating all tasks, feeds, risk, and control loops | M4 | Survey / R1-R3 |
| 32 | End-to-End Test Suite & Verification | Pass 100% of E2E test suite (Tiers 1-4) published in `TEST_READY.md` and adversarial hardening | M5 | Survey / Acceptance Criteria |
| 33 | Estrategia V: Dynamic Cross-Venue Arbitrage & AMM Sniping | Arbitrage curve deviations, binary parity (YES+NO < 1.00 - fee), 2-15s scalp horizon, 15% cap, LatencyGuard abort | M6 | Directive 2026-10-07T08:38:51Z |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Ingestion, Connectors & Microstructure Core | `conectores/binance_async.py`, `continuitis/microestructura_binance.py`: WebSocket L2 depth, Binance REST client, OBI calculation ($I \ge 0.60$), Golden Rule 1 (Spread $\le \$0.03$), Golden Rule 2 (Suspended lock), Golden Rule 3 (Top 3 BIDs liquidity calculation), Latency monitor (<800ms) | none | DONE |
| M2 | Risk Engine, Automated Treasury & Metrics Auditor | `continuitis/riesgo_binance.py`, `continuitis/tesoreria.py`, `continuitis/auditor_metricas.py`: EV calculation ($EV \ge 0.015$), Stop-loss sizing, $0.85^n$ streak attenuation, 15% cluster cap, Top-3 BIDs liquidity clamping, "Ordeño e Inyección" ($10 \to 100 \to 1,000$ USD), +$100 event trigger, 40/60 split, 35% MXN harvest, metrics ($WR, B_N, ROI, \text{Yield}, N$) and $p$-value validation | none | DONE |
| M3 | Trading Strategies (HFT + Swing) & Concurrency Pipeline | `estrategias/hft_engine.py`, `estrategias/swing_engine.py`: 4-Phase HFT logic, Strategy A (Time Decay), Strategy B (Overreaction Hunting) across 7 sports, Orthogonal Swing Engine, Non-blocking concurrent execution pipeline | M1, M2 | DONE |
| M4 | Interactive Telegram Bot & Main Continuous Orchestrator | `conectores/telegram_bidireccional.py`, `orquestadores_principales/HFT_BINANCE.py`: Bidirectional Telegram bot, `/kill`, `/pause`, `/resume`, `/risk`, `/report`, `MockTelegramClient`, main continuous orchestrator coordinating all pipelines, GCP Tokyo low-latency deployment manifests | M2, M3 | DONE |
| M6 | Estrategia V: Dynamic Arbitrage & AMM Sniping | `estrategias/arbitraje_amm.py`: Binary parity detection ($Ask(YES) + Ask(NO) < 1.00 - fees$), fair price curve deviation arbitrage, 2-15s scalp horizon, 15% cluster cap, LatencyGuard/Suspended abort | M1, M2 | DONE |
| M5 | E2E Integration, Full Verification & Adversarial Hardening | Phase 1: Pass 100% of E2E test suite from `TEST_READY.md` (all suites including M6). Phase 2: Adversarial coverage hardening (Tier 5) with Challenger. | M4, M6, TEST_READY.md | DONE |

---

## Interface Contracts

### 1. Ingestion (`conectores/binance_async.py`) $\leftrightarrow$ Microstructure (`continuitis/microestructura_binance.py`)
```python
@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    bids: Tuple[Tuple[float, float], ...]  # Tuple of (price, volume), sorted descending
    asks: Tuple[Tuple[float, float], ...]  # Tuple of (price, volume), sorted ascending
    timestamp_ms: int
    market_status: str  # "ACTIVE" or "SUSPENDED"

class BinanceConnectorProtocol(Protocol):
    async def get_orderbook_snapshot(self, symbol: str) -> OrderBookSnapshot: ...
    async def place_order(self, symbol: str, side: str, order_type: str, price: float, quantity: float) -> dict: ...
    async def cancel_order(self, symbol: str, order_id: str) -> dict: ...
    async def cancel_all_orders(self, symbol: str) -> list: ...
```

### 2. Microstructure $\leftrightarrow$ Risk Engine (`continuitis/riesgo_binance.py`)
```python
@dataclass(frozen=True)
class OrderProposal:
    symbol: str
    side: str
    target_price: float
    stop_price: float
    estimated_prob: float
    payout_decimal: float
    strategy_id: str

@dataclass(frozen=True)
class RiskApprovedOrder:
    symbol: str
    side: str
    price: float
    quantity: float
    ev_net: float
    approved: bool
    rejection_reason: Optional[str] = None
```

### 3. Risk Engine $\leftrightarrow$ Treasury & Metrics (`continuitis/tesoreria.py` & `continuitis/auditor_metricas.py`)
```python
@dataclass
class TradeResult:
    trade_id: str
    symbol: str
    stake: float
    pnl: float
    is_win: bool
    timestamp: float

class TreasuryProtocol(Protocol):
    def registrar_trade(self, trade: TradeResult) -> None: ...
    def verificar_hitos(self) -> dict: ...
    def corte_mensual(self, ganancia_mensual: float) -> dict: ...

class MetricsAuditorProtocol(Protocol):
    def registrar_trade(self, trade: TradeResult) -> None: ...
    def obtener_metricas(self) -> dict: ...  # {"win_rate": float, "capital_acumulado": float, "roi": float, "yield": float, "total_trades": int}
```

### 4. Orchestrator $\leftrightarrow$ Telegram Bot (`conectores/telegram_bidireccional.py`)
```python
class TelegramControlProtocol(Protocol):
    async def notify(self, message: str) -> None: ...
    def register_command_handlers(self, kill_switch_cb, pause_cb, resume_cb, risk_update_cb, query_metrics_cb) -> None: ...
```
