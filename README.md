# CONTINUITYEM: High-Frequency Trading (HFT) Sports Exchange Engine

**CONTINUITYEM** es un ecosistema modular de trading algorítmico de alta frecuencia (HFT) diseñado exclusivamente para operar en *exchanges* deportivos y ESports (actualmente **Matchbook MX y BINANCE PREDICCION**).

Su objetivo principal es la **multiplicación de micro-capitales** (ej. de $100 MXN a $500 MXN al primer mes) explotando ineficiencias milimétricas del mercado mediante arbitraje de *spreads* y apalancamiento matemático agresivo (*Kelly Criterion* + Interés Compuesto).

---

## 🏛️ Arquitectura del Sistema

El ecosistema ha sido depurado para ser asíncrono, ultraligero y evasivo frente a firewalls (Cloudflare). Se divide en 3 módulos principales:

1. **`orquestadores_principales/` (El Cerebro HFT)**
   - `HFT_GALO.py`: El demonio principal **v2.0 Multi-Strategy**. Escanea cientos de eventos por segundo, filtra mercados según liquidez y ejecuta 3 estrategias paralelas por ciclo en menos de 10 milisegundos.

2. **`continuitis/` (El Motor Matemático y Memoria)**
   - `financiero.py`: Motor de interés compuesto y calculador de Kelly fraccional dinámico según el *bankroll*.
   - `microestructura.py`: Calcula VWAP, EV neto post-comisión y estrategia Maker/Taker.
   - `memoria_hft.py`: Almacenamiento ultrarrápido en RAM para operaciones en vivo, vaciado asíncrono hacia SQLite para MLOps.
   - `constantes.py`: Límites de escaneo, IPs, URLs de las APIs y parámetros del sistema.

3. **`conectores/` (Redes y Alertas)**
   - `matchbook_async.py`: Cliente de API especializado usando `curl_cffi` para simular la huella digital TLS de Chrome, evadiendo 429/403 de Cloudflare.
   - `telegram_bot.py`: Emisor de alertas de Telegram para monitoreo en tiempo real.

---

## 🎯 Arquitectura Multi-Estrategia (v2.0)

El motor ejecuta **3 estrategias en paralelo** dentro del mismo ciclo de escaneo, cada una con su propia lógica de EV y cooldown independiente:

### Estrategia A — Pure Market Maker (`MKR_` prefix)
- Coloca *limit orders* a `maker_odds` (1 tick inside the spread).
- **Filtro de entrada**: `prob_gap < 3%`.
- **Comportamiento**: Órdenes esperan en el libro, ejecutadas cuando los apostadores casuales toman el precio.
- **Cooldown**: 300s por runner.

### Estrategia B — VWAP Momentum Scalp (`VWAP_` prefix)
- **Solo para eventos in-play** (`in-running-flag == True`).
- Usa `CalculadorVWAP` para encontrar el precio justo ponderado por volumen del libro.
- Si `back_odds > VWAP × (1 + 2%)`, el mercado está ofreciendo mejor precio que el fair value → entra como Taker inmediato (EV positivo para el back).
- Captura situaciones donde el top-of-book de back supera el precio VWAP (ej. lay-listers en pánico ofrecen cuotas muy altas).
- **Cooldown**: 120s por runner.

### Estrategia C — Liquidity Drain Scalp (`DRN_` prefix)
- Filtra runners donde `1.5% ≤ prob_gap < 3%` (mercados tight = más líquidos).
- Requiere que el runner haya sido visto en **al menos 1 ciclo anterior** (runner confirmado en el libro).
- Entra con `maker_odds = back_odds + 2 ticks` (precio ultra-agresivo para entrar más profundo en la cola).
- **Cooldown**: 300s por runner.

### Control de Estrategias
```python
ESTRATEGIA_ACTIVA = {
    "A_MARKET_MAKER": True,
    "B_VWAP_SCALP":   True,
    "C_DRAIN_SCALP":  True,
}
```

---

## ⚙️ Mecanismos de Protección (Preservados)

| Mecanismo | Valor | Descripción |
|-----------|-------|-------------|
| Hard Stop | 40 MXN | Detiene todo si bankroll cae a ≤ 40 MXN |
| Trailing Stop | -20% diario | Detiene por el día si bankroll cae 20% desde el pico |
| Kill-or-Fill GC | 45s | Cancela órdenes no ejecutadas para rotar capital |
| Reporte 3H | Telegram | Corte de caja cada 3 horas vía Telegram |
| Cooldown | MKR/VWAP/DRN | Bloqueo independiente por runner y estrategia |

---

## 🚀 Viabilidad y Escalabilidad

- **Kelly Acelerado**: Multiplicador x5 para bankroll < $1,000 MXN; reduce a x3 hasta $10k, x2 hasta $50k, x1 en la fase final.
- **Comisión Matchbook**: 4% sobre ganancias netas (solo al ganar). `AjustadorComisiones` descuenta esto en todo cálculo de EV.
- **Mínimo de apuesta**: ~$2 MXN. Cualquier stake calculado menor a $2 MXN es descartado.
- **Escalabilidad Modular**: Nuevas estrategias se integran como funciones `evaluar_estrategia_X()` independientes.

---

## 🔒 Variables de Entorno (Requeridas)
Para operar, el servidor debe tener configurado un archivo `.env` con las credenciales:
- `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- `MATCHBOOK_USERNAME`, `MATCHBOOK_PASSWORD` (O `MB_USER`, `MB_PASS`)
