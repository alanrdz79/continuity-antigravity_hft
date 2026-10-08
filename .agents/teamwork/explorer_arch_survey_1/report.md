# INFORME TÉCNICO DE ARQUITECTURA Y MATRIZ DE CRITERIOS DE ACEPTACIÓN
## CONTINUITY HFT — Binance Spot Predicción Deportiva
### (Actualizado con Directivas de Negocio y Reglas de Oro ## 2026-10-07T03:48:12Z)

**Autor**: Equipo de Exploración de Arquitectura (Architecture Surveyor)  
**Fecha**: 2026-10-07  
**Estado**: Completado  
**Documentos de Referencia**: `ORIGINAL_REQUEST.md` (incluyendo actualización `## 2026-10-07T03:48:12Z`), `PLANnew.md`, base de código en `c:\Users\alanr\AE_ecosistema\CONTINUITYEM`

---

## 1. RESUMEN EJECUTIVO Y OBJETIVOS DEL SISTEMA

El sistema **CONTINUITY HFT Binance** es un motor algorítmico autónomo y de alta frecuencia diseñado para operar mercados de predicción deportiva (contratos binarios / tokens deportivos de predicción en Binance Spot). El sistema integra:
1. **Doble Motor Estratégico Concurrente**: Una estrategia HFT de microestructura (desequilibrio del libro de órdenes *L2 Depth*, Time Decay y Caza de Sobrereacciones) ejecutándose en paralelo con una estrategia ortogonal de **Swing Trading** (posicionamiento macro de mayor ventana temporal sin canibalización de capital ni bloqueo del event loop).
2. **Motor de Riesgo y Tesorería Autónoma**: Gestión matemática de Valor Esperado ($EV \ge 0.015$), dimensionamiento dinámico con atenuación exponencial por rachas perdedoras ($0.85^{\text{racha}}$), techo rígido de exposición por clúster ($\le 15\%$), **filtro de liquidez de escape en los 3 mejores niveles de BID**, e hitos automáticos de inyección ($10 \to 100 \text{ USD}$) y cosecha de beneficios ($\ge 1,000 \text{ USD}$).
3. **Control Bidireccional por Telegram**: Interfaz de telemetría y mando en tiempo real que permite emitir reportes de rendimiento y recibir órdenes interactivas prioritarias (Kill Switch instantáneo, pausa/reanudación y ajuste dinámico de riesgo).
4. **Reglas de Oro de Ejecución**: Techo estricto de spread ($\le \$0.03$), bloqueo total ante estado `SUSPENDED` y garantía de salida de emergencia a mercado.

---

## 2. DIRECTIVAS DE NEGOCIO Y REGLAS DE ORO (ACTUALIZACIÓN 2026-10-07)

De acuerdo con la última especificación oficial del usuario, se incorporan formalmente las siguientes 6 directivas al diseño arquitectónico:

### Directiva 1: Cobertura Multi-Deporte Universal
* **Alcance**: Fútbol, béisbol, fútbol americano (NFL), básquetbol, tenis, hockey y eSports.
* **Foco**: Eventos en vivo (*in-play*) y en tendencia (*trending matches*).
* **Implicación Arquitectónica**: El feed de eventos y el calculador de microestructura deben desacoplarse de la semántica exclusiva del fútbol. La entidad `EventContext` maneja métricas temporales normalizadas (minuto de juego, cuarto, entrada/inning, set/game) y estado de peligro (*danger index*).

### Directiva 2: Estrategia A — Explotación del Time Decay (Scalp de Bajo Riesgo)
* **Ventana**: Minutos 65 al 70 en partidos estancados (ritmo lento, $\text{Danger Index} \to 0$).
* **Entrada**: Compra contratos del resultado actual (Empate / Victoria parcial).
* **Exposición**: Retención temporal de 3 a 5 minutos para capturar el valor del avance del reloj (*time tick*).
* **Salida**: Venta de la posición en mercado secundario antes del pitido final (evitando riesgo de liquidación tardía).

