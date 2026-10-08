# PACIFICO KyJ — Ecosistema CONTINUITY

**ECOSISTEMA DE ANALISIS DE RESULTADOS Y GESTION DE CAPITAL Y RIESGOS PARA MERCADOS DE APUESTAS DEPORTIVAS.**

> Este documento es la fuente única de verdad sobre qué existe hoy, hacia dónde va el proyecto, y qué falta. Cualquier persona o IA que lo lea debe poder responder tres preguntas sin ambigüedad: **¿qué hace el sistema hoy?**, **¿cuál es el objetivo inmediato de rentabilidad?**, **¿cómo escala a más ligas y más deportes sin rehacerse?**

---

## 0. Norte del proyecto — léase primero

| Pregunta | Respuesta corta |
|---|---|
| **¿Qué es?** | Un fondo cuantitativo institucional diversificado (Fútbol, Baloncesto, Tenis, Béisbol) con motor predictivo multideporte (`continuitis/motor_deportivo.py`), orquestación 24/7 (`GALO.py`), gestión de riesgo financiera estricta (`EscudoFinanciero`, Kelly, P-Value, Clúster 15%), ejecución automatizada en Exchange (`MatchbookClient`) y despliegue en Microsoft Azure. |

| **¿Cuál es el objetivo de rentabilidad a corto plazo?** | *35% a 40%* de rentabilidad mensual combinada reduciendo la varianza estocástica al operar simultáneamente en 4 disciplinas deportivas. |

| **¿Cuál es el objetivo de largo plazo?** | Generar entre 200 y 300 operaciones mensuales auditadas en la nube 24/7 con colocación de órdenes vía REST API en Exchange y monitoreo en tiempo real por Telegram. |

| **¿Cómo escala?** | Mediante la interfaz abstracta `BaseDeporteEngine` e inyección de nuevos deportes en la fábrica `obtener_motor_deportivo`, manteniendo agnósticas e intactas las capas de Auditoría, Escudo Financiero y Persistencia SQLite. |

| **¿Cuál es el estado actual de implementación?** | **Plan Maestro 2027 Completado al 100% (Fases 1 a 6)**. El sistema cuenta con Dockerfile, scripts de despliegue Azure ACI/VM, conector oficial de Matchbook API y orquestador desatendido 24/7. |

**Orden de prioridad actual (no negociable, en este orden):**

1. Cerrar Fase 0 (3 bugs documentados, §12).
2. Conectar `cola_partidos_pendientes` a persistencia real (§13.1) — es el hallazgo más crítico de esta auditoría.
3. Acumular apuestas cerradas por liga hasta el gate estadístico.
4. Solo entonces: automatizar cierre de resultados (Fase 1) y evaluar expansión de ligas o deportes.

Cualquier propuesta que salte este orden (por ejemplo, "agreguemos un deporte nuevo" antes de confirmar edge en fútbol) debe rechazarse por el mismo principio que ya se aplicó a la migración prematura a MySQL: **complejidad sin evidencia que la justifique**.

---


---

## 1. Visión general

PACIFICO KyJ (antes AEGIST/AEGIST MATRIX) es un sistema de decisión cuantitativa para apuestas deportivas que combina:

- Un **motor estocástico-estadístico** (Dixon-Coles + Poisson bivariado) con una capa de **machine learning** (Random Forest + Gradient Boosting) y **aprendizaje online** (EWMA adaptativo).
- Una **capa de datos ETL** propia sobre SQLite, con deduplicación determinista y trazabilidad completa de cada carga.
- Una **capa financiera** de gestión de riesgo (Kelly fraccionado, descuento de overround, penalización por rachas adversas) — esta capa está diseñada para ser **agnóstica al deporte**.
- Una **interfaz de control** en Streamlit que reduce la carga cognitiva de operar el sistema en producción, partido a partido.

El objetivo del ecosistema no es "ganarle al mercado" con una caja negra, sino **construir un sistema auditable, incremental y honesto sobre sus propios límites**: cada ajuste queda documentado con el problema que resuelve, cada capacidad no implementada se declara explícitamente, y ningún ROI se reporta como "confirmado" sin evidencia estadística suficiente.

