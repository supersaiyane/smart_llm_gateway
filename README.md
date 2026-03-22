# 🚀 Smart LLM Gateway

Smart LLM Gateway is a **production-style, policy-driven AI inference
platform** that demonstrates how modern distributed systems can
intelligently route traffic across multiple Large Language Models (LLMs)
while maintaining **performance, reliability, and cost efficiency**.

This system is not just an API wrapper --- it is a **mini control plane
for AI workloads**, implementing core principles from:

-   Site Reliability Engineering (SRE)
-   Distributed Systems Design
-   Platform Engineering
-   AI Infrastructure (LLMOps)

## 🧠 Problem Statement

Modern AI systems face a fundamental challenge:

> How do we efficiently route requests across multiple models and nodes\
> while balancing: - Cost 💰\
> - Latency ⚡\
> - Reliability 🔁\
> - Throughput 📈

Naively sending all traffic to a single model or node results in: -
Resource exhaustion\
- Increased latency\
- Single points of failure\
- Poor scalability

------------------------------------------------------------------------

### ⚠️ Extended Problem: Multi-Model Infrastructure Alignment

As AI platforms evolve, a deeper challenge emerges:

> How do we dynamically align **model-level traffic distribution** with\
> **infrastructure provisioning (containers/pods)**?

In most systems: - Model selection (control plane) is **decoupled** from
infrastructure (data plane) - Scaling decisions are often **manual or
reactive** - Traffic distribution does **not reflect actual compute
allocation**

This leads to: - Overloaded nodes for popular models\
- Underutilized resources for less-used models\
- Inefficient cost utilization\
- Inconsistent performance under varying workloads

------------------------------------------------------------------------

### 🎯 Required Capability

A modern AI platform must:

-   Support **multi-model configurability**
-   Allow defining **traffic distribution ratios per model**
-   Automatically translate these ratios into:
    -   Container / pod provisioning
    -   Model-specific node allocation
-   Ensure **routing logic and infrastructure stay in sync**

------------------------------------------------------------------------

## 🚀 Solution Extension: Config-Driven Multi-Model Orchestration

This system introduces a **config-driven control plane** that unifies:

### 1. Model Distribution Policy

``` python
MODEL_WEIGHTS = {
    "phi3:mini": 0.7,
    "llama3.2": 0.3
}
```

Defines how traffic is split across models.

------------------------------------------------------------------------

### 2. Infrastructure Provisioning Policy

``` python
MODEL_REPLICAS = {
    "phi3:mini": 1,
    "llama3.2": 2
}
```

Defines how many containers/pods should run per model.

------------------------------------------------------------------------

### 3. Automated Infra Generation

Using a generator:

    config.py → generate_compose.py → docker-compose.generated.yml

-   Containers are created dynamically
-   Each node is preloaded with the correct model
-   Naming and indexing are deterministic (`ollama1`, `ollama2`, ...)

------------------------------------------------------------------------

### 4. Control Plane ↔ Data Plane Synchronization

-   `MODEL_REPLICAS` → defines infrastructure\
-   `MODEL_WEIGHTS` → defines traffic\
-   Gateway → enforces routing

This ensures: - Traffic aligns with compute capacity\
- No model is over/under-provisioned\
- System behaves predictably under load

# 🚀 Controller & Generator — Feature Guide

---

# 🧠 Overview

- Controller (Control Plane)
- Generator (Infra Provisioning)
- Configurable Flags
- How to Use
- Behavior & Tuning

---

# ⚙️ 1. Infrastructure Generator

## 🎯 Purpose
Automatically converts model requirements into running infrastructure.

---

## 🧠 What It Does

- Reads MODEL_REPLICAS
- Creates containers
- Assigns ports
- Generates init commands
- Produces docker-compose.generated.yml

---

## 📦 Example Input

MODEL_REPLICAS = {
  "phi3:mini": 2,
  "llama3.2": 1
}

---

## ⚡ Output

- 3 containers
- Model-specific pulls
- Persistent volumes

---

## 🚀 How to Use

make generate

Then:

make up

---

## 💥 Key Benefits

- No manual infra setup
- Deterministic deployments
- Scalable instantly

---

# ⚙️ 2. Controller (Control Plane)

## 🎯 Purpose

Ensures:
Desired State == Actual State

---

## 🔁 Core Loop

Every cycle:

1. Read MODEL_REPLICAS
2. Check nodes
3. Assign models
4. Store in Redis
5. Install if missing

---

## 🧠 Features

