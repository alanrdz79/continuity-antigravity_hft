---
name: continuity-hft-architecture
description: "Reference architecture, mathematical principles, and constraints for the CONTINUITY HFT sports trading system v2.0 Multi-Strategy. Invoke this when adding new sports, new strategies, expanding to new exchanges, or altering the Kelly sizing logic."
---

# CONTINUITY HFT Engine Architecture & Guidelines (v2.0 Multi-Strategy)

When modifying or expanding the CONTINUITYEM project, adhere strictly to the following architectural guidelines to maintain HFT performance and safety.

## 1. Core Mathematical Philosophy
The system operates on micro-capital multiplication ($100 MXN → $500 MXN in month 1) using edge-case mathematical arbitrage:
- **Kelly Criterion**: Fractional Kelly is dynamically adjusted. For micro-cap (< $1,000 MXN), multiplier is x5. For $1k–$10k: x3. For $10k–$50k: x2. Above $50k: x1. Kelly is capped at 30% of bankroll per trade.
- **Commission Discount**: Matchbook charges 4% on net winnings. `AjustadorComisiones.ev_neto()` MUST ALWAYS be called before approving any trade signal.
- **Minimum Bet**: $2 MXN. Any stake below this threshold is discarded immediately.

## 2. Multi-Strategy Architecture (v2.0)
Three strategies run **in parallel** every scan cycle. Each has an isolated cooldown and EV logic:

| ID | Prefix | Cooldown | Entry Logic | Order Type |
|----|--------|----------|-------------|------------|
| A  | `MKR_` | 300s     | prob_gap < 3% → maker at best_back + 1 tick | Maker (limit) |
| B  | `VWAP_` | 120s    | in_play + back_odds > VWAP × 1.02 | Taker (immediate) |
| C  | `DRN_` | 300s     | 1.5% ≤ prob_gap < 3% + runner seen ≥ 1 cycle | Maker (best_back + 2 ticks) |

**To add a new strategy**:
1. Create a `evaluar_estrategia_X()` function following the same signature pattern (returns `None` or a signal dict).
2. Add a unique cooldown prefix (e.g., `ARB_`, `LAY_`).
3. Add it to `ESTRATEGIA_ACTIVA` dict.
4. Call it in `ciclo_escaneo_hft()` and include its result in the `for señal in [...]` loop.

## 3. Market Execution Logic
- **No Blocking Calls**: The main event loop (`HFT_GALO.py`) must never wait for disk I/O.
- **Microsecond RAM state**: Cooldowns (`cooldowns_mercado`), pending offers (`ofertas_pendientes`), and cycle tracking (`runners_vistos`) are plain Python dicts.
- **Graceful Fault Tolerance**: Heartbeat mechanisms ping Matchbook every 15s. Re-authenticates on 401/400 errors.

## 4. Circuit Breakers (MUST NOT REMOVE)
- **Hard Stop** at ≤ $40 MXN bankroll. All strategies halt, Telegram alert sent once.
- **Daily Trailing Stop** at -20% from daily peak. Halts for the day, Telegram alert sent once per day.
- Both are checked at the top of `ciclo_escaneo_hft()` before any strategy evaluation.

## 5. Extending the System (New Exchanges)
1. Create `conectores/<exchange_name>_async.py`.
2. Emulate the `obtener_eventos_hft` contract: return list of dicts with `markets` → `runners` → `prices` (both `back` and `lay` sides with `odds` and `available-amount`).
3. Standardize data so `HFT_GALO.py` ingests it without knowing the exchange source.
4. If the exchange uses Cloudflare, use `curl_cffi` (impersonate="chrome110").

## 6. MLOps / Data
- Data is asynchronously flushed from RAM to `continuitis/db_metrics/metricas_hft.sqlite`.
- Do NOT introduce pandas, CSV, or heavy ML inference inside `HFT_GALO.py`. ML must run in a separate async thread.