**Visión final:** un ecosistema maduro y automatizado, con arquitectura propia, que sostenga una rentabilidad neta positiva y verificada por encima de sus costos operativos (APIs, infraestructura), operando sobre fútbol y al menos dos deportes adicionales, con la mínima intervención humana posible en el ciclo diario.

---

## 2. Filosofía y principios de diseño

Estos principios están verificados en el código (docstrings, comentarios de versión, estructura de gaps) y gobiernan cualquier cambio futuro:

| Principio | Cómo se expresa en el código |
|---|---|
| **ROI no es un dial** | 1.5–2% (corto plazo) y 9–10% (largo plazo) son **metas de medición**, no parámetros que se ajustan en el código para "lograrlas". Si el sistema mide 0.3%, el sistema mide 0.3% — la respuesta es más datos o mejor calibración, nunca inflar el número. |
| **Verificar antes de corregir** | Ningún gap se "arregla" sin antes demostrar con datos que existe (ver Fase 0). |
| **Simplicidad sobre complejidad** | Ajustes nuevos se aplican como multiplicadores *post-blend* (p. ej. `factor_tabla_posiciones`, `factor_intensidad_adaptativa_tacde`) en vez de reentrenar modelos — evita invalidar `.pkl`/Parquet ya calibrados. |
| **Desarrollo por fases con evidencia** | `FASE_1_NAFTA` y `FASE_2_EUROPA` en `CONTINUITY.py` son literalmente el gate: no se opera una liga hasta que tiene datos e infraestructura suficiente. El mismo principio aplicará a deportes nuevos (§19). |
| **Cambios quirúrgicos, no scope-creep** | Cada gap (`GAP1`…`GAP13`, `TACDE T-1`…`T-7`) tiene un número, un docstring de "qué resuelve" y compatibilidad regresiva declarada. |
| **La base de datos es la fuente de verdad, no la UI** | `pacificokyj.py` nunca calcula estado de negocio por sí mismo; siempre delega a `CONTINUITY` o consulta `cerebrillum.db`. |
| **Documentar los huecos, no ocultarlos** | `factor_arbitro = 3.5` (constante) se mantiene así **a propósito**, con justificación matemática escrita en el propio código (ver §12). |

---

## 3. Mapa del ecosistema

```
                          ┌───────────────────────────┐
                          │   football-data.co.uk      │
                          │  (CSV estáticos, sin login) │
                          └──────────────┬─────────────┘
                                         │
                       ┌─────────────────▼─────────────────┐
                       │   diana.py  (Capa 1b — Captura)     │
                       │   descarga automática de CSV        │
                       │   formato "main" (EU) + "extra" (AM) │
                       └─────────────────┬─────────────────┘
                                         │ csv_data/*.csv
                       ┌─────────────────▼─────────────────┐
                       │  CEREBELLIUM.py (Capa 2 — ETL)      │
                       │  hash SHA-1 · batch insert · etl_log │
                       └─────────────────┬─────────────────┘
                                         │
                       ┌─────────────────▼─────────────────┐
                       │        cerebrillum.db (SQLite/WAL)   │
                       │  historial_partidos · historial_hot  │
                       │  cuotas_1x2 / ou / ah · dim_equipos   │
                       └───────┬─────────────────┬───────────┘
                               │                 │
             ┌─────────────────▼───┐   ┌─────────▼─────────────┐
             │  CONTINUITY.py        │   │  pacificokyj.py         │
             │  motor predictivo      │◄──┤  UI / orquestador        │
             │  Capas 1–10 (ver §6)   │   │  Streamlit (8 módulos)   │
             └────────────────────────┘   └──────────────────────────┘

                       PURGA.py — mantenimiento transversal
                       (limpia caches/Parquet/.pkl bajo demanda,
                        nunca se ejecuta automáticamente)
```

---

## 4. Índice de archivos fuente

