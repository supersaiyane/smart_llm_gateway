import time
import random


def compute_score(latency, failures, last_failure):
    penalty = failures * 2

    recency_penalty = 0
    if time.time() - last_failure < 20:
        recency_penalty = 3

    return latency + penalty + recency_penalty

def get_best_server(r, servers):
    scored = []

    for s in servers:
        key = f"server:{s}"

        latency = float(r.hget(key, "latency") or 1)
        failures = int(r.hget(key, "failures") or 0)

        # 🔥 improved score
        score = latency + (failures * 2) + random.uniform(0, 0.2)

        scored.append((score, s))

    # sort by score (lowest best)
    scored.sort(key=lambda x: x[0])

    return [s for _, s in scored]