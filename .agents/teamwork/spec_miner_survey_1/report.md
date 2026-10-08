# CONTINUITY HFT — PLANnew Technical Specification Mining Report

**Date**: 2026-10-07  
**Agent**: `teamwork_preview_spec_miner` (PLANnew Spec Miner)  
**Primary Specification Sources**:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md` (Documento Técnico de Arquitectura Modular: CONTINUITY HFT)
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md` (Teamwork Project Prompts: 2026-10-07T03:48:12Z, 2026-10-07T03:43:52Z, and predecessor 2026-09-29T05:17:20Z)
3. Existing Codebase Reference: `continuitis/microestructura.py`, `continuitis/financiero.py`, `continuitis/memoria_hft.py`, `continuitis/constantes.py`, `conectores/telegram_bot.py`, `orquestadores_principales/HFT_GALO.py`

---

## 1. Executive Summary

This specification report documents all mathematical equations, quantitative parameters, state transitions, execution triggers, risk controls, treasury rules, and verification criteria for **CONTINUITY HFT (Binance Spot / Predict Markets)**, incorporating the latest user directives.

The system is an autonomous, high-frequency, modular algorithmic trading engine operating on sports prediction markets (binary contracts `YES`/`NO` on Binance Predict / AMMs) and spot order books across **all sports disciplines** (Soccer, Baseball, American Football, Basketball, Tennis, Hockey, eSports) with primary focus on **live and trending matches**. It extracts positive expected value ($EV > 0$) by exploiting microstructural order book imbalances, oracle latency differentials, time decay scalping, and panic overreactions without requiring positions to be held until final event settlement. Capital compounds through a 6-module architecture governed by strict risk caps, dynamic streak attenuation, liquidity-backed exit safety, and an automated treasury harvesting protocol.

---