### 🔥 Replica-Aware Scheduling
phi3 → ollama1,ollama2

---

### 🔥 Redis State Management
model:phi3 → ollama1,ollama2

---

### 🔥 Intelligent Node Selection
Based on CPU and Memory

---

### 🔥 Parallel Model Pulls
Controlled via MAX_PARALLEL_PULLS

---

### 🔥 Self-Healing
- Detects missing models
- Reinstalls automatically

---

# 🎛️ Controller Flags

## 1. MODEL_REPLICAS
Defines architecture

## 2. OLLAMA_NODES
Defines available nodes

## 3. MAX_PARALLEL_PULLS
Controls concurrency

## 4. REDIS_HOST
Defines Redis backend

---

# ⚙️ Behavior Summary

MODEL_REPLICAS → scaling  
OLLAMA_NODES → infra  
MAX_PARALLEL_PULLS → performance  
REDIS_HOST → state  

---

# 🚀 How Controller Works (Flow)

Start → Read Config → Score Nodes → Assign → Update Redis → Install Models

---

# 🧪 Validation Commands

## Check Redis
docker exec -it smart-redis redis-cli GET model:phi3:mini

## Test Gateway
curl http://localhost:8080/generate -H "Content-Type: application/json" -d '{"prompt":"hello"}'

---

# 💥 System Behavior

## Node failure
Controller skips node

## Missing model
Controller installs automatically

## High load
Gateway distributes across replicas

---

# 🧠 Design Principles

- Declarative config
- Idempotency
- Self-healing
- Distributed control

---

# 🧪 Testing & Validation Guide

## 🎯 Purpose

This document provides a **comprehensive testing strategy** for
validating the Smart LLM Gateway system across:

-   Functional correctness
-   Load balancing behavior
-   Model routing accuracy
-   Failure handling
-   Resilience & recovery
-   Performance under load

This is written from an **architect/SRE perspective**, focusing not just
on *what to test*, but *why it matters*.

------------------------------------------------------------------------

# 🧠 Testing Philosophy

Modern distributed systems must be validated across:

  Layer           What to Validate
  --------------- ------------------------------
  Control Plane   Config → routing correctness
  Data Plane      Model serving correctness
  Resilience      Failure + recovery
  Performance     Latency, throughput
  Stability       Behavior under pressure

------------------------------------------------------------------------

# ✅ 1. INFRA VALIDATION

## Command

``` bash
docker ps
```

## Expected

-   smart-gateway
-   smart-nginx
-   smart-redis
-   ollama1..N

------------------------------------------------------------------------

# ✅ 2. MODEL DISTRIBUTION VALIDATION

``` bash
for i in 1 2 3; do
  docker exec -it ollama$i ollama list
done
```

Expected mapping must match MODEL_REPLICAS.

------------------------------------------------------------------------

# ✅ 3. BASIC API TEST

``` bash
curl http://localhost:8080/generate \
-H "Content-Type: application/json" \
-d '{"prompt": "hello"}'
```

Expected: - model_used present - served_by present

------------------------------------------------------------------------

# ✅ 4. MODEL DISTRIBUTION TEST

``` bash
for i in {1..40}; do
  curl -s http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "hello"}' | jq -r '.model_used'
done | sort | uniq -c
```

Validates weight-based routing.

------------------------------------------------------------------------

# ✅ 5. NODE LOAD BALANCING TEST

``` bash
for i in {1..40}; do
  curl -s http://localhost:8080/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "hello"}' | jq -r '.served_by'
done | sort | uniq -c
```

Validates load distribution across nodes.

------------------------------------------------------------------------

# ✅ 6. CONCURRENCY TEST

``` bash
python3 test_gateway.py
```

Check: - success rate - latency - distribution

------------------------------------------------------------------------

# ✅ 7. OVERLOAD TEST

Increase concurrency beyond limit.

Expected: - controlled rejection - system stability

------------------------------------------------------------------------

# ✅ 8. FAILURE TEST

``` bash
docker stop ollama2
```

Expected: - no traffic to failed node - system continues

------------------------------------------------------------------------

# ✅ 9. RECOVERY TEST

``` bash
docker start ollama2
```

Expected: - node reintroduced automatically

------------------------------------------------------------------------

# ✅ 10. RESOURCE TEST

``` bash
docker stats
```

Expected: - all nodes active

------------------------------------------------------------------------

# 🚀 FINAL CHECK

If all above pass:

You have: - Resilient routing - Load balancing - Failure handling -
Backpressure control

------------------------------------------------------------------------

