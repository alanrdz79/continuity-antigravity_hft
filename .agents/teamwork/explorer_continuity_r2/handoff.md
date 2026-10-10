# INFORME DE INVESTIGACIÓN R2: TESORERÍA AUTÓNOMA, FÓRMULAS FINANCIERAS Y EARLY EXIT POR TARGET EV (DEPORTES Y ESPORTS)

**Investigador**: Explorer 2 (Treasury Financial Explorer)  
**Fecha**: 2026-10-10  
**Directorio de Trabajo**: `c:\Users\alanr\AE_ecosistema\CONTINUITYEM\.agents\teamwork\explorer_continuity_r2`  
**Objetivo**: Auditoría técnica exhaustiva del Módulo de Tesorería Autónoma y Fórmulas Financieras (Requisito R2), verificación de criterios de aceptación, análisis del nuevo requerimiento de Target EV para salida temprana pre-match e in-play (Deportes y ESports), y propuesta de cambios concretos.

---

## 1. OBSERVACIÓN (Direct Observations)

### 1.1 Archivos del Código Fuente Auditados
- `continuitis/tesoreria.py` (251 líneas)
- `continuitis/riesgo_binance.py` (441 líneas)
- `continuitis/auditor_metricas.py` (355 líneas)
- `continuitis/financiero.py` (732 líneas)
- `continuitis/constantes.py` (272 líneas)
- `estrategias/hft_engine.py` (1491 líneas)
- `orquestadores_principales/HFT_BINANCE.py` (655 líneas)
- `test_tesoreria.py` (307 líneas)
- `pruebas_unitarias/test_tesoreria.py` (322 líneas)
- `pruebas_unitarias/test_metricas.py` (269 líneas)
- `pruebas_unitarias/test_riesgo_tesoreria_metricas.py` (298 líneas)

---

### 1.2 Formulación Matemática Implementada vs Requerida

| Requisito R2 | Estado en Codebase | Archivo y Ubicación | Observación Verbatim / Cita Exacta |
|---|---|---|---|
| **Criterio de Kelly ($f^*$)** | ⚠️ **Faltante en motor Binance** | `continuitis/riesgo_binance.py` | La búsqueda de `kelly` en `riesgo_binance.py` devuelve **0 resultados**. `EscudoFinancieroBinance` solo implementa sizing por stop loss (líneas 235-238): `posicion_nominal = riesgo_objetivo / stop_loss_efectivo`. Kelly solo existe en el módulo legacy 1X2 Matchbook (`continuitis/financiero.py:60`). |
| **Tamaño de Posición Real** | ✅ Implementado (con gap de precisión) | `continuitis/riesgo_binance.py:234-263` | `riesgo_objetivo = balance * self.pct_riesgo_fijo * factor_racha`, `posicion_nominal = riesgo_objetivo / stop_loss_efectivo`. Acotado por techo de clúster (15%) y liquidez Top 3 BIDs. |
| **Atenuación por Racha ($0.85^n$)** | ✅ Implementado | `continuitis/riesgo_binance.py:108-113, 417-433` | `factor_racha = 0.85 ** self.consecutive_losses`. Incrementa en pérdida y resetea a 1.0 en victoria. |
| **Techo de Clúster (15%)** | ✅ Implementado | `continuitis/riesgo_binance.py:240-272` | `max_cluster_capital = balance * self.max_cluster_exp` (0.15). Se comprime o rechaza si se supera. |
| **Límite Liquidez Top 3 BID (GR3)** | ✅ Implementado | `continuitis/riesgo_binance.py:275-296` | Si `posicion_nominal > v_bid_top3`, se acota. Si `v_bid_top3 <= 0`, rechaza por violación de Regla de Oro 3. |
| **Valor Esperado ($EV$)** | ✅ Implementado | `continuitis/riesgo_binance.py:128-158` | `cuota_neta = 1.0 + (cuota_bruta - 1.0) * (1.0 - fee)`, `EV = (P * cuota_neta) - 1.0`. Umbral mínimo: $EV \ge 0.015$. Descuento BNB (0.075%). |
| **Capital Acumulado (Interés Compuesto)** | ✅ Implementado | `continuitis/auditor_metricas.py:151-195` | $B_N = B_0 \prod_{i=1}^N (1 + f_i R_i)$, donde $f_i = S_i / B_{i-1}$, $R_i = \text{PnL}_i / S_i$. |
| **ROI** | ✅ Implementado | `continuitis/auditor_metricas.py:196-204` | $\text{ROI} = \sum \text{PnL} / B_0$. |
| **Yield** | ✅ Implementado | `continuitis/auditor_metricas.py:205-213` | $\text{Yield} = \sum \text{PnL} / \sum S_i$ (turnover total). |
| **Win Rate ($WR$)** | ✅ Implementado | `continuitis/auditor_metricas.py:143-150` | $WR = \text{Ganadas} / N$. |

