#!/bin/sh
# =============================================================
#  Smart LLM Gateway — container entrypoint
#
#  Decision tree:
#    1. CONFIG_PATH is set AND the file exists and is non-empty
#       → use it as-is
#    2. /app/config.yaml exists and is non-empty (volume-mounted)
#       → use it as-is
#    3. Neither → generate config.yaml from environment variables
#       → requires at least GATEWAY_MODELS to be set
# =============================================================
set -e

RESOLVED_CONFIG="${CONFIG_PATH:-/app/config.yaml}"

if [ -s "$RESOLVED_CONFIG" ]; then
    echo "[entrypoint] Using config: $RESOLVED_CONFIG"
else
    echo "[entrypoint] No config.yaml found — generating from environment variables ..."
    python3 /app/generate_config.py "$RESOLVED_CONFIG"
    echo "[entrypoint] Config written to $RESOLVED_CONFIG"
fi

export CONFIG_PATH="$RESOLVED_CONFIG"

PORT="${GATEWAY_PORT:-8081}"
LOG_LEVEL="${LOG_LEVEL:-info}"

echo "[entrypoint] Starting gateway on port $PORT (log level: $LOG_LEVEL)"
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port "$PORT" \
    --log-level "$LOG_LEVEL"
