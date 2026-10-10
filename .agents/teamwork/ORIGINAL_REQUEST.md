# Original User Request

## 2026-09-29T05:17:20Z

# Teamwork Project Prompt — Final

> Status: Launched (v2 - Policy Compliant).
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: [none — teamwork routes from the description]

Develop a multi-platform algorithmic trading and automation ecosystem.
System A: A high-frequency liquidity provision strategy for Matchbook Exchange (implementing strict Time-In-Force controls cancelling unmatched limit orders after 45s).
System B: An automated execution cluster targeting Playdoit, Winspot, and Draftea. The cluster must operate with isolated capital per platform and use dynamic volume throttling (profit caps + variance injection via uncorrelated trades) to maintain a natural account profile.

Working directory: c:\Users\alanr\AE_ecosistema\CONTINUITYEM
Integrity mode: development

## Requirements

### R1. High-Reliability Browser Automation (Playdoit & Winspot)
Use Playwright/Puppeteer with advanced browser fingerprint management to control a headless Chrome instance. It must simulate natural human-like mouse movements, randomized click delays, and visual DOM interaction to ensure high reliability and avoid false-positive automated blocking on Playdoit and Winspot.

### R2. Mobile API Client Conformance (Draftea)
Develop an API client for the Draftea mobile backend. The client must implement strict protocol conformance by matching standard mobile headers, standard TLS fingerprints (JA3), and standard device IDs to ensure full compatibility and reliability with the private API.

### R3. Dynamic Profile Management
For commercial platforms, track net profit per platform. Enforce a weekly hard profit cap and inject occasional low-stake uncorrelated trades to manage variance and maintain a standard, natural account behavior profile.

### R4. Matchbook HFT Capital Rotation
Update the existing Matchbook engine to implement strict Time-in-Force (TIF) rules: auto-cancel any unmatched Maker order after 45 seconds to free up capital, enabling rapid ROI compounding.

## Acceptance Criteria

### Automated Reliability Verification (Web)
- [ ] A local mock server simulating strict browser integrity checks must be built.
- [ ] The Playwright automation must successfully authenticate against the mock server in 5 out of 5 headless attempts without triggering integrity failures.

### Automated API Verification (Mobile)
- [ ] A local mock mobile endpoint must be built to intercept API requests.
- [ ] The Draftea client must send requests that programmatically pass a strict TLS fingerprint (JA3) and standard mobile header validation test.

### HFT Capital Rotation Verification
- [ ] A unit test must mock the Matchbook API, inject a pending Maker order, and assert that the garbage collection task triggers an exact cancellation payload after exactly 45 seconds of simulated time.


## 2026-10-07T03:43:52Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: [none — teamwork routes from the description]

Construir e implementar un motor algorítmico autónomo (CONTINUITY HFT) para operar en los mercados de predicción deportiva de Binance Spot. El sistema debe tener una arquitectura modular que integre estrategias de Alta Frecuencia (HFT), una estrategia complementaria de Swing Trading diseñada por el equipo, gestión estricta de riesgo y tesorería automática.

Working directory: ~/teamwork_projects/continuity_hft_binance
Integrity mode: development