---

### 1.3 Precisión Matemática (4 Decimales: 0.0001)

| Métrica | Precisión Actual en Código | Línea de Código | Observación |
|---|---|---|---|
| **Win Rate** | 4 decimales (`0.0001`) | `auditor_metricas.py:333` | `round(wr, 4)` en `obtener_metricas()`. |
| **EV** | 4 decimales (`0.0001`) | `riesgo_binance.py:302` | `round(ev, 4)` en `calcular_posicion()`. |
| **ROI** | 4 a 6 decimales | `auditor_metricas.py:335, 309` | `round(roi, 4)` en `obtener_metricas()` y `round(..., 6)` en `validar_compuerta()`. |
| **Tamaño de Posición (Stake)** | ⚠️ **2 decimales (`0.01`)** | `riesgo_binance.py:304-305` | `"stake": round(posicion_nominal, 2)`. Un valor de `9.211875` se redondea a `9.21`, perdiendo los decimales 3 y 4 (`0.0019`). No garantiza precisión al cuarto decimal (0.0001). |
| **Capital Acumulado** | ⚠️ **2 decimales en reporte** | `auditor_metricas.py:334` | `"capital_acumulado": round(cap_acumulado, 2)`. |

---

### 1.4 Hitos de Crecimiento ($10 \to \$100 \to \$1,000$ USD) y Cosecha Autónoma (Harvesting)

En `continuitis/tesoreria.py`:
1. **$10 \to \$100$ USD (Inyección Condicionada)**:
   - Requiere validación estadística previa: $N \ge 300$, $p\text{-value} < 0.05$ ($Z > 1.645$), $EV / \text{Yield} > 0$.
   - Al aprobarse, inyecta +100 USD (`self.balance += 100.0`, `self.hito_100_inyectado = True`).
2. **Fase de Aceleración ($<\$1,000$ USD)**:
   - Corte mensual: 40% gastos operativos, 60% reinversión compuesta, 0% retiro.
3. **Meta de 4 Cifras ($\ge \$1,000$ USD) y Cosecha Autónoma**:
   - En `verificar_hitos()` (líneas 115-124):
     ```python
     if self.balance >= UMBRAL_COSECHA_1000:
         if not self.meta_1000_activada:
             self.meta_1000_activada = True
             acciones.append("MODO_COSECHA_AUTONOMA_DISPONIBLE")
     ```
     **Hallazgo crítico**: `verificar_hitos()` **solo activa la bandera** `meta_1000_activada = True`. No ejecuta la cosecha, no aisla el 35% de utilidades netas, ni retiene los fondos en ninguna variable de reserva.
   - En `corte_mensual()` (líneas 204-219):
     ```python
     retiro_35 = ganancia_mensual * PCT_COSECHA_AUTONOMA
     retiro_mxn = retiro_35 * fx
     utilidad_restante = ganancia_mensual - retiro_35
     operacion_40 = utilidad_restante * PCT_GASTOS_OPERACION
     reinversion_60 = utilidad_restante * PCT_REINVERSION_COMPUESTA
     self.balance = (self.balance - ganancia_mensual) + reinversion_60
     ```
     La matemática de distribución es correcta ($35\%$ retiro, $26\%$ operación, $39\%$ reinversión), pero **requiere que un agente externo invoque manualmente `corte_mensual()` pasando `ganancia_mensual`**.
   - `GestorTesoreria` carece de un método autónomo `ejecutar_cosecha_autonoma()` que calcule la utilidad neta de forma automática y asile los fondos en contenedores contables específicos (`capital_aislado_cosecha_usd`, `capital_aislado_cosecha_mxn`, `fondo_gastos_operacion_usd`).

