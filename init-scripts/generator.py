#!/usr/bin/env python3
"""
docker-compose generator

Reads config.yaml from the repo root and writes docker-compose.yml.
Run via:  python3 init-scripts/generator.py
Or:       make generate
"""

import sys
import yaml
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
CONFIG_PATH = REPO_ROOT / "config.yaml"
OUTPUT_PATH = REPO_ROOT / "docker-compose.yml"


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def build_compose(cfg: dict) -> dict:
    models = cfg["models"]
    redis_cfg = cfg.get("redis", {})
    gateway_cfg = cfg.get("gateway", {})
    monitoring_cfg = cfg.get("monitoring", {})

    services = {}
    volumes = {}
    node_names = []   # e.g. ["ollama1", "ollama2", ...]
    model_replica_map = {}   # model_name → [ollamaN, ...]

    # ---------------------------------------------------------------
    # Ollama containers — one per replica
    # ---------------------------------------------------------------
    idx = 1
    for model in models:
        model_name = model["name"]
        replicas = model["replicas"]
        model_replica_map[model_name] = []

        for _ in range(replicas):
            svc_name = f"ollama{idx}"
            vol_name = f"ollama{idx}_data"
            node_names.append(svc_name)
            model_replica_map[model_name].append(svc_name)

            services[svc_name] = {
                "image": "ollama/ollama:latest",
                "restart": "unless-stopped",
                "volumes": [f"{vol_name}:/root/.ollama"],
                "networks": ["llm-net"],
                "healthcheck": {
                    "test": ["CMD", "curl", "-sf", f"http://localhost:11434/api/tags"],
                    "interval": "30s",
                    "timeout": "10s",
                    "retries": 5,
                    "start_period": "20s",
                },
            }
            volumes[vol_name] = None
            idx += 1

    # Build MODEL_REPLICAS and OLLAMA_NODES env strings for controller
    model_replicas_str = ",".join(
        f"{m['name']}:{m['replicas']}" for m in models
    )
    ollama_nodes_str = ",".join(f"{n}:11434" for n in node_names)

    # ---------------------------------------------------------------
    # Redis
    # ---------------------------------------------------------------
    services["redis"] = {
        "image": "redis:7-alpine",
        "restart": "unless-stopped",
        "networks": ["llm-net"],
        "healthcheck": {
            "test": ["CMD", "redis-cli", "ping"],
            "interval": "10s",
            "timeout": "5s",
            "retries": 5,
        },
    }

    # ---------------------------------------------------------------
    # Controller  (Python — replaces the old bash script)
    # ---------------------------------------------------------------
    services["controller"] = {
        "build": {"context": "./controller"},
        "restart": "unless-stopped",
        "depends_on": ["redis"] + node_names,
        "environment": {
            "REDIS_HOST": redis_cfg.get("host", "redis"),
            "REDIS_PORT": str(redis_cfg.get("port", 6379)),
            "OLLAMA_NODES": ollama_nodes_str,
            "MODEL_REPLICAS": model_replicas_str,
            "MAX_PARALLEL_PULLS": str(
                cfg.get("self_healing", {}).get("max_parallel_pulls", 2)
            ),
            "PULL_RETRIES": str(
                cfg.get("self_healing", {}).get("pull_retries", 5)
            ),
            "RECONCILE_INTERVAL": str(
                cfg.get("self_healing", {}).get("reconcile_interval", 20)
            ),
        },
        "volumes": [
            "./config.yaml:/app/config.yaml:ro",
            "/var/run/docker.sock:/var/run/docker.sock",
        ],
        "networks": ["llm-net"],
    }

    # ---------------------------------------------------------------
    # Gateway
    # ---------------------------------------------------------------
    gateway_depends = ["redis", "controller"] + node_names
    services["gateway"] = {
        "build": {"context": "./gateway"},
        "restart": "unless-stopped",
        "ports": [f"{gateway_cfg.get('port', 8081)}:8081"],
        "depends_on": gateway_depends,
        "environment": {
            "CONFIG_PATH": "/app/config.yaml",
            "REDIS_HOST": redis_cfg.get("host", "redis"),
            "REDIS_PORT": str(redis_cfg.get("port", 6379)),
        },
        "volumes": ["./config.yaml:/app/config.yaml:ro"],
        "networks": ["llm-net"],
        "healthcheck": {
            "test": ["CMD", "curl", "-sf", "http://localhost:8081/health"],
            "interval": "15s",
            "timeout": "5s",
            "retries": 5,
        },
    }

    # ---------------------------------------------------------------
    # Nginx
    # ---------------------------------------------------------------
    services["nginx"] = {
        "image": "nginx:alpine",
        "restart": "unless-stopped",
        "ports": ["8080:80"],
        "depends_on": ["gateway"],
        "volumes": ["./configs/nginx.conf:/etc/nginx/nginx.conf:ro"],
        "networks": ["llm-net"],
    }

    # ---------------------------------------------------------------
    # Prometheus  (optional)
    # ---------------------------------------------------------------
    if monitoring_cfg.get("prometheus_enabled", False):
        services["prometheus"] = {
            "image": "prom/prometheus:latest",
            "restart": "unless-stopped",
            "ports": ["9090:9090"],
            "volumes": [
                "./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro"
            ],
            "networks": ["llm-net"],
        }

    # ---------------------------------------------------------------
    # Assemble
    # ---------------------------------------------------------------
    compose = {
        "services": services,
        "volumes": {k: {} if v is None else v for k, v in volumes.items()},
        "networks": {"llm-net": {"driver": "bridge"}},
    }

    return compose


def main():
    print(f"Reading config from: {CONFIG_PATH}")
    cfg = load_config()

    # Basic validation
    models = cfg.get("models", [])
    if not models:
        print("ERROR: no models defined in config.yaml", file=sys.stderr)
        sys.exit(1)

    total_weight = sum(m.get("weight", 0) for m in models)
    if not (0.95 <= total_weight <= 1.05):
        print(
            f"WARNING: model weights sum to {total_weight:.2f} (expected ~1.0)",
            file=sys.stderr,
        )

    compose = build_compose(cfg)

    with open(OUTPUT_PATH, "w") as f:
        yaml.dump(compose, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    total_replicas = sum(m.get("replicas", 1) for m in models)
    print(f"Generated: {OUTPUT_PATH}")
    print(f"  Models   : {[m['name'] for m in models]}")
    print(f"  Replicas : {total_replicas} Ollama containers")
    print(f"  Algorithm: {cfg.get('load_balancing', {}).get('algorithm', 'adaptive')}")
    if cfg.get("monitoring", {}).get("prometheus_enabled"):
        print("  Prometheus: enabled (port 9090)")


if __name__ == "__main__":
    main()
