#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"
LOG_DIR="$ROOT_DIR/logs"

mkdir -p "$RUN_DIR" "$LOG_DIR"

export LITELLM_MASTER_KEY="${LITELLM_MASTER_KEY:-sk-mysecretkey}"
export LITELLM_BASE_URL="${LITELLM_BASE_URL:-http://localhost:4000}"
export LITELLM_API_KEY="${LITELLM_API_KEY:-$LITELLM_MASTER_KEY}"
export EMBEDDINGS_MODEL="${EMBEDDINGS_MODEL:-oai-text-embedding-3-small}"
export MCP_SERVER_URL="${MCP_SERVER_URL:-http://localhost:8002}"
export WEB_PORT="${WEB_PORT:-8000}"

if [[ -n "${DATABASE_URL:-}" ]]; then
  echo "Using DATABASE_URL from environment for LiteLLM persistent state."
else
  echo "DATABASE_URL not set. LiteLLM will run without DB persistence in native mode."
fi

start_service() {
  local name="$1"
  local workdir="$2"
  shift 2

  local pid_file="$RUN_DIR/${name}.pid"
  local out_log="$LOG_DIR/${name}.out.log"
  local err_log="$LOG_DIR/${name}.err.log"

  if [[ -f "$pid_file" ]]; then
    local existing_pid
    existing_pid="$(cat "$pid_file")"
    if [[ -n "$existing_pid" ]] && kill -0 "$existing_pid" 2>/dev/null; then
      echo "$name is already running (PID $existing_pid)."
      return
    fi
    rm -f "$pid_file"
  fi

  (
    cd "$workdir"
    nohup "$@" >"$out_log" 2>"$err_log" &
    echo $! >"$pid_file"
  )

  echo "Started $name (PID $(cat "$pid_file"))"
}

start_service "litellm" "$ROOT_DIR/0_litellm" \
  uvx --from "litellm[proxy]" litellm \
  --config litellm_config.yaml \
  --host 0.0.0.0 \
  --port 4000 \
  --num_workers 1

sleep 2

start_service "mcp" "$ROOT_DIR/1_mcp" uv run python server.py

sleep 2

start_service "web" "$ROOT_DIR/3_web" uv run uvicorn app:app --host 0.0.0.0 --port "$WEB_PORT"

echo "All native services started."
echo "Web UI: http://localhost:$WEB_PORT"