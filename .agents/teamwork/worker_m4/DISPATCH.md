# Dispatch: Worker M4 — Interactive Telegram Bot & Main Continuous Orchestrator

Read ORIGINAL_REQUEST.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\ORIGINAL_REQUEST.md
Read PROJECT.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PROJECT.md
Read PLANnew.md at: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md

Files you own exclusively:
- `conectores/telegram_bidireccional.py`
- `orquestadores_principales/HFT_BINANCE.py`
- `pruebas_unitarias/test_orquestador_binance.py`

Deliverables:
1. `conectores/telegram_bidireccional.py`:
   - Interactive bidirectional Telegram bot module with:
     * Inline keyboard layout (Reanudar/Pausar, KILL SWITCH, Reporte Métricas, Gráfica, Parámetros, Tesorería).
     * Command routing: `/start`, `/status`, `/kill` (panic switch with immediate pause), `/pause`, `/resume`, `/risk <param> <val>`, `/report` (telemetry string), `/harvest`.
     * `MockTelegramClient`: Test simulator for headless test environments.
     * Autonomous push notifications: startup, 3-6h interval summaries, daily close, emergency circuit breaker alerts.
2. `orquestadores_principales/HFT_BINANCE.py`:
   - Main continuous async orchestrator class `ContinuityHFTBinanceOrchestrator`:
     * Coordinates `BinanceAsyncConnector`, `MicroestructuraBinanceEngine`, `EscudoFinancieroBinance`, `TesoreriaBinance`, `AuditorMetricas`, `HFTEngine`, `SwingEngine`, and `TelegramBidireccionalBot`.
     * Manages async pipeline tasks (`OrderBookListenerTask`, `HFTStrategyTask`, `SwingStrategyTask`, `TelegramListenerTask`).
     * Real-time metrics streaming, atomic capital reservations, and clean shutdown handling.
3. `pruebas_unitarias/test_orquestador_binance.py`:
   - Verification suite validating end-to-end orchestration, task coordination, and command responses.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A teamwork_preview_auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\worker_m4
Write your report to `report.md` and deliver `handoff.md` in your working directory. Send a message to parent when complete.

## 2026-10-07T04:16:31Z
Received assignment from parent f2f51f43-3860-4c33-b19f-c0b7ef73f3b6. Task started.


## 2026-10-07T04:18:41Z
Received directive from parent f2f51f43-3860-4c33-b19f-c0b7ef73f3b6:
The user requires cloud deployment support on Google Cloud Platform (GCP) optimized for ultra-low latency with Binance Spot:
1. Target GCP Region: Tokyo (`asia-northeast1`), co-located / adjacent to Binance Spot matching engines in Tokyo (`ap-northeast-1`).
2. Deployment artifacts: Ensure `Dockerfile`, `cloud-init.yaml`, and systemd service files (`continuity-hft.service`) are created with Linux/GCP networking optimizations (TCP tuning, CPU pinning, low-latency kernel parameters).
Action: Incorporate these deployment files into deliverables.
