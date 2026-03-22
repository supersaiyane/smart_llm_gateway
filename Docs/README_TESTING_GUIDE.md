# 🧪 Smart LLM Gateway -- Testing & Validation Guide (Architect Level)

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

🔥 This is **production-grade system validation**.
