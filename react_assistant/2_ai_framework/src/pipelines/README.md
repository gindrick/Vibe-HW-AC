# SharePoint Ingest Pipeline

## Multi-source ingest

Use `--sources-config` to ingest from multiple SharePoint sites/folders in one run.

Example:

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --persist .sharepoint_chroma \
  --collection sharepoint_docs
```

Sync SharePoint files into local mirror and ingest in one run:

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --sync-files \
  --persist .sharepoint_chroma \
  --collection sharepoint_docs \
  --extensions pdf,docx,doc
```

Incremental sync behavior:

- Default mode uses Graph delta endpoint and stores delta state in `.sharepoint_chroma/sharepoint_sync_state.json`.
- Only new/changed files are downloaded; deleted files are removed from local mirror.
- Ingest then updates only changed/new files and removes deleted files from Chroma via manifest cleanup.

Delta/full mode controls:

- `--no-sync-delta` forces full listing sync.
- `--sync-reset-delta` discards stored delta token and starts new baseline.
- `--sync-state <path>` sets custom state file location.

Optional sync controls:

- `--sync-max-items 50` limits downloaded files per source.
- `--overwrite-local-files` refreshes already downloaded files.
- `docx` content is extracted natively.
- `doc` uses Windows Word COM fallback (requires Word + pywin32 available); otherwise `.doc` is skipped during ingest.

Track skipped files (unsupported format / extract issues / empty text):

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --sync-files \
  --persist .sharepoint_chroma_test \
  --collection sharepoint_docs_test \
  --extensions pdf,docx,doc,xls \
  --skipped-log src/pipelines/sp_skipped.log
```

Tune chunking without code changes:

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --persist .sharepoint_chroma_test \
  --collection sharepoint_docs_test \
  --extensions pdf,docx,doc \
  --chunk-size 1400 \
  --chunk-overlap 250
```

Recommended chunking profiles:

- **Precision** (short fact lookups, lower noise): `--chunk-size 900 --chunk-overlap 180`
- **Balanced** (default for most manuals): `--chunk-size 1200 --chunk-overlap 200`
- **Context-heavy** (long process descriptions): `--chunk-size 1600 --chunk-overlap 300`

Ready-to-run examples:

```bash
# Precision
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --sync-files \
  --persist .sharepoint_chroma_test \
  --collection sharepoint_docs_precision \
  --extensions pdf,docx,doc \
  --chunk-size 900 \
  --chunk-overlap 180

# Balanced
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --sync-files \
  --persist .sharepoint_chroma_test \
  --collection sharepoint_docs_balanced \
  --extensions pdf,docx,doc \
  --chunk-size 1200 \
  --chunk-overlap 200

# Context-heavy
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --sync-files \
  --persist .sharepoint_chroma_test \
  --collection sharepoint_docs_context \
  --extensions pdf,docx,doc \
  --chunk-size 1600 \
  --chunk-overlap 300
```

Each source supports:

- `source_id` - stable source key (used in metadata and ACL)
- `site_url` - SharePoint site URL
- `drive_name` - drive/library name (default: `Documents`)
- `folder_path` - relative folder path or full SharePoint folder URL
- `source_dir` - local mirrored folder for file ingestion
- `allowed_aad_groups` - default source access groups
- `enabled` - include/exclude source in runs

## Add new SharePoint site pipeline

Use this checklist when onboarding another site/folder:

1. Add a new source entry to `src/pipelines/sharepoint_sources.json`:
   - Set unique `source_id` (example: `hr_global`).
   - Set `site_url`, `drive_name`, `folder_path`.
   - Set dedicated mirror path in `source_dir` (example: `./src/pipelines/sharepoint_mirror/hr_global`).
   - Set `enabled: true`.
2. Add source ACL mapping to `src/pipelines/sharepoint_source_policies.json`:
   - Add key `hr_global` with allowed Entra groups list.
3. Create mirror folder for the source:
  - Linux/macOS: `mkdir -p src/pipelines/sharepoint_mirror/hr_global`
  - Windows PowerShell: `New-Item -ItemType Directory -Force -Path src/pipelines/sharepoint_mirror/hr_global`
4. Validate source access and listing:

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --list-only \
  --sp-list-log src/pipelines/sp_list.log
```

5. Run first sync+ingest for all sources (including the new one):

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --sources-config src/pipelines/sharepoint_sources.json \
  --source-policies src/pipelines/sharepoint_source_policies.json \
  --sync-files \
  --persist .sharepoint_chroma \
  --collection sharepoint_docs \
  --extensions pdf,docx,doc \
  --skipped-log src/pipelines/sp_skipped.log
```

6. Verify retrieval ACL for the new source:

```bash
uv run -m src.pipelines.sharepoint_retrieval \
  --env src/pipelines/.env \
  --query "test query" \
  --sources-config src/pipelines/sharepoint_sources.json \
  --source-policies src/pipelines/sharepoint_source_policies.json \
  --user-groups "HR-Team" \
  --n-results 5
```

Notes:

- Keep each site in its own `source_id` and `source_dir`.
- Reuse one Chroma collection with `source_id` metadata filtering, or split collections if required by governance.
- For production onboarding, prefer `sharepoint_sources.json` + `sharepoint_source_policies.json` (not `*.example`/`*.test`).

## Access-control helpers