---

### 1.5 Nueva Directiva del Usuario: Target EV Early Exit Pre-Match e In-Play (Deportes y ESports)

Directiva recibida bajo header `## 2026-10-10T18:00:42Z`:
> *"que haga operaciones y cierre antes y durante al cumplir con el valor esperado asegurate de eso de los eventos deportivos y deESports"*

Observaciones en el código respecto a la salida temprana y target EV:
1. **Contrato de Posición**: En `estrategias/hft_engine.py:237-254`, `HftPosition` almacena:
   - `entry_price`: Precio de compra inicial.
   - `target_exit_price`: Precio objetivo de salida (Take Profit por EV).
   - `timeout_seconds`: Límite máximo de retención (2-10s en Fase 1, 60-90s en Fase 4, 180-300s en Estrategia A).
2. **Pre-Match (Antes)**:
   - En Fase 1 (`evaluar_fase_1_prematch_obi`), la entrada es Maker en `Best Bid + 1 tick` y la salida proyectada es Maker en `Best Ask + 2 ticks`.
   - Cuando el spread se comprime o la postura de venta es tocada, la posición se liquida con ganancia de $2\%\dots 4\%$ de EV en solo 2 a 10 segundos, **sin esperar al inicio del partido**.
3. **In-Play (Durante)**:
   - En Fase 4 (Time Decay en Empate), la orden compra el YES al Empate en la ventana final y se cierra vía mercado tras 60 a 90 segundos asegurando el tick de ganancia por decaimiento del tiempo, **sin esperar al silbatazo final**.
   - En Estrategia B (Overreaction Hunting), se compra el dip del favorito tras recibir un gol y se vende en el rebote especulativo tras la **primera jugada peligrosa a favor**, **sin esperar a que anote gol ni a que concluya el juego**.
4. **Cobertura Universal (Deportes Tradicionales vs ESports)**:
   - En `estrategias/hft_engine.py:159-170`, `SportConfig` incluye `SportType.ESPORTS` con duración estándar de **35.0 minutos** (vs 90m fútbol, 60m hockey, 120m béisbol).
   - En ESports, las ventanas de decaimiento y timeout ocurren en escalas de tiempo más aceleradas: ventana de Time Decay en minutos 28 a 35, y timeout de cierre temprano entre 30 y 45 segundos.

---

### 1.6 Diagnóstico de Ejecución de Pruebas Existentes

1. **Ejecución con pytest**:
   Comando: `python -m pytest -v pruebas_unitarias/test_tesoreria.py pruebas_unitarias/test_metricas.py pruebas_unitarias/test_riesgo_tesoreria_metricas.py`
   Resultado: **40 passed in 0.14s** (100% de éxito).
2. **Conflicto de Nombres de Módulo en pytest**:
   Comando: `python -m pytest test_tesoreria.py pruebas_unitarias/test_tesoreria.py`
   Resultado: **ERROR de colección**:
   `import file mismatch: imported module 'test_tesoreria' has this __file__ attribute: pruebas_unitarias\test_tesoreria.py which is not the same as test_tesoreria.py`.
3. **Ejecución de `test_tesoreria.py` en Windows PowerShell**:
   Comando: `python test_tesoreria.py`
   Resultado: **Fallo por codificación CP1252**:
   `UnicodeEncodeError: 'charmap' codec can't encode character '\u2713' in position 0`.
   Se requiere `$env:PYTHONIOENCODING="utf-8"` para su ejecución limpia.

