## 2026-10-10T18:05:33Z
You are Worker M2 (M2 Treasury & Financials Worker).
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m2
Project root: c:\Users\alanr\AE_ecosistema\CONTINUITYEM

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

MANDATORY: Read these files before beginning work:
1. ORIGINAL_REQUEST.md: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md (specifically headers ## 2026-10-10T17:53:44Z and ## 2026-10-10T18:00:42Z)
2. PROJECT.md: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
3. Explorer 2 Handoff Report: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r2\handoff.md

Your Exclusive Write Ownership:
- continuitis/riesgo_binance.py
- continuitis/tesoreria.py
- continuitis/auditor_metricas.py
- pruebas_unitarias/test_r2_exactitud_financiera.py
(DO NOT write to any files owned by other milestones!)

Milestone M2 Tasks:
1. Refactor `continuitis/riesgo_binance.py`:
   - Implement `calcular_criterio_kelly(self, p_estimada: float, cuota_neta: float, fraccion_kelly: float = 0.25) -> float`:
     Formula: $f^* = \text{fraccion\_kelly} \times \frac{(p \times \text{cuota\_neta}) - 1}{\text{cuota\_neta} - 1.0}$.
     Bounded in $[0.0, 1.0]$, rounded to 4 decimals (`0.0001`).
   - In `calcular_posicion()`, update return dictionary to guarantee 4-decimal precision:
     `"stake": round(posicion_nominal, 4)`,
     `"riesgo_monetario": round(riesgo_real, 4)`.
   - Maintain full support for streak attenuation factor ($0.85^n$), 15% cluster exposure cap, and Top-3 BIDs liquidity ceiling (Golden Rule 3).
2. Refactor `continuitis/tesoreria.py`:
   - Add state tracking attributes:
     `capital_aislado_cosecha_usd: float = 0.0`,
     `capital_aislado_cosecha_mxn: float = 0.0`,
     `fondo_gastos_operacion_usd: float = 0.0`,
     `fondo_reinversion_total_usd: float = 0.0`,
     `cosechas_ejecutadas: list = []`.
   - Implement `ejecutar_cosecha_autonoma(self, ganancia_neta: Optional[float] = None, tipo_cambio_mxn: Optional[float] = None) -> Dict[str, Any]`:
     When balance crosses $\ge \$1,000$ USD:
     - Automatically calculate net profit if not provided (`max(0.0, self.balance - self.balance_inicial)`).
     - Isolate 35% of net profit for harvesting / withdrawal to MXN (`retiro_35 = ganancia_neta * 0.35`, `retiro_mxn = retiro_35 * fx`).
     - Split remaining 65%: 40% (26% total) to operating expenses (`operacion_40`), 60% (39% total) to compound reinvestment (`reinversion_60`).
     - Formal fund isolation: accumulate into `capital_aislado_cosecha_usd`, `capital_aislado_cosecha_mxn`, `fondo_gastos_operacion_usd`, `fondo_reinversion_total_usd`.
     - Update operational balance: `self.balance = round((self.balance - ganancia_neta) + reinversion_60, 4)`.
   - In `verificar_hitos(auto_cosechar: bool = True)`:
     If `self.balance >= UMBRAL_COSECHA_1000` and `auto_cosechar`: automatically call `ejecutar_cosecha_autonoma()`.
3. Refactor `continuitis/auditor_metricas.py`:
   - In `obtener_metricas()` ensure 4-decimal precision on all outputs:
     `"win_rate": round(wr, 4)`,
     `"capital_acumulado": round(cap_acumulado, 4)`,
     `"roi": round(roi, 4)`,
     `"yield": round(rendimiento_yield, 4)`.
4. Create `pruebas_unitarias/test_r2_exactitud_financiera.py`:
   - Test 1 (Acceptance Criterion 3): Test script demonstrating that reaching $1,000 USD balance triggers autonomous isolation of exactly 35% net profit for harvesting to MXN, with 40/60 split of remaining utility.
   - Test 2 (Acceptance Criterion 4): Unit tests for financial formulas (Win Rate, EV, ROI, Position Size, Yield, and Kelly Criterion) asserting exact mathematical correctness with 4-decimal precision (`abs=1e-4`).
   - Test 3: Losing streak attenuation ($0.85^n$) and Top-3 BID liquidity clamp.
5. Run the test suite:
   - `python -m pytest pruebas_unitarias/test_r2_exactitud_financiera.py pruebas_unitarias/test_tesoreria.py pruebas_unitarias/test_metricas.py pruebas_unitarias/test_riesgo_tesoreria_metricas.py -v`
   - Ensure 100% of tests pass.

Write your completion handoff report to:
c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m2\handoff.md

Report back to orchestrator (conversation ID: b660446f-78e3-4243-b28e-49f6b55b2087) with results and test outcomes.
