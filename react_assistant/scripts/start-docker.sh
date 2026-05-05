#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "Starting LiteLLM stack (Postgres + LiteLLM) via Docker Compose..."
(
  cd "$ROOT_DIR/0_litellm"
  docker compose up -d
)

echo "Starting MCP server via Docker Compose..."
(
  cd "$ROOT_DIR/1_mcp"
  docker compose up -d --build
)

echo "Starting web UI natively..."
cd "$ROOT_DIR/3_web"
uv run uvicorn app:app --host 0.0.0.0 --port 8080