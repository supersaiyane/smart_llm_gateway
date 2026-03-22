import requests
from collections import Counter

URL = "http://localhost:8080/generate"
TOTAL_REQUESTS = 20

served_by_counter = Counter()
model_counter = Counter()
failures = 0

print("\n🚀 Sending Requests...\n")

for i in range(1, TOTAL_REQUESTS + 1):
    try:
        res = requests.post(
            URL,
            json={"prompt": f"hello {i}"},
            timeout=60
        )

        data = res.json()

        server = data.get("served_by", "unknown")
        model = data.get("model_used", "unknown")

        served_by_counter[server] += 1
        model_counter[model] += 1

        print(f"Request {i:02d} → {server} | model: {model}")

    except Exception as e:
        failures += 1
        print(f"Request {i:02d} → FAILED ({e})")

# -------------------------
# Summary
# -------------------------
print("\n📊 Node Distribution:")
for server, count in served_by_counter.items():
    print(f"{server} → {count}")

print("\n🧠 Model Distribution:")
for model, count in model_counter.items():
    print(f"{model} → {count}")

print(f"\n❌ Failures: {failures}")

# -------------------------
# Basic Health Check
# -------------------------
if len(served_by_counter) > 1:
    print("\n✅ Load balancing looks ACTIVE")
else:
    print("\n⚠️ Load balancing NOT working properly")

if failures == 0:
    print("✅ No request failures")
else:
    print("⚠️ Some requests failed")