## 2. Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | Ingestion & L2 | `conectar_orderbook_ws` | Establishes persistent WebSocket connection to Binance Level-2 depth channel | `market_id: str` | L2 depth feed stream | Disconnect/reconnect with exponential backoff | PLANnew.md §3 Módulo 1 |
| 2 | Ingestion & L2 | `actualizar_libro` | Maintains in-RAM $\mathcal{O}(1)$ top 5-10 bids and asks | `bids: List[Tuple]`, `asks: List[Tuple]` | Normalized depth book | Ignores malformed/zero levels | PLANnew.md §3 Módulo 1 |
| 3 | Ingestion & L2 | `escuchar_feed_deportivo` | Monitored real-time event feed for scores, cards, xG, dangerous attacks | External sports feed stream | Event telemetry, timestamps | Feed stall raises latency flag | PLANnew.md §3 Módulo 1 |
| 4 | Ingestion & L2 | `detectar_estado_mercado` (Golden Rule 2) | Detects Binance market status transitions; locks all new orders if `SUSPENDED` | WebSocket ticker/status message | `status`: `ACTIVE` \| `SUSPENDED` | If `SUSPENDED`, locks new orders immediately | PLANnew.md §3 Módulo 1; ORIGINAL_REQUEST.md GR2 |
| 5 | Execution | Order Book Imbalance (OBI) Phase 1 Trigger | Computes order book imbalance $I$; if buy imbalance $\ge 80\%$ ($I \ge 0.60$), places Limit Buy at Best Bid + 1 tick | Depth bids, depth asks, tick size | Limit Buy order payload | Blocked if $I < 0.60$, latency $> 800\text{ ms}$, or suspended | PLANnew.md §3 Módulo 2 |
| 6 | Execution | Phase 1 Exit Limit Order | Upon fill of entry order, immediately places Limit Sell at Best Ask + 2 ticks; max exposure 2-10s | Filled buy order, best ask, tick size | Limit Sell order payload | Cancels on timeout (2-10s) | PLANnew.md §3 Módulo 2 |
| 7 | Execution | Phase 2 Pre-Match Transition (`limpiar_mesa`) | At T-5 minutes before match start, cancels all pending orders atomically; converts trapped fills via Market Sell | Active orders, unfilled contracts | Order cancellation payloads, Market Sell orders | Fail-safe: retries market sell until 0 exposure | PLANnew.md §3 Módulo 2 |
| 8 | Execution | Phase 3 In-Play Latency Sniping (`snipe_desfase_oraculo`) | Detects real-world event before Binance book freezes; buys mispriced contracts and places immediate exit on book resumption | Real-time event (goal/red card), Binance state | Taker Buy order, conditional Limit Exit order | Aborts if market suspends before transmission | PLANnew.md §3 Módulo 2 |
| 9 | Execution | Phase 4 Time Decay Scalping | Enters contracts in draw matches with $\text{Danger Attacks/min} \to 0$ between min 75-90; holds 60-90s and exits via Market order | Minute $\in [75, 90]$, current score, attack metric | Market Buy entry, Market Sell exit after 60-90s | Forced exit if danger attacks spike | PLANnew.md §3 Módulo 2 |
| 10 | Execution | Strategy A: Time Decay Exploitation | Low-risk scalp between minutes 65-70 in stagnant live games; buys current Draw/Result share, holds 3-5 min, sells before end | Minute $\in [65, 70]$, stagnant pace, Draw/Result odds | Limit/Market Buy, Exit Sell order after 3-5 min | Aborts if goal/danger occurs during holding window | ORIGINAL_REQUEST.md Strategy A |
| 11 | Execution | Strategy B: Overreaction Hunting | High-risk scalp on panic price crashes (favorite concedes but dominates xG/possession); buys dip, sells on speculative rebound | Price crash delta, favorite xG/possession dominance | Buy Order on dip, Limit/Market Sell on first rebound | Time-stop exit if rebound fails to materialize | ORIGINAL_REQUEST.md Strategy B |
| 12 | Execution | Multi-Sport Market Coverage | Extends scanning across all sports (soccer, baseball, football, basketball, tennis, hockey, eSports), live and trending | Match discovery stream across 7 sports | Multi-sport contract candidate queue | Filters out low-liquidity or stagnant markets | ORIGINAL_REQUEST.md Directive 1 |
| 13 | Execution | Golden Rule 1: Max Spread Filter | Strict threshold: Spread between best Ask and best Bid must be $\le \$0.03$. If spread $> \$0.03$, do not operate | `best_ask`, `best_bid` | Boolean trading permission | Hard rejection if $\text{Ask} - \text{Bid} > 0.03$ | ORIGINAL_REQUEST.md GR1 |
| 14 | Execution | Parallel Swing Trading Strategy | Parallel or orthogonal multi-hour/daily swing execution running concurrently with HFT without thread contention | Market trends, daily liquidity, sports stats | Swing orders | Isolated state to prevent mutex contention with HFT | ORIGINAL_REQUEST.md R1 |
| 15 | Risk Engine | $EV$ Calculation & Filter | Computes Expected Value net of BNB-discounted fees; enforces $EV \ge 0.015$ threshold | $P_{\text{estimada}}$, $\text{Cuota/Payout}$ | $EV$: float, `operar`: bool | Rejects trade if $EV < 0.015$ | PLANnew.md §3 Módulo 3, §4 |
| 16 | Risk Engine | Stop-Loss Position Sizing | Computes nominal position size as risk budget divided by stop loss percentage | `balance`, `pct_riesgo_fijo` (1.5%), `pct_stop_loss` | `posicion_nominal`: float | Clamps stop loss to min 1% to prevent division by zero | PLANnew.md §3 Módulo 3, §4 |
| 17 | Risk Engine | Golden Rule 3: Dynamic Sizing with Top-3 BID Liquidity | Dynamic position sizing strictly reads available volume in top 3 BID levels to guarantee emergency market exit liquidity | Nominal stake, depth levels $V_{\text{Bid}}^{(1..3)}$ | `stake_ejecutable`: float | Clamps stake to $\le \sum_{k=1}^3 V_{\text{Bid}}^{(k)}$; rejects if $< \text{min\_order}$ | ORIGINAL_REQUEST.md GR3 |
| 18 | Risk Engine | Fractional Kelly Sizing | Alternative position sizing formula using 25% Fractional Kelly | $p$, $b = \text{Cuota} - 1$ | $f^*$: float | Clamps negative Kelly to 0.0 | PLANnew.md §3 Módulo 3 |
| 19 | Risk Engine | Losing Streak Attenuation | Compresses nominal risk by factor $0.85^{\text{perdidas\_consecutivas}}$ | Consecutive loss counter | `factor_racha`: float | Resets counter to 0 on any win | PLANnew.md §3 Módulo 3, §4 |
| 20 | Risk Engine | Cluster Exposure Cap (15%) | Clamps proposed stake so total cluster exposure across active concurrent trades $\le 15\%$ of bankroll | Proposed stake, active trades, bankroll | Scaled `stake`: float | Reduces stake or rejects (stake = 0) if cap saturated | PLANnew.md §3 Módulo 3, §4 |
| 21 | Latency Guard | Latency Audit & Circuit Breaker | Monitors feed and WebSocket heartbeat; if delta $> 800\text{ ms}$, raises emergency state | Timestamp of last heartbeat | `autorizacion_disparo`: (bool, reason) | Sets `emergencia_activa = True`, blocks orders | PLANnew.md §3 Módulo 4, §4 |
| 22 | Latency Guard | Panic Button / Kill Switch | Instantly cancels all active orders and purges pending orders in memory | Kill signal / user command | Cancellation API payloads | Emits emergency alert; halts loop | PLANnew.md §3 Módulo 4, §4 |
| 23 | Metrics | Analytical Metric Auditor | Computes Win Rate, ROI, Yield, Total Trades, and Accumulated Capital ($B_N$) in SQLite WAL | Trade execution log (stakes, returns, wins) | Real-time metric snapshot | Handled via WAL mode to avoid blocking HFT | PLANnew.md §3 Módulo 5, §4 |
| 24 | Treasury | $10 \to 100\text{ USD}$ Injection Milestone | Authorizes $100\text{ USD}$ capital injection once bankroll reaches $100\text{ USD}$ and validation criteria pass | `balance_actual`, trade count, $p$-value | Capital injection (+100 USD) | Requires $N \ge 300$, $p < 0.05$, $EV > 0$; one-time execution | PLANnew.md §3 Módulo 6, §4, §5 |
| 25 | Treasury | Monthly Compounding & Split | At monthly cut, allocates positive profit: 40% operating/admin expenses, 60% compound reinvestment | Monthly net profit, current balance | Split allocation, updated balance | Zero action if monthly profit $\le 0$ | PLANnew.md §3 Módulo 6, §4 |
| 26 | Treasury | $1,000\text{ USD}$ Autonomous Harvest | At monthly cut when balance $\ge 1,000\text{ USD}$, harvests 35% of monthly profit, converting to MXN; splits remainder 40/60 | Monthly net profit, balance | MXN withdrawal amount, retained balance | Activated only once balance crosses 1000 USD | PLANnew.md §3 Módulo 6, §4 |
| 27 | Telegram Bot | Interactive Bidirectional Bot | Provides real-time notifications, interactive inline buttons, and hot parameter updates | Telegram commands / callbacks | Status messages, charts, ack responses | Rejects unauthorized chat IDs; fail-soft on network retry | ORIGINAL_REQUEST.md R3 |
| 28 | Telegram Bot | Kill Switch Remote Command | Remotely triggers emergency panic button and pauses orchestrator | Command `/kill` or inline button | Confirmation message, emergency stop | Immediate async execution | ORIGINAL_REQUEST.md R3 |
| 29 | Telegram Bot | Pause / Resume Controls | Pauses and resumes trading scans | Command `/pause`, `/resume` | State confirmation | Idempotent state transitions | ORIGINAL_REQUEST.md R3 |
| 30 | Telegram Bot | Metrics Telemetry Report | Returns formatted operational report with WR, ROI, Yield, Capital, and Trade Count | Command `/report` or `/metricas` | Formatted HTML/Markdown message | Fallback to latest cached metrics if DB locked | ORIGINAL_REQUEST.md R3 |
| 31 | Telegram Bot | Hot Risk Adjustment | Updates risk parameters (`pct_riesgo_fijo`, `ev_minimo`, `max_cluster_exp`) on the fly | Command `/risk <param> <value>` | Parameter update confirmation | Validates bounds before applying | ORIGINAL_REQUEST.md R3 |
| 32 | Validation | Out-of-Sample Verification Gate | Validates paper trading results ($N \ge 300$, $p\text{-value} < 0.05$) before real capital injection | Historical trade outcomes | Statistical test result (z-score, p-value) | Blocks capital injection if $p \ge 0.05$ | PLANnew.md §5 |

