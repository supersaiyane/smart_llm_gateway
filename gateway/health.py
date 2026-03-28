"""
Passive health-check daemon.

Runs in a background thread and probes every Ollama node on /api/tags
every `interval` seconds. On success it resets the failure counter.
On failure it increments it (which may trigger the circuit breaker).
"""

import time
import threading
import logging
from typing import List

import requests
import redis as redis_lib

logger = logging.getLogger("health")


def _probe(r: redis_lib.Redis, server: str):
    key = f"server:{server}"
    try:
        res = requests.get(f"{server}/api/tags", timeout=3)
        if res.status_code == 200:
            r.hset(key, mapping={"failures": 0, "circuit_open": 0})
            logger.debug(f"[health] {server} OK")
        else:
            _mark_unhealthy(r, key, server)
    except Exception as exc:
        _mark_unhealthy(r, key, server)
        logger.debug(f"[health] {server} unreachable: {exc}")


def _mark_unhealthy(r: redis_lib.Redis, key: str, server: str):
    failures = int(r.hget(key, "failures") or 0) + 1
    r.hset(key, mapping={"failures": failures, "last_failure": time.time()})
    logger.warning(f"[health] {server} unhealthy (failures={failures})")


def health_check_loop(r: redis_lib.Redis, servers: List[str], interval: int = 10):
    """Run forever, probing all servers every `interval` seconds."""
    while True:
        for server in servers:
            _probe(r, server)
        time.sleep(interval)


def start_health_checker(r: redis_lib.Redis, servers: List[str], interval: int = 10) -> threading.Thread:
    t = threading.Thread(
        target=health_check_loop,
        args=(r, servers, interval),
        daemon=True,
        name="health-checker",
    )
    t.start()
    return t
