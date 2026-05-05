from app.config import settings
from litellm import completion

try:
    resp = completion(
        model=settings.litellm_model,
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        custom_llm_provider="openai",
        temperature=0,
        response_format={"type": "json_object"},
        messages=[{"role": "user", "content": "Return JSON object: {\"ok\": true}"}],
    )
    print("OK:", resp.choices[0].message.content)
except Exception as e:
    print("ERROR:", type(e).__name__, str(e))
