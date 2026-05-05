import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from .base import Agent, AgentResponse
from ..clients import LLMClient, MCPClient


class ToolArgumentsOutput(BaseModel):
    """Structured model for normalized tool arguments."""

    arguments: Dict[str, Any] = Field(default_factory=dict)


class ReActFinalOutput(BaseModel):
    """Structured model for the final ReAct response."""

    answer: str = Field(description="Final answer for the user")
    summary: str = Field(
        default="",
        description="Short summary of how the answer was produced",
    )
    confidence: str = Field(
        default="medium",
        description="low|medium|high confidence in the final answer",
    )
    citations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of exact citations with source metadata",
    )


class LocalizedAnswerOutput(BaseModel):
    """Structured model for localized final answer text."""

    answer: str = Field(description="Localized final answer text")


class ReActAgent(Agent):
    """ReAct (Reason and Act) Agent implementation using MCP tools."""

    def __init__(
        self,
        name: str = "ReAct Agent",
        model: str = "oai-gpt-4.1-nano",
        always_structured_tool_args: bool = False,
    ):
        super().__init__(name)
        self.llm = LLMClient(llm_model=model)
        self.mcp_client = MCPClient()
        self.max_iterations = 10
        self.always_structured_tool_args = always_structured_tool_args
        self._connected = False

    async def connect(self):
        """Connect to the MCP tools server."""
        if not self._connected:
            await self.mcp_client.connect()
            self._connected = True

    async def disconnect(self):
        """Disconnect from the MCP tools server."""
        if self._connected:
            await self.mcp_client.disconnect()
            self._connected = False

    async def execute(self, task: str) -> AgentResponse:
        """Execute a task using ReAct pattern with MCP tools."""
        # Ensure we're connected
        await self.connect()

        response_mode = self._normalize_response_mode(task)

        actions_taken = []
        reasoning_steps = []
        retrieval_retry_used = False
        retrieval_retry_limit = 1
        retrieval_task_context = self._extract_retrieval_context_from_task(task)

        # Get available tools from MCP server
        try:
            tool_schemas = await self.mcp_client.get_tools_definitions()
            tool_schema_map = self._build_tool_schema_map(tool_schemas)
        except Exception as e:
            return AgentResponse(
                success=False,
                result=None,
                reasoning="Failed to get tools from MCP server",
                actions_taken=actions_taken,
                error=str(e),
            )

        # Build system prompt and add to history if this is the first message
        if not self.conversation_history:
            system_prompt = self._build_system_prompt()
            self.add_to_history({"role": "system", "content": system_prompt})

        # Add user message
        self.add_to_history({"role": "user", "content": task})

        for iteration in range(self.max_iterations):
            try:

                print(f"\n--- Iteration {iteration + 1} ---")
                print("Current conversation history:")
                for msg in self.conversation_history:
                    print(msg)
                print("--------------------------------------")

                # Call LLM with tools
                response = await self.llm.call(
                    messages=self.conversation_history,
                    tools=tool_schemas,
                )

                # Check if the response contains tool calls
                message = response.choices[0].message

                print(f"\n--- Iteration {iteration + 1} ---")
                print(f"LLM Response:")
                print(message)
                print(message.model_dump())
                print("--------------------------------------")

                # First check if there's any content (reasoning) before tool calls
                if message.content:
                    print(f"Assistant reasoning: {message.content}")

                if message.tool_calls:
                    tool_call_msg = {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": [
                            {
                                "id": tool_call.id,
                                "type": "function",
                                "function": {
                                    "name": tool_call.function.name,
                                    "arguments": tool_call.function.arguments,
                                },
                            }
                            for tool_call in message.tool_calls
                        ],
                    }

                    self.add_to_history(tool_call_msg)

                    # Execute each tool call via MCP
                    for tool_call in message.tool_calls:
                        tool_name = tool_call.function.name
                        try:
                            tool_args = await self._parse_tool_arguments(
                                tool_call.function.arguments,
                                tool_name,
                            )
                            tool_args = self._sanitize_tool_arguments(
                                tool_name=tool_name,
                                tool_args=tool_args,
                                tool_schema_map=tool_schema_map,
                            )
                            self._validate_required_tool_arguments(
                                tool_name=tool_name,
                                tool_args=tool_args,
                                tool_schema_map=tool_schema_map,
                            )

                            reasoning_steps.append(f"Using tool: {tool_name}")

                            # Call tool via MCP
                            tool_result = await self.mcp_client.call_tool(
                                tool_name, tool_args
                            )
                            actions_taken.append(f"{tool_name}({tool_args})")

                            # Add tool result to conversation
                            tool_message = {
                                "role": "tool",
                                "tool_call_id": tool_call.id,
                                "content": str(tool_result),  # Ensure it's a string
                            }

                            print("--- Tool Result ---")
                            print(f"Tool: {tool_name}({tool_args})")
                            print(f"Result: {tool_result}")
                            print("---------------------")

                            self.add_to_history(tool_message)

                            retry_instruction = self._build_retrieval_retry_instruction(
                                tool_name=tool_name,
                                tool_result=tool_result,
                                retrieval_task_context=retrieval_task_context,
                                retry_used=retrieval_retry_used,
                                retry_limit=retrieval_retry_limit,
                            )
                            if retry_instruction:
                                retrieval_retry_used = True
                                reasoning_steps.append("Low-recall retrieval detected, forcing optimized retry")
                                self.add_to_history(
                                    {
                                        "role": "user",
                                        "content": retry_instruction,
                                    }
                                )

                        except Exception as e:
                            error_msg = f"Tool execution error: {str(e)}"
                            return AgentResponse(
                                success=False,
                                result=None,
                                reasoning=" -> ".join(reasoning_steps),
                                actions_taken=actions_taken,
                                error=error_msg,
                            )
                else:
                    # No tool calls, we have the final answer
                    content = message.content or ""
                    user_question = self._extract_user_question_from_task(task)
                    target_language = self._detect_target_language(user_question)
                    structured_output = await self._build_structured_final_output(
                        task=task,
                        draft_answer=content,
                        tool_context=self._collect_recent_tool_context(),
                        user_question=user_question,
                        target_language=target_language,
                        response_mode=response_mode,
                    )
                    retrieval_records = self._get_latest_retrieval_records()
                    final_content = self._format_final_content(
                        structured_output=structured_output,
                        response_mode=response_mode,
                        tool_context=self._collect_recent_tool_context(),
                        retrieval_records=retrieval_records,
                        user_question=user_question,
                    )
                    if not self._is_answer_in_target_language(final_content, target_language):
                        final_content = await self._localize_answer(
                            answer=final_content,
                            user_question=user_question,
                            target_language=target_language,
                        )

                    if structured_output.summary:
                        reasoning_steps.append(structured_output.summary)
                    reasoning_steps.append(f"Response mode: {response_mode}")
                    reasoning_steps.append(f"Confidence: {structured_output.confidence}")

                    print("\n" + "=" * 80)
                    print("FINAL ANSWER TO USER")
                    print("-" * 80)
                    print(final_content)
                    print("=" * 80)

                    self.add_to_history({"role": "assistant", "content": final_content})
                    reasoning_steps.append("Generated final response")

                    return AgentResponse(
                        success=True,
                        result=final_content,
                        reasoning=" -> ".join(reasoning_steps),
                        actions_taken=actions_taken,
                    )

            except Exception as e:
                return AgentResponse(
                    success=False,
                    result=None,
                    reasoning=" -> ".join(reasoning_steps),
                    actions_taken=actions_taken,
                    error=f"LLM error: {str(e)}",
                )

        # Max iterations reached
        return AgentResponse(
            success=False,
            result=None,
            reasoning=" -> ".join(reasoning_steps),
            actions_taken=actions_taken,
            error="Max iterations reached without completing the task",
        )

    def _normalize_response_mode(self, task: str) -> str:
        lowered = task.lower()
        if "response_mode='citations'" in lowered or "response_mode=\"citations\"" in lowered:
            return "citations"
        if "response_mode='detailed'" in lowered or "response_mode=\"detailed\"" in lowered:
            return "detailed"
        if "response_mode='short'" in lowered or "response_mode=\"short\"" in lowered:
            return "short"
        return "short"

    async def _parse_tool_arguments(self, raw_arguments: str, tool_name: str) -> Dict[str, Any]:
        if not self.always_structured_tool_args:
            try:
                parsed = json.loads(raw_arguments)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass

        repair_prompt = (
            "Normalize tool arguments into a valid JSON object. "
            "Do not invent fields. If uncertain, return an empty object."
        )
        messages = [
            {"role": "system", "content": repair_prompt},
            {
                "role": "user",
                "content": (
                    f"Tool name: {tool_name}\n"
                    f"Raw arguments string:\n{raw_arguments}"
                ),
            },
        ]

        try:
            structured = await self.llm.call_structured(
                messages=messages,
                response_model=ToolArgumentsOutput,
            )
            return structured.arguments
        except Exception as e:
            raise ValueError(
                f"Invalid tool arguments for {tool_name}: {raw_arguments}. Error: {str(e)}"
            )

    def _build_tool_schema_map(self, tool_schemas: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        schema_map: Dict[str, Dict[str, Any]] = {}
        for tool in tool_schemas:
            function_data = tool.get("function", {}) if isinstance(tool, dict) else {}
            if not isinstance(function_data, dict):
                continue
            tool_name = function_data.get("name")
            parameters = function_data.get("parameters", {})
            if isinstance(tool_name, str) and isinstance(parameters, dict):
                schema_map[tool_name] = parameters
        return schema_map

    def _sanitize_tool_arguments(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_schema_map: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(tool_args, dict):
            return {}

        schema = tool_schema_map.get(tool_name, {})
        properties = schema.get("properties", {}) if isinstance(schema, dict) else {}
        if not isinstance(properties, dict) or not properties:
            return tool_args

        allowed_keys = set(properties.keys())
        return {key: value for key, value in tool_args.items() if key in allowed_keys}

    def _validate_required_tool_arguments(
        self,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_schema_map: Dict[str, Dict[str, Any]],
    ) -> None:
        schema = tool_schema_map.get(tool_name, {})
        required = schema.get("required", []) if isinstance(schema, dict) else []
        if not isinstance(required, list):
            return

        missing = [
            key for key in required if not isinstance(key, str) or key not in tool_args
        ]
        if missing:
            raise ValueError(
                f"Missing required tool arguments for {tool_name}: {missing}"
            )

    def _collect_recent_tool_context(self, max_messages: int = 3, max_chars: int = 9000) -> str:
        tool_messages = [
            msg for msg in self.conversation_history if isinstance(msg, dict) and msg.get("role") == "tool"
        ]
        if not tool_messages:
            return ""

        selected = tool_messages[-max_messages:]
        chunks: List[str] = []
        for idx, msg in enumerate(selected, start=1):
            content = str(msg.get("content", ""))
            if not content:
                continue
            chunks.append(f"Tool output {idx}:\n{content}")

        joined = "\n\n".join(chunks)
        if len(joined) > max_chars:
            return joined[:max_chars]
        return joined

    def _format_final_content(
        self,
        structured_output: ReActFinalOutput,
        response_mode: str,
        tool_context: str,
        retrieval_records: List[Dict[str, Any]],
        user_question: str,
    ) -> str:
        if response_mode == "short":
            return structured_output.answer

        if response_mode == "detailed":
            return self._ensure_multiple_paragraphs(structured_output.answer)

        citations = structured_output.citations or []
        valid_citations: List[Dict[str, Any]] = []
        for citation in citations:
            if not isinstance(citation, dict):
                continue
            quote = str(citation.get("quote", "")).strip()
            if not quote:
                continue
            if quote not in tool_context:
                continue
            enriched = dict(citation)
            if (
                not str(enriched.get("file_name", "")).strip()
                or not str(enriched.get("source_id", "")).strip()
            ):
                matched = self._find_record_for_quote(quote, retrieval_records)
                if matched:
                    enriched.setdefault("file_name", matched.get("file_name", ""))
                    enriched.setdefault("source_id", matched.get("source_id", ""))
                    enriched.setdefault("page", matched.get("page", ""))
                    enriched["file_name"] = str(enriched.get("file_name", "")).strip() or str(
                        matched.get("file_name", "")
                    ).strip()
                    enriched["source_id"] = str(enriched.get("source_id", "")).strip() or str(
                        matched.get("source_id", "")
                    ).strip()
                    if enriched.get("page") in (None, ""):
                        enriched["page"] = matched.get("page", "")

            valid_citations.append(enriched)

        ranked_records = self._rank_retrieval_records(user_question, retrieval_records)

        if not valid_citations:
            valid_citations = self._fallback_citations_from_records(
                retrieval_records=ranked_records,
                user_question=user_question,
            )
        else:
            top_fallback = self._fallback_citations_from_records(
                retrieval_records=ranked_records,
                user_question=user_question,
                limit=2,
            )
            if top_fallback:
                existing_quotes = {
                    str(item.get("quote", "")).strip() for item in valid_citations if isinstance(item, dict)
                }
                for item in top_fallback:
                    quote = str(item.get("quote", "")).strip()
                    if quote and quote not in existing_quotes:
                        valid_citations.append(item)
                        existing_quotes.add(quote)
                    if len(valid_citations) >= 3:
                        break

        if not valid_citations:
            return (
                structured_output.answer
                + "\n\nCitace nebyly k dispozici v požadovaném formátu z nalezených dokumentů."
            )

        lines = [structured_output.answer.strip(), "", "Přesné citace:"]
        for item in valid_citations:
            quote = str(item.get("quote", "")).strip()
            file_name = str(item.get("file_name", "")).strip() or "unknown"
            source_id = str(item.get("source_id", "")).strip() or "unknown"
            page = item.get("page")
            page_part = f", page={page}" if page not in (None, "") else ""
            lines.append(f"- \"{quote}\" (source_id={source_id}, file={file_name}{page_part})")
        return "\n".join(lines)

    def _ensure_multiple_paragraphs(self, answer: str) -> str:
        content = (answer or "").strip()
        if not content:
            return content
        if "\n\n" in content:
            return content

        sentences = re.split(r"(?<=[.!?])\s+", content)
        sentences = [s.strip() for s in sentences if s.strip()]
        if len(sentences) < 2:
            return content

        split_at = max(1, len(sentences) // 2)
        first = " ".join(sentences[:split_at]).strip()
        second = " ".join(sentences[split_at:]).strip()
        if not second:
            return content
        return f"{first}\n\n{second}"

    def _get_latest_retrieval_records(self) -> List[Dict[str, Any]]:
        tool_messages = [
            msg for msg in self.conversation_history if isinstance(msg, dict) and msg.get("role") == "tool"
        ]
        for msg in reversed(tool_messages):
            content = str(msg.get("content", "")).strip()
            if not content:
                continue
            try:
                data = json.loads(content)
            except Exception:
                continue
            if not isinstance(data, dict):
                continue
            results = data.get("results", [])
            if isinstance(results, list):
                normalized = [item for item in results if isinstance(item, dict)]
                if normalized:
                    return normalized
        return []

    def _find_record_for_quote(
        self,
        quote: str,
        retrieval_records: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        needle = quote.strip()
        if not needle:
            return None
        for record in retrieval_records:
            document = str(record.get("document", ""))
            if needle in document:
                return record
        return None

    def _fallback_citations_from_records(
        self,
        retrieval_records: List[Dict[str, Any]],
        user_question: str,
        limit: int = 2,
    ) -> List[Dict[str, Any]]:
        citations: List[Dict[str, Any]] = []
        for record in retrieval_records:
            document = str(record.get("document", "")).strip()
            if not document:
                continue
            quote = self._extract_relevant_quote(
                document=document,
                user_question=user_question,
            )
            if not quote:
                continue
            citations.append(
                {
                    "quote": quote,
                    "source_id": str(record.get("source_id", "")).strip(),
                    "file_name": str(record.get("file_name", "")).strip(),
                    "page": record.get("page", ""),
                }
            )
            if len(citations) >= limit:
                break
        return citations

    def _rank_retrieval_records(
        self,
        user_question: str,
        retrieval_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        question_tokens = self._tokenize_text(user_question)
        code_matches = re.findall(r"\d+(?:\.\d+)+", user_question)

        scored: List[tuple[float, Dict[str, Any]]] = []
        for record in retrieval_records:
            document = str(record.get("document", ""))
            tokens = self._tokenize_text(document)
            overlap = len(question_tokens.intersection(tokens))
            token_score = overlap / max(1, len(question_tokens))

            code_score = 0.0
            lowered_document = document.lower()
            for code in code_matches:
                if code.lower() in lowered_document:
                    code_score += 1.0

            distance = record.get("distance")
            distance_score = 0.0
            if isinstance(distance, (int, float)):
                distance_score = -float(distance) * 0.05

            final_score = token_score + code_score + distance_score
            scored.append((final_score, record))

        scored.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in scored]

    def _tokenize_text(self, text: str) -> set[str]:
        tokens = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        return {token for token in tokens if len(token) >= 3}

    def _extract_relevant_quote(self, document: str, user_question: str, max_len: int = 280) -> str:
        lines = [line.strip() for line in document.splitlines() if line.strip()]
        if not lines:
            return ""

        code_matches = re.findall(r"\d+(?:\.\d+)+", user_question)
        lowered_question = user_question.lower()
        question_tokens = self._tokenize_text(user_question)

        for code in code_matches:
            for line in lines:
                if code in line:
                    return line[:max_len].strip()

        best_line = ""
        best_score = -1
        for line in lines:
            lowered_line = line.lower()
            line_tokens = self._tokenize_text(line)
            overlap = len(question_tokens.intersection(line_tokens))
            if lowered_question and lowered_question in lowered_line:
                overlap += 3
            if overlap > best_score:
                best_score = overlap
                best_line = line

        if best_line:
            return best_line[:max_len].strip()
        return document[:max_len].strip()

    def _extract_user_question_from_task(self, task: str) -> str:
        patterns = [
            r"query='([^']+)'",
            r'query="([^"]+)"',
        ]
        for pattern in patterns:
            match = re.search(pattern, task)
            if match:
                return match.group(1).strip()
        return task.strip()

    def _detect_target_language(self, user_question: str) -> str:
        question = user_question.lower()
        if any(ch in user_question for ch in "ěščřžýáíéůúňťďó"):  # Czech diacritics
            return "Czech"
        czech_markers = [
            "k čemu",
            "k cemu",
            "jak",
            "proč",
            "proc",
            "používá",
            "pouziva",
            "funkce",
            "zákazník",
            "zakaznik",
            "co je",
            "kde",
            "pro koho",
        ]
        if any(marker in question for marker in czech_markers):
            return "Czech"
        return "same as user question"

    def _is_answer_in_target_language(self, answer: str, target_language: str) -> bool:
        if target_language != "Czech":
            return True
        lowered = answer.lower()
        if any(ch in answer for ch in "ěščřžýáíéůúňťďó"):
            return True
        czech_words = ["funkce", "používá", "slouží", "pro", "která", "tato", "dotaz"]
        return any(word in lowered for word in czech_words)

    async def _localize_answer(
        self,
        answer: str,
        user_question: str,
        target_language: str,
    ) -> str:
        if target_language == "same as user question":
            return answer

        messages = [
            {
                "role": "system",
                "content": (
                    "Rewrite the answer into the requested language. "
                    "Keep meaning and uncertainty level unchanged."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"User question: {user_question}\n"
                    f"Target language: {target_language}\n"
                    f"Answer to rewrite:\n{answer}"
                ),
            },
        ]

        try:
            localized = await self.llm.call_structured(
                messages=messages,
                response_model=LocalizedAnswerOutput,
            )
            return localized.answer
        except Exception:
            return answer

    async def _build_structured_final_output(
        self,
        task: str,
        draft_answer: str,
        tool_context: str,
        user_question: str,
        target_language: str,
        response_mode: str,
    ) -> ReActFinalOutput:
        messages = [
            {
                "role": "system",
                "content": (
                    "Return a structured final answer focused on the user's question. "
                    "Prioritize a direct, helpful answer over process description. "
                    "Do not describe internal tools unless explicitly asked. "
                    "If evidence is insufficient, state uncertainty clearly and suggest next step. "
                    "Use the same language as the user's question unless explicitly requested otherwise. "
                    "If response mode is short, return 3-5 sentences. "
                    "If response mode is detailed, return multiple paragraphs with richer explanation. "
                    "If response mode is citations, include exact quotes and citation metadata in citations field. "
                    "For citations mode, do not paraphrase quotes in citations field."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Original task:\n{task}\n\n"
                    f"User question:\n{user_question}\n\n"
                    f"Required answer language:\n{target_language}\n\n"
                    f"Response mode:\n{response_mode}\n\n"
                    f"Draft answer:\n{draft_answer}\n\n"
                    f"Relevant tool outputs:\n{tool_context}\n\n"
                    "Write answer as if for end-user UI. "
                    "First sentence must answer the user directly."
                ),
            },
        ]

        try:
            return await self.llm.call_structured(
                messages=messages,
                response_model=ReActFinalOutput,
            )
        except Exception:
            return ReActFinalOutput(answer=draft_answer, summary="")

    def _build_system_prompt(self) -> str:
        """Build the system prompt for ReAct pattern."""
        return """You are an AI assistant that follows the ReAct (Reason + Act) pattern.

For each step:
1. Reason: Think about what needs to be done next
2. Act: Use the appropriate tool to take action
3. Observe: Consider the tool's output

Retrieval policy (mandatory for knowledge questions):
- First call query_optimizer with the user query.
- Then call chroma_query_multi with optimized query_variants.
- If retrieval count is low (0-1) or evidence is weak, run one retry with broader variants and larger max_per_query.
- Only produce final answer after retrieval evidence is sufficient or after one explicit retry; then clearly state uncertainty.
- Prefer exact numeric function code matches (e.g., 51.2.2.22) when ranking evidence.

Continue this cycle until the task is complete. When you have achieved the goal, provide a final answer without using any more tools.

Important: Once you have all the information needed to answer the user's request, stop using tools and provide your final response."""

    def _extract_retrieval_context_from_task(self, task: str) -> Dict[str, Any]:
        context: Dict[str, Any] = {
            "query": self._extract_user_question_from_task(task),
            "user_message": '{"user_id":"web_user"}',
            "persist_dir": ".sharepoint_chroma",
            "collection_name": "sharepoint_docs",
            "n_results": 5,
        }

        patterns = {
            "user_message": [r"user_message='([^']*)'", r'user_message="([^"]*)"'],
            "persist_dir": [r"persist_dir='([^']*)'", r'persist_dir="([^"]*)"'],
            "collection_name": [r"collection_name='([^']*)'", r'collection_name="([^"]*)"'],
            "n_results": [r"n_results=([0-9]+)"],
        }

        for key, key_patterns in patterns.items():
            for pattern in key_patterns:
                match = re.search(pattern, task)
                if not match:
                    continue
                raw = match.group(1).strip()
                if key == "n_results":
                    try:
                        context[key] = max(1, int(raw))
                    except Exception:
                        pass
                else:
                    context[key] = raw
                break

        return context

    def _extract_retrieval_count(self, tool_result: Any) -> Optional[int]:
        try:
            data = json.loads(str(tool_result))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        count = data.get("count")
        if isinstance(count, int):
            return count
        return None

    def _build_retrieval_retry_instruction(
        self,
        tool_name: str,
        tool_result: Any,
        retrieval_task_context: Dict[str, Any],
        retry_used: bool,
        retry_limit: int,
    ) -> Optional[str]:
        if retry_used or retry_limit <= 0:
            return None
        if tool_name not in {"chroma_query", "chroma_query_multi"}:
            return None

        count = self._extract_retrieval_count(tool_result)
        if count is None or count > 1:
            return None

        query = str(retrieval_task_context.get("query", "")).strip()
        user_message = str(retrieval_task_context.get("user_message", "")).strip() or '{"user_id":"web_user"}'
        persist_dir = str(retrieval_task_context.get("persist_dir", ".sharepoint_chroma")).strip()
        collection_name = str(retrieval_task_context.get("collection_name", "sharepoint_docs")).strip()
        n_results = int(retrieval_task_context.get("n_results", 5))

        expanded_results = min(12, max(6, n_results + 3))
        max_per_query = min(12, max(6, n_results + 2))

        return (
            "Retrieval evidence is too weak. Run one optimized retry now.\n"
            "1) Call query_optimizer with:\n"
            f"   - query='{query}'\n"
            f"   - user_message='{user_message}'\n"
            "   - max_variants=6\n"
            "2) Parse query_variants from query_optimizer output.\n"
            "3) Call chroma_query_multi with:\n"
            f"   - query='{query}'\n"
            f"   - user_message='{user_message}'\n"
            f"   - persist_dir='{persist_dir}'\n"
            f"   - collection_name='{collection_name}'\n"
            f"   - n_results={expanded_results}\n"
            f"   - max_per_query={max_per_query}\n"
            "   - query_variants=<variants from query_optimizer>\n"
            "4) Then continue with final answer grounded in retrieved evidence."
        )

    def __del__(self):
        """Cleanup on deletion."""
        if hasattr(self, "_connected") and self._connected:
            import asyncio

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.disconnect())
            finally:
                loop.close()