---

## 3. Mathematical Formulations & Quantitative Constraints

### 3.1 Order Book Imbalance (OBI) & HFT Execution Trigger

#### Imbalance Formula
Let $V_{\text{Bid}}^{(k)}$ and $V_{\text{Ask}}^{(k)}$ be the quoted volume at depth level $k$ ($k = 1, \dots, K$, with $K \in [5, 10]$). The aggregate depth volumes are:
$$\sum V_{\text{Bid}} = \sum_{k=1}^{K} V_{\text{Bid}}^{(k)}, \quad \sum V_{\text{Ask}} = \sum_{k=1}^{K} V_{\text{Ask}}^{(k)}$$

The Order Book Imbalance metric $I \in [-1.0, 1.0]$ is defined as:
$$I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$$

#### Derivation of the "80% Buy Volume" Equivalence ($I \ge 0.60$)
Let total top-of-book depth volume be $V_{\text{Total}} = \sum V_{\text{Bid}} + \sum V_{\text{Ask}}$.  
If buy volume represents a fraction $\alpha$ of total depth volume:
$$\sum V_{\text{Bid}} = \alpha \cdot V_{\text{Total}}, \quad \sum V_{\text{Ask}} = (1 - \alpha) \cdot V_{\text{Total}}$$

Substituting into the imbalance equation:
$$I = \frac{\alpha \cdot V_{\text{Total}} - (1 - \alpha) \cdot V_{\text{Total}}}{V_{\text{Total}}} = 2\alpha - 1$$

Setting the buy volume dominance to $\alpha = 0.80$ (80% buy volume):
$$I = 2(0.80) - 1 = 1.60 - 1.0 = 0.60$$

Hence, the specification statement *"Si el desequilibrio de compra supera el 80% ($I \ge 0.60$)"* is mathematically exact and consistent: an 80% buy volume dominance corresponds identically to $I \ge 0.60$.

#### Trigger Conditions
1. **Timing Window**: $T \in [T_0 - 120\text{ min}, T_0 - 5\text{ min}]$ where $T_0$ is event kickoff.
2. **Order Book Condition**: $I \ge 0.60$.
3. **Golden Rule 1 (Spread Filter)**: $\text{Best Ask} - \text{Best Bid} \le \$0.03$. If $> \$0.03$, trade is rejected.
4. **Golden Rule 2 (Market Status)**: `status == "ACTIVE"`; if `status == "SUSPENDED"`, lock all orders.
5. **Execution Guard**: `emergencia_activa == False`, latency $\Delta t \le 800\text{ ms}$.
6. **Order Placement**:
   - Order Type: `LIMIT` (Maker).
   - Side: `BUY` (`YES` or specific contract).
   - Price: $\text{Best Bid} + 1\text{ tick}$.
