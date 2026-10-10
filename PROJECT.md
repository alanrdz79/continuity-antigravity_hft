# Project: CONTINUITY HFT Binance (GCP Cloud Refactoring, Autonomous Treasury & HFT Engine)

## Architecture
CONTINUITY HFT Binance is an autonomous, ultra-low latency algorithmic trading system engineered for sports and eSports prediction markets on Binance Spot. The system refactors legacy local state to Google Cloud Platform (GCP) primitives: Cloud Memorystore (Redis) for live sub-microsecond state caching (<50ns) and Cloud Bigtable (SSD) for immutable historical trade persistence.

### Core Architectural Components
1. **High-Speed State Layer (Cloud Memorystore Redis & Cloud Bigtable)**:
   - `StateRegistry`: Replaces all local SQLite databases (`continuity_state.db`, `hft.db`, `cerebrillum.db`). Manages live system balance, loss streak counters, circuit breakers, and pending match queue (`cola_partidos_pendientes`) in Redis. Historical trade records are stored in Cloud Bigtable using reverse-timestamp lexicographical row keys (`{symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}`). Includes transparent thread-safe in-memory mock fallback for local test execution without external GCP credentials.
2. **Autonomous Treasury & Financial Engine (`continuitis/tesoreria.py`, `continuitis/riesgo_binance.py`, `continuitis/auditor_metricas.py`)**:
   - Kelly Criterion formula ($f^* = \text{fraccion} \times (p(b+1)-1)/b$).
   - Real Position Sizing ($S_{\text{nominal}}$) bounded by streak attenuation ($0.85^n$), 15% cluster capital cap, and Golden Rule 3 (Top-3 BIDs liquidity limit).
   - Strict 4-decimal precision (`0.0001`) across all financial calculations (Win Rate, EV, ROI, Yield, Stake, Capital).
   - Autonomous acceleration milestones ($10 \to 100 \to 1,000$ USD) and Autonomous Harvesting Protocol: upon reaching balance $\ge \$1,000$ USD, automatically isolates 35% net profit to MXN, allocating 40% of the remainder to expenses and 60% to compound reinvestment.
3. **Continuous 4-Phase HFT & Strategy V Engine (`estrategias/hft_engine.py`, `estrategias/arbitraje_amm.py`)**:
   - **Fase 1 (Pre-Match)**: Order Book Imbalance ($I \ge 0.60$, 80% volume dominance), spread $\le \$0.03$, Maker limit entry at Best Bid + 1 tick, target exit at Best Ask + 2 ticks with 2-10s exposure timeout.
   - **Fase 2 (Transition T-5m)**: `limpiar_mesa` atomic cancellation of open orders and conversion of fills, verifying exactly 0% exposure prior to event start.
   - **Fase 3 (In-Play)**: Oracle latency sniping on key match events prior to Binance market suspension (`MarketStatus: SUSPENDED`).
   - **Fase 4 (Time Decay Scalp)**: Buy YES on Draw between min 75-90 with low danger index, holding 60-90s and exiting without waiting for match end.
   - **Pre-Match & In-Play Target EV Early Exits (`_vigilar_y_cerrar_posiciones_abiertas`)**: Both pre-match ("antes") and in-play ("durante"), positions are monitored and closed immediately upon reaching target EV or timeout across all 7 Sports disciplines and ESports.
   - **Estrategia V (AMM Sniping & Binary Parity Arbitrage)**: Detects terminal binary parity arbitrage (`Ask(YES) + Ask(NO) < 1.00 - fees`), generating atomic `DualBuyProposal` for concurrent execution.
4. **Continuous Orchestrator (`orquestadores_principales/HFT_BINANCE.py`)**:
   - Unifies all phases, feeds, risk checks, telegram controls, and cloud state in an asynchronous event loop with clean shutdown guarantees.

---

## Code Layout & Write Boundaries

| Path / Module | Purpose | Owner Milestone |
|---|---|---|
| `continuitis/state_registry.py` | Cloud Memorystore (Redis) & Cloud Bigtable state manager, `cola_partidos_pendientes` | M1 |
| `continuitis/financiero.py` | Cluster controller refactored to read pending queue from `StateRegistry` | M1 |
| `continuitis/memoria_hft.py` | In-memory HFT store refactored to remove local sqlite3 dependencies | M1 |
| `Dockerfile` & `requirements.txt` | Container definition with non-root appuser and Redis environment variables | M1 |
| `continuitis/riesgo_binance.py` | Kelly Criterion, Real Position Sizing, 4-decimal precision, streak attenuation, cluster cap | M2 |
| `continuitis/tesoreria.py` | Growth acceleration ($10 \to 100 \to 1000$), autonomous harvesting (35% MXN isolation) | M2 |
| `continuitis/auditor_metricas.py` | 4-decimal analytical metrics (WR, B_N, ROI, Yield, N) and Z-score statistical gate | M2 |
| `pruebas_unitarias/test_r2_exactitud_financiera.py` | Acceptance tests for R2 financial formulas and $1,000 harvesting demonstration | M2 |
| `estrategias/hft_engine.py` | 4-Phase HFT logic, Strategy A/B, Multispot & ESports, Phase 3 oracle hook | M3 |
| `estrategias/arbitraje_amm.py` | Strategy V AMM curve deviation & binary parity with `DualBuyProposal` | M3 |
| `orquestadores_principales/HFT_BINANCE.py` | Main orchestrator with `_vigilar_y_cerrar_posiciones_abiertas` EV exits, T-5m cleanup | M3 |
| `TEST_INFRA.md`, `TEST_READY.md`, `pruebas_unitarias/` | Comprehensive test infrastructure, E2E acceptance suites Tiers 1-4 | E2E Testing Track |

