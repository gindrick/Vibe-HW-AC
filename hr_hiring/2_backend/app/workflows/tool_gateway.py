from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import httpx

from app.config import settings


class MCPToolGateway:
    """Small adapter for MCP tools with local import fallback for dev."""

    def __init__(self) -> None:
        self._local_tools = None

    def _load_local_tools(self):
        if self._local_tools is not None:
            return self._local_tools
        mcp_tools_dir = Path(__file__).resolve().parents[4] / "01_mcp"
        if str(mcp_tools_dir) not in sys.path:
            sys.path.insert(0, str(mcp_tools_dir))
        from tools import evaluation_tools  # pylint: disable=import-outside-toplevel

        self._local_tools = evaluation_tools
        return self._local_tools

    def _call_via_http(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        # Placeholder transport for future MCP JSON-RPC integration.
        # Current fallback path keeps development moving with same tool contract.
        payload = {"tool": tool_name, "arguments": arguments}
        resp = httpx.post(settings.mcp_server_url, json=payload, timeout=20.0)
        if resp.status_code >= 400:
            raise RuntimeError(f"MCP HTTP call failed: {resp.status_code}")
        body = resp.json()
        if isinstance(body, dict) and "result" in body:
            return body["result"]
        return body

    def call(self, tool_name: str, **kwargs: Any) -> Any:
        if settings.mcp_mode == "http":
            return self._call_via_http(tool_name, kwargs)

        local_tools = self._load_local_tools()
        fn = getattr(local_tools, tool_name, None)
        if fn is None:
            raise ValueError(f"Unknown MCP tool: {tool_name}")
        return fn(**kwargs)

    def read_document(self, doc_id: str) -> str:
        return str(self.call("read_document", doc_id=doc_id))

    def list_documents(self, position_id: str) -> list[dict[str, Any]]:
        result = self.call("list_documents", position_id=position_id)
        return result if isinstance(result, list) else []

    def build_jd_context(self, position_id: str) -> str:
        return str(self.call("build_jd_context", position_id=position_id))

    def build_candidate_context(self, candidate_id: str) -> str:
        return str(self.call("build_candidate_context", candidate_id=candidate_id))

    def save_evaluation(self, candidate_id: str, card_json: str) -> None:
        self.call("save_evaluation", candidate_id=candidate_id, card_json=card_json)

    def get_evaluation(self, candidate_id: str) -> dict[str, Any]:
        result = self.call("get_evaluation", candidate_id=candidate_id)
        if isinstance(result, dict):
            return result
        if isinstance(result, str):
            try:
                parsed = json.loads(result)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
        return {"status": "unknown"}


gateway = MCPToolGateway()