7. **Exit Order Programmed Upon Fill**:
   - Order Type: `LIMIT` (Maker).
   - Side: `SELL`.
   - Price: $\text{Best Ask} + 2\text{ ticks}$.
   - Time in Force / Maximum Exposure: $2\text{ to } 10\text{ seconds}$. If unfilled after 10s, cancel limit and route to cleanup/market sell.

---

### 3.2 Expected Value ($EV$), Position Sizing, Golden Rule 3, Streak Attenuation & Cluster Cap

#### Expected Value ($EV > 0$)
$$EV = (P_{\text{estimada}} \times \text{Cuota}) - 1.0$$
where:
- $P_{\text{estimada}} \in (0, 1)$ is the model's calibrated probability of the contract settling in the money.
- $\text{Cuota}$ is the decimal payout per unit stake.
- **Entry Filter**: Trade is strictly rejected if $EV < 0.015$ (i.e. minimum edge is $+1.5\%$).
- **Commission Netting**: The payout must be net of exchange fees. In Binance Spot, trading fees are paid in BNB (at a 25% discount). When factoring in fee rate $c$ (e.g. $0.075\%$ with BNB):
  $$\text{Cuota}_{\text{neta}} = 1 + (\text{Cuota} - 1)(1 - c)$$
  The net EV is:
  $$EV_{\text{neto}} = P_{\text{estimada}} \cdot \text{Cuota}_{\text{neta}} - 1.0 \ge 0.015$$

#### Real Position Size Formula
The initial nominal position size $S_{\text{nominal}}$ is sized by allocating a fixed risk budget and dividing by the stop-loss percentage:
$$S_{\text{nominal}} = \frac{B \times \text{pct\_riesgo\_fijo} \times \text{factor\_racha}}{\max(\text{pct\_stop\_loss}, 0.01)}$$
where:
- $B$: Current account balance (`balance_actual`).
- $\text{pct\_riesgo\_fijo}$: Default is $0.015$ ($1.5\%$ of bankroll).
- $\text{pct\_stop\_loss}$: Percentage distance to the stop price; clamped by $\max(\cdot, 0.01)$ to prevent division by zero or infinite leverage.
- $\text{Riesgo Objetivo}$: $R_{\text{target}} = B \times \text{pct\_riesgo\_fijo} \times \text{factor\_racha}$.

#### Golden Rule 3: Dynamic Sizing with Top-3 BID Liquidity
To guarantee that the bot can always execute an emergency market exit (`Market Sell`) without blowing out slippage or running out of liquidity, position sizing must be bounded by available volume in the first 3 BID levels:
$$V_{\text{escape}} = \sum_{k=1}^{3} V_{\text{Bid}}^{(k)}$$
$$S_{\text{ejecutable}} = \min(S_{\text{cluster\_capped}}, V_{\text{escape}})$$
If $S_{\text{ejecutable}} < \text{MinNotional}$ (e.g. 5 USDT on Binance), the trade is rejected:
$$\text{operar} = \text{False}, \quad \text{motivo} = \text{"Liquidez BID insuficiente para salida de emergencia"}$$

#### Losing Streak Attenuation Factor
To mitigate drawdown during unfavorable regimes, the risk budget is exponentially attenuated based on the number of consecutive losses:
$$\text{factor\_racha} = 0.85^{\text{perdidas\_consecutivas}}$$
- If trade is a win ($\text{PnL} > 0$): $\text{perdidas\_consecutivas} \leftarrow 0$, yielding $\text{factor\_racha} = 1.0$.
- If trade is a loss ($\text{PnL} \le 0$): $\text{perdidas\_consecutivas} \leftarrow \text{perdidas\_consecutivas} + 1$.
- Attenuation schedule:
  - 0 losses: $0.85^0 = 1.0000$ (100% size)
  - 1 loss: $0.85^1 = 0.8500$ (85% size)
  - 2 losses: $0.85^2 = 0.7225$ (72.25% size)
  - 3 losses: $0.85^3 = 0.6141$ (61.41% size)
  - 4 losses: $0.85^4 = 0.5220$ (52.20% size)
  - 5 losses: $0.85^5 = 0.4437$ (44.37% size)

#### Cluster Exposure Cap (15%)
Let $K_{\text{active}}$ be the number of currently open/unsettled trades, and $S_i$ their allocated positions. The prospective exposure including the new trade is:
$$\text{exposicion\_futura} = \frac{(K_{\text{active}} + 1) \times S_{\text{nominal}}}{B}$$
If $\text{exposicion\_futura} > \text{max\_cluster\_exp}$ (where $\text{max\_cluster\_exp} = 0.15$ or 15%):
$$\text{compresion} = \frac{\text{max\_cluster\_exp} \times B}{(K_{\text{active}} + 1) \times S_{\text{nominal}}}$$
$$S_{\text{cluster\_capped}} = S_{\text{nominal}} \times \text{compresion} = \frac{0.15 \times B}{K_{\text{active}} + 1}$$
Total simultaneously committed capital across any active cluster is strictly capped at $\le 15\%$ of balance.