### Directiva 3: Estrategia B — Caza de Reacciones Exageradas (Overreaction Hunting - Scalp de Alto Riesgo)
* **Disparador**: Desplome abrupto de precio por pánico del mercado (ej. favorito encaja gol o pierde ventaja inicial, pero mantiene dominancia en métricas subyacentes como posesión y $xG$).
* **Entrada**: Compra en el suelo de pánico (*buy the dip*).
* **Salida**: Venta inmediata en el rebote especulativo tras la primera jugada de peligro a favor, **sin esperar a que anote gol**.

### Directiva 4: Regla de Oro 1 — Techo Máximo de Spread ($\le \$0.03$)
* **Condición Innegociable**:
  $$\text{Spread} = \text{Best Ask} - \text{Best Bid} \le 0.03\text{ USD}$$
  Si $\text{Spread} > 0.03\text{ USD}$, el motor aborta la evaluación de cualquier orden (`operar = False`, motivo: `SPREAD_EXCESIVO`).

### Directiva 5: Regla de Oro 2 — Bloqueo Inmediato ante Mercado Suspendido
* **Condición**: Si Binance notifica o el oráculo detecta `MarketStatus == "SUSPENDED"` (por gol, VAR, revisión de jugada o tiempo fuera):
  - Se bloquea la emisión de cualquier orden nueva de forma atómica.
  - Se congelan las colas de disparo de HFT y Swing.

### Directiva 6: Regla de Oro 3 — Sizing Dinámico con Liquidez de Escape (Top 3 BIDs)
* **Garantía de Escape**: Para evitar quedar atrapado en contratos ilíquidos, el tamaño máximo de posición calculado por Kelly/Riesgo se acota estrictamente por la profundidad de compra inmediata:
  $$\text{Liquidez Escape Bid} = \sum_{i=1}^3 V_{\text{Bid}, i}$$
  $$\text{Stake Final} = \min\left(\text{Posición Nominal RiskEngine}, \; \text{Liquidez Escape Bid} \times \text{Factor Seguridad}\right)$$
  donde $\text{Factor Seguridad} \in (0.50, 1.00)$ asegura que una orden de salida de pánico a mercado (`Market Sell`) se llene en los 3 primeros niveles sin barrer el libro a cero.

---

## 3. MODELO DE CONCURRENCIA: HFT Y SWING TRADING EN TIEMPO REAL

### 3.1. Análisis de Riesgos y Cuellos de Botella (Hazards Analysis)

| Riesgo / Hazard | Mecanismo del Problema | Impacto en el Sistema |
|---|---|---|
| **Bloqueo del Event Loop (GIL / CPU Jitter)** | Cálculos estadísticos de Swing Trading (análisis de $xG$, regresiones multivariadas) ejecutados en el hilo principal de `asyncio`. | Retiene el loop; se atrasa la lectura de paquetes WebSocket de Binance; la latencia del feed excede los $800\text{ ms}$, disparando `LatencyGuard` en falso pánico. |
| **Condición de Carrera en Capital (Balance Race Condition)** | HFT y Swing consultan simultáneamente el balance disponible. Ambos deciden arriesgar el $15\%$. Ambas órdenes se envían al unísono, violando el techo de clúster o provocando saldo insuficiente en Binance. | Sobre-exposición catastrófica del bankroll, rechazos por la API de Binance (`insufficient balance`). |
| **Corrupción de Estado del Libro (Memory Mutation Hazard)** | El worker de WebSocket muta el diccionario en RAM de `bids`/`asks` mientras el motor de Swing Trading itera sobre el mismo objeto para calcular métricas. | Excepciones `RuntimeError: dictionary changed size during iteration` o lecturas inconsistentes (dirty reads). |
| **Saturación de I/O de Base de Datos** | Escrituras sincrónicas en SQLite (`INSERT` / `COMMIT`) tras cada evento o trade. | Bloqueo de disco en el bucle principal de Python, introduciendo latencias de 5 a 50 ms por ciclo. |

---

### 3.2. Arquitectura de Concurrencia Recomendada: *Asyncio Pipeline + Token Reservation*

