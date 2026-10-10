# Handoff Report — Requirement R3: Orquestación de las 4 Fases HFT, Estrategia V y Cierre por Valor Esperado (Deportes y ESports)

**Date**: 2026-10-10  
**Agent**: Explorer 3 (`explorer_continuity_r3`)  
**Parent Orchestrator ID**: `b660446f-78e3-4243-b28e-49f6b55b2087`  
**Mission**: In-depth survey of the codebase regarding Requirement R3, incorporating the new directive regarding pre-match and in-play operations with early EV-driven closures across Sports and ESports.

---

## 1. Observation

Direct inspection of the codebase and test runs yielded the following concrete observations:

### Observation 1.1: Core Mathematical & Microstructural Engines
- **`estrategias/hft_engine.py` (1491 lines)**:
  - **Fase 1 (Pre-Match OBI Scalping)**: lines 323–466 (`evaluar_fase_1_prematch_obi`), checks `5.0 <= time_to_ko <= 120.0`, requires $I \ge 0.60$ (dominancia compradora $\ge 80\%$), spread $\le \$0.03$, entrada Maker en `Best Bid + 1 tick`, y calcula el precio objetivo de salida en `Best Ask + 2 ticks` (`target_exit_price`). Registra posición con temporizador de exposición rápida de 2 a 10s.
  - **Fase 2 (Transición T-5m / limpiar_mesa)**: lines 471–534 (`ejecutar_fase_2_limpiar_mesa`), cancela atómicamente órdenes en `self.pending_orders`, liquida a mercado en Best Bid las posiciones abiertas en `self.active_positions`, y verifica `exposicion_final_pct = 0.0` y `liquidez_usdt_pct = 100.0`.
  - **Fase 3 (In-Play Latency Sniping)**: lines 538–680 (`snipe_desfase_oraculo`), detecta eventos oraculares críticos (gol, tarjeta roja, first blood) antes de la suspensión del libro (`MarketStatus: SUSPENDED`), evalúa spread $\le \$0.03$, y compra el Ask desactualizado con salida objetivo en `best_ask + 0.10` y timeout de 30s.
  - **Fase 4 (Time Decay Scalp)**: lines 684–869 (`evaluar_fase_4_time_decay_scalping`), compra share de empate en minutos 75–90 cuando el índice de peligro $\le 0.20$ ataques/min, fija `target_exit_price = precio_entrada + 0.02`, y define timeout estricto de 60 a 90 segundos (`auditar_timeouts` ejecuta salida a mercado sin esperar el fin del evento).
  - **Estrategia A (Time Decay 65–70 min)**: lines 873–1043, retención de 3 a 5 min en juego estancado, venta anticipada al capturar el tick de tiempo.
  - **Estrategia B (Caza de Sobre-Reacciones)**: lines 1047–1280, compra de dip por pánico en favorito dominante y venta en rebote tras la primera jugada peligrosa a favor, **sin esperar a que anote gol**.
  - **Cobertura Multideporte y ESports**: lines 67–170, enum `SportType` incluye `SOCCER`, `BASEBALL`, `AMERICAN_FOOTBALL`, `BASKETBALL`, `TENNIS`, `HOCKEY` y `ESPORTS` (configurado con duración estándar de 35.0 min, umbral de peligro 0.25, ventana Estrategia A min 22–26, y ventana Fase 4 min 28–35).

- **`estrategias/arbitraje_amm.py` (907 lines)**:
  - **Estrategia V (Paridad Binaria Determinista)**: lines 253–330 (`detectar_paridad_binaria`), detecta ineficiencias terminales cuando `Best Ask(YES) + Best Ask(NO) < 1.00 - fees_totales`.
  - **Ejecución Dual Atómica**: lines 526–658 (`ejecutar_arbitraje_paridad`), compra dual simultánea con cantidades idénticas (`quantities = {yes: qty, no: qty}`), guardián de latencia rígido $\le 2.5\text{s}$, y techo de clúster del 15%.
  - **Desviación de Curva AMM**: lines 335–431 (`detectar_desviacion_curva`), adquiere el contrato infravalorado respecto a $P_{fair}$ externa con salida scalp en 2 a 15 segundos hacia el target de rebote `entry_price + (p_fair - entry_price) * 0.70`.

