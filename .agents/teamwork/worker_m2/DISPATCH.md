# Dispatch: Worker M2 — Risk Engine, Automated Treasury & Metrics Auditor

## 2026-10-07T03:59:10Z
From: parent (f2f51f43-3860-4c33-b19f-c0b7ef73f3b6)
You are teamwork_preview_worker (Worker M2).
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m2
Your task assignment is in: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m2\DISPATCH.md

MANDATORY: Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Files you own exclusively:
- continuitis/riesgo_binance.py
- continuitis/tesoreria.py
- continuitis/auditor_metricas.py

Deliverables:
1. continuitis/riesgo_binance.py:
   - Expected Value (EV) calculation net of BNB fee discount: EV = (P_estimada * Cuota_neta) - 1.0 >= 0.015.
   - Real Position Sizing formula: S_nominal = (B * pct_riesgo_fijo * factor_racha) / max(pct_stop_loss, 0.01).
   - Losing streak attenuation: factor_racha = 0.85^streak, reset to 1.0 on win.
   - Cluster exposure cap: <= 15% of bankroll simultaneously committed across active cluster.
   - Golden Rule 3: Dynamic sizing bounded by available volume in top 3 BID levels (S <= sum V_Bid^(1..3)) to guarantee emergency exit liquidity.
2. continuitis/tesoreria.py:
   - "Ordeño e Inyección" capital progression ($10 -> 100 -> 1,000 USD).
   - $10 -> 100 USD capital injection (+100 USD event) gated by validation (N >= 300, p < 0.05, EV > 0).
   - Acceleration phase (<$1,000): monthly profit split (40% operating, 60% compound reinvestment).
   - Autonomous harvest (>= $1,000): 35% monthly profit harvest to MXN, remainder split 40/60.
3. continuitis/auditor_metricas.py:
   - Accurate continuous analytical metrics: Win Rate (WR), Accumulated Capital (B_N = B_0 * prod(1 + f_i * R_i)), ROI (sum PnL / B_0), Yield on turnover (sum PnL / sum S_i), Total Trades (N).
   - Statistical validation gate: Z = (WR - 0.50) / (0.50 / sqrt(N)), p-value < 0.05 <=> Z > 1.645.
4. Verify your work by running Python syntax checks or unit tests.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Write report.md and deliver handoff.md in your working directory. Send a message to parent when complete.
