# 🚀 Docker Compose–Driven AI Model Orchestration (Focus: Compose Layer)

## 🧠 Overview

This README focuses specifically on the **Docker Compose architecture and generation strategy**, which is the **core strength of this system**.

We are not just writing a static `docker-compose.yml` — we are **programmatically generating and controlling a distributed system** using Docker Compose as the execution layer.

👉 This turns Docker Compose into a **mini orchestration engine**.

---

# 🏗️ What Makes This Special

Instead of:
```
Write docker-compose.yml manually ❌
```

We do:
```
config.py → generator → docker-compose.generated.yml → runtime control
```

👉 This is **dynamic infrastructure generation**, not static configuration.

---

# ⚙️ Core Idea

We define desired state in:
```python
MODEL_REPLICAS = {
  "phi3:mini": 2,
  "llama3.2": 1
}
```

Then automatically generate:
- Multiple Ollama containers
- Ports
- Volumes
- Dependencies
- Controller wiring

---

# 🔁 Docker Compose Generation Flow

```
gateway/config.py
        ↓
scripts/generate_compose.py
        ↓
docker-compose.generated.yml
        ↓
docker compose up
```

---

# 🧱 Generated Docker Compose Structure

The generated file contains:

## 1. Core Services

### 🔹 Gateway
- Entry point for all AI requests
- Depends on all Ollama nodes

### 🔹 Redis
- Future control plane / caching layer

### 🔹 NGINX
- Public-facing entrypoint

---

## 2. Dynamic Ollama Nodes (🔥 Key Part)

Generated automatically based on config:

```yaml
ollama1:
ollama2:
ollama3:
```

Each node includes:
- Dedicated port mapping
- Persistent volume
- Independent lifecycle

👉 This enables:
- Horizontal scaling
- Isolation per model instance

---

## 3. Controller (Most Important Layer)

```yaml
ollama-controller:
```

This is injected into Docker Compose and acts as:

👉 **Control Plane over Docker Compose**

Responsibilities:
- Reads `MODEL_REPLICAS` from ENV
- Discovers containers dynamically
- Ensures models are present
- Reconciles continuously

---

# 🔥 Key Compose Features Used

## ✅ Dynamic Service Creation

Instead of static YAML:

```yaml
ollama1:
ollama2:
```

We generate it via Python loops.

---

## ✅ Dynamic Port Allocation

```yaml
11434 → 11435 → 11436
```

Avoids collisions automatically.

---

## ✅ Volume Isolation

```yaml
ollama_data1
ollama_data2
```

Each container has independent model storage.

---

## ✅ Dependency Injection

```yaml
depends_on:
  - ollama1
  - ollama2
```

Auto-generated for:
- Gateway
- Controller

---

## ✅ Runtime Configuration Injection

```yaml
environment:
  MODEL_REPLICAS: '{"phi3:mini":2,"llama3.2":1}'
```

👉 This bridges:
- Build-time (Python)
- Runtime (Controller)

---

## ✅ Controller Bootstrapping

```yaml
entrypoint: >
  sh -c "
  apk add --no-cache jq curl &&
  /bin/sh /scripts/ollama-controller.sh
  "
```

👉 Ensures runtime dependencies exist dynamically.

---

# 🧠 Why This Design Matters

## Traditional Docker Compose

- Static
- One-time execution
- No recovery logic

## Your System

- Dynamic generation
- Continuous reconciliation
- Self-healing behavior

👉 This is closer to:
- Kubernetes
- Control-plane systems

---

# 🔁 Lifecycle (Compose-Centric)

## Start
```
make up
```

- Generates compose file
- Starts all containers
- Controller begins reconciliation

---

## Stop
```
make down
```

---

## Rebuild
```
make rebuild
```

---

## Inspect
```
make show
make ps
make logs
```

---

# 🔍 Validation via Compose

## Check Models
```
make models
```

## Test Load Balancing
```
make test-lb
```

---

# ⚠️ Design Trade-offs

## Pros
- Fully dynamic compose generation
- Easy scaling via config change
- No manual YAML edits
- Clean separation of concerns

## Cons
- Not event-driven (polling controller)
- No native scheduling intelligence
- Docker Compose limitations vs Kubernetes

---

# 🚀 Future Enhancements (Compose Layer)

- Dynamic scaling (regenerate + rolling restart)
- Multiple controllers (leader election)
- Healthchecks in compose
- Network segmentation

---

# 🧩 Key Takeaway

👉 Docker Compose here is not just a tool — it is:

> **The execution engine for a dynamically generated, self-healing AI platform**

---

# 🏁 Final Thought

This approach transforms Docker Compose from:

```
Static YAML runner ❌
```

into:

```
Programmable orchestration layer ✅
```

---

💡 *This is how you evolve from writing configs → designing systems.*

