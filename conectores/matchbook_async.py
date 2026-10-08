# -*- coding: utf-8 -*-
"""
conectores.matchbook_async
===========================
[v7.1-MICRO] Cliente asíncrono para Matchbook Exchange API.
Bypass Cloudflare con curl_cffi. Incluye:
  - Profundidad de mercado (price-mode=expanded)
  - Heartbeat kill-switch
  - Soporte Maker/Taker para in-play
"""

import os
import asyncio
import json
import logging
import difflib
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dotenv import load_dotenv
from curl_cffi.requests import AsyncSession

load_dotenv()

from continuitis.constantes import (
    MB_BASE_URL_API, MB_AUTH_URL,
    MB_HEARTBEAT_INTERVAL_SEC, MB_LIQUIDITY_RATIO_MIN,
)

logger = logging.getLogger("CONTINUITY.Matchbook")


class MatchbookClientAsync:
    BASE_URL = MB_BASE_URL_API
    AUTH_URL = MB_AUTH_URL

    def __init__(self):
        self.username = os.getenv("MATCHBOOK_USERNAME")
        self.password = os.getenv("MATCHBOOK_PASSWORD")

        self.session_token: Optional[str] = None
        self.session: Optional[AsyncSession] = None
        self.token_expiry: Optional[datetime] = None

        self.call_timestamps: List[datetime] = []
        self._throttle_lock = asyncio.Lock()

    async def _throttle(self):
        async with self._throttle_lock:
            now = datetime.now()
            self.call_timestamps = [t for t in self.call_timestamps if (now - t).total_seconds() < 60]
            if len(self.call_timestamps) >= 290:
                espera = 60 - (now - self.call_timestamps[0]).total_seconds()
                if espera > 0:
                    await asyncio.sleep(espera)
                now = datetime.now()
                self.call_timestamps = [t for t in self.call_timestamps if (now - t).total_seconds() < 60]
            self.call_timestamps.append(datetime.now())

    async def init_session(self):
        if not self.session:
            # impersonate="chrome120" es la clave para pasar Cloudflare
            self.session = AsyncSession(
                impersonate="chrome120",
                headers={
                    "content-type": "application/json;charset=UTF-8",
                    "accept": "*/*",
                    "Accept-Encoding": "gzip",  # Optimización obligatoria de transporte
                    "User-Agent": "api-doc-test-client"
                }
            )
        await self.asegurar_token()

    async def asegurar_token(self):
        ahora = datetime.now()
        if not self.session_token or not self.token_expiry or (self.token_expiry - ahora).total_seconds() < 600:
            return await self.autenticar()
        return True

    # ==============================================================
    # 1. API SECURITY: LOGIN (POST)
    # ==============================================================
    async def autenticar(self) -> bool:
        payload = {
            "username": self.username,
            "password": self.password,
        }

        try:
            await self._throttle()
            res = await self.session.post(self.AUTH_URL, json=payload, timeout=15)
            
            if res.status_code == 200:
                data = res.json()
                self.session_token = data.get("session-token")
                self.session.headers.update({"session-token": self.session_token})
                self.token_expiry = datetime.now() + timedelta(hours=5, minutes=30)
                logger.info("[Matchbook] Autenticacion (Login) Exitosa con curl_cffi.")
                return True
            elif res.status_code == 400:
                logger.error(f"[Matchbook] Credenciales incorrectas o MFA requerido: {res.text}")
                return False
            else:
                logger.error(f"[Matchbook] Falla de Auth: {res.status_code} - {res.text[:200]}")
                return False
        except Exception as e:
            logger.error(f"[Matchbook] Error de conexion en Login: {e}")
            return False

    # ==============================================================
    # 2. API SECURITY: GET SESSION (GET)
    # ==============================================================
    async def get_session(self) -> bool:
        if not self.session_token:
            return False

        try:
            await self._throttle()
            res = await self.session.get(self.AUTH_URL, timeout=10)
            if res.status_code == 200:
                return True
            elif res.status_code == 401:
                self.session_token = None
                return False
            else:
                return False
        except Exception:
            return False

    # ==============================================================
    # 3. API SECURITY: LOGOUT (DELETE)
    # ==============================================================
    async def logout(self) -> bool:
        if not self.session_token:
            return True

        try:
            await self._throttle()
            res = await self.session.delete(self.AUTH_URL, timeout=10)
            if res.status_code == 200:
                logger.info("[Matchbook] Logout exitoso. Sesion terminada.")
                self.session_token = None
                if "session-token" in self.session.headers:
                    del self.session.headers["session-token"]
                return True
            return False
        except Exception:
            return False

    # ==============================================================
    # 4. API ACCOUNT: GET ACCOUNT (GET)
    # ==============================================================
    async def get_account(self) -> Dict:
        await self.asegurar_token()
        url = f"{self.BASE_URL}/account"
        try:
            await self._throttle()
            res = await self.session.get(url, timeout=10)
            if res.status_code == 200:
                return res.json()
            else:
                logger.warning(f"[Matchbook] Error obteniendo cuenta: {res.status_code}")
        except Exception as e:
            logger.error(f"[Matchbook] Falla de red en Get Account: {e}")
        return {}

    # ==============================================================
    # 5. API ACCOUNT: GET BALANCE (GET)
    # ==============================================================
    async def get_balance(self) -> Dict:
        await self.asegurar_token()
        url = f"{self.BASE_URL}/account/balance"
        try:
            await self._throttle()
            res = await self.session.get(url, timeout=5)
            if res.status_code == 200:
                return res.json()
            elif res.status_code == 401:
                logger.warning("[Matchbook] Get Balance: 401 Unauthorized")
        except Exception as e:
            logger.error(f"[Matchbook] Error de Red en Get Balance: {e}")
        return {}

    async def obtener_balance(self) -> float:
        data = await self.get_balance()
        return float(data.get("balance", 0.0))

    # ==============================================================
    # 6. API ACCOUNT: GET ACCOUNT SPORTS (GET)
    # ==============================================================
    async def get_account_sports(self) -> List[Dict]:
        await self.asegurar_token()
        url = f"{self.BASE_URL}/account/sports"
        try:
            await self._throttle()
            res = await self.session.get(url, timeout=5)
            if res.status_code == 200:
                return res.json()
            elif res.status_code == 401:
                logger.warning("[Matchbook] Get Account Sports: 401 Unauthorized")
        except Exception as e:
            logger.error(f"[Matchbook] Error de Red en Get Account Sports: {e}")
        return []

    # ==============================================================
    # 7. API REPORTS: GET NEW WALLET TRANSACTIONS (GET)
    # ==============================================================
    async def get_new_wallet_transactions(self, offset: int = 0, per_page: int = 20,
                                          transaction_type: str = None,
                                          after: str = None, before: str = None) -> Dict:
        await self.asegurar_token()
        url = f"{self.BASE_URL}/reports/v1/transactions"
        params = {"offset": offset, "per-page": per_page}
        if transaction_type: params["transaction-type"] = transaction_type
        if after: params["after"] = after
        if before: params["before"] = before

        try:
            await self._throttle()
            res = await self.session.get(url, params=params, timeout=10)
            if res.status_code == 200:
                return res.json()
            elif res.status_code == 401:
                logger.warning("[Matchbook] Get New Wallet Transactions: 401 Unauthorized")
        except Exception as e:
            logger.error(f"[Matchbook] Error de Red en Get New Wallet Transactions: {e}")
        return {}

    # ==============================================================
    # EVENT & MARKET DATA
    # ==============================================================
    async def resolver_runner_id(self, local: str, visita: str, mkt_str: str, sport_id: int = 1) -> Optional[int]:
        await self.asegurar_token()
        url = f"{self.BASE_URL}/events"
        
        # Segmentacion temporal estricta (solo mercados próximos a iniciar en 120 min)
        ahora = datetime.utcnow()
        limite_inferior = ahora
        limite_superior = ahora + timedelta(minutes=120)

        params = {
            "sport-ids": sport_id,
            "states": "open",
            "per-page": 50,
            "include-markets": "true",
            "include-runners": "true",
            "minimum-liquidity": 50,  # Prevenir mercados ilíquidos
            "price-depth": 3,
            "price-mode": "aggregated",
            "after": int(limite_inferior.timestamp()),
            "before": int(limite_superior.timestamp())
        }
        try:
            await self._throttle()
            res = await self.session.get(url, params=params, timeout=10)
            if res.status_code != 200:
                return None
            data = res.json()

            eventos = data.get("events", [])
            mejor_evento, mejor_score = None, 0
            for ev in eventos:
                nombre_ev = ev.get("name", "").lower()
                score_total = (
                    difflib.SequenceMatcher(None, local.lower(), nombre_ev).ratio()
                    + difflib.SequenceMatcher(None, visita.lower(), nombre_ev).ratio()
                )
                if score_total > mejor_score and (local.lower() in nombre_ev or visita.lower() in nombre_ev):
                    mejor_score, mejor_evento = score_total, ev

            if not mejor_evento: return None
            mercados = mejor_evento.get("markets", [])
            if not mercados: return None

            for r in mercados[0].get("runners", []):
                r_name = r.get("name", "").lower()
                if mkt_str == "1" and local.lower()[:4] in r_name: return r.get("id")
                elif mkt_str == "2" and visita.lower()[:4] in r_name: return r.get("id")
                elif mkt_str == "X" and "draw" in r_name: return r.get("id")
            return None
        except Exception:
            return None

    # ==============================================================
    # BETTING V2: SUBMIT OFFERS (con soporte Maker/Taker)
    # ==============================================================
    async def colocar_apuesta(
        self, runner_id: int, stake: float, odds: float,
        side: str = "back", modo: str = "taker",
        keep_in_play: bool = False
    ) -> Dict:
        """
        [v7.1-MICRO] Envía orden al Exchange con soporte Maker/Taker.

        modo='taker': toma el best price (ejecución inmediata, con delay in-play)
        modo='maker': coloca orden pasiva (sin delay, puede no ejecutarse)
        """
        await self.asegurar_token()
        url = f"{self.BASE_URL}/v2/offers"
        payload = {
            "offers": [{
                "runner-id": runner_id,
                "side": side,
                "odds": odds,
                "stake": stake,
                "keep-in-play": keep_in_play
            }]
        }
        try:
            await self._throttle()
            res = await self.session.post(url, json=payload, timeout=10)
            if res.status_code in (200, 201):
                data = res.json()
                ofertas = data.get("offers", [{}])
                logger.info(
                    f"[Matchbook] Orden {modo.upper()} enviada: "
                    f"runner={runner_id} {side}@{odds:.2f} stake={stake:.2f} "
                    f"keep_in_play={keep_in_play}"
                )
                return {
                    "status": ofertas[0].get("status", "open"),
                    "runner_id": runner_id,
                    "offer_id": ofertas[0].get("id"),
                    "odds": odds,
                    "modo": modo,
                }
            else:
                logger.error(f"[Matchbook] Orden rechazada ({res.status_code}): {res.text[:300]}")
        except Exception as e:
            logger.error(f"[Matchbook] Excepcion al colocar apuesta: {e}")
        return {"status": "ERROR"}

    # ==============================================================
    # MARKET DATA: OBTENER PROFUNDIDAD (price-mode=expanded)
    # ==============================================================
    async def obtener_profundidad_mercado(
        self, event_id: int, market_id: int, runner_id: int,
        side: str = "back"
    ) -> List[Dict]:
        """
        [v7.1-MICRO] Obtiene todos los niveles de profundidad del libro de órdenes.

        Usa price-mode=expanded para recibir el ladder completo,
        no solo el best price. Esto alimenta al CalculadorVWAP.

        Retorna lista de dicts: [{"odds": 2.50, "available-amount": 100.0}, ...]
        """
        await self.asegurar_token()
        url = f"{self.BASE_URL}/events/{event_id}/markets/{market_id}/runners/{runner_id}/prices"
        params = {
            "side": side,
            "price-mode": "expanded",
        }
        try:
            await self._throttle()
            res = await self.session.get(url, params=params, timeout=10)
            if res.status_code == 200:
                data = res.json()
                precios = data.get("prices", [])
                logger.info(
                    f"[Matchbook] Profundidad obtenida: {len(precios)} niveles "
                    f"para runner {runner_id} ({side})"
                )
                return precios
            elif res.status_code == 401:
                logger.warning("[Matchbook] 401 en profundidad — renovando token")
                await self.autenticar()
        except Exception as e:
            logger.error(f"[Matchbook] Error obteniendo profundidad: {e}")
        return []

    async def obtener_libro_ordenes(self, event_id: int) -> Dict:
        await self.asegurar_token()
        url = f"{self.BASE_URL}/events/{event_id}"
        try:
            await self._throttle()
            res = await self.session.get(url, params={"include-prices": "true"}, timeout=5)
            if res.status_code == 200:
                return res.json()
        except Exception:
            pass
        return {}

    # ==============================================================
    # BETTING V2: CANCEL OFFER
    # ==============================================================
    async def cancelar_oferta(self, offer_id: str) -> bool:
        await self.asegurar_token()
        url = f"{self.BASE_URL}/offers/{offer_id}"
        try:
            await self._throttle()
            res = await self.session.delete(url, timeout=5)
            return res.status_code == 200
        except Exception:
            return False

    # ==============================================================
    # [v7.1-MICRO] HEARTBEAT KILL-SWITCH
    # ==============================================================
    async def heartbeat_loop(self):
        """
        [v7.1-MICRO] Envía POST /v1/heartbeat cada MB_HEARTBEAT_INTERVAL_SEC.

        Si falla 2 veces consecutivas → alerta de emergencia y log crítico.
        El servidor de Matchbook purgará automáticamente todas las órdenes
        abiertas si no recibe heartbeat en MB_HEARTBEAT_TIMEOUT_SEC.

        Se inicia como tarea asyncio en daemon_principal().
        Se cancela cuando se cierra la sesión.
        """
        fallos_consecutivos = 0
        ciclo = 0
        url = f"{self.BASE_URL}/v1/heartbeat"

        logger.info(f"[Heartbeat] Iniciado — ping cada {MB_HEARTBEAT_INTERVAL_SEC}s")

        while True:
            try:
                await asyncio.sleep(MB_HEARTBEAT_INTERVAL_SEC)

                if not self.session_token:
                    continue

                await self._throttle()
                res = await self.session.post(url, json={"timeout": 30}, timeout=5)
                
                ciclo += 1
                if ciclo >= 4:
                    # Keep login session alive explicitly via GET every ~60s
                    await self.session.get(self.AUTH_URL, timeout=5)
                    ciclo = 0

                if res.status_code == 200:
                    fallos_consecutivos = 0
                else:
                    fallos_consecutivos += 1
                    logger.warning(
                        f"[Heartbeat] Fallo #{fallos_consecutivos} "
                        f"(status={res.status_code})"
                    )

            except asyncio.CancelledError:
                logger.info("[Heartbeat] Tarea cancelada — apagando heartbeat")
                break
            except Exception as e:
                fallos_consecutivos += 1
                logger.error(f"[Heartbeat] Error de red #{fallos_consecutivos}: {e}")

            # Alerta crítica después de 2 fallos consecutivos
            if fallos_consecutivos >= 2:
                logger.critical(
                    "[Heartbeat] ⚠️ 2+ FALLOS CONSECUTIVOS — "
                    "Matchbook puede purgar órdenes huérfanas. "
                    "Verificar conexión de red inmediatamente."
                )
                # Intentar renovar la sesión
                try:
                    await self.autenticar()
                    fallos_consecutivos = 0
                    logger.info("[Heartbeat] Sesión renovada tras fallos de heartbeat")
                except Exception:
                    pass

    async def cerrar_sesion(self):
        # Cancelar heartbeat si existe
        if hasattr(self, '_heartbeat_task') and self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        await self.logout()
        if self.session:
            try:
                self.session.close()
            except Exception:
                pass

    def iniciar_heartbeat(self) -> asyncio.Task:
        """Inicia el heartbeat loop como tarea asyncio y guarda referencia."""
        self._heartbeat_task = asyncio.create_task(self.heartbeat_loop())
        return self._heartbeat_task


    async def obtener_eventos_hft(self, sport_ids: str = "1,2,9") -> list:
        """
        [HFT] Extrae eventos activos y liquidos.
        """
        await self.asegurar_token()
        url = f"{self.BASE_URL}/events"
        from datetime import datetime, timedelta
        ahora = datetime.utcnow()
        limite = ahora + timedelta(days=1)
        params = {
            "states": "open,suspended", "per-page": 100,
            "include-markets": "true", "include-runners": "true",
            "minimum-liquidity": 10, "price-depth": 3, "price-mode": "aggregated",
            "after": int(ahora.timestamp()), "before": int(limite.timestamp())
        }
        if sport_ids:
            params["sport-ids"] = sport_ids
        try:
            await self._throttle()
            res = await self.session.get(url, params=params, timeout=10)
            if res.status_code == 200:
                return res.json().get("events", [])
            else:
                logger.warning(f"[HFT] Error extrayendo eventos. Status {res.status_code}")
                return []
        except Exception as e:
            logger.error(f"[HFT] Excepcion extrayendo eventos: {e}")
            return []
