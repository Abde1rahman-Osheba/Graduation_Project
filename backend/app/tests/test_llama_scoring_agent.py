"""Tests for the OpenRouter Llama scoring agent.

We never hit the real OpenRouter endpoint here. Instead we mock the
HTTP layer with `respx` (already pulled in via httpx) and exercise:

  * valid JSON response is parsed + validated
  * agent_score is auto-rebalanced when criteria don't sum to it
  * invalid JSON triggers a retry, then surfaces an error
  * the API key / Bearer token never leak into error messages
  * offline fallback works when no API key is configured
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from app.services.scoring.llama_scoring_agent import (
    AgentScoreError,
    AgentScoreResult,
    score_candidate_for_job,
)
from app.services.scoring.scoring_criteria import DEFAULT_CRITERIA


# ── Helper builders ──────────────────────────────────────────────────────


def _well_formed_response(agent_score: int = 80) -> dict[str, Any]:
    """Return an OpenRouter-shaped chat completion with a valid JSON body."""
    breakdown = {
        c.key: {"score": c.max_score, "max_score": c.max_score, "reason": "ok"}
        for c in DEFAULT_CRITERIA
    }
    # Force the criteria to sum to `agent_score` so validation passes
    breakdown[DEFAULT_CRITERIA[0].key]["score"] = max(
        0, agent_score - sum(c.max_score for c in DEFAULT_CRITERIA[1:])
    )
    body = {
        "agent_score": agent_score,
        "criteria_breakdown": breakdown,
        "matched_skills": ["Python", "FastAPI"],
        "missing_required_skills": [],
        "missing_preferred_skills": ["Docker"],
        "strengths": ["Strong backend background"],
        "weaknesses": ["Limited cloud exposure"],
        "recommendation": "strong_match",
        "explanation": "Looks like a great fit.",
        "confidence": 0.9,
    }
    return {
        "choices": [{"message": {"content": json.dumps(body)}}],
        "model": "meta-llama/llama-3.2-3b-instruct:free",
    }


def _build_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.MockTransport(handler), timeout=5,
    )


def _set_api_key(monkeypatch, key: str = "sk-test-key"):
    from app.services.scoring import llama_scoring_agent as svc
    monkeypatch.setattr(svc.settings, "openrouter_api_key", key, raising=False)


# ── Tests ──────────────────────────────────────────────────────────────


def test_parses_valid_response(monkeypatch):
    _set_api_key(monkeypatch)
    response_payload = _well_formed_response(agent_score=80)

    def handler(req: httpx.Request) -> httpx.Response:
        # The Authorization header must be present but never appear in errors
        assert req.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, json=response_payload)

    async def run():
        async with _build_client(handler) as client:
            return await score_candidate_for_job(
                anonymized_candidate={
                    "skills": [{"name": "python"}],
                    "years_of_experience": 5,
                },
                anonymized_job={
                    "required_skills": ["python"],
                    "preferred_skills": ["docker"],
                },
                client=client,
            )

    result = asyncio.run(run())
    assert isinstance(result, AgentScoreResult)
    assert result.agent_score == 80.0
    assert "Python" in result.matched_skills or "python" in result.matched_skills
    assert result.recommendation == "strong_match"
    assert 0.0 <= result.confidence <= 1.0


def test_invalid_json_triggers_retry_then_error(monkeypatch):
    _set_api_key(monkeypatch)

    call_count = {"n": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "not json at all"}}]},
        )

    async def run():
        async with _build_client(handler) as client:
            return await score_candidate_for_job(
                anonymized_candidate={"skills": []},
                anonymized_job={"required_skills": []},
                client=client,
            )

    result = asyncio.run(run())
    assert call_count["n"] == 2  # initial + 1 retry
    assert isinstance(result, AgentScoreError)
    assert result.error_type in {"InvalidAgentJSON", "InvalidAgentSchema"}


def test_offline_fallback_when_api_key_missing(monkeypatch):
    from app.services.scoring import llama_scoring_agent as svc

    monkeypatch.setattr(svc.settings, "openrouter_api_key", "", raising=False)
    monkeypatch.setattr(
        svc.settings, "scoring_allow_offline_fallback", True, raising=False,
    )

    async def run():
        return await score_candidate_for_job(
            anonymized_candidate={
                "skills": [{"name": "python"}, {"name": "fastapi"}],
                "years_of_experience": 4,
                "projects": [{"name": "Demo"}],
                "education": [{"institution": "X"}],
            },
            anonymized_job={
                "required_skills": ["python", "fastapi"],
                "preferred_skills": ["docker"],
                "min_years_experience": 3,
                "max_years_experience": 6,
                "workplace_type": "hybrid",
            },
        )

    result = asyncio.run(run())
    assert isinstance(result, AgentScoreResult)
    assert 0 <= result.agent_score <= 100
    assert result.model_name.startswith("offline-fallback")


def test_api_key_does_not_leak_into_error(monkeypatch):
    secret = "sk-very-secret-1234567890"
    _set_api_key(monkeypatch, key=secret)

    def handler(req: httpx.Request) -> httpx.Response:
        # Simulate an HTTP error that includes the bearer token in the URL
        raise httpx.HTTPError(f"oops Bearer {secret} could not connect")

    async def run():
        async with _build_client(handler) as client:
            return await score_candidate_for_job(
                anonymized_candidate={},
                anonymized_job={},
                client=client,
            )

    result = asyncio.run(run())
    assert isinstance(result, AgentScoreError)
    assert secret not in result.error_message
    assert "***" in result.error_message


def test_agent_score_is_rebalanced_to_match_criteria_sum(monkeypatch):
    _set_api_key(monkeypatch)

    # Body claims agent_score=100 but criteria sum to 60 → final value should be 60
    breakdown = {
        c.key: {"score": 10, "max_score": c.max_score, "reason": "x"}
        for c in DEFAULT_CRITERIA
    }
    body = {
        "agent_score": 100,
        "criteria_breakdown": breakdown,
        "matched_skills": [],
        "missing_required_skills": [],
        "missing_preferred_skills": [],
        "strengths": [],
        "weaknesses": [],
        "recommendation": "good_match",
        "explanation": "",
        "confidence": 0.7,
    }

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": json.dumps(body)}}]},
        )

    async def run():
        async with _build_client(handler) as client:
            return await score_candidate_for_job(
                anonymized_candidate={"skills": []},
                anonymized_job={"required_skills": []},
                client=client,
            )

    result = asyncio.run(run())
    assert isinstance(result, AgentScoreResult)
    assert result.agent_score == 60.0  # rebalanced to criteria sum
    expected_sum = sum(item["score"] for item in result.criteria_breakdown.values())
    assert expected_sum == 60
