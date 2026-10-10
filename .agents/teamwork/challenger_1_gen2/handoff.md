# Handoff Report — Challenger 1 (Adversarial Stress Verification)

**Verdict**: `REQUEST_CHANGES`  
**Date**: 2026-10-10  
**Target Project**: CONTINUITY HFT Binance  
**Test Suite Created & Certified**: `pruebas_unitarias/test_adversarial_challenger_gen2.py` (31 tests: 30 passed, 1 xfailed)

---

## 1. Observation

### Observation 1: Bigtable Row Key Reverse-Timestamp Lexicographical Sorting Math
- **File**: `continuitis/state_registry.py:250-267`
- **Code**:
  ```python
  long_max = 9223372036854775807
  if isinstance(timestamp_micros, float) and timestamp_micros < 1e11:
      ts_int = int(timestamp_micros * 1_000_000)
  else:
      ts_int = int(timestamp_micros)
  reverse_ts = max(0, long_max - ts_int)
  seq_norm = max(0, int(seq_id)) % 10_000_000_000
  return f"{symbol}#{reverse_ts:019d}#{seq_norm:010d}"
  ```
- **Empirical Test**: `TestBigtableRowKeyMath::test_reverse_timestamp_monotonic_sorting_across_epochs` and `test_microsecond_single_tick_resolution`.
- **Result**: PASSED. Verified strictly that across timestamps from epoch 0 to `Long.MAX_VALUE`, `k_newer < k_older` holds unconditionally. Sub-millisecond and microsecond ticks (1 microsecond apart) produce unique, strictly ordered keys. Float second inputs scale identically to integer microsecond inputs. Sequence IDs normalize cleanly with 10-digit zero padding (`%010d`).

### Observation 2: Zero SQLite File Generation Under Heavy Concurrency
- **File**: `continuitis/state_registry.py:10-362`
- **Empirical Test**: `TestZeroSQLiteAndConcurrency::test_zero_sqlite_files_created_under_heavy_concurrent_operations`.
- **Result**: PASSED. 100 concurrent threads executing 5,000 state read/write, queue management (`encolar_partido`, `obtener_partidos_pendientes`, `cerrar_partido`), and trade record operations in the transparent thread-safe in-memory mock mode. Zero `.db`, `.sqlite`, `-wal`, or `-shm` files were created anywhere in the workspace.

### Observation 3: Kelly Criterion Formula & Critical IEEE-754 NaN Vulnerability
- **File**: `continuitis/riesgo_binance.py:70-97`
- **Code**:
  ```python
  def calcular_criterio_kelly(
      p_estimada: float,
      cuota_neta: float,
      fraccion_kelly: float = 0.25,
  ) -> float:
      if cuota_neta <= 1.0 or p_estimada <= 0.0:
          return 0.0

      b = cuota_neta - 1.0
      ev = (p_estimada * cuota_neta) - 1.0
      if ev <= 0.0:
          return 0.0

      kelly_puro = ev / b
      frac_val = max(0.0, float(fraccion_kelly))
      kelly_frac = frac_val * kelly_puro
      # Acotado estrictamente dentro de [0.0, 0.25]
      f_star = max(0.0, min(0.25, kelly_frac))
      return round(float(f_star), 4)
  ```
- **Empirical Command Executed**:
  ```bash
  python -c "
  from continuitis.riesgo_binance import EscudoFinancieroBinance, calcular_criterio_kelly, OrderProposal
  print('Kelly with NaN prob:', calcular_criterio_kelly(float('nan'), 2.0))
  escudo = EscudoFinancieroBinance()
  res = escudo.calcular_posicion(balance_actual=1000.0, p_estimada=float('nan'), cuota=2.0, pct_stop_loss=0.05, usar_kelly=True)
  print('Escudo posicion with NaN prob:', res['operar'], 'stake:', res['stake'], 'ev:', res['ev'])
  prop = OrderProposal(symbol='SOCCER_PRED', side='BUY', target_price=0.50, stop_price=0.48, estimated_prob=float('nan'), payout_decimal=2.0, strategy_id='TEST')
  decision = escudo.evaluar_propuesta(proposal=prop, balance=1000.0)
  print('Approved order with NaN prob:', decision.approved, 'quantity:', decision.quantity, 'ev_net:', decision.ev_net)
  "
  ```
