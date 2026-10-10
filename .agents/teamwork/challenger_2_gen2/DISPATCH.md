# Task Assignment — Challenger 2 (Adversarial Stress Verification)

## Identity
- Role: teamwork_preview_challenger
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\challenger_2_gen2
- Parent: orchestrator_continuity_gen2

## Mandatory Reading Before Starting Work
You MUST read:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\TEST_INFRA.md`
4. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\TEST_READY.md`

## Mission & Instructions
1. Stress test concurrency, race conditions, and precision edge cases:
   - Concurrency stress on `StateRegistry` (simultaneous reads/writes/enqueues/dequeues).
   - Strict 4-decimal precision float rounding invariance on financial metrics (`round(..., 4)` vs IEEE 754 floating point drift).
   - Orchestrator multi-loop lifecycle in `HFT_BINANCE.py` with mock client under simulated market updates and `/kill` signal.
   - Target EV exit edge cases (spread $= 0$, best bid exactly equals target exit price, timeout expiration).
2. Execute tests with python/pytest.
3. Deliver verdict: `APPROVE` or `REQUEST_CHANGES`.
4. Write `handoff.md` in your working directory and notify the parent orchestrator via `send_message`.


## 2026-10-10T20:24:41Z
[Message] timestamp=2026-10-10T20:24:41Z sender=0b1e3aa7-d71b-46b4-8e54-43600e417893 priority=MESSAGE_PRIORITY_HIGH content=You are Challenger 2 for CONTINUITY HFT Binance.
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\challenger_2_gen2
Read DISPATCH.md in your working directory and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md, TEST_INFRA.md, and TEST_READY.md.

Stress test concurrency, race conditions, precision edge cases: StateRegistry concurrency, strict 4-decimal precision float rounding invariance, orchestrator multi-loop lifecycle in HFT_BINANCE.py, EV exit timing and zero-spread boundaries.
Execute verification scripts via pytest.
Deliver your verdict: APPROVE or REQUEST_CHANGES.
Write handoff.md in your working directory and notify the parent orchestrator via send_message.