---

### 3.3 New High-Frequency Scalping Strategies

#### Strategy A: Time Decay Exploitation (Scalp de Bajo Riesgo)
- **Concept**: Exploits the steep non-linear time decay in prediction/binary markets as the match approaches completion in stagnant games.
- **Entry Window**: Minutes 65 to 70 of live matches.
- **Filter**: Stagnant pace / low offensive pressure ($\text{Dangerous Attacks/min} < \text{threshold}$, low xG growth rate).
- **Target Contract**: Buy current Draw (`Empate`) or current leading Result share.
- **Holding Period**: Exactly 3 to 5 minutes to harvest the price appreciation generated by time decay ticks.
- **Exit Action**: Sell position (Limit or Market Sell) before match conclusion (never hold through endgame stoppage time).
- **Golden Rules Enforced**: Spread must be $\le \$0.03$; size bounded by top 3 BIDs.

#### Strategy B: Overreaction Hunting (Scalp de Alto Riesgo)
- **Concept**: Capitalizes on retail market panic and temporary liquidity vacuums when an unexpected event occurs against a heavy favorite.
- **Trigger**: Sudden price crash / collapse on the pre-match favorite's contract (e.g. underdog scores first), despite real-time statistical feeds confirming the favorite continues to dominate possession ($> 60\%$) and cumulative Expected Goals ($\text{xG}_{\text{fav}} \gg \text{xG}_{\text{und}}$).
- **Entry Action**: Buy the panic "dip" on the favorite at distressed odds.
- **Exit Action**: Sell on the speculative bounce / rebound immediately following the favorite's next dangerous attack, shot on target, or box pressure—**without waiting for the favorite to actually score an equalizing goal**.
- **Risk Control**: Hard time-stop (e.g. 180–300s) if the speculative rebound fails to occur.

#### Multi-Sport Market Coverage
The market scanner operates across 7 core sporting disciplines:
1. **Soccer (Fútbol)**: Match winner (1X2), Draw in-play decay, Over/Under.
2. **Baseball (Béisbol)**: Inning moneyline, run line, time/outs decay in stagnant innings.
3. **American Football (Fútbol Americano)**: Quarter/half moneylines, drive overreaction scalping.
4. **Basketball (Básquetbol)**: In-play quarter/spread momentum, run-and-gun overreaction bounces.
5. **Tennis (Tenis)**: Game/set server advantage, break-point overreactions.
6. **Hockey (Hockey)**: Low-scoring period decay, empty-net overreaction.
7. **eSports**: Round momentum, economic round overreactions (CS/Dota/LoL).

---

### 3.4 Golden Rules of Microstructure Execution

1. **Golden Rule 1 (Spread Máximo Permitido $\le \$0.03$)**:
   $$\text{Spread} = P_{\text{Best Ask}} - P_{\text{Best Bid}}$$
   $$\text{Spread} \le 0.03 \implies \text{Permitido}; \quad \text{Spread} > 0.03 \implies \text{BLOQUEADO}$$
   Protects against adverse selection and slippage drain.

2. **Golden Rule 2 (Monitoreo de Bloqueo / MarketStatus: Suspended)**:
   Whenever Binance emits `status == "SUSPENDED"` (e.g. goal scored, VAR check, pitch review):
   $$\text{Bloquear de inmediato toda nueva orden; cancelar órdenes límite huérfanas en el libro}$$

3. **Golden Rule 3 (Dynamic Sizing con Liquidez de Escape en Top 3 BIDs)**:
   $$S_{\text{max\_permitido}} = \sum_{k=1}^{3} V_{\text{Bid}}^{(k)}$$
   No trade can be entered whose position size exceeds the instantaneous exit liquidity of the top 3 bid price levels.

---

### 3.5 "Ordeño e Inyección" & Capital Progression ($10 \to \$100 \to \$1,000$)

```
  [Stage 1: Micro-Bootstrapping]
  Initial Balance: $10.00 USD
         │
         ▼
  Autonomous HFT & Compounding
  Accumulate $10.00 -> $100.00 USD
  Requires: N >= 300 paper trades, p-value < 0.05, EV > 0
         │
         ▼
  [Stage 2: Capital Injection Gate]
  Balance >= $100.00 USD
  --> Action: Inject +$100.00 USD (Balance becomes >= $200.00 USD)
  --> Event: INYECCION_100_USD_APLICADA (one-time flag)
         │
         ▼
  [Stage 3: Acceleration Compounding]
  Balance $200.00 -> $1,000.00 USD
  Monthly Settlement:
    - 40% to Operating / Administrative Expenses
    - 60% Reinvested into Compounding Base Balance
         │
         ▼
  [Stage 4: Autonomous Harvesting ("Ordeño")]
  Balance >= $1,000.00 USD
  --> Flag: meta_1000_activada = True
  Monthly Settlement:
    1. Harvest 35% of Monthly Net Profit (converted to MXN via P2P/Fiat)
    2. Remaining 65% of Profit is split:
       - 40% (26% of total profit) to Operating Expenses
       - 60% (39% of total profit) to Compounding Base Balance
```

