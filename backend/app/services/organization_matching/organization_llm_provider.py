"""
PATHS Backend — LLM provider abstraction (OpenRouter | Ollama).

Used by the organization-side ranking, outreach, and streaming services
so they can swap between OpenRouter (default) and a local Ollama server
based on `LLM_PROVIDER` without changing the call sites.

Public interface:

    class LLMProvider:
        async def generate_text(messages, *, temperature=None, max_tokens=None) -> str
        async def generate_json(messages, *, temperature=None, max_tokens=None) -> dict
        async def stream_text(messages, *, temperature=None, max_tokens=None) -> AsyncIterator[str]

Both providers share the same chat-message shape:

    [
      {"role": "system", "content": "..."},
      {"role": "user",   "content": "..."},
      ...
    ]

Errors are raised as `LLMProviderError` with a redacted message — the
API key is never exposed in error text.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from typing import AsyncIterator, Iterable

import httpx

from app.core.config import get_settings
from app.services.scoring.llama_scoring_agent import _balanced_object

logger = logging.getLogger(__name__)
settings = get_settings()


class LLMProviderError(RuntimeError):
    """Raised when the LLM provider cannot complete a request."""


def _safe_error(exc: Exception) -> str:
    msg = str(exc)
    if settings.openrouter_api_key:
        msg = msg.replace(settings.openrouter_api_key, "***")
    msg = re.sub(r"Bearer\s+[A-Za-z0-9_.\-]+", "Bearer ***", msg)
    return msg[:600]


# ── Base interface ──────────────────────────────────────────────────────


class LLMProvider(ABC):
    """Abstract LLM provider used by the organization-matching workflow."""

    name: str = "base"

    @abstractmethod
    async def generate_text(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        ...

    async def generate_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        """Default implementation: ask for plain text + extract JSON object."""
        text = await self.generate_text(
            messages, temperature=temperature, max_tokens=max_tokens,
        )
        return _extract_json(text)


# ── OpenRouter ───────────────────────────────────────────────────────────


class OpenRouterProvider(LLMProvider):
    """OpenRouter chat-completions client (default provider)."""

    name = "openrouter"

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model or settings.openrouter_model

    @staticmethod
    def _headers() -> dict[str, str]:
        if not settings.openrouter_api_key:
            raise LLMProviderError("OPENROUTER_API_KEY is not configured")
        return {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": settings.openrouter_referer or "https://paths.local",
            "X-Title": settings.openrouter_app_title or "PATHS Scoring Agent",
        }

    def _payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None,
        max_tokens: int | None,
        stream: bool = False,
        json_mode: bool = False,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": (
                settings.llm_temperature if temperature is None else float(temperature)
            ),
            "max_tokens": (
                settings.llm_max_tokens if max_tokens is None else int(max_tokens)
            ),
            "stream": stream,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        return payload

    @property
    def _url(self) -> str:
        return f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        async with httpx.AsyncClient(
            timeout=settings.scoring_request_timeout_seconds,
        ) as client:
            try:
                resp = await client.post(
                    self._url,
                    headers=self._headers(),
                    json=self._payload(messages, temperature=temperature, max_tokens=max_tokens),
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMProviderError(_safe_error(exc)) from exc
        return _extract_message_content(resp.json())

    async def generate_json(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict:
        async with httpx.AsyncClient(
            timeout=settings.scoring_request_timeout_seconds,
        ) as client:
            try:
                resp = await client.post(
                    self._url,
                    headers=self._headers(),
                    json=self._payload(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        json_mode=True,
                    ),
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMProviderError(_safe_error(exc)) from exc
        return _extract_json(_extract_message_content(resp.json()))

    async def stream_text(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        async for chunk in self._stream_text(messages, temperature, max_tokens):
            yield chunk

    async def _stream_text(
        self,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int | None,
    ):
        async with httpx.AsyncClient(
            timeout=settings.scoring_request_timeout_seconds,
        ) as client:
            try:
                async with client.stream(
                    "POST",
                    self._url,
                    headers=self._headers(),
                    json=self._payload(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                    ),
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode(errors="replace")[:500]
                        raise LLMProviderError(
                            _safe_error(RuntimeError(f"OpenRouter {resp.status_code}: {body}"))
                        )
                    async for line in resp.aiter_lines():
                        chunk = _parse_sse_chunk(line)
                        if chunk is not None:
                            yield chunk
            except httpx.HTTPError as exc:
                raise LLMProviderError(_safe_error(exc)) from exc


# ── Ollama ───────────────────────────────────────────────────────────────


class OllamaProvider(LLMProvider):
    """Local Ollama chat client (`/api/chat` endpoint)."""

    name = "ollama"

    def __init__(self, *, model: str | None = None) -> None:
        self.model = model or settings.ollama_model

    @property
    def _url(self) -> str:
        return f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    def _payload(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None,
        max_tokens: int | None,
        stream: bool,
    ) -> dict:
        return {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": (
                    settings.llm_temperature if temperature is None else float(temperature)
                ),
                "num_predict": (
                    settings.llm_max_tokens if max_tokens is None else int(max_tokens)
                ),
            },
        }

    async def generate_text(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        async with httpx.AsyncClient(
            timeout=settings.scoring_request_timeout_seconds,
        ) as client:
            try:
                resp = await client.post(
                    self._url,
                    json=self._payload(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=False,
                    ),
                )
                resp.raise_for_status()
            except httpx.HTTPError as exc:
                raise LLMProviderError(_safe_error(exc)) from exc
        body = resp.json()
        msg = body.get("message") or {}
        return str(msg.get("content") or "").strip()

    async def stream_text(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        async for chunk in self._stream_text(messages, temperature, max_tokens):
            yield chunk

    async def _stream_text(
        self,
        messages: list[dict[str, str]],
        temperature: float | None,
        max_tokens: int | None,
    ):
        async with httpx.AsyncClient(
            timeout=settings.scoring_request_timeout_seconds,
        ) as client:
            try:
                async with client.stream(
                    "POST",
                    self._url,
                    json=self._payload(
                        messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        stream=True,
                    ),
                ) as resp:
                    if resp.status_code >= 400:
                        body = (await resp.aread()).decode(errors="replace")[:500]
                        raise LLMProviderError(f"Ollama {resp.status_code}: {body}")
                    async for line in resp.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError:
                            continue
                        msg = obj.get("message") or {}
                        chunk = msg.get("content")
                        if chunk:
                            yield chunk
                        if obj.get("done"):
                            break
            except httpx.HTTPError as exc:
                raise LLMProviderError(_safe_error(exc)) from exc


# ── Provider factory ────────────────────────────────────────────────────


def get_provider(name: str | None = None) -> LLMProvider:
    """Return the configured LLM provider instance.

    Falls back to Ollama if `LLM_ALLOW_FALLBACK_TO_OLLAMA=true` and the
    OpenRouter API key is missing.
    """
    chosen = (name or settings.llm_provider or "openrouter").strip().lower()
    if chosen == "openrouter":
        if not settings.openrouter_api_key and settings.llm_allow_fallback_to_ollama:
            logger.warning(
                "[LLMProvider] OPENROUTER_API_KEY missing — falling back to Ollama",
            )
            return OllamaProvider()
        return OpenRouterProvider()
    if chosen == "ollama":
        return OllamaProvider()
    raise LLMProviderError(f"unknown LLM provider: {chosen!r}")


# ── Helpers ──────────────────────────────────────────────────────────────


def _extract_message_content(body: dict) -> str:
    choices = body.get("choices") or []
    if not choices:
        raise LLMProviderError("no choices in response")
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p)
            for p in content
        )
    if not isinstance(content, str):
        raise LLMProviderError("non-string content in response")
    return content.strip()


def _extract_json(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        raise LLMProviderError("empty response")
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        snippet = _balanced_object(text)
        if not snippet:
            raise LLMProviderError("response did not contain a JSON object")
        try:
            parsed = json.loads(snippet)
        except json.JSONDecodeError as exc:
            raise LLMProviderError(f"invalid JSON: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LLMProviderError("JSON response was not an object")
    return parsed


def _parse_sse_chunk(line: str) -> str | None:
    """Parse a single SSE line from OpenRouter chat-completions stream."""
    line = (line or "").strip()
    if not line.startswith("data:"):
        return None
    payload = line[len("data:") :].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        obj = json.loads(payload)
    except json.JSONDecodeError:
        return None
    choices = obj.get("choices") or []
    if not choices:
        return None
    delta = choices[0].get("delta") or {}
    chunk = delta.get("content")
    return chunk if isinstance(chunk, str) and chunk else None


__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "OpenRouterProvider",
    "OllamaProvider",
    "get_provider",
]
