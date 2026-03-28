#!/usr/bin/env python3
"""
Gateway smoke test — validates every endpoint is reachable and returns
expected data.

Usage:
    python3 test-scripts/test_health.py [--url http://localhost:8080]

Exit codes:
    0  All critical checks passed
    1  One or more critical checks failed
"""

import argparse
import sys

import requests


def parse_args():
    p = argparse.ArgumentParser(description="Gateway endpoint smoke test")
    p.add_argument("--url", default="http://localhost:8080",
                   help="Base URL of the gateway (via nginx, default port 8080)")
    p.add_argument("--timeout", type=int, default=10)
    return p.parse_args()


def check(label: str, fn) -> tuple:
    """Run fn(), return (label, passed, note)."""
    try:
        passed, note = fn()
        return label, passed, note
    except requests.exceptions.ConnectionError:
        return label, False, "connection refused — is the gateway running?"
    except requests.exceptions.Timeout:
        return label, False, "request timed out"
    except Exception as exc:
        return label, False, str(exc)


def run(args) -> int:
    base = args.url.rstrip("/")
    t = args.timeout

    print(f"\n  Gateway Smoke Test")
    print(f"  {'─' * 60}")
    print(f"  Base URL : {base}")
    print()

    suite = [
        (
            "GET /health",
            lambda: (
                (res := requests.get(f"{base}/health", timeout=t))
                and res.status_code == 200
                and res.json().get("status") == "ok",
                f"HTTP {res.status_code}"
            ),
        ),
        (
            "GET /status",
            lambda: (
                (res := requests.get(f"{base}/status", timeout=t))
                and res.status_code == 200
                and "nodes" in res.json(),
                f"HTTP {res.status_code} — keys: {list(res.json().keys()) if res.status_code == 200 else 'n/a'}"
            ),
        ),
        (
            "GET /nodes",
            lambda: (
                (res := requests.get(f"{base}/nodes", timeout=t))
                and res.status_code == 200,
                f"HTTP {res.status_code} — {len(res.json())} nodes" if res.status_code == 200 else f"HTTP {res.status_code}"
            ),
        ),
        (
            "GET /metrics",
            lambda: (
                (res := requests.get(f"{base}/metrics", timeout=t))
                and res.status_code == 200
                and "gateway_requests_total" in res.text,
                f"HTTP {res.status_code} — prometheus format {'OK' if res.status_code == 200 else 'missing'}"
            ),
        ),
        (
            "POST /generate (basic)",
            lambda: (
                (res := requests.post(
                    f"{base}/generate",
                    json={"prompt": "Reply with the single word: hello"},
                    timeout=120,
                ))
                and res.status_code == 200
                and "model_used" in res.json(),
                f"HTTP {res.status_code}"
                + (f" — model={res.json().get('model_used')} server={res.json().get('served_by')}"
                   if res.status_code == 200 else "")
            ),
        ),
        (
            "POST /generate (empty prompt → 400)",
            lambda: (
                (res := requests.post(f"{base}/generate", json={"prompt": ""}, timeout=t))
                and res.status_code == 400,
                f"HTTP {res.status_code} (expected 400)"
            ),
        ),
        (
            "POST /config/reload",
            lambda: (
                (res := requests.post(f"{base}/config/reload", timeout=t))
                and res.status_code == 200
                and "models" in res.json(),
                f"HTTP {res.status_code}"
            ),
        ),
    ]

    results = []
    for label, fn in suite:
        label, passed, note = check(label, fn)
        results.append((label, passed, note))
        mark = "PASS" if passed else "FAIL"
        print(f"  [{mark}]  {label:<35}  {note}")

    failed = [r for r in results if not r[1]]
    passed_count = len(results) - len(failed)

    print(f"\n  {'─' * 60}")
    print(f"  {passed_count}/{len(results)} checks passed")

    if failed:
        print(f"\n  Failed checks:")
        for label, _, note in failed:
            print(f"    - {label}: {note}")

    overall = "PASSED" if not failed else "FAILED"
    print(f"\n  {overall}\n")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(run(parse_args()))
