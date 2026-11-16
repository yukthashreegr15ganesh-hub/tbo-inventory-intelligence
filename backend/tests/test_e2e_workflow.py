"""End-to-End Complete Integration Workflow Test for TBO Inventory Intelligence 2.0.

Validates the full 10-step business sequence:
1. DATA UPLOAD: CSV bookings upload
2. DATA VALIDATION: Provenance & schema verification
3. DEMAND FORECASTING: Unconstrained demand distributions (P10/P50/P90)
4. CANCELLATION RISK: ML probability and risk tier calibration
5. SUPPLIER SELECTION: Multi-criteria benchmark evaluation
6. INVENTORY OPTIMIZATION: Budget-constrained CVaR optimization
7. PRICING RECOMMENDATIONS: Price elasticity & margin maximization
8. REPLANNING: Delta analysis against current inventory positions
9. APPROVAL QUEUE: Human-in-the-loop sign-off (APPROVE action)
10. AUDIT HISTORY: Immutable audit trail persistence
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from app import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_complete_e2e_inventory_intelligence_workflow(client):
    """Execute all 10 phases sequentially and verify data flow consistency."""
    
    # -------------------------------------------------------------------------
    # STEP 1: DATA UPLOAD
    # -------------------------------------------------------------------------
    csv_payload = (
        b"date,item_id,bookings,searches,avg_sell_price\n"
        b"2026-11-01,H-GOA-A,45,350,5500\n"
        b"2026-11-02,H-GOA-A,50,400,5600\n"
        b"2026-11-03,H-GOA-A,48,380,5550\n"
    )
    upload_resp = client.post(
        "/api/data/upload",
        files={"file": ("live_october_bookings.csv", csv_payload, "text/csv")},
        data={"data_type": "bookings"},
    )
    assert upload_resp.status_code == 200, f"Step 1 Upload failed: {upload_resp.text}"
    upload_data = upload_resp.json()
    assert upload_data["success"] is True
    assert upload_data["rows_processed"] == 3

    # -------------------------------------------------------------------------
    # STEP 2: DATA VALIDATION & PROVENANCE
    # -------------------------------------------------------------------------
    status_resp = client.get("/api/data/status")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert "source_mode" in status_data
    assert status_data["source_mode"] == "user_uploaded"
    audit_list = status_data.get("upload_audit", [])
    assert len(audit_list) > 0
    assert any(a["filename"] == "live_october_bookings.csv" for a in audit_list)

    # -------------------------------------------------------------------------
    # STEP 3: DEMAND FORECASTING
    # -------------------------------------------------------------------------
    fc_resp = client.get("/api/forecast/H-GOA-B")
    assert fc_resp.status_code == 200
    fc_data = fc_resp.json()
    assert "forecast" in fc_data
    assert len(fc_data["forecast"]) > 0
    sample_fc = fc_data["forecast"][0]
    assert "p10" in sample_fc and "p50" in sample_fc and "p90" in sample_fc
    assert sample_fc["p10"] <= sample_fc["p50"] <= sample_fc["p90"]

    # -------------------------------------------------------------------------
    # STEP 4: CANCELLATION RISK PREDICTION
    # -------------------------------------------------------------------------
    cancel_resp = client.post("/api/cancellation-risk", json={
        "base_cancel_rate": 0.15,
        "lead_days": 40,
        "channel": "Corporate_B2B",
    })
    assert cancel_resp.status_code == 200
    cancel_data = cancel_resp.json()
    assert 0.0 < cancel_data["cancellation_probability"] < 1.0
    cancel_rate_to_use = cancel_data["cancellation_probability"]

    # -------------------------------------------------------------------------
    # STEP 5: SUPPLIER SELECTION & BENCHMARKING
    # -------------------------------------------------------------------------
    supp_resp = client.get("/api/suppliers?limit=10")
    assert supp_resp.status_code == 200
    supp_data = supp_resp.json()
    assert "supplier_benchmarks" in supp_data
    assert len(supp_data["supplier_benchmarks"]) > 0
    top_benchmark = supp_data["supplier_benchmarks"][0]
    assert "recommended_supplier" in top_benchmark
    assert "all_suppliers" in top_benchmark
    assert top_benchmark["recommended_supplier"]["reliability_score"] >= 0.85
    assert len(top_benchmark["selection_rationale"]) > 10

    # -------------------------------------------------------------------------
    # STEP 6: INVENTORY OPTIMIZATION
    # -------------------------------------------------------------------------
    budget_target = 600_000_000.0  # 600M INR
    opt_resp = client.post("/api/optimize", json={
        "budget": budget_target,
        "risk_aversion": 0.35,
        "max_dest_share": 0.25,
        "item_types": ["Hotel", "Flight"],
        "include_alternatives": True,
    })
    assert opt_resp.status_code == 200
    opt_data = opt_resp.json()
    assert "plan" in opt_data
    assert opt_data["allocated_budget"] <= budget_target + 1e-4
    assert opt_data["stats"]["expected_profit"] > 0
    assert "alternative_scenarios" in opt_data

    # -------------------------------------------------------------------------
    # STEP 7: PRICING RECOMMENDATIONS
    # -------------------------------------------------------------------------
    first_plan_item = opt_data["plan"][0]
    pricing_resp = client.post("/api/pricing-recommendations", json={
        "market_price": float(first_plan_item["market_price"]),
        "unit_cost": float(first_plan_item["unit_cost"]),
        "demand_p50": float(first_plan_item["demand_p50"]),
        "elasticity": 1.25,
        "cancel_rate": cancel_rate_to_use,
        "salvage_rate": 0.40,
        "allotment_units": float(first_plan_item["units"]),
    })
    assert pricing_resp.status_code == 200
    pricing_data = pricing_resp.json()
    assert pricing_data["recommended_price"] > 0
    assert "PASS" in pricing_data["guardrail_status"]

    # -------------------------------------------------------------------------
    # STEP 8: AUTOMATED REPLANNING
    # -------------------------------------------------------------------------
    replan_resp = client.post("/api/replan", json={
        "trigger_reason": "End-to-End Integration Validation Test",
        "budget": 650_000_000.0,
        "risk_aversion": 0.40,
        "max_dest_share": 0.30,
        "item_types": ["Hotel", "Flight"],
        "auto_approve": False,
        "auto_threshold_pct": 5.0,
    })
    assert replan_resp.status_code == 200
    replan_data = replan_resp.json()
    audit_entry = replan_data["replan_audit"]
    replan_id = audit_entry["replan_id"]
    assert replan_id.startswith("RPL-")

    # -------------------------------------------------------------------------
    # STEP 9: APPROVAL QUEUE (HUMAN-IN-THE-LOOP)
    # -------------------------------------------------------------------------
    approve_resp = client.post("/api/replan/approve", json={
        "replan_id": replan_id,
        "action": "APPROVE",
        "approver": "QA_Principal_Validator",
    })
    assert approve_resp.status_code == 200
    approve_data = approve_resp.json()
    assert approve_data["success"] is True
    assert approve_data["status"] == "APPROVED"

    # -------------------------------------------------------------------------
    # STEP 10: AUDIT HISTORY PERSISTENCE
    # -------------------------------------------------------------------------
    hist_resp = client.get("/api/replan/history")
    assert hist_resp.status_code == 200
    hist_list = hist_resp.json()
    assert isinstance(hist_list, list)
    replan_records = [r for r in hist_list if r["replan_id"] == replan_id]
    assert len(replan_records) == 1
    assert replan_records[0]["status"] == "APPROVED"
    assert replan_records[0]["approver"] == "QA_Principal_Validator"
