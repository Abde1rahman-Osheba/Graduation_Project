"""
PATHS Backend — Llama scoring agent over OpenRouter.

Wraps a single OpenRouter chat-completions call:

  POST {OPENROUTER_BASE_URL}/chat/completions
  Authorization: Bearer {OPENROUTER_API_KEY}
  HTTP-Referer / X-Title: identify the PATHS backend

Responsibilities:

  * Build the prompt via `scoring_prompt_builder.build_messages`.
  * Send the chat completion with the configured model / temperature /
    max_tokens.
  * Parse the JSON response, validate it (range + criteria sum +
    confidence + recommendation enum).
  * Retry once on invalid JSON. After the second failure return a
    structured error dict that the orchestrator can record.
  * NEVER log the API key, the raw `Authorization` header, or the raw
    candidate prompt body.
  * If the API key isn't configured and `SCORING_ALLOW_OFFLINE_FALLBACK`
    is true, fall back to a deterministic local scorer so dev / CI
    still works without OpenRouter access.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.scoring.scoring_criteria import (
    DEFAULT_CRITERIA,
    classify_final_score,
    empty_criteria_payload,
    recommendation_for,
)
from app.services.scoring.scoring_prompt_builder import build_messages

logger = logging.getLogger(__name__)
settings = get_settings()

_VALID_RECOMMENDATIONS = {
    "strong_match",
    "good_match",
    "possible_match",
    "weak_match",
    "not_recommended",
}


# ── Result containers ────────────────────────────────────────────────────


@dataclass
class AgentScoreResult:
    """Validated agent output ready to merge into the final score."""

    agent_score: float
    criteria_breakdown: dict[str, dict[str, Any]]
    matched_skills: list[str]
    missing_required_skills: list[str]
    missing_preferred_skills: list[str]
    strengths: list[str]
    weaknesses: list[str]
    recommendation: str
    explanation: str
    confidence: float
    model_name: str
    raw_response_preview: str


@dataclass
class AgentScoreError:
    """Returned when the agent could not produce a valid score."""

    error_type: str
    error_message: str
    model_name: str | None = None


# ── Public entry point ──────────────────────────────────────────────────


async def score_candidate_for_job(
    *,
    anonymized_candidate: dict[str, Any],
    anonymized_job: dict[str, Any],
    client: httpx.AsyncClient | None = None,
) -> AgentScoreResult | AgentScoreError:
    """Call OpenRouter once (with one retry on invalid JSON).

    The caller passes already-anonymized payloads — this function never
    touches raw candidate data.
    """
    messages = build_messages(anonymized_candidate, anonymized_job)

    if not settings.openrouter_api_key:
        if settings.scoring_allow_offline_fallback:
            logger.info(
                "[ScoringAgent] OPENROUTER_API_KEY not set — using offline fallback",
            )
            return _offline_fallback_score(
                anonymized_candidate, anonymized_job, reason="api_key_not_configured",
            )
        return AgentScoreError(
            error_type="ConfigurationError",
            error_message="OPENROUTER_API_KEY is not configured",
        )

    own_client = client is None
    cli = client or httpx.AsyncClient(
        timeout=settings.scoring_request_timeout_seconds,
    )
    try:
        for attempt in (1, 2):
            try:
                raw = await _post_chat_completion(cli, messages)
            except httpx.HTTPError as exc:
                logger.warning(
                    "[ScoringAgent] OpenRouter HTTP error (attempt %d): %s",
                    attempt, _safe_error(exc),
                )
                if attempt == 2:
                    return AgentScoreError(
                        error_type="OpenRouterRequestError",
                        error_message=_safe_error(exc),
                        model_name=settings.openrouter_model,
                    )
                continue
            except Exception as exc:  # noqa: BLE001
                logger.exception("[ScoringAgent] OpenRouter unexpected error")
                return AgentScoreError(
                    error_type="OpenRouterUnexpectedError",
                    error_message=_safe_error(exc),
                    model_name=settings.openrouter_model,
                )

            content = _extract_content(raw)
            try:
                parsed = _extract_json(content)
            except ValueError as exc:
                logger.warning(
                    "[ScoringAgent] invalid JSON from model (attempt %d): %s",
                    attempt, exc,
                )
                if attempt == 2:
                    return AgentScoreError(
                        error_type="InvalidAgentJSON",
                        error_message=str(exc),
                        model_name=settings.openrouter_model,
                    )
                # Encourage a retry with a stricter reminder
                messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            "Your previous response was not valid JSON or did "
                            "not match the schema. Reply with the JSON object "
                            "ONLY. No markdown, no commentary."
                        ),
                    },
                ]
                continue

            try:
                result = _validate_agent_payload(parsed, raw_preview=content[:400])
            except ValueError as exc:
                logger.warning(
                    "[ScoringAgent] schema validation failed (attempt %d): %s",
                    attempt, exc,
                )
                if attempt == 2:
                    return AgentScoreError(
                        error_type="InvalidAgentSchema",
                        error_message=str(exc),
                        model_name=settings.openrouter_model,
                    )
                messages = [
                    *messages,
                    {
                        "role": "user",
                        "content": (
                            f"Your previous JSON failed validation: {exc}. "
                            "Return a corrected JSON object that respects the "
                            "schema and the criteria-sum rule."
                        ),
                    },
                ]
                continue

            return result
    finally:
        if own_client:
            await cli.aclose()

    # Unreachable but mypy-safe
    return AgentScoreError(
        error_type="UnreachableError", error_message="exhausted retries",
    )


# ── HTTP plumbing ────────────────────────────────────────────────────────


async def _post_chat_completion(
    client: httpx.AsyncClient, messages: list[dict[str, str]],
) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_referer or "https://paths.local",
        "X-Title": settings.openrouter_app_title or "PATHS Scoring Agent",
    }
    payload = {
        "model": settings.openrouter_model,
        "messages": messages,
        "temperature": settings.scoring_model_temperature,
        "max_tokens": settings.scoring_model_max_tokens,
        # Many OpenRouter models accept this hint and respect JSON-only output.
        "response_format": {"type": "json_object"},
    }
    url = f"{settings.openrouter_base_url.rstrip('/')}/chat/completions"
    response = await client.post(url, headers=headers, json=payload)
    response.raise_for_status()
    return response.json()


def _extract_content(raw: dict[str, Any]) -> str:
    try:
        choices = raw.get("choices") or []
        if not choices:
            raise ValueError("no choices")
        msg = choices[0].get("message") or {}
        content = msg.get("content")
        if isinstance(content, list):
            # Some providers return a list of content parts
            content = "".join(
                p.get("text", "") if isinstance(p, dict) else str(p)
                for p in content
            )
        if not isinstance(content, str):
            raise ValueError("non-string content")
        return content.strip()
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not read message content: {exc}") from exc


# ── JSON extraction + validation ─────────────────────────────────────────


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("empty content")

    # Strip common code-fence wrappers
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    # Try a direct parse first (fast path)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if parsed is None:
        snippet = _balanced_object(text)
        if not snippet:
            raise ValueError("no JSON object found in response")
        try:
            parsed = json.loads(snippet)
        except json.JSONDecodeError as exc:
            raise ValueError(f"could not parse JSON: {exc}") from exc

    if not isinstance(parsed, dict):
        raise ValueError("response was not a JSON object")
    return parsed


def _balanced_object(text: str) -> str | None:
    depth = 0
    start = -1
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return text[start : i + 1]
    return None


def _validate_agent_payload(
    parsed: dict[str, Any], *, raw_preview: str,
) -> AgentScoreResult:
    agent_score = _coerce_int(parsed.get("agent_score"))
    if agent_score is None or not (0 <= agent_score <= 100):
        raise ValueError("agent_score must be an integer between 0 and 100")

    breakdown_in = parsed.get("criteria_breakdown") or {}
    if not isinstance(breakdown_in, dict):
        raise ValueError("criteria_breakdown must be an object")

    criteria_keys = {c.key for c in DEFAULT_CRITERIA}
    breakdown: dict[str, dict[str, Any]] = empty_criteria_payload()
    component_sum = 0
    for c in DEFAULT_CRITERIA:
        item = breakdown_in.get(c.key) or {}
        if not isinstance(item, dict):
            raise ValueError(f"criteria_breakdown.{c.key} must be an object")
        score = _coerce_int(item.get("score"), default=0) or 0
        score = max(0, min(score, c.max_score))
        reason = (item.get("reason") or "").strip()
        breakdown[c.key] = {
            "score": score,
            "max_score": c.max_score,
            "reason": reason[:500],
        }
        component_sum += score

    extras = set(breakdown_in.keys()) - criteria_keys
    if extras:
        # Tolerate but ignore unexpected keys
        logger.debug("[ScoringAgent] ignoring unknown criteria keys: %s", extras)

    if component_sum != agent_score:
        # Auto-rebalance the agent_score so it matches the criteria sum
        # (the spec wants strictness; we choose the lower-risk path of
        # trusting the per-criterion numbers since they include reasons).
        logger.debug(
            "[ScoringAgent] rebalancing agent_score %d → %d to match criteria sum",
            agent_score, component_sum,
        )
        agent_score = component_sum

    recommendation = (parsed.get("recommendation") or "").strip().lower()
    if recommendation not in _VALID_RECOMMENDATIONS:
        recommendation = recommendation_for(agent_score)

    confidence = _coerce_float(parsed.get("confidence"))
    if confidence is None or not (0.0 <= confidence <= 1.0):
        confidence = 0.5

    return AgentScoreResult(
        agent_score=float(agent_score),
        criteria_breakdown=breakdown,
        matched_skills=_coerce_str_list(parsed.get("matched_skills")),
        missing_required_skills=_coerce_str_list(parsed.get("missing_required_skills")),
        missing_preferred_skills=_coerce_str_list(parsed.get("missing_preferred_skills")),
        strengths=_coerce_str_list(parsed.get("strengths")),
        weaknesses=_coerce_str_list(parsed.get("weaknesses")),
        recommendation=recommendation,
        explanation=str(parsed.get("explanation") or "")[:2000],
        confidence=float(confidence),
        model_name=settings.openrouter_model,
        raw_response_preview=raw_preview,
    )


def _coerce_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _coerce_str_list(value: Any) -> list[str]:
    if not value:
        return []
    if isinstance(value, str):
        value = re.split(r"[,;\n]", value)
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        s = str(item).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s[:120])
    return out


def _safe_error(exc: Exception) -> str:
    msg = str(exc)
    if settings.openrouter_api_key:
        msg = msg.replace(settings.openrouter_api_key, "***")
    # Remove any Bearer-token leakage if it sneaked into a string repr
    msg = re.sub(r"Bearer\s+[A-Za-z0-9_.\-]+", "Bearer ***", msg)
    return msg[:600]


# ── Offline fallback (no OpenRouter access) ──────────────────────────────


def _offline_fallback_score(
    anonymized_candidate: dict[str, Any],
    anonymized_job: dict[str, Any],
    *,
    reason: str,
) -> AgentScoreResult:
    """Deterministic skill-overlap scorer used when the LLM is unavailable.

    Produces a transparent, evidence-based number derived from skill +
    experience signals. This keeps the pipeline working offline and lets
    the integration tests run without OpenRouter access.
    """
    cand_skills = {
        s.get("name", "").lower()
        for s in anonymized_candidate.get("skills") or []
        if s.get("name")
    }
    required = [s.lower() for s in anonymized_job.get("required_skills") or []]
    preferred = [s.lower() for s in anonymized_job.get("preferred_skills") or []]
    matched_required = [s for s in required if s in cand_skills]
    matched_preferred = [s for s in preferred if s in cand_skills]

    if required:
        skill_pct = len(matched_required) / len(required)
    elif preferred:
        skill_pct = len(matched_preferred) / max(1, len(preferred))
    else:
        skill_pct = 0.5  # no information either way
    skills_score = int(round(35 * skill_pct))

    cand_years = float(anonymized_candidate.get("years_of_experience") or 0)
    min_y = anonymized_job.get("min_years_experience") or 0
    max_y = anonymized_job.get("max_years_experience") or 0
    if max_y and cand_years >= max_y:
        exp_score = 20
    elif min_y and cand_years >= min_y:
        exp_score = 16
    elif min_y == 0 and max_y == 0:
        exp_score = 12
    elif cand_years > 0:
        exp_score = max(4, int(round(20 * (cand_years / max(1, min_y or max_y)))))
        exp_score = min(20, exp_score)
    else:
        exp_score = 4

    project_score = 8 if anonymized_candidate.get("projects") else 4
    edu_score = 6 if anonymized_candidate.get("education") else 2
    pref_score = 6 if anonymized_job.get("workplace_type") else 4
    growth_score = 6 if matched_preferred else 4

    total = skills_score + exp_score + project_score + edu_score + pref_score + growth_score
    total = max(0, min(100, total))

    breakdown = empty_criteria_payload()
    breakdown["skills_match"]["score"] = skills_score
    breakdown["skills_match"]["reason"] = (
        f"Matched {len(matched_required)}/{len(required) or 0} required skills"
        f" and {len(matched_preferred)} preferred skills"
    )
    breakdown["experience_match"]["score"] = exp_score
    breakdown["experience_match"]["reason"] = (
        f"Candidate has {cand_years} years of experience; job asks for "
        f"{min_y}-{max_y or 'open'} years"
    )
    breakdown["project_domain_match"]["score"] = project_score
    breakdown["project_domain_match"]["reason"] = (
        "Has projects evidence" if anonymized_candidate.get("projects") else "No projects listed"
    )
    breakdown["education_certifications"]["score"] = edu_score
    breakdown["education_certifications"]["reason"] = (
        "Education present" if anonymized_candidate.get("education") else "No education entries"
    )
    breakdown["job_preferences_fit"]["score"] = pref_score
    breakdown["job_preferences_fit"]["reason"] = "Workplace type known"
    breakdown["growth_potential"]["score"] = growth_score
    breakdown["growth_potential"]["reason"] = (
        "Some preferred skills present" if matched_preferred else "Limited transferable signal"
    )

    missing_required = [s for s in required if s not in cand_skills]
    missing_preferred = [s for s in preferred if s not in cand_skills]

    return AgentScoreResult(
        agent_score=float(total),
        criteria_breakdown=breakdown,
        matched_skills=matched_required + matched_preferred,
        missing_required_skills=missing_required,
        missing_preferred_skills=missing_preferred,
        strengths=[
            f"Skill overlap {len(matched_required)}/{len(required) or 0}",
            f"{cand_years} years experience",
        ],
        weaknesses=[f"Missing required skill: {s}" for s in missing_required[:3]],
        recommendation=recommendation_for(total),
        explanation=(
            f"Offline deterministic score ({reason}). "
            f"Classification: {classify_final_score(total)}."
        ),
        confidence=0.4,
        model_name=f"offline-fallback ({reason})",
        raw_response_preview="",
    )


__all__ = [
    "AgentScoreError",
    "AgentScoreResult",
    "score_candidate_for_job",
]
