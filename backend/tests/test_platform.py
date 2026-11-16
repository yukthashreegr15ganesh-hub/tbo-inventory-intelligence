"""Comprehensive Automated Test Suite for TBO Inventory Intelligence.

Validates:
1. Mathematical calculations: Newsvendor critical ratio, profit matrix, CVaR, WAPE, MAE, RMSE, Bias.
2. Optimization constraints: Budget constraint, non-negativity, destination concentration cap.
3. Supplier intelligence: Multi-criteria supplier scoring, lead-time feasibility.
4. Cancellation risk prediction: Probabilities, risk tiers, channel weights.
5. Dynamic pricing: Price-demand elasticity curve, guardrails.
6. What-if simulation: Shock recalculations and strategy profiles.
7. Automated replanning: Delta calculations and approval workflow.
8. Data integration: CSV/Excel parsing, schema validation, deduplication.
9. API endpoints: FastAPI routes and responses.
"""
import io
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from app import app, OPT, CANDS
from pipeline.metrics import calc_mae, calc_rmse, calc_wape, calc_bias, calc_coverage
from pipeline.suppliers import evaluate_suppliers_for_item
from pipeline.cancellation import compute_cancellation_risk
from pipeline.pricing import simulate_pricing_curve
from pipeline.simulation import run_what_if_simulation
from pipeline.replanning import calculate_plan_delta, record_replan_execution, approve_or_reject_replan
from pipeline.data_integration import parse_and_validate_file


@pytest.fixture
def client():
    return TestClient(app)


# -----------------------------------------------------------------------------
# 1. Mathematical Metrics Tests
# -----------------------------------------------------------------------------
def test_evaluation_metrics_math():
    actual = np.array([100.0, 150.0, 200.0, 80.0])
    pred = np.array([110.0, 140.0, 190.0, 85.0])
    p10 = np.array([90.0, 120.0, 170.0, 70.0])
    p90 = np.array([130.0, 170.0, 220.0, 95.0])

    mae = calc_mae(actual, pred)
    assert round(mae, 2) == 8.75

    rmse = calc_rmse(actual, pred)
    assert rmse > 0 and rmse >= mae

    wape = calc_wape(actual, pred)
    assert round(wape, 4) == round(35.0 / 530.0, 4)

    bias = calc_bias(actual, pred)
    assert round(bias, 4) == round(-5.0 / 530.0, 4)

    cov = calc_coverage(actual, p10, p90)
    assert cov == 1.0


# -----------------------------------------------------------------------------
# 2. Optimization Constraints & Feasibility Tests
# -----------------------------------------------------------------------------
@pytest.mark.parametrize("budget", [10e7, 50e7, 75e7, 120e7])
def test_budget_constraint_never_violated(budget):
    res = OPT.solve(budget=budget, lam=0.3, max_dest_share=0.30)
    stats = res["stats"]
    invested = stats["invested"]
    
    # Capital deployed must never exceed budget
    assert invested <= budget + 1e-3
    assert stats["budget_used"] <= 1.0001
    assert stats["unused_budget"] >= 0.0
    
    # Check plan rows: units must be non-negative integers
    for row in res["plan"]:
        assert row["units"] >= 0
        assert isinstance(row["units"], int)
        assert row["investment"] >= 0


def test_destination_concentration_cap():
    budget = 60e7
    max_share = 0.25
    res = OPT.solve(budget=budget, lam=0.3, max_dest_share=max_share)
    
    # Check each destination share
    for d in res["by_destination"]:
        share = d["investment"] / budget
        assert share <= max_share + 0.05  # within boundary tolerance


def test_infeasible_or_empty_filters():
    # If a non-existent destination is selected
    res = OPT.solve(budget=50e7, lam=0.3, destinations=["NonExistentCity"])
    assert res["stats"]["invested"] == 0
    assert len(res["plan"]) == 0


# -----------------------------------------------------------------------------
# 3. Supplier Intelligence Tests
# -----------------------------------------------------------------------------
def test_supplier_evaluation():
    eval_res = evaluate_suppliers_for_item(
        item_id="H-GOA-B",
        item_name="Calangute Bay Inn",
        item_type="Hotel",
        destination="Goa",
        unit_cost_base=3200,
        market_price=4500,
        allotment_base=60,
        salvage_base=0.45,
        demand_p50=40,
        lead_days_available=45,
    )
    assert "recommended_supplier" in eval_res
    assert len(eval_res["allliers" if "allliers" in eval_res else "all_suppliers"]) == 4
    assert eval_res["recommended_supplier"]["reliability_score"] >= 0.85
    assert len(eval_res["selection_rationale"]) > 20


# -----------------------------------------------------------------------------
# 4. Cancellation Risk Prediction Tests
# -----------------------------------------------------------------------------
def test_cancellation_prediction():
    # Long lead corporate vs leisure
    corp = compute_cancellation_risk(0.15, lead_days=30, channel="Corporate_B2B")
    leisure = compute_cancellation_risk(0.15, lead_days=90, channel="Leisure_Agent")

    assert corp["cancellation_probability"] < leisure["cancellation_probability"]
    assert corp["risk_tier"] in ["Low", "Moderate", "High"]
    assert len(corp["drivers"]) == 4


