# Task Assignment — Challenger 1 (Adversarial Stress Verification)

## Identity
- Role: teamwork_preview_challenger
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\challenger_1_gen2
- Parent: orchestrator_continuity_gen2

## Mandatory Reading Before Starting Work
You MUST read:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\TEST_INFRA.md`
4. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\TEST_READY.md`

## Mission & Instructions
1. As an adversarial verifier, write oracles and stress tests to empirically verify:
   - Bigtable reverse-timestamp row key sorting math under extreme microsecond timestamps and seq_ids.
   - Zero SQLite file generation under heavy concurrent state operations.
   - Kelly Criterion boundary extremes ($p \to 0$, $p \to 1$, extreme odds, $f^* \le 0.25$).
   - Streak factor attenuation ($0.85^n$) at $n=0, 1, 10, 50$ and 15% cluster cap invariance.
   - Autonomous harvesting at $1,000 balance with exact 35% net profit isolation to MXN.
   - Strategy V `DualBuyProposal` generation when `Ask(YES) + Ask(NO) < 1.00 - fees`.
   - Pre-match and in-play Target EV early exits (`_vigilar_y_cerrar_posiciones_abiertas`) across Sports & ESports.
   - Phase 2 T-5m `limpiar_mesa` verifying 0% exposure.
2. Execute your verification scripts using python/pytest.
3. Deliver verdict: `APPROVE` or `REQUEST_CHANGES`.
4. Write `handoff.md` in your working directory and notify the parent orchestrator via `send_message`.

## 2026-10-10T20:24:41Z
You are Challenger 1 for CONTINUITY HFT Binance.
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\challenger_1_gen2
Read DISPATCH.md in your working directory and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md, TEST_INFRA.md, and TEST_READY.md.

Adversarially stress test the system: Bigtable row key math, Kelly boundary extremes, streak attenuation 0.85^n, 15% cluster cap, autonomous harvesting at $1000 balance with 35% MXN, Strategy V DualBuyProposal, pre-match and in-play EV early exits.
Execute verification scripts via pytest.
Deliver your verdict: APPROVE or REQUEST_CHANGES.
Write handoff.md in your working directory and notify the parent orchestrator via send_message.
