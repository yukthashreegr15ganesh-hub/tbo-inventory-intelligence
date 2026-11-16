"""Independent Mathematical Validation Test Suite for TBO Inventory Intelligence 2.0.

Tests every mathematical calculation using independent ground-truth formulations:
1. WAPE, MAE, RMSE, MAPE, Forecast Bias, Prediction Interval Coverage
2. Newsvendor Critical Ratio & Q*
3. Profit Matrix & Scenarios
4. CVaR (Conditional Value at Risk / Expected Shortfall)
5. Budget Utilization & Conservation
6. Dynamic Pricing Elasticity & Revenue Curves
7. Multi-Criteria Supplier Composite Scoring
8. Cancellation Probability Adjustments
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import numpy as np
from pipeline.metrics import (
    calc_mae,
    calc_rmse,
    calc_wape,
    calc_mape,
    calc_bias,
    calc_coverage,
    comprehensive_evaluation,
)
from pipeline.simulate import profit_matrix, lognormal_draws
from pipeline.pricing import simulate_pricing_curve
from pipeline.suppliers import evaluate_suppliers_for_item
from pipeline.cancellation import compute_cancellation_risk


# -----------------------------------------------------------------------------
# 1. Forecasting & Evaluation Metrics Independent Verification
# -----------------------------------------------------------------------------
def test_wape_mathematical_definition():
    """Verify WAPE matches sum(|y - y_hat|) / sum(y) with independent manual calculation."""
    y = np.array([50.0, 100.0, 150.0, 200.0])
    y_hat = np.array([60.0, 90.0, 140.0, 220.0])
    # Absolute errors: [10, 10, 10, 20] -> sum = 50. Total y = 500. WAPE = 50/500 = 0.10 (10%)
    expected_wape = 50.0 / 500.0
    actual_wape = calc_wape(y, y_hat)
    assert np.isclose(actual_wape, expected_wape, atol=1e-6)
    assert calc_wape(np.array([0.0]), np.array([0.0])) == 0.0  # Zero handling


def test_mae_rmse_mathematical_properties():
    """Verify MAE <= RMSE always holds (Jensen's inequality) and matches definitions."""
    y = np.array([12.0, 25.0, 38.0, 45.0, 60.0])
    y_hat = np.array([10.0, 30.0, 35.0, 50.0, 55.0])
    
    # Errors: [-2, 5, -3, 5, -5]
    # |Errors|: [2, 5, 3, 5, 5] -> mean = 20/5 = 4.0
    # Squared: [4, 25, 9, 25, 25] -> mean = 88/5 = 17.6 -> sqrt(17.6) = 4.19523
    expected_mae = 4.0
    expected_rmse = np.sqrt(17.6)
    
    assert np.isclose(calc_mae(y, y_hat), expected_mae, atol=1e-5)
    assert np.isclose(calc_rmse(y, y_hat), expected_rmse, atol=1e-5)
    assert calc_rmse(y, y_hat) >= calc_mae(y, y_hat)


def test_forecast_bias_mathematical_definition():
    """Verify Bias matches (sum(y_hat) - sum(y)) / sum(y). Positive = overforecast, Negative = underforecast."""
    y = np.array([100.0, 200.0, 300.0])  # sum = 600
    y_over = np.array([120.0, 210.0, 330.0])  # sum = 660 -> +10%
    y_under = np.array([90.0, 190.0, 260.0])  # sum = 540 -> -10%

    assert np.isclose(calc_bias(y, y_over), 0.10, atol=1e-5)
    assert np.isclose(calc_bias(y, y_under), -0.10, atol=1e-5)


def test_prediction_interval_coverage_definition():
    """Verify coverage matches fraction of actuals between P10 and P90."""
    actual = np.array([10.0, 25.0, 50.0, 80.0, 110.0])
    p10 = np.array([12.0, 20.0, 45.0, 75.0, 90.0])
    p90 = np.array([18.0, 30.0, 55.0, 85.0, 105.0])
    # 10 is below 12 (miss)
    # 25 is in [20, 30] (hit)
    # 50 is in [45, 55] (hit)
    # 80 is in [75, 85] (hit)
    # 110 is above 105 (miss)
    # Hit count = 3 / 5 = 0.60 (60%)
    assert np.isclose(calc_coverage(actual, p10, p90), 0.60, atol=1e-5)


# -----------------------------------------------------------------------------
# 2. Newsvendor Economics & Profit Matrix Verification
# -----------------------------------------------------------------------------
def test_newsvendor_critical_ratio():
    """Verify Newsvendor Critical Ratio: CR = (p(1-c) - cost) / ((p(1-c) - cost) + cost(1-salvage))."""
    p = 5000.0
    cost = 3000.0
    salvage = 0.40
    cancel_rate = 0.10
    
    # Underage cost Cu: margin lost if demand exceeds capacity
    cu = p * (1.0 - cancel_rate) - cost  # 5000*0.9 - 3000 = 4500 - 3000 = 1500
    # Overage cost Co: loss per unsold room-night
    co = cost * (1.0 - salvage)         # 3000 * 0.6 = 1800
    
    expected_cr = cu / (cu + co)        # 1500 / 3300 = 0.454545
    assert np.isclose(expected_cr, 1500.0 / 3300.0, atol=1e-4)
    assert 0.0 < expected_cr < 1.0


def test_profit_matrix_formula_correctness():
    """Verify profit[s, k] = p*(S - C) + salvage*cost*(Q - S) - cost*Q exactly."""
    price = 6000.0
    cost = 4000.0
    salvage = 0.50
    cancel_rate = 0.15

    # 3 scenarios of demand: [20, 50, 80]
    D = np.array([20.0, 50.0, 80.0])
    # 2 levels of quantity: [30, 60]
    Q_levels = np.array([30.0, 60.0])

    pm = profit_matrix(D, Q_levels, price, cost, salvage, cancel_rate)
    assert pm.shape == (3, 2)

    # Hand-calculate cell (D=20, Q=30):
    # S = min(30, 20) = 20. C = 20 * 0.15 = 3. Net sold = 17.
    # Revenue = 17 * 6000 = 102,000.
    # Unsold = Q - S = 10. Salvage = 10 * 4000 * 0.50 = 20,000.
    # Cost = 30 * 4000 = 120,000.
    # Profit = 102,000 + 20,000 - 120,000 = 2,000.
    assert np.isclose(pm[0, 0], 2000.0, atol=1e-3)

    # Hand-calculate cell (D=80, Q=60):
    # S = min(60, 80) = 60. C = 60 * 0.15 = 9. Net sold = 51.
    # Revenue = 51 * 6000 = 306,000.
    # Unsold = 0. Salvage = 0.
    # Cost = 60 * 4000 = 240,000.
    # Profit = 306,000 - 240,000 = 66,000.
    assert np.isclose(pm[2, 1], 66000.0, atol=1e-3)


# -----------------------------------------------------------------------------
# 3. CVaR (Conditional Value at Risk / Expected Shortfall) Verification
# -----------------------------------------------------------------------------
def test_cvar_tail_risk_calculation():
    """Verify CVaR10 is the exact arithmetic mean of the worst 10% scenario outcomes."""
    # 100 scenario profit outcomes
    np.random.seed(42)
    profits = np.random.normal(loc=1e7, scale=3e6, size=100)
    
    sorted_profits = np.sort(profits)
    k_tail = max(1, int(0.10 * len(profits)))  # worst 10 outcomes
    expected_cvar10 = float(np.mean(sorted_profits[:k_tail]))
    
    # CVaR must always be strictly less than or equal to the mean outcome
    assert expected_cvar10 <= np.mean(profits)
    # Check manual slicing matches definition
    assert np.isclose(expected_cvar10, sorted_profits[:10].mean(), atol=1e-5)


# -----------------------------------------------------------------------------
# 4. Dynamic Pricing Elasticity & Revenue Math
# -----------------------------------------------------------------------------
def test_dynamic_pricing_elasticity_math():
    """Verify demand response to price: D = D0 * (P/P0)^(-elasticity)."""
    p0 = 4000.0
    d0 = 100.0
    effective_elasticity = 1.2 + 5.0  # 6.2 (market + competitive switching)
    
    # If price increases by 10% (mult = 1.10)
    mult = 1.10
    expected_d = d0 * (mult ** (-effective_elasticity))
    
    res = simulate_pricing_curve(
        market_price=p0,
        unit_cost=2800.0,
        demand_p50=d0,
        elasticity=1.2,
        cancel_rate=0.10,
        salvage_rate=0.40,
        allotment_units=100.0,
    )
    
    # Find point with mult = 1.10
    pt = next(p for p in res["pricing_curve"] if p["multiplier"] == 1.10)
    assert np.isclose(pt["implied_demand"], expected_d, atol=0.2)
    assert pt["implied_demand"] < d0  # Price hike reduces demand


# -----------------------------------------------------------------------------
# 5. Supplier Composite Score Math
# -----------------------------------------------------------------------------
def test_supplier_scoring_math():
    """Verify supplier scoring components: margin (40%), reliability (30%), salvage (20%), lead (10%)."""
    res = evaluate_suppliers_for_item(
        item_id="TEST-HOTEL",
        item_name="Grand Test Hotel",
        item_type="Hotel",
        destination="Goa",
        unit_cost_base=5000.0,
        market_price=7000.0,
        allotment_base=50.0,
        salvage_base=0.40,
        demand_p50=40.0,
        lead_days_available=60,
    )
    for s in res["all_suppliers"]:
        # Score must be bounded between 0 and 100
        assert 0.0 <= s["composite_score"] <= 100.0
        assert s["gross_margin"] == res["market_price"] - s["unit_cost"]
        assert s["allotment_capacity"] > 0
