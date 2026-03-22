#!/bin/sh

echo "🔍 Checking models on all Ollama nodes..."
echo "----------------------------------------"

NODES=$(getent hosts | grep ollama | awk '{print $2}' | sort)

for node in $NODES; do
  echo ""
  echo "🧠 Node: $node"

  if ! curl -s --max-time 2 http://$node:11434 > /dev/null; then
    echo "❌ Node is DOWN"
    continue
  fi

  models=$(OLLAMA_HOST=http://$node:11434 ollama list 2>/dev/null)

  if [ -z "$models" ]; then
    echo "⚠️ No models found"
  else
    echo "$models"
  fi
done

echo ""
echo "✅ Model inspection complete"