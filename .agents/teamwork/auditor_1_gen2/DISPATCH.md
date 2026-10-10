# Task Assignment — Forensic Auditor (Integrity Forensics)

## Identity
- Role: teamwork_preview_auditor
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\auditor_1_gen2
- Parent: orchestrator_continuity_gen2

## Mandatory Reading Before Starting Work
You MUST read:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\TEST_INFRA.md`
4. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\TEST_READY.md`

## Mission & Instructions
Perform an exhaustive forensic audit on the codebase across M1, M2, and M3:
1. **Static Analysis & Anti-Cheat Forensics**:
   - Verify that NO test results, expected values, or assertions are hardcoded in source code (`continuitis/`, `estrategias/`, `orquestadores_principales/`).
   - Verify that there are NO dummy or facade implementations (e.g. methods returning mock true or constant strings).
   - Verify that SQLite was genuinely eliminated and not merely renamed or hidden. Check imports and database calls.
   - Verify that `StateRegistry` has genuine Redis and Bigtable client logic with reverse-timestamp keys.
   - Verify that Kelly Criterion and Position Sizing formulas are genuine mathematical implementations.
   - Verify that Autonomous Harvesting genuinely calculates net profit and isolates 35% to MXN in account variables.
   - Verify that `_vigilar_y_cerrar_posiciones_abiertas` genuinely checks `best_bid >= target_exit_price` or timeout and executes close orders.
   - Verify that Strategy V genuinely checks `Ask(YES) + Ask(NO) < 1.00 - fees` and returns `DualBuyProposal`.
2. **Runtime Verification**:
   - Run tests: `pytest pruebas_unitarias/test_e2e_acceptance_criteria.py -v`.
   - Run tests: `pytest pruebas_unitarias/test_r1_gcp_redis_bigtable.py pruebas_unitarias/test_r2_exactitud_financiera.py pruebas_unitarias/test_r3_hft_amm_ev.py -v`.
3. Deliver verdict: `CLEAN` or `INTEGRITY VIOLATION`.
   (Note: If any hardcoding, facade, or dummy logic is found, report `INTEGRITY VIOLATION` with full evidence).
4. Write `handoff.md` in your working directory and notify parent orchestrator via `send_message`.


## 2026-10-10T20:24:42Z
[Message] sender=0b1e3aa7-d71b-46b4-8e54-43600e417893
You are the Forensic Auditor for CONTINUITY HFT Binance.
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\auditor_1_gen2
Read DISPATCH.md in your working directory and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md, TEST_INFRA.md, and TEST_READY.md.

Perform an exhaustive integrity forensic audit: check for hardcoded test values, dummy/facade implementations, genuine SQLite elimination, genuine Redis/Bigtable StateRegistry logic, genuine Kelly and position sizing math, genuine 35% MXN harvesting accounting, genuine pre-match and in-play EV early exits, and genuine Strategy V DualBuyProposal.
Run runtime test execution.
Deliver your verdict: CLEAN or INTEGRITY VIOLATION.
Write handoff.md in your working directory and notify the parent orchestrator via send_message.
