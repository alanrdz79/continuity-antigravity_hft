# Task Assignment — Worker M1 (GCP State Migration & SQLite Elimination)

## Identity
- Role: teamwork_preview_worker
- Working Directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m1_gen2
- Parent: orchestrator_continuity_gen2
- Milestone: M1 — GCP State Migration & SQLite Elimination (Requirement R1)

## Mandatory Reading Before Starting Work
You MUST read the following files before writing any code:
1. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md`
2. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md`
3. `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r1\handoff.md`

## Write Ownership Boundaries
You have exclusive write access ONLY to the following files:
- `continuitis/state_registry.py`
- `continuitis/financiero.py`
- `continuitis/memoria_hft.py`
- `Dockerfile`
- `requirements.txt`
- `pruebas_unitarias/test_r1_gcp_redis_bigtable.py` (unit test suite for M1)
DO NOT write to or modify any other files (e.g., `continuitis/riesgo_binance.py`, `tesoreria.py`, `arbitraje_amm.py`, or `HFT_BINANCE.py`).

## Mandatory Integrity Warning
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

## Detailed Requirements to Implement
1. **Eliminate SQLite Dependencies**:
   - Remove all SQLite database creation, locks, and `.db` files (`continuity_state.db`, `hft.db`, `cerebrillum.db`, `metricas_hft.sqlite`).
   - Refactor `continuitis/state_registry.py` to use Cloud Memorystore (Redis) for live state (`balance`, `racha_perdidas`, `kill_switch`) and pending match queue (`cola_partidos_pendientes`).
   - Implement `encolar_partido(partido_id, payload)`, `obtener_partidos_pendientes()`, and `cerrar_partido(partido_id, trade_result)` in `StateRegistry`.
   - Implement historical trade logging in Cloud Bigtable using reverse-timestamp lexicographical row keys:
     `{symbol}#{Long.MAX_VALUE - timestamp_micros:019d}#{seq_id:010d}`
   - Provide transparent in-memory mock fallback in `StateRegistry` when Redis / Bigtable hosts or credentials are not configured, so tests run cleanly without external dependencies.
2. **Refactor `continuitis/financiero.py`**:
   - Replace any SQLite queries to `cola_partidos_pendientes` in `ControladorCluster.factor_cluster` with calls to `StateRegistry.obtener_partidos_pendientes()`.
3. **Refactor `continuitis/memoria_hft.py`**:
   - Remove SQLite storage; keep fast in-memory storage (with Redis backup if configured).
4. **Update `Dockerfile` and `requirements.txt`**:
   - Add `redis` and `google-cloud-bigtable` to `requirements.txt`.
   - Verify `Dockerfile` runs as non-root `appuser` (UID 10001) with `REDIS_HOST` environment variable support and without any `sqlite3.OperationalError` file lock crashes.
5. **Create Unit Tests in `pruebas_unitarias/test_r1_gcp_redis_bigtable.py`**:
   - Test Redis state operations, queue operations (`cola_partidos_pendientes`), Bigtable row key format, in-memory fallback, and zero `.db` file generation.
6. **Verify and Deliver**:
   - Run tests with pytest. Ensure all M1 tests pass 100%.
   - Write `handoff.md` in your working directory and notify parent via `send_message`.


## 2026-10-10T19:51:11Z
From: 0b1e3aa7-d71b-46b4-8e54-43600e417893
Priority: MESSAGE_PRIORITY_HIGH
Content: You are Worker M1 for the CONTINUITY HFT Binance project.
Your working directory is: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_continuity_m1_gen2
Read your assignment in DISPATCH.md in your working directory, and read ORIGINAL_REQUEST.md at c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md.
Also read PROJECT.md and c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r1\handoff.md.

Your mission: Implement M1 (GCP State Migration & SQLite Elimination) in accordance with PROJECT.md and DISPATCH.md.
Write ownership:
- continuitis/state_registry.py
- continuitis/financiero.py
- continuitis/memoria_hft.py
- Dockerfile
- requirements.txt
- pruebas_unitarias/test_r1_gcp_redis_bigtable.py

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Run build and test verification using pytest. Write handoff.md in your working directory and notify the parent orchestrator via send_message when complete.
