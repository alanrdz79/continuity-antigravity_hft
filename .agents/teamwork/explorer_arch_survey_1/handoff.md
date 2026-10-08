# Handoff Report — Architecture Surveyor (explorer_arch_survey_1)

## 1. Observation
- **Requerimientos Formales**:
  - `ORIGINAL_REQUEST.md`: R1 (WebSocket L2 Imbalance, latencia, enrutamiento Binance Spot, HFT + Swing concurrente), R2 (Riesgo, EV > 0, atenuación por racha perdedora, techo de 15% por clúster, ordeño/inyección 10 -> 100 -> 1,000 USD, métricas WR, ROI, Yield, Total Trades), R3 (Bot Telegram bidireccional, Kill Switch, ajustes en caliente).
  - Directivas de Negocio adicionadas (`## 2026-10-07T03:48:12Z`): Cobertura multi-deporte (fútbol, béisbol, NFL, básquetbol, tenis, hockey, eSports), Estrategia A (Time Decay Scalp minutos 65-70 en partidos estancados), Estrategia B (Overreaction Hunting tras desplome de cuota sin gol), Regla de Oro 1 (Spread máx $0.03), Regla de Oro 2 (MarketStatus: Suspended bloquea órdenes), Regla de Oro 3 (Dynamic sizing limitado por liquidez disponible en Top 3 BIDs para escape a mercado).
  - Criterios de Aceptación: `test_hft.py` (>80% imbalance -> orden límite), prueba concurrente no bloqueante HFT + Swing, `test_tesoreria.py` (racha, sizing, hitos financieros y métricas), y `MockTelegramClient` (enrutamiento Kill Switch y pausa).
- **Especificación Matemática en PLANnew.md**:
  - Imbalance: $I = \frac{\sum V_{Bid} - \sum V_{Ask}}{\sum V_{Bid} + \sum V_{Ask}} \ge 0.60$ (equivalente a $>80\%$ del volumen en compras).
  - Factor de atenuación: $\text{factor\_racha} = 0.85^{\text{perdidas\_consecutivas}}$.
  - Sizing de posición: $\text{Posición} = \frac{\text{Balance} \times \text{pct\_riesgo} \times \text{factor\_racha}}{\max(\text{pct\_stop\_loss}, 0.01)}$ con techo de clúster de $15\%$.
  - Tesorería: Inyección de $+100$ USD al cruzar $100$ USD; modo cosecha a los $1,000$ USD ($35\%$ retiro mensual, $40\%$ gastos, $60\%$ reinversión).
- **Estado del Código Base**:
  - Existen implementaciones heredadas para Matchbook en MXN (`orquestadores_principales/HFT_GALO.py`, `conectores/matchbook_async.py`, `continuitis/financiero.py`, `continuitis/microestructura.py`, `continuitis/memoria_hft.py`).
  - Las fórmulas matemáticas y la estructura de memoria RAM con SQLite asíncrono son reutilizables, pero la infraestructura de conexión y el bot de Telegram requieren nueva implementación para Binance Spot y control bidireccional.

## 2. Logic Chain
1. **Concurrencia sin Bloqueos**: Si Swing Trading realizara cómputo estadístico síncrono en el bucle principal de `asyncio`, el GIL y el procesamiento encolarían los frames de WebSocket de Binance, elevando la latencia del feed por encima del umbral de $800\text{ ms}$ de `LatencyGuard`. Por ende, todo cómputo pesado de Swing Trading debe delegarse a hilos mediante `asyncio.to_thread()`, manteniendo el bucle reactivo libre para la ingesta HFT (<1ms).
2. **Prevención de Carreras en Capital**: Si HFT y Swing acceden de forma independiente al saldo disponible, dos decisiones concurrentes de $15\%$ violarían el techo de clúster de $15\%$ simultáneo. Una pasarela atómica de reserva de capital (`RiskGateway` con `asyncio.Lock` y emisión de `ReservationToken`) resuelve la contención de capital sin bloquear el flujo de datos.
3. **Inmutabilidad del Libro de Órdenes**: Actualizar directamente el diccionario del libro en RAM mientras las estrategias lo leen provocaría condiciones de carrera o excepciones de iteración. Emitir copias inmutables congeladas (`OrderBookSnapshot`) garantiza lecturas $\mathcal{O}(1)$ concurrentes sin bloqueos.
4. **Reglas de Oro como Filtros de Entrada**:
   - Spread $> \$0.03 \implies$ Abandono inmediato de trade para evitar fricción letal.
   - Estado `SUSPENDED` $\implies$ `LatencyAndKillSwitchGuard` bloquea emisión de órdenes.
   - Escape en Top 3 BIDs $\implies$ El stake nominal se acota por $\sum_{i=1}^3 V_{Bid, i}$, asegurando que ante una salida de emergencia a mercado no se produzca deslizamiento destructivo.

## 3. Caveats
- Se asume que el feed de WebSocket de Binance para contratos/tokens deportivos provee eventos de profundidad L2 compatibles con diff streams estándar de Binance Spot.
- La liquidez de Binance Spot en contratos deportivos puede tener granularidad de tick específica; el cálculo de `Best Bid + 1 tick` debe parametrizarse mediante `symbol_info["filters"]["PRICE_FILTER"]["tickSize"]`.

## 4. Conclusion
- Se ha diseñado una arquitectura completamente desacoplada y orientada a eventos para CONTINUITY HFT Binance bajo la estructura de paquetes de `continuitis/`.
- Los 4 criterios de aceptación exigidos (`test_hft.py`, prueba concurrente, `test_tesoreria.py`, `MockTelegramClient`) junto con las 6 directivas de negocio y las 3 Reglas de Oro han sido detalladamente mapeados con fórmulas, contratos de datos y casos de prueba en `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_arch_survey_1\report.md`.
- Se recomienda al orquestador proceder con la definición de `PROJECT.md` y despachar la implementación en dos vías paralelas: Track A (Núcleo Financiero, Riesgo y Tesorería) y Track B (Concurrencia, Microestructura HFT/Swing y Telegram).

## 5. Verification Method
- **Inspección de Reporte**: Verificar la completitud del reporte en `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_arch_survey_1\report.md`.
- **Validación de Criterios**:
  - AC 1: Archivo de prueba `test_hft.py` que valide el desequilibrio $>80\%$ ($I \ge 0.60$), spread $\le 0.03$, y generación de orden `BUY LIMIT` a `Best Bid + 1 tick`.
  - AC 2: Prueba concurrente no bloqueante (`test_concurrencia.py`) que ejecute bucles HFT y Swing compitiendo por reservas de capital a 100 ticks/seg con latencia de jitter $< 5\text{ ms}$.
  - AC 3: Simulación de tesorería (`test_tesoreria.py`) que evalúe atenuación $0.85^n$, compresión por Top 3 BIDs, disparo de inyección a los $100$ USD, activación de cosecha a $1,000$ USD y exactitud de WR, ROI, Yield.
  - AC 4: Test con `MockTelegramClient` (`test_telegram_control.py`) que inyecte `/kill` y valide pausa inmediata, cancelación de órdenes y generación de reporte de métricas.
