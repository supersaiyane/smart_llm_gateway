"""
Smart LLM Gateway — main application.

Request lifecycle:
  1. Acquire semaphore (concurrency cap from config)
  2. Choose model by weight (reads adaptive weights from Redis)
  3. Fetch replica list from Redis (set by controller at startup)
  4. Rank replicas with the configured load-balancing algorithm
  5. Try each replica in order, skipping OPEN circuit breakers
  6. On total failure, cascade to the model's configured fallback
  7. Release semaphore, record metrics
"""

import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager
from typing import Optional

import redis
import requests
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from circuit import CircuitBreaker
from config import get_config, reload_config
from health import start_health_checker
from healer import SelfHealer
from metrics import (
    active_requests,
    fallbacks_total,
    metrics_response,
    model_weight,
    node_failures,
    node_latency,
    request_latency_seconds,
    requests_total,
)
from router import rank_servers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger("gateway")

# ------------------------------------------------------------------
# Globals initialised in lifespan
# ------------------------------------------------------------------
_r: redis.Redis = None
_semaphore: asyncio.Semaphore = None
_healer: SelfHealer = None


# ------------------------------------------------------------------
# Application lifespan
# ------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _r, _semaphore, _healer

    cfg = get_config()
    _r = redis.Redis(host=cfg.redis.host, port=cfg.redis.port, decode_responses=True)
    _semaphore = asyncio.Semaphore(cfg.gateway.max_concurrent)

    _init_server_state(cfg)

    servers = cfg.all_servers()
    start_health_checker(_r, servers, interval=cfg.monitoring.health_check_interval)

    _healer = SelfHealer(_r, servers)
    _healer.start()

    logger.info(
        f"Gateway ready | models={[m.name for m in cfg.models]} "
        f"| replicas={sum(m.replicas for m in cfg.models)} "
        f"| algorithm={cfg.load_balancing.algorithm}"
    )

    yield

    _healer.stop()
    logger.info("Gateway shutting down")


app = FastAPI(title="Smart LLM Gateway", version="2.0", lifespan=lifespan)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _init_server_state(cfg=None):
    """Seed Redis with default stats for every known server."""
    if cfg is None:
        cfg = get_config()
    for s in cfg.all_servers():
        key = f"server:{s}"
        if not _r.exists(key):
            _r.hset(key, mapping={
                "latency": 0.5,
                "failures": 0,
                "circuit_open": 0,
                "last_failure": 0,
                "active_connections": 0,
            })


def _get_model_servers(model: str):
    """Look up replica nodes registered by the controller."""
    val = _r.get(f"model:{model}")
    if not val:
        return []
    return [f"http://{n.strip()}:11434" for n in val.split(",") if n.strip()]


def _choose_model() -> str:
    """
    Weighted random model selection.
    Uses adaptive weights stored in Redis; falls back to config baseline.
    """
    cfg = get_config()
    names, weights = [], []
    for m in cfg.models:
        stored = _r.hget("model_weights", m.name)
        w = float(stored) if stored else m.weight
        names.append(m.name)
        weights.append(w)
        model_weight.labels(model=m.name).set(w)
    return random.choices(names, weights=weights, k=1)[0]


def _http_generate(server: str, model: str, prompt: str, timeout: int) -> Optional[dict]:
    """
    Synchronous Ollama call — runs in a thread-pool executor.
    Tracks active_connections atomically via Redis HINCRBY.
    """
    key = f"server:{server}"
    _r.hincrby(key, "active_connections", 1)
    t0 = time.time()
    try:
        res = requests.post(
            f"{server}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=timeout,
        )
        latency = time.time() - t0
        _r.hset(key, "latency", round(latency, 4))
        node_latency.labels(server=server).set(latency)

        if res.status_code == 200:
            data = res.json()
            data["_latency"] = latency
            return data

        logger.warning(f"[gateway] {server} returned HTTP {res.status_code}")
        return None

    except Exception as exc:
        logger.warning(f"[gateway] {server} error: {exc}")
        return None

    finally:
        _r.hincrby(key, "active_connections", -1)


