# -*- coding: utf-8 -*-
"""
conectores.base
===============
Clase base para conectores de API externas.
Implementa rate limiting (Token Bucket), retries con exponential backoff,
y manejo unificado de errores (requests y respuestas vacías).
"""

import time
import requests
import logging
from typing import Optional, Dict, Any
from requests.exceptions import RequestException

logger = logging.getLogger("CONTINUITY.Conectores")

class RateLimiter:
    """Implementa Rate Limiting genérico (Token Bucket simplificado)."""
    def __init__(self, calls: int, period: float):
        self.calls = calls
        self.period = period
        self.timestamps = []

    def wait(self):
        now = time.time()
        # Remove timestamps older than the period
        self.timestamps = [t for t in self.timestamps if now - t < self.period]
        
        if len(self.timestamps) >= self.calls:
            # We hit the limit, need to wait until the oldest timestamp falls out of the period
            sleep_time = self.period - (now - self.timestamps[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
        
        self.timestamps.append(time.time())


class ConectorBase:
    def __init__(self, api_key: str, calls_per_sec: float = 2.0, max_retries: int = 3):
        self.api_key = api_key
        # Default: 2 requests per second
        self.limiter = RateLimiter(calls=int(max(1, calls_per_sec)), period=1.0 if calls_per_sec >= 1 else 1.0/calls_per_sec)
        self.max_retries = max_retries
        self.session = requests.Session()

    def get_json(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """
        Realiza una petición GET segura con rate limiting y retries.
        """
        if not headers:
            headers = {}

        for attempt in range(self.max_retries):
            self.limiter.wait()
            try:
                resp = self.session.get(url, headers=headers, params=params, timeout=15)
                
                # Check for rate limit status codes
                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 2 ** attempt))
                    logger.warning(f"[API] 429 Rate Limit. Esperando {retry_after}s (intento {attempt+1}/{self.max_retries})")
                    time.sleep(retry_after)
                    continue
                
                resp.raise_for_status()
                return resp.json()

            except RequestException as e:
                logger.error(f"[API] Error en GET {url}: {e}")
                if attempt < self.max_retries - 1:
                    sleep_time = 2 ** attempt
                    logger.info(f"[API] Reintentando en {sleep_time}s...")
                    time.sleep(sleep_time)
                else:
                    logger.error("[API] Se agotaron los reintentos.")
                    return None
            except ValueError:
                logger.error(f"[API] La respuesta no es JSON válido en {url}")
                return None

        return None
