"""
PATHS Backend — Organization registration and member management tests.
"""

import pytest
from fastapi.testclient import TestClient


def test_register_organization_success(client: TestClient):
    data = {
        "organization_name": "Acme Corp",
        "organization_slug": "acme-corp",
        "industry": "Technology",
        "first_admin_full_name": "Admin User",
        "first_admin_email": "admin@acme-corp.com",
        "first_admin_password": "AdminPassword123!"
    }

    resp = client.post("/api/v1/auth/register/organization", json=data)
    assert resp.status_code == 201

    resp_data = resp.json()
    assert "organization_id" in resp_data
    assert "user_id" in resp_data
    assert resp_data["role_code"] == "org_admin"


def test_register_organization_duplicate_slug(client: TestClient):
    data1 = {
        "organization_name": "Beta Corp",
        "organization_slug": "beta-corp",
        "first_admin_full_name": "Beta Admin 1",
        "first_admin_email": "admin1@beta-corp.com",
        "first_admin_password": "Password123"
    }
    client.post("/api/v1/auth/register/organization", json=data1)

    data2 = {
        "organization_name": "Beta Corp New",
        "organization_slug": "beta-corp",  # Duplicate
        "first_admin_full_name": "Beta Admin 2",
        "first_admin_email": "admin2@beta-corp.com",
        "first_admin_password": "Password123"
    }
    resp = client.post("/api/v1/auth/register/organization", json=data2)
    assert resp.status_code == 409
    assert "slug already exists" in resp.json()["detail"]


def test_org_admin_can_create_member(client: TestClient):
    # 1. Register Org
    org_data = {
        "organization_name": "Gamma Inc",
        "organization_slug": "gamma-inc",
        "first_admin_full_name": "Gamma Admin",
        "first_admin_email": "admin@gamma-inc.com",
        "first_admin_password": "Password123"
    }
    reg_resp = client.post("/api/v1/auth/register/organization", json=org_data)
    org_id = reg_resp.json()["organization_id"]

    # 2. Login Admin
    login_resp = client.post("/api/v1/auth/login", json={
        "email": "admin@gamma-inc.com",
        "password": "Password123"
    })
    token = login_resp.json()["access_token"]

    # 3. Create Member (HR Manager)
    member_data = {
        "full_name": "HR Manager",
        "email": "hr@gamma-inc.com",
        "password": "Password123",
        "role_code": "hr_manager"
    }
    headers = {"Authorization": f"Bearer {token}"}
    create_resp = client.post(
        f"/api/v1/organizations/{org_id}/members",
        json=member_data,
        headers=headers
    )
    assert create_resp.status_code == 201
    
    # Verify the new member can login
    login_member = client.post("/api/v1/auth/login", json={
        "email": "hr@gamma-inc.com",
        "password": "Password123"
    })
    member_data = login_member.json()
    assert member_data["user"]["organization"]["role_code"] == "hr_manager"

def test_non_admin_cannot_create_member(client: TestClient):
    # Candidate login should fail org authorization
    cand_resp = client.post("/api/v1/auth/register/candidate", json={
        "full_name": "Hacker",
        "email": "hacker@test.com",
        "password": "Password123"
    })
    # .. get token ..
    login_resp = client.post("/api/v1/auth/login", json={"email": "hacker@test.com", "password": "Password123"})
    token = login_resp.json()["access_token"]
    
    resp = client.post(
        f"/api/v1/organizations/00000000-0000-0000-0000-000000000000/members",
        json={"full_name": "X", "email": "x@x.com", "password": "Password123", "role_code": "hr"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert resp.status_code == 403
    assert "Only organization members can access" in resp.json()["detail"]