---

## 2. CADENA LÓGICA (Logic Chain)

1. **Sobre la ausencia de Kelly**:
   - *Observación*: R2 exige expresamente: "motor financiero basado en las fórmulas solicitadas: Tamaño de Posición Real, Capital Acumulado (Interés Compuesto), EV, ROI, Yield, y Criterio de Kelly".
   - *Inferencia*: `EscudoFinancieroBinance` en `continuitis/riesgo_binance.py` es el motor activo de riesgo de Binance Spot, pero carece de la función de Kelly Criterion. Kelly solo reside en el código legacy de Matchbook.
   - *Consecuencia*: R2 no está completamente cubierto en `riesgo_binance.py` hasta que se incorpore `calcular_criterio_kelly(p_estimada, cuota_neta, fraccion_kelly)` y la opción de modular el stake por Kelly.

2. **Sobre la precisión de 4 decimales**:
   - *Observación*: Criterio de Aceptación 2 exige: "Unit tests for financial formulas (Win Rate, EV, ROI, Position Size) guaranteeing 4 decimal precision (0.0001)".
   - *Inferencia*: `calcular_posicion()` redondea `stake` a 2 decimales (`round(posicion_nominal, 2)`).
   - *Consecuencia*: En mercados de contratos predictivos (donde los precios son típicamente centavos como $0.48 y las cuotas varían milimétricamente), limitar el stake a 2 decimales introduce un error de truncamiento de hasta $0.005 USD, impidiendo certificar precisión de 4 decimales en el dimensionamiento de posición.

3. **Sobre la Cosecha Autónoma al cruzar $1,000 USD**:
   - *Observación*: Criterio de Aceptación 1 exige: "Test script demonstrating $1,000 USD balance triggers 35% net profit isolation for harvesting".
   - *Inferencia*: Actualmente, cuando el balance llega a $1,000 USD, `verificar_hitos()` solo devuelve `MODO_COSECHA_AUTONOMA_DISPONIBLE` en un string, sin aislar fondos. Los tests existentes solo evalúan llamadas manuales pasando parámetros estáticos a `corte_mensual(500.0)`.
   - *Consecuencia*: Se requiere un flujo verdaderamente autónomo en `GestorTesoreria`: cuando una operación cerrada o verificación de balance detecte $\ge \$1,000$ USD, el motor debe calcular automáticamente la ganancia neta, aislar el 35% a MXN en variables contables dedicadas, transferir el 40% del remanente a gastos y mantener el 60% en reinversión compuesta.

4. **Sobre el impacto financiero de Target EV Early Exit (Pre-Match e In-Play)**:
   - *Observación*: La nueva directiva exige abrir y cerrar operaciones tanto pre-match como in-play el momento en que se alcanza el EV objetivo, sin esperar el desenlace final del evento, aplicable a Deportes y ESports.
   - *Inferencia*: El cierre temprano por EV objetivo ($P_{exit} \ge P_{target\_exit}$) reduce el tiempo de exposición de capital de horas a segundos/minutos ($2\text{s} - 90\text{s}$). Esto eleva drásticamente la velocidad de rotación ($Turnover$) y maximiza el factor multiplicador de la fórmula de Interés Compuesto:
     $$B_N = B_0 \prod_{i=1}^N (1 + f_i R_i)$$
     Al cerrar con $R_i \approx +2.5\%\dots +5.0\%$ neto en lugar de arriesgar el $100\%$ del stake en la resolución binaria final, la tasa de supervivencia de la cuenta aumenta y el capital alcanza los hitos de $10 \to 100 \to 1,000$ USD con varianza minimizada.
   - *Consecuencia*: El motor de riesgo y tesorería debe registrar cada trade cerrado anticipadamente mediante `TradeResult(pnl, stake, is_win=pnl>0)` e incorporar la verificación de Target EV en la toma de beneficios tanto para Deportes tradicionales como para ESports.