---

## Feature Inventory

Every required feature is mapped to an implementation milestone:

| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | `StateRegistry` Redis Memorystore | Sub-microsecond live state caching (<50ns) via `REDIS_HOST`/`REDIS_PORT` with in-memory fallback | M1 | R1 / Acceptance Criterion 2 |
| 2 | `cola_partidos_pendientes` in Redis | Manage pending match queue (`encolar_partido`, `obtener_partidos_pendientes`, `cerrar_partido`) | M1 | R1 |
| 3 | Cloud Bigtable Historical Archival | Reverse-timestamp row keys (`{symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}`) | M1 | R1 |
| 4 | Elimination of `sqlite3` Dependencies | Complete removal of local database files (`continuity_state.db`, `hft.db`, `cerebrillum.db`) | M1 | R1 |
| 5 | Docker Crash Loop Resolution | Container boots stably without `sqlite3.OperationalError` under non-root UID 10001 | M1 | R1 / Acceptance Criterion 1 |
| 6 | Kelly Criterion (`calcular_criterio_kelly`) | Formula $f^* = \text{fraccion} \times ((p(b+1)-1)/b)$ with bounded fraction and 4-decimal output | M2 | R2 |
| 7 | Real Position Sizing ($S_{\text{nominal}}$) | Sizing modulated by streak factor $0.85^n$, 15% cluster cap, and Top-3 BIDs liquidity limit | M2 | R2 |
| 8 | 4-Decimal Precision (`0.0001`) | All financial metrics (Win Rate, EV, ROI, Yield, Stake, Capital) guaranteed to 4 decimals | M2 | R2 / Acceptance Criterion 4 |
| 9 | Acceleration Cycle ($10 \to 100 \to 1,000$) | Dynamic growth cycle with statistical validation gate ($N \ge 300, p < 0.05$) | M2 | R2 |
| 10 | Autonomous Harvesting Protocol | At balance $\ge \$1,000$ USD, automatically isolates 35% net profit to MXN, 40% expenses, 60% reinvestment | M2 | R2 / Acceptance Criterion 3 |
| 11 | Financial Test Verification Script | `test_r2_exactitud_financiera.py` demonstrating $1,000 balance 35% net profit isolation and 4-decimal unit tests | M2 | R2 / Acceptance Criteria 3, 4 |
| 12 | HFT Phase 1: Pre-Match OBI Scalping | Maker limit entry at Best Bid + 1 tick when $I \ge 0.60$ and spread $\le \$0.03$ with fast target exit | M3 | R3 |
| 13 | HFT Phase 2: T-5m `limpiar_mesa` | Programmatic verification of total order cancellation at T-5m with verified 0% exposure | M3 | R3 / Acceptance Criterion 5 |
| 14 | HFT Phase 3: In-Play Latency Sniping | Oracle latency sniping before book suspension (`MarketStatus: SUSPENDED`) | M3 | R3 |
| 15 | HFT Phase 4: Time Decay Scalp | Draw contract scalp between min 75-90 with 60-90s exit without waiting for match conclusion | M3 | R3 |
| 16 | Pre-Match & In-Play Target EV Early Exits | `_vigilar_y_cerrar_posiciones_abiertas`: close positions pre-match and in-play upon reaching target EV across Sports & ESports | M3 | User Update 2026-10-10T18:00:42Z |
| 17 | Strategy V: Binary Parity Arbitrage | Detect `Ask(YES) + Ask(NO) < 1.00 - fees` and generate atomic `DualBuyProposal` | M3 | R3 / Acceptance Criterion 6 |
| 18 | Strategy V: AMM Curve Inefficiencies | Arbitrage curve deviations against $P_{\text{fair}}$ with 2-15s scalp horizon and 15% cap | M3 | R3 |
| 19 | Orchestrator Concurrency & Integration | Restore full orchestrator compliance in `HFT_BINANCE.py` (capital gateway, swing, amm engines) | M3 | R3 |
| 20 | E2E Test Suite & Adversarial Hardening | Pass 100% of E2E test suite (Tiers 1-4) and adversarial coverage hardening (Tier 5) | M4 | Final Milestone |

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | GCP State Migration & SQLite Elimination | `continuitis/state_registry.py`, `continuitis/financiero.py`, `continuitis/memoria_hft.py`, `Dockerfile`, `requirements.txt`: Cloud Memorystore (Redis), Cloud Bigtable, `cola_partidos_pendientes`, Docker crash-loop fix | none | IN_PROGRESS |
| M2 | Autonomous Treasury & Financial Engine | `continuitis/riesgo_binance.py`, `continuitis/tesoreria.py`, `continuitis/auditor_metricas.py`, `pruebas_unitarias/test_r2_exactitud_financiera.py`: Kelly criterion, 4-decimal precision, $1,000 balance 35% MXN harvesting isolation | none | IN_PROGRESS |
| M3 | 4 HFT Phases, Strategy V & EV-Driven Exits | `orquestadores_principales/HFT_BINANCE.py`, `estrategias/hft_engine.py`, `estrategias/arbitraje_amm.py`: Pre-match & In-play EV exits (`_vigilar_y_cerrar_posiciones_abiertas`), Phase 2 T-5m 0% exposure, Strategy V `DualBuyProposal`, Sports & ESports | M1, M2 | PLANNED |
| M4 | Final Milestone: 100% E2E Pass & Adversarial Hardening | Execute full test suite against all acceptance criteria (Tiers 1-4) and Tier 5 adversarial coverage hardening | M1, M2, M3, TEST_READY.md | PLANNED |
| E2E | E2E Testing Track | `TEST_INFRA.md`, `TEST_READY.md`, test suites covering Features 1-19 | none | IN_PROGRESS |

