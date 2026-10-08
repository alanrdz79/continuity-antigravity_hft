# REPORTE DE INSPECCIÓN Y PROSPECCIÓN ARQUITECTÓNICA DEL REPOSITORIO
**Proyecto**: CONTINUITY HFT — Ecosistema Algorítmico y Predictivo  
**Ruta del Workspace**: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM`  
**Fecha de Inspección**: 2026-10-07  
**Auditor**: Teamwork Explorer (Repo Surveyor)

---

## 1. Resumen Ejecutivo

El repositorio `CONTINUITYEM` alberga la base tecnológica del ecosistema **CONTINUITY v6.5 / v7.1**, originalmente desarrollado como un motor de trading deportivo de alta frecuencia (HFT) sobre la casa de intercambio **Matchbook MX**, complementado con modelos cuantitativos y almacenamiento relacional MLOps en SQLite (`cerebrillum.db` con >17,000 partidos y registros).

El entorno de ejecución actual es **Python 3.14.2** sobre Windows, con un entorno virtual `.venv` completamente funcional y aprovisionado con librerías numéricas modernas (`numpy 2.4.6`, `scipy 1.17.1`, `pandas 3.0.3`, `scikit-learn 1.8.0`), librerías de asincronía (`websockets 17.1`, `aiohttp 3.14.3`, `anyio 4.13.0`), testing (`pytest 9.1.1`), y bypass de protecciones (`curl_cffi 0.16.3`).

El nuevo mandato arquitectónico (definido en `PLANnew.md` y `ORIGINAL_REQUEST.md` a fecha 2026-10-07) requiere la evolución o integración hacia un **motor autónomo de trading de alta frecuencia (CONTINUITY HFT) para los mercados de predicción deportiva de Binance Spot**. Este nuevo sistema demanda una arquitectura desacoplada de 6 submódulos con concurrencia asíncrona (WebSocket L2, cálculo de desequilibrio de libro *Order Book Imbalance*, estrategias paralelas HFT + Swing Trading, Escudo Financiero con atenuación exponencial de racha, Tesorería de ordeño e inyección escalonada $10 \to $100 \to $1,000 USD, y un bot de Telegram con control bidireccional interactivo y botón de pánico *Kill Switch*).

---

## 2. Inventario del Repositorio y Estructura de Directorios

### 2.1 Árbol de Archivos Existente

```
c:\Users\alanr\AE_ecosistema\CONTINUITYEM\
│
├── .antigravityrules           # Reglas del proyecto: async puro, memoria RAM + SQLite async, UTF-8
├── .env                        # Variables de entorno (Telegram token/chat, Matchbook credentials, USD/MXN)
├── Dockerfile                  # Imagen Python 3.11-slim para despliegue en Azure/Cloud
├── cloud-init.yaml             # Script de inicialización cloud (Ubuntu/Debian) para systemd galo.service
├── PLANnew.md                  # Especificación técnica del nuevo motor CONTINUITY HFT Binance
├── README.md                   # Documentación del sistema actual Matchbook HFT v2.0
├── requirements.txt            # Dependencias base declaradas (10 librerías)
├── cerebrillum.db              # Base de datos SQLite principal (18.8 MB, 25 tablas/vistas históricas)
├── test_metrics.sqlite         # Base SQLite de pruebas unitarias de métricas HFT
│
├── conectores/                 # [Capa de Red y APIs Externas]
│   ├── __init__.py
│   ├── base.py                 # ConectorBase con Token Bucket RateLimiter sincrónico y retries
│   ├── matchbook_async.py      # Cliente Matchbook API con curl_cffi (impersonate="chrome120")
│   ├── telegram_bot.py         # Notificador Telegram unidireccional (POST /sendMessage)
│   └── LEEME.md
│
├── continuitis/                # [Capa de Inteligencia Cuantitativa y Memoria]
│   ├── __init__.py
│   ├── constantes.py           # Constantes globales, umbrales Kelly, comisiones, helpers SQL
│   ├── financiero.py           # EscudoFinanciero, AlmgrenChriss, WassersteinDRO, ControladorCluster, MotorInteresCompuesto
│   ├── microestructura.py      # CalculadorVWAP, AjustadorComisiones, EstrategiaMakerTaker
│   ├── memoria_hft.py          # HFTMemoryStore (RAM dict + batch flush asíncrono a SQLite)
│   ├── LEEME.md
│   ├── README.md
│   └── db_metrics/
│       └── metricas_hft.sqlite # Almacén SQLite para telemetría de trades HFT
│
├── orquestadores_principales/  # [Capa de Orquestación y Demonios de Ejecución]
│   ├── HFT_GALO.py             # Demonio principal Matchbook v2.0 (Estrategias A, B, C; GC a 45s; Circuit Breakers)
│   └── LEEME.md
│
├── pruebas_unitarias/          # [Capa de Validación y Pruebas]
│   ├── test_microestructura.py # Pruebas de VWAP, Comisiones y selección Maker/Taker
│   └── LEEME.md
│
├── documentacion_oficial/      # [Guías Institucionales y Directrices]
│   ├── CONTINUITYEM_README.md  # Documento técnico detallado
│   ├── instrucciones_generales.md # Principios de arquitectura por capas, justificación y dependencias
│   ├── SKILL.md                # Skill de arquitectura HFT
│   └── LEEME.md
│
└── Scripts Sueltos en Raíz (Ad-hoc / Scratch):
    ├── check_db.py             # Script de inspección de cerebrillum.db
    ├── consulta_mercados.py    # Consulta de liquidez y spreads en Matchbook
    ├── demo_trade.py           # Demostración de colocación de orden en Matchbook
    ├── fix.py, fix_100.py, fix_mb.py, fix_report.py, fix_tg.py # Scripts utilitarios de parches regex
    ├── test_db.py              # Prueba de recuperación de racha y bankroll en HFTMemoryStore
    ├── test_hb.py              # Prueba de heartbeat en Matchbook
    └── test_hft.py             # Prueba de MotorInteresCompuesto y circuit breakers
