"""Organization matching: URL safety and scoring weight helper."""

from __future__ import annotations

from app.services.scoring.scoring_service import combine_scores
from app.services.organization_matching.organization_csv_candidate_import_service import (
    is_safe_http_url_for_cv,
)


def test_ssrf_rejects_non_http() -> None:
    ok, _ = is_safe_http_url_for_cv("file:///etc/passwd")
    assert ok is False


def test_ssrf_allows_https_public() -> None:
    ok, _ = is_safe_http_url_for_cv("https://example.com/cv.pdf")
    assert ok is True


def test_combine_scores_uses_custom_weights() -> None:
    f = combine_scores(80, 90, agent_weight=0.65, vector_weight=0.35)
    assert abs(f - 83.5) < 0.01