#### Monthly Settlement Formulas

Let $G_M = \text{ganancia\_mensual}$ be the net profit realized in the monthly cycle.
If $G_M \le 0$:
$$\text{retiro} = 0.0, \quad \text{operacion} = 0.0, \quad \text{reinversion} = 0.0, \quad B_{\text{nuevo}} = B$$

**Case A: Balance $< \$1,000$ (Stage 3 Acceleration)**:
$$\text{retiro\_autonomo\_35} = 0.0$$
$$\text{gastos\_operacion\_40} = 0.40 \times G_M$$
$$\text{reinversion\_compuesta\_60} = 0.60 \times G_M$$
$$B_{\text{nuevo}} = (B - G_M) + \text{reinversion\_compuesta\_60} = B - 0.40 \times G_M$$

**Case B: Balance $\ge \$1,000$ (Stage 4 Autonomous Harvesting)**:
$$\text{retiro\_autonomo\_35} = 0.35 \times G_M$$
$$U_{\text{restante}} = G_M - \text{retiro\_autonomo\_35} = 0.65 \times G_M$$
$$\text{gastos\_operacion\_40} = 0.40 \times U_{\text{restante}} = 0.26 \times G_M$$
$$\text{reinversion\_compuesta\_60} = 0.60 \times U_{\text{restante}} = 0.39 \times G_M$$
$$B_{\text{nuevo}} = (B - G_M) + \text{reinversion\_compuesta\_60} = B - 0.61 \times G_M$$

---

### 3.6 Key Performance Metrics Formulas

1. **Total Trades ($N$)**:
   $$N = \sum_{i=1}^{M} 1 = N_{\text{win}} + N_{\text{loss}} + N_{\text{push}}$$

2. **Win Rate ($WR$)**:
   $$WR = \frac{N_{\text{win}}}{N} = \frac{\sum_{i=1}^{N} \mathbb{I}(\text{PnL}_i > 0)}{N}$$
   Expressed as a percentage: $WR\% = WR \times 100$.

3. **Accumulated Capital ($B_N$)**:
   $$B_N = B_0 \cdot \prod_{i=1}^{N} (1 + f_i \cdot R_i)$$
   where:
   - $B_0$ is initial capital ($10.0\text{ USD}$).
   - $f_i = \frac{S_i}{B_{i-1}}$ is the fraction of total bankroll allocated to trade $i$.
   - $R_i = \frac{\text{PnL}_i}{S_i}$ is the fractional return on the trade ($R_i = \text{Payout} - 1$ on a win; $R_i = -1$ on a total loss; or $R_i = -\text{pct\_stop\_loss}$ on a stop-out).
   - In additive accounting: $B_N = B_0 + \sum_{i=1}^N \text{PnL}_i + \text{Inyecciones} - \text{Retiros}$.

4. **Return on Investment ($ROI$)**:
   $$ROI = \frac{B_N - B_0 - \text{Inyecciones Netas}}{B_0} = \frac{\sum_{i=1}^N \text{PnL}_i}{B_0}$$
   (Cumulative net gain divided by initial baseline capital).

5. **Yield (Volume Turnover Profitability)**:
   $$\text{Yield} = \frac{\text{Ganancia Neta Total}}{\text{Volumen Total Operado (Turnover)}} = \frac{\sum_{i=1}^{N} \text{PnL}_i}{\sum_{i=1}^{N} S_i}$$
   Measures structural trading edge per monetary unit transacted, invariant to position sizing or compound growth.

6. **Out-of-Sample Statistical Test ($p\text{-value}$)**:
   For validation before capital injection ($N \ge 300$):
   $$Z = \frac{WR - 0.50}{\sqrt{\frac{0.50 \times (1 - 0.50)}{N}}} = \frac{WR - 0.50}{\frac{0.50}{\sqrt{N}}}$$
   For a one-tailed test asserting $WR > 0.50$:
   $$p\text{-value} = 1 - \Phi(Z) < 0.05 \implies Z > 1.645$$

---

## 4. Telegram Bot Requirements & Commands Specification

Per `ORIGINAL_REQUEST.md` R3 and `PLANnew.md`, the Telegram interface provides **bidirectional interactive control** with the main orchestrator:

### 4.1 Required Bot Commands

| Command | Arguments | Interaction Type | Behavior / System Action |
|---------|-----------|------------------|--------------------------|
| `/start` | None | Message + Inline Keyboard | Displays system status banner and persistent control keypad |
| `/status` | None | Instant Response | Reports live status: HFT & Swing state, WebSocket latency, Binance market status, open orders |
| `/kill` | None | Inline Button / Command | Triggers `boton_panico()`: cancels all pending orders, terminates positions if configured, halts loops |
| `/pause` | None | Inline Button / Command | Pauses order scanning and entry triggers; leaves existing orders or cancels them safely |
| `/resume` | None | Inline Button / Command | Resumes order book scanning and entry triggers |
| `/report` or `/metricas` | None | Formatted Message | Generates full audit report: $WR$, $B_N$, $ROI$, $\text{Yield}$, $N$, losing streak count, and daily PnL |
| `/chart` | None | Photo / Document | Generates and sends matplotlib/plotly equity curve and drawdown plot |
| `/risk` | `<param> <val>` | Text Command | Dynamically updates risk configuration in hot memory: `pct_riesgo_fijo`, `ev_minimo`, `max_cluster_exp` |
| `/harvest` | None | Confirmation Prompt | Queries treasury status, reports progress toward $\$1,000$, and manually triggers monthly cut calculation if authorized |

