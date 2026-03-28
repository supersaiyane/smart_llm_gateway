"""
Self-healing daemon (runs inside the gateway process).

Responsibilities:
  1. Circuit recovery  — probes OPEN-circuit nodes; closes them when they respond.
  2. Adaptive weights  — if a model's average latency is significantly higher
                         than the fleet average, its routing weight is reduced
                         automatically. It recovers toward the baseline weight
                         when latency normalises.

This is intentionally lightweight. Heavy lifting (container restarts, model
pulls) is handled by the separate controller service which has Docker socket
access.
"""

import time
import threading
import logging
from typing import List, Dict

import requests
import redis as redis_lib

from config import get_config

logger = logging.getLogger("healer")


class SelfHealer:

    def __init__(self, r: redis_lib.Redis, servers: List[str]):
        self.r = r
        self.servers = servers
        self._running = False
        self._thread: threading.Thread = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="self-healer",
        )
        self._thread.start()
        logger.info("Self-healer started")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self):
        while self._running:
            cfg = get_config()
            interval = cfg.self_healing.reconcile_interval
            try:
                self._reconcile()
            except Exception as exc:
                logger.error(f"[healer] reconcile error: {exc}")
            time.sleep(interval)

    def _reconcile(self):
        cfg = get_config()
        self._recover_open_circuits()
        if cfg.self_healing.adaptive_weights:
            self._adjust_weights()

    # ------------------------------------------------------------------
    # Circuit recovery
    # ------------------------------------------------------------------

    def _recover_open_circuits(self):
        for server in self.servers:
            data = self.r.hgetall(f"server:{server}")
            if int(data.get("circuit_open", 0)) == 1:
                logger.warning(f"[healer] Probing open circuit: {server}")
                self._probe_and_recover(server)

    def _probe_and_recover(self, server: str):
        try:
            res = requests.get(f"{server}/api/tags", timeout=4)
            if res.status_code == 200:
                self.r.hset(f"server:{server}", mapping={"circuit_open": 0, "failures": 0})
                logger.info(f"[healer] {server} recovered — circuit closed")
        except Exception as exc:
            logger.debug(f"[healer] {server} still down: {exc}")

    # ------------------------------------------------------------------
    # Adaptive weight adjustment
    # ------------------------------------------------------------------

    def _adjust_weights(self):
        """
        Algorithm:
          - Compute average observed latency per model (mean of its replicas).
          - Compute global fleet average.
          - Models > 1.5x global average get their weight reduced by step.
          - Models < 0.8x global average recover toward their config baseline.
          - Weights are floored at weight_min to avoid complete starvation.
        """
        cfg = get_config()
        step = cfg.self_healing.weight_adjust_step
        w_min = cfg.self_healing.weight_min

        model_latencies: Dict[str, float] = {}
        for model in cfg.models:
            servers = cfg.servers_for_model(model.name)
            if not servers:
                continue
            lats = [
                float(self.r.hget(f"server:{s}", "latency") or 1.0)
                for s in servers
            ]
            model_latencies[model.name] = sum(lats) / len(lats)

        if not model_latencies:
            return

        global_avg = sum(model_latencies.values()) / len(model_latencies)

        for model_name, avg_lat in model_latencies.items():
            baseline = cfg.model_map[model_name].weight
            stored = self.r.hget("model_weights", model_name)
            current = float(stored) if stored else baseline

            if avg_lat > global_avg * 1.5:
                new_w = round(max(w_min, current - step), 4)
                self.r.hset("model_weights", model_name, new_w)
                logger.info(
                    f"[healer] {model_name} slow ({avg_lat:.2f}s vs avg {global_avg:.2f}s) "
                    f"→ weight {current:.3f} → {new_w:.3f}"
                )
            elif avg_lat < global_avg * 0.8 and current < baseline:
                new_w = round(min(baseline, current + step), 4)
                self.r.hset("model_weights", model_name, new_w)
                logger.info(
                    f"[healer] {model_name} recovering ({avg_lat:.2f}s) "
                    f"→ weight {current:.3f} → {new_w:.3f}"
                )
