# Task Assignment — Worker M2 (Autonomous Treasury & Financial Engine)

## Identity
- Role: teamwork_preview_worker
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m2_gen2
- Parent: orchestrator_continuity_gen2
- Milestone: M2 — Autonomous Treasury & Financial Engine (Requirement R2)

## Mandatory Reading Before Starting Work
You MUST read the following files before writing any code:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r2\handoff.md`

## Write Ownership Boundaries
You have exclusive write access ONLY to the following files:
- `continuitis/riesgo_binance.py`
- `continuitis/tesoreria.py`
- `continuitis/auditor_metricas.py`
- `pruebas_unitarias/test_r2_exactitud_financiera.py`
DO NOT write to or modify any other files (e.g., `continuitis/state_registry.py`, `memoria_hft.py`, `arbitraje_amm.py`, or `HFT_BINANCE.py`).

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Detailed Requirements to Implement
1. **Kelly Criterion in `continuitis/riesgo_binance.py`**:
   - Implement `calcular_criterio_kelly(p_estimada, cuota_neta, fraccion_kelly=0.25)` using the exact formula:
     $f^* = \text{fraccion} \times \frac{p(b+1) - 1}{b}$, where $b = \text{cuota\_neta} - 1$.
   - Bound fraction within $[0.0, 0.25]$ and return 4-decimal precision float.
2. **Real Position Sizing ($S_{\text{nominal}}$)**:
   - Modulate position by streak factor $0.85^n$ (`0.85 ** racha_perdidas`).
   - Strictly respect the 15% cluster capital cap (`balance * 0.15`).
   - Strictly cap by Golden Rule 3 (liquidity limit of Top 3 BIDs: `v_bid_top3`).
   - Ensure the calculated stake is formatted to 4-decimal precision (`round(posicion, 4)`).
3. **Strict 4-Decimal Precision (`0.0001`)**:
   - Ensure Win Rate, EV, ROI, Yield, Stake, and Capital are maintained and reported with 4-decimal precision across `continuitis/riesgo_binance.py` and `continuitis/auditor_metricas.py`.
4. **Acceleration Milestones ($10 \to 100 \to 1000$ USD)**:
   - In `continuitis/tesoreria.py`, ensure the $10 \to 100 \to 1000$ growth cycle is properly gated by statistical checks ($N \ge 300, p < 0.05, Z > 1.645$).
5. **Autonomous Harvesting Protocol ($\ge \$1,000$ USD Balance)**:
   - Implement autonomous harvesting method: `ejecutar_cosecha_autonoma(ganancia_neta=None, tipo_cambio_mxn=None)`:
     When balance $\ge \$1,000$ USD, calculate net profit ($B - B_0$), isolate exactly 35% net profit to MXN (`capital_aislado_cosecha_usd` and `capital_aislado_cosecha_mxn`), route 40% of the remainder to operational expenses (`fondo_gastos_operacion_usd`), and retain 60% of the remainder in compound reinvestment.
   - Update `verificar_hitos(auto_cosechar=True)` so that crossing $\ge \$1,000$ automatically executes this harvesting logic.
6. **Financial Test Verification Suite (`pruebas_unitarias/test_r2_exactitud_financiera.py`)**:
   - Create unit tests verifying:
     - Kelly Criterion formula and bounds
     - Streak attenuation ($0.85^n$) and 15% cluster cap
     - Top-3 BIDs liquidity ceiling
     - 4-decimal precision across all financial metrics (Win Rate, EV, ROI, Yield, Stake, Capital)
     - Full simulation of $1,000 USD balance achieving 35% net profit isolation to MXN, 40% expenses, and 60% reinvestment.
7. **Verify and Deliver**:
   - Run tests with pytest. Ensure all M2 unit tests pass 100%.
   - Write `handoff.md` in your working directory and notify parent via `send_message`.


## 2026-10-10T19:51:11Z
You are Worker M2 for the CONTINUITY HFT Binance project.
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m2_gen2
Read your assignment in DISPATCH.md in your working directory, and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md and c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r2\handoff.md.

Your mission: Implement M2 (Autonomous Treasury & Financial Engine) in accordance with PROJECT.md and DISPATCH.md.
Write ownership:
- continuitis/riesgo_binance.py
- continuitis/tesoreria.py
- continuitis/auditor_metricas.py
- pruebas_unitarias/test_r2_exactitud_financiera.py