5. **Sobre la infraestructura de pruebas**:
   - *Observación*: El script raíz `test_tesoreria.py` falla en Windows por el caracter `✓` y colisiona en pytest con `pruebas_unitarias/test_tesoreria.py`.
   - *Inferencia*: Para que cualquier auditor o pipeline ejecute el script de verificación sin errores ambientales de Windows, se debe proveer un script autónomo en UTF-8/ASCII-safe y renombrar o desacoplar los archivos con nombres colisionantes.

---

## 3. SALVEDADES (Caveats)

1. **Modo de Operación**: La inspección se realizó en modo de solo lectura sobre el código estático y las pruebas locales. No se realizaron órdenes en vivo contra la API de producción de Binance.
2. **Tipo de Cambio USD/MXN**: La liquidación de USD a MXN usa `TIPO_CAMBIO_MXN_DEFAULT = 20.0` como referencia configurable. La integración con pasarelas bancarias o P2P de Binance está fuera del alcance del cálculo numérico del motor de tesorería y se maneja como conversión teórica monetaria.
3. **Cálculo de Ganancia Neta Mensual**: En trading autónomo continuo, la "utilidad neta mensual" puede calcularse como:
   a) La ganancia neta acumulada sobre la base de capital (`self.balance - self.balance_inicial`), o
   b) La suma de PnL del período registrada por `AuditorMetricas` (`auditor.suma_pnl`).
   La propuesta soporta ambas opciones de forma transparente.
4. **Diferencias entre Deportes y ESports**: En ESports (League of Legends, Counter-Strike, Dota 2), las partidas no tienen reloj continuo predecible como el fútbol; se dividen en rondas o mapas de ~30-40 min. Los thresholds de ataque peligroso se calibran contra eventos de objetivos (ej. Baron, Dragon, Primera Sangre), pero la matemática de EV de salida anticipada permanece idéntica: $P_{exit} \cdot (1 - fee) - P_{entry} \ge \Delta EV_{target}$.

---

## 4. CONCLUSIÓN Y PROPUESTA DE CAMBIOS CONCRETOS (Conclusion)

### 4.1 Brechas Identificadas (Summary of Gaps)
1. **Brecha 1**: Falta la implementación del **Criterio de Kelly** en `continuitis/riesgo_binance.py`.
2. **Brecha 2**: **Precisión insuficiente** en el cálculo de `stake` (Tamaño de Posición), redondeado a 2 decimales en lugar de 4.
3. **Brecha 3**: La cosecha al cruzar $1,000 USD **no es autónoma**; solo marca un flag y no aisla activamente los fondos en variables contables dedicadas.
4. **Brecha 4**: Falta un **script de prueba dedicado** que demuestre que al alcanzar $1,000 USD se aisla automáticamente el 35% de la ganancia neta a MXN.
5. **Brecha 5**: Ausencia de una función explícita en el Escudo Financiero para auditar el cumplimiento del **Target EV de salida temprana** (Take-Profit) antes del desenlace para Deportes y ESports.
6. **Brecha 6**: Colisión de nombres en pytest y error de codificación CP1252 en Windows para `test_tesoreria.py`.

---

### 4.2 Propuesta Concreta de Código

#### Cambio 1: Añadir Criterio de Kelly, Target EV Exit y Precisión de 4 Decimales en `continuitis/riesgo_binance.py`