| Archivo | Versión declarada | Rol en el ecosistema | Capa(s) |
|---|---|---|---|
| `requirements.txt` | — | Dependencias Python fijadas (Streamlit, sklearn, pandas, pyarrow…) | Infraestructura |
| `Notas_sobre_los_datos_de_fútbol.txt` | — | Diccionario de columnas de football-data.co.uk | Referencia de datos |
| `Herramientas_o_Modulos_del_Ecosistema...` | — | Glosario conceptual del proyecto en español | Documentación |
| `NORMA_1_-_ESTANDARIZACION...py` | — | Norma interna: nomenclatura de archivos sin sufijos de versión | Gobernanza de código |
| `diana.py` | v1.0 | Captura automática de CSVs desde football-data.co.uk | Capa 1b |
| `CEREBELLIUM.py` | v4.1 | ETL, esquema SQLite, deduplicación, vista `historial_hot` | Capa 2 |
| `CONTINUITY.py` | v4.6 | Motor predictivo completo: estado adaptativo → inferencia → Dixon-Coles → Kelly → auditoría → backtest | Capas 1–10 |
| `pacificokyj.py` | v5.1 | Interfaz Streamlit / orquestador de todo el flujo operativo | UI + Capa 8 (parcial) |
| `PURGA.py` | v1.0 | Limpieza de cachés y del modelo `.pkl` | Mantenimiento transversal |

**Módulos mencionados en la documentación pero sin archivo `.py` verificado** (tratarlos como diseño, no como código operativo): `ARGUS-FEED`/`ARGUS-PORTFOLIO`, `GAIA.py`, `contimarquets.py`.

---

## 5. Componentes del sistema

### 5.1 `diana.py` — Captura automática (Capa 1b)

Reemplaza únicamente el paso manual de "ir a buscar el archivo"; **no decide qué se importa** (eso es de CEREBELLIUM/Capa 2).

- Dos formatos: `"main"` (un CSV por temporada: `E0, SP1, I1, D1, F1, N1, E2`) y `"extra"` (histórico único: `MEX, USA`).
- **Resolución dinámica de temporada vigente**: hace una petición real contra `E0.csv` y retrocede una temporada si el sitio aún no publicó la entrante, evitando un fallo ya documentado en producción (404 en 7 ligas por corte de mes fijo).
- `champions_league` y `concacaf_cl` están **excluidas intencionalmente**: la fuente no las distribuye.
- CLI: `--historico N`, `--forzar`, `--importar`, `--carpeta`. Pensado para `schtasks` diario en Windows.

### 5.2 `CEREBELLIUM.py` — ETL y estructura de datos (Capa 2)

- **Deduplicación por hash SHA-1** de `(fecha, local_id, visita_id)`, calculado antes de tocar la base.
- **Batch insert** con `executemany()` cada `BATCH_SIZE=500` filas.
- **`etl_log`**: trazabilidad de cada corrida.
- **Doble formato** de CSV (europeo vs. americano), detectado automáticamente.
- **`historial_hot`**: `VIEW` que expone las temporadas más recientes (con el bug de `LIMIT 4` global, ver §13.4).
- Incluye `cola_partidos_pendientes`, creada para persistir la cola de apuestas pero **aún no conectada** (§13.1).

### 5.3 `CONTINUITY.py` — Motor predictivo (Capas 1–10)

Ver desglose completo en §6.

### 5.4 `pacificokyj.py` — Interfaz de control (UI)

| Módulo | Qué hace | Capas de CONTINUITY que invoca |
|---|---|---|
| **RADAR** | Estado de temporada por liga, avisos de parón FIFA y Mundial | Ninguna (solo calendario) |
| **INFERENCIA** | Formulario de partido → pipeline completo → probabilidades 1X2 + O/U → señal Kelly | 1 a 8 |
| **CIERRE** | Registra el resultado real, cierra el lazo de feedback y el ROI monetario | 9, 9b |
| **DASHBOARD** | Curva de P&L de la sesión, EV por partido, tasa de acierto real | 9b (lectura) |
| **ETL** | Importación de CSVs desde `csv_data/` | Capa 2 |
| **AUDITORIA** | Integridad de tablas/vistas de la base | Capa 2 |
| **PIPELINE** | Vista de "salud" en vivo de cada capa del motor | Todas (solo lectura) |
| **RENTABILIDAD** | ROI real por liga, sugerencia de reponderación del blend, backtesting bajo demanda | 9b, 10 |

### 5.5 `PURGA.py` — Mantenimiento transversal

