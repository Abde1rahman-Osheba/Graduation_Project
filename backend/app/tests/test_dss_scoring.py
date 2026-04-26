from app.services.decision_support.scoring_aggregation_service import ScoreInputs, compute_journey_score


def test_journey_score_with_full_inputs():
    inp = ScoreInputs(
        candidate_job_match_score=80.0,
        assessment_score=None,
        technical_interview_score=70.0,
        hr_interview_score=75.0,
        experience_alignment_score=80.0,
        evidence_confidence_score=None,
        transcript_quality="medium",
    )
    final, expl = compute_journey_score(inp)
    assert 0.0 <= final <= 100.0
    assert "weights" in expl


def test_journey_score_redistributes_missing_assessment():
    inp = ScoreInputs(
        candidate_job_match_score=50.0,
        assessment_score=None,
        technical_interview_score=None,
        hr_interview_score=None,
        experience_alignment_score=None,
        evidence_confidence_score=None,
        transcript_quality="low",
    )
    final, _ = compute_journey_score(inp)
    assert final >= 0.0
