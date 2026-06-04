from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import OpenAI, OpenAIError

log = logging.getLogger(__name__)


@dataclass
class CompletionResult:
    text: str
    model: str
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class VeniceClient:
    """Thin wrapper around the OpenAI SDK pointed at any OpenAI-compatible endpoint.

    Default base URL is Venice, but anything that speaks /chat/completions works:
    Together, OpenRouter, a self-hosted vLLM, etc.
    """

    def __init__(self, base_url: str, api_key: str, default_model: str):
        if not api_key:
            raise ValueError(
                "No API key. Set VENICE_API_KEY (or whichever provider) before starting."
            )
        self._client = OpenAI(base_url=base_url, api_key=api_key)
        self._default_model = default_model

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.7,
    ) -> CompletionResult:
        chosen = model or self._default_model
        resp = self._client.chat.completions.create(
            model=chosen,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        usage = resp.usage
        return CompletionResult(
            text=text,
            model=chosen,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        )

    def list_models(self) -> list[str]:
        try:
            models = self._client.models.list()
            return sorted(m.id for m in models.data)
        except OpenAIError as exc:
            log.warning("model list failed: %s", exc)
            return []
