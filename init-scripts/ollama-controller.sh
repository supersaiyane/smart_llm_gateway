#!/bin/sh

echo "🚀 Ollama Intelligent Controller Started..."

# -------------------------
# Config
# -------------------------
REDIS_HOST=${REDIS_HOST:-redis}
MAX_PARALLEL_PULLS=${MAX_PARALLEL_PULLS:-2}

# -------------------------
# Parallel Control
# -------------------------
wait_for_slot() {
  while [ "$(jobs -rp | wc -l)" -ge "$MAX_PARALLEL_PULLS" ]; do
    sleep 1
  done
}

# -------------------------
# Redis Helpers
# -------------------------
redis_get() {
  redis-cli -h "$REDIS_HOST" GET "$1"
}

redis_set() {
  redis-cli -h "$REDIS_HOST" SET "$1" "$2" >/dev/null
}

# -------------------------
# Validate Dependencies
# -------------------------
for cmd in jq curl ollama docker bc awk redis-cli; do
  if ! command -v $cmd >/dev/null 2>&1; then
    echo "❌ Missing dependency: $cmd"
    exit 1
  fi
done

# -------------------------
# Validate ENV
# -------------------------
if [ -z "$MODEL_REPLICAS" ]; then
  echo "❌ MODEL_REPLICAS not set"
  exit 1
fi

if [ -z "$OLLAMA_NODES" ]; then
  echo "❌ OLLAMA_NODES not set"
  exit 1
fi

echo "📦 MODEL CONFIG: $MODEL_REPLICAS"
echo "🔍 NODES: $OLLAMA_NODES"
echo "⚡ MAX_PARALLEL_PULLS: $MAX_PARALLEL_PULLS"
echo "🧠 REDIS_HOST: $REDIS_HOST"

echo "$MODEL_REPLICAS" | jq empty || {
  echo "❌ Invalid MODEL_REPLICAS JSON"
  exit 1
}

# -------------------------
# Build Model List
# -------------------------
MODEL_LIST=$(echo "$MODEL_REPLICAS" | jq -r '
  to_entries[] | .key as $model | .value | range(.) | $model
')

echo "🧠 Desired Models:"
echo "$MODEL_LIST"

# -------------------------
# Nodes
# -------------------------
NODES=$(echo "$OLLAMA_NODES" | tr ',' ' ')

# -------------------------
# Helper Functions
# -------------------------
is_service_up() {
  curl -s --max-time 2 http://$1:11434 >/dev/null 2>&1
}

model_exists() {
  host=$1
  model=$2
  OLLAMA_HOST=http://$host:11434 ollama list 2>/dev/null | awk '{print $1}' | grep -q "^$model$"
}

pull_model() {
  host=$1
  model=$2

  echo "📦 Pulling $model → $host"

  for i in 1 2 3 4 5; do
    echo "🔁 [$host] Attempt $i for $model"
    if OLLAMA_HOST=http://$host:11434 ollama pull "$model"; then
      echo "✅ SUCCESS: $model on $host"
      return 0
    fi
    sleep 3
  done

  echo "❌ FAILED: $model on $host"
  return 1
}

# -------------------------
# Node Scoring
# -------------------------
get_node_score() {
  node=$1

  stats=$(docker stats --no-stream --format "{{.Name}} {{.CPUPerc}} {{.MemUsage}}" | grep "^$node ")

  if [ -z "$stats" ]; then
    echo "0"
    return
  fi

  cpu=$(echo "$stats" | awk '{print $2}' | tr -d '%')
  mem=$(echo "$stats" | awk '{print $3}' | cut -d'/' -f1)
  mem=$(echo "$mem" | sed 's/MiB//;s/GiB/*1024/' | bc 2>/dev/null)

  cpu=${cpu:-100}
  mem=${mem:-9999}

  score=$(echo "100 - $cpu - ($mem / 20)" | bc 2>/dev/null)
  [ -z "$score" ] && score=0

  echo "$score"
}

assign_model_to_best_node() {
  best_node=""
  best_score=-9999

  for node in $NODES; do
    if ! is_service_up "$node"; then
      continue
    fi

    score=$(get_node_score "$node")
    echo "📊 $node score: $score" >&2

    better=$(awk "BEGIN {print ($score > $best_score)}")

    if [ "$better" -eq 1 ]; then
      best_score=$score
      best_node=$node
    fi
  done

  echo "$best_node"
}

# -------------------------
# Redis Replica Append Logic (NEW 🔥🔥🔥)
# -------------------------
add_node_to_model() {
  key=$1
  node=$2

  existing=$(redis_get "$key")

  if [ -z "$existing" ]; then
    redis_set "$key" "$node"
    echo "🆕 [$node] assigned as first replica"
  else
    echo "$existing" | grep -q "$node"

    if [ $? -eq 0 ]; then
      echo "✅ [$node] already part of replicas"
    else
      redis_set "$key" "$existing,$node"
      echo "➕ Added [$node] to replicas → $existing,$node"
    fi
  fi
}

# -------------------------
# Reconciliation Loop
# -------------------------
while true; do
  echo ""
  echo "🔁 ==============================="
  echo "🔁 Intelligent Reconciliation"
  echo "🔁 ==============================="

  for model in $MODEL_LIST; do

    key="model:$model"

    # Always assign based on replicas (no single-node lock anymore)
    node=$(assign_model_to_best_node)

    if [ -z "$node" ]; then
      echo "❌ No available node for $model"
      continue
    fi

    echo "🎯 Assign $model → $node"

    # Add node to replica list
    add_node_to_model "$key" "$node"

    # Ensure model exists
    if model_exists "$node" "$model"; then
      echo "✅ [$node] already has $model"
    else
      wait_for_slot
      pull_model "$node" "$model" &
    fi

  done

  wait

  echo "😴 Sleeping..."
  sleep 20
done