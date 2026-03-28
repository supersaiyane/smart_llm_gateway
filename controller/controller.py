#!/usr/bin/env python3
"""
Smart LLM Gateway — Controller

Runs as a separate container alongside the Ollama nodes.
Responsibilities:
  1. Bootstrap   — wait for Ollama nodes, pull required models.
  2. Register    — write model→node assignments into Redis so the gateway
                   knows where to send requests.
  3. Reconcile   — run a continuous loop to detect and fix drift:
                     * missing model on a node → re-pull
                     * crashed container (if Docker socket is mounted) → restart
                     * update Redis assignments after any change
"""

import logging
import os
import sys
import time
import concurrent.futures
from typing import Dict, List, Optional

import redis
import requests
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s controller — %(message)s",
)
log = logging.getLogger("controller")


# ------------------------------------------------------------------
# Configuration (from env + config.yaml)
# ------------------------------------------------------------------

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
RECONCILE_INTERVAL = int(os.getenv("RECONCILE_INTERVAL", 20))
MAX_PARALLEL_PULLS = int(os.getenv("MAX_PARALLEL_PULLS", 2))
PULL_RETRIES = int(os.getenv("PULL_RETRIES", 5))

CONFIG_PATH = os.getenv("CONFIG_PATH", "/app/config.yaml")


def _load_yaml_config() -> Optional[dict]:
    try:
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return None


def _parse_model_assignments() -> Dict[str, List[str]]:
    """
    Returns  { model_name: ["ollamaN:11434", ...] }

    Priority:
      1. config.yaml  (mounted into /app/config.yaml)
      2. MODEL_REPLICAS env var as fallback
         format: "phi3:mini:2,llama3.2:5"
    """
    cfg = _load_yaml_config()
    if cfg and "models" in cfg:
        assignments: Dict[str, List[str]] = {}
        idx = 1
        for m in cfg["models"]:
            name = m["name"]
            replicas = int(m.get("replicas", 1))
            assignments[name] = []
            for _ in range(replicas):
                assignments[name].append(f"ollama{idx}:11434")
                idx += 1
        return assignments

    # Fallback: parse MODEL_REPLICAS env var
    raw = os.getenv("MODEL_REPLICAS", "")
    if not raw:
        log.error("Neither config.yaml nor MODEL_REPLICAS env var found — exiting")
        sys.exit(1)

    assignments: Dict[str, List[str]] = {}
    idx = 1
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.rsplit(":", 1)
        if len(parts) != 2:
            log.warning(f"Skipping malformed MODEL_REPLICAS entry: {entry!r}")
            continue
        model_name, replicas_str = parts
        replicas = int(replicas_str)
        assignments[model_name] = []
        for _ in range(replicas):
            assignments[model_name].append(f"ollama{idx}:11434")
            idx += 1
    return assignments


# ------------------------------------------------------------------
# Ollama helpers
# ------------------------------------------------------------------

def _ollama_url(node: str) -> str:
    return f"http://{node}"


def _is_node_alive(node: str, timeout: int = 3) -> bool:
    try:
        r = requests.get(f"{_ollama_url(node)}/api/tags", timeout=timeout)
        return r.status_code == 200
    except Exception:
        return False


def _models_on_node(node: str) -> List[str]:
    try:
        r = requests.get(f"{_ollama_url(node)}/api/tags", timeout=5)
        if r.status_code == 200:
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass
    return []


def _pull_model(node: str, model: str, retries: int = PULL_RETRIES) -> bool:
    """Pull `model` onto `node`. Returns True on success."""
    url = f"{_ollama_url(node)}/api/pull"
    for attempt in range(1, retries + 1):
        try:
            log.info(f"[pull] {node} ← {model} (attempt {attempt}/{retries})")
            res = requests.post(
                url,
                json={"name": model, "stream": False},
                timeout=600,   # large models can take a while
            )
            if res.status_code == 200:
                log.info(f"[pull] {node} ← {model} OK")
                return True
            log.warning(f"[pull] {node} ← {model} HTTP {res.status_code}")
        except Exception as exc:
            log.warning(f"[pull] {node} ← {model} error: {exc}")
        if attempt < retries:
            time.sleep(min(2 ** attempt, 30))
    log.error(f"[pull] {node} ← {model} FAILED after {retries} attempts")
    return False


# ------------------------------------------------------------------
# Redis helpers
# ------------------------------------------------------------------