---

## Interface Contracts

### 1. State Registry (`continuitis/state_registry.py`)
```python
class StateRegistryProtocol(Protocol):
    def get_state(self, key: str, default: str = "") -> str: ...
    def set_state(self, key: str, value: str) -> None: ...
    def encolar_partido(self, partido_id: str, payload: dict) -> None: ...
    def obtener_partidos_pendientes(self) -> List[dict]: ...
    def cerrar_partido(self, partido_id: str, trade_result: Optional[dict] = None) -> None: ...
    def record_trade(self, trade_id: str, symbol: str, pnl: float, is_win: bool, timestamp: float, stake: float = 0.0) -> None: ...
    def get_recent_trades(self, limit: int = 100) -> List[Dict[str, Any]]: ...
```

### 2. Risk Engine & Treasury (`continuitis/riesgo_binance.py`, `continuitis/tesoreria.py`)
```python
class RiskEngineProtocol(Protocol):
    def calcular_criterio_kelly(self, p_estimada: float, cuota_neta: float, fraccion_kelly: float = 0.25) -> float: ...
    def calcular_posicion(self, balance: float, cuota_bruta: float, p_estimada: float, ...) -> Dict[str, Any]: ...

class TreasuryProtocol(Protocol):
    def ejecutar_cosecha_autonoma(self, ganancia_neta: Optional[float] = None, tipo_cambio_mxn: Optional[float] = None) -> Dict[str, Any]: ...
    def verificar_hitos(self, auto_cosechar: bool = True) -> Dict[str, Any]: ...
    def registrar_trade(self, trade: TradeResult) -> None: ...
```

### 3. Strategy V & AMM Engine (`estrategias/arbitraje_amm.py`)
```python
@dataclass(frozen=True)
class DualBuyProposal:
    proposal_id: str
    event_id: str
    symbol_yes: str
    symbol_no: str
    price_yes: float
    price_no: float
    quantity: float
    sum_asks: float
    fees_total: float
    net_edge: float
    order_yes: OrderProposal
    order_no: OrderProposal
    timestamp: float = field(default_factory=time.time)

class ArbitrageEngineProtocol(Protocol):
    def detectar_paridad_binaria(self, snap_yes: OrderBookSnapshot, snap_no: OrderBookSnapshot, ...) -> Optional[ArbitrageSignal]: ...
    def detectar_desviacion_curva(self, snapshot: OrderBookSnapshot, p_fair: float, ...) -> Optional[ArbitrageSignal]: ...
```

### 4. Orchestrator Target EV Exits (`orquestadores_principales/HFT_BINANCE.py`)
```python
class OrchestratorProtocol(Protocol):
    async def _vigilar_y_cerrar_posiciones_abiertas(self, symbol: str, snapshot: OrderBookSnapshot) -> List[TradeResult]: ...
    async def step_hft_cycle(self, symbol: str) -> Optional[Any]: ...
    async def step_amm_cycle(self, event_id: str) -> Optional[Any]: ...
```
