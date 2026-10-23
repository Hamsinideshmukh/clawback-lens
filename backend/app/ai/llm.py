"""Optional LLM client for any OpenAI-compatible chat-completions endpoint
(Hugging Face router, Groq, Gemini, a local Ollama...). The system never
depends on it: every caller has a local-model or deterministic fallback, and
the LLM never produces a verdict."""

import json
import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.metrics import LLM_REQUESTS

logger = logging.getLogger(__name__)


class LLMUnavailable(Exception):
    """Not configured, or the call failed. Callers fall back; they never guess."""


def chat(
    messages: list[dict[str, Any]],
    *,
    purpose: str,
    tools: list[dict[str, Any]] | None = None,
    json_mode: bool = False,
) -> dict[str, Any]:
    """Returns the assistant message ({"content": ..., "tool_calls": [...]})."""
    settings = get_settings()
    if not settings.llm_enabled:
        raise LLMUnavailable("LLM_API_KEY not configured")

    body: dict[str, Any] = {"model": settings.llm_model, "messages": messages, "temperature": 0}
    if tools:
        body["tools"] = tools
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    try:
        response = httpx.post(
            f"{settings.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {settings.llm_api_key}"},
            json=body,
            timeout=settings.llm_timeout_seconds,
        )
        response.raise_for_status()
        message: dict[str, Any] = response.json()["choices"][0]["message"]
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        LLM_REQUESTS.labels(purpose, "error").inc()
        logger.warning("llm call failed", exc_info=exc)
        raise LLMUnavailable(f"LLM call failed: {exc}") from exc

    LLM_REQUESTS.labels(purpose, "ok").inc()
    return message


def parse_json(content: str | None) -> dict[str, Any]:
    """Tolerates markdown fences some models add despite JSON mode."""
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.strip("`").removeprefix("json").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMUnavailable("LLM returned invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise LLMUnavailable("LLM returned non-object JSON")
    return parsed
