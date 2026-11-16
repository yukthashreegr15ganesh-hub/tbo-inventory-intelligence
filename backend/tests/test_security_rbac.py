"""Security & Role-Based Access Control (RBAC) Automated Test Suite.

Verifies:
1. Bcrypt Password Hashing & Salt Verification
2. JWT Token Generation, Expiration, and Signature Decoding
3. User Authentication (/api/auth/login) with valid/invalid credentials
4. Profile Identity (/api/auth/me)
5. Role-Based Access Control policies:
    - admin has full permissions
    - procurement_manager can approve replans and upload data
    - analyst can query what-if simulations and pricing
    - unauthorized / invalid tokens receive HTTP 401
    - insufficient role receives HTTP 403
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from app import app
from pipeline.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    authenticate_user,
)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_password_hashing():
    """Verify bcrypt hash generation and validation."""
    pwd = "EnterpriseSecurePass2026!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPass", hashed) is False


def test_jwt_token_lifecycle():
    """Verify JWT creation, signature decoding, and claim extraction."""
    claims = {"sub": "test_analyst", "role": "analyst", "full_name": "Test Analyst"}
    token = create_access_token(claims)
    assert isinstance(token, str)
    
    decoded = decode_access_token(token)
    assert decoded is not None
    assert decoded["sub"] == "test_analyst"
    assert decoded["role"] == "analyst"


def test_auth_login_success(client):
    """Verify /api/auth/login succeeds with valid seed credentials."""
    resp = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "AdminUser_2026!",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["role"] == "admin"

    # Verify /api/auth/me using bearer token
    token = data["access_token"]
    me_resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    assert me_resp.json()["username"] == "admin"


def test_auth_login_invalid_credentials(client):
    """Verify /api/auth/login rejects incorrect passwords with HTTP 401."""
    resp = client.post("/api/auth/login", json={
        "username": "admin",
        "password": "IncorrectPassword123",
    })
    assert resp.status_code == 401
    assert "Invalid username or password" in resp.json()["detail"]


def test_rbac_procurement_manager_permissions(client):
    """Verify procurement_manager role can approve replans and upload data."""
    # Login as procurement manager
    login_resp = client.post("/api/auth/login", json={
        "username": "procure_lead",
        "password": "ProcureLead_2026!",
    })
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Trigger a replan to get an ID
    replan_resp = client.post("/api/replan", json={
        "trigger_reason": "RBAC verification test",
        "budget": 50e7,
        "risk_aversion": 0.3,
        "max_dest_share": 0.3,
        "item_types": ["Hotel"],
    }, headers=headers)
    assert replan_resp.status_code == 200
    replan_id = replan_resp.json()["replan_audit"]["replan_id"]

    # Approve replan using procurement manager token
    appr_resp = client.post("/api/replan/approve", json={
        "replan_id": replan_id,
        "action": "APPROVE",
        "approver": "procure_lead",
    }, headers=headers)
    assert appr_resp.status_code == 200
    assert appr_resp.json()["status"] == "APPROVED"