```
                         ┌──────────────────────────────────────┐
                         │       BINANCE WEBSOCKET FEED         │
                         │  (Depth L2 diff, Trades, Status)     │
                         └──────────────────┬───────────────────┘
                                            │ async stream
                                            ▼
                         ┌──────────────────────────────────────┐
                         │       OrderBookListenerTask          │
                         │   (Mantiene memoria RAM L2 Depth)    │
                         └───────┬──────────────────────┬───────┘
     Copia Inmutable L2 Snapshot │                      │ Copia Inmutable L2 Snapshot
                                 ▼                      ▼
    ┌──────────────────────────────┐        ┌──────────────────────────────┐
    │       HFTStrategyTask        │        │      SwingStrategyTask       │
    │  (Imbalance, Decay, Rebote)  │        │  (Trend, Macro, Multi-Frame) │
    │    Bucle reactivo (<1ms)     │        │  Cálculo pesado en ThreadPool│
    └──────────────┬───────────────┘        └──────────────┬───────────────┘
                   │ Emite OrderSignal                     │ Emite OrderSignal
                   ▼                                       ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │            RISK & CAPITAL GATEWAY (EscudoFinanciero)                 │
    │   - `asyncio.Lock` en reserva de capital                             │
    │   - Valida Regla de Oro 1 (Spread <= $0.03)                          │
    │   - Valida Regla de Oro 3 (Capacidad de Escape Top 3 BIDs)           │
    │   - Valida EV >= 0.015 y factor de atenuación (0.85^racha)           │
    │   - Control de techo de clúster (<= 15% del balance)                 │
    │   - Emite `ReservationToken` atómico por estrategia                  │
    └──────────────────────────────────┬───────────────────────────────────┘
                                       │ Señal aprobada + Token
                                       ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │                     ExecutionRouterTask                              │
    │   - Verificación de `LatencyGuard` (<800ms)                          │
    │   - Verificación de Regla de Oro 2 (MarketStatus != SUSPENDED)       │
    │   - Envío asíncrono no bloqueante a Binance Spot REST / WebSocket    │
    │   - Si Kill Switch activo: rechaza y cancela todo                    │
    └──────────────────────────────────┬───────────────────────────────────┘
                                       │
                                       ▼
    ┌──────────────────────────────────────────────────────────────────────┐
    │                     StateRegistry & MetricAuditor                    │
    │   - RAM cache (<1ms)                                                 │
    │   - Escritura persistente desacoplada: `asyncio.to_thread` en SQLite │
    └──────────────────────────────────────────────────────────────────────┘
```

#### Reglas de Diseño de la Concurrencia:
1. **Instantáneas Inmutables del Libro (`OrderBookSnapshot`)**:
   El listener de WebSocket actualiza los diccionarios internos en RAM ($\mathcal{O}(1)$). Al emitir actualizaciones a las estrategias, genera un objeto inmutable de solo lectura (`OrderBookSnapshot`) con tuplas congeladas de los niveles del libro. Las estrategias leen este snapshot sin bloqueos ni riesgo de mutación concurrente.
2. **Aislamiento de Cómputo Pesado (Offloading a Worker Threads)**:
   La estrategia de Swing Trading ejecuta sus filtros pesados delegando la computación a un pool de hilos mediante:
   ```python
   senales = await asyncio.to_thread(self._calcular_senales_swing_heavy, snapshot, contexto)
   ```
   Esto asegura que el bucle de eventos permanezca $100\%$ libre para la ingesta HFT de WebSocket.
3. **Reserva Atómica de Capital (`ReservationToken`)**:
   Ni HFT ni Swing colocan órdenes directamente en el router. Ambas solicitan una reserva a `RiskEngine`:
   ```python
   token = await risk_engine.solicitar_reserva(
       estrategia_id="HFT_TIME_DECAY",
       stake_solicitado=stake,
       pct_stop_loss=0.02,
       top3_bid_liquidity=snapshot.top3_bid_volume
   )
   if token.aprobado:
       orden = await router.ejecutar_orden(token, ...)
       await risk_engine.confirmar_ejecucion(token, orden)
   ```
   La función `solicitar_reserva` utiliza un `asyncio.Lock()` interno de muy corta duración (microsegundos) para verificar el balance no comprometido, la liquidez de escape y el límite del $15\%$ por clúster, previniendo cualquier sobre-asignación de capital.