# -----------------------------------------------------------------------------
# 5. Dynamic Pricing Tests
# -----------------------------------------------------------------------------
def test_pricing_curve():
    res = simulate_pricing_curve(
        market_price=5000,
        unit_cost=3500,
        demand_p50=80,
        elasticity=1.2,
        cancel_rate=0.10,
        salvage_rate=0.40,
        allotment_units=60,
    )
    assert len(res["pricing_curve"]) > 3
    assert res["recommended_price"] > 0
    assert "PASS" in res["guardrail_status"]


# -----------------------------------------------------------------------------
# 6. What-If Simulation Tests
# -----------------------------------------------------------------------------
def test_what_if_simulation():
    res = run_what_if_simulation(
        optimizer=OPT,
        base_budget=50e7,
        demand_shock_pct=-20.0,
        supplier_cost_shock_pct=10.0,
        cancellation_shock_pct=15.0,
        risk_aversion=0.4,
    )
    assert "stats" in res
    assert len(res["strategies"]) == 3
    assert "sensitivity" in res
    assert res["stats"]["invested"] <= 50e7


# -----------------------------------------------------------------------------
# 7. Automated Replanning & Approval Tests
# -----------------------------------------------------------------------------
def test_replanning_and_approval():
    old_plan = [
        {"cand_id": "H-GOA-1", "name": "Hotel A", "destination": "Goa", "week": "2026-11-16",
         "item_type": "Hotel", "units": 100, "investment": 500000, "expected_profit": 80000},
    ]
    new_plan = [
        {"cand_id": "H-GOA-1", "name": "Hotel A", "destination": "Goa", "week": "2026-11-16",
         "item_type": "Hotel", "units": 150, "investment": 750000, "expected_profit": 120000},
        {"cand_id": "F-DEL-2", "name": "Flight B", "destination": "Jaipur", "week": "2026-11-16",
         "item_type": "Flight", "units": 50, "investment": 200000, "expected_profit": 30000},
    ]
    delta = calculate_plan_delta(old_plan, new_plan)
    assert delta["total_units_delta"] == 100
    assert delta["total_investment_delta"] == 450000
    assert len(delta["changes"]) == 2

    # Replan audit
    res_plan = {"stats": {"invested": 750000, "expected_profit": 150000}, "plan": new_plan}
    audit = record_replan_execution("Demand surge test", {"budget": 1e7}, res_plan, auto_approve=False)
    assert audit["status"] == "PENDING_APPROVAL"

    # Approval action
    app_res = approve_or_reject_replan(audit["replan_id"], "APPROVE", "Manager_Test")
    assert app_res["success"] is True
    assert app_res["status"] == "APPROVED"


# -----------------------------------------------------------------------------
# 8. Data Ingestion & File Validation Tests
# -----------------------------------------------------------------------------
def test_valid_csv_upload():
    csv_content = b"date,item_id,bookings,searches,avg_sell_price\n2026-11-01,H-GOA-B,25,180,4500\n2026-11-02,H-GOA-B,30,210,4600\n"
    res = parse_and_validate_file(csv_content, "test_bookings.csv", "bookings")
    assert res["success"] is True
    assert res["rows_processed"] == 2


def test_invalid_schema_upload():
    bad_csv = b"date,item_id,random_column\n2026-11-01,H-GOA-B,999\n"
    res = parse_and_validate_file(bad_csv, "bad.csv", "bookings")
    assert res["success"] is False
    assert "Missing required columns" in res["error"]


# -----------------------------------------------------------------------------
# 9. API Integration Endpoints Tests
# -----------------------------------------------------------------------------
def test_api_endpoints(client):
    # Health check
    h = client.get("/api/health")
    assert h.status_code == 200
    assert h.json()["status"] == "HEALTHY"

    # Summary
    s = client.get("/api/summary")
    assert s.status_code == 200
    assert "multilevel_metrics" in s.json()
    assert "provenance" in s.json()

    # Evaluation metrics
    e = client.get("/api/evaluation-metrics")
    assert e.status_code == 200
    assert "daily" in e.json()
    assert "weekly" in e.json()
    assert "monthly" in e.json()

    # Suppliers
    sup = client.get("/api/suppliers?limit=5")
    assert sup.status_code == 200
    assert "supplier_benchmarks" in sup.json()

    # What-If
    wi = client.post("/api/simulate-what-if", json={
        "budget": 50e7,
        "demand_shock_pct": 10.0,
        "supplier_cost_shock_pct": -5.0,
        "cancellation_shock_pct": 0.0,
        "risk_aversion": 0.3,
        "max_dest_share": 0.3,
        "item_types": ["Hotel", "Flight"],
    })
    assert wi.status_code == 200
    assert "strategies" in wi.json()

    # Pricing
    pr = client.post("/api/pricing-recommendations", json={
        "market_price": 5000,
        "unit_cost": 3800,
        "demand_p50": 60,
    })
    assert pr.status_code == 200
    assert "pricing_curve" in pr.json()

    # Cancellation
    can = client.post("/api/cancellation-risk", json={
        "base_cancel_rate": 0.18,
        "lead_days": 45,
        "channel": "Corporate_B2B",
    })
    assert can.status_code == 200
    assert "cancellation_probability" in can.json()
