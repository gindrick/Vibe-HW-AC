# 3_web - Modern Web UI for ReAct Chroma Agent

Web interface for interacting with the ReAct agent using `chroma_query` retrieval flow.

## Features

- Query input + direct final answer output
- Response modes: `short`, `detailed`, `citations`
- Adjustable `n_results`
- Configurable `persist_dir` and `collection`
- UI-ready output (backend returns only final user answer as `answer`)
- Query history (last 10) stored in browser `localStorage`

## Prerequisites

1. LiteLLM running (`0_litellm`)
2. MCP server running (`1_mcp`)
3. Chroma collection already populated (e.g. `.sharepoint_chroma_test/sharepoint_docs_test`)

If Docker is unavailable on server, use native stack start from repository root:

```bash
./scripts/start-native.sh
```

Windows:

```powershell
./scripts/start-native.ps1
```

If Docker is available, use:

```bash
./scripts/start-docker.sh
```

## Run

```bash
cd 3_web
uv sync
uv run uvicorn app:app --host 0.0.0.0 --port 8080 --reload
```

Open:

- `http://localhost:8080`

## Microsoft Entra login (optional)

Backend supports server-side login via Microsoft Entra ID (OIDC authorization code flow).

Set in `3_web/.env`:

```env
AUTH_PROVIDER=entra
SESSION_SECRET=replace-with-long-random-secret
ENTRA_TENANT_ID=<tenant-id>
ENTRA_CLIENT_ID=<app-client-id>
ENTRA_CLIENT_SECRET=<app-client-secret>
ENTRA_REDIRECT_URI=http://localhost:8080/auth/callback
# Optional: comma-separated allow list (example: yourcompany.com,subsidiary.com)
ENTRA_ALLOWED_DOMAINS=
# Optional: defaults to "User.Read"
ENTRA_SCOPES=User.Read
```

App registration redirect URI must include the same callback URL (`/auth/callback`).

## LDAP login fallback (optional)

If you want local form login without Entra app registration, switch provider to LDAP bind.

Set in `3_web/.env`:

```env
AUTH_PROVIDER=ldap
SESSION_SECRET=replace-with-long-random-secret
LDAP_SERVER=hranipex.net
LDAP_DOMAIN=hranipex.net
# Optional: restrict login to selected users/emails
LDAP_ALLOWED_USERS=user1,user2,user3@hranipex.net
```

Then use `http://localhost:8081/auth/login` and sign in with your domain credentials.

Default app port in this project is `8080`, so login page is usually `http://localhost:8080/auth/login`.

## API

### `POST /api/ask`

Request:

```json
{
  "query": "k cemu se pouziva funkce 51.2.2.22?",
  "response_mode": "short",
  "n_results": 5,
  "persist_dir": "C:/_git/ai_framework/2_ai_framework/.sharepoint_chroma_test",
  "collection_name": "sharepoint_docs_test",
  "user_message": "{\"user_id\":\"web_user\"}"
}
```

Response:

```json
{
  "success": true,
  "answer": "...final answer to user...",
  "error": null,
  "reasoning": "..."
}
```

## Model change note (Chroma)

- You can switch chat model (`AGENT_MODEL`) without rebuilding Chroma.
- Keep embedding model (`EMBEDDINGS_MODEL`) the same for ingest and retrieval in the same collection.
- If `EMBEDDINGS_MODEL` changes, re-embed/reindex the collection (or use a new collection), otherwise retrieval quality may drop and vector dimension mismatch can occur.

## MCP URL note

Use base URL in env: `MCP_SERVER_URL=http://localhost:8002`.
MCP route itself is available on `/mcp`.
