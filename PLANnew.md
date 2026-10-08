# DOCUMENTO TÉCNICO DE ARQUITECTURA MODULAR: CONTINUITY HFT

## Motor Cuantitativo y Microestructura de Mercados de Predicción Deportiva (Binance)

---

### 1. OBJETIVO DEL SISTEMA Y RESUMEN EJECUTIVO

El presente documento técnico formaliza el diseño, la parametrización matemática, las interfaces y la arquitectura modular del sistema **CONTINUITY HFT - Binance Predicción**.

El propósito central es construir un motor autónomo, disciplinado y modular para operar mercados de predicción deportiva (contratos binarios tipo `YES`/`NO` sobre Binance Predict / AMMs asociados). El sistema aprovecha las micro-ineficiencias del libro de órdenes (Pre-Match e In-Play) sin la obligación estricta de mantener posiciones hasta la liquidación final del evento deportivo, garantizando la extracción de valor esperado ($EV > 0$) mediante rotación de capital, interés compuesto y un protocolo de tesorería riguroso.

---

### 2. ARQUITECTURA MODULAR DEL SISTEMA

Siguiendo el principio de **Separación de Responsabilidades** y el **Paradigma del Operador Único**, el sistema se estructura en seis submódulos desacoplados operando concurrentemente:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        ORQUESTADOR / UI PACÍFICO                       │
└──────┬─────────────────────────┬───────────────────────────────┬───────┘
       │                         │                               │
┌──────▼──────────────────┐ ┌────▼────────────────────────┐ ┌────▼───────┐
│     MÓDULO 1:           │ │        MÓDULO 2:            │ │ MÓDULO 6:  │
│ OrderBookListener & Ingest│ │  MarketMicrostructureEngine   │ │ Tesorería &│
│ (WebSocket L2 / Feeds)  │ │ (Imbalance, Spread & Sniping)│ │ Ordeño     │
└──────┬──────────────────┘ └────┬────────────────────────┘ │ (Retiros/  │
       │                         │                          │  Inyección)│
┌──────▼─────────────────────────▼────────────────────────┐ └────▲───────┘
│                       MÓDULO 3:                         │      │
│              EscudoFinanciero & RiskEngine              │      │
│      (Kelly Fraccionario, Fixed Fractional, Stop Loss)  ├──────┘
└──────┬──────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│                       MÓDULO 4:                         │
│            ExecutionRouter & LatencyGuard               │
│        (Órdenes Límite/Market, Slippage & Queues)       │
└──────┬──────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────┐
│                       MÓDULO 5:                         │
│             StateRegistry & MetricAuditor               │
│         (SQLite WAL, Win Rate, ROI, Yield, EV)          │
└─────────────────────────────────────────────────────────┘