- **Test Suites Status**:
  - `python -m pytest pruebas_unitarias/test_hft.py pruebas_unitarias/test_arbitraje_amm.py pruebas_unitarias/test_estrategias_hft_swing.py pruebas_unitarias/test_microestructura_binance.py pruebas_unitarias/test_golden_rules.py -v`: **103 PASSED in 3.76s** (0 failures).

### Observation 1.2: Pre-Match ("Antes") and In-Play ("Durante") EV-Driven Exits Mechanism
- The user directive states: *"que haga operaciones y cierre antes y durante al cumplir con el valor esperado asegurate de eso de los eventos deportivos y deESports"*
- In `estrategias/hft_engine.py`:
  - **Pre-match ("antes")**:
    - Las posiciones de Fase 1 nacen con `target_exit_price = Best Ask + 2 ticks` y `timeout_seconds = 2.0 a 10.0s`. Si en el libro el Best Bid sube alcanzando el target de EV, o expira el timeout, la posición debe cerrarse de inmediato con ganancia sin esperar al inicio del partido.
    - Fase 2 a T-5m ejecuta `ejecutar_fase_2_limpiar_mesa`, liquidando cualquier saldo remanente a 0% de exposición antes del minuto cero.
  - **In-play ("durante")**:
    - Las posiciones de Fase 3 fijan target de normalización (`best_ask + 0.10`) y timeout 30s.
    - Las posiciones de Fase 4 compran empate y liquidan a mercado tras 60–90 segundos (`auditar_timeouts`), **sin esperar al silbatazo final ni conclusión del partido**.
    - Las posiciones de Estrategia A compran empate/resultado actual y liquidan tras 3–5 minutos, **antes del final del partido**.
    - Las posiciones de Estrategia B liquidan en el primer ataque peligroso favorable, **sin esperar a que concluya el partido ni que anote gol**.
    - Las posiciones de Estrategia V de curva liquidan en rebote (`SCALP_BOUNCE`) o expiración de 2 a 15s (`SCALP_TIMEOUT`), **sin esperar al fin del evento**.
  - **ESports Adaptation**:
    - En ESports (LoL, CS2, Dota 2), las partidas duran típicamente ~30–35 minutos. Las ventanas operativas están adaptadas en `SPORT_CONFIGS[SportType.ESPORTS]` (inicio Fase 4 en minuto 28), y los timeouts son ultrarrápidos (2 a 10s pre-match, 60s in-play).

### Observation 1.3: Architectural Gaps & Orchestrator Regressions in `HFT_BINANCE.py`
In `orquestadores_principales/HFT_BINANCE.py`:
1. **Critical Missing Method (`_vigilar_y_cerrar_posiciones_abiertas`)**:
   Line 456 calls:
   ```python
   await self._vigilar_y_cerrar_posiciones_abiertas(symbol, snap)
   ```
   This method is **nowhere defined** in the file! Because it is missing, `step_hft_cycle` crashes with `AttributeError`. Furthermore, **this missing method is the exact mechanism responsible for auditing whether open positions have reached their target EV or expired their timeouts and closing them before or during the match**!
2. **Phase 2 Bypass at T-5m**:
   Line 460 branches:
   ```python
   if match_state.is_prematch:
       senal = self.hft_engine.evaluar_fase_1_prematch_obi(...)
   ```
   When `time_to_kickoff_minutes <= 5.0`, `is_prematch` is True, but `evaluar_fase_1_prematch_obi` rejects (`time_to_ko < 5.0`). Therefore, `ejecutar_fase_2_limpiar_mesa` is never executed in the orchestrator loop.
3. **Phase 2 Exchange Execution Missing**:
   Lines 478–508 only handle buy orders. When `senal.action == "CLEANUP"`, the orchestrator does not invoke `await self.binance_client.cancel_all_orders(symbol)` or market sell liquidations on the exchange.
4. **Strategy V Not Integrated**:
   `estrategias.arbitraje_amm` is neither imported nor wired into `ContinuityHFTBinanceOrchestrator`.
5. **Phase 3 Omitted in `HFTEngine.procesar_mercado`**:
   In `estrategias/hft_engine.py:1378–1407`, `snipe_desfase_oraculo` is never dispatched during live market ticks.
6. **Strategy V Proposal Contract**:
   `ArbitrageSignal` lacks a dedicated `DualBuyProposal` dataclass containing atomic `OrderProposal` objects for YES and NO contracts to satisfy Acceptance Criterion 2 unambiguously.