1. Purga cachés (Parquet, `__pycache__`, caché de Streamlit).
2. Elimina `modelos_rf/motor_ia.pkl` para forzar reentrenamiento limpio.

Regla explícita: **cachés primero, modelo al final**.

---

## 6. CONTINUITY — el motor predictivo, capa por capa

| Capa | Clase | Responsabilidad | Persistencia |
|---|---|---|---|
| 1 | `EstadoAdaptativo` | Inercia de ataque/defensa por equipo (EWMA lento) | `state.json` |
| 2a | `MotorOnline` | Ganancia adaptativa por equipo, MAE reciente por liga | `state_online.json` |
| 2b | `BlendAdaptativo` | Pondera RF vs. Online por MAE reciente, con nudge opcional por ROI atribuido | `state_blend.json` |
| 3 | `FeatureStore` | Caché Parquet por liga (TTL 24h), invalida por esquema | `feature_store/*.parquet` |
| 4 | `DataPipeline` | Extracción de dataset, features, tabla de posiciones, variables TACDE | `cerebrillum.db` |
| 5 | `MotorInferenciaIA` | RF (300 árboles) + GBM opcional | `modelos_rf/motor_ia.pkl` |
| 6 | `AjustadorCuantico` | Blend de xG, penalización térmica/fatiga/rojas, factores post-blend | — |
| 6b | `RhoDinamicoCalculator` | ρ de Dixon-Coles como función endógena del MAE y de la apertura ofensiva | — |
| 7 | `TransmutadorEstocastico` | Matriz de Poisson bivariado (Dixon-Coles); deriva 1X2 y O/U | — |
| 8 | `EscudoFinanciero` | Kelly fraccionado, overround descontado, filtro EV+edge, penalización por racha | — |
| 9 | `RegistradorFeedback` | Lazo cerrado de error de lambda | `state*.json` |
| 9b | `AuditorRentabilidad` | ROI real por liga/global, racha, ROI por predictor líder | `state_roi.json` |
| 10 | `Backtester` | Simulación walk-forward contra cuotas históricas reales | — |

**Separación relevante para la expansión multideporte (§19):** las capas 7 (Poisson/Dixon-Coles) y 4–6 son **específicas de fútbol**. Las capas 8, 9, 9b y 10 (Kelly, auditoría, backtest) son matemáticamente **agnósticas al deporte** — no mencionan goles, lambdas de Poisson ni nada específico de fútbol en su lógica de decisión financiera.

### Backtester — alcance declarado (Capa 10)

- **Sí mide:** la lógica financiera completa (Kelly + overround + filtro de edge) contra cuotas reales históricas, walk-forward estricto.
- **No mide:** el componente RF/GBM, el ρ dinámico, ni los factores de tabla/TACDE.
- Conclusión explícita: responde a *"¿la capa financiera sería rentable contra cuotas reales con una lambda simple?"*, no a *"¿el sistema completo sería rentable?"*.

---

## 7. TACDE — marco teórico propio

**Teoría de la Adaptación Competitiva Dinámica Evolutiva.** Modela cómo la posición en tabla y la urgencia temporal modifican el rendimiento esperado de un equipo.

| Variable | Significado |
|---|---|
| **PA** (Presión Adaptativa) | Déficit de puntos-por-partido frente al límite de descenso (o al líder, sin descenso) |
| **RC** (Riesgo Clasificatorio) | Distancia normalizada a la posición límite |
| **IA** (Intensidad Adaptativa) | `PA × RC` modulada por urgencia temporal |
| **EC** (Efecto de Confianza) | Racha de victorias consecutivas recientes |

Multiplicador de lambda acotado a `[0.75, 1.25]`, aplicado después de la tabla de posiciones y antes del ρ dinámico.

**Nota de diseño relevante para multideporte:** TACDE está formulado en términos de "tabla de posiciones" y "descenso", conceptos que existen en ligas de todos los deportes de liga regular (baloncesto, béisbol, hockey). Es, por diseño, uno de los componentes **más portables** del sistema.

**Estado de calibración:** pendiente hasta que `AuditorRentabilidad` acumule ≥100 apuestas etiquetadas con señal TACDE activa.

---

