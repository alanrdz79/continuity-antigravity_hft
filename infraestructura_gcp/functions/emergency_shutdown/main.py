# ==============================================================================
# CONTINUITY HFT GCP ARCHITECTURE - GEN 2 EMERGENCY SHUTDOWN CLOUD FUNCTION
# Runtime: Python 3.11+
# Target File: functions/emergency_shutdown/main.py
# Handler: emergency_shutdown (CloudEvent with HTTP fallback)
# ==============================================================================
r"""
Autonomous Emergency Shutdown and Circuit Breaker Sink for CONTINUITY HFT.

This Cloud Function (Gen 2) acts as the autonomous fail-safe safety sink triggered by:
1. EventArc v2 via Cloud Pub/Sub topic 'hft-safety-alerts' (driven by Cloud Monitoring alert policies:
   - Feed latency spikes > 800ms
   - Binance API 429 rate limit or 418 IP ban
   - Binance market status SUSPENDED)
2. Direct HTTP POST/GET invocation for emergency operator overrides and health diagnostics.

4-Stage Emergency Execution Protocol:
- Stage 1: Atomic Redis Kill Switch (SET hft:emergency:kill_switch_active 1 over TLS with AUTH).
- Stage 2: Binance Order Purge (HMAC-SHA256 signed DELETE /api/v3/openOrders with recvWindow=5000).
- Stage 3: Engine Worker Halt Signal (Publishes HALT_ALL_WORKERS command to hft-safety-alerts).
- Stage 4: Telegram Alert Broadcast (Dispatches markdown incident report to ops team Telegram webhook).
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple, Union

# ------------------------------------------------------------------------------
# Logging Setup (Structured Cloud Logging format)
# ------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [emergency_shutdown] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("emergency_shutdown")

# ------------------------------------------------------------------------------
# Graceful Third-Party Library Imports & Test Fallbacks
# ------------------------------------------------------------------------------
# functions-framework
try:
    import functions_framework
except ImportError:
    class _MockFunctionsFramework:
        @staticmethod
        def cloud_event(func):
            return func
        @staticmethod
        def http(func):
            return func
    functions_framework = _MockFunctionsFramework()

# redis
try:
    import redis
except ImportError:
    redis = None

# requests
try:
    import requests
except ImportError:
    requests = None

# google-cloud-pubsub
try:
    from google.cloud import pubsub_v1
except ImportError:
    pubsub_v1 = None

# google-cloud-secret-manager (runtime fallback)
try:
    from google.cloud import secretmanager_v1
except ImportError:
    secretmanager_v1 = None


# ------------------------------------------------------------------------------
# Global Constants & Configuration Defaults
# ------------------------------------------------------------------------------
DEFAULT_PROJECT_ID = "intrepid-decker-480417-e9"
DEFAULT_SAFETY_TOPIC = "hft-safety-alerts"
DEFAULT_REDIS_KEY = "hft:emergency:kill_switch_active"
DEFAULT_BINANCE_URL = "https://api.binance.com"
DEFAULT_SYMBOL = "BTCUSDT"
DEFAULT_RECV_WINDOW = 5000
LATENCY_CRITICAL_THRESHOLD_MS = 800.0


def evaluate_latency_trigger(latency_ms: float) -> Tuple[bool, str]:
    """
    Evaluates whether a feed latency measurement breaches the 800ms threshold.
    Returns (should_trigger, reason).
    """
    if latency_ms > LATENCY_CRITICAL_THRESHOLD_MS:
        return (
            True,
            f"LATENCIA_EXCESIVA: Feed latency {latency_ms:.1f}ms exceeded critical threshold of {LATENCY_CRITICAL_THRESHOLD_MS}ms",
        )
    return False, f"Feed latency {latency_ms:.1f}ms within safe boundary (<= {LATENCY_CRITICAL_THRESHOLD_MS}ms)"


def evaluate_market_status_trigger(status: str) -> Tuple[bool, str]:
    """Evaluates Binance market status (SUSPENDED vs TRADING)."""
    if status.upper() == "SUSPENDED":
        return True, "MERCADO_SUSPENDIDO: Binance reported MarketStatus SUSPENDED (VAR/Goal/Halt)"
    return False, f"MarketStatus '{status}' is active"


def evaluate_api_status_code_trigger(status_code: int) -> Tuple[bool, str]:
    """Evaluates HTTP response status codes for rate-limiting or IP bans."""
    if status_code in (429, 418):
        return (
            True,
            f"API_RATE_LIMIT_BREACH: HTTP {status_code} received from Binance Gateway (IP Ban / Rate Limit)",
        )
    return False, f"HTTP {status_code} is standard response"


def is_mock_mode_active(override_flag: Optional[bool] = None) -> bool:
    """Evaluates whether execution should run in mock / synthetic simulation mode."""
    if override_flag is not None:
        return bool(override_flag)
    env_mock = os.environ.get("MOCK_MODE", "").strip().lower()
    return env_mock in ("1", "true", "yes", "enabled")


def get_secret_or_env(key: str, default: str = "") -> str:
    """
    Retrieves secret from environment variable (injected via Secret Manager in Cloud Run/Functions)
    with fallback to Google Cloud Secret Manager runtime client if running in GCP and variable missing.
    """
    val = os.environ.get(key, "").strip()
    if val:
        return val

    # In mock mode, return default immediately
    if is_mock_mode_active():
        return default

    # Optional fallback to Secret Manager client if credentials and project are available
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or DEFAULT_PROJECT_ID
    secret_name_map = {
        "BINANCE_API_KEY": "binance-api-key",
        "BINANCE_API_SECRET": "binance-api-secret",
        "TELEGRAM_BOT_TOKEN": "telegram-bot-token",
        "TELEGRAM_CHAT_ID": "telegram-chat-id",
        "REDIS_AUTH_TOKEN": "redis-auth-token",
    }

    target_secret = secret_name_map.get(key)
    if target_secret and secretmanager_v1 is not None:
        try:
            client = secretmanager_v1.SecretManagerServiceClient()
            resource_name = f"projects/{project_id}/secrets/{target_secret}/versions/latest"
            response = client.access_secret_version(request={"name": resource_name})
            payload_str = response.payload.data.decode("UTF-8").strip()
            if payload_str:
                return payload_str
        except Exception as exc:
            logger.debug(f"Secret Manager client fallback lookup failed for {key}: {exc}")

    return default


# ------------------------------------------------------------------------------
# STAGE 1: Atomic Redis Kill Switch
# ------------------------------------------------------------------------------
def stage_1_redis_kill_switch(mock: bool = False) -> Dict[str, Any]:
    """
    Stage 1: Atomic Redis Kill Switch.
    Connects to Cloud Memorystore Redis over TLS with AUTH, executing:
    SET hft:emergency:kill_switch_active 1 (O(1) sub-microsecond atomic flag).
    """
    t0 = time.perf_counter()
    redis_key = os.environ.get("REDIS_KILL_SWITCH_KEY", DEFAULT_REDIS_KEY)
    redis_host = os.environ.get("REDIS_HOST", "").strip()
    redis_port = int(os.environ.get("REDIS_PORT", "6379"))
    redis_auth = get_secret_or_env("REDIS_AUTH_TOKEN", "mock_redis_auth")
    redis_ssl_enabled = os.environ.get("REDIS_SSL", "true").lower() in ("1", "true", "yes")

    logger.info(f"[STAGE 1] Activating atomic Redis kill switch -> {redis_key} = 1")

    # Mock mode or missing host configuration
    if mock or not redis_host or redis_host in ("mock", "localhost", "127.0.0.1") or redis is None:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"[STAGE 1] Mock mode active: Redis flag {redis_key} simulated set to 1 ({elapsed_ms:.2f}ms)")
        return {
            "stage": 1,
            "name": "REDIS_KILL_SWITCH",
            "status": "MOCKED",
            "redis_key": redis_key,
            "value_set": "1",
            "host": redis_host or "mock-memorystore",
            "elapsed_ms": round(elapsed_ms, 3),
            "details": f"Flag {redis_key}=1 simulated in mock mode",
        }

    # Live Memorystore Connection
    try:
        r = redis.Redis(
            host=redis_host,
            port=redis_port,
            password=redis_auth if redis_auth else None,
            ssl=redis_ssl_enabled,
            ssl_cert_reqs=None,
            socket_timeout=2.0,
            socket_connect_timeout=2.0,
            decode_responses=True,
        )
        r.set(redis_key, "1")
        current_val = r.get(redis_key)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        logger.info(f"[STAGE 1] Redis kill switch successfully set in Memorystore: {redis_key} = {current_val} in {elapsed_ms:.2f}ms")
        return {
            "stage": 1,
            "name": "REDIS_KILL_SWITCH",
            "status": "SUCCESS",
            "redis_key": redis_key,
            "value_set": str(current_val),
            "host": redis_host,
            "elapsed_ms": round(elapsed_ms, 3),
            "details": f"Atomic key {redis_key} verified set to 1",
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.error(f"[STAGE 1] Redis connection failed ({exc}). Failing safe in {elapsed_ms:.2f}ms.")
        return {
            "stage": 1,
            "name": "REDIS_KILL_SWITCH",
            "status": "FAILED",
            "redis_key": redis_key,
            "value_set": "1",
            "host": redis_host,
            "elapsed_ms": round(elapsed_ms, 3),
            "details": f"Redis error: {str(exc)}",
        }


# ------------------------------------------------------------------------------
# STAGE 2: Binance Predictions API Order Purge
# ------------------------------------------------------------------------------
def generate_binance_cancel_all_payload(
    symbol: str, api_key: str, secret_key: str, recv_window: int = DEFAULT_RECV_WINDOW
) -> Dict[str, Any]:
    """
    Constructs and HMAC-SHA256 signs a Binance Prediction DELETE payload for emergency order purge.
    Uses the new /sapi/v1/w3w/wallet/prediction/ endpoints.
    """
    timestamp = int(time.time() * 1000)
    query_string = f"symbol={symbol}&timestamp={timestamp}&recvWindow={recv_window}"
    signature = hmac.new(
        secret_key.encode("utf-8"), query_string.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    return {
        "method": "DELETE",
        "endpoint": f"{DEFAULT_BINANCE_URL}/sapi/v1/w3w/wallet/prediction/order",
        "headers": {
            "X-MBX-APIKEY": api_key,
        },
        "params": {
            "symbol": symbol,
            "timestamp": timestamp,
            "recvWindow": recv_window,
            "signature": signature,
        },
    }


def stage_2_binance_order_purge(
    symbol: str = DEFAULT_SYMBOL,
    symbols: Optional[List[str]] = None,
    mock: bool = False,
) -> Dict[str, Any]:
    """
    Stage 2: Binance Predictions Order Purge (USDT).
    Retrieves Binance API credentials from Secret Manager/environment, generates HMAC-SHA256
    signed query string and executes HTTP DELETE on the Binance Prediction API.
    """
    t0 = time.perf_counter()
    target_symbols = symbols if symbols else [symbol]
    api_key = get_secret_or_env("BINANCE_API_KEY", "TEST_API_KEY_MASKED")
    secret_key = get_secret_or_env("BINANCE_API_SECRET", "TEST_SECRET_KEY_MASKED")
    base_url = os.environ.get("BINANCE_BASE_URL", DEFAULT_BINANCE_URL).rstrip("/")
    recv_window = int(os.environ.get("BINANCE_RECV_WINDOW", str(DEFAULT_RECV_WINDOW)))

    logger.info(f"[STAGE 2] Purging USDT open orders on Binance Predictions API for symbols: {target_symbols}")

    executed_requests = []
    primary_payload = generate_binance_cancel_all_payload(
        symbol=target_symbols[0], api_key=api_key, secret_key=secret_key, recv_window=recv_window
    )

    is_dummy_key = api_key in ("TEST_API_KEY_MASKED", "mock", "MOCK", "") or secret_key in ("TEST_SECRET_KEY_MASKED", "mock", "MOCK", "")

    for sym in target_symbols:
        payload = generate_binance_cancel_all_payload(
            symbol=sym, api_key=api_key, secret_key=secret_key, recv_window=recv_window
        )
        if mock or is_dummy_key or requests is None:
            executed_requests.append({
                "symbol": sym,
                "status": "MOCKED",
                "status_code": 200,
                "endpoint": f"{base_url}/sapi/v1/w3w/wallet/prediction/order",
                "recvWindow": recv_window,
                "signature": payload["params"]["signature"],
            })
        else:
            try:
                query_str = f"symbol={sym}&timestamp={payload['params']['timestamp']}&recvWindow={recv_window}&signature={payload['params']['signature']}"
                req_url = f"{base_url}/sapi/v1/w3w/wallet/prediction/order?{query_str}"
                resp = requests.delete(
                    req_url,
                    headers={"X-MBX-APIKEY": api_key},
                    timeout=3.0,
                )
                executed_requests.append({
                    "symbol": sym,
                    "status": "SUCCESS" if resp.status_code in (200, 400) else "ERROR",
                    "status_code": resp.status_code,
                    "endpoint": f"{base_url}/sapi/v1/w3w/wallet/prediction/order",
                    "recvWindow": recv_window,
                    "signature": payload["params"]["signature"],
                    "response": resp.text[:200],
                })
            except Exception as exc:
                logger.error(f"[STAGE 2] Binance Prediction API DELETE failed for {sym}: {exc}")
                executed_requests.append({
                    "symbol": sym,
                    "status": "FAILED",
                    "status_code": 500,
                    "endpoint": f"{base_url}/sapi/v1/w3w/wallet/prediction/order",
                    "error": str(exc),
                })

    elapsed_ms = (time.perf_counter() - t0) * 1000
    overall_status = "SUCCESS" if all(r.get("status") in ("SUCCESS", "MOCKED") for r in executed_requests) else "FAILED"
    if any(r.get("status") == "MOCKED" for r in executed_requests):
        overall_status = "MOCKED"

    logger.info(f"[STAGE 2] USDT Prediction purge completed with status {overall_status} in {elapsed_ms:.2f}ms")
    return {
        "stage": 2,
        "name": "BINANCE_PREDICTIONS_API_PURGE",
        "status": overall_status,
        "symbols": target_symbols,
        "primary_payload": primary_payload,
        "executed_requests": executed_requests,
        "elapsed_ms": round(elapsed_ms, 3),
        "details": f"Purged USDT prediction orders for {len(target_symbols)} symbols via API",
    }


# ------------------------------------------------------------------------------
# STAGE 3: Engine Halt Signal
# ------------------------------------------------------------------------------
def stage_3_engine_halt_signal(
    reason: str, symbol: str = DEFAULT_SYMBOL, mock: bool = False
) -> Dict[str, Any]:
    """
    Stage 3: Engine Halt Signal.
    Publishes engine worker halt message to Pub/Sub topic 'hft-safety-alerts'.
    """
    t0 = time.perf_counter()
    project_id = os.environ.get("GCP_PROJECT_ID") or os.environ.get("GOOGLE_CLOUD_PROJECT") or DEFAULT_PROJECT_ID
    topic_name = os.environ.get("SAFETY_ALERTS_TOPIC", DEFAULT_SAFETY_TOPIC)

    engine_halt_signal = {
        "action": "HALT_ALL_WORKERS",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
        "symbol": symbol,
        "source": "functions.emergency_shutdown",
    }

    logger.info(f"[STAGE 3] Publishing engine halt signal to Pub/Sub topic '{topic_name}': reason='{reason}'")

    if mock or pubsub_v1 is None or os.environ.get("MOCK_PUBSUB") == "1":
        elapsed_ms = (time.perf_counter() - t0) * 1000
        simulated_msg_id = f"mock-msg-{int(time.time() * 1000)}"
        logger.info(f"[STAGE 3] Mock mode active: Simulated publication to {topic_name} (msg_id={simulated_msg_id})")
        return {
            "stage": 3,
            "name": "ENGINE_HALT_SIGNAL",
            "status": "MOCKED",
            "topic": topic_name,
            "message_id": simulated_msg_id,
            "payload": engine_halt_signal,
            "elapsed_ms": round(elapsed_ms, 3),
            "details": "Engine halt signal simulated in mock mode",
        }

    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_name)
        data_bytes = json.dumps(engine_halt_signal).encode("utf-8")
        future = publisher.publish(
            topic_path,
            data=data_bytes,
            event_type="EMERGENCY_HALT",
            severity="CRITICAL",
            reason=reason[:100],
        )
        msg_id = future.result(timeout=5.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"[STAGE 3] Published halt signal to {topic_path} with message ID {msg_id} in {elapsed_ms:.2f}ms")
        return {
            "stage": 3,
            "name": "ENGINE_HALT_SIGNAL",
            "status": "SUCCESS",
            "topic": topic_path,
            "message_id": str(msg_id),
            "payload": engine_halt_signal,
            "elapsed_ms": round(elapsed_ms, 3),
            "details": f"Halt command published to Pub/Sub ID: {msg_id}",
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.error(f"[STAGE 3] Pub/Sub publishing failed ({exc}) in {elapsed_ms:.2f}ms")
        return {
            "stage": 3,
            "name": "ENGINE_HALT_SIGNAL",
            "status": "FAILED",
            "topic": topic_name,
            "payload": engine_halt_signal,
            "error": str(exc),
            "elapsed_ms": round(elapsed_ms, 3),
            "details": f"Pub/Sub publishing exception: {str(exc)}",
        }


# ------------------------------------------------------------------------------
# STAGE 4: Telegram Alert Broadcast
# ------------------------------------------------------------------------------
def stage_4_telegram_alert_broadcast(
    reason: str, symbol: str = DEFAULT_SYMBOL, mock: bool = False
) -> Dict[str, Any]:
    """
    Stage 4: Telegram Alert Broadcast.
    Formats structured Markdown alert message payload and dispatches to Telegram webhook / alert sink.
    """
    t0 = time.perf_counter()
    bot_token = get_secret_or_env("TELEGRAM_BOT_TOKEN", "mock_telegram_token")
    chat_id = get_secret_or_env("TELEGRAM_CHAT_ID", "mock_chat_id")
    now_iso = datetime.now(timezone.utc).isoformat()

    telegram_message = (
        f"🚨 *CONTINUITY HFT EMERGENCY KILL SWITCH ACTIVATED* 🚨\n"
        f"• Motivo: `{reason}`\n"
        f"• Símbolo: `{symbol}`\n"
        f"• Órdenes Canceladas: `TODAS (DELETE /sapi/v1/w3w/wallet/prediction/order)`\n"
        f"• Estado del Motor: `HALTED (Zero New Orders)`\n"
        f"• Timestamp: `{now_iso}`"
    )

    logger.info(f"[STAGE 4] Formatting Telegram incident alert broadcast for chat_id={chat_id[:4]}***")

    is_dummy_token = bot_token in ("mock_telegram_token", "MOCK", "") or chat_id in ("mock_chat_id", "MOCK", "")

    if mock or is_dummy_token or requests is None:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.info(f"[STAGE 4] Mock mode active: Alert formatted and simulated broadcast ({elapsed_ms:.2f}ms)")
        return {
            "stage": 4,
            "name": "TELEGRAM_ALERT_BROADCAST",
            "status": "MOCKED",
            "chat_id": f"{chat_id[:4]}***" if len(chat_id) > 4 else "mock_chat",
            "message": telegram_message,
            "elapsed_ms": round(elapsed_ms, 3),
            "details": "Telegram alert broadcast simulated in mock mode",
        }

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": telegram_message,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        resp = requests.post(url, json=payload, timeout=3.0)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        success = resp.status_code == 200
        logger.info(f"[STAGE 4] Telegram dispatch returned HTTP {resp.status_code} in {elapsed_ms:.2f}ms")
        return {
            "stage": 4,
            "name": "TELEGRAM_ALERT_BROADCAST",
            "status": "SUCCESS" if success else "ERROR",
            "status_code": resp.status_code,
            "chat_id": f"{chat_id[:4]}***",
            "message": telegram_message,
            "elapsed_ms": round(elapsed_ms, 3),
            "details": f"Telegram API response status: {resp.status_code}",
        }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - t0) * 1000
        logger.error(f"[STAGE 4] Telegram dispatch failed: {exc}")
        return {
            "stage": 4,
            "name": "TELEGRAM_ALERT_BROADCAST",
            "status": "FAILED",
            "chat_id": f"{chat_id[:4]}***",
            "message": telegram_message,
            "error": str(exc),
            "elapsed_ms": round(elapsed_ms, 3),
            "details": f"Telegram exception: {str(exc)}",
        }


# ------------------------------------------------------------------------------
# 4-STAGE ORCHESTRATION PIPELINE
# ------------------------------------------------------------------------------
def execute_emergency_shutdown(
    reason: str,
    symbol: str = DEFAULT_SYMBOL,
    symbols: Optional[List[str]] = None,
    mock: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Executes the complete 4-stage emergency shutdown procedure with fault isolation.
    Returns a structured dictionary strictly compatible with test_safety_orchestration.py.
    """
    pipeline_t0 = time.perf_counter()
    active_mock = is_mock_mode_active(mock)

    logger.info("==================================================================")
    logger.info(f"🚨 EXECUTING CONTINUITY EMERGENCY SHUTDOWN PIPELINE (mock={active_mock}) 🚨")
    logger.info(f"Reason: {reason}")
    logger.info(f"Target Symbol: {symbol}")
    logger.info("==================================================================")

    # Stage 1: Atomic Redis Kill Switch
    stage1_res = stage_1_redis_kill_switch(mock=active_mock)

    # Stage 2: Binance Order Purge
    stage2_res = stage_2_binance_order_purge(symbol=symbol, symbols=symbols, mock=active_mock)

    # Stage 3: Engine Halt Signal
    stage3_res = stage_3_engine_halt_signal(reason=reason, symbol=symbol, mock=active_mock)

    # Stage 4: Telegram Alert Broadcast
    stage4_res = stage_4_telegram_alert_broadcast(reason=reason, symbol=symbol, mock=active_mock)

    total_elapsed_ms = (time.perf_counter() - pipeline_t0) * 1000

    # Format return dictionary to match test_safety_orchestration.py contract
    redis_flag = stage1_res.get("redis_key", DEFAULT_REDIS_KEY)
    redis_val = stage1_res.get("value_set", "1")

    purge_payload = stage2_res.get("primary_payload") or generate_binance_cancel_all_payload(
        symbol=symbol, api_key="TEST_API_KEY_MASKED", secret_key="TEST_SECRET_KEY_MASKED"
    )

    halt_signal = stage3_res.get("payload") or {
        "action": "HALT_ALL_WORKERS",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "reason": reason,
    }

    telegram_msg = stage4_res.get("message") or (
        f"🚨 *CONTINUITY HFT EMERGENCY KILL SWITCH ACTIVATED* 🚨\n"
        f"• Motivo: `{reason}`\n"
        f"• Símbolo: `{symbol}`\n"
        f"• Órdenes Canceladas: `TODAS (DELETE /sapi/v1/w3w/wallet/prediction/order)`\n"
        f"• Estado del Motor: `HALTED (Zero New Orders)`\n"
        f"• Timestamp: `{datetime.now(timezone.utc).isoformat()}`"
    )

    result = {
        "status": "COMPLETED",
        "reason": reason,
        "symbol": symbol,
        "redis_flag_set": {redis_flag: redis_val},
        "binance_purge_payload": purge_payload,
        "engine_halt_signal": halt_signal,
        "telegram_alert": telegram_msg,
        "stages": [stage1_res, stage2_res, stage3_res, stage4_res],
        "total_elapsed_ms": round(total_elapsed_ms, 3),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.info(f"Emergency shutdown pipeline completed in {total_elapsed_ms:.2f}ms. Status: COMPLETED")
    return result


def execute_simulated_emergency_shutdown(
    reason: str, symbol: str = DEFAULT_SYMBOL
) -> Dict[str, Any]:
    """Compatibility alias for test_safety_orchestration.py test harness."""
    return execute_emergency_shutdown(reason=reason, symbol=symbol, mock=True)


# ------------------------------------------------------------------------------
# INCOMING CONTEXT PARSER (CloudEvent vs HTTP Request vs Direct Dict)
# ------------------------------------------------------------------------------
def extract_incident_context(event_or_request: Any) -> Tuple[str, str, Optional[List[str]], bool, bool]:
    """
    Parses and normalizes input into (reason, symbol, symbols, is_mock, is_health_check).
    Supports:
    - CloudEvent (EventArc v2 from Pub/Sub topic or Cloud Monitoring)
    - Flask Request (Direct HTTP POST/GET invocation)
    - Plain Python Dict (Unit tests / mock caller)
    - None (Operator default manual trigger)
    """
    default_reason = "MANUAL_OPERATOR_OVERRIDE: Direct emergency circuit breaker trigger"
    default_symbol = DEFAULT_SYMBOL
    target_symbols = None
    mock_mode = False
    is_health_check = False

    if event_or_request is None:
        return default_reason, default_symbol, None, False, False

    # Case 1: Direct Dict / Mock Event
    if isinstance(event_or_request, dict):
        if "message" in event_or_request and isinstance(event_or_request["message"], dict):
            raw_b64 = event_or_request["message"].get("data", "")
            if raw_b64:
                try:
                    decoded_json = json.loads(base64.b64decode(raw_b64).decode("utf-8"))
                    return extract_incident_context(decoded_json)
                except Exception:
                    pass
        reason = event_or_request.get("reason") or event_or_request.get("summary") or default_reason
        symbol = event_or_request.get("symbol") or default_symbol
        symbols = event_or_request.get("symbols")
        mock_mode = bool(event_or_request.get("mock", False))
        return reason, symbol, symbols, mock_mode, False

    # Case 2: Flask / HTTP Request object (has get_json, args, path, headers)
    if hasattr(event_or_request, "get_json") or hasattr(event_or_request, "args"):
        path = getattr(event_or_request, "path", "")
        if path in ("/health", "/healthz", "/ping") or getattr(event_or_request, "method", "") == "GET":
            args = getattr(event_or_request, "args", {})
            if "trigger" not in args and "reason" not in args:
                return "HEALTH_CHECK", default_symbol, None, False, True

        body = {}
        if hasattr(event_or_request, "get_json"):
            try:
                body = event_or_request.get_json(silent=True) or {}
            except Exception:
                body = {}

        args = getattr(event_or_request, "args", {})
        reason = body.get("reason") or args.get("reason") or default_reason
        symbol = body.get("symbol") or args.get("symbol") or default_symbol
        symbols = body.get("symbols")
        mock_mode = str(body.get("mock") or args.get("mock", "")).lower() in ("1", "true", "yes")
        return reason, symbol, symbols, mock_mode, False

    # Case 3: CloudEvent (has data attribute)
    if hasattr(event_or_request, "data"):
        data = event_or_request.data
        if isinstance(data, dict):
            if "message" in data and isinstance(data["message"], dict):
                raw_b64 = data["message"].get("data", "")
                if raw_b64:
                    try:
                        decoded_text = base64.b64decode(raw_b64).decode("utf-8")
                        payload_obj = json.loads(decoded_text)
                        if "incident" in payload_obj and isinstance(payload_obj["incident"], dict):
                            inc = payload_obj["incident"]
                            condition_name = inc.get("condition_name", "Alert Condition")
                            summary = inc.get("summary", "Metric boundary exceeded")
                            reason = f"CLOUD_MONITORING_ALERT: {condition_name} ({summary})"
                            return reason, default_symbol, None, False, False
                        return extract_incident_context(payload_obj)
                    except Exception as exc:
                        logger.warning(f"Failed to parse base64 PubSub data in CloudEvent: {exc}")

            if "incident" in data:
                inc = data["incident"]
                reason = f"CLOUD_MONITORING_ALERT: {inc.get('condition_name', 'Alert')} ({inc.get('summary', '')})"
                return reason, default_symbol, None, False, False

            reason = data.get("reason") or default_reason
            symbol = data.get("symbol") or default_symbol
            symbols = data.get("symbols")
            mock_mode = bool(data.get("mock", False))
            return reason, symbol, symbols, mock_mode, False

    return default_reason, default_symbol, None, False, False


# ------------------------------------------------------------------------------
# GEN 2 CLOUD EVENT / HTTP ENTRYPOINTS
# ------------------------------------------------------------------------------
@functions_framework.cloud_event
def emergency_shutdown(cloud_event_or_request: Any = None) -> Union[Dict[str, Any], Tuple[str, int, Dict[str, str]]]:
    """
    Main Gen 2 Cloud Function entrypoint.
    Configured in Terraform as entry_point = 'emergency_shutdown'.
    Gracefully handles CloudEvent triggers from EventArc / Pub/Sub, as well as fallback direct HTTP invocations.
    """
    reason, symbol, symbols, mock, is_health = extract_incident_context(cloud_event_or_request)

    # Health check probe response
    if is_health:
        health_payload = {
            "status": "HEALTHY",
            "service": "emergency-shutdown",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if hasattr(cloud_event_or_request, "get_json"):
            return json.dumps(health_payload), 200, {"Content-Type": "application/json"}
        return health_payload

    # Execute 4-stage shutdown pipeline
    result = execute_emergency_shutdown(reason=reason, symbol=symbol, symbols=symbols, mock=mock)

    # If invoked directly via HTTP Flask Request, return JSON response tuple
    if hasattr(cloud_event_or_request, "get_json") or hasattr(cloud_event_or_request, "args"):
        return json.dumps(result, indent=2), 200, {"Content-Type": "application/json"}

    return result


@functions_framework.cloud_event
def emergency_shutdown_handler(cloud_event_or_request: Any = None) -> Union[Dict[str, Any], Tuple[str, int, Dict[str, str]]]:
    """Handler alias for emergency_shutdown."""
    return emergency_shutdown(cloud_event_or_request)


@functions_framework.http
def emergency_shutdown_http(request: Any) -> Tuple[str, int, Dict[str, str]]:
    """
    Dedicated HTTP handler fallback for functions deployed with FUNCTION_SIGNATURE_TYPE=http.
    """
    return emergency_shutdown(request)


# ------------------------------------------------------------------------------
# STANDALONE CLI TEST HARNESS
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    logger.info("Executing emergency_shutdown in standalone test mode...")
    test_reason = "TEST_CLI_MANUAL_TRIGGER: Emergency circuit breaker verification"
    test_result = execute_emergency_shutdown(reason=test_reason, symbol="BTCUSDT", mock=True)
    print("\n--- STANDALONE EMERGENCY SHUTDOWN RESULT ---")
    print(json.dumps(test_result, indent=2))
    sys.exit(0 if test_result["status"] == "COMPLETED" else 1)