```python
# En continuitis/riesgo_binance.py:

def calcular_criterio_kelly(
    self,
    p_estimada: float,
    cuota_neta: float,
    fraccion_kelly: float = 0.25,
) -> float:
    """
    Calcula la fracción óptima de Kelly según PLANnew.md §3 Módulo 3:
      f* = fraccion_kelly * ((p * (b + 1) - 1) / b)
    donde b = cuota_neta - 1.0 (ganancia neta por unidad apostada).
    Retorna la fracción f* acotada en [0.0, 1.0] con 4 decimales.
    """
    if cuota_neta <= 1.0:
        return 0.0
    b = cuota_neta - 1.0
    ev = (p_estimada * cuota_neta) - 1.0
    if ev <= 0.0:
        return 0.0
    kelly_puro = ev / b
    kelly_frac = fraccion_kelly * kelly_puro
    return round(max(0.0, min(1.0, kelly_frac)), 4)


def evaluar_target_ev_salida(
    self,
    precio_entrada: float,
    precio_actual_bid: float,
    ev_objetivo_minimo: float = 0.02, # 2.0% neto de ganancia
) -> Dict[str, Any]:
    """
    Audita si una posición abierta (Pre-match o In-play en Deportes o ESports)
    ha cumplido su Valor Esperado objetivo para ejecutar salida temprana sin
    esperar la liquidación final del evento deportivo.
    """
    if precio_entrada <= 0.0:
        return {"cerrar_posicion": False, "motivo": "Precio de entrada inválido"}
    
    # Rendimiento neto considerando comisión BNB
    fee = self.tasa_comision_efectiva
    retorno_neto = ((precio_actual_bid * (1.0 - fee)) - precio_entrada) / precio_entrada
    
    cumple_ev = retorno_neto >= ev_objetivo_minimo
    return {
        "cerrar_posicion": cumple_ev,
        "retorno_neto": round(retorno_neto, 4),
        "ev_objetivo": round(ev_objetivo_minimo, 4),
        "motivo": "TARGET_EV_ALCANZADO" if cumple_ev else "EV_PENDIENTE",
    }
```

En `calcular_posicion()` de `riesgo_binance.py`:
- Actualizar el retorno de `stake` y `riesgo_monetario` a **4 decimales**:
```python
"stake": round(posicion_nominal, 4),
"riesgo_monetario": round(riesgo_real, 4),
```

---

#### Cambio 2: Automatización de Aislamiento de Cosecha (35% MXN) en `continuitis/tesoreria.py`

En `GestorTesoreria`:
1. Agregar atributos de estado para custodia de fondos aislados:
```python
self.capital_aislado_cosecha_usd: float = 0.0
self.capital_aislado_cosecha_mxn: float = 0.0
self.fondo_gastos_operacion_usd: float = 0.0
self.fondo_reinversion_total_usd: float = 0.0
self.cosechas_ejecutadas: List[Dict[str, Any]] = []
```

2. Agregar método `ejecutar_cosecha_autonoma()`:
```python
def ejecutar_cosecha_autonoma(
    self,
    ganancia_neta: Optional[float] = None,
    tipo_cambio_mxn: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Ejecuta el protocolo autónomo de Harvesting al cruzar >= $1,000 USD:
    - 35% de utilidad neta aislado para retiro y liquidación a MXN.
    - 65% restante dividido:
        * 40% (26% total) a gastos de operación.
        * 60% (39% total) a reinversión compuesta.
    - Los fondos cosechados se transfieren a capital_aislado_cosecha_usd/mxn.
    - El balance operativo retiene únicamente la porción de reinversión.
    """
    fx = float(tipo_cambio_mxn) if tipo_cambio_mxn is not None else self.tipo_cambio_mxn
    
    if ganancia_neta is None:
        # Calcular automáticamente la utilidad neta sobre el capital base
        ganancia_neta = max(0.0, self.balance - self.balance_inicial)

    if ganancia_neta <= 0.0 or self.balance < UMBRAL_COSECHA_1000:
        return {
            "cosecha_ejecutada": False,
            "motivo": "Condiciones no cumplidas (balance < 1000 o sin ganancia neta)",
            "balance_actual": round(self.balance, 4),
        }

    self.meta_1000_activada = True
    retiro_35 = round(ganancia_neta * PCT_COSECHA_AUTONOMA, 4)
    retiro_mxn = round(retiro_35 * fx, 4)
    utilidad_restante = ganancia_neta - retiro_35
    operacion_40 = round(utilidad_restante * PCT_GASTOS_OPERACION, 4)
    reinversion_60 = round(utilidad_restante * PCT_REINVERSION_COMPUESTA, 4)

    # Aislamiento formal de fondos en bóvedas dedicadas
    self.capital_aislado_cosecha_usd += retiro_35
    self.capital_aislado_cosecha_mxn += retiro_mxn
    self.fondo_gastos_operacion_usd += operacion_40
    self.fondo_reinversion_total_usd += reinversion_60

    # Actualización del balance de trading: se extrae la ganancia neta y se retiene la reinversión
    self.balance = round((self.balance - ganancia_neta) + reinversion_60, 4)

    resultado = {
        "cosecha_ejecutada": True,
        "ganancia_neta": round(ganancia_neta, 4),
        "retiro_autonomo_35_usd": retiro_35,
        "retiro_autonomo_mxn": retiro_mxn,
        "gastos_operacion_40_usd": operacion_40,
        "reinversion_compuesta_60_usd": reinversion_60,
        "nuevo_balance_operativo": round(self.balance, 4),
        "total_aislado_historico_usd": round(self.capital_aislado_cosecha_usd, 4),
        "total_aislado_historico_mxn": round(self.capital_aislado_cosecha_mxn, 4),
    }

    self.cosechas_ejecutadas.append(resultado)
    self.log_eventos.append({"evento": "COSECHA_AUTONOMA_EJECUTADA", "detalle": resultado})
    return resultado
```

