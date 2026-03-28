#!/usr/bin/env python3
"""
Inspect which models are loaded on each Ollama node.

Replaces check_models.sh — uses the Ollama REST API directly, so it works
from the host machine without the ollama CLI or getent.

Usage:
    python3 test-scripts/check_models.py [options]

Options:
    --nodes    Comma-separated list of host:port pairs
               (default: reads config.yaml, falls back to ollama1:11434,...,ollama7:11434)
    --timeout  Per-node request timeout in seconds (default: 5)

Exit codes:
    0  All nodes reachable
    1  One or more nodes are down
"""

import argparse
import sys
from pathlib import Path

import requests


def parse_args():
    p = argparse.ArgumentParser(description="Inspect models on all Ollama nodes")
    p.add_argument("--nodes",   default=None,
                   help="Comma-separated host:port list, e.g. ollama1:11434,ollama2:11434")
    p.add_argument("--timeout", type=int, default=5)
    return p.parse_args()


def discover_nodes() -> list:
    """Read node list from config.yaml in the repo root."""
    config_path = Path(__file__).parent.parent / "config.yaml"
    try:
        import yaml
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        nodes = []
        idx = 1
        for m in cfg.get("models", []):
            for _ in range(m.get("replicas", 1)):
                nodes.append(f"ollama{idx}:11434")
                idx += 1
        return nodes
    except Exception:
        return []


def check_node(node: str, timeout: int) -> dict:
    url = f"http://{node}/api/tags"
    try:
        res = requests.get(url, timeout=timeout)
        if res.status_code == 200:
            models = res.json().get("models", [])
            return {"node": node, "up": True, "models": models}
        return {"node": node, "up": False, "models": [], "error": f"HTTP {res.status_code}"}
    except requests.exceptions.ConnectionError:
        return {"node": node, "up": False, "models": [], "error": "connection refused"}
    except requests.exceptions.Timeout:
        return {"node": node, "up": False, "models": [], "error": "timeout"}
    except Exception as exc:
        return {"node": node, "up": False, "models": [], "error": str(exc)}


def fmt_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def run(args) -> int:
    if args.nodes:
        nodes = [n.strip() for n in args.nodes.split(",") if n.strip()]
    else:
        nodes = discover_nodes()

    if not nodes:
        # last-resort defaults
        nodes = [f"ollama{i}:11434" for i in range(1, 8)]

    print(f"\n  Model Inspection — {len(nodes)} node(s)")
    print(f"  {'─' * 60}")
    print()

    down_nodes = []
    total_models_loaded = 0

    for info in (check_node(n, args.timeout) for n in nodes):
        node = info["node"]
        if not info["up"]:
            down_nodes.append(node)
            print(f"  {node}")
            print(f"    STATUS : DOWN  ({info.get('error', 'unknown')})")
            print()
            continue

        models = info["models"]
        total_models_loaded += len(models)
        print(f"  {node}")
        print(f"    STATUS : UP")
        if models:
            for m in models:
                name   = m.get("name", "unknown")
                size   = m.get("size", 0)
                family = m.get("details", {}).get("family", "")
                tag    = f"  [{family}]" if family else ""
                print(f"    MODEL  : {name:<30}  {fmt_size(size)}{tag}")
        else:
            print(f"    MODEL  : (none loaded yet)")
        print()

    print(f"  {'─' * 60}")
    print(f"  Nodes up   : {len(nodes) - len(down_nodes)}/{len(nodes)}")
    print(f"  Models     : {total_models_loaded} total across cluster")

    if down_nodes:
        print(f"  Down nodes : {', '.join(down_nodes)}")
        print(f"\n  FAILED\n")
        return 1

    print(f"\n  PASSED\n")
    return 0


if __name__ == "__main__":
    sys.exit(run(parse_args()))
