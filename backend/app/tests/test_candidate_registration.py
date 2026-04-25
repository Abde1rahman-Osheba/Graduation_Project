"""
PATHS Backend — Candidate registration tests.
"""

from fastapi.testclient import TestClient


def test_register_candidate_success(client: TestClient):
    data = {
        "full_name": "John Doe",
        "email": "johndoe@test.com",
        "password": "SecurePassword1!",
        "location": "New York, NY",
        "headline": "Senior Software Engineer"
    }

    resp = client.post("/api/v1/auth/register/candidate", json=data)
    assert resp.status_code == 201

    resp_data = resp.json()
    assert "user_id" in resp_data
    assert "candidate_profile_id" in resp_data
    assert resp_data["account_type"] == "candidate"


def test_register_candidate_duplicate_email(client: TestClient):
    data = {
        "full_name": "Jane Doe",
        "email": "janedoe_dup@test.com",
        "password": "SecurePassword1!"
    }
    resp1 = client.post("/api/v1/auth/register/candidate", json=data)
    assert resp1.status_code == 201

    resp2 = client.post("/api/v1/auth/register/candidate", json=data)
    assert resp2.status_code == 409
    assert resp2.json()["detail"] == "A user with this email already exists"


def test_register_candidate_invalid_email(client: TestClient):
    data = {
        "full_name": "Bad Email User",
        "email": "not-an-email",
        "password": "SecurePassword1!"
    }
    resp = client.post("/api/v1/auth/register/candidate", json=data)
    assert resp.status_code == 422  # Pydantic validation error