7. **Broken Orchestrator Unit Tests**:
   Due to attributes removed in commit `b653d9f` (`capital_gateway`, `swing_engine`, `step_swing_cycle`, `_tasks`), 10 tests in `test_orquestador_binance.py` fail.

---

## 2. Logic Chain

1. **Premise 1: Pre-Match and In-Play EV Exits (Sports & ESports)**:
   - *Requirement*: The system must open and close positions pre-match ("antes") and in-play ("durante") the moment target EV is reached, without waiting for the event to finish, across Sports and ESports.
   - *Logic*: In `HFTEngine`, every opened position records `target_exit_price` and `timeout_seconds`.
     - In Pre-match: Phase 1 captures spread EV in 2–10s Maker exit; Phase 2 guarantees 0% exposure at T-5m.
     - In-play: Phase 4 liquidates after 90s; Strategy A after 3–5 min; Strategy B on first dangerous attack; Strategy V in 2–15s on bounce.
     - In ESports: `SportType.ESPORTS` scales these windows to 35-minute match durations.
   - *Root Cause of Missing Live Execution*: The orchestrator calls `_vigilar_y_cerrar_posiciones_abiertas` on line 456, but this method was never written! Implementing this method to evaluate:
     `(best_bid >= pos.target_exit_price)` OR `(now - pos.entry_time >= pos.timeout_seconds)`
     and execute the exit immediately closes positions as soon as target EV is reached, satisfying the directive.

2. **Premise 2: Acceptance Criterion 1 (Phase 2 at T-5m)**:
   - *Requirement*: Phase 2 programmatically verifies order cancellation at T-5m with 0% exposure.
   - *Logic*: `HFTEngine.ejecutar_fase_2_limpiar_mesa` returns `{"exposicion_final_pct": 0.0, "liquidez_usdt_pct": 100.0, "regla_innegociable_cumplida": True}`. By changing line 460 in `HFT_BINANCE.py` to call `evaluar_mercado_completo(...)` (which invokes Phase 2 when `time_to_ko <= 5.0`), and executing `binance_client.cancel_all_orders(symbol)`, Criterion 1 is programmatically verified end-to-end.

3. **Premise 3: Acceptance Criterion 2 (Strategy V Dual Buy Proposal)**:
   - *Requirement*: Strategy V detects `Ask(YES) + Ask(NO) < 1.00 - fees` and generates dual buy atomic proposal.
   - *Logic*: `detectar_paridad_binaria` already detects `sum_asks + fees < 1.00`. Defining an explicit `DualBuyProposal` dataclass and attaching it to `ArbitrageSignal` satisfies Criterion 2 with complete syntactic rigor.

4. **Premise 4: Complete Lifecycle Unification**:
   - Connecting `snipe_desfase_oraculo` in `procesar_mercado` when `match_state.last_event` is fresh (<3.0s) completes Phase 3 in the unified continuous cycle.

---

## 3. Caveats

1. **Oracle Feed Latency**:
   Phase 3 in-play latency sniping depends on the event feed arriving faster than Binance's market suspension. If Binance suspends first (`MarketStatus: SUSPENDED`), Golden Rule 2 immediately aborts order submission.
2. **ESports Data Feeds**:
   ESports markets (LoL, CS2) have higher volatility and faster objective events (Baron/Dragon kill, bomb plant). The ESports config uses a 0.25 danger threshold and 35.0-minute match length; feed providers must supply timestamps with sub-second accuracy.
3. **Read-Only Scope**:
   In compliance with the Teamwork Explorer archetype, no source files were altered in production directories. Complete code proposals and diffs are supplied below for implementation by designated agents.

---

## 4. Conclusion & Concrete Implementation Proposals

### Summary Assessment
The continuous HFT engine and Strategy V have all necessary mathematical and microstructural models implemented. However, the system is blocked from end-to-end operation by:
1. The missing `_vigilar_y_cerrar_posiciones_abiertas` method in `HFT_BINANCE.py` (which is also the required vehicle for early EV closures).
2. The branching bypass of Phase 2 at T-5m in `HFT_BINANCE.py`.
3. The lack of an explicit `DualBuyProposal` dataclass in `estrategias/arbitraje_amm.py`.
4. The omission of Phase 3 dispatching in `HFTEngine.procesar_mercado`.

---

### Detailed Implementation Specifications (For Implementer Agent)

