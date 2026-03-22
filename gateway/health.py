import time
import requests

def health_check_loop(r, servers):
    while True:
        for server in servers:
            key = f"server:{server}"

            try:
                # 🔍 lightweight health check
                res = requests.get(f"{server}/api/tags", timeout=2)

                if res.status_code == 200:
                    # ✅ healthy → reset failures
                    r.hset(key, "failures", 0)
                    r.hset(key, "circuit_open", 0)

                else:
                    raise Exception("bad response")

            except Exception:
                # ❌ failure → increment
                failures = int(r.hget(key, "failures") or 0) + 1
                r.hset(key, "failures", failures)
                r.hset(key, "last_failure", time.time())

        # ⏳ run every 10 sec
        time.sleep(10)