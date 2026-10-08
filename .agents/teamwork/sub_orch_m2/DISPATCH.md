# Dispatch: Milestone 2 Sub-Orchestrator

Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Scope: Milestone 2 — Risk Engine, Automated Treasury & Metrics Auditor
Files owned exclusively:
- `continuitis/riesgo_binance.py`
- `continuitis/tesoreria.py`
- `continuitis/auditor_metricas.py`

Deliverables:
1. `continuitis/riesgo_binance.py`:
   - Expected Value ($EV$) calculation net of BNB fee discount: $EV = (P_{\text{estimada}} \times \text{Cuota}_{\text{neta}}) - 1.0 \ge 0.015$.
   - Real Position Sizing formula: $S_{\text{nominal}} = \frac{B \times \text{pct\_riesgo\_fijo} \times \text{factor\_racha}}{\max(\text{pct\_stop\_loss}, 0.01)}$.
   - Losing streak attenuation: $\text{factor\_racha} = 0.85^{\text{consecutive\_losses}}$, reset on win.
   - Cluster exposure cap: $\le 15\%$ of bankroll simultaneously committed across active cluster.
   - Golden Rule 3: Dynamic sizing bounded by available volume in top 3 BID levels ($S \le \sum_{k=1}^3 V_{\text{Bid}}^{(k)}$) to guarantee emergency exit liquidity.
2. `continuitis/tesoreria.py`:
   - "Ordeño e Inyección" capital progression ($10 \to 100 \to 1,000$ USD).
   - $10 \to 100\text{ USD}$ capital injection (+100 USD event) gated by validation ($N \ge 300$, $p < 0.05$, $EV > 0$).
   - Acceleration phase (<$1,000): monthly profit split (40% operating, 60% compound reinvestment).
   - Autonomous harvest ($\ge $1,000): 35% monthly profit harvest to MXN, remainder split 40/60.
3. `continuitis/auditor_metricas.py`:
   - Accurate continuous analytical metrics: Win Rate ($WR$), Accumulated Capital ($B_N = B_0 \prod (1 + f_i R_i)$), ROI ($\sum \text{PnL} / B_0$), Yield on turnover ($\sum \text{PnL} / \sum S_i$), Total Trades ($N$).
   - Statistical validation gate: $Z = \frac{WR - 0.50}{0.50 / \sqrt{N}}$, $p$-value $< 0.05 \iff Z > 1.645$.
4. Unit verification tests for M2 components ensuring 100% build and test pass.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\sub_orch_m2
Follow standard orchestrator iteration loop (Explorer -> Worker -> Reviewer -> Challenger -> Auditor -> Gate) and report back with handoff.md.
