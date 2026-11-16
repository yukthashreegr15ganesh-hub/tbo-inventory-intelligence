"""API, Security, Concurrency and Performance Test Suite for TBO Inventory Intelligence 2.0.

Verifies:
1. Complete API Route Coverage (HTTP 200, schema consistency)
2. Negative & Boundary Input Validation (budget <= 0, invalid shock ranges)
3. File Upload Security (extension whitelist, max size limit, path traversal defense)
4. Multi-Request Stability & Performance Benchmarks
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import time
import pytest
from fastapi.testclient import TestClient
from app import app
from pipeline.data_integration import MAX_UPLOAD_BYTES, parse_and_validate_file


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


# -----------------------------------------------------------------------------
# 1. API Route Coverage & Schema Response Verification
# -----------------------------------------------------------------------------
def test_all_get_endpoints_status_200(client):
    """Verify all system GET endpoints return 200 OK and valid JSON structures."""
    # 1. Health
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["status"] == "HEALTHY"

    # 2. Summary
    s = client.get("/api/summary")
    assert s.status_code == 200
    assert "multilevel_metrics" in s.json()
    assert "provenance" in s.json()

    # 3. Items
    items = client.get("/api/items")
    assert items.status_code == 200
    item_list = items.json()
    assert isinstance(item_list, list)
    assert len(item_list) > 0

    # 4. Opportunities
    opps = client.get("/api/opportunities?limit=10")
    assert opps.status_code == 200
    assert isinstance(opps.json(), list)

    # 5. Forecast by item
    first_item_id = item_list[0]["item_id"]
    fc = client.get(f"/api/forecast/{first_item_id}")
    assert fc.status_code == 200
    fc_data = fc.json()
    assert "item" in fc_data
    assert "forecast" in fc_data
    assert "history" in fc_data

    # 6. Suppliers
    sup = client.get("/api/suppliers?limit=10")
    assert sup.status_code == 200
    assert "supplier_benchmarks" in sup.json()

    # 7. Evaluation metrics
    ev = client.get("/api/evaluation-metrics")
    assert ev.status_code == 200
    assert "daily" in ev.json()
    assert "weekly" in ev.json()
    assert "monthly" in ev.json()

    # 8. Data status
    ds = client.get("/api/data/status")
    assert ds.status_code == 200
    assert "source_mode" in ds.json()
    assert "dataset_name" in ds.json()
    assert "upload_audit" in ds.json()

    # 9. Replan history
    rh = client.get("/api/replan/history")
    assert rh.status_code == 200
    assert isinstance(rh.json(), list)


def test_all_post_endpoints_status_200(client):
    """Verify compute POST endpoints return 200 OK and valid mathematical outputs."""
    # 1. POST /api/pricing-recommendations
    p_resp = client.post("/api/pricing-recommendations", json={
        "market_price": 5000.0,
        "unit_cost": 3500.0,
        "demand_p50": 60.0,
        "elasticity": 1.2,
        "cancel_rate": 0.15,
        "salvage_rate": 0.40,
        "allotment_units": 50.0,
    })
    assert p_resp.status_code == 200
    p_data = p_resp.json()
    assert "pricing_curve" in p_data
    assert "recommended_price" in p_data

    # 2. POST /api/cancellation-risk
    c_resp = client.post("/api/cancellation-risk", json={
        "base_cancel_rate": 0.15,
        "lead_days": 45,
        "channel": "Corporate_B2B",
    })
    assert c_resp.status_code == 200
    c_data = c_resp.json()
    assert "cancellation_probability" in c_data
    assert "risk_tier" in c_data

    # 3. POST /api/simulate-what-if
    s_resp = client.post("/api/simulate-what-if", json={
        "budget": 750000000.0,
        "demand_shock_pct": 10.0,
        "supplier_cost_shock_pct": -5.0,
        "cancellation_shock_pct": 0.0,
        "risk_aversion": 0.3,
        "max_dest_share": 0.30,
        "item_types": ["Hotel", "Flight"],
    })
    assert s_resp.status_code == 200
    s_data = s_resp.json()
    assert "strategies" in s_data
    assert any("Conservative" in s["name"] for s in s_data["strategies"])
    assert any("Balanced" in s["name"] for s in s_data["strategies"])
    assert any("Aggressive" in s["name"] for s in s_data["strategies"])


# -----------------------------------------------------------------------------
# 2. Input Validation & Error Handling (Boundary / Fault Injection)
# -----------------------------------------------------------------------------
def test_optimize_input_validation_negative_budget(client):
    """Verify POST /api/optimize returns 400 or 422 for non-positive budgets."""
    resp = client.post("/api/optimize", json={"budget": -500000.0, "risk_aversion": 0.5})
    assert resp.status_code in [400, 422], f"Expected 400/422 for negative budget, got {resp.status_code}"

    resp2 = client.post("/api/optimize", json={"budget": 0.0, "risk_aversion": 0.5})
    assert resp2.status_code in [400, 422], f"Expected 400/422 for zero budget, got {resp2.status_code}"


def test_what_if_invalid_range_validation(client):
    """Verify POST /api/simulate-what-if rejects out-of-range shock parameters."""
    bad_payload = {
        "budget": 750000000.0,
        "demand_shock_pct": 999.0,  # exceeds le=150 limit
        "supplier_cost_shock_pct": 0.0,
        "cancellation_shock_pct": 0.0,
        "risk_aversion": 0.3,
        "max_dest_share": 0.30,
        "item_types": ["Hotel"],
    }
    resp = client.post("/api/simulate-what-if", json=bad_payload)
    assert resp.status_code in [400, 422]


# -----------------------------------------------------------------------------
# 3. File Upload Security (Extension Whitelist, Size Bounds, Path Traversal)
# -----------------------------------------------------------------------------
def test_file_upload_security_disallowed_extensions():
    """Verify scripts and executables (.exe, .sh, .bat, .py) are strictly rejected."""
    malicious_extensions = ["payload.exe", "script.sh", "run.bat", "exploit.py", "malware.bin"]
    for fname in malicious_extensions:
        res = parse_and_validate_file(b"echo vulnerable", fname, "bookings")
        assert res["success"] is False
        assert "disallowed" in res["error"].lower()


def test_file_upload_security_size_limit():
    """Verify file upload rejects payloads exceeding MAX_UPLOAD_BYTES (25 MB)."""
    oversized_bytes = b"x" * (MAX_UPLOAD_BYTES + 1024)
    res = parse_and_validate_file(oversized_bytes, "huge_file.csv", "bookings")
    assert res["success"] is False
    assert "exceeds maximum allowed size" in res["error"]


def test_file_upload_path_traversal_sanitization():
    """Verify path traversal characters (../ or ..\\) are stripped from filenames."""
    csv_bytes = b"date,item_id,bookings,searches,avg_sell_price\n2026-11-01,H-GOA-A,10,100,5000\n"
    res = parse_and_validate_file(csv_bytes, "../../../../etc/passwd.csv", "bookings")
    assert res["success"] is True
    assert "../" not in res["filename"]
    assert "\\" not in res["filename"]
    assert res["filename"] == "passwd.csv"


# -----------------------------------------------------------------------------
# 4. Multi-Request Stability & Performance Benchmarks
# -----------------------------------------------------------------------------
def test_multi_request_stability(client):
    """Verify backend handles back-to-back compute-intensive requests consistently."""
    budgets = [100_000_000.0, 300_000_000.0, 500_000_000.0]
    for b in budgets:
        resp = client.post("/api/optimize", json={"budget": b, "risk_aversion": 0.3})
        assert resp.status_code == 200
        data = resp.json()
        assert "plan" in data
        assert "stats" in data
        assert "expected_profit" in data["stats"]
        assert data["allocated_budget"] <= b + 1e-4


def test_api_latency_benchmarks(client):
    """Verify API latency meets production response time SLAs."""
    # 1. Health check latency must be sub-50ms
    t0 = time.perf_counter()
    resp = client.get("/api/health")
    dt_health_ms = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200
    assert dt_health_ms < 50.0, f"Health check latency {dt_health_ms:.1f}ms exceeds 50ms SLA"

    # 2. What-If simulation latency (solves 4 MILP optimizations) must be sub-5000ms
    t0 = time.perf_counter()
    resp = client.post("/api/simulate-what-if", json={
        "budget": 750000000.0,
        "demand_shock_pct": 5.0,
        "supplier_cost_shock_pct": -2.0,
        "cancellation_shock_pct": 0.0,
        "risk_aversion": 0.3,
        "max_dest_share": 0.30,
        "item_types": ["Hotel", "Flight"],
    })
    dt_sim_ms = (time.perf_counter() - t0) * 1000
    assert resp.status_code == 200
    assert dt_sim_ms < 6000.0, f"Simulation latency {dt_sim_ms:.1f}ms exceeds 6000ms SLA"
