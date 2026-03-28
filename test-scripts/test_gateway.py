#!/usr/bin/env python3
"""
Concurrent load test for the Smart LLM Gateway.

Usage:
    python3 test-scripts/test_gateway.py [options]

Options:
    --url         Gateway URL          (default: http://localhost:8080/generate)
    --requests    Total requests       (default: 20)
    --concurrency Parallel workers     (default: 5)
    --timeout     Per-request timeout  (default: 60)
    --prompt      Prompt to send       (default: "What is 2+2?")
    --fail-rate   Max allowed failure % before exit 1 (default: 10)

Exit codes:
    0  All good (failure rate within --fail-rate threshold)
    1  Failure rate exceeded threshold or gateway unreachable
"""

import argparse
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


def parse_args():
    p = argparse.ArgumentParser(description="Concurrent gateway load test")
    p.add_argument("--url",         default="http://localhost:8080/generate")
    p.add_argument("--requests",    type=int,   default=20,    dest="total")
    p.add_argument("--concurrency", type=int,   default=5)
    p.add_argument("--timeout",     type=int,   default=60)
    p.add_argument("--prompt",      default="What is 2+2? Answer in one word.")
    p.add_argument("--fail-rate",   type=float, default=10.0,  dest="fail_rate",
                   help="Max allowed failure percentage (default 10)")
    return p.parse_args()


def send_request(idx: int, url: str, prompt: str, timeout: int) -> dict:
    t0 = time.time()
    try:
        res = requests.post(url, json={"prompt": prompt}, timeout=timeout)
        latency = time.time() - t0
        if res.status_code == 200:
            data = res.json()
            return {
                "id": idx,
                "status": "success",
                "server": data.get("served_by", "unknown"),
                "model": data.get("model_used", "unknown"),
                "fallback": data.get("fallback", False),
                "latency": latency,
            }
        return {"id": idx, "status": f"http_{res.status_code}", "server": "none",
                "model": "none", "fallback": False, "latency": latency}
    except requests.exceptions.ConnectionError:
        return {"id": idx, "status": "connection_error", "server": "none",
                "model": "none", "fallback": False, "latency": time.time() - t0}
    except requests.exceptions.Timeout:
        return {"id": idx, "status": "timeout", "server": "none",
                "model": "none", "fallback": False, "latency": timeout}
    except Exception as exc:
        return {"id": idx, "status": f"error:{exc}", "server": "none",
                "model": "none", "fallback": False, "latency": 0}


def percentile(data: list, pct: float) -> float:
    if not data:
        return 0.0
    s = sorted(data)
    idx = int(len(s) * pct / 100)
    return s[min(idx, len(s) - 1)]


def bar(count: int, total: int, width: int = 30) -> str:
    filled = int(width * count / total) if total else 0
    return f"[{'#' * filled}{'-' * (width - filled)}] {count:3d} ({100*count/total:.1f}%)"


def run(args) -> int:
    print(f"\n  Gateway Load Test")
    print(f"  {'─' * 50}")
    print(f"  URL         : {args.url}")
    print(f"  Requests    : {args.total}")
    print(f"  Concurrency : {args.concurrency}")
    print(f"  Timeout     : {args.timeout}s")
    print(f"  Prompt      : {args.prompt[:60]}")
    print()

    results = []
    t_start = time.time()

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(send_request, i, args.url, args.prompt, args.timeout): i
            for i in range(1, args.total + 1)
        }
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            status_mark = "OK" if r["status"] == "success" else "FAIL"
            print(f"  [{r['id']:>3}] {status_mark:<4}  {r['server']:<35}  {r['latency']:.2f}s")

    wall_time = time.time() - t_start

    success  = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] != "success"]
    fallbacks = [r for r in success if r["fallback"]]
    latencies = [r["latency"] for r in success]

    server_dist = Counter(r["server"] for r in success)
    model_dist  = Counter(r["model"]  for r in success)

    fail_pct = 100 * len(failures) / len(results) if results else 100

    print(f"\n  Results")
    print(f"  {'─' * 50}")
    print(f"  Total        : {len(results)}")
    print(f"  Success      : {len(success)}")
    print(f"  Failures     : {len(failures)}")
    print(f"  Fallbacks    : {len(fallbacks)}")
    print(f"  Failure rate : {fail_pct:.1f}%")
    print(f"  Wall time    : {wall_time:.2f}s")
    print(f"  Throughput   : {len(results)/wall_time:.2f} req/s")

    if latencies:
        print(f"\n  Latency (successful requests)")
        print(f"  {'─' * 50}")
        print(f"  Min    : {min(latencies):.3f}s")
        print(f"  Avg    : {sum(latencies)/len(latencies):.3f}s")
        print(f"  p95    : {percentile(latencies, 95):.3f}s")
        print(f"  Max    : {max(latencies):.3f}s")

    if server_dist:
        print(f"\n  Server distribution")
        print(f"  {'─' * 50}")
        for server, count in sorted(server_dist.items(), key=lambda x: -x[1]):
            print(f"  {server:<35}  {bar(count, len(success))}")

    if model_dist:
        print(f"\n  Model distribution")
        print(f"  {'─' * 50}")
        for model, count in sorted(model_dist.items(), key=lambda x: -x[1]):
            print(f"  {model:<20}  {bar(count, len(success))}")

    if failures:
        print(f"\n  Failure breakdown")
        print(f"  {'─' * 50}")
        for status, count in Counter(r["status"] for r in failures).items():
            print(f"  {status:<30}  {count}")

    passed = fail_pct <= args.fail_rate
    verdict = "PASSED" if passed else "FAILED"
    print(f"\n  {verdict}  (failure rate {fail_pct:.1f}% {'<=' if passed else '>'} threshold {args.fail_rate}%)\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(run(parse_args()))