---

## 4. MAPEO DETALLADO DE CRITERIOS DE ACEPTACIÓN

A continuación se traduce cada criterio de aceptación del requerimiento oficial a su especificación técnica, formulación matemática y diseño del caso de prueba ejecutable.

---

### 4.1. Criterio 1: Simulación `test_hft.py` (Desequilibrio del Libro > 80% $\to$ Orden Límite)

#### Especificación Matemática y de Negocio (PLANnew.md Fase 1):
* **Fórmula de Desequilibrio de Libro (*Order Book Imbalance* - $I$):**
  $$I = \frac{\sum_{i=1}^K V_{\text{Bid}, i} - \sum_{i=1}^K V_{\text{Ask}, i}}{\sum_{i=1}^K V_{\text{Bid}, i} + \sum_{i=1}^K V_{\text{Ask}, i}}$$
  donde $K \in [5, 10]$ representa la profundidad considerada.
* **Equivalencia Matemática del $> 80\%$ de Desequilibrio:**
  Si el volumen de compra ($V_{\text{Bid}}$) representa el $80\%$ del volumen total combinado y los Asks el $20\%$:
  $$I = \frac{0.80 - 0.20}{0.80 + 0.20} = \frac{0.60}{1.00} = 0.60$$
  Por ende, la condición de disparo de compra agresiva es:
  $$\text{Bid Share} \ge 0.80 \iff I \ge 0.60$$
* **Filtros Adicionales (Reglas de Oro):**
  - $\text{Spread} \le \$0.03$.
  - $\text{MarketStatus} \neq \text{SUSPENDED}$.
  - $\text{Stake} \le \sum_{i=1}^3 V_{\text{Bid}, i}$.
* **Regla de Formateo de Orden Límite (Maker Spot):**
  - Si $I \ge 0.60$ y pasa los filtros:
    - **Lado**: `BUY`.
    - **Tipo de Orden**: `LIMIT` (Post-Only).
    - **Precio de Entrada**: $\text{Best Bid} + 1\text{ tick}$ (ej. si Best Bid es $0.550$ y tick es $0.001 \to 0.551$).
    - **Salida**: Programa orden de venta límite a $\text{Best Ask} + 2\text{ ticks}$ con exposición entre $2$ y $10$ segundos.

#### Matriz del Test `test_hft.py`:
| Parámetro de Prueba | Entrada Simulada | Resultado Esperado |
|---|---|---|
| Inyección de Libro Balanceado | Bids: 500 vol @ 0.55, Asks: 500 vol @ 0.56 ($I=0.0$) | No emite orden (`operar = False`). |
| Inyección de Desequilibrio Venta | Bids: 100 vol @ 0.55, Asks: 900 vol @ 0.56 ($I=-0.80$) | No emite orden de compra Fase 1. |
| Violación de Regla de Oro 1 | Desequilibrio $I=+0.80$, pero Best Ask 0.59 y Best Bid 0.55 (Spread = $0.04 > 0.03$) | Bloqueada: `motivo = "SPREAD_EXCESIVO"`. |
| Violación de Regla de Oro 2 | Desequilibrio $I=+0.80$, pero `MarketStatus = "SUSPENDED"` | Bloqueada: `motivo = "MERCADO_SUSPENDIDO"`. |
| Inyección Válida $> 80\%$ | Bids: 900 vol @ 0.550, Asks: 100 vol @ 0.560 ($I=+0.80$, Spread 0.01) | Emite `OrderSignal`: Lado `BUY`, Precio `0.551`, Tipo `LIMIT`. |
| Validación de Carga Útil Binance | `OrderSignal` convertida a payload REST | Payload válido: `{"symbol": "...", "side": "BUY", "type": "LIMIT", "price": "0.551", "timeInForce": "GTC", ...}` |

---

### 4.2. Criterio 2: Prueba Concurrente No Bloqueante de HFT y Swing Trading