Evaluate allowed sources for a user group set:

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --sources-config src/pipelines/sharepoint_sources.json \
  --source-policies src/pipelines/sharepoint_source_policies.json \
  --user-groups "Finance-Team,Audit" \
  --print-allowed-sources
```

Notes:

- `--source-policies` overrides `allowed_aad_groups` from sources config.
- If a source has no groups configured, it is treated as open.
- Ingested chunks include `source_id` metadata for retrieval-time filtering.

## Export documents + SharePoint permissions

List real SharePoint documents and write ACL identities per document:

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --list-only \
  --include-permissions \
  --expand-group-members \
  --sp-list-log src/pipelines/sp_list.log \
  --sp-permissions-log src/pipelines/sp_permissions.log
```

Optional speed limit for permissions export:

```bash
uv run -m src.pipelines.sharepoint_ingest \
  --env src/pipelines/.env \
  --list-only \
  --include-permissions \
  --permissions-max-items 20 \
  --sp-permissions-log src/pipelines/sp_permissions.log
```

Notes:

- Permissions come from Microsoft Graph endpoint `/drives/{driveId}/items/{itemId}/permissions`.
- Output contains resolved users/groups/links as returned by Graph metadata.
- `--expand-group-members` tries to resolve listed groups to users via Graph `/groups/{groupId}/transitiveMembers`.
- If item-level users are not explicitly listed, SharePoint often returns site groups (inheritance); expansion may fail for non-Entra groups or missing Graph permissions.

## Retrieval with source ACL filter

Query with user-group-based source resolution:

```bash
uv run -m src.pipelines.sharepoint_retrieval \
  --env src/pipelines/.env \
  --query "Jaká je schvalovací politika faktur?" \
  --sources-config src/pipelines/sharepoint_sources.json \
  --source-policies src/pipelines/sharepoint_source_policies.json \
  --user-groups "Finance-Team,Audit" \
  --n-results 5
```

Query with explicit source allowlist override:

```bash
uv run -m src.pipelines.sharepoint_retrieval \
  --env src/pipelines/.env \
  --query "Jaká je schvalovací politika faktur?" \
  --allowed-source-ids "finance_cs" \
  --n-results 5
```

Query with automatic groups from Entra delegated token:

```bash
set AAD_USER_ACCESS_TOKEN=<jwt_token>
uv run -m src.pipelines.sharepoint_retrieval \
  --env src/pipelines/.env \
  --query "Jaká je schvalovací politika faktur?" \
  --sources-config src/pipelines/sharepoint_sources.json \
  --source-policies src/pipelines/sharepoint_source_policies.json \
  --print-resolved-groups \
  --n-results 5
```

Behavior:

- If `--allowed-source-ids` is provided, it is used directly.
- Else if `--sources-config` is provided, allowed `source_id` values are resolved from user groups + policies.
- User groups are resolved in this order: `--user-groups` → token (`--entra-access-token` or env `AAD_USER_ACCESS_TOKEN`) → empty list.
- For token mode, script reads `groups` claim from JWT; if token indicates group overage, it tries Graph `/me/transitiveMemberOf`.
- Else no source filter is applied.

## ReAct Chroma query validation example

The script `src.examples.react.chroma_query_validation` supports env configuration for query and Chroma target:

```env
CHROMA_QUERY_TEXT=what is this function 51.2.2.22 good for ?
CHROMA_PERSIST_DIR=C:/_git/ai_framework/2_ai_framework/.sharepoint_chroma_test
CHROMA_COLLECTION=sharepoint_docs_test
CHROMA_RESPONSE_MODE=short
```

Run:

```bash
uv run -m src.examples.react.chroma_query_validation
```

Notes:

- Use absolute `CHROMA_PERSIST_DIR` when MCP server runs from another working directory.
- Keep `LITELLM_BASE_URL`, `LITELLM_API_KEY`, and `EMBEDDINGS_MODEL` set for MCP retrieval flow.

## Model compatibility for Chroma (important)

When using Chroma retrieval, there are two different model roles:

- **Embedding model** (`EMBEDDINGS_MODEL`) - used to create vectors during ingest and query vectors during retrieval.
- **Chat/generation model** (`AGENT_MODEL`) - used only to synthesize the final answer from retrieved chunks.

Key rule:

- `AGENT_MODEL` can be changed without reindexing Chroma.
- `EMBEDDINGS_MODEL` should stay the same for ingest + retrieval in the same collection.

What happens if you change models:

- Change only `AGENT_MODEL` (e.g., OpenAI -> Ollama): retrieval stays functional.
- Change `EMBEDDINGS_MODEL`: you should re-embed/reindex the collection (or create a new collection), otherwise relevance can degrade and vector dimension mismatches may occur.

Recommended migration to Ollama (safe for existing Chroma data):

1. Keep `EMBEDDINGS_MODEL` unchanged.
2. Switch only `AGENT_MODEL` to your Ollama-mapped model in LiteLLM.
3. Restart services and validate retrieval quality with the same `persist_dir` + `collection_name`.

Response modes:

- `short` - concise answer in roughly 3-5 sentences.
- `detailed` - broader explanation in multiple paragraphs.
- `citations` - answer plus exact quotes from retrieved documents with source metadata.

For local testing, set mode via environment before run:

```bash
set CHROMA_RESPONSE_MODE=citations
uv run -m src.examples.react.chroma_query_validation
```