- **Verbatim Output**:
  ```
  Kelly with NaN prob: 0.25
  Escudo posicion with NaN prob: True stake: 150.0 ev: nan
  Approved order with NaN prob: True quantity: 300.0 ev_net: nan
  ```
- **Empirical Tests in Suite**:
  - `TestKellyIEEE754ExtremeStress::test_kelly_nan_safe_fail_closed_contract`: XFAIL (asserts `calcular_criterio_kelly(nan, 2.0) == 0.0`).
  - `TestKellyIEEE754ExtremeStress::test_kelly_nan_vulnerability_empirical_confirmation`: PASSED (asserts `calcular_criterio_kelly(nan, 2.0) == 0.25`).
  - `TestKellyIEEE754ExtremeStress::test_escudo_nan_approval_vulnerability_empirical_confirmation`: PASSED (asserts `calcular_posicion` returns `operar: True`, `stake: 150.0`).
- **Standard Extremes for Finite Numbers**: `TestKellyCriterionBoundaryExtremes` (7 tests: $p \to 0$, $p \to 1$, odds $\le 1.0$, odds $\to 1.000001$, longshots $100,000$, zero/negative EV, cap at 0.25) all PASSED.

### Observation 4: Streak Factor Attenuation ($0.85^n$) & 15% Cluster Cap Invariance
- **File**: `continuitis/riesgo_binance.py:120-156, 400-505`
- **Empirical Test**: `TestStreakAttenuationAndClusterCap::test_streak_attenuation_decay_values` and `test_cluster_cap_15_percent_strict_invariance`.
- **Result**: PASSED. Verified decay values: $n=0 \to 1.0$, $n=1 \to 0.85$, $n=10 \to 0.1969$, $n=50 \to 0.0003$. Win resets streak to $n=0$ and factor to $1.0$ immediately. When cluster headroom is exhausted or reached, `evaluar_propuesta` strictly clamps allocations and rejects with `Exposición máxima de clúster (15%) alcanzada`.

### Observation 5: Autonomous Harvesting at $1,000 USD Balance with 35% MXN Isolation
- **File**: `continuitis/tesoreria.py:194-257`
- **Empirical Test**: `TestAutonomousHarvestingProtocol::test_harvesting_exact_mathematical_identity`, `test_harvesting_boundary_sub_1000_strictly_blocked`, and `TestSequentialHarvestingAndCompoundingStress::test_multi_cycle_harvesting_cumulative_vaults`.
- **Result**: PASSED.
  - At $B_0 = \$10.00, B = \$1000.00$: net profit $= \$990.00$.
  - 35% net profit isolated to MXN: $\$346.50$ USD ($6930.00$ MXN at FX 20.0).
  - Remainder $(\$643.50)$: 40% expenses $(\$257.40)$ and 60% compound reinvestment $(\$386.10)$.
  - Post-harvest trading balance: $\$396.10$.
  - Exact balance identity verified to 4 decimals: $\$1000.00 == \$346.50 + \$257.40 + \$396.10$.
  - Boundary: balance $\$999.9999$ is strictly blocked; $\$1000.0000$ executes.
  - Sequential multi-cycle harvesting tracks cumulative vaults across multiple growth periods without drift.

### Observation 6: Strategy V `DualBuyProposal` (Binary Parity Arbitrage)
- **File**: `estrategias/arbitraje_amm.py:78-93, 292-385`
- **Empirical Test**: `TestStrategyVDualBuyProposal` (3 tests) and `TestStrategyVDualBuyEdgeBoundaries` (2 tests).
- **Result**: PASSED.
  - Generates atomic `DualBuyProposal` when `Ask(YES) + Ask(NO) < 1.00 - fees`.
  - Accurately discounts fees with BNB discount ($0.075\%$ effective).
  - Unbalanced book liquidity sizing correctly takes $min(V_{\text{yes}}, V_{\text{no}})$.
  - Golden Rule 2 fail-closed: immediately aborts/rejects if either leg is marked `MarketStatus: SUSPENDED`.
  - Rejects when net edge $< \text{min\_parity\_edge}$ or total cost $\ge 1.00$.