#### Especificación Técnica:
* Se debe crear una prueba automatizada con `pytest-asyncio` que orqueste:
  1. Un generador sintético de flujo WebSocket que bombee $200$ actualizaciones de profundidad del libro por segundo hacia `OrderBookListener`.
  2. La tarea `HFTStrategyTask` procesando cada tick, calculando el imbalance en memoria y evaluando señales de Time Decay y Overreaction en $< 1\text{ ms}$.
  3. La tarea `SwingStrategyTask` ejecutando su ciclo analítico cada $50\text{ ms}$, realizando una simulación de cálculo estadístico (vía `asyncio.to_thread`) y emitiendo órdenes de posición de mayor plazo.
  4. Ambas tareas compitiendo por registrar órdenes en `RiskEngine`.
* **Criterios de Aprobación de la Prueba:**
  - Cero excepciones de tipo `RuntimeError` o bloqueos del event loop.
  - El retardo o *jitter* del ciclo de HFT debe mantenerse por debajo de $5\text{ ms}$ por tick (medido con `time.perf_counter()`).
  - El balance y capital reservado en el `RiskEngine` deben permanecer consistentes en todo momento ($\text{Capital Reservado} \le \text{Techo de Clúster de } 15\%$).
  - Ninguna tarea entra en estado de inanición (*starvation*).

---

### 4.3. Criterio 3: Simulación `test_tesoreria.py` (Atenuación, Tamaño de Posición, Umbrales y Métricas)

#### Especificación Matemática y de Negocio (PLANnew.md Módulos 3, 5 y 6 + Golden Rule 3):

1. **Filtro de Valor Esperado ($EV$):**
   $$EV = (P_{\text{estimada}} \times \text{Cuota}) - 1$$
   *Regla*: No se opera si $EV < 0.015$ ($1.5\%$).

2. **Factor de Atenuación por Racha Perdedora:**
   $$\text{factor\_racha} = 0.85^{\text{perdidas\_consecutivas}}$$
   - $0$ derrotas: $0.85^0 = 1.000$
   - $1$ derrota: $0.85^1 = 0.850$
   - $2$ derrotas: $0.85^2 = 0.7225$
   - $3$ derrotas: $0.85^3 \approx 0.6141$
   - Al ocurrir una victoria: `perdidas_consecutivas = 0`, el factor regresa a $1.000$.

3. **Fórmula de Tamaño de Posición Real (Position Sizing) con Regla de Oro 3:**
   $$\text{riesgo\_objetivo} = \text{Balance} \times \text{pct\_riesgo\_fijo} \times \text{factor\_racha}$$
   $$\text{posicion\_nominal} = \frac{\text{riesgo\_objetivo}}{\max(\text{pct\_stop\_loss}, 0.01)}$$
   *Modulación por Techo de Clúster ($15\%$):*
   $$\text{Si } \text{exposicion\_futura} > 0.15 \implies \text{posicion\_nominal} = \frac{0.15 \times \text{Balance}}{\text{operaciones\_activas} + 1}$$
   *Modulación por Liquidez de Escape (Regla de Oro 3):*
   $$\text{posicion\_final} = \min\left(\text{posicion\_nominal}, \; \sum_{i=1}^3 V_{\text{Bid}, i}\right)$$

4. **Reglas Operativas de Tesorería e Inyección de Capital:**
   - **Hito $10 \to 100 \text{ USD}$**: Capital de arranque: $10 \text{ USD}$. Al cruzar $\ge 100 \text{ USD}$, se dispara el evento `INYECCION_100_USD_APLICADA`, sumando $100 \text{ USD}$ al balance (alcanzando $\ge 200 \text{ USD}$). Solo se aplica una única vez.
   - **Hito de Cosecha ($1,000 \text{ USD}$)**: Al cruzar $\ge 1,000 \text{ USD}$, se activa `meta_1000_activada = True`.
   - **Cierre Mensual de Beneficios**:
     - Con `meta_1000_activada == True`:
       - Retiro autónomo: $35\%$ de la ganancia mensual.
       - Del restante $65\%$: $40\%$ gastos operativos y $60\%$ reinversión de interés compuesto.
     - Con `meta_1000_activada == False`:
       - Retiro: $0\%$.
       - Ganancia dividida en: $40\%$ gastos operativos y $60\%$ reinversión.

