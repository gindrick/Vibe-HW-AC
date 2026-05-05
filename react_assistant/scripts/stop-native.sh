#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/.run"

if [[ ! -d "$RUN_DIR" ]]; then
  echo "No running-state directory found. Nothing to stop."
  exit 0
fi

for name in web mcp litellm; do
  pid_file="$RUN_DIR/${name}.pid"
  if [[ ! -f "$pid_file" ]]; then
    echo "$name is not running (pid file missing)."
    continue
  fi

  pid="$(cat "$pid_file")"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" || true
    echo "Stopped $name (PID $pid)"
  else
    echo "$name pid file found, process already stopped."
  fi

  rm -f "$pid_file"
done

echo "Native services stop sequence finished."