**Reference material**: 
Documento de Arquitectura Original: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\PLANnew.md`

## Requirements

### R1. Arquitectura de Ejecución y Estrategias Mixtas
Implementar un sistema modular con escucha asíncrona (WebSocket) del libro de órdenes (*Order Book Imbalance*), cálculo de latencia y enrutamiento de órdenes a la API de Binance Spot. El equipo debe integrar la lógica HFT descrita en el documento de referencia y diseñar una estrategia paralela u ortogonal de Swing Trading que se complemente de manera óptima.

### R2. Motor de Riesgo, Métricas y Tesorería
Implementar los cálculos matemáticos de Valor Esperado ($EV > 0$), el dimensionamiento dinámico de posiciones (con atenuación en rachas perdedoras y techo del 15% por clúster), la fórmula de tamaño de posición real, y el submódulo de "Ordeño e Inyección" que aplique las reglas de crecimiento ($10 \to \$100 \to \$1,000$) descritas en el plan original. Además, integrar el cálculo continuo y preciso de métricas clave: Win Rate, Capital Acumulado, ROI, Yield y Número total de operaciones.

### R3. Bot de Telegram con Control Bidireccional
Desarrollar un bot de Telegram integrado al orquestador principal que no solo envíe notificaciones y gráficas de rendimiento, sino que ofrezca control bidireccional interactivo (botones para activar un *Kill Switch*, pausar/reanudar operativas, ajustar parámetros de riesgo en caliente y solicitar reportes detallados de las métricas de R2).

## Acceptance Criteria

### Verificación de Estrategia y Ejecución
- [ ] Debe existir un script de prueba o simulación (`test_hft.py`) que inyecte datos falsos del libro de órdenes (ej. un desequilibrio $> 80\%$) y verifique que el sistema genere la orden Límite correspondiente correctamente formateada.
- [ ] Debe existir una prueba que valide la ejecución concurrente de las lógicas de HFT y Swing Trading sin bloqueos.

### Verificación de Riesgo, Métricas y Tesorería
- [ ] Un script de simulación de caja (`test_tesoreria.py`) que ingrese una racha simulada de pérdidas y ganancias, verificando que el factor de atenuación y el tamaño de posición real se calculan correctamente.
- [ ] La simulación debe validar que al cruzar los umbrales financieros definidos en el plan, se dispare el evento correspondiente (ej. inyección de capital a los 100 USD).
- [ ] Una prueba unitaria que valide que las fórmulas de Win Rate, Capital Acumulado, ROI y Yield devuelven valores matemáticamente correctos tras un conjunto de operaciones simuladas.

### Verificación del Bot de Telegram
- [ ] Debe existir un mock test o script de prueba que valide el enrutamiento de comandos (ej. `MockTelegramClient` simulando el comando *Kill Switch*) y verifique que el orquestador principal pausa su ejecución inmediatamente y puede reportar las métricas de rendimiento actuales.


## 2026-10-07T03:48:12Z

El usuario acaba de proporcionar nuevas reglas, requisitos y estrategias críticas para el proyecto CONTINUITY. Por favor, actualiza los requisitos del proyecto e integra esta información en el trabajo actual (R1, R2, R3) sin reiniciar desde cero, pero asegurando que se incluyan en la arquitectura y auditoría final.

Nuevas Directivas de Negocio:
1. **Cobertura de Mercados**: Todos los deportes (fútbol, béisbol, fútbol americano, básquetbol, tenis, hockey, eSports), con foco principal en partidos en vivo y en tendencia.
2. **Estrategia A (Explotación del Time Decay)**: Scalp de bajo riesgo. Entrar entre minutos 65-70 en partidos estancados (ritmo lento). Comprar share del Empate/Resultado actual y mantener 3-5 minutos para ganar el tick del tiempo, vendiendo antes de que acabe el partido.
3. **Estrategia B (Caza de Reacciones Exageradas)**: Scalp de alto riesgo. Detectar desplomes de precios por pánico (ej. favorito recibe gol pero domina posesión/XG). Comprar el 'dip' y vender en el rebote especulativo tras la primera jugada peligrosa a favor, sin esperar a que anote gol.
4. **Regla de Oro 1 (Spread y Volumen)**: Spread MÁXIMO permitido de $0.03. Si es mayor, no operar.
5. **Regla de Oro 2 (Monitoreo de Bloqueo)**: Monitorear el estado de Binance. Si "MarketStatus: Suspended" (por gol o VAR), bloquear cualquier orden nueva.
6. **Regla de Oro 3 (Dynamic Sizing con Liquidez)**: El cálculo del tamaño de posición debe leer estrictamente el volumen disponible en los primeros 3 niveles del BID para garantizar que siempre haya liquidez de escape ante una salida de emergencia a mercado.

Pasa esta información al Project Orchestrator inmediatamente para que los agentes implementadores ajusten la lógica de HFT/Swing y el manejo de riesgo.


## 2026-10-07T04:18:09Z

El usuario tiene un requisito adicional para la fase final o documentación del sistema. 

Directiva: Mantener la implementación y despliegue en la nube mediante máquinas virtuales de Google Cloud Platform (GCP) (o scripts de despliegue en VM/Docker) que el proyecto original ya contemplaba, pero el usuario solicita cambiar el servidor a una ubicación estratégica (ej. Tokyo o la región AWS/GCP más cercana a los servidores de matching de Binance Spot) para minimizar al máximo la latencia, que es crítica para las estrategias de HFT.

Por favor, indica al Project Orchestrator y al equipo que aseguren que los archivos de despliegue (`Dockerfile`, `cloud-init.yaml` o similares) y la documentación de arquitectura incluyan la configuración para este despliegue en GCP orientado a latencia ultra baja con Binance.


## 2026-10-07T08:38:51Z

ALERTA DE NUEVO REQUISITO: El usuario acaba de proporcionar una nueva estrategia crítica ("Estrategia V: Dynamic Cross-Venue Arbitrage & AMM Bonding-Curve Sniping") para acoplar al sistema CONTINUITY. 

Directivas de la Estrategia V:
1. **Lógica Principal**: Arbitrar desviaciones de curva y sub-colateralización en Binance Predict (YES/NO) usando un precio de referencia externo ($P_{fair}$). Comprar el contrato infravalorado y venderlo en el rebote (horizonte de 2 a 15 segundos máximo).
2. **Paridad Binaria**: Detección determinista de compras duales atómicas si `Best Ask(YES) + Best Ask(NO) < 1.00 - Comisiones`.
3. **Escudo de Riesgo y Latencia**: Integrado con el dimensionamiento del 15%, y liquidación/aborto vía LatencyGuard si toma más de 2.5 segundos o entra en "MarketStatus: Suspended".
4. **Impacto en el Desarrollo Actual**: El usuario pide acoplar esto de manera eficiente **sin dañar ni afectar negativamente el avance actual** que ya lleva el equipo.

Por favor, instruye al Project Orchestrator para que:
- Agregue esto como el Hito / Milestone 6 (o dentro de M3 de forma segura).
- Despliegue un `worker` para implementar `estrategias/arbitraje_amm.py` con estas reglas de micro-arbitraje.
- Añada las pruebas correspondientes y vuelva a certificar antes de la Auditoría de Victoria.


## 2026-10-09T03:49:39Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Use a very large team of agents.

Implement a real-time High-Frequency Trading (HFT) autonomous cloud architecture on GCP. Use a very large team of agents. Generate production-ready Infrastructure as Code (Terraform) with robust error handling to provision Pub/Sub, Dataflow, Compute Engine (C3/C4), Memorystore (Redis), Bigtable, and EventArc, and then **apply the configuration to provision the live resources**.

Working directory: ~/teamwork_projects/hft_gcp_architecture
Integrity mode: demo

## Requirements

### R1. Core Infrastructure Provisioning & Execution
Provision and **deploy** the core HFT GCP architecture using Terraform. This includes Pub/Sub topics/subscriptions for market data ingestion, Dataflow jobs for stream processing, C3/C4 Compute Engine instances (with gVNIC enabled) in the Asia-Northeast region (closest to Binance), Cloud Bigtable for historical tick data, and Cloud Memorystore (Redis) for high-speed state caching.

### R2. Autonomous Safety Orchestration
Configure Cloud EventArc resources to react autonomously to system events, such as network latency spikes or API errors, and route them to an emergency shutdown or alert sink.

### R3. Production-Ready Resilience
The infrastructure code must be designed for production. It should define strict IAM roles, isolated VPC networks for the Compute Engine instances, and secure secret management for API credentials. 

### R4. Architectural Documentation
Generate a detailed markdown report (`architecture_summary.md`) explaining the exact procedure followed, how the infrastructure was optimally validated, and explicitly detailing any missing steps or functions that should be reviewed or added in the future.

## Acceptance Criteria

### Verification & Validation
- [ ] `terraform apply -auto-approve` must run successfully and provision all the requested GCP resources in the user's project.
- [ ] The `architecture_summary.md` file must exist and contain a thorough breakdown of the implemented architecture, validation results, and a checklist of future improvements.
- [ ] Security scanners or manual checks confirm that network isolation (VPC) and IAM least-privilege roles are successfully deployed to the cloud.


## 2026-10-10T14:45:33Z

The server restarted and all subagents were stopped. Please resume the Milestone 6 evaluation and proceed to the Victory Audit.