5. **Auditoría Matemática de Métricas Clave:**
   - **Win Rate ($WR$):** $\frac{\text{Operaciones Ganadoras}}{N}$
   - **ROI (%):** $\frac{\text{Ganancia Neta Acumulada}}{\text{Capital Inicial}} \times 100$
   - **Yield (%):** $\frac{\text{Ganancia Neta Total}}{\text{Volumen Total Operado (Turnover)}} \times 100$
   - **Capital Acumulado ($B_N$):** $B_N = B_0 \cdot \prod_{i=1}^N (1 + f_i \cdot R_i)$

#### Matriz del Test `test_tesoreria.py`:
| Escenario de Simulación | Secuencia de Entrada | Verificación Esperada |
|---|---|---|
| Racha de Pérdidas y Recuperación | 3 derrotas consecutivas seguidas de 1 victoria | Stake disminuye en factores $0.85$, $0.7225$, $0.6141$. Tras la victoria, el stake se restablece al $100\%$ ($factor=1.0$). |
| Límite de Clúster (15%) | 5 operaciones concurrentes de alto stake | Cada operación es comprimida para que la suma total no exceda el $15\%$ del balance. |
| Límite de Liquidez de Escape (Regla de Oro 3) | Stake calculado $50$ USD, pero Top 3 BIDs solo suman $20$ USD | Stake comprimido a $20$ USD para garantizar escape a mercado. |
| Inyección de 100 USD | Balance inicial $10$, ganancias acumuladas cruzan $100$ USD | Se dispara evento `INYECCION_100_USD_APLICADA`; nuevo balance $= 200$; hito marcado como completado. |
| Cosecha a los 1,000 USD | Balance cruza $1,000$ USD y se procesa cierre con ganancia de $200$ USD | Se extrae $35\%$ ($70$ USD); de los $130$ USD restantes: $52$ USD ($40\%$) a operación y $78$ USD ($60\%$) a reinversión. |
| Integridad de Fórmulas Métricas | 10 operaciones simuladas (6 ganadas, 4 perdidas, turnover $500$ USD, ganancia neta $+50$ USD con base $100$ USD) | $WR = 60.0\%$, $ROI = 50.0\%$, $Yield = 10.0\%$, $Total = 10$. |

---

### 4.4. Criterio 4: `MockTelegramClient` y Enrutamiento Bidireccional de Comandos

#### Especificación Técnica:
* Se implementa un cliente simulador (`MockTelegramClient`) que permite enviar mensajes entrantes (comandos) al `TelegramCommandHandler` como si provinieran de la API de Telegram.
* **Comandos Requeridos y Acciones en el Orquestador:**
  1. `/kill` o botón *Kill Switch*:
     - Invoca de forma inmediata `LatencyAndKillSwitchGuard.boton_panico()`.
     - El orquestador pausa inmediatamente toda actividad de escaneo y ejecución.
     - Cancela atómicamente todas las órdenes abiertas en Binance Spot.
     - Envía mensaje de confirmación por Telegram con el estado de pánico activado.
  2. `/pause` y `/resume`:
     - Pausa o reanuda las nuevas entradas de HFT y Swing sin liquidar forzosamente posiciones pasivas en espera.
  3. `/risk <pct_riesgo>`:
     - Modifica en caliente los parámetros de `EscudoFinancieroHFT` (ej. cambiar riesgo del $1.5\%$ al $1.0\%$).
  4. `/report` o `/status`:
     - Consulta en tiempo real a `MetricAuditor` y `TreasuryManager`.
     - Genera y devuelve el resumen formateado con: Balance Actual, Win Rate, ROI, Yield, Total Trades, Operaciones Abiertas y Estado del Motor.

#### Matriz del Mock Test:
| Estímulo del Mock | Acción en el Orquestador | Verificación en el Test |
|---|---|---|
| Mock envía `/kill` | Invoca `boton_panico()` | `orquestador.esta_pausado == True`, llamadas a `cancel_all_orders()` confirmadas en mock router, mensaje de respuesta contiene `🚨 KILL SWITCH ACTIVADO`. |
| Mock envía `/report` | Consulta métricas actuales | Mensaje de respuesta devuelto contiene valores exactos de Balance, WR, ROI y Yield actuales. |
| Mock envía `/risk 0.02` | Actualiza parámetro en caliente | `risk_engine.pct_riesgo_fijo == 0.02`, mensaje de confirmación recibido en mock. |

