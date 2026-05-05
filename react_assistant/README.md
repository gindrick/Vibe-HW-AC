# AI Framework

Monorepo for AI agents + MCP tools + SharePoint-to-Chroma retrieval pipeline.

## Workspace structure

- `0_litellm` - local LiteLLM proxy (OpenAI-compatible endpoint)
- `1_mcp` - MCP tools server (calculator, web_search, python_repl, wolfram, chroma_query, ...)
- `2_ai_framework` - agent implementations, examples, SharePoint pipelines
- `3_web` - modern web UI for ReAct Chroma agent

## Quick start (end-to-end)

1. Start LiteLLM:

```bash
cd 0_litellm
docker compose up -d
```

2. Start MCP tools server:

```bash
cd ../1_mcp
uv run python server.py
```

3. Run agent example with Chroma query:

```bash
cd ../2_ai_framework
uv run -m src.examples.react.chroma_query_validation
```

## Key docs

- LiteLLM runtime details: [0_litellm/README.md](0_litellm/README.md)
- MCP tools and env setup: [1_mcp/README.md](1_mcp/README.md)
- Agent framework usage and examples: [2_ai_framework/README.md](2_ai_framework/README.md)
- SharePoint ingestion + ACL + retrieval: [2_ai_framework/src/pipelines/README.md](2_ai_framework/src/pipelines/README.md)
- Web UI runbook: [3_web/README.md](3_web/README.md)

## Production checklist

Use this checklist before exposing agent responses to end users:

1. **Runtime up**
	- LiteLLM is running (`http://localhost:4000`)
	- MCP server is running (`http://localhost:8002/mcp`)

2. **Config files prepared**
	- Sources config: `2_ai_framework/src/pipelines/sharepoint_sources.json`
	- ACL policy: `2_ai_framework/src/pipelines/sharepoint_source_policies.json`

3. **Ingest done**
	- Run SharePoint sync+ingest to populate Chroma collection
	- Verify non-zero collection count

4. **ACL verified**
	- Test allowed/denied access for sample group sets
	- Confirm deny-all behavior for users without permitted sources

5. **Final-answer quality validated**
	- Test `short`, `detailed`, `citations` response modes
	- Confirm answer language follows user question language

6. **Operational defaults set**
	- `LITELLM_BASE_URL`, `LITELLM_API_KEY`, `EMBEDDINGS_MODEL`
	- Absolute `CHROMA_PERSIST_DIR` for cross-folder process runs

7. **Frontend contract fixed**
	- UI displays `AgentResponse.result` as final user answer
	- Internal fields (`reasoning`, `actions_taken`) remain debug/audit only

## SharePoint chunking quick guide

Use these profiles for SharePoint ingestion based on retrieval behavior:

| Profile | When to use | Parameters |
|---|---|---|
| Precision | Short factual lookups, less noise in top results | `--chunk-size 900 --chunk-overlap 180` |
| Balanced | Default for most manuals and mixed queries | `--chunk-size 1200 --chunk-overlap 200` |
| Context-heavy | Long process descriptions, higher context continuity | `--chunk-size 1600 --chunk-overlap 300` |