async def _try_servers(model: str, prompt: str) -> Optional[dict]:
    """Try all ranked replicas for `model`, respecting circuit breakers."""
    cfg = get_config()
    loop = asyncio.get_event_loop()

    servers = _get_model_servers(model)
    if not servers:
        return None

    ranked = await loop.run_in_executor(
        None, rank_servers, _r, servers, cfg.load_balancing.algorithm
    )

    for server in ranked:
        cb = CircuitBreaker(
            _r, server,
            cfg.circuit_breaker.failure_threshold,
            cfg.circuit_breaker.timeout,
        )
        if not cb.is_available():
            continue

        result = await loop.run_in_executor(
            None, _http_generate, server, model, prompt, cfg.gateway.request_timeout
        )

        if result is not None:
            cb.record_success()
            latency = result.pop("_latency", 0)
            request_latency_seconds.labels(model=model, server=server).observe(latency)
            requests_total.labels(model=model, server=server, status="success").inc()
            result["served_by"] = server
            result["model_used"] = model
            return result

        cb.record_failure()
        requests_total.labels(model=model, server=server, status="failure").inc()
        failures = int(_r.hget(f"server:{server}", "failures") or 0)
        node_failures.labels(server=server).set(failures)

    return None


async def _call_llm(prompt: str) -> dict:
    """Full routing logic: primary model → fallback chain → error."""
    cfg = get_config()
    model = _choose_model()

    result = await _try_servers(model, prompt)
    if result is not None:
        return result

    # Cascade to fallback
    model_cfg = cfg.model_map.get(model)
    if model_cfg and model_cfg.fallback:
        fallback = model_cfg.fallback
        logger.warning(f"[gateway] All {model} replicas failed — trying fallback '{fallback}'")
        fallbacks_total.labels(original_model=model, fallback_model=fallback).inc()
        result = await _try_servers(fallback, prompt)
        if result is not None:
            result["fallback"] = True
            result["original_model"] = model
            requests_total.labels(model=fallback, server=result.get("served_by", ""), status="fallback").inc()
            return result

    return {"error": "all backends failed", "model_attempted": model}


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.post("/generate")
async def generate(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)

    cfg = get_config()
    active_requests.inc()

    # Wait for semaphore slot (bounded by request_timeout)
    try:
        await asyncio.wait_for(_semaphore.acquire(), timeout=cfg.gateway.request_timeout)
    except asyncio.TimeoutError:
        active_requests.dec()
        return JSONResponse(
            {"error": "system overloaded", "message": "try again shortly"},
            status_code=503,
            headers={"Retry-After": "5"},
        )

    try:
        result = await asyncio.wait_for(
            _call_llm(prompt),
            timeout=cfg.gateway.request_timeout,
        )
        return result
    except asyncio.TimeoutError:
        return JSONResponse({"error": "request timed out"}, status_code=504)
    finally:
        _semaphore.release()
        active_requests.dec()


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/status")
async def status():
    cfg = get_config()
    loop = asyncio.get_event_loop()
    servers = cfg.all_servers()

    node_info = {}
    for s in servers:
        data = await loop.run_in_executor(None, _r.hgetall, f"server:{s}")
        node_info[s] = {
            "latency_s": round(float(data.get("latency", 0)), 3),
            "failures": int(data.get("failures", 0)),
            "active_connections": int(data.get("active_connections", 0)),
            "circuit": "open" if int(data.get("circuit_open", 0)) else "closed",
        }

    weights = {}
    for m in cfg.models:
        stored = _r.hget("model_weights", m.name)
        weights[m.name] = float(stored) if stored else m.weight

    return {
        "gateway": "healthy",
        "algorithm": cfg.load_balancing.algorithm,
        "model_weights": weights,
        "nodes": node_info,
        "settings": {
            "max_concurrent": cfg.gateway.max_concurrent,
            "request_timeout": cfg.gateway.request_timeout,
            "circuit_failure_threshold": cfg.circuit_breaker.failure_threshold,
            "circuit_timeout_s": cfg.circuit_breaker.timeout,
        },
    }


@app.get("/nodes")
async def nodes():
    cfg = get_config()
    loop = asyncio.get_event_loop()
    result = {}
    for s in cfg.all_servers():
        data = await loop.run_in_executor(None, _r.hgetall, f"server:{s}")
        result[s] = {k: (float(v) if _is_numeric(v) else v) for k, v in data.items()}
    return result


@app.post("/config/reload")
async def config_reload():
    new_cfg = reload_config()
    _init_server_state(new_cfg)
    return {
        "status": "reloaded",
        "models": [m.name for m in new_cfg.models],
        "algorithm": new_cfg.load_balancing.algorithm,
    }


@app.get("/metrics")
async def metrics():
    return metrics_response()


# ------------------------------------------------------------------
# Util
# ------------------------------------------------------------------

def _is_numeric(v: str) -> bool:
    try:
        float(v)
        return True
    except (ValueError, TypeError):
        return False