### 4.2 Interactive Inline Keyboard Layout
```
┌───────────────────────────┬───────────────────────────┐
│  🟢 Reanudar / Pausar ⏸️   │    🛑 KILL SWITCH 🛑     │
├───────────────────────────┼───────────────────────────┤
│   📊 Reporte Métricas     │    📈 Gráfica Rendimiento │
├───────────────────────────┼───────────────────────────┤
│   ⚙️ Parámetros Riesgo    │    💰 Estado Tesorería    │
└───────────────────────────┴───────────────────────────┘
```

### 4.3 Autonomous Push Notifications

1. **System Startup (`notificar_inicio`)**:
   - Engine version, initial balance (USDT/MXN), active strategy modes.
2. **Periodic Interval Report (every 3 to 6 hours)**:
   - Initial balance, current balance, session PnL ($ and %), active strategies, open orders.
3. **Daily Close Report (21:00 CDMX / 03:00 BST)**:
   - Opening balance, closing balance, day PnL, consecutive loss streak, monthly goal progress, engine health.
4. **Emergency / Circuit Breaker Alerts**:
   - Feed/WS latency $> 800\text{ ms}$ (`LATENCIA_EXCESIVA`).
   - Market transition to `SUSPENDED` (`MERCADO_SUSPENDIDO_BINANCE`).
   - Drawdown trip: Hard stop triggered or consecutive loss threshold crossed.

---

## 5. Acceptance Criteria & Test Verification Matrix

From `ORIGINAL_REQUEST.md` (lines 73-86), the acceptance criteria specify three automated test verification suites:

### 5.1 Verification Test Matrix

| Test Suite / Script | Target Component | Input / Scenario | Expected Verification Assertion | Acceptance Gate |
|---------------------|------------------|------------------|---------------------------------|-----------------|
| `test_hft.py` | OrderBookListener & MicrostructureEngine | Injected synthetic L2 book data with Buy Imbalance $> 80\%$ ($I \ge 0.60$) and Spread $\le \$0.03$ | System generates a Limit Buy order with price = $\text{Best Bid} + 1\text{ tick}$, correctly formatted for Binance Spot API | Test passes without runtime error; order payload matches API spec |
| `test_golden_rules.py` | Microstructure & Risk Engine | 1. Spread $= \$0.04 > \$0.03$<br>2. `status == "SUSPENDED"`<br>3. Top 3 BIDs volume $= 10$ contracts, nominal stake $= 25$ contracts | 1. Spread filter blocks trade.<br>2. Suspended status locks order.<br>3. Position size clamped to $10$ contracts | All three golden rules verified with unit assertions |
| `test_hft_concurrencia.py` | Orchestrator & Task Scheduler | Concurrent execution of HFT micro-scalping loop and Swing Trading engine | Both loops execute concurrently via `asyncio` without deadlocks, shared state corruption, or blocking | Zero lockups across 100 simulated iterations |
| `test_tesoreria.py` (Risk & Sizing) | `EscudoFinancieroHFT` | Injected sequence of simulated wins and losses (e.g. 3 consecutive losses) | Factor de atenuación computes exactly $0.85^3 \approx 0.614125$; position sizing scales by this factor and obeys 15% cluster cap | Mathematical assertion match within $10^{-4}$ precision |
| `test_tesoreria.py` (Thresholds) | `TreasuryAndHarvestingManager` | Simulated balance growth crossing $100\text{ USD}$ and $\$1,000\text{ USD}$ | 1. At $B \ge 100$, triggers `INYECCION_100_USD_APLICADA` and adds $+100$ USD once.<br>2. At $B \ge 1000$, enables `meta_1000_activada` and calculates 35% harvest on monthly close | State transitions fire precisely at threshold crossings |
| `test_metricas.py` | `StateRegistry & MetricAuditor` | Controlled set of closed trades (e.g. 10 trades: 7 wins, 3 losses, known stakes and payouts) | 1. $WR == 0.70$<br>2. $B_N == B_0 \prod (1 + f_i R_i)$<br>3. $ROI == \frac{\sum \text{PnL}}{B_0}$<br>4. $\text{Yield} == \frac{\sum \text{PnL}}{\sum S_i}$ | Assertions match exact calculated values |
| `test_telegram_mock.py` | TelegramBot & Orchestrator | `MockTelegramClient` sending simulated `/kill` and `/report` commands | 1. Orchestrator immediately pauses and enters emergency state (`boton_panico`).<br>2. Bot responds with current accurate performance metrics | Orchestrator state updates within $< 50\text{ ms}$; report text verified |

---

## 6. Edge Cases & Boundary Conditions

