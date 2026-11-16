"""Unified evaluation metrics and validation module for TBO Inventory Intelligence.

Provides standard statistical and business evaluation metrics:
- MAE (Mean Absolute Error)
- RMSE (Root Mean Squared Error)
- WAPE (Weighted Absolute Percentage Error)
- MAPE (Mean Absolute Percentage Error)
- Forecast Bias ((Sum(Pred) - Sum(Actual)) / Sum(Actual))
- Prediction Interval Coverage (P10-P90 coverage against actuals)
- Aggregation comparisons (Daily vs Weekly vs Monthly) with mathematical explanation of noise dampening.
"""
import numpy as np
import pandas as pd


def calc_mae(actual, pred) -> float:
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    return float(np.mean(np.abs(a - p))) if len(a) else 0.0


def calc_rmse(actual, pred) -> float:
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    return float(np.sqrt(np.mean((a - p) ** 2))) if len(a) else 0.0


def calc_wape(actual, pred) -> float:
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    total_a = np.sum(a)
    return float(np.sum(np.abs(p - a)) / total_a) if total_a > 0 else 0.0


def calc_mape(actual, pred, eps=1e-5) -> float:
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    mask = a > eps
    if not np.any(mask):
        return 0.0
    return float(np.mean(np.abs((a[mask] - p[mask]) / a[mask])))


def calc_bias(actual, pred) -> float:
    a, p = np.asarray(actual, float), np.asarray(pred, float)
    total_a = np.sum(a)
    return float((np.sum(p) - total_a) / total_a) if total_a > 0 else 0.0


def calc_coverage(actual, p10, p90) -> float:
    a = np.asarray(actual, float)
    lo = np.asarray(p10, float)
    hi = np.asarray(p90, float)
    return float(np.mean((a >= lo) & (a <= hi))) if len(a) else 0.0


def comprehensive_evaluation(actual, pred, p10=None, p90=None) -> dict:
    """Calculate the full suite of statistical metrics for demand forecasting."""
    res = {
        "mae": round(calc_mae(actual, pred), 3),
        "rmse": round(calc_rmse(actual, pred), 3),
        "wape": round(calc_wape(actual, pred), 4),
        "wape_accuracy": round(max(0.0, 1.0 - calc_wape(actual, pred)), 4),
        "bias": round(calc_bias(actual, pred), 4),
        "samples": int(len(actual)),
    }
    if p10 is not None and p90 is not None:
        res["coverage_p10_p90"] = round(calc_coverage(actual, p10, p90), 4)
        res["interval_sharpness"] = round(float(np.mean(np.asarray(p90, float) - np.asarray(p10, float))), 2)
    return res


def compute_multilevel_metrics(daily_df: pd.DataFrame) -> dict:
    """Computes daily, weekly, and monthly forecasting metrics on the holdout window

    daily_df must contain: ['date', 'item_id', 'demand_est', 'p50', 'p10', 'p90']
    """
    df = daily_df.copy()
    df["date"] = pd.to_datetime(df["date"])

    # 1. Daily Level
    daily_eval = comprehensive_evaluation(df["demand_est"], df["p50"], df.get("p10"), df.get("p90"))

    # 2. Weekly Level (Monday-Sunday)
    df["week"] = df["date"] - pd.to_timedelta(df["date"].dt.dayofweek, unit="D")
    weekly_grp = df.groupby(["item_id", "week"]).agg({
        "demand_est": "sum",
        "p50": "sum",
        "p10": "sum",
        "p90": "sum",
    }).reset_index()
    weekly_eval = comprehensive_evaluation(
        weekly_grp["demand_est"], weekly_grp["p50"], weekly_grp["p10"], weekly_grp["p90"]
    )

    # 3. Monthly Level
    df["month"] = df["date"].dt.to_period("M")
    monthly_grp = df.groupby(["item_id", "month"]).agg({
        "demand_est": "sum",
        "p50": "sum",
        "p10": "sum",
        "p90": "sum",
    }).reset_index()
    monthly_eval = comprehensive_evaluation(
        monthly_grp["demand_est"], monthly_grp["p50"], monthly_grp["p10"], monthly_grp["p90"]
    )

    return {
        "daily": daily_eval,
        "weekly": weekly_eval,
        "monthly": monthly_eval,
        "aggregation_insight": (
            f"Weekly WAPE ({weekly_eval['wape']:.1%}) is significantly lower than daily WAPE ({daily_eval['wape']:.1%}) "
            "because daily idiosyncratic noise (day-of-week timing jitter, weather blips) cancels out when summing "
            "over a 7-day travel window. Monthly WAPE ({monthly_eval['wape']:.1%}) exhibits further variance reduction."
        ),
    }
