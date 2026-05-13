#!/usr/bin/env bash
# Uruchamia lokalny serwer webhook do testów.
# Użycie: ./scripts/run-local.sh [--copilot | --azure | --cli]
#
# Tryby LLM:
#   --copilot  (domyślnie) GitHub Copilot — wystarczy: gh auth login
#   --azure    Azure OpenAI — wymaga AZURE_OPENAI_* zmiennych
#
# Wymagana zmienna przy trybie webhook:
#   ADO_PAT  — Personal Access Token do Azure DevOps
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_BIN="$REPO_ROOT/.venv/bin"

# --- Opcje ---
MODE="serve"
LLM_PROVIDER="copilot"
PORT="${PORT:-8080}"
LOG_FILE="${LOG_FILE:-/tmp/webhook.log}"
WEBHOOK_USERNAME="${WEBHOOK_USERNAME:-test}"
WEBHOOK_PASSWORD="${WEBHOOK_PASSWORD:-testpass}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --copilot) LLM_PROVIDER="copilot" ;;
    --azure)   LLM_PROVIDER="azure" ;;
    --cli)     MODE="cli" ;;
    *) echo "Nieznana opcja: $1"; exit 1 ;;
  esac
  shift
done

# --- Walidacja ---
if [[ "$MODE" == "serve" ]] && [[ -z "${ADO_PAT:-}" ]]; then
  echo "ERROR: ADO_PAT jest wymagany dla trybu webhook."
  echo "       Ustaw go: export ADO_PAT=<twój-token>"
  echo ""
  echo "       Aby uruchomić tryb lokalny (bez ADO, bez webhooka):"
  echo "       ./scripts/run-local.sh --cli"
  exit 1
fi

if [[ "$LLM_PROVIDER" == "azure" ]]; then
  : "${AZURE_OPENAI_BASE_URL:?AZURE_OPENAI_BASE_URL jest wymagany przy --azure}"
  : "${AZURE_OPENAI_DEPLOYMENT:?AZURE_OPENAI_DEPLOYMENT jest wymagany przy --azure}"
fi

# --- Tryb CLI (brak webhooka, brak ADO) ---
if [[ "$MODE" == "cli" ]]; then
  COMMAND="${CLI_COMMAND:-review}"
  TARGET_BRANCH="${TARGET_BRANCH:-main}"
  echo "Uruchamiam przegląd lokalny (komenda: $COMMAND, baza: $TARGET_BRANCH, LLM: $LLM_PROVIDER)..."
  LLM_PROVIDER="$LLM_PROVIDER" \
    "$VENV_BIN/ado-ai-pr-review" local \
      --command "$COMMAND" \
      --target-branch "$TARGET_BRANCH" \
      --llm "$LLM_PROVIDER"
  exit 0
fi

# --- Tryb serve (webhook) ---

# Zatrzymaj poprzedni proces na tym samym porcie
EXISTING_PID=$(lsof -ti :"$PORT" 2>/dev/null || true)
if [[ -n "$EXISTING_PID" ]]; then
  echo "Zatrzymuję poprzedni proces na porcie $PORT (PID $EXISTING_PID)..."
  kill "$EXISTING_PID"
  sleep 1
fi

echo "Uruchamiam serwer webhook (LLM=$LLM_PROVIDER, port=$PORT)..."
echo "Logi: $LOG_FILE"

ADO_AUTH_MODE=pat \
ADO_PAT="$ADO_PAT" \
LLM_PROVIDER="$LLM_PROVIDER" \
WEBHOOK_USERNAME="$WEBHOOK_USERNAME" \
WEBHOOK_PASSWORD="$WEBHOOK_PASSWORD" \
  "$VENV_BIN/ado-ai-pr-review" serve \
    --host 0.0.0.0 \
    --port "$PORT" \
    --verbose \
    > "$LOG_FILE" 2>&1 &

SERVER_PID=$!
echo "PID: $SERVER_PID"

sleep 2

if curl -sf "http://localhost:$PORT/health" > /dev/null; then
  echo "Serwer działa na http://localhost:$PORT"
  echo ""
  echo "Testowy payload:"
  echo "  curl -s -u $WEBHOOK_USERNAME:$WEBHOOK_PASSWORD \\"
  echo "    -H 'Content-Type: application/json' \\"
  echo "    -d @tests/fixtures/webhook_pr_created.json \\"
  echo "    http://localhost:$PORT/webhook/ado"
  echo ""
  echo "Logi na żywo: tail -f $LOG_FILE"
else
  echo "ERROR: serwer nie uruchomił się. Sprawdź: $LOG_FILE"
  exit 1
fi
