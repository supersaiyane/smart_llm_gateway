#!/usr/bin/env python3
"""
Load balancing distribution validator.

Sends N sequential requests and validates that:
  - More than one server is used (lb is active)
  - More than one model is used (weight routing is active)
  - No single server handles all the traffic (distribution is spread)

Usage:
    python3 test-scripts/test_load_balancing.py [options]

Options:
    --url       Gateway URL        (default: http://localhost:8080/generate)
    --requests  Total requests     (default: 30)
    --timeout   Per-request timeout (default: 60)

Exit codes:
    0  Load balancing is active and traffic is distributed
    1  All requests hit a single server (lb not working)
"""

import argparse
import sys
import time
from collections import Counter

import requests


def parse_args():
    p = argparse.ArgumentParser(description="Load balancing distribution validator")
    p.add_argument("--url",      default="http://localhost:8080/generate")
    p.add_argument("--requests", type=int, default=30, dest="total")
    p.add_argument("--timeout",  type=int, default=60)
    return p.parse_args()


def bar(count: int, total: int, width: int = 30) -> str:
    filled = int(width * count / total) if total else 0
    return f"[{'#' * filled}{'-' * (width - filled)}] {count:3d} ({100*count/total:.1f}%)"


def run(args) -> int:
    print(f"\n  Load Balancing Distribution Test")
    print(f"  {'─' * 55}")
    print(f"  URL      : {args.url}")
    print(f"  Requests : {args.total}")
    print()

    server_dist = Counter()
    model_dist  = Counter()
    fallback_count = 0
    failures = 0

    for i in range(1, args.total + 1):
        try:
            res = requests.post(
                args.url,
                json={"prompt": f"Say the number {i} and nothing else."},
                timeout=args.timeout,
            )
            if res.status_code == 200:
                data = res.json()
                server   = data.get("served_by", "unknown")
                model    = data.get("model_used", "unknown")
                fallback = data.get("fallback", False)
                latency  = data.get("total_duration", 0)

                server_dist[server] += 1
                model_dist[model]   += 1
                if fallback:
                    fallback_count += 1

                fb_tag = " [FALLBACK]" if fallback else ""
                print(f"  [{i:>3}]  {server:<35}  {model}{fb_tag}")
            else:
                failures += 1
                print(f"  [{i:>3}]  HTTP {res.status_code}")
        except Exception as exc:
            failures += 1
            print(f"  [{i:>3}]  ERROR: {exc}")

    total_ok = sum(server_dist.values())

    print(f"\n  Server distribution  ({total_ok} successful requests)")
    print(f"  {'─' * 55}")
    for server, count in sorted(server_dist.items(), key=lambda x: -x[1]):
        print(f"  {server:<35}  {bar(count, total_ok)}")

    print(f"\n  Model distribution")
    print(f"  {'─' * 55}")
    for model, count in sorted(model_dist.items(), key=lambda x: -x[1]):
        print(f"  {model:<20}  {bar(count, total_ok)}")

    print(f"\n  Summary")
    print(f"  {'─' * 55}")
    print(f"  Requests sent    : {args.total}")
    print(f"  Successful       : {total_ok}")
    print(f"  Failures         : {failures}")
    print(f"  Fallbacks used   : {fallback_count}")
    print(f"  Unique servers   : {len(server_dist)}")
    print(f"  Unique models    : {len(model_dist)}")

    # Validation checks
    checks = []

    if len(server_dist) > 1:
        checks.append(("PASS", "Multiple servers used — load balancing is active"))
    else:
        checks.append(("FAIL", "Only 1 server used — load balancing is NOT working"))

    if len(model_dist) > 1:
        checks.append(("PASS", "Multiple models used — weight routing is active"))
    elif len(model_dist) == 1:
        checks.append(("WARN", f"Only 1 model used — check weights in config.yaml"))

    if total_ok > 0:
        top_server_pct = 100 * max(server_dist.values()) / total_ok
        if top_server_pct < 80:
            checks.append(("PASS", f"Top server handled {top_server_pct:.1f}% — traffic is spread"))
        else:
            checks.append(("WARN", f"Top server handled {top_server_pct:.1f}% — distribution is skewed"))

    if failures == 0:
        checks.append(("PASS", "Zero request failures"))
    else:
        checks.append(("FAIL", f"{failures} requests failed"))

    print(f"\n  Checks")
    print(f"  {'─' * 55}")
    for verdict, message in checks:
        print(f"  [{verdict:<4}]  {message}")

    failed = any(v == "FAIL" for v, _ in checks)
    overall = "FAILED" if failed else "PASSED"
    print(f"\n  {overall}\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run(parse_args()))
