import asyncio
import logging
import os
from typing import Any, Dict, List, Optional
import contextlib
from collections.abc import AsyncIterator
from pathlib import Path
import uvicorn
from dotenv import load_dotenv

# Načti .env soubory (root globální, pak lokální 01_mcp)
_root = Path(__file__).resolve().parent.parent
load_dotenv(_root / ".env", override=False)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)

# MCP
from mcp.server.lowlevel import Server
import mcp.types as types
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.types import Receive, Scope, Send

# General tools
from tools.calculator import calculate
from tools.web_search import web_search
from tools.file_operations import read_file, write_file, list_files
from tools.python_repl import execute_python
from tools.wolfram import wolfram_query
from tools.chroma_retrieval import query_chroma, query_chroma_multi
from tools.query_optimizer import optimize_query

# HR Hiring tools
from tools.pdf_tools import extract_pdf_text

# HR Hiring tools
from tools.evaluation_tools import (
    build_candidate_context,
    build_jd_context,
    get_evaluation,
    get_position_dashboard,
    list_documents,
    list_position_candidates,
    ping,
    read_document,
    run_evaluation,
    save_evaluation,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

server = Server("mcp-tools-server")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="calculator",
            description="Perform mathematical calculations using Python expressions",
            inputSchema={
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "Mathematical expression to evaluate (e.g., '2 + 2', 'sqrt(16)')",
                    }
                },
                "required": ["expression"],
            },
        ),
        types.Tool(
            name="web_search",
            description="Search the web using Tavily API for current information",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "max_results": {"type": "integer", "description": "Maximum number of results", "default": 5},
                    "include_raw_content": {"type": "boolean", "description": "Include raw HTML content", "default": False},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="read_file",
            description="Read contents of a file",
            inputSchema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path to the file to read"}},
                "required": ["path"],
            },
        ),
        types.Tool(
            name="write_file",
            description="Write or overwrite contents to a file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file to write"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        ),
        types.Tool(
            name="list_files",
            description="List files in a directory",
            inputSchema={
                "type": "object",
                "properties": {"directory": {"type": "string", "description": "Directory path", "default": "."}},
            },
        ),
        types.Tool(
            name="python_repl",
            description="Execute Python code in an isolated environment",
            inputSchema={
                "type": "object",
                "properties": {"code": {"type": "string", "description": "Python code to execute"}},
                "required": ["code"],
            },
        ),
        types.Tool(
            name="wolfram_alpha",
            description="Query Wolfram Alpha for computational knowledge",
            inputSchema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Query for Wolfram Alpha"}},
                "required": ["query"],
            },
        ),
        types.Tool(
            name="query_optimizer",
            description="Optimize and expand user query for stronger retrieval recall",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Original user query text"},
                    "user_message": {"type": "string", "description": "Optional user context string", "default": ""},
                    "max_variants": {"type": "integer", "description": "Maximum number of query variants", "default": 4},
                },
                "required": ["query"],
            },
        ),
        types.Tool(
            name="chroma_query",
            description="Query Chroma DB for semantically similar documents",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "User query text"},
                    "user_message": {"type": "string", "description": "Context string with access info"},
                    "persist_dir": {"type": "string", "description": "Chroma persistent directory", "default": ".sharepoint_chroma"},
                    "collection_name": {"type": "string", "description": "Chroma collection name", "default": "sharepoint_docs"},
                    "n_results": {"type": "integer", "description": "Number of top results", "default": 5},
                },
                "required": ["query", "user_message"],
            },
        ),
        types.Tool(
            name="chroma_query_multi",
            description="Query Chroma DB using multiple query variants and merge/rerank hits",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Primary user query text"},
                    "user_message": {"type": "string", "description": "Context string with access info"},
                    "query_variants": {"type": "array", "description": "Optional additional query variants", "items": {"type": "string"}},
                    "persist_dir": {"type": "string", "description": "Chroma persistent directory", "default": ".sharepoint_chroma"},
                    "collection_name": {"type": "string", "description": "Chroma collection name", "default": "sharepoint_docs"},
                    "n_results": {"type": "integer", "description": "Number of final merged top results", "default": 5},
                    "max_per_query": {"type": "integer", "description": "Candidates fetched per query variant", "default": 5},
                },
                "required": ["query", "user_message"],
            },
        ),
        types.Tool(
            name="extract_pdf_text",
            description="Extract plain text from a PDF file. Works with both text-based and OCR-layered PDFs. Returns raw text per page, suitable as input for LLM structured extraction.",
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Absolute path to the PDF file"},
                },
                "required": ["file_path"],
            },
        ),
        # --- HR Hiring tools ---
        types.Tool(
            name="hr_ping",
            description="Health check for HR hiring MCP tools",
            inputSchema={"type": "object", "properties": {}},
        ),
        types.Tool(
            name="hr_read_document",
            description="Return extracted text of one position/candidate document by doc id",
            inputSchema={
                "type": "object",
                "properties": {"doc_id": {"type": "string", "description": "Document ID"}},
                "required": ["doc_id"],
            },
        ),
        types.Tool(
            name="hr_list_documents",
            description="List position-level documents (JD + supplementary) for one position",
            inputSchema={
                "type": "object",
                "properties": {"position_id": {"type": "string", "description": "Position ID"}},
                "required": ["position_id"],
            },
        ),
        types.Tool(
            name="hr_build_jd_context",
            description="Build one context string from JD and supplementary position documents",
            inputSchema={
                "type": "object",
                "properties": {"position_id": {"type": "string", "description": "Position ID"}},
                "required": ["position_id"],
            },
        ),
        types.Tool(
            name="hr_build_candidate_context",
            description="Build one context string from candidate CV and interview transcript documents",
            inputSchema={
                "type": "object",
                "properties": {"candidate_id": {"type": "string", "description": "Candidate ID"}},
                "required": ["candidate_id"],
            },
        ),
        types.Tool(
            name="hr_save_evaluation",
            description="Insert or update evaluation record for a candidate",
            inputSchema={
                "type": "object",
                "properties": {
                    "candidate_id": {"type": "string", "description": "Candidate ID"},
                    "card_json": {"type": "string", "description": "Evaluation card as JSON string"},
                },
                "required": ["candidate_id", "card_json"],
            },
        ),
        types.Tool(
            name="hr_get_evaluation",
            description="Load latest evaluation record for a candidate",
            inputSchema={
                "type": "object",
                "properties": {"candidate_id": {"type": "string", "description": "Candidate ID"}},
                "required": ["candidate_id"],
            },
        ),
        types.Tool(
            name="hr_list_position_candidates",
            description="List all candidates for a position with their evaluation status and scores",
            inputSchema={
                "type": "object",
                "properties": {"position_id": {"type": "string", "description": "Position ID"}},
                "required": ["position_id"],
            },
        ),
        types.Tool(
            name="hr_run_evaluation",
            description="Trigger AI evaluation for a candidate via the backend API",
            inputSchema={
                "type": "object",
                "properties": {"candidate_id": {"type": "string", "description": "Candidate ID"}},
                "required": ["candidate_id"],
            },
        ),
        types.Tool(
            name="hr_get_position_dashboard",
            description="Get full dashboard data for a position: stats + all candidates with full evaluation cards",
            inputSchema={
                "type": "object",
                "properties": {"position_id": {"type": "string", "description": "Position ID"}},
                "required": ["position_id"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: Optional[Dict[str, Any]] = None
) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    if arguments is None:
        arguments = {}

    try:
        if name == "calculator":
            result = await calculate(arguments.get("expression", ""))
            return [types.TextContent(type="text", text=str(result))]

        elif name == "web_search":
            results = await web_search(
                query=arguments.get("query", ""),
                max_results=arguments.get("max_results", 5),
                include_raw_content=arguments.get("include_raw_content", False),
            )
            return [types.TextContent(type="text", text=results)]

        elif name == "read_file":
            content = await read_file(arguments.get("path", ""))
            return [types.TextContent(type="text", text=content)]

        elif name == "write_file":
            result = await write_file(path=arguments.get("path", ""), content=arguments.get("content", ""))
            return [types.TextContent(type="text", text=result)]

        elif name == "list_files":
            files = await list_files(arguments.get("directory", "."))
            return [types.TextContent(type="text", text=files)]

        elif name == "python_repl":
            output = await execute_python(arguments.get("code", ""))
            return [types.TextContent(type="text", text=output)]

        elif name == "wolfram_alpha":
            result = await wolfram_query(arguments.get("query", ""))
            return [types.TextContent(type="text", text=result)]

        elif name == "query_optimizer":
            result = await optimize_query(
                query=arguments.get("query", ""),
                user_message=arguments.get("user_message", ""),
                max_variants=arguments.get("max_variants", 4),
            )
            return [types.TextContent(type="text", text=result)]

        elif name == "chroma_query":
            result = await query_chroma(
                query=arguments.get("query", ""),
                user_message=arguments.get("user_message", ""),
                persist_dir=arguments.get("persist_dir", ".sharepoint_chroma"),
                collection_name=arguments.get("collection_name", "sharepoint_docs"),
                n_results=arguments.get("n_results", 5),
            )
            return [types.TextContent(type="text", text=result)]

        elif name == "chroma_query_multi":
            result = await query_chroma_multi(
                query=arguments.get("query", ""),
                user_message=arguments.get("user_message", ""),
                query_variants=arguments.get("query_variants", None),
                persist_dir=arguments.get("persist_dir", ".sharepoint_chroma"),
                collection_name=arguments.get("collection_name", "sharepoint_docs"),
                n_results=arguments.get("n_results", 5),
                max_per_query=arguments.get("max_per_query", 5),
            )
            return [types.TextContent(type="text", text=result)]

        elif name == "extract_pdf_text":
            result = await extract_pdf_text(arguments.get("file_path", ""))
            return [types.TextContent(type="text", text=result)]

        # --- HR Hiring tools ---
        elif name == "hr_ping":
            result = ping()
            return [types.TextContent(type="text", text=result)]

        elif name == "hr_read_document":
            result = read_document(arguments.get("doc_id", ""))
            return [types.TextContent(type="text", text=result)]

        elif name == "hr_list_documents":
            result = list_documents(arguments.get("position_id", ""))
            import json
            return [types.TextContent(type="text", text=json.dumps(result))]

        elif name == "hr_build_jd_context":
            result = build_jd_context(arguments.get("position_id", ""))
            return [types.TextContent(type="text", text=result)]

        elif name == "hr_build_candidate_context":
            result = build_candidate_context(arguments.get("candidate_id", ""))
            return [types.TextContent(type="text", text=result)]

        elif name == "hr_save_evaluation":
            save_evaluation(arguments.get("candidate_id", ""), arguments.get("card_json", "{}"))
            return [types.TextContent(type="text", text="ok")]

        elif name == "hr_get_evaluation":
            result = get_evaluation(arguments.get("candidate_id", ""))
            import json
            return [types.TextContent(type="text", text=json.dumps(result))]

        elif name == "hr_list_position_candidates":
            result = list_position_candidates(arguments.get("position_id", ""))
            import json
            return [types.TextContent(type="text", text=json.dumps(result))]

        elif name == "hr_run_evaluation":
            result = run_evaluation(arguments.get("candidate_id", ""))
            import json
            return [types.TextContent(type="text", text=json.dumps(result))]

        elif name == "hr_get_position_dashboard":
            result = get_position_dashboard(arguments.get("position_id", ""))
            import json
            return [types.TextContent(type="text", text=json.dumps(result))]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        error_msg = f"Tool execution error: {str(e)}"
        logger.error(error_msg)
        return [types.TextContent(type="text", text=error_msg)]


session_manager = StreamableHTTPSessionManager(
    app=server,
    json_response=True,
    event_store=None,
    stateless=True,
)


async def handle_streamable_http(scope: Scope, receive: Receive, send: Send) -> None:
    await session_manager.handle_request(scope, receive, send)


@contextlib.asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    async with session_manager.run():
        print("MCP tools server started.")
        try:
            yield
        finally:
            print("MCP tools server shutting down.")


starlette_app = Starlette(
    debug=True,
    routes=[Mount("/mcp", app=handle_streamable_http)],
    lifespan=lifespan,
)

if __name__ == "__main__":
    try:
        print("Starting MCP tools server on port 8002...")
        uvicorn.run(starlette_app, host="0.0.0.0", port=8002)
    except KeyboardInterrupt:
        print("Server stopped.")
    except Exception as e:
        logger.error(f"Error starting server: {str(e)}")
        raise e