```

---

### 3. ESPECIFICACIÓN TÉCNICA DE LOS MÓDULOS

#### Módulo 1: OrderBookListener & Ingesta Asíncrona

* **Objetivo:** Mantener una réplica exacta del libro de órdenes (*Level 2 Depth*) en memoria RAM ($\mathcal{O}(1)$) y monitorear la salud de los oráculos externos.
* **Funciones:**
* `conectar_orderbook_ws(market_id)`: Establece una conexión WebSocket persistente al canal de profundidad del mercado de Binance.
* `actualizar_libro(bids, asks)`: Mantiene en memoria las mejores 5 a 10 posturas de compra y venta.
* `escuchar_feed_deportivo()`: Monitorea el estado y latencia de los datos del evento real (marcador, tarjetas, ataques peligrosos).
* `detectar_estado_mercado()`: Identifica si Binance transiciona el mercado a `Suspended` o `Active`.



#### Módulo 2: MarketMicrostructureEngine (Estrategia de 4 Fases)

* **Objetivo:** Ejecutar la lógica de arbitraje de transición de fase, provisión de liquidez asimétrica y captura de *decay*.
* **Funciones y Lógica por Fase:**
1. **Fase 1 (HFT Pre-Match / 120 min a 5 min antes):**
* Calcula el desequilibrio del libro (*Order Book Imbalance*):

$$I = \frac{\sum V_{\text{Bid}} - \sum V_{\text{Ask}}}{\sum V_{\text{Bid}} + \sum V_{\text{Ask}}}$$


* Si el desequilibrio de compra supera el $80\%$ ($I \ge 0.60$), inyecta una orden límite de compra a $\text{Best Bid} + 1\text{ tick}$.
* Al llenarse, programa la orden de venta límite a $\text{Best Ask} + 2\text{ ticks}$. Exposición máxima: $2$ a $10$ segundos.


2. **Fase 2 (Rebalanceo y Transición / 5 min antes):**
* `limpiar_mesa()`: Cancela de forma atómica todas las órdenes pendientes en el libro.
* Si existen contratos atrapados no emparejados, ejecuta `Market Sell` inmediato.
* **Regla Innegociable:** Exposición en el minuto cero = $0\%$; liquidez en USDT = $100\%$.


3. **Fase 3 (In-Play Latency Sniping / Minuto 1 al 75):**
* `snipe_desfase_oraculo(evento)`: Detecta discrepancias de tiempo real frente al congelamiento de Binance.
* Si ocurre un gol o tarjeta roja antes de la suspensión del libro, adquiere contratos desactualizados y coloca orden de salida inmediata tras el restablecimiento del mercado.


4. **Fase 4 (Time Decay Exponencial / Minuto 75 al 90):**
* Monitorea partidos en empate con índice de peligro aproximándose a cero: $\text{Danger Attacks/min} \to 0$.
* Entra en contratos con decaimiento acelerado durante ventanas cortas (ej. $60$ a $90$ segundos) y liquida la posición con orden de mercado sin esperar la conclusión del partido.





#### Módulo 3: EscudoFinanciero & RiskEngine (Gestión de Capital)

* **Objetivo:** Proteger el capital frente a rachas adversas, evitar la ruina y dimensionar cada operación.
* **Fórmulas y Reglas de Entrada:**
* **Cálculo del Valor Esperado ($EV$):**

$$EV = (P_{\text{estimada}} \times \text{Cuota/Payout}) - 1$$



*Filtro:* No se emite orden si $EV < 0.015$ ($1.5\%$) neto de comisiones.
* **Dimensionamiento del Tamaño de Posición (Position Sizing):**

$$\text{Tamaño de Posición} = \frac{\text{Balance Total} \times \text{Porcentaje de Riesgo}}{\text{Porcentaje de Stop Loss}}$$



*Alternativa (Kelly Fraccionario al 25% o Fracción Fija del 1% al 3%):*

$$f^* = 0.25 \times \left( \frac{p \cdot (b + 1) - 1}{b} \right)$$


* **Techo de Exposición por Clúster:** Máximo $15\%$ del capital total comprometido simultáneamente.
* **Freno de Racha:** Si se registran pérdidas consecutivas, se comprime el riesgo por un factor de atenuación ($0.85$).



#### Módulo 4: ExecutionRouter & LatencyGuard

* **Objetivo:** Enviar órdenes firmadas a la API de Binance, controlar el *slippage* y aplicar el botón de pánico (*Kill Switch*).
* **Funciones:**
* `ejecutar_orden(tipo, lado, precio, cantidad)`: Firma y transmite las órdenes (Maker/Taker) considerando las comisiones netas descontadas con BNB.
* `auditar_latencia_feed()`: Si la latencia del feed deportivo o del WebSocket supera los $800\text{ ms}$, activa el protocolo de emergencia.
* `boton_panico()`: Cancela todas las órdenes activas y cancela transacciones pendientes en memoria.



#### Módulo 5: StateRegistry & MetricAuditor

* **Objetivo:** Registro transaccional inmutable en SQLite (modo WAL) y telemetría de rendimiento.
* **Métricas Clave:**
* **Win Rate ($WR$):** $\frac{\text{Operaciones Ganadoras}}{N}$.
* **Retorno sobre la Inversión ($ROI$):** Rendimiento neto acumulado sobre el capital inicial.
* **Yield:** Rentabilidad neta sobre el volumen total transaccionado:

$$\text{Yield} = \frac{\text{Ganancia Neta Total}}{\text{Volumen Total Operado (Turnover)}}$$


* **Capital Acumulado:**

$$B_N = B_0 \cdot \prod_{i=1}^{N} (1 + f_i \cdot R_i)$$





#### Módulo 6: Tesorería, Ordeño e Inyección (Cashflow & Harvesting)

* **Objetivo:** Gestionar el ciclo de inyecciones, retiros programados y la conversión de ganancias.
* **Reglas Operativas:**
1. **Hito de Validación e Inyección ($10 \to 100\text{ USD}$):**
* Capital inicial base: $10\text{ USD}$.
* Al alcanzar $100\text{ USD}$ demostrando rentabilidad consistente, se autoriza la inyección de capital de $100\text{ USD}$ adicionales.


2. **Ciclo de Reinversión e Interés Compuesto:**
* Durante la fase de aceleración, el capital opera con reinversión continua.
* En cortes mensuales: se distribuye la utilidad generada en $40\%$ para gastos operativos/administración y $60\%$ se retiene para capital compuesto.


3. **Protocolo de Cosecha Autónoma ($1,000\text{ USD}$):**
* Al superar los $1,000\text{ USD}$ de balance, se activa el ordeño automático del $35\%$ de los beneficios mensuales.
* Convierte de forma autónoma el excedente a moneda mexicana (MXN vía liquidación P2P/fiat de Binance o pasarela configurada), preservando la integridad del capital operativo base.





---

### 4. ESPECIFICACIÓN DEL CÓDIGO CORE (IMPLEMENTACIÓN MÍNIMA VIABLE)

A continuación se presenta la integración ejecutable en Python que consolida los módulos de **Escudo Financiero**, **Gestor de Microestructura con Kill Switch** y **Gestión de Tesorería**:

```python
# -*- coding: utf-8 -*-
"""
CONTINUITY HFT — Binance Prediction Engine
Módulos: LatencyGuard, MicrostructureEngine, EscudoFinanciero & TreasuryManager.
"""