3. Modificar `verificar_hitos(auto_cosechar: bool = True)`:
   Si `self.balance >= UMBRAL_COSECHA_1000` y `auto_cosechar` es `True`:
   Invocar automáticamente `ejecutar_cosecha_autonoma()`.

---

#### Cambio 3: Actualizar `AuditorMetricas` para 4 Decimales en `continuitis/auditor_metricas.py`

En `obtener_metricas()`:
```python
"win_rate": round(wr, 4),
"capital_acumulado": round(cap_acumulado, 4),
"roi": round(roi, 4),
"yield": round(rendimiento_yield, 4),
```

---

#### Cambio 4: Crear Script de Verificación Formal de Criterios de Aceptación R2

Crear `pruebas_unitarias/test_r2_exactitud_financiera.py` que valide:
1. Script demostrativo: Balance de $1,000 USD dispara de forma autónoma el cálculo y aislamiento de exactamente el 35% de la utilidad neta a MXN.
2. Pruebas unitarias de las 4 fórmulas clave (Win Rate, EV, ROI, Position Size) + Criterio de Kelly garantizando precisión matemática al cuarto decimal (`abs=1e-4`).
3. Pruebas de Target EV Early Exit pre-match e in-play para Deportes y ESports.

---

## 5. MÉTODO DE VERIFICACIÓN INDEPENDIENTE (Verification Method)

Para que el orquestador y cualquier agente implementador verifiquen de forma independiente estas conclusiones:

1. **Verificación de Ausencia de Kelly en `riesgo_binance.py`**:
   ```powershell
   Get-Content continuitis\riesgo_binance.py | Select-String "kelly"
   # Salida esperada: Vacío (0 coincidencias)
   ```

2. **Verificación del Redondeo a 2 Decimales de Stake**:
   Inspeccionar línea 304 de `continuitis/riesgo_binance.py`:
   `"stake": round(posicion_nominal, 2)`

3. **Verificación de Tests Actuales**:
   ```powershell
   python -m pytest -v pruebas_unitarias\test_tesoreria.py pruebas_unitarias\test_metricas.py pruebas_unitarias\test_riesgo_tesoreria_metricas.py
   # Pasan 40/40 tests actuales
   ```

4. **Verificación del Script Raíz y Conflicto en Windows**:
   ```powershell
   python test_tesoreria.py
   # Produce: UnicodeEncodeError si no se fuerza UTF-8
   
   python -m pytest test_tesoreria.py pruebas_unitarias\test_tesoreria.py
   # Produce: import file mismatch
   ```

5. **Condición de Invalidación**:
   Este reporte quedaría invalidado si el motor de Binance estuviera diseñado para heredar de `continuitis/financiero.py` (lo cual no ocurre actualmente, pues son módulos completamente independientes).
