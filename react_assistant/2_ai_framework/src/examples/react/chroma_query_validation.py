#!/usr/bin/env python3
"""
ReAct Agent Example: Chroma DB Query Validation
Validate that querying SharePoint documents from Chroma DB works.

Prerequisites:
1. Start the MCP tools server:
   cd 1_mcp
   uv run python server.py

2. Set environment variables:
   - LITELLM_API_KEY or OPENAI_API_KEY
   - (Optional) LITELLM_BASE_URL, EMBEDDINGS_MODEL

3. Ensure Chroma collection already exists (ingest finished):
   uv run -m src.pipelines.sharepoint_ingest ...
"""

import asyncio
import os
from dotenv import load_dotenv
from ...agents import ReActAgent

load_dotenv()


async def main():
    print("=== ReAct Agent: Chroma Query Validation ===")
    print("Answer user question using Chroma DB via MCP chroma_query tool\n")

    query_text = os.getenv("CHROMA_QUERY_TEXT", "k čemu se používá funkce 51.2.2.22?")
    persist_dir = os.getenv(
        "CHROMA_PERSIST_DIR",
        "C:/_git/ai_framework/2_ai_framework/.sharepoint_chroma_test",
    )
    collection_name = os.getenv("CHROMA_COLLECTION", "sharepoint_docs_test")
    response_mode = os.getenv("CHROMA_RESPONSE_MODE", "short")
    agent_model = os.getenv("AGENT_MODEL", "oai-gpt-4.1-nano")

    agent = ReActAgent(
        name="ReAct Chroma Validator",
        model=agent_model,
    )
    agent.max_iterations = 3

    try:
        print("Connecting to MCP tools server...")
        await agent.connect()
        print("Connected successfully!\n")

        task = """Answer the user's question using chroma_query tool.

Steps:
1. Call chroma_query with:
    - query='""" + query_text + """'
    - user_message='{"user_id":"demo_user"}'
    - persist_dir='""" + persist_dir + """'
    - collection_name='""" + collection_name + """'
   - n_results=3
2. Synthesize a direct answer to the user's question from retrieved content.
3. Do not describe internal tools or process unless asked.
4. If evidence is weak or missing, clearly say what is uncertain.
5. Respond in the same language as the user's question.
6. Use response_mode='""" + response_mode + """' where allowed values are short|detailed|citations.
"""

        result = await agent.execute(task)
        print(f"Success: {result.success}")
        print(f"Result: {result.result}")
        print(f"Reasoning: {result.reasoning}")
        print(f"Actions taken: {result.actions_taken}")
        if result.error:
            print(f"Error: {result.error}")

    except Exception as e:
        print(f"Error: {e}")
    finally:
        await agent.disconnect()
        print("\nDisconnected from MCP server")


if __name__ == "__main__":
    if not os.getenv("LITELLM_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print("Error: Please set either LITELLM_API_KEY or OPENAI_API_KEY environment variable")
        import sys

        sys.exit(1)

    asyncio.run(main())
