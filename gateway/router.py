"""
Load balancing algorithms.

Four strategies selectable via config.yaml → load_balancing.algorithm:

  round_robin       Simple turn-by-turn fairness using a Redis counter.
  least_connections Fewest in-flight requests wins — best general-purpose choice.
  weighted_latency  Sorts by recent observed latency; good for heterogeneous hardware.
  adaptive          Combines latency + active connections + failure recency.
                    This is the default and works best in production.
"""

import random
import time
from typing import List

import redis as redis_lib


# ------------------------------------------------------------------
# Individual algorithms
# ------------------------------------------------------------------

def _round_robin(r: redis_lib.Redis, servers: List[str]) -> List[str]:
    """Increment a shared counter and rotate the list from that offset."""
    idx = int(r.incr("rr:counter")) % len(servers)
    return servers[idx:] + servers[:idx]


def _least_connections(r: redis_lib.Redis, servers: List[str]) -> List[str]:
    """Sort by active_connections ascending with small jitter to spread ties."""
    scored = []
    for s in servers:
        conns = int(r.hget(f"server:{s}", "active_connections") or 0)
        scored.append((conns + random.uniform(0, 0.1), s))
    scored.sort(key=lambda x: x[0])
    return [s for _, s in scored]


def _weighted_latency(r: redis_lib.Redis, servers: List[str]) -> List[str]:
    """Sort by recent latency + failure penalty."""
    scored = []
    for s in servers:
        latency = float(r.hget(f"server:{s}", "latency") or 1.0)
        failures = int(r.hget(f"server:{s}", "failures") or 0)
        score = latency + (failures * 0.5) + random.uniform(0, 0.05)
        scored.append((score, s))
    scored.sort(key=lambda x: x[0])
    return [s for _, s in scored]


def _adaptive(r: redis_lib.Redis, servers: List[str]) -> List[str]:
    """
    Composite score:
      latency             — observed round-trip time
      failures * 0.5      — each failure adds half-second equivalent penalty
      active_connections * 0.2 — light penalty for busy nodes
      recency_penalty     — extra 3-point hit if failed in the last 20s
      jitter              — small random noise prevents thundering herd
    """
    now = time.time()
    scored = []
    for s in servers:
        key = f"server:{s}"
        latency = float(r.hget(key, "latency") or 1.0)
        failures = int(r.hget(key, "failures") or 0)
        conns = int(r.hget(key, "active_connections") or 0)
        last_failure = float(r.hget(key, "last_failure") or 0)

        recency = 3.0 if (now - last_failure) < 20 else 0.0
        score = latency + (failures * 0.5) + (conns * 0.2) + recency + random.uniform(0, 0.05)
        scored.append((score, s))

    scored.sort(key=lambda x: x[0])
    return [s for _, s in scored]


# ------------------------------------------------------------------
# Dispatch table
# ------------------------------------------------------------------

_ALGORITHMS = {
    "round_robin": _round_robin,
    "least_connections": _least_connections,
    "weighted_latency": _weighted_latency,
    "adaptive": _adaptive,
}


def rank_servers(r: redis_lib.Redis, servers: List[str], algorithm: str = "adaptive") -> List[str]:
    """
    Return servers sorted best-first by the chosen algorithm.
    Falls back to adaptive if an unknown algorithm name is given.
    """
    fn = _ALGORITHMS.get(algorithm, _adaptive)
    return fn(r, servers)