## 8. Gestión financiera y control de riesgo

- **Kelly fraccionado al 25%** sobre el mercado de mayor EV (1X2 y, de forma independiente, O/U 2.5).
- **Doble filtro:** `EV_THRESHOLD = 0.05` (5%) **y** `MIN_EDGE_REQUERIDO = 0.02` (2% frente a probabilidad implícita limpia de overround).
- **Overround descontado matemáticamente**, no estimado.
- **Penalización por racha de derrotas**, piso en 30% del stake original.
- **Atribución de rentabilidad por predictor** (RF vs. Online), con nudge acotado (±10 puntos) sobre el blend.

Esta capa es la que debe sostener el objetivo de **1.5–2% ROI** en el corto plazo (§18) — es agnóstica al deporte y por tanto es la base sobre la que se construye la expansión (§19).

---

## 9. Ligas y fases de cobertura

```python
FASE_1_NAFTA = {liga_mx_clausura, liga_mx_apertura, concacaf_cl, mls}
FASE_2_EUROPA = {premier_league, la_liga, serie_a, eredivisie,
                  bundesliga, ligue_1, champions_league, league_one}
```

El desbloqueo de Fase 2 está condicionado a evidencia documentada de Fase 1, no a preferencia. `champions_league` y `concacaf_cl` no reciben CSVs automáticos — deben cargarse manualmente.

---

## 10. Modelo de datos (`cerebrillum.db`)

| Tabla / Vista | Tipo | Propósito |
|---|---|---|
| `dim_ligas` | Tabla | Metadatos por liga: ρ base, λ base, promedio de goles |
| `dim_equipos` | Tabla | ELO, prestigio histórico, altitud, capacidad |
| `historial_partidos` | Tabla | Histórico completo, con `hash_fila` |
| `historial_hot` | **VIEW** | Ventana activa (bug de `LIMIT 4` global, §13.4) |
| `cuotas_1x2` / `cuotas_ou` / `cuotas_ah` | Tablas | Cuotas de mercado, esquema variable |
| `etl_log` | Tabla | Trazabilidad de importaciones |
| `cola_partidos_pendientes` | Tabla | Diseñada para persistir la cola — **no conectada aún** (§13.1) |

---

## 11. Roadmap del proyecto (Fase 0–5 + expansión)

| Fase | Objetivo | Estado |
|---|---|---|
| **Fase 0** | Corregir SLUG-DESYNC, `historial_hot` LIMIT, conectar `cola_partidos_pendientes` | Parches diseñados, **no aplicados** |
| **Fase 1** | Cierre automático de resultados vía API-Football | No iniciada |
| **Fase 1.5** | Validación estadística de edge por liga — gate para el objetivo de 1.5–2% ROI (§18) | No iniciada |
| **Fase 2** | Cuotas pre-partido vía The Odds API + tracking de CLV | No iniciada |
| **Fase 2.5** | Notificador Telegram (`[VALIDADO]` vs `[PAPER]`) | No iniciada |
| **Fase 3** | Migración a MySQL, disparada solo por conflictos de escritura reales de un daemon ARGUS-FEED | No iniciada |
| **Fase 4** | Kelly a nivel de portafolio con penalización por correlación | No iniciada |
| **Fase 5** | Mercados secundarios (hándicap asiático, corners, O/U de tiros) | No iniciada |
| **Fase 6 (nueva)** | Generalización de esquema y Capa 4/5 para admitir un segundo deporte (§19) — **gate: Fase 1.5 confirmada en al menos 2 ligas de fútbol** | No iniciada |
| **Fase 7 (nueva)** | Tercer deporte, reutilizando el trabajo de generalización de la Fase 6 | No iniciada |

**Regla de bloqueo explícita:** ningún deporte nuevo se agrega antes de que Fase 1.5 confirme edge estadístico en fútbol. Agregar superficie de datos sin haber confirmado que el núcleo financiero es rentable es exactamente el tipo de expansión prematura que el proyecto ya rechazó una vez con MySQL.

---

## 12. Deuda técnica activa y gaps documentados