---

## 5. FRONTERAS MODULARES, CONTRATOS DE INTERFAZ Y ESTRUCTURA DE COMPONENTES

```
c:\Users\alanr\AE_ecosistema\CONTINUITYEM\
├── continuitis/
│   ├── __init__.py
│   ├── constantes.py                  # Constantes globales, umbrales y tipos
│   ├── tipos.py                       # Dataclasses y TypedDicts de contratos
│   ├── ingest/                        # MÓDULO 1: Ingesta y réplica de libro
│   │   ├── __init__.py
│   │   ├── listener_ws.py             # Conexión WebSocket Depth L2 a Binance
│   │   └── libro_ram.py               # Estructura O(1) de libro de órdenes en RAM
│   ├── estrategias/                   # MÓDULO 2: Lógica algorítmica
│   │   ├── __init__.py
│   │   ├── base.py                    # Interfaz base StrategyProtocol
│   │   ├── hft_microestructura.py     # Fase 1 (Imbalance), Time Decay, Overreaction
│   │   └── swing_trading.py           # Estrategia ortogonal de Swing Trading
│   ├── riesgo/                        # MÓDULO 3: Escudo financiero
│   │   ├── __init__.py
│   │   ├── escudo_financiero.py       # Kelly, racha (0.85^n), cluster (15%), Top 3 BIDs
│   │   └── gateway_reserva.py         # Pasarela atómica con asyncio.Lock
│   ├── ejecucion/                     # MÓDULO 4: Enrutamiento de órdenes
│   │   ├── __init__.py
│   │   ├── latency_guard.py           # LatencyAndKillSwitchGuard (<800ms, Suspended lock)
│   │   └── router_binance.py          # Cliente Binance Spot REST / WebSocket
│   ├── auditoria/                     # MÓDULO 5: Registro y métricas
│   │   ├── __init__.py
│   │   ├── metric_auditor.py          # Fórmulas de WR, ROI, Yield, Turnover
│   │   └── state_registry.py          # SQLite WAL persistente con buffer RAM
│   ├── tesoreria/                     # MÓDULO 6: Crecimiento y cosecha
│   │   ├── __init__.py
│   │   └── treasury_manager.py        # Hitos 10->100->1000 y cosechas mensuales
│   ├── telegram/                      # MÓDULO 7: Bot bidireccional
│   │   ├── __init__.py
│   │   ├── bot_bidireccional.py       # Polling de comandos + notificaciones
│   │   └── command_handler.py         # Despacho de /kill, /pause, /risk, /report
│   └── orquestador/                   # MÓDULO 8: Ciclo vital del sistema
│       ├── __init__.py
│       └── motor_continuo.py          # Bucle de tareas asíncronas concurrentes
├── pruebas_unitarias/
│   ├── test_hft.py                    # AC 1: Simulación de Imbalance > 80% + Golden Rules
│   ├── test_concurrencia.py           # AC 2: Concurrencia no bloqueante HFT + Swing
│   ├── test_tesoreria.py              # AC 3: Racha, Sizing con Top3 BIDs, Hitos y Fórmulas
│   └── test_telegram_control.py       # AC 4: MockTelegramClient y Kill Switch
```

### 5.1. Contratos de Datos e Interfaces Formales (`tipos.py`)

