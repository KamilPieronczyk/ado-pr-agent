#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${ADO_AUTH_TOKEN:?ADO_AUTH_TOKEN is required. Export it before running this script.}"

WEBHOOK_USERNAME="${WEBHOOK_USERNAME:-test}"
WEBHOOK_PASSWORD="${WEBHOOK_PASSWORD:-testpass}"
LLM_PROVIDER="${LLM_PROVIDER:-copilot}"
PORT="${PORT:-8080}"
LOG_FILE="${LOG_FILE:-/tmp/webhook.log}"

# Kill any existing instance on the same port
EXISTING_PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [[ -n "$EXISTING_PID" ]]; then
  echo "Stopping existing process on port $PORT (PID $EXISTING_PID)..."
  kill "$EXISTING_PID"
  sleep 1
fi

echo "Starting webhook server (LLM=$LLM_PROVIDER, port=$PORT)..."
echo "Logs: $LOG_FILE"

ADO_AUTH_TOKEN="$ADO_AUTH_TOKEN" \
LLM_PROVIDER="$LLM_PROVIDER" \
WEBHOOK_USERNAME="$WEBHOOK_USERNAME" \
WEBHOOK_PASSWORD="$WEBHOOK_PASSWORD" \
  "$REPO_ROOT/.venv/bin/ado-ai-pr-review" serve --verbose > "$LOG_FILE" 2>&1 &

echo "PID: $!"

sleep 2
curl -sf "http://localhost:$PORT/health" && echo " — server is up" || echo "ERROR: server did not start, check $LOG_FILE"
