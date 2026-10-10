# Task Assignment — Remediation Worker (Iteration 2)

## Identity
- Role: teamwork_preview_worker
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_remediation_gen2
- Parent: orchestrator_continuity_gen2

## Mandatory Reading Before Starting Work
You MUST read:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. Challenger reports:
   - `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\challenger_1_gen2\handoff.md`
   - `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\challenger_2_gen2\handoff.md`

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Write Ownership Boundaries
You have exclusive write access to:
- `continuitis/state_registry.py`
- `continuitis/riesgo_binance.py`

## Defects to Remediate
1. **IEEE-754 NaN/Inf Vulnerability in `continuitis/riesgo_binance.py`**:
   - In `calcular_criterio_kelly(p_estimada, cuota_neta, fraccion_kelly)`:
     Add immediate check:
     ```python
     if (
         math.isnan(p_estimada)
         or math.isinf(p_estimada)
         or math.isnan(cuota_neta)
         or math.isinf(cuota_neta)
     ):
         return 0.0
     ```
   - In `EscudoFinancieroBinance.calcular_posicion`:
     Check if `p_estimada` or `cuota` is NaN or Inf. If so, fail-closed: return dictionary with `operar: False`, `motivo: "PROBABILIDAD_O_CUOTA_INVALIDA"`, `stake: 0.0`, `ev: 0.0`, `cuota_neta: 0.0`, `factor_racha: 1.0`, `riesgo_monetario: 0.0`, `f_star_kelly: 0.0`.
   - In `EscudoFinancieroBinance.evaluar_propuesta`:
     Check if `proposal.estimated_prob` or `proposal.payout_decimal` is NaN or Inf. If so, return `RiskDecision(approved=False, reason="PROBABILIDAD_O_CUOTA_INVALIDA", quantity=0.0, ...)`.
2. **Type Safety Crash in `continuitis/state_registry.py:cerrar_partido`**:
   - In `cerrar_partido(partido_id, trade_result)`:
     Replace any `float(trade_result.get("pnl", 0.0))` with safe null-coalescing:
     ```python
     pnl_val = 0.0
     if trade_result and trade_result.get("pnl") is not None:
         try:
             pnl_val = float(trade_result["pnl"])
         except (ValueError, TypeError):
             pnl_val = 0.0
     ```
     Ensure the same safe handling for `stake` and `timestamp`.

## Verification Instructions
1. Run `python -m pytest pruebas_unitarias/test_adversarial_challenger_gen2.py pruebas_unitarias/test_adversarial_challenger_2_gen2.py -v`.
   Ensure all 31 tests in `test_adversarial_challenger_gen2.py` (including the previously xfailed NaN test) and all 22 tests in `test_adversarial_challenger_2_gen2.py` pass cleanly!
2. Run `python -m pytest pruebas_unitarias/test_e2e_acceptance_criteria.py -v`.
3. Run `python -m pytest pruebas_unitarias/test_r1_gcp_redis_bigtable.py pruebas_unitarias/test_r2_exactitud_financiera.py pruebas_unitarias/test_r3_hft_amm_ev.py -v`.
4. Write `handoff.md` in your working directory and notify the parent orchestrator via `send_message`.


## 2026-10-10T20:37:06Z
You are the Remediation Worker for CONTINUITY HFT Binance (Iteration 2).
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_remediation_gen2
Read DISPATCH.md in your working directory and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md and the handoff reports of Challenger 1 and Challenger 2.

Your mission: Remediate the two defects found by the challengers:
1. In continuitis/riesgo_binance.py:
   - In calcular_criterio_kelly: if math.isnan(p_estimada) or math.isinf(p_estimada) or math.isnan(cuota_neta) or math.isinf(cuota_neta), return 0.0.
   - In EscudoFinancieroBinance.calcular_posicion: if math.isnan(p_estimada) or math.isinf(p_estimada) or math.isnan(cuota) or math.isinf(cuota), return operar: False, motivo: "PROBABILIDAD_O_CUOTA_INVALIDA", stake: 0.0, ev: 0.0, etc.
   - In EscudoFinancieroBinance.evaluar_propuesta: if math.isnan(proposal.estimated_prob) or math.isinf(proposal.estimated_prob) or math.isnan(proposal.payout_decimal) or math.isinf(proposal.payout_decimal), return RiskDecision(approved=False, reason="PROBABILIDAD_O_CUOTA_INVALIDA", quantity=0.0).
2. In continuitis/state_registry.py:
   - In cerrar_partido: safe null-coalescing on trade_result.get("pnl"), trade_result.get("stake"), and trade_result.get("timestamp") so that None values do not trigger TypeError when calling float().

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Run pytest on test_adversarial_challenger_gen2.py, test_adversarial_challenger_2_gen2.py, test_e2e_acceptance_criteria.py, and test_r1/r2/r3 suites.
Write handoff.md in your working directory and notify the parent orchestrator via send_message.