#### 1. In `estrategias/arbitraje_amm.py`: Add `DualBuyProposal`
```python
@dataclass(frozen=True)
class DualBuyProposal:
    """Propuesta atómica de compra dual generada por la Estrategia V."""
    proposal_id: str
    event_id: str
    symbol_yes: str
    symbol_no: str
    price_yes: float
    price_no: float
    quantity: float
    sum_asks: float
    fees_total: float
    net_edge: float
    order_yes: OrderProposal
    order_no: OrderProposal
    timestamp: float = field(default_factory=time.time)
```
In `detectar_paridad_binaria`, construct `DualBuyProposal` and assign it to `dual_proposal` field of `ArbitrageSignal`.

#### 2. In `estrategias/hft_engine.py`: Wire Phase 3 in `procesar_mercado`
In `procesar_mercado` (around line 1380), before Strategy A/B checks:
```python
        # 0. Fase 3: In-Play Latency Sniping ante evento oracular reciente
        if match_state.last_event and (time.time() - match_state.last_event_timestamp <= 3.0):
            sig_fase3 = self.snipe_desfase_oraculo(
                event_type=match_state.last_event,
                event_timestamp=match_state.last_event_timestamp,
                snapshot=snapshot,
                match_state=match_state,
                balance=balance,
                operaciones_activas=operaciones_activas,
                exposicion_cluster=exposicion_cluster,
            )
            if sig_fase3.authorized:
                return sig_fase3
```

#### 3. In `orquestadores_principales/HFT_BINANCE.py`:
##### A. Implement `_vigilar_y_cerrar_posiciones_abiertas` (Executing Early EV-Driven Closures Before and During Matches)
```python
    async def _vigilar_y_cerrar_posiciones_abiertas(
        self, symbol: str, snapshot: OrderBookSnapshot
    ) -> List[TradeResult]:
        """
        Monitorea y ejecuta salidas anticipadas tanto Pre-Match ('antes') como
        In-Play ('durante') al alcanzarse el valor esperado (EV) o el timeout
        de exposición, sin esperar a que el evento concluya.
        Aplica a deportes tradicionales y ESports.
        """
        trades_cerrados: List[TradeResult] = []
        now = time.time()

        # 1. Auditar timeouts de exposición (Fase 1: 2-10s, Fase 4: 60-90s, Stra A: 3-5m)
        senales_timeout = self.hft_engine.auditar_timeouts(current_time=now, snapshot=snapshot)
        for s in senales_timeout:
            pos_id = s.metadata.get("position_id", "TIMEOUT")
            pnl = s.metadata.get("pnl", 0.0)
            is_win = pnl >= 0.0
            trade = TradeResult(
                trade_id=f"TRADE_{pos_id}",
                symbol=s.symbol,
                stake=s.price * s.quantity,
                pnl=pnl,
                is_win=is_win,
                timestamp=now,
            )
            self.tesoreria.registrar_trade(trade)
            self.auditor.registrar_trade(trade)
            self.risk_engine.registrar_resultado(is_win)
            trades_cerrados.append(trade)

        # 2. Monitorear Take Profit por cumplimiento de Valor Esperado (EV) en libro L2
        best_bid = snapshot.bids[0][0] if snapshot.bids else 0.0
        for pid, pos in list(self.hft_engine.active_positions.items()):
            if pos.symbol == symbol and pos.status == "OPEN":
                # Salida al alcanzar o superar el target_exit_price (EV cumplido)
                if best_bid >= pos.target_exit_price:
                    closed = self.hft_engine.cerrar_posicion(pid, exit_price=best_bid)
                    if closed:
                        trade = TradeResult(
                            trade_id=f"TRADE_EV_{pid}",
                            symbol=symbol,
                            stake=closed.entry_price * closed.quantity,
                            pnl=closed.pnl,
                            is_win=closed.pnl >= 0.0,
                            timestamp=now,
                        )
                        self.tesoreria.registrar_trade(trade)
                        self.auditor.registrar_trade(trade)
                        self.risk_engine.registrar_resultado(closed.pnl >= 0.0)
                        trades_cerrados.append(trade)
                        logger.info(
                            f"[EV EXIT] Posición {pid} ({pos.phase}) cerrada con EV cumplido: "
                            f"Entry={pos.entry_price:.4f}, Exit={best_bid:.4f}, PnL={closed.pnl:.4f}"
                        )

        return trades_cerrados
```