import time
import logging
from typing import Dict, Any, Tuple

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class LatencyAndKillSwitchGuard:
    """Módulo 4: Guardián de latencia y control de estado de mercado."""
    def __init__(self, max_latencia_ms: float = 800.0):
        self.max_latencia_ms = max_latencia_ms
        self.ultimo_heartbeat = time.time()
        self.mercado_suspendido = False
        self.emergencia_activa = False

    def registrar_pulso_feed(self, timestamp: float) -> None:
        self.ultimo_heartbeat = timestamp
        if self.emergencia_activa:
            logging.info("Feed deportivo estabilizado. Sistema operativo.")
            self.emergencia_activa = False

    def actualizar_estado_binance(self, status: str) -> None:
        self.mercado_suspendido = (status.upper() == "SUSPENDED")

    def autorizacion_disparo(self) -> Tuple[bool, str]:
        if self.emergencia_activa:
            return False, "EMERGENCIA_ACTIVA"
        
        delta_ms = (time.time() - self.ultimo_heartbeat) * 1000.0
        if delta_ms > self.max_latencia_ms:
            self.emergencia_activa = True
            return False, f"LATENCIA_EXCESIVA ({delta_ms:.2f} ms)"
        
        if self.mercado_suspendido:
            return False, "MERCADO_SUSPENDIDO_BINANCE"
            
        return True, "AUTORIZADO"


class EscudoFinancieroHFT:
    """Módulo 3: Dimensionamiento de postura, control de clúster y drawdown."""
    def __init__(self, pct_riesgo_fijo: float = 0.015, ev_minimo: float = 0.015, max_cluster_exp: float = 0.15):
        self.pct_riesgo_fijo = pct_riesgo_fijo
        self.ev_minimo = ev_minimo
        self.max_cluster_exp = max_cluster_exp
        self.perdidas_consecutivas = 0

    def calcular_posicion(
        self,
        balance_actual: float,
        p_estimada: float,
        cuota: float,
        pct_stop_loss: float,
        operaciones_activas: int
    ) -> Dict[str, Any]:
        # 1. Validación de Valor Esperado
        ev = (p_estimada * cuota) - 1.0
        if ev < self.ev_minimo:
            return {"operar": False, "motivo": f"EV insuficiente ({ev:.4f})", "stake": 0.0}

        # 2. Factor de atenuación por racha negativa
        factor_racha = 0.85 ** self.perdidas_consecutivas

        # 3. Tamaño de posición en función del Stop Loss
        # Posición = (Balance * % Riesgo) / % Stop Loss
        riesgo_objetivo = balance_actual * self.pct_riesgo_fijo * factor_racha
        posicion_nominal = riesgo_objetivo / max(pct_stop_loss, 0.01)

        # 4. Modulación por techo de clúster
        exposicion_futura = ((operaciones_activas + 1) * posicion_nominal) / balance_actual
        if exposicion_futura > self.max_cluster_exp:
            compresion = (self.max_cluster_exp * balance_actual) / ((operaciones_activas + 1) * posicion_nominal)
            posicion_nominal *= compresion

        return {
            "operar": True,
            "ev": round(ev, 4),
            "stake": round(posicion_nominal, 2),
            "riesgo_monetario": round(riesgo_objetivo, 2)
        }

    def registrar_resultado(self, es_ganadora: bool) -> None:
        if es_ganadora:
            self.perdidas_consecutivas = 0
        else:
            self.perdidas_consecutivas += 1


