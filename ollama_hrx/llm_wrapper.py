import os
from typing import List, Dict, Any, Optional

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

LITELLM_BASE_URL = os.getenv("LITELLM_BASE_URL", "http://0.0.0.0:4000")
LITELLM_API_KEY = os.getenv("LITELLM_API_KEY", "dummy-key")
DEFAULT_MODEL = os.getenv("LITELLM_MODEL", "oai-gpt-4.1-nano")

_client: Optional[OpenAI] = None


def get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=LITELLM_API_KEY, base_url=LITELLM_BASE_URL)
    return _client


def chat_completion(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.1,
):
    client = get_client()
    return client.chat.completions.create(
        model=model or DEFAULT_MODEL,
        messages=messages,
        temperature=temperature,
    )


def chat_completion_text(
    messages: List[Dict[str, Any]],
    model: Optional[str] = None,
    temperature: float = 0.1,
) -> str:
    resp = chat_completion(messages=messages, model=model, temperature=temperature)
    return resp.choices[0].message.content or ""
