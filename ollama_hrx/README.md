# Ollama ReAct AI Agent

A proper **ReAct (Reason and Act)** agent implementation using Ollama local models that handles multiple tool calls in a loop.

## Key Features

- **Local Models**: Uses Ollama for running models locally
- **Multiple Tool Calls**: Processes ALL tool calls in each response
- **Mixed Tool Format**: Supports both function references and schema objects
- **No API Keys**: Runs completely locally
- **Optional LiteLLM/OpenAI**: Switchable provider via env

## API Differences from OpenAI

- **Tool Format**: Mixed format - direct function references and schema objects
- **Response**: Uses `ChatResponse` object with `message` attribute
- **No API Key**: Requires local Ollama installation
- **Tool Results**: Simple `role: "tool"` messages

## Prerequisites

```bash
# Install and run Ollama
curl -fsSL https://ollama.ai/install.sh | sh
ollama pull llama3.2
```

## LiteLLM (Docker)

```
docker compose up
```

Config: [ollama_hrx/litellm_config.yaml](ollama_hrx/litellm_config.yaml)
Env template: [ollama_hrx/.env.example](ollama_hrx/.env.example)

App (API + UI):

- http://localhost:8000/

## Provider Switch (Ollama vs LiteLLM/OpenAI)

Set environment variables:

```
LLM_PROVIDER=ollama            # or litellm / openai
OLLAMA_MODEL=gpt-oss:20b-cloud

# When LLM_PROVIDER=litellm|openai
LITELLM_BASE_URL=http://0.0.0.0:4000
LITELLM_API_KEY=dummy-key
LITELLM_MODEL=oai-gpt-4.1-nano
```

## Examples

Same examples as OpenAI version but using Ollama's local models.

# Run

## Run directly

`uv run main.py` (or alternative files)

## Run indirectly

Create a virtual environment

```bash
uv venv
```

Activate virtual environment

```bash
source .venv/bin/activate
```

Install packages

```bash
uv sync
```

Run script main (or alternative files)

```bash
python main.py
```