1. **SLUG-DESYNC** — normalización de nombre de equipo distinta entre ETL y UI. **Confirmado presente** (§13.3).
2. **`historial_hot` bug** — `LIMIT 4` global en vez de partición por liga. **Confirmado presente** (§13.4).
3. **`factor_arbitro = 3.5`** — constante de varianza cero, **deferida a propósito**: el RF nunca aprendió señal de esta columna, así que no hay *distribution shift*. Corregirla de verdad exige capturar árbitro real y reentrenar — fuera de alcance actual.

---

## 13. Hallazgos de auditoría de esta revisión

### 13.1 — `cola_partidos_pendientes` existe pero no está conectada (crítico)

`CEREBELLIUM.py` define la tabla con el comentario `[v4.6-GAP13]`. **Sin embargo**, `pacificokyj.py` (`_cola_get/_cola_append/_cola_remove`) sigue operando exclusivamente sobre `st.session_state["cola_partidos"]` — ninguna llamada SQL hacia esa tabla.

**Impacto:** un reinicio del proceso Streamlit pierde cualquier inferencia no cerrada — exactamente el problema que la tabla fue creada para resolver. Auditoría real: 7 de 35+ apuestas de dos meses quedaron registradas en `state_roi.json`.

**Recomendación:** este es el parche quirúrgico de mayor prioridad de Fase 0 — la tabla ya existe, solo falta cablear tres funciones.

### 13.2 — `DIV_LIGA` ya incluye `E2` (contradice el docstring de `diana.py`)

Sin impacto funcional. Es una inconsistencia de documentación: actualizar el docstring de `diana.py`.

### 13.3 — SLUG-DESYNC confirmado en el código actual

```python
# CEREBELLIUM._slug()
for ch in [" ", "-", ".", "'", "/"]:
    s = s.replace(ch, "_")

# pacificokyj._normalizar_equipo_id()
slug = raw.replace(" ", "_").replace("-", "_")   # falta ".", "'", "/"
```

Un equipo con apóstrofe o punto (`"Nott'm Forest"`, `"St. Etienne"`) genera un `equipo_id` distinto según la vía de entrada — fragmentando silenciosamente su historial.

### 13.4 — `historial_hot` sigue con `LIMIT 4` global, no por liga

```sql
CREATE VIEW IF NOT EXISTS historial_hot AS
SELECT * FROM historial_partidos
WHERE temporada IN (
    SELECT DISTINCT temporada FROM historial_partidos
    ORDER BY temporada DESC LIMIT 4
)
```

Selecciona las 4 temporadas más recientes de **todo el sistema combinado**, no por liga. Una liga con etiquetas de temporada distintas o historial más corto puede quedar fuera de la ventana "hot" aunque tenga datos recientes.

---

## 14. Ética y fuentes de datos

- **football-data.co.uk** es la fuente primaria: CSVs estáticos, sin scraping ni credenciales.
- **Flashscore** prohíbe descarga automatizada en sus ToS — descartada como fuente.
- Escalón de acceso a datos en vivo: (1) resultado final vía API gratuita — *donde está el proyecto hoy*; (2) casi tiempo real, requiere revisión de ToS; (3) datos in-play — diferido indefinidamente.

---

## 15. Stack tecnológico

| Categoría | Herramienta | Rol |
|---|---|---|
| UI / orquestación | Streamlit 1.58 | Interfaz de control operativo |
| Base de datos | SQLite (WAL) | Fuente de verdad actual; MySQL planeado tras el trigger de Fase 3 |
| ML | scikit-learn 1.8 (RandomForest, GradientBoosting, TimeSeriesSplit) | Capa 5 |
| Datos | pandas 3.0, numpy 2.4, pyarrow 24.0 | ETL, features, caché Parquet |
| Persistencia de modelos | joblib | `motor_ia.pkl` |
| Visualización | plotly 6.7 | Dashboard financiero |
| HTTP | requests | Descarga de CSVs en `diana.py` |

---

## 16. Cómo ejecutar el sistema

```bash
# 1. Entorno
python -m venv machine
machine\Scripts\activate        # Windows
pip install -r requirements.txt

# 2. Inicializar el esquema de la base de datos
python -c "from CEREBELLIUM import inicializar_schema; inicializar_schema()"

# 3. (Opcional) Descargar datos automáticamente
python diana.py --importar

# 4. Levantar la interfaz de control
streamlit run pacificokyj.py

# 5. Mantenimiento — solo cuando se necesite reentrenar en limpio
python PURGA.py
```

