#!/usr/bin/env python3
"""
Runtime config generator.

Called by docker-entrypoint.sh when no config.yaml is mounted.
Reads environment variables and writes a valid config.yaml to the
path given as the first CLI argument (default: /app/config.yaml).

GATEWAY_MODELS format
---------------------
Semicolon-separated list of models. Each model is pipe-separated:

    name|replicas|weight[|fallback]

Examples:
    phi3:mini|2|0.7|llama3.2;llama3.2|5|0.3
    mistral|1|1.0
    llama3.2|3|0.6|phi3:mini;phi3:mini|2|0.4

All other settings are optional and have sensible defaults.
"""

import os
import sys

import yaml


def parse_models(raw: str) -> list:
    models = []
    for entry in raw.split(";"):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split("|")
        if len(parts) < 3:
            print(
                f"[generate_config] WARNING: skipping malformed model entry {entry!r} "
                f"(expected name|replicas|weight[|fallback])",
                file=sys.stderr,
            )
            continue
        m = {
            "name":     parts[0].strip(),
            "replicas": int(parts[1].strip()),
            "weight":   float(parts[2].strip()),
        }
        if len(parts) >= 4 and parts[3].strip():
            m["fallback"] = parts[3].strip()
        models.append(m)
    return models


def getenv_int(key: str, default: int) -> int:
    return int(os.getenv(key, default))


def getenv_bool(key: str, default: bool) -> bool:
    val = os.getenv(key, str(default)).lower()
    return val in ("1", "true", "yes")


def build_config() -> dict:
    models_raw = os.getenv("GATEWAY_MODELS", "").strip()
    if not models_raw:
        print(
            "[generate_config] ERROR: GATEWAY_MODELS is not set.\n"
            "  Either mount a config.yaml or set GATEWAY_MODELS.\n"
            "  Example: GATEWAY_MODELS='phi3:mini|2|0.7|llama3.2;llama3.2|5|0.3'",
            file=sys.stderr,
        )
        sys.exit(1)

    models = parse_models(models_raw)
    if not models:
        print("[generate_config] ERROR: No valid models parsed from GATEWAY_MODELS", file=sys.stderr)
        sys.exit(1)

    total_weight = sum(m["weight"] for m in models)
    if not (0.95 <= total_weight <= 1.05):
        print(
            f"[generate_config] WARNING: model weights sum to {total_weight:.2f} (expected ~1.0)",
            file=sys.stderr,
        )

    return {
        "gateway": {
            "host": "0.0.0.0",
            "port": getenv_int("GATEWAY_PORT", 8081),
            "max_concurrent": getenv_int("MAX_CONCURRENT", 20),
            "request_timeout": getenv_int("REQUEST_TIMEOUT", 30),
            "queue_size": getenv_int("QUEUE_SIZE", 100),
        },
        "models": models,
        "load_balancing": {
            "algorithm": os.getenv("LB_ALGORITHM", "adaptive"),
        },
        "circuit_breaker": {
            "failure_threshold": getenv_int("CIRCUIT_FAILURE_THRESHOLD", 3),
            "timeout": getenv_int("CIRCUIT_TIMEOUT", 30),
        },
        "self_healing": {
            "reconcile_interval": getenv_int("RECONCILE_INTERVAL", 20),
            "auto_restart": getenv_bool("AUTO_RESTART", True),
            "adaptive_weights": getenv_bool("ADAPTIVE_WEIGHTS", True),
            "weight_adjust_step": float(os.getenv("WEIGHT_ADJUST_STEP", "0.05")),
            "weight_min": float(os.getenv("WEIGHT_MIN", "0.05")),
            "max_parallel_pulls": getenv_int("MAX_PARALLEL_PULLS", 2),
            "pull_retries": getenv_int("PULL_RETRIES", 5),
        },
        "monitoring": {
            "prometheus_enabled": getenv_bool("PROMETHEUS_ENABLED", True),
            "health_check_interval": getenv_int("HEALTH_CHECK_INTERVAL", 10),
        },
        "redis": {
            "host": os.getenv("REDIS_HOST", "redis"),
            "port": getenv_int("REDIS_PORT", 6379),
        },
    }


def main():
    output_path = sys.argv[1] if len(sys.argv) > 1 else "/app/config.yaml"
    config = build_config()

    with open(output_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    model_summary = ", ".join(
        f"{m['name']} x{m['replicas']} ({m['weight']*100:.0f}%)"
        for m in config["models"]
    )
    print(f"[generate_config] Written: {output_path}")
    print(f"[generate_config] Models : {model_summary}")
    print(f"[generate_config] Redis  : {config['redis']['host']}:{config['redis']['port']}")
    print(f"[generate_config] Algo   : {config['load_balancing']['algorithm']}")


if __name__ == "__main__":
    main()