def _register_assignments(r: redis.Redis, assignments: Dict[str, List[str]]):
    """Write model→nodes into Redis so the gateway can look them up."""
    for model, nodes in assignments.items():
        # Store as "ollamaN" (no port) — gateway appends :11434
        node_names = [n.split(":")[0] for n in nodes]
        r.set(f"model:{model}", ",".join(node_names))
        log.info(f"[redis] model:{model} → {node_names}")


# ------------------------------------------------------------------
# Bootstrap: wait for all nodes, then pull all models
# ------------------------------------------------------------------

def _wait_for_nodes(nodes: List[str], timeout: int = 300):
    """Block until every node responds to /api/tags or timeout expires."""
    deadline = time.time() + timeout
    pending = set(nodes)
    log.info(f"Waiting for {len(nodes)} Ollama node(s) ...")

    while pending and time.time() < deadline:
        for node in list(pending):
            if _is_node_alive(node):
                log.info(f"  {node} ready")
                pending.remove(node)
        if pending:
            time.sleep(3)

    if pending:
        log.warning(f"Timed out waiting for: {pending} — continuing anyway")


def _bootstrap(r: redis.Redis, assignments: Dict[str, List[str]]):
    all_nodes = [n for nodes in assignments.values() for n in nodes]
    _wait_for_nodes(all_nodes)

    # Pull models in parallel (bounded by MAX_PARALLEL_PULLS)
    tasks = []  # (node, model)
    for model, nodes in assignments.items():
        for node in nodes:
            tasks.append((node, model))

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_PARALLEL_PULLS) as pool:
        futures = {pool.submit(_pull_model, node, model): (node, model) for node, model in tasks}
        for fut in concurrent.futures.as_completed(futures):
            node, model = futures[fut]
            ok = fut.result()
            if not ok:
                log.warning(f"Model {model} may be missing on {node}")

    _register_assignments(r, assignments)
    log.info("Bootstrap complete")


# ------------------------------------------------------------------
# Reconciliation loop
# ------------------------------------------------------------------

def _reconcile(r: redis.Redis, assignments: Dict[str, List[str]]):
    """
    For each (model, node) pair:
      - If the node is alive and the model is missing → pull it.
      - If the node is down → attempt Docker restart (if socket available).
    Re-register assignments after any repair.
    """
    changed = False

    for model, nodes in assignments.items():
        for node in nodes:
            if not _is_node_alive(node, timeout=3):
                log.warning(f"[reconcile] {node} is down")
                _try_restart_container(node)
                continue

            loaded = _models_on_node(node)
            # Normalise names for comparison (strip ":latest" suffix if absent in config)
            loaded_base = [m.split(":")[0] if ":" not in m else m for m in loaded]
            model_base = model.split(":")[0] if ":" not in model else model

            if model not in loaded and model_base not in loaded_base:
                log.warning(f"[reconcile] {model} missing on {node} — pulling")
                ok = _pull_model(node, model, retries=PULL_RETRIES)
                if ok:
                    changed = True

    if changed:
        _register_assignments(r, assignments)


def _try_restart_container(node: str):
    """
    Attempt to restart the container named after the node (e.g. "ollama3").
    Only works when /var/run/docker.sock is mounted into the controller container.
    """
    container_name = node.split(":")[0]
    try:
        import docker  # optional dependency
        client = docker.from_env()
        container = client.containers.get(container_name)
        container.restart(timeout=10)
        log.info(f"[restart] {container_name} restarted via Docker API")
    except ImportError:
        log.debug("docker SDK not available — skipping container restart")
    except Exception as exc:
        log.warning(f"[restart] Could not restart {container_name}: {exc}")


# ------------------------------------------------------------------
# Entry point
# ------------------------------------------------------------------

def main():
    log.info("Controller starting ...")

    assignments = _parse_model_assignments()
    log.info(f"Model assignments: { {k: len(v) for k, v in assignments.items()} }")

    # Connect to Redis with retry
    r = None
    for attempt in range(1, 11):
        try:
            r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
            r.ping()
            log.info(f"Redis connected ({REDIS_HOST}:{REDIS_PORT})")
            break
        except redis.exceptions.ConnectionError:
            log.warning(f"Redis not ready (attempt {attempt}/10) ...")
            time.sleep(3)
    else:
        log.error("Cannot connect to Redis — exiting")
        sys.exit(1)

    _bootstrap(r, assignments)

    log.info(f"Reconciliation loop started (interval={RECONCILE_INTERVAL}s)")
    while True:
        time.sleep(RECONCILE_INTERVAL)
        try:
            _reconcile(r, assignments)
        except Exception as exc:
            log.error(f"Reconcile error: {exc}")


if __name__ == "__main__":
    main()