Programación diaria en Windows:
```
schtasks /create /tn "DIANA_Diario" /tr "python C:\ruta\diana.py --importar" /sc daily /st 07:00
```

---

## 17. Convenciones de desarrollo

- **NORMA 1**: nombres de archivo `.py` sin sufijo de versión; la versión vive en un comentario dentro del archivo.
- **Comentarios en español**; nombres de módulo con convención mitológica.
- **Cada gap tiene identificador único** (`GAP1`…`GAP13`, `T-1`…`T-7`) con docstring de qué resuelve, qué compatibilidad mantiene, qué NO cubre.
- **Verificación técnica antes de entrega**: `py_compile`/`ast.parse`, cambios de esquema probados contra SQLite real.
- **Ningún cambio de alcance mayor sin gate explícito.**

---

## 18. Validación estadística y el objetivo de 1.5–2% ROI — análisis crítico

### 18.1 El gate ya definido

`AuditorRentabilidad` (Capa 9b) ya calcula ROI, tasa de acierto y racha por liga. El estándar acordado para declarar "edge confirmado" (Capa 9c, no implementada aún) es:

- **≥100–150 apuestas cerradas por liga** (nunca agregadas globalmente).
- **Intervalo de confianza del ROI que no cruce cero.**
- **Estabilidad fuera de muestra**: el ROI debe sostenerse al dividir el historial en dos mitades temporales.

### 18.2 Crítica cuantitativa directa — este umbral probablemente no alcanza para 1.5–2% ROI

Aquí es donde hay que ser honesto en vez de complaciente: **el tamaño de muestra de 100–150 apuestas fue pensado implícitamente para detectar un edge grande, no uno de 1.5–2%.**

Cálculo de orden de magnitud (heurística estándar en analítica de apuestas deportivas):

- El retorno de una apuesta individual (stake normalizado a 1) tiene una desviación estándar aproximada de **σ ≈ 1.0–1.5**, dependiendo de la cuota promedio operada (a mayor cuota, mayor varianza).
- El error estándar del ROI muestral es `σ / √N`.
- Con `N = 150` y `σ ≈ 1.2`: error estándar ≈ `1.2 / √150 ≈ 0.098` → **±9.8%**.
- Un ROI real de 1.5–2% queda **completamente dentro del ruido** de ±9.8%; el intervalo de confianza al 95% (±~19.2%) cruza cero con enorme margen.

**Conclusión:** para que el intervalo de confianza de un ROI de 1.5–2% no cruce cero, el sistema necesita, en un orden de magnitud realista, **entre 1,500 y 6,000+ apuestas cerradas por liga** (dependiendo de la varianza real observada), no 100–150. Este no es un tecnicismo menor: con la muestra actualmente planeada, el sistema **no podrá distinguir estadísticamente un ROI real de 2% de un ROI real de 0%**, aunque el ROI puntual medido parezca positivo.

### 18.3 Qué hacer con esto (recomendación, no solo diagnóstico)

1. **No cambiar el objetivo de negocio** (1.5–2% sigue siendo una meta de corto plazo razonable y conservadora frente al 9–10% aspiracional).
2. **Sí cambiar el gate de la Capa 9c** para que sea explícito sobre esta limitación: en vez de un número fijo de apuestas, calcular el ancho del intervalo de confianza en cada revisión y exigir que sea menor que el propio ROI objetivo (por ejemplo, IC95% con ancho < 1.5%).
3. **Mientras tanto, tratar cualquier ROI reportado con N < 500 como "señal preliminar", nunca como "edge confirmado"** — esto ya es coherente con el principio de "ROI no es un dial": medir sin engañarse a uno mismo es parte del mismo principio.
4. Este problema es **independiente del deporte** — aplica igual a fútbol que a cualquier deporte futuro (§19), así que conviene resolverlo una sola vez en `AuditorRentabilidad`/Capa 9c antes de replicar el patrón.