### Observation 7: Pre-Match and In-Play Target EV Early Exits
- **File**: `orquestadores_principales/HFT_BINANCE.py:502-606`
- **Empirical Test**: `TestTargetEVEarlyExits::test_ev_exit_pre_match_and_in_play_sports_and_esports` and `TestMultiAssetEVEarlyExitsStress::test_eight_discipline_simultaneous_ev_exits`.
- **Result**: PASSED.
  - `_vigilar_y_cerrar_posiciones_abiertas` monitors and closes positions immediately when `best_bid >= target_exit_price` (EV fulfilled) without waiting for match conclusion.
  - Verified across 8 distinct disciplines: Soccer, Basketball, Tennis, Baseball, American Football, LOL, CS2, and DOTA.
  - Verified in both pre-match (`is_live=False`, Phase 1) and in-play (`is_live=True`, Phase 3/4) states.

### Observation 8: Phase 2 T-5m `limpiar_mesa`
- **File**: `estrategias/hft_engine.py:471-539`
- **Empirical Test**: `TestPhase2LimpiarMesaZeroExposure::test_t5m_limpiar_mesa_cancels_and_liquidates_to_zero_exposure`.
- **Result**: PASSED. Verified that at T-5m, `ejecutar_fase_2_limpiar_mesa` cancels all open orders, liquidates open positions at market, clears `active_positions`, and guarantees `exposicion_final_pct == 0.0`.

---

## 2. Logic Chain

1. **Step 1 (Core Functional Alignment)**:
   Observations 1, 2, 4, 5, 6, 7, and 8 confirm that the system meets the functional requirements specified in `ORIGINAL_REQUEST.md`, `PROJECT.md`, and `TEST_INFRA.md`. Bigtable row key reverse math is monotonically sound; SQLite has been completely eliminated in memory mock and Redis modes; streak attenuation and cluster caps are invariant; autonomous harvesting satisfies conservation of capital; Strategy V produces atomic `DualBuyProposal` objects; and both pre-match and in-play EV early exits execute properly across all sports disciplines.

2. **Step 2 (Identification of Critical Edge-Case Vulnerability in Observation 3)**:
   In `continuitis/riesgo_binance.py:70-97`, `calcular_criterio_kelly` handles boundary conditions with:
   ```python
   if cuota_neta <= 1.0 or p_estimada <= 0.0:
       return 0.0
   ...
   if ev <= 0.0:
       return 0.0
   ...
   f_star = max(0.0, min(0.25, kelly_frac))
   ```
   Under IEEE-754 semantics in Python:
   - Any comparison with `NaN` (such as `float('nan') <= 0.0` or `ev <= 0.0`) evaluates to `False`.
   - Therefore, when `p_estimada` is `float('nan')`, execution bypasses both zero-checks.
   - `kelly_frac` evaluates to `float('nan')`.
   - In Python's built-in `min(0.25, float('nan'))`, because `float('nan') < 0.25` is `False`, the function returns `0.25`.
   - `max(0.0, 0.25)` returns `0.25`.

3. **Step 3 (Blast Radius Assessment in Risk Engine)**:
   In `continuitis/riesgo_binance.py:280-480`, `calcular_posicion` and `evaluar_propuesta`:
   - Checks `if ev < self.ev_minimo:` where `self.ev_minimo = 0.015`. Because `float('nan') < 0.015` evaluates to `False`, the EV gate is bypassed.
   - When Kelly sizing is active, `f_star_kelly` is returned as `0.25`.
   - The risk engine treats this corrupt prediction as an ultra-high conviction edge, approving an order for 25% of bankroll (clamped to the 15% cluster cap, or 300 contracts / $150 USD).
   - If executed, the trade's PnL is NaN, which poisons `AuditorMetricas` accumulators (`suma_pnl = nan`, `ROI = nan`), causing permanent metric telemetry corruption.

