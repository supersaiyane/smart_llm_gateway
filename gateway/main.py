from fastapi import FastAPI
import requests
import time
import redis
import random
import threading

from health import health_check_loop
from config import *
from circuit import is_available

app = FastAPI()

# Redis connection
r = redis.Redis(host=REDIS_HOST, port=6379, decode_responses=True)

from threading import Lock

MAX_CONCURRENT_REQUESTS = 5
REQUEST_TIMEOUT = 30

active_requests = 0
lock = Lock()


# -------------------------
# Weighted Model Selection
# -------------------------
def choose_model_by_weight():
    models = list(MODEL_WEIGHTS.keys())
    weights = list(MODEL_WEIGHTS.values())
    return random.choices(models, weights=weights, k=1)[0]


# -------------------------
# Redis-based Model Routing (UPDATED 🔥)
# -------------------------
def get_model_servers(model: str):
    """
    Fetch assigned node(s) from Redis
    Now supports MULTIPLE replicas
    """
    key = f"model:{model}"

    nodes = r.get(key)

    if not nodes:
        return []

    # 🔥 Split comma-separated nodes
    node_list = [n.strip() for n in nodes.split(",") if n.strip()]

    return [f"http://{n}:11434" for n in node_list]


# -------------------------
# Initialize server stats
# -------------------------
def init_servers():
    for s in OLLAMA_SERVERS:
        key = f"server:{s}"
        if not r.exists(key):
            r.hset(key, mapping={
                "latency": 0.5,
                "failures": 0,
                "circuit_open": 0,
                "last_failure": 0
            })


# -------------------------
# Core LLM Call Logic
# -------------------------
def call_llm(payload):

    prompt = payload["prompt"]

    # 🎯 Step 1: choose model
    model = choose_model_by_weight()

    # 🔥 Step 2: get ALL replica servers
    servers = get_model_servers(model)

    if not servers:
        return {
            "error": "model not assigned",
            "model": model
        }

    # 🔥 Step 3: Shuffle for load balancing
    random.shuffle(servers)

    # 🔁 Try all replicas
    for server in servers:

        if not is_available(r, server, CIRCUIT_TIMEOUT):
            continue

        key = f"server:{server}"
        start = time.time()

        try:
            res = requests.post(
                f"{server}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=25
            )

            latency = time.time() - start
            r.hset(key, "latency", latency)

            if res.status_code == 200:
                # 🧠 self-healing
                current_failures = int(r.hget(key, "failures") or 0)

                if current_failures > 0:
                    r.hset(key, "failures", current_failures - 1)

                r.hset(key, "circuit_open", 0)

                data = res.json()
                data["served_by"] = server
                data["model_used"] = model

                return data

            raise Exception("bad response")

        except Exception:
            r.hincrby(key, "failures", 1)
            r.hset(key, "last_failure", time.time())

            failures = int(r.hget(key, "failures"))

            if failures >= FAILURE_THRESHOLD:
                r.hset(key, "circuit_open", 1)

            time.sleep(random.uniform(0.1, 0.3))

    # -------------------------
    # 🔥 Fallback Logic
    # -------------------------
    fallback_model = "llama3.2"
    fallback_servers = get_model_servers(fallback_model)

    random.shuffle(fallback_servers)

    for server in fallback_servers:

        if not is_available(r, server, CIRCUIT_TIMEOUT):
            continue

        try:
            res = requests.post(
                f"{server}/api/generate",
                json={
                    "model": fallback_model,
                    "prompt": prompt,
                    "stream": False
                },
                timeout=25
            )

            if res.status_code == 200:
                data = res.json()
                data["served_by"] = server
                data["model_used"] = fallback_model
                data["fallback"] = True
                return data

        except Exception:
            time.sleep(random.uniform(0.1, 0.3))
            continue

    return {"error": "all backends failed"}


# -------------------------
# FastAPI Lifecycle
# -------------------------
@app.on_event("startup")
def startup():
    init_servers()

    threading.Thread(
        target=health_check_loop,
        args=(r, OLLAMA_SERVERS),
        daemon=True
    ).start()


# -------------------------
# API Endpoint
# -------------------------
@app.post("/generate")
def generate(payload: dict):
    global active_requests

    start_wait = time.time()

    while True:
        with lock:
            if active_requests < MAX_CONCURRENT_REQUESTS:
                active_requests += 1
                break

        if time.time() - start_wait > REQUEST_TIMEOUT:
            return {
                "error": "system overloaded",
                "message": "try again later"
            }

        time.sleep(0.05)

    try:
        return call_llm(payload)

    finally:
        with lock:
            active_requests -= 1