Esta es exactamente el tipo de relación entre campos que vale la pena explotar: el problema es idéntico al de **potencia estadística en un ensayo clínico** (detectar un efecto pequeño requiere una muestra mucho mayor que detectar uno grande) — la fórmula y la intuición se importan directamente de bioestadística sin inventar nada nuevo.

---

## 19. Expansión a dos deportes adicionales — requisitos arquitectónicos

### 19.1 Qué ya es reutilizable sin cambios

Estas capas son matemáticamente agnósticas al deporte porque operan sobre probabilidades y dinero, no sobre goles:

- **Capa 8 — `EscudoFinanciero`**: Kelly fraccionado, overround, filtro EV+edge, penalización por racha. No menciona fútbol en ningún lado de su lógica.
- **Capa 9/9b — `RegistradorFeedback` / `AuditorRentabilidad`**: error de predicción y ROI real son conceptos universales.
- **Capa 10 — `Backtester`**: walk-forward contra cuotas reales es igual de válido para cualquier deporte con mercado 1X2/2 vías.
- **TACDE (Capa 6/T-4)**: PA/RC/IA/EC están formulados sobre "tabla de posiciones" y "urgencia temporal", conceptos presentes en cualquier deporte de liga regular (básquetbol, béisbol, hockey, incluso ciclismo por etapas con ajustes menores).

### 19.2 Qué debe generalizarse (esto es el verdadero costo de la expansión)

| Componente actual | Problema para multideporte | Qué se necesita |
|---|---|---|
| `CEREBELLIUM.py` — esquema `historial_partidos` | Columnas específicas de fútbol (`goles_local`, `tiros_puerta_local`, `corners_local`) | Esquema con columnas núcleo agnósticas (`puntuacion_local`, `puntuacion_visitante`, `metrica_1..N` genéricas) + tabla de metadatos por deporte que declare qué columnas aplican |
| `CONTINUITY.py` — Capa 4 `DataPipeline` | Métodos como `_forma()`, `_h2h()` asumen "goles" | Extraer una interfaz `PipelineDeporte` con implementación `PipelineFutbol` actual; un deporte nuevo implementa la misma interfaz sin tocar Capas 7–10 |
| `CONTINUITY.py` — Capa 7 `TransmutadorEstocastico` | Dixon-Coles/Poisson bivariado es específico de deportes de bajo scoring discreto (fútbol, hockey) | Para un deporte de scoring alto/continuo (básquetbol) se necesita un modelo distinto (p. ej. distribución normal sobre el margen de puntos); para deportes de "quien gana" puro (tenis, boxeo) un modelo logístico simple basta. Este es un módulo nuevo por deporte, no una generalización del existente |
| `diana.py` | Fuente de datos específica de football-data.co.uk | Cada deporte nuevo requiere su propia fuente de datos gratuita/barata evaluada bajo el mismo criterio ético (§14) antes de integrarse |

### 19.3 Criterio de selección del próximo deporte (recomendación)

Para minimizar el costo de generalización, el **primer candidato lógico es un deporte con mercado 1X2 o 2 vías y scoring discreto bajo**, porque reutiliza directamente Dixon-Coles/Poisson sin nuevo modelo estadístico (ejemplo: hockey sobre hielo, water polo). Un deporte de scoring alto (baloncesto) o de resultado binario puro (tenis) es más simple en el modelo pero exige escribir la Capa 7 desde cero — es una decisión de trade-off que debe tomarse **después**, no antes, de tener el gate de la Capa 9c resuelto en fútbol (§18).

### 19.4 Gate de expansión (no negociable)

No se inicia trabajo de generalización de esquema hasta que:
1. Al menos 2 ligas de fútbol tengan edge confirmado bajo el gate corregido de §18.3.
2. `cola_partidos_pendientes` esté conectada y en uso real (§13.1) — de lo contrario, cualquier deporte nuevo hereda el mismo problema de pérdida de datos.

---

### Nota de mantenimiento de este documento

Este README refleja el estado del código en la fecha de esta auditoría. Como el proyecto evoluciona por parches quirúrgicos incrementales, **cualquier discrepancia futura entre este documento y el código debe resolverse a favor del código**, y debe documentarse explícitamente la próxima vez que se regenere este archivo.
