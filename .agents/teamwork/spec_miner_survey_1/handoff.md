# Handoff Report: PLANnew Technical Specification Mining

**Agent**: `teamwork_preview_spec_miner` (PLANnew Spec Miner)  
**Working Directory**: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\spec_miner_survey_1`  
**Handoff Type**: Hard (Task Complete)  
**Target Recipient**: Project Orchestrator (`f2f51f43-3860-4c33-b19f-c0b7ef73f3b6`)

---

## 1. Observation

Direct observations from primary authoritative documents:

1. **`ORIGINAL_REQUEST.md` (Active Request 2026-10-07T03:43:52Z & 2026-10-07T03:48:12Z)**:
   - Lines 54-57: *"Construir e implementar un motor algorítmico autónomo (CONTINUITY HFT) para operar en los mercados de predicción deportiva de Binance Spot. El sistema debe tener una arquitectura modular que integre estrategias de Alta Frecuencia (HFT), una estrategia complementaria de Swing Trading diseñada por el equipo, gestión estricta de riesgo y tesorería automática."*
   - Lines 92-98:
     * *1. Cobertura de Mercados: Todos los deportes (fútbol, béisbol, fútbol americano, básquetbol, tenis, hockey, eSports), con foco principal en partidos en vivo y en tendencia.*
     * *2. Estrategia A (Explotación del Time Decay): Scalp de bajo riesgo. Entrar entre minutos 65-70 en partidos estancados (ritmo lento). Comprar share del Empate/Resultado actual y mantener 3-5 minutos para ganar el tick del tiempo, vendiendo antes de que acabe el partido.*
     * *3. Estrategia B (Caza de Reacciones Exageradas): Scalp de alto riesgo. Detectar desplomes de precios por pánico (ej. favorito recibe gol pero domina posesión/XG). Comprar el 'dip' y vender en el rebote especulativo tras la primera jugada peligrosa a favor, sin esperar a que anote gol.*
     * *4. Regla de Oro 1 (Spread y Volumen): Spread MÁXIMO permitido de $0.03. Si es mayor, no operar.*
     * *5. Regla de Oro 2 (Monitoreo de Bloqueo): Monitorear el estado de Binance. Si "MarketStatus: Suspended" (por gol o VAR), bloquear cualquier orden nueva.*
     * *6. Regla de Oro 3 (Dynamic Sizing con Liquidez): El cálculo del tamaño de posición debe leer estrictamente el volumen disponible en los primeros 3 niveles del BID para garantizar que siempre haya liquidez de escape ante una salida de emergencia a mercado.*
   - Acceptance Criteria (Lines 75-86): Defines `test_hft.py`, concurrency testing, `test_tesoreria.py`, and `MockTelegramClient`.

2. **`PLANnew.md` (Documento Técnico de Arquitectura Modular)**:
   - Lines 70-76 (Order Book Imbalance):
     $$I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$$
     *Si el desequilibrio de compra supera el 80% ($I \ge 0.60$), inyecta una orden límite de compra a Best Bid + 1 tick. Al llenarse, programa la orden de venta límite a Best Ask + 2 ticks. Exposición máxima: 2 a 10 segundos.*
   - Lines 79-82 (Phase 2): `limpiar_mesa()` atomic order cancel at T-5m; Market Sell if trapped; exposure at minute zero = 0%, USDT = 100%.
   - Lines 85-94 (Phases 3 & 4): Oracle latency sniping (`snipe_desfase_oraculo`) and exponential time decay scalping in draw games where dangerous attacks/min $\to 0$.
   - Lines 102-123 (Risk Engine):
     * $EV = (P_{\text{estimada}} \times \text{Cuota/Payout}) - 1$, filter $EV < 0.015$.
     * $\text{Tamaño de Posición} = \frac{\text{Balance Total} \times \text{Porcentaje de Riesgo}}{\text{Porcentaje de Stop Loss}}$.
     * Fractional Kelly alternative: $f^* = 0.25 \times \frac{p(b+1)-1}{b}$.
     * Cluster Cap: 15% maximum capital exposure.
     * Losing streak attenuation: Compression by factor $0.85^{\text{perdidas\_consecutivas}}$.
   - Lines 125-134 (Execution Router & Latency Guard): Feed latency $> 800\text{ ms}$ triggers emergency; panic button cancels all active/in-memory orders.
   - Lines 135-152 (Metrics): Win Rate $WR = \frac{\text{Wins}}{N}$, $ROI = \frac{\text{Net Gain}}{\text{Initial Capital}}$, $\text{Yield} = \frac{\text{Net Gain}}{\text{Total Turnover}}$, $B_N = B_0 \prod_{i=1}^N (1 + f_i R_i)$.
   - Lines 154-174 (Treasury & Harvesting):
     * Initial capital $10\text{ USD}$.
     * Milestone $10 \to 100\text{ USD}$: Inject $+100\text{ USD}$ (validated by $N \ge 300$, $p\text{-value} < 0.05$, $EV > 0$).
     * Monthly reinvestment ($< \$1,000$): 40% operations, 60% compound reinvestment.
     * Autonomous harvest ($\ge \$1,000$): 35% profit harvested to MXN via P2P/fiat; remainder split 40/60.

3. **Existing Codebase State (`c:\Users\alanr\AE_ecosistema\CONTINUITYEM`)**:
   - `continuitis/microestructura.py`: Implements VWAP calculation, `AjustadorComisiones`, and `EstrategiaMakerTaker`.
   - `continuitis/financiero.py`: Implements `EscudoFinanciero`, `ControladorCluster`, and `MotorInteresCompuesto`.
   - `continuitis/memoria_hft.py`: Ultra-low latency in-RAM order book and async SQLite audit flushing.
   - `conectores/telegram_bot.py`: Implements one-way notifier (`TelegramNotifier`) with 6h reports and alerts; needs upgrade to bidirectional interactive bot with inline commands per R3.

---

## 2. Logic Chain

1. **OBI Calculation & Trigger Equivalence**:
   - From Observation 2 (PLANnew.md lines 70-76), $I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$.
   - Let buy volume ratio be $\alpha = \frac{\sum V_{\text{Bid}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$.
   - Then $I = \alpha - (1 - \alpha) = 2\alpha - 1$.
   - When $\alpha = 0.80$ (80% buy volume dominance), $I = 2(0.80) - 1 = 0.60$.
   - This mathematically proves the equivalence between 80% buy volume and $I \ge 0.60$.
   - Trigger placement is Best Bid + 1 tick (Maker), with exit Limit at Best Ask + 2 ticks and exposure timeout of 2–10 seconds.

2. **Integration of Golden Rules into Risk & Sizing**:
   - From Observation 1 (ORIGINAL_REQUEST.md lines 96-98), three Golden Rules are non-negotiable gates:
     * Golden Rule 1: $\text{Ask} - \text{Bid} \le \$0.03$. Any book with wider spread is rejected prior to signal calculation.
     * Golden Rule 2: `status == "SUSPENDED"` immediately locks order submissions and triggers orphan cancellation.
     * Golden Rule 3: Available liquidity in the top 3 BID levels ($\sum_{k=1}^3 V_{\text{Bid}}^{(k)}$) forms an upper ceiling on nominal position size:
       $$S_{\text{ejecutable}} = \min(S_{\text{cluster\_capped}}, \sum_{k=1}^3 V_{\text{Bid}}^{(k)})$$
       This ensures emergency market exit orders will not suffer catastrophic slippage.

3. **Risk Budget, Attenuation, and Cluster Cap Integration**:
   - Nominal position size uses $S_{\text{nominal}} = \frac{B \times \text{pct\_riesgo\_fijo} \times 0.85^n}{\max(\text{pct\_stop\_loss}, 0.01)}$.
   - Prospective cluster exposure across active trades $(K_{\text{active}} + 1) S_{\text{nominal}} / B$ is compressed if $> 0.15$.
   - Together with Golden Rule 3, the final executable stake is mathematically bounded by both capital risk caps and instantaneous exit order book depth.

4. **Capital Progression & Harvesting Protocol**:
   - Bootstrapping: $B_0 = \$10.00$.
   - Progression Gate: At $B \ge \$100.00$, capital injection of $+100.00\text{ USD}$ is gated by statistical validation ($N \ge 300$, $p\text{-value} < 0.05$).
   - Compounding Phase: Profit distributed 40% operations, 60% compounding reinvestment.
   - Harvesting Phase: Once $B \ge \$1,000.00$, 35% of monthly net profit is harvested and converted to MXN via P2P/fiat, while the remaining 65% is split 40/60.

5. **Telegram Bot Evolution**:
   - Existing `conectores/telegram_bot.py` is a push notifier.
   - Requirement R3 mandates bidirectional interaction (Kill Switch button, `/pause`, `/resume`, `/status`, `/report`, `/risk`).
   - Telegram bot must be wired directly to the orchestrator state to trigger `boton_panico()` upon user action.

---

## 3. Caveats

1. **Binance Predict / Spot Contract Specs**:
   - Prediction market contracts on Binance or associated AMMs typically trade in decimal probability brackets ($[0.00, 1.00]$ USD equivalent). Tick size and minimum notional (e.g. 5 USDT) must be verified against the specific Binance Spot pair/contract API.
2. **Oracle Feed Latency Provider**:
   - While the $800\text{ ms}$ threshold and `detectar_estado_mercado` are fully specified, the concrete sports data provider (API-Football, Sportmonks, or WebSockets) must supply xG and dangerous attacks with $< 500\text{ ms}$ latency to enable Phase 3 sniping.
3. **No other caveats**: All mathematical formulas, operational rules, constraints, edge cases, and acceptance tests have been completely extracted and reconciled.

---

## 4. Conclusion

All quantitative requirements, mathematical derivations, operational strategies (including newly specified Strategy A Time Decay, Strategy B Overreaction Hunting, Multi-Sport coverage, and Golden Rules 1-3), treasury progressions ($10 \to 100 \to 1,000$), Telegram bot command interfaces, and acceptance verification criteria have been successfully mined and compiled into `report.md`. The specification is self-consistent, mathematically verified, and ready for architectural planning and test-driven implementation.

---

## 5. Verification Method

1. **Inspect Report Artifact**:
   - View `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\spec_miner_survey_1\report.md`.
   - Confirm presence of Features Discovered table (32 features), Edge Cases table (17 boundary conditions), mathematical formulas, Telegram commands, and acceptance criteria matrix.
2. **Mathematical Verification of OBI Formula**:
   - Run in python:
     ```python
     def obi(v_bid, v_ask):
         return (v_bid - v_ask) / (v_bid + v_ask)
     # When bid is 80% of total volume (e.g., 80 bid, 20 ask):
     assert obi(80, 20) == 0.60
     ```
3. **Mathematical Verification of Streak & Treasury**:
   - Run in python:
     ```python
     assert round(0.85**3, 6) == 0.614125
     # At 1000 USD with 200 USD monthly profit:
     retiro_35 = 200 * 0.35 # 70.0
     restante = 200 - 70 # 130.0
     op_40 = 130 * 0.40 # 52.0
     reinv_60 = 130 * 0.60 # 78.0
     assert retiro_35 == 70.0 and reinv_60 == 78.0
     ```
4. **Invalidation Conditions**:
   - If Binance Predict changes binary contract pricing to continuous AMM bonding curves without an order book, OBI triggers would require AMM depth formulation.