| # | Feature | Boundary Input / Scenario | Observed / Required Behavior |
|---|---------|---------------------------|------------------------------|
| 1 | OBI Calculation | Empty Order Book ($\sum V_{\text{Bid}} = 0, \sum V_{\text{Ask}} = 0$) | Return $I = 0.0$; do not raise ZeroDivisionError |
| 2 | OBI Calculation | One-sided Book ($\sum V_{\text{Bid}} > 0, \sum V_{\text{Ask}} = 0$) | $I = +1.0$; valid trigger candidate only if Best Bid and Ask definitions exist |
| 3 | Golden Rule 1 | Spread is exactly $\$0.0300$ | Trade permitted ($\le \$0.03$). If $\$0.0301$, strictly blocked |
| 4 | Golden Rule 2 | Market transitions to `SUSPENDED` while order is in flight | Order rejected or cancelled by Binance; bot flags status and locks new orders |
| 5 | Golden Rule 3 | Top 3 BID levels have zero volume | Position size clamped to 0.0; trade rejected with liquidity error |
| 6 | Position Sizing | Zero or negative Stop-Loss (`pct_stop_loss <= 0`) | Clamped by $\max(\text{pct\_stop\_loss}, 0.01)$ to 1%, preventing zero division or infinite stake |
| 7 | Position Sizing | Severe losing streak (e.g. 20 consecutive losses) | $0.85^{20} \approx 0.03876$. Position size shrinks smoothly to ~3.88% of nominal. Minimum order size limit applied |
| 8 | Position Sizing | Calculated stake below Binance minimum notional (e.g. 5 USDT) | Trade must be skipped (`operar: False, motivo: "Stake menor al mínimo permitido"`) |
| 9 | Cluster Cap | Active cluster exposure already at or above 15% | Compression factor $\le 0.0 \implies \text{stake} = 0.0$; trade rejected |
| 10 | Strategy A Decay | Goal scored during minutes 65-70 holding window | Emergency exit triggered via market order; loss capped by stop-loss buffer |
| 11 | Strategy B Overreaction | Favorite fails to mount dangerous attack after 300s | Time-stop triggered; position liquidated at market to prevent prolonged exposure |
| 12 | Latency Guard | Sporadic feed delay exceeding $800\text{ ms}$ | `emergencia_activa` activates, blocking order firing. When feed stabilizes, recovers automatically |
| 13 | Monthly Cut | Negative monthly profit ($G_M \le 0$) | Zero withdrawal, zero operational fee deduction, balance remains unmodified |
| 14 | Treasury Injection | Balance reaches $\$100$ but paper trade count $N < 300$ or $p \ge 0.05$ | Injection is deferred until validation criteria are fully satisfied |
| 15 | Treasury Injection | Balance reaches $\$100$ a second time after dip below $\$100$ | Injection executes only once (`hito_100_inyectado == True` blocks re-injection) |
| 16 | Telegram Control | Rapid duplicate `/kill` commands | Idempotent execution; logs warning and maintains safe emergency state |
| 17 | Telegram Control | Unauthorized user messaging the bot | Commands rejected with unauthorized alert; logs offending `user_id` |

---

## 7. Comparative Synthesis: PLANnew vs Predecessor vs Existing Codebase

| Dimension | PLANnew.md (Active Target) | Predecessor (ORIGINAL_REQUEST.md 2026-09-29) | Existing Codebase (`CONTINUITYEM`) |
|-----------|---------------------------|---------------------------------------------|-----------------------------------|
| **Target Platform** | Binance Spot (Prediction Markets / AMMs) | Matchbook, Playdoit, Winspot, Draftea | Matchbook API & SQLite (`cerebrillum.db`) |
| **Market Scope** | All 7 sports (Soccer, Baseball, Football, Basketball, Tennis, Hockey, eSports) | Commercial sportsbooks + Matchbook | Sports exchange (Soccer, Tennis, Basketball) |
| **Strategy Core** | 4 Phases + OBI ($I \ge 0.60$) + Strat A (Time Decay) + Strat B (Overreaction) | TIF Maker GC (45s) + Browser automation + Mobile API conformance | 3 HFT Strats (A: Pure Maker, B: VWAP Scalp, C: Drain Scalp) |
| **Golden Rules** | Spread $\le \$0.03$; Suspended lock; Top-3 BID escape sizing | Hard weekly profit caps + variance injection | VWAP slippage $\le 3\%$, Heartbeat 15/30s |
| **Risk Model** | $EV > 0.015$, Risk/StopLoss, $0.85^n$ streak attenuation, 15% cluster cap | Weekly hard profit cap + variance injection | Fractional Kelly (0.25), 15% cluster cap, 3H/Daily stops |
| **Treasury & Growth**| $10 \to \$100 \to \$1,000$ (+$100$ injection, 40/60 split, 35% MXN harvest) | Dynamic volume throttling per platform | Compound interest multipliers ($100 \to \$100,000$ MXN) |
| **Telegram Role** | Bidirectional interactive controller (Kill switch, hot params, reports) | None specified | Periodic reporter (3H cut, daily close, startup/shutdown) |

---
*Report completed, updated with latest business directives, and verified against all specification sources.*