#### 1. Instantánea del Libro de Órdenes (`OrderBookSnapshot`):
```python
from dataclasses import dataclass
from typing import Tuple, Optional

@dataclass(frozen=True)
class OrderBookSnapshot:
    symbol: str
    timestamp: float
    bids: Tuple[Tuple[float, float], ...]  # ((precio, volumen), ...) orden descendente
    asks: Tuple[Tuple[float, float], ...]  # ((precio, volumen), ...) orden ascendente
    is_suspended: bool = False

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0][0] if self.asks else None

    @property
    def spread(self) -> float:
        if self.best_bid is not None and self.best_ask is not None:
            return round(self.best_ask - self.best_bid, 4)
        return float('inf')

    @property
    def top3_bid_volume(self) -> float:
        """Regla de Oro 3: Suma de volumen disponible en los primeros 3 niveles de compra."""
        return sum(vol for _, vol in self.bids[:3])

    def calculate_imbalance(self, depth: int = 5) -> float:
        vol_bid = sum(v for _, v in self.bids[:depth])
        vol_ask = sum(v for _, v in self.asks[:depth])
        total = vol_bid + vol_ask
        if total <= 0:
            return 0.0
        return (vol_bid - vol_ask) / total
```

#### 2. Señal y Reserva de Capital:
```python
from dataclasses import dataclass
from enum import Enum

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

@dataclass
class OrderSignal:
    strategy_id: str           # "HFT_IMBALANCE", "HFT_TIME_DECAY", "HFT_OVERREACTION", "SWING"
    symbol: str
    side: OrderSide
    order_type: OrderType
    target_price: float
    estimated_p: float
    odds: float
    stop_loss_pct: float
    urgency_sec: float = 10.0

@dataclass
class ReservationToken:
    token_id: str
    strategy_id: str
    approved: bool
    stake_approved: float
    ev: float
    rejection_reason: Optional[str] = None
```

---

## 6. ESTRATEGIA DE PRUEBAS Y SUITE DE MOCKS

### Mapeo de Archivos de Prueba Requeridos

| Archivo de Prueba | Criterio Validado | Método de Verificación Principal |
|---|---|---|
| `test_hft.py` | AC 1: Desequilibrio $>80\%$ $\to$ Orden Límite + Reglas de Oro 1 y 2 | Instancia `HFTMicrostructureStrategy`, inyecta snapshot con $V_{Bid}=900, V_{Ask}=100$, valida rechazo si spread $>0.03$, valida bloqueo si `is_suspended=True`, y aserta emisión de orden `BUY LIMIT` a $\text{Best Bid} + 1\text{ tick}$. |
| `test_concurrencia.py` | AC 2: Concurrencia HFT + Swing sin bloqueos | Lanza `HFTStrategyTask` y `SwingStrategyTask` en bucle concurrente por 3 segundos con 100 ticks/seg; verifica cero excepciones y latencia $<5\text{ ms}$. |
| `test_tesoreria.py` | AC 3: Racha, Sizing con Regla de Oro 3 (Top 3 BIDs), Hitos e Integridad de Fórmulas | Simula serie temporal de 20 trades; verifica atenuación $0.85^n$, compresión por liquidez de escape de Top 3 BIDs, disparo de inyección a los $100$ USD, activación de cosecha a $1000$ USD y exactitud matemática de WR, ROI, Yield. |
| `test_telegram_control.py` | AC 4: Control Bidireccional y Kill Switch | Inyecta `/kill` vía `MockTelegramClient`; verifica que `motor.esta_pausado == True`, que las órdenes activas se cancelan y que se recibe reporte de estado. |

---

## 7. CONCLUSIÓN Y RECOMENDACIONES PARA EL ORQUESTADOR

1. **Estructura Modular Limpia**: Toda la arquitectura se organiza bajo `continuitis/` en paquetes cohesivos y desacoplados.
2. **Cumplimiento de las 6 Directivas de Negocio**: Se han blindado formalmente el multi-deporte, las estrategias de Time Decay y Overreaction, el techo de spread de $0.03$, el bloqueo de estado suspendido y el sizing atado a la liquidez de escape de los 3 mejores BIDs.
3. **Dual Track de Implementación**:
   - **Track A (Núcleo Financiero, Riesgo y Tesorería)**: Implementación de `EscudoFinanciero`, `TreasuryManager`, `MetricAuditor` y `test_tesoreria.py`.
   - **Track B (Concurrencia, Microestructura HFT/Swing y Telegram)**: Implementación de `OrderBookSnapshot`, `HFTMicrostructureStrategy`, `SwingStrategy`, `MockTelegramClient`, `test_hft.py` y `test_concurrencia.py`.
