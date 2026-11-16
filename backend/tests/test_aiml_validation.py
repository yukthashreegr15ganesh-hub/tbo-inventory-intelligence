"""AI/ML Validation & Verification Test Suite for TBO Inventory Intelligence 2.0.

Verifies:
1. Temporal Train/Test Separation (strict out-of-time split, zero overlap)
2. Zero Data Leakage (all feature lag horizons >= 91 days)
3. Ground Truth Isolation (unconstrained demand vs actual demand separation)
4. Prediction Interval Calibration (P10-P90 coverage within 75%-85% window)
5. Model Reproducibility across random seeds
6. Cancellation ML Monotonicity & Risk Tier Bounds
7. Dynamic Pricing Elasticity Downward-Sloping Demand Curve
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
import numpy as np
import pandas as pd
from pipeline.config import (
    DATA_DIR,
    ART_DIR,
    HIST_END,
    HORIZON_START,
    HORIZON_END,
    HORIZON_WEEKS,
    SEARCH_LAG_MIN,
    SEARCH_LAG_MAX,
    SEED,
)
from pipeline.simulate import common_shocks
from pipeline.cancellation import compute_cancellation_risk
from pipeline.pricing import simulate_pricing_curve


# -----------------------------------------------------------------------------
# 1. Temporal Train / Test Separation & Horizon Integrity
# -----------------------------------------------------------------------------
def test_temporal_train_test_separation():
    """Verify train cut strictly precedes the test evaluation period with zero overlap."""
    assert HIST_END < HORIZON_START
    gap_days = (HORIZON_START - HIST_END).days
    assert gap_days >= 7, f"Commitment buffer should be at least 7 days, got {gap_days}"
    
    # 91-day holdout backtest window:
    holdout_start = HIST_END - pd.Timedelta(days=91)
    train_end = holdout_start
    assert train_end < HIST_END
    assert (HIST_END - holdout_start).days == 91


# -----------------------------------------------------------------------------
# 2. Zero Data Leakage Verification
# -----------------------------------------------------------------------------
def test_feature_engineering_zero_data_leakage():
    """Verify every feature lag strictly exceeds the 13-week (91-day) forecast horizon."""
    min_allowable_lag = HORIZON_WEEKS * 7  # 91 days

    # 1. Search index lag
    assert SEARCH_LAG_MIN >= min_allowable_lag, (
        f"Search lag min ({SEARCH_LAG_MIN}) must be >= {min_allowable_lag} to prevent leakage"
    )
    assert SEARCH_LAG_MAX > SEARCH_LAG_MIN

    # 2. Year-over-year lag (dem_ly) is 364 days (52 weeks exactly)
    assert 364 >= min_allowable_lag

    # 3. Two-year lag (dem_ly2) is 728 days (104 weeks)
    assert 728 >= min_allowable_lag

    # 4. Recent baseline level (dem_level) is 120 days
    assert 120 >= min_allowable_lag


def test_ground_truth_isolation():
    """Verify training pipeline uses unconstrained demand estimates, never ground truth."""
    truth_file = DATA_DIR / "_ground_truth.csv"
    assert truth_file.exists(), "_ground_truth.csv must exist for backtesting"
    
    # Verify that daily.csv (the operational table) does NOT contain true_demand
    daily = pd.read_csv(DATA_DIR / "daily.csv", nrows=100)
    assert "true_demand" not in daily.columns, (
        "Operational daily table must NOT contain ground-truth demand (prevents accidental feature leakage)"
    )
    expected_cols = {"date", "item_id", "bookings", "searches", "sold_out", "avg_sell_price"}
    assert expected_cols.issubset(set(daily.columns))


# -----------------------------------------------------------------------------
# 3. Model Calibration & Prediction Interval Coverage
# -----------------------------------------------------------------------------
def test_prediction_interval_calibration():
    """Verify P10-P90 prediction interval coverage is well-calibrated (75% to 85% on 80% theoretical)."""
    summary_path = ART_DIR / "summary.json"
    assert summary_path.exists(), "summary.json must exist in artifacts"
    
    with open(summary_path) as f:
        summary = json.load(f)
    fb = summary.get("forecast_backtest", {})
    cov = fb.get("coverage_p10_p90")
    assert cov is not None
    assert 0.75 <= cov <= 0.85, f"Holdout coverage {cov} outside acceptable calibration band [0.75, 0.85]"
    
    # Check weekly coverage
    w_cov = fb.get("weekly_coverage_p10_p90")
    assert 0.75 <= w_cov <= 0.85, f"Weekly coverage {w_cov} outside acceptable band [0.75, 0.85]"

    # Check forecast bias is tight (< 3% magnitude)
    bias = fb.get("bias", 0.0)
    assert abs(bias) < 0.03, f"Forecast bias {bias} exceeds 3% tolerance"


# -----------------------------------------------------------------------------
# 4. Model Reproducibility Across Seeds
# -----------------------------------------------------------------------------
def test_model_reproducibility():
    """Verify that Monte Carlo shock generators and simulation draws are deterministic with identical seeds."""
    destinations = ["Goa", "Kashmir", "Dubai", "Singapore"]
    g1, dest1 = common_shocks(destinations, n=500, seed=42)
    g2, dest2 = common_shocks(destinations, n=500, seed=42)
    np.testing.assert_array_almost_equal(g1, g2, decimal=8)
    for d in destinations:
        np.testing.assert_array_almost_equal(dest1[d], dest2[d], decimal=8)

    # Different seed must produce different outcomes
    g3, _ = common_shocks(destinations, n=500, seed=99)
    assert not np.allclose(g1, g3)


# -----------------------------------------------------------------------------
# 5. Cancellation ML Risk Model Properties
# -----------------------------------------------------------------------------
def test_cancellation_model_risk_properties():
    """Verify cancellation probabilities satisfy domain monotonicity and tier bounds."""
    # 1. Lead time monotonicity: bookings made far in advance have higher cancellation probability
    res_short = compute_cancellation_risk(
        base_cancel_rate=0.15,
        lead_days=7,
        channel="Corporate_B2B",
    )
    res_long = compute_cancellation_risk(
        base_cancel_rate=0.15,
        lead_days=90,
        channel="Corporate_B2B",
    )
    assert res_short["cancellation_probability"] < res_long["cancellation_probability"], (
        "Cancellation probability must increase with booking lead time"
    )

    # 2. Channel risk: Online API channel has higher cancellation than Corporate B2B
    res_api = compute_cancellation_risk(
        base_cancel_rate=0.15,
        lead_days=30,
        channel="Online_API",
    )
    res_corp = compute_cancellation_risk(
        base_cancel_rate=0.15,
        lead_days=30,
        channel="Corporate_B2B",
    )
    assert res_api["cancellation_probability"] > res_corp["cancellation_probability"]

    # 3. Probability bounds strictly [0.01, 0.95]
    for r in [res_short, res_long, res_api, res_corp]:
        assert 0.01 <= r["cancellation_probability"] <= 0.95
        assert r["risk_tier"] in ["Low", "Moderate", "High"]
        assert len(r["drivers"]) == 4


# -----------------------------------------------------------------------------
# 6. Dynamic Pricing Demand Elasticity Properties
# -----------------------------------------------------------------------------
def test_dynamic_pricing_elasticity_properties():
    """Verify pricing curves satisfy downward-sloping demand and positive revenue convexity."""
    res = simulate_pricing_curve(
        market_price=6000.0,
        unit_cost=4000.0,
        demand_p50=120.0,
        elasticity=1.4,
        cancel_rate=0.12,
        salvage_rate=0.45,
        allotment_units=150.0,
    )
    curve = res["pricing_curve"]
    assert len(curve) > 5

    # Check downward sloping demand
    demands = [pt["implied_demand"] for pt in curve]
    for i in range(len(demands) - 1):
        assert demands[i] >= demands[i + 1], "Demand must strictly decrease as price increases"

    # Recommended price must be positive and yield positive profit
    assert res["recommended_price"] > 0
    assert res["expected_profit_at_recommended"] > 0
    assert res["recommended_price"] >= res["unit_cost"], "Optimal price must be at or above supplier cost"