##### B. Fix Unified Dispatching & Phase 2 Cleanup in `step_hft_cycle`
```python
        # Llamar siempre a evaluar_mercado_completo para respetar el ciclo continuo unificado
        senal = self.hft_engine.evaluar_mercado_completo(
            snapshot=snap,
            match_state=match_state,
            balance=balance,
            operaciones_activas=len(self.hft_engine.active_positions),
            exposicion_cluster=self.get_exposicion_cluster(),
        )

        # Manejo de Fase 2: T-5m limpiar_mesa
        if senal.authorized and senal.action == "CLEANUP":
            if hasattr(self.binance_client, "_mock_cancel_all_orders"):
                self.binance_client._mock_cancel_all_orders(symbol)
            elif hasattr(self.binance_client, "cancel_all_orders"):
                await self.binance_client.cancel_all_orders(symbol)
            logger.info(f"[FASE 2 T-5m] Mesa limpia para {symbol}. Exposición verificada = 0%.")
            return senal
```

##### C. Wire `capital_gateway`, `swing_engine` and `amm_engine`
Instantiate `AsyncCapitalGateway`, `SwingEngine`, and `EstrategiaVArbitrajeAMM` in `__init__`, and add `step_swing_cycle` and `step_amm_cycle` to restore complete orchestrator compliance and fix the 10 failing unit tests.

##### D. ESports Symbol Auto-Detection in `live_matches`
```python
        # Detectar disciplina automáticamente por el símbolo
        for sym in self.symbols:
            sport = SportType.ESPORTS if any(k in sym for k in ("ESPORT", "LOL", "CS2", "DOTA")) else SportType.SOCCER
            self.live_matches[sym] = MatchLiveState(
                match_id=f"MATCH_{sym}",
                symbol=sym,
                sport=sport,
                time_to_kickoff_minutes=None,
                is_live=True,
            )
```

---

## 5. Verification Method

To independently verify the implementation once applied:

### Test Command 1: Core HFT, AMM & Microstructure
```powershell
python -m pytest pruebas_unitarias/test_hft.py pruebas_unitarias/test_arbitraje_amm.py pruebas_unitarias/test_estrategias_hft_swing.py pruebas_unitarias/test_microestructura_binance.py pruebas_unitarias/test_golden_rules.py -v
```
**Expected Result**: 103+ PASSED, 0 FAILURES.

### Test Command 2: Acceptance Criterion 1 (Phase 2 T-5m 0% Exposure)
```powershell
python -m pytest pruebas_unitarias/test_hft.py -k "test_hft_phase2_limpiar_mesa_pre_match" -v
```
**Asserts**:
- `ordenes_canceladas` populated.
- Open positions converted to market sell.
- `exposicion_remanente == 0.0`.
- `liquidez_pct == 100.0`.

### Test Command 3: Acceptance Criterion 2 (Strategy V Dual Buy Atomic Proposal)
```powershell
python -m pytest pruebas_unitarias/test_arbitraje_amm.py -k "test_binary_parity" -v
```
**Asserts**:
- Detection triggers when `Ask(YES) + Ask(NO) < 1.00 - fees`.
- `signal.dual_proposal` is not None.
- `signal.dual_proposal.order_yes.side == "BUY"`.
- `signal.dual_proposal.order_no.side == "BUY"`.
- `signal.dual_proposal.net_edge > 0.0`.

### Test Command 4: Pre-Match and In-Play EV Exits (Sports & ESports)
Add and run tests in `pruebas_unitarias/test_hft.py` verifying:
1. `test_ev_driven_exit_prematch_soccer`: Enters Phase 1 maker at `0.51`, L2 bids reach target `0.54` before match kickoff, position closes immediately locking profit.
2. `test_ev_driven_exit_inplay_esports`: Enters ESports Phase 4 in min 29, L2 bids reach target `precio_entrada + 0.02` (or 60s timeout fires), position closes immediately without waiting for the 35-min match to finish.

### Test Command 5: Fixed Orchestrator Suite
```powershell
python -m pytest pruebas_unitarias/test_orquestador_binance.py -v
```
**Expected Result**: All 11 tests in `test_orquestador_binance.py` PASSED with 0 `AttributeError`.

### Invalidation Conditions
- Any open exposure (> 0.0) remaining at T-5m.
- Parity buy proposal triggered when `Ask(YES) + Ask(NO) >= 1.00 - fees`.
- Positions held until the end of the sporting/ESports match rather than exiting upon reaching EV or timeout.
- Unhandled `AttributeError` on `_vigilar_y_cerrar_posiciones_abiertas`.
