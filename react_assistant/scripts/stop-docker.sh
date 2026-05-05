#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Stopping MCP Docker Compose stack..."
(
  cd "$ROOT_DIR/1_mcp"
  docker compose down
)

echo "Stopping LiteLLM Docker Compose stack..."
(
  cd "$ROOT_DIR/0_litellm"
  docker compose down
)

echo "Docker services stopped."