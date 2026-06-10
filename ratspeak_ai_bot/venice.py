from __future__ import annotations

import logging
from dataclasses import dataclass

from openai import AuthenticationError, OpenAI, OpenAIError, PermissionDeniedError

log = logging.getLogger(__name__)


class InferenceAuthError(Exception):
    """Raised when the provider rejects the credential (401/403)."""


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
        self._base_url = base_url
        # BYOK-only deployments may run without a shared key. We still need the
        # client object for things like list_models / validate_key, so pass a
        # placeholder; any call that tries to actually use it will 401.
        self._client = OpenAI(base_url=base_url, api_key=api_key or "byok-only")
        self._has_shared_key = bool(api_key)
        self._default_model = default_model

    @property
    def has_shared_key(self) -> bool:
        return self._has_shared_key

    @property
    def base_url(self) -> str:
        return self._base_url

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        max_tokens: int = 800,
        temperature: float = 0.7,
        api_key: str | None = None,
    ) -> CompletionResult:
        chosen = model or self._default_model
        client = (
            OpenAI(base_url=self._base_url, api_key=api_key) if api_key else self._client
        )
        try:
            resp = client.chat.completions.create(
                model=chosen,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        except (AuthenticationError, PermissionDeniedError) as exc:
            raise InferenceAuthError(str(exc)) from exc
        choice = resp.choices[0]
        text = (choice.message.content or "").strip()
        usage = resp.usage
        return CompletionResult(
            text=text,
            model=chosen,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) if usage else 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) if usage else 0,
        )

    def validate_key(self, api_key: str) -> tuple[bool, str]:
        """Tiny ping to confirm the key works. Returns (ok, message)."""
        client = OpenAI(base_url=self._base_url, api_key=api_key)
        try:
            client.chat.completions.create(
                model=self._default_model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
                temperature=0,
            )
            return True, "ok"
        except (AuthenticationError, PermissionDeniedError) as exc:
            return False, f"rejected: {exc}"
        except OpenAIError as exc:
            return False, f"provider error: {exc}"

    def list_models(self) -> list[str]:
        try:
            models = self._client.models.list()
            return sorted(m.id for m in models.data)
        except OpenAIError as exc:
            log.warning("model list failed: %s", exc)
            return []