4. **Step 4 (Conclusion Formulation)**:
   While the system passes all 7 formal Acceptance Criteria and 124 E2E tests for well-formed numbers, this IEEE-754 vulnerability is a critical financial hazard for an autonomous algorithmic trading system. A financial risk engine must be **fail-closed** to all non-finite numerical inputs (`NaN`, `Inf`). Consequently, Challenger 1 must issue `REQUEST_CHANGES` to address this before final release.

---

## 3. Caveats

- **Network I/O**: Tests were executed against local mock backends (`mock_mode=True`, Redis in-memory mock fallback, mock exchange client). Live network connectivity to GCP Memorystore / Cloud Bigtable endpoints in Asia-Northeast was not tested due to development sandbox boundaries.
- **Hardware Failure**: Physical machine power failure and OS SIGKILL kernel events during in-flight memory writes were not investigated.

---

## 4. Conclusion

**Verdict**: `REQUEST_CHANGES`

The system exhibits robust architecture, correct Bigtable row key reverse math, zero SQLite persistence, mathematically exact autonomous harvesting, and clean EV early exits. However, a critical edge-case vulnerability was empirically confirmed:
- **Flaw**: `calcular_criterio_kelly` and `EscudoFinancieroBinance.calcular_posicion` approve trades with maximum 0.25 / 15% capital allocations when supplied with `float('nan')` probabilities or odds.
- **Required Remediation (for Milestone 2 / Worker)**:
  In `continuitis/riesgo_binance.py`, add explicit validation for non-finite IEEE-754 floats at the entry points of `calcular_criterio_kelly` and `calcular_posicion`:
  ```python
  if math.isnan(p_estimada) or math.isnan(cuota_neta) or math.isinf(p_estimada) or math.isinf(cuota_neta):
      return 0.0
  ```
  And in `calcular_posicion`:
  ```python
  if math.isnan(p_estimada) or math.isnan(cuota) or math.isnan(balance_actual) or math.isnan(ev):
      return {"operar": False, "motivo": "Entrada numérica inválida (NaN/Inf)", ...}
  ```

---

## 5. Verification Method

To independently verify all findings and reproduce the vulnerability:

1. **Run the Challenger Gen 2 Adversarial Test Suite**:
   ```bash
   python -m pytest pruebas_unitarias/test_adversarial_challenger_gen2.py -v
   ```
   **Expected Result**: 30 passed, 1 xfailed. `test_kelly_nan_safe_fail_closed_contract` records XFAIL, while `test_kelly_nan_vulnerability_empirical_confirmation` and `test_escudo_nan_approval_vulnerability_empirical_confirmation` pass, proving the vulnerability.

2. **Run One-Line Python Empirical Reproduction**:
   ```bash
   python -c "from continuitis.riesgo_binance import calcular_criterio_kelly, EscudoFinancieroBinance; print('Kelly:', calcular_criterio_kelly(float('nan'), 2.0)); print('Risk Approved:', EscudoFinancieroBinance().calcular_posicion(1000.0, float('nan'), 2.0, 0.05)['operar'])"
   ```
   **Expected Result**: Prints `Kelly: 0.25` and `Risk Approved: True`.

3. **Run Full Repository E2E Suite**:
   ```bash
   python -m pytest pruebas_unitarias/test_e2e_acceptance_criteria.py -v
   ```
   **Expected Result**: 124 passed in ~31s.

4. **Invalidation Condition**:
   Once the worker applies `math.isnan()` checks in `continuitis/riesgo_binance.py`, `test_kelly_nan_safe_fail_closed_contract` will turn XPASS and the one-line command will return `Kelly: 0.0` and `Risk Approved: False`. At that point, the verdict can transition to `APPROVE`.
