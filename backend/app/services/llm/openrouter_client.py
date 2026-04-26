"""
OpenRouter client for structured JSON (Decision Support, development plans, emails).

Never logs API keys. Retries once on invalid JSON with a repair hint.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.scoring.llama_scoring_agent import _balanced_object

logger = logging.getLogger(__name__)
settings = get_settings()


class OpenRouterClientError(RuntimeError):
    """OpenRouter request failed or returned unusable data."""


def _redact(s: str) -> str:
    if settings.openrouter_api_key:
        s = s.replace(settings.openrouter_api_key, "***")
    return s[:800]


def _parse_json_object(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\s*", "", t)
        t = re.sub(r"\s*```$", "", t)
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        snip = _balanced_object(t)
        if not snip:
            raise OpenRouterClientError("response did not contain a JSON object")
        out = json.loads(snip)
    if not isinstance(out, dict):
        raise OpenRouterClientError("JSON root must be an object")
    return out


def _chat(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    temperature: float,
    max_tokens: int,
) -> str:
    if not settings.openrouter_api_key:
        raise OpenRouterClientError("OPENROUTER_API_KEY is not configured")
    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_referer or "https://paths.local",
        "X-Title": settings.openrouter_app_title or "PATHS",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    to = max(5.0, float(settings.dss_openrouter_timeout_seconds or 120.0))
    with httpx.Client(timeout=to) as client:
        r = client.post(url, headers=headers, json=body)
    if r.status_code >= 400:
        raise OpenRouterClientError(_redact(f"openrouter {r.status_code}: {r.text}"))
    data = r.json()
    ch = (data.get("choices") or [{}])[0]
    msg = ch.get("message") or {}
    content = msg.get("content")
    if isinstance(content, list):
        content = "".join(
            p.get("text", "") if isinstance(p, dict) else str(p) for p in content
        )
    if not isinstance(content, str):
        raise OpenRouterClientError("empty or non-text content in response")
    return content.strip()


def generate_json_response(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.2,
    max_tokens: int = 4000,
) -> dict[str, Any]:
    """
    Returns a dict from model JSON. Retries once if JSON parse fails.
    """
    m = model or settings.openrouter_dss_model
    last_err: str | None = None
    for attempt in range(2):
        up = user_prompt
        if attempt == 1:
            up = (
                user_prompt
                + "\n\nYour previous output was not valid JSON. "
                "Reply with ONLY a single valid JSON object, no markdown."
            )
        try:
            raw = _chat(system_prompt, up, model=m, temperature=temperature, max_tokens=max_tokens)
            return _parse_json_object(raw)
        except OpenRouterClientError:
            raise
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            last_err = str(exc)
            logger.warning("DSS JSON parse attempt %s failed: %s", attempt, last_err)
            if attempt == 1:
                raise OpenRouterClientError(last_err) from exc
    raise OpenRouterClientError(last_err or "invalid JSON")