class TreasuryAndHarvestingManager:
    """Módulo 6: Gobierno de balance, inyección de capital y cosechas autónomas."""
    def __init__(self, balance_inicial: float = 10.0):
        self.balance = balance_inicial
        self.hito_100_inyectado = False
        self.meta_1000_activada = False

    def auditar_progreso(self) -> Dict[str, Any]:
        acciones = []
        
        # Regla de Inyección: de 10 a 100 USD
        if self.balance >= 100.0 and not self.hito_100_inyectado:
            self.balance += 100.0
            self.hito_100_inyectado = True
            acciones.append("INYECCION_100_USD_APLICADA")

        # Regla de Umbral de Cosecha: 1,000 USD
        if self.balance >= 1000.0:
            self.meta_1000_activada = True
            acciones.append("MODO_COSECHA_AUTONOMA_DISPONIBLE")

        return {"balance_actual": self.balance, "acciones": acciones}

    def procesar_cierre_mensual(self, ganancia_mensual: float) -> Dict[str, float]:
        """Aplica la regla de retención / reinversión mensual."""
        if ganancia_mensual <= 0:
            return {"reinversion": 0.0, "operacion": 0.0, "retiro_mxn": 0.0}

        # Si ya se superaron los 1,000 USD, se activa el retiro del 35%
        if self.meta_1000_activada:
            retiro_35 = ganancia_mensual * 0.35
            utilidad_restante = ganancia_mensual - retiro_35
            operacion_40 = utilidad_restante * 0.40
            reinversion_60 = utilidad_restante * 0.60
            self.balance = (self.balance - ganancia_mensual) + reinversion_60
            return {
                "retiro_autonomo_35": round(retiro_35, 2),
                "gastos_operacion_40": round(operacion_40, 2),
                "reinversion_compuesta_60": round(reinversion_60, 2),
                "nuevo_balance": round(self.balance, 2)
            }
        else:
            # División estándar: 40% operación, 60% reinversión
            operacion_40 = ganancia_mensual * 0.40
            reinversion_60 = ganancia_mensual * 0.60
            self.balance = (self.balance - ganancia_mensual) + reinversion_60
            return {
                "retiro_autonomo_35": 0.0,
                "gastos_operacion_40": round(operacion_40, 2),
                "reinversion_compuesta_60": round(reinversion_60, 2),
                "nuevo_balance": round(self.balance, 2)
            }

```

---

### 5. EVALUACIÓN Y VALIDACIÓN EMPÍRICA (REGLA DE SUPERACIÓN)

Bajo las directrices del **Ecosistema CONTINUITY**:

1. **Microestructura Real de Binance Predict:** A diferencia de mercados spot de alta liquidez como BTC/USDT, los libros deportivos presentan *spreads* más amplios y menor profundidad de contratos. Las órdenes deben ser estrictamente tipo *Maker* (Límite) en la Fase 1 para capturar el spread sin pagar tarifas de *Taker*.
2. **Fricción por Comisiones:** Todo cálculo de $EV$ debe incorporar el descuento de comisiones mediante saldo en BNB. Un *spread* de $3\text{ ticks}$ puede ser consumido en su totalidad si la orden se liquida como tomador (*Taker*).
3. **Validación Fuera de Muestra (N = 300):** Antes de autorizar la inyección de $100\text{ USD}$ o escalar la posición, el sistema debe registrar un mínimo de $N=300$ transacciones en modo de prueba (*paper trading*) confirmando un $p\text{-value} < 0.05$ y un $EV$ neto positivo.