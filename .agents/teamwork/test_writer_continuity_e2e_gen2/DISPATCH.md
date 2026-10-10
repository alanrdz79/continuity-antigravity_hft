# Task Assignment — E2E Test Writer (Comprehensive 4-Tier Test Suite)

## Identity
- Role: teamwork_preview_test_writer
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\test_writer_continuity_e2e_gen2
- Parent: orchestrator_continuity_gen2
- Milestone: E2E Testing Track — Acceptance Verification Suite

## Mandatory Reading Before Starting Work
You MUST read the following files before writing any tests:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\TEST_INFRA.md`

## Write Ownership Boundaries
You have exclusive write access ONLY to the following files:
- `pruebas_unitarias/test_e2e_acceptance_criteria.py` (and any auxiliary test files needed under `pruebas_unitarias/`)
- `TEST_READY.md` (at project root when complete)
DO NOT write to implementation code files (e.g., `continuitis/`, `estrategias/`, `orquestadores_principales/`).

## Detailed Requirements to Implement
1. **Opaque-Box & Requirement-Driven**:
   - Construct test cases strictly from the 19 features in `PROJECT.md` and the 7 acceptance criteria in `TEST_INFRA.md`.
2. **Implement 4-Tier Test Suite in `pruebas_unitarias/test_e2e_acceptance_criteria.py`**:
   - **Tier 1 (Feature Coverage)**: Happy-path isolated tests for all features (Redis StateRegistry, match queue, Bigtable row key format, SQLite elimination, Docker boot, Kelly criterion, position sizing, 4-decimal precision, $10->$100->$1000 acceleration, $1000 harvesting, HFT Phase 1, Phase 2, Phase 3, Phase 4, Pre-match & In-play EV early exits, Strategy V binary parity, Strategy V curve deviation, orchestrator integration).
   - **Tier 2 (Boundary & Corner Cases)**: Edge cases, zero balances, zero depths, extreme loss streaks, exact 4-decimal bounds, boundary timestamps, T-5m boundary, fee bounds.
   - **Tier 3 (Cross-Feature Combinations)**: Multi-component interactions (StateRegistry + risk engine, Phase 2 cancellation + balance check, EV exit + treasury update).
   - **Tier 4 (Real-World Application Scenarios)**: Full lifecycle simulation across Sports and ESports, autonomous harvesting at $1,000 balance, crash-loop resilience.
3. **Dedicated Acceptance Criteria Tests**:
   - AC1: Docker container run & SQLite elimination (no `.db` files generated).
   - AC2: Orchestrator Redis connection with environment variable `REDIS_HOST`.
   - AC3: Autonomous harvesting at $1,000 USD balance isolating 35% net profit to MXN, 40% expenses, 60% reinvestment.
   - AC4: Unit tests for financial formulas (Win Rate, EV, ROI, Stake, Yield, Kelly) verifying 4-decimal precision (`0.0001`).
   - AC5: Phase 2 cancellation at T-5m verifying 0% exposure.
   - AC6: Strategy V binary parity arbitrage generating atomic `DualBuyProposal`.
   - AC7: Pre-match and in-play EV early exits (`_vigilar_y_cerrar_posiciones_abiertas`) across Sports & ESports.
4. **Publish `TEST_READY.md`**:
   - When the test suite is constructed and verified, create `TEST_READY.md` at project root with runner commands, test counts, and coverage summary.
5. **Verify and Deliver**:
   - Ensure tests are syntactically sound, self-contained, and run cleanly via `pytest`.
   - Write `handoff.md` and send message to parent orchestrator.


## 2026-10-10T19:51:11Z
You are the E2E Test Writer for the CONTINUITY HFT Binance project.
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\test_writer_continuity_e2e_gen2
Read your assignment in DISPATCH.md in your working directory, and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md and TEST_INFRA.md.

Your mission: Construct the requirement-driven 4-tier E2E acceptance test suite covering all 19 features and 7 acceptance criteria in pruebas_unitarias/test_e2e_acceptance_criteria.py, and publish TEST_READY.md at project root.
Write ownership:
- pruebas_unitarias/test_e2e_acceptance_criteria.py
- TEST_READY.md

Run tests using pytest to ensure syntactic soundness. Write handoff.md in your working directory and notify the parent orchestrator via send_message when complete.
