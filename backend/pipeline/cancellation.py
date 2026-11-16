"""Cancellation Risk Prediction Module for TBO Inventory Intelligence.

Features:
- Predicts cancellation probability per item-week / booking condition
- Analyzes key drivers: lead time, channel, seasonality, destination type, holiday proximity
- Classifies risk into tiers: Low (<15%), Moderate (15-30%), High (>30%)
- Supplies risk adjustments to the Newsvendor critical ratio and portfolio Monte Carlo
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


CHANNEL_WEIGHTS = {
    "Corporate_B2B": 0.85,    # Corporate business travel has lower cancellation rates
    "Leisure_Agent": 1.05,    # Standard agency leisure bookings
    "Online_API": 1.25,       # Instant API feeds have higher searcher churn / rebooking
    "Group_Tour": 0.70,       # Group allotments have strict contractual cancellation
}


def compute_cancellation_risk(
    base_cancel_rate: float,
    lead_days: int = 45,
    channel: str = "Leisure_Agent",
    is_international: bool = False,
    holiday_intensity: float = 0.0,
    event_intensity: float = 0.0,
    month: int = 11,
) -> Dict:
    """Computes calibrated cancellation probability and key driver impacts.

    Cancellation probability increases with:
    - Longer advance booking lead times (plans change)
    - High holiday/event intensity (speculative bookings)
    - Dynamic API channels
    Cancellation probability decreases with:
    - International destinations (visa/passport requirements commit travelers)
    - Shorter lead times
    """
    # 1. Lead time multiplier (e.g., 90-day lead has higher cancellation risk than 7-day)
    lead_multiplier = 0.70 + 0.50 * (min(lead_days, 120) / 120.0) ** 0.8
    
    # 2. Channel multiplier
    channel_multiplier = CHANNEL_WEIGHTS.get(channel, 1.0)
    
    # 3. Destination commitment factor
    dest_factor = 0.82 if is_international else 1.0
    
    # 4. Holiday/Event pressure factor
    pressure_factor = 1.0 + 0.25 * holiday_intensity + 0.15 * event_intensity
    
    # Adjusted probability
    raw_prob = base_cancel_rate * lead_multiplier * channel_multiplier * dest_factor * pressure_factor
    prob = float(np.clip(raw_prob, 0.02, 0.55))
    
    # Risk Tier
    if prob < 0.15:
        tier = "Low"
        tone = "green"
    elif prob <= 0.30:
        tier = "Moderate"
        tone = "amber"
    else:
        tier = "High"
        tone = "red"
        
    # Driver decomposition
    drivers = [
        {
            "name": "Booking Lead Time",
            "impact": round((lead_multiplier - 1.0) * 100, 1),
            "detail": f"{lead_days} days advance booking window",
        },
        {
            "name": "Distribution Channel",
            "impact": round((channel_multiplier - 1.0) * 100, 1),
            "detail": channel.replace("_", " "),
        },
        {
            "name": "Market Type",
            "impact": round((dest_factor - 1.0) * 100, 1),
            "detail": "International (Higher commitment)" if is_international else "Domestic",
        },
        {
            "name": "Peak Travel Demand",
            "impact": round((pressure_factor - 1.0) * 100, 1),
            "detail": f"Holiday intensity: {holiday_intensity:.2f}",
        },
    ]
    
    return {
        "cancellation_probability": round(prob, 4),
        "cancellation_pct": round(prob * 100, 1),
        "risk_tier": tier,
        "risk_tone": tone,
        "base_historical_rate": round(base_cancel_rate, 4),
        "drivers": drivers,
        "recommendation": (
            "Standard allotment terms acceptable; low forfeiture risk." if tier == "Low" else
            "Monitor rebooking trends; align with high-salvage bedbank suppliers." if tier == "Moderate" else
            "High cancellation exposure: demand non-refundable client terms or increase procurement salvage rate."
        ),
    }


def analyze_portfolio_cancellations(candidates_df: pd.DataFrame) -> Dict:
    """Portfolio-level cancellation vulnerability analytics."""
    viable = candidates_df[candidates_df.viable]
    rates = viable.cancel_rate.values
    
    low_pct = float(np.mean(rates < 0.15))
    mod_pct = float(np.mean((rates >= 0.15) & (rates <= 0.30)))
    high_pct = float(np.mean(rates > 0.30))
    avg_rate = float(np.mean(rates))
    
    return {
        "average_cancellation_rate": round(avg_rate, 4),
        "tier_distribution": {
            "low": round(low_pct, 3),
            "moderate": round(mod_pct, 3),
            "high": round(high_pct, 3),
        },
        "high_risk_positions_count": int(np.sum(rates > 0.30)),
        "total_viable_positions": int(len(viable)),
    }
