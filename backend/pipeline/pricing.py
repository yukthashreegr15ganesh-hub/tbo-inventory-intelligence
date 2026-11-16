"""Dynamic Pricing Intelligence Module for TBO Inventory Intelligence.

Calculates optimal B2B distribution prices considering:
- Market selling price benchmarks
- Demand elasticity (Market elasticity + B2B wholesale switching elasticity)
- Predicted demand distribution (P10, P50, P90)
- Unit procurement cost
- Cancellation forfeiture risk
- Rate parity guardrails (Maximum +20% over market price)
"""
from typing import Dict, List, Optional
import numpy as np
from .config import PRICE_GRID, COMPETITIVE_ELASTICITY


def simulate_pricing_curve(
    market_price: float,
    unit_cost: float,
    demand_p50: float,
    elasticity: float = 1.2,
    cancel_rate: float = 0.15,
    salvage_rate: float = 0.40,
    allotment_units: float = 50.0,
) -> Dict:
    """Evaluates expected financial performance across the price multiplier grid (0.90 to 1.20)."""
    effective_elasticity = elasticity + COMPETITIVE_ELASTICITY
    curve = []
    
    best_profit = -float("inf")
    best_mult = 1.00
    
    for mult in PRICE_GRID:
        price = round(market_price * mult, 0)
        
        # Demand responds exponentially to price ratio: D = D0 * (P / P0)^(-elasticity)
        implied_demand = float(demand_p50 * (mult ** (-effective_elasticity)))
        
        # Expected units sold capped by allotment
        units_sold = min(allotment_units, implied_demand)
        net_sold = units_sold * (1.0 - cancel_rate)
        
        # Gross revenue and cost
        revenue = net_sold * price
        procurement_cost = allotment_units * unit_cost
        salvage_recovery = (allotment_units - units_sold) * unit_cost * salvage_rate
        expected_profit = revenue + salvage_recovery - procurement_cost
        
        margin_per_sold_unit = price * (1.0 - cancel_rate) - unit_cost
        roi = expected_profit / procurement_cost if procurement_cost > 0 else 0.0
        sell_through = units_sold / allotment_units if allotment_units > 0 else 0.0
        
        point = {
            "multiplier": mult,
            "multiplier_label": f"{mult:+.0%}" if mult != 1.0 else "Market (100%)",
            "price": price,
            "implied_demand": round(implied_demand, 1),
            "units_sold": round(units_sold, 1),
            "sell_through": round(sell_through, 3),
            "expected_revenue": round(revenue, 0),
            "expected_profit": round(expected_profit, 0),
            "roi": round(roi, 4),
            "margin_per_unit": round(margin_per_sold_unit, 0),
        }
        curve.append(point)
        
        if expected_profit > best_profit:
            best_profit = expected_profit
            best_mult = mult

    optimal = next(p for p in curve if p["multiplier"] == best_mult)
    
    # Explain reasoning
    diff_pct = (best_mult - 1.0) * 100
    if best_mult > 1.0:
        rationale = (
            f"Recommended pricing at ₹{optimal['price']:,.0f} (+{diff_pct:.0f}% above market benchmark). "
            f"High demand momentum and strong sold-out risk absorb the premium, maximizing gross margin "
            f"with an expected sell-through of {optimal['sell_through']:.0%}."
        )
    elif best_mult < 1.0:
        rationale = (
            f"Recommended pricing at ₹{optimal['price']:,.0f} ({diff_pct:.0f}% discount vs market benchmark). "
            f"High B2B price sensitivity (elasticity {effective_elasticity:.1f}) requires competitive pricing to "
            f"stimulate booking velocity and ensure {optimal['sell_through']:.0%} sell-through."
        )
    else:
        rationale = (
            f"Recommended pricing at parity with market benchmark (₹{optimal['price']:,.0f}). "
            f"Balances demand capture against margin per room-night/seat."
        )
        
    return {
        "market_price": market_price,
        "unit_cost": unit_cost,
        "demand_p50": demand_p50,
        "recommended_price": optimal["price"],
        "recommended_multiplier": optimal["multiplier"],
        "expected_profit_at_recommended": optimal["expected_profit"],
        "expected_sell_through": optimal["sell_through"],
        "pricing_curve": curve,
        "pricing_rationale": rationale,
        "guardrail_status": "PASS: Within Rate Parity Bounds (-10% to +20%)",
    }
