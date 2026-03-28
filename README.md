# Smart LLM Gateway

A production-grade AI inference router that sits in front of multiple [Ollama](https://ollama.com) nodes.
It handles load balancing, circuit breaking, self-healing, and adaptive traffic shifting — all driven by a single config file.

---

## Table of Contents

- [For Beginners — Just Make It Work](#for-beginners--just-make-it-work)
- [How It Works (Plain English)](#how-it-works-plain-english)
- [Configuration Reference](#configuration-reference)
- [API Reference](#api-reference)
- [For Architects — Deep Dive](#for-architects--deep-dive)
  - [System Architecture](#system-architecture)
  - [Load Balancing Algorithms](#load-balancing-algorithms)
  - [Circuit Breaker](#circuit-breaker)
  - [Self-Healing System](#self-healing-system)
  - [Adaptive Weight Adjustment](#adaptive-weight-adjustment)
  - [Observability](#observability)
  - [Request Lifecycle](#request-lifecycle)
- [Operations Runbook](#operations-runbook)

---

## For Beginners — Just Make It Work

### Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) installed and running
- Python 3.8+ (`python3 --version`)
- `make` (pre-installed on macOS/Linux)

### Step 1 — Clone the repo

```bash
git clone https://github.com/supersaiyane/smart_llm_gateway.git
cd smart_llm_gateway
```

### Step 2 — Tell it which models you want

Open `config.yaml` (the **only** file you need to touch):

```yaml
models:
  - name: phi3:mini    # model name exactly as Ollama knows it
    replicas: 2        # how many containers to run for this model
    weight: 0.7        # 70% of traffic goes here
    fallback: llama3.2 # if this model fails, use llama3.2 instead

  - name: llama3.2
    replicas: 5
    weight: 0.3
```

Want only one model? Remove the other entry. Want more replicas? Change the number. That is it.

### Step 3 — Start everything

```bash
make up
```

This single command:
1. Reads your `config.yaml`
2. Generates the full Docker Compose infrastructure
3. Starts all containers (Ollama nodes, Redis, Nginx, Gateway, Controller, Prometheus)
4. The controller automatically pulls your models onto the right nodes

First run takes a few minutes while models download. Watch progress:

```bash
make logs-controller
```

### Step 4 — Send a request

```bash
curl -X POST http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Explain quantum computing in one sentence."}'
```

Response:

```json
{
  "response": "Quantum computing uses quantum bits...",
  "model_used": "phi3:mini",
  "served_by": "http://ollama1:11434"
}
```

### Step 5 — Check system health

```bash
make status    # full system snapshot
make nodes     # per-node details
```

### Quick-reference commands

| Command | What it does |
|---|---|
| `make up` | Start everything |
| `make down` | Stop everything |
| `make restart` | Stop then start |
| `make logs` | Stream all logs |
| `make logs-gateway` | Gateway logs only |
| `make status` | Routing weights and node health |
| `make nodes` | Per-node stats |
| `make reload` | Reload config.yaml without restart |
| `make test-lb` | Run load balancing test |
| `make clean` | Full reset — removes volumes |

---

## How It Works (Plain English)

Imagine you have 7 servers, each running an AI model. You do not want to manually decide which server handles each request — that is what this gateway does automatically.

**When a request comes in:**
1. The gateway decides which model to use based on weights (e.g. 70% chance of phi3:mini)
2. It looks up which servers are running that model
3. It picks the best server right now — fewest busy requests, lowest latency, no recent failures
4. If that server is broken, it tries the next one
5. If all servers for that model are broken, it tries the fallback model
6. Meanwhile, a background process watches every server and fixes broken ones automatically

**Self-healing means:**
- Server goes down? The healer notices, keeps probing, and reconnects it when it comes back
- Model got erased from a node? The controller re-pulls it automatically
- Server is responding slowly? Traffic is automatically shifted away from it

You do not need to do anything. It fixes itself.

---

## Configuration Reference

```yaml
# config.yaml — full reference with defaults

gateway:
  host: "0.0.0.0"
  port: 8081
  max_concurrent: 20      # max requests in-flight (queue beyond this)
  request_timeout: 30     # seconds — 504 if exceeded
  queue_size: 100         # max queued before 503 is returned

models:
  - name: phi3:mini       # Ollama model tag
    replicas: 2           # number of dedicated Ollama containers
    weight: 0.7           # fraction of traffic (weights should sum ~1.0)
    fallback: llama3.2    # try this if all replicas fail (optional)

load_balancing:
  algorithm: adaptive     # round_robin | least_connections | weighted_latency | adaptive

circuit_breaker:
  failure_threshold: 3    # failures before a node is marked down
  timeout: 30             # seconds before a down node gets a retry probe

self_healing:
  reconcile_interval: 20  # seconds between healer runs
  auto_restart: true      # restart crashed containers via Docker socket
  adaptive_weights: true  # auto-reduce weight for slow models
  weight_adjust_step: 0.05
  weight_min: 0.05        # floor — never completely starve a model
  max_parallel_pulls: 2
  pull_retries: 5

monitoring:
  prometheus_enabled: true
  health_check_interval: 10

redis:
  host: redis
  port: 6379
```

**Add a model:** add an entry, run `make rebuild`.
**Change weights:** edit and run `make reload` (no downtime).
**Scale replicas:** change the number and run `make rebuild`.

---

## API Reference

All endpoints available on port **8080** (via Nginx) and **8081** (direct to gateway).

### `POST /generate`

**Request**
```json
{ "prompt": "Your prompt here" }
```

**Response — success**
```json
{
  "response": "...",
  "model_used": "phi3:mini",
  "served_by": "http://ollama1:11434"
}
```

**Response — fallback triggered**
```json
{
  "response": "...",
  "model_used": "llama3.2",
  "served_by": "http://ollama3:11434",
  "fallback": true,
  "original_model": "phi3:mini"
}
```

**Error codes**

| Status | Meaning |
|---|---|
| `400` | Missing or empty prompt |
| `503` | System overloaded — retry after 5s |
| `504` | Request timed out |

---

### `GET /health`
Liveness check. Returns `{"status": "ok"}`.

---

### `GET /status`
Full system snapshot — weights, node states, circuit states, settings.

---

### `GET /nodes`
Raw per-node Redis state. Useful for debugging routing decisions.

---

### `GET /metrics`
Prometheus scrape endpoint.

| Metric | Type | Description |
|---|---|---|
| `gateway_requests_total` | Counter | Requests by model, server, status |
| `gateway_request_latency_seconds` | Histogram | Latency distribution |
| `gateway_fallbacks_total` | Counter | Fallback activations |
| `gateway_circuit_opens_total` | Counter | Circuit breaker trips |
| `gateway_active_requests` | Gauge | In-flight request count |
| `gateway_model_weight` | Gauge | Current adaptive routing weight |
| `gateway_node_failures` | Gauge | Current failure count per node |
| `gateway_node_latency_seconds` | Gauge | Last observed latency per node |

---

### `POST /config/reload`
Hot-reload `config.yaml` without restart. Weights and algorithm take effect immediately.

---

## For Architects — Deep Dive

### System Architecture

```
                ┌──────────────────────────────────────────┐
                │  Client                                  │
                └────────────────┬─────────────────────────┘
                                 │ :8080
                ┌────────────────▼─────────────────────────┐
                │  Nginx                                   │
                │  proxy_pass → gateway:8081               │
                │  proxy_next_upstream on 5xx              │
                └────────────────┬─────────────────────────┘
                                 │ :8081
  ┌──────────────────────────────▼──────────────────────────────────────────┐
  │  FastAPI Gateway                                                         │
  │                                                                          │
  │  asyncio.Semaphore (concurrency cap)                                     │
  │       │                                                                  │
  │  _choose_model()  ← adaptive weights from Redis                         │
  │       │                                                                  │
  │  _get_model_servers()  ← model:X key from Redis (set by controller)     │
  │       │                                                                  │
  │  rank_servers()   ← router.py  (4 algorithms)                           │
  │       │                                                                  │
  │  CircuitBreaker.is_available()  per node                                │
  │       │                                                                  │
  │  _http_generate()  [thread-pool executor]                                │
  │       │  HINCRBY active_connections ±1 atomically                        │
  │       │  POST /api/generate → Ollama                                     │
  │       │  record latency in Redis                                         │
  │       │                                                                  │
  │  fallback chain if all replicas fail                                     │
  │                                                                          │
  │  Background daemons:                                                     │
  │    health.py  — probes /api/tags every 10s                               │
  │    healer.py  — recovers circuits, adjusts weights every 20s             │
  │                                                                          │
  │  Admin API: /health /status /nodes /metrics /config/reload              │
  └──────────────────────────────────────┬──────────────────────────────────┘
                                         │
               ┌─────────────────────────▼──────────────────────────┐
               │  Redis                                              │
               │  model:phi3:mini  → "ollama1,ollama2"              │
               │  model:llama3.2   → "ollama3,...,ollama7"          │
               │  server:http://ollamaX:11434 → {latency,fails,...} │
               │  model_weights    → {phi3:mini: 0.65, ...}         │
               │  rr:counter       → int (round-robin state)        │
               └─────────────────────────┬──────────────────────────┘
                                         │
          ┌──────────────────────────────▼──────────────────────────┐
          │  Controller (separate container)                         │
          │  1. wait for all Ollama nodes                            │
          │  2. pull models in parallel (bounded by MAX_PARALLEL)    │
          │  3. write model→node assignments to Redis                │
          │  4. reconciliation loop every 20s:                       │
          │       missing model → re-pull                            │
          │       down node    → Docker API restart                  │
          └────────────┬────────────────────────────────────────────┘
                       │ Docker socket  +  direct HTTP
         ┌─────────────┼─────────────────────┐
         │             │                     │
  ┌──────▼──────┐ ┌────▼───────┐     ┌──────▼──────┐
  │  ollama1    │ │  ollama2   │ ... │  ollama7    │
  │  phi3:mini  │ │  phi3:mini │     │  llama3.2   │
  └─────────────┘ └────────────┘     └─────────────┘

  Prometheus (:9090) scrapes /metrics every 15s
```

---

### Load Balancing Algorithms

All algorithms live in `gateway/router.py`.

**`round_robin`**
Maintains a Redis counter (`rr:counter`) and rotates the server list from that offset. Zero per-request overhead. Best for homogeneous nodes with predictable request duration.

**`least_connections`**
Sorts by `active_connections` per server (tracked atomically in Redis). The gateway does `HINCRBY active_connections +1` before the Ollama call and `-1` in a `finally` block. This is the correct general-purpose algorithm when request duration varies widely.

**`weighted_latency`**
Sorts by `latency + (failures × 0.5)`. Latency is the round-trip time of the last successful call. Favours nodes with recent low latency. Good for heterogeneous hardware.

**`adaptive`** (default)
```
score = latency
      + failures × 0.5
      + active_connections × 0.2
      + 3.0  (if failed within last 20s)
      + jitter(0, 0.05)   ← prevents thundering herd
```
Lowest score wins. Combines health history, current load, and recency. Most resilient option.

---

### Circuit Breaker

`gateway/circuit.py` — per-server, Redis-backed.

```
            threshold failures
  CLOSED ────────────────────► OPEN
                                │
                        timeout │ elapses
                                ▼
                           HALF-OPEN ──── probe OK ──► CLOSED
                                │
                                └──── probe fails ────► OPEN
```

State is stored in Redis so multiple gateway instances (horizontal scaling) share the same view. `record_success()` and `record_failure()` use Redis pipelines to keep writes atomic.

---

### Self-Healing System

Three independent components work together:

**Health Checker** (`gateway/health.py`)
Daemon thread. Calls `GET /api/tags` on every node every `health_check_interval` seconds. On success: reset failures, close circuit. On failure: increment failure counter.

**Self-Healer** (`gateway/healer.py`)
Daemon thread. Every `reconcile_interval` seconds:
- Circuit recovery: probes every OPEN-circuit node. Closes circuit when node responds.
- Adaptive weights: reads per-node latency from Redis, shifts model weights.

**Controller** (`controller/controller.py`)
Separate container with Docker socket access. Bootstraps the cluster and then reconciles continuously:
- Missing model on a live node → pull it
- Node not responding → restart its container via Docker API
- After repairs → re-register assignments in Redis

---

### Adaptive Weight Adjustment

```
Every reconcile_interval seconds:

  for each model M:
    avg_latency(M) = mean(latency of all M replicas from Redis)

  global_avg = mean of all model avg_latencies

  if avg_latency(M) > global_avg × 1.5:
    weight(M) = max(weight_min, weight(M) - weight_adjust_step)

  if avg_latency(M) < global_avg × 0.8 AND weight(M) < config_baseline:
    weight(M) = min(config_baseline, weight(M) + weight_adjust_step)
```

The gateway reads from Redis first on every request; config baseline is the fallback when no Redis value exists. Weights never drop below `weight_min` (no model is completely starved).

---

### Observability

**Metrics** at `GET /metrics` (Prometheus format):

- `gateway_requests_total{model, server, status}` — request rate and error rate by model and node
- `gateway_request_latency_seconds{model, server}` — p50/p95/p99 per model/node
- `gateway_fallbacks_total{original_model, fallback_model}` — fallback activation rate
- `gateway_circuit_opens_total{server}` — leading indicator of node instability
- `gateway_active_requests` — in-flight count vs `max_concurrent`
- `gateway_model_weight{model}` — live adaptive weight changes
- `gateway_node_failures{server}` — per-node failure counters
- `gateway_node_latency_seconds{server}` — per-node last observed latency

If `monitoring.prometheus_enabled: true`, a Prometheus container starts and scrapes the gateway every 15 seconds (port 9090).

**Structured log lines to watch:**

```
INFO  controller — [pull] ollama3 <- llama3.2 OK
WARN  health     — http://ollama2:11434 unhealthy (failures=3)
INFO  healer     — [healer] phi3:mini slow (2.4s vs avg 0.8s) → weight 0.700 → 0.650
INFO  healer     — [healer] http://ollama2:11434 recovered — circuit closed
WARN  gateway    — All phi3:mini replicas failed — trying fallback 'llama3.2'
```

---

### Request Lifecycle

```
POST /generate
  │
  ├─ Nginx :8080 → gateway :8081
  │
  ├─ validate prompt (400 if empty)
  │
  ├─ asyncio.Semaphore.acquire()
  │     wait up to request_timeout → 503 if no slot
  │
  ├─ _choose_model()
  │     read adaptive weights from Redis
  │     random.choices() by weight
  │
  ├─ _get_model_servers(model)
  │     read Redis: model:<name> → "ollama1,ollama2"
  │
  ├─ rank_servers() [executor]
  │     run chosen algorithm
  │     return servers best-first
  │
  ├─ for each server:
  │     CircuitBreaker.is_available()? skip if OPEN
  │     _http_generate() [executor]
  │       HINCRBY active_connections +1
  │       POST /api/generate to Ollama
  │       record latency
  │       HINCRBY active_connections -1
  │     success → record_success(), emit metrics, return
  │     failure → record_failure(), try next server
  │
  ├─ all servers failed → cascade to fallback model
  │     repeat server loop for fallback
  │
  ├─ fallback also failed → {"error": "all backends failed"}
  │
  └─ Semaphore.release(), active_requests gauge decrement
```

---

## Operations Runbook

### Adding a new model
1. Add entry to `config.yaml`
2. Run `make rebuild`
3. Controller pulls the model automatically

### Changing traffic weights (no downtime)
1. Edit `weight:` values in `config.yaml`
2. Run `make reload`

### Scaling replicas
1. Change `replicas:` in `config.yaml`
2. Run `make rebuild`

### Force-reset a circuit breaker
```bash
docker exec -it $(docker ps -qf name=gateway) \
  redis-cli -h redis hset server:http://ollama2:11434 circuit_open 0 failures 0
```

### Watch adaptive weights in real time
```bash
watch -n 5 'curl -s http://localhost:8081/status | python3 -m json.tool'
```

### Disable adaptive weights temporarily
```yaml
# config.yaml
self_healing:
  adaptive_weights: false
```
Then `make reload`.

### Full reset
```bash
make clean   # removes all containers and volumes
make up      # fresh start
```