```

### 2.2 Bases de Datos Relacionales SQLite

1. **`cerebrillum.db` (18.8 MB)**:
   - Contiene 25 entidades (tablas y vistas), incluyendo:
     - `historial_partidos` (17,647 filas, 50 columnas)
     - `cuotas_1x2` (16,758 filas)
     - `cuotas_ou` (5,871 filas)
     - `cuotas_ah` (5,871 filas)
     - `dim_equipos` (509 filas)
     - `dim_ligas` (14 filas)
     - `dim_equipos_geo` (53 filas con altitud y temperatura)
     - `cola_partidos_pendientes` (gestión de clústeres y concurrencia)
     - `apuestas_cerradas` (auditoría de rendimiento histórico)
2. **`continuitis/db_metrics/metricas_hft.sqlite`**:
   - Tabla `hft_metrics` con columnas: `id, timestamp, evento, deporte, mercado, stake, cuota_ofrecida, ev_neto, roi_esperado, resultado, ganancia_real, bankroll_momento`.

---

## 3. Auditoría del Entorno de Ejecución y Dependencias

### 3.1 Versión de Python y Sistema Operativo
- **OS**: Windows (PowerShell / Windows 11).
- **Python**: **Python 3.14.2** (tanto global en `C:\Python314` como en `.venv\Scripts\python.exe`).
- **Estado de Compilación / Binarios**: La presencia de `numpy 2.4.6`, `scipy 1.17.1`, `pandas 3.0.3`, y `curl_cffi 0.16.3` operando sobre Python 3.14.2 confirma que los enlaces de extensiones en C/C++ están correctamente instalados.

### 3.2 Comparativa de Dependencias: `requirements.txt` vs `.venv`

| Paquete | Declarado en `requirements.txt` | Instalado en `.venv` | Rol / Observaciones |
|---|---|---|---|
| `numpy` | `>=1.24.0` | `2.4.6` | Motor de cálculo matricial y vectorial |
| `pandas` | `>=2.0.0` | `3.0.3` | Manipulación de datos tabulares (offline) |
| `scipy` | `>=1.10.0` | `1.17.1` | Cálculos estadísticos y optimización |
| `scikit-learn` | `>=1.2.0` | `1.8.0` | Modelado de machine learning |
| `playwright` | `>=1.38.0` | `1.62.0` | Automatización headless de navegador |
| `requests` | `>=2.31.0` | `2.34.2` | Peticiones HTTP sincrónicas |
| `schedule` | `>=1.2.0` | `1.2.2` | Planificador de tareas de fondo |
| `pytz` | `>=2023.3` | `2026.3.post1` | Manejo de zonas horarias (BST/CDMX) |
| `websockets` | *No declarado* | **`17.1`** | **Crítico para L2 WebSocket Stream de Binance** |
| `aiohttp` | *No declarado* | **`3.14.3`** | **Crítico para cliente REST asíncrono** |
| `curl_cffi` | *No declarado* | `0.16.3` | Cliente con TLS bypass para Cloudflare |
| `pytest` | *No declarado* | `9.1.1` | Framework de pruebas unitarias |
| `orjson` | *No declarado* | `3.12.0` | Serialización JSON de ultra-alta velocidad |
| `python-dotenv` | *No declarado* | `1.2.3` | Carga de variables de entorno `.env` |
| `pytest-asyncio` | *No declarado* | **No instalado** | **Faltante para pruebas asíncronas de pytest** |
| `python-telegram-bot` | *No declarado* | **No instalado** | Faltante si no se implementa cliente aiohttp directo |

### 3.3 Diagnóstico de Pruebas Unitarias
Al ejecutar `pytest` directamente en la raíz:
1. `ModuleNotFoundError: No module named 'continuitis'` debido a la ausencia de `pytest.ini` o `pyproject.toml` que declare `pythonpath = .`.
2. Al ejecutar `python -m pytest`:
   - `pruebas_unitarias/test_microestructura.py` pasó las 4 pruebas unitarias (100% OK).
   - `test_hb.py` falló porque es un script suelto en raíz con una función `async def test()` que pytest recolecta por error y rechaza al no tener un plugin de ejecución asíncrona configurado.
   - `test_db.py` arrojó una advertencia de recolección porque define la clase `TestHFTMemoryStore(HFTMemoryStore)` con un constructor `__init__`.

---

## 4. Análisis de Componentes Existentes vs. Reutilizables

| Componente | Archivo Fuente | Estado Actual | Viabilidad de Reutilización para Binance HFT |
|---|---|---|---|
| **Calculador VWAP** | `continuitis/microestructura.py` | Implementado y probado | **100% Reutilizable**. Algoritmo de barrido ponderado del libro $L2 Depth$. |
| **HFT Memory Store** | `continuitis/memoria_hft.py` | Implementado | **90% Reutilizable**. Registro en RAM sub-milisegundo + guardado asíncrono a SQLite (`hft_metrics`). Requiere adaptar esquema a símbolos/órdenes de Binance. |
| **Controlador de Clúster** | `continuitis/financiero.py` | Implementado | **85% Reutilizable**. Regla de techo del 15% del bankroll en riesgo simultáneo mediante factor atenuador en `[0, 1]`. |
| **Motor de Interés Compuesto** | `continuitis/financiero.py` | Implementado (Matchbook) | **75% Reusable con adaptación**. Contiene Kelly dinámico, pero tiene límites fijos de Matchbook ($40 MXN). Debe incorporar las fórmulas de `PLANnew.md`. |
| **Ajustador de Comisiones** | `continuitis/microestructura.py` | Implementado (Matchbook 2%) | **Adaptar**. Binance cobra comisiones porcentuales sobre nocional (Maker/Taker en BNB, ej. 0.075%-0.1%), no solo sobre ganancias netas. |
| **Notificador Telegram** | `conectores/telegram_bot.py` | Unidireccional (POST REST) | **Extender/Refactorizar**. Solo emite mensajes. El requerimiento R3 exige control bidireccional interactivo (botones, comandos, Kill Switch). |
| **Cliente Matchbook** | `conectores/matchbook_async.py` | Específico para Matchbook | **Preservar intacto**. El nuevo sistema necesita un conector paralelo para Binance Spot (`conectores/binance_async.py`). |
| **Orquestador GALO** | `orquestadores_principales/HFT_GALO.py` | Específico para Matchbook | **Preservar intacto**. El nuevo sistema debe implementar `orquestadores_principales/orquestador_continuity.py`. |

---

## 5. Análisis de Brecha (Gap Analysis) frente a los Requisitos de CONTINUITY HFT

De acuerdo con `ORIGINAL_REQUEST.md` (fecha 2026-10-07) y `PLANnew.md`:

### 5.1 Requisito R1: Arquitectura de Ejecución y Estrategias Mixtas
- **WebSocket y Order Book Imbalance**:
  - *Brecha*: Actualmente el sistema depende de HTTP polling a la API de Matchbook. Binance requiere ingesta persistente vía WebSocket (`wss://stream.binance.com:9443/ws/<symbol>@depth10@100ms`).
  - *Fórmula requerida*: $I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$.
  - *Ciclo de 4 Fases*: Fase 1 (HFT Pre-Match con $I \ge 0.60$), Fase 2 (Transición 5 min antes con `limpiar_mesa`), Fase 3 (In-Play Sniping), Fase 4 (Time Decay exponencial).
  - *Estrategia Swing Trading Concurrente*: Se requiere diseñar e integrar un módulo de Swing Trading desacoplado que opere en paralelo sin bloquear el event loop.

### 5.2 Requisito R2: Motor de Riesgo, Métricas y Tesorería
- **Fórmula de Tamaño de Posición Real**:
  $$\text{Tamaño de Posición} = \frac{\text{Balance Total} \times \text{Porcentaje de Riesgo}}{\text{Porcentaje de Stop Loss}}$$
  Modulado por factor de racha adversa ($0.85^{\text{perdidas\_consecutivas}}$) y techo de clúster (15%).
- **Submódulo de Ordeño e Inyección ($10 \to 100 \to 1,000 USD$)**:
  - Capital base inicial: $10 USD.
  - Hito $100 USD: Inyección autorizada de $100 USD adicionales.
  - Hito $1,000 USD: Activación de cosecha autónoma (35% retiro a MXN, y del 65% restante: 40% operación, 60% reinversión compuesta).
- **Métricas Clave Continuas**:
  - Win Rate ($WR = \frac{\text{Ganadas}}{N}$).
  - Retorno sobre la Inversión ($ROI$).
  - Yield ($\frac{\text{Ganancia Neta}}{\text{Volumen Total Operado}}$).
  - Capital Acumulado ($B_N = B_0 \prod (1 + f_i R_i)$).

### 5.3 Requisito R3: Bot de Telegram con Control Bidireccional
- **Control Interactivo**:
  - Botón/Comando de **Kill Switch** (activa `boton_panico()`, cancela órdenes abiertas y pausa el motor inmediatamente).
  - Pausar / Reanudar operativas.
  - Ajuste dinámico de parámetros de riesgo en caliente.
  - Consulta bajo demanda de métricas en tiempo real ($WR$, $ROI$, $Yield$, Balance).
- *Brecha*: El conector actual en `conectores/telegram_bot.py` no recibe mensajes ni procesa callbacks.

---

## 6. Recomendación de Diseño y Organización del Código

Siguiendo las directrices institucionales de `documentacion_oficial/instrucciones_generales.md` (Arquitectura por Capas, No invasiva, Respeto de código existente y Cero complejidad innecesaria), se propone la siguiente estructura modular:

### 6.1 Disposición del Código Propuesta

```
c:\Users\alanr\AE_ecosistema\CONTINUITYEM\
│
├── pytest.ini                            # Configuración de pruebas (pythonpath = ., testpaths)
├── pyproject.toml                        # Metadatos del proyecto y configuración de herramientas
├── requirements.txt                      # Dependencias consolidadas y depuradas
│
├── conectores/
│   ├── base.py                           # [Capa 1] Se agrega AsyncRateLimiter token bucket
│   ├── matchbook_async.py                # [Capa 1] (Preservado para Matchbook)
│   ├── telegram_bot.py                   # [Capa 1] (Preservado / extendido)
│   ├── telegram_bidireccional.py         # [Capa 1] Cliente interactivo con polling/callbacks y MockTelegramClient
│   └── binance_async.py                  # [Capa 1] Cliente WebSocket L2 depth + REST firmado para Binance Spot
│
├── continuitis/
│   ├── constantes.py                     # [Capa 0] Constantes globales actualizadas con parámetros Binance
│   ├── financiero.py                     # [Capa 6] Preservado con métodos de apoyo
│   ├── microestructura.py                # [Capa 3] VWAP, Maker/Taker y nuevo calculador OrderBookImbalance
│   ├── memoria_hft.py                    # [Capa 5] HFTMemoryStore extensible para Binance
│   ├── riesgo_binance.py                 # [Capa 6] EscudoFinancieroHFT, fórmula Stop Loss, atenuación 0.85
│   ├── tesoreria.py                      # [Capa 6] TreasuryAndHarvestingManager (reglas 10 -> 100 -> 1,000 USD)
│   ├── auditor_metricas.py               # [Capa 5] StateRegistry & MetricAuditor (WR, ROI, Yield, Turnover)
│   └── estrategias/
│       ├── __init__.py
│       ├── hft_microestructura.py        # [Capa 8] Estrategia HFT 4 Fases (Pre-Match, Minute 0, In-Play, Decay)
│       └── swing_trading.py              # [Capa 8] Estrategia ortogonal de Swing Trading para Binance
│
├── orquestadores_principales/
│   ├── HFT_GALO.py                       # [Capa 8] (Preservado para Matchbook)
│   └── orquestador_binance.py            # [Capa 8] Orquestador CONTINUITY HFT Binance (Master Daemon)
│
└── pruebas_unitarias/
    ├── test_microestructura.py           # Pruebas existentes (VWAP, comisiones)
    ├── test_hft.py                       # Prueba de Imbalance > 80% y concurrencia HFT + Swing
    ├── test_tesoreria.py                 # Prueba de simulación de caja, racha 0.85, hitos y métricas WR/ROI/Yield
    └── test_telegram.py                  # Prueba de MockTelegramClient y activación de Kill Switch
```

### 6.2 Justificación de Capas (por `instrucciones_generales.md`)

| Capa | Módulos Propuestos | Problema que Resuelve | Impacto en el Sistema |
|---|---|---|---|
| **Capa 1 (Conexión / Red)** | `binance_async.py`, `telegram_bidireccional.py` | Falta de conector a Binance Spot y falta de escucha de comandos de Telegram. | Habilita ingesta L2 a baja latencia y control interactivo sin alterar conectores existentes. |
| **Capa 3 (Microestructura)** | `calculador_imbalance` en `microestructura.py` | Cálculo formal del desequilibrio de oferta/demanda $I$ según fórmula de PLANnew.md. | Provee la señal cuantitativa elemental para disparar órdenes Maker en Fase 1. |
| **Capa 5 (Telemetría / Métricas)** | `auditor_metricas.py`, `memoria_hft.py` | Cálculo matemático exacto de Win Rate, ROI, Yield sobre volumen y persistencia inmutable en SQLite. | Visibilidad financiera total y auditoría requerida por el criterio de aceptación. |
| **Capa 6 (Riesgo y Tesorería)** | `riesgo_binance.py`, `tesoreria.py` | Dimensionamiento de postura por Stop Loss, atenuación $0.85^k$, techo del 15% y ciclo de vida financiero ($10 \to 100 \to 1,000 USD$). | Evita la ruina, frena rachas y ejecuta los retiros e inyecciones automáticas de forma determinista. |
| **Capa 8 (Estrategias y Orquestación)** | `hft_microestructura.py`, `swing_trading.py`, `orquestador_binance.py` | Ejecución concurrente sin bloqueos de HFT y Swing Trading; botón de pánico *Kill Switch*. | Orquestador principal desacoplado que coordina todos los subsistemas. |

---

## 7. Gestión de Dependencias Recomendadas

De acuerdo con las reglas institucionales para dependencias:

1. **`websockets` (Ya instalada en venv: 17.1)**:
   - *Ventajas*: Protocolo nativo de Python para WebSocket, latencia ultrabaja, cero sobrecarga.
   - *Desventajas*: Requiere gestión manual de reconexión y heartbeats ping/pong.
   - *Requisitos*: Ya presente en el entorno.
   - *Impacto*: Rendimiento óptimo en el procesamiento del feed L2.

2. **`aiohttp` (Ya instalada en venv: 3.14.3)**:
   - *Ventajas*: Cliente HTTP asíncrono estándar, permite llamadas a la REST API de Binance y Telegram con `ClientSession` reutilizable sin dependencias pesadas de terceros.
   - *Desventajas*: Ninguna relevante.
   - *Impacto*: Permite implementar tanto el cliente Binance Spot como el Telegram Bot interactivo (long polling asíncrono con `getUpdates`) manteniendo la compatibilidad nativa con Python 3.14.

3. **`pytest-asyncio` (Recomendada para instalación)**:
   - *Ventajas*: Permite ejecutar directamente funciones de prueba `async def` en `pytest` sin envoltorios manuales.
   - *Alternativa ligera sin instalación adicional*: Como `anyio` ya está instalado en el venv (v4.13.0), se pueden usar los fixtures de AnyIO o envolver las pruebas asíncronas con `asyncio.run()`, garantizando cero dependencias externas obligatorias si el usuario prefiere no instalar librerías adicionales.

4. **Configuración de Testing (`pytest.ini`)**:
   - Crear un archivo `pytest.ini` mínimo en la raíz:
     ```ini
     [pytest]
     pythonpath = .
     testpaths = pruebas_unitarias
     python_files = test_*.py
     ```
   - Esto soluciona de inmediato el `ModuleNotFoundError` y previene que pytest recolecte scripts de prueba scratch en la raíz.

---

## 8. Conclusiones y Próximos Pasos

1. **Estado de la Base de Código**: El proyecto cuenta con fundamentos matemáticos y de microestructura sólidos (`CalculadorVWAP`, `HFTMemoryStore`, `ControladorCluster`), desarrollados previamente para Matchbook.
2. **Estrategia de Evolución**: No se debe sobreescribir ni romper el código de Matchbook (`HFT_GALO.py`, `matchbook_async.py`), sino introducir los módulos de Binance (`binance_async.py`, `riesgo_binance.py`, `tesoreria.py`, `auditor_metricas.py`, `orquestador_binance.py`, `telegram_bidireccional.py`) en sus capas correspondientes.
3. **Validación Inmediata Requerida**: Crear el archivo de configuración `pytest.ini` para estandarizar la suite de pruebas y preparar los scripts de prueba de aceptación especificados (`test_hft.py`, `test_tesoreria.py`, y test de Telegram con `MockTelegramClient`).
