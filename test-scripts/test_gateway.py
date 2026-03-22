import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter

URL = "http://localhost:8080/generate"

TOTAL_REQUESTS = 20
CONCURRENCY = 5


def call(i):
    start = time.time()

    try:
        res = requests.post(
            URL,
            json={"prompt": "hello"},
            timeout=60
        )

        latency = time.time() - start

        if res.status_code == 200:
            data = res.json()
            server = data.get("served_by", "unknown")

            return {
                "status": "success",
                "server": server,
                "latency": latency
            }

        return {"status": "error", "server": "none", "latency": latency}

    except Exception as e:
        return {"status": "fail", "server": "none", "latency": 0}


def run_test():
    print(f"\n🚀 Running test: {TOTAL_REQUESTS} requests | concurrency={CONCURRENCY}\n")

    results = []

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        futures = [executor.submit(call, i) for i in range(TOTAL_REQUESTS)]

        for future in as_completed(futures):
            results.append(future.result())

    analyze(results)


def analyze(results):
    success = [r for r in results if r["status"] == "success"]
    failures = [r for r in results if r["status"] != "success"]

    servers = [r["server"] for r in success]
    latency = [r["latency"] for r in success]

    print("📊 RESULTS\n")

    print(f"✅ Success: {len(success)}")
    print(f"❌ Failures: {len(failures)}")

    if latency:
        print(f"⏱ Avg Latency: {sum(latency)/len(latency):.2f}s")
        print(f"⚡ Min Latency: {min(latency):.2f}s")
        print(f"🐢 Max Latency: {max(latency):.2f}s")

    print("\n🧠 Load Distribution:\n")

    counter = Counter(servers)
    for server, count in counter.items():
        print(f"{server} → {count} requests")


if __name__ == "__main__":
    run_test()