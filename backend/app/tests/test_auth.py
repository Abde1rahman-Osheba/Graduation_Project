"""
PATHS Backend — Auth endpoint tests.
"""

import pytest
from fastapi.testclient import TestClient


def test_auth_login_candidate(client: TestClient):
    # 1. Register candidate
    reg_data = {
        "full_name": "Test Candidate Login",
        "email": "login_candidate@test.com",
        "password": "StrongPassword123",
        "phone": "123456789",
    }
    resp = client.post("/api/v1/auth/register/candidate", json=reg_data)
    assert resp.status_code == 201

    # 2. Login
    login_data = {
        "email": "login_candidate@test.com",
        "password": "StrongPassword123"
    }
    resp = client.post("/api/v1/auth/login", json=login_data)
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["user"]["email"] == "login_candidate@test.com"
    assert data["user"]["account_type"] == "candidate"
    
    # 3. GET /me
    token = data["access_token"]
    resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    me = resp.json()
    assert me["email"] == "login_candidate@test.com"
    assert me["account_type"] == "candidate"
    assert me["candidate_profile"]["phone"] == "123456789"


def test_auth_login_invalid_credentials(client: TestClient):
    login_data = {
        "email": "nonexistent@test.com",
        "password": "WrongPassword123"
    }
    resp = client.post("/api/v1/auth/login", json=login_data)
    assert resp.status_code == 401


def test_auth_me_requires_token(client: TestClient):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
