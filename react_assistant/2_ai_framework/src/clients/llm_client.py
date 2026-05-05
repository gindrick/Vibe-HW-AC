import os
from typing import List, Dict, Any, Optional, AsyncGenerator, Type, TypeVar
import logging
from urllib.parse import urlparse, urlunparse
from openai import AsyncOpenAI
import instructor
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """LiteLLM proxy client - supports multiple LLM providers through a unified API"""

    def __init__(
        self,
        llm_model: str = "ollama-mistral",
    ):
        raw_base_url = os.getenv("LITELLM_BASE_URL", "http://localhost:4000")
        self.base_url = self._normalize_base_url(raw_base_url)
        self.api_key = os.getenv("LITELLM_API_KEY", "dummy-key")

        self.llm_model = llm_model

        # self.client = None
        self._initialize_client()

    @staticmethod
    def _normalize_base_url(base_url: str) -> str:
        """Use localhost instead of wildcard bind address for outbound client calls."""
        parsed = urlparse(base_url)
        if parsed.hostname != "0.0.0.0":
            return base_url

        netloc = parsed.netloc.replace("0.0.0.0", "localhost", 1)
        return urlunparse(parsed._replace(netloc=netloc))

    def _initialize_client(self):
        """Initialize the LiteLLM client using OpenAI SDK"""
        try:
            self.client = AsyncOpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
            )

            # Also create an instructor client for structured outputs
            self.instructor_client = instructor.from_openai(
                self.client, mode=instructor.Mode.JSON
            )

            logger.info(f"✅ LiteLLM client initialized with base URL: {self.base_url}")
        except Exception as e:
            logger.error(f"❌ Failed to initialize LiteLLM client: {e}")
            raise

    async def call(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ):
        """Generate chat response using LiteLLM proxy"""
        try:
            if tools:
                response = await self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                    tools=tools,
                    tool_choice="auto",
                )
            else:
                response = await self.client.chat.completions.create(
                    model=self.llm_model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=False,
                )

            # response = litellm.completion(
            #     api_base=self.base_url,
            #     api_key=self.api_key,
            #     model=f"litellm_proxy/{self.llm_model}",
            #     messages=messages,
            #     temperature=temperature,
            #     max_tokens=max_tokens,
            #     stream=False,
            #     tools=tools,
            #     tool_choice="auto",
            # )

            # Just return the OpenAI response as-is
            return response

        except Exception as e:
            logger.error(f"❌ LiteLLM chat error: {e}")
            raise

    async def call_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        temperature: float = 0.1,
        max_tokens: Optional[int] = None,
        max_retries: int = 3,
    ) -> T:
        """Generate structured response using Instructor"""
        try:
            response = await self.instructor_client.chat.completions.create(
                model=self.llm_model,
                messages=messages,
                response_model=response_model,
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=max_retries,
            )

            return response

        except Exception as e:
            logger.error(f"❌ Instructor structured output error: {e}")
            raise
