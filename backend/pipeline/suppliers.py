"""Supplier Intelligence Module for TBO Inventory Intelligence.

Evaluates and benchmarks multiple inventory suppliers:
- Direct Property / Airline Contract
- Global Bedbank & Consolidator (e.g. Hotelbeds / Amadeus)
- Regional Wholesaler
- Aggregator / Marketplace Pool

Provides multi-criteria supplier scoring:
- Cost competitiveness
- Availability & allotment capacity
- Reliability / SLA fulfillment score
- Lead-time flexibility
- Refund / salvage policies on cancellations
- Historical fulfillment performance
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd


# Default supplier archetypes for travel inventory procurement
SUPPLIER_PROFILES = [
    {
        "id": "SUP-DIRECT",
        "name": "Direct Contract (Hotel / Airline)",
        "tier": "Primary Direct",
        "cost_multiplier_offset": -0.04,  # 4% cheaper at long lead times
        "reliability_score": 0.98,        # 98% fulfillment SLA
        "allotment_factor": 1.2,          # High direct allotment
        "salvage_rate_offset": -0.10,     # Stricter refund policy
        "min_lead_days": 21,              # Needs advance commitment
        "cancellation_lead_days": 14,
        "rating": "A+",
        "features": ["Best Base Pricing", "Guaranteed Room Category", "Strict Cutoff"],
    },
    {
        "id": "SUP-BEDBANK",
        "name": "Global Bedbank / GDS Consolidator",
        "tier": "Global Wholesaler",
        "cost_multiplier_offset": 0.02,   # Slight premium
        "reliability_score": 0.94,        # 94% fulfillment SLA
        "allotment_factor": 1.5,          # Very large allotment
        "salvage_rate_offset": 0.15,      # More generous refund/salvage
        "min_lead_days": 7,               # Flexible lead time
        "cancellation_lead_days": 7,
        "rating": "A",
        "features": ["High Allotment Depth", "Flexible Cancellation", "Short Lead Time"],
    },
    {
        "id": "SUP-REGIONAL",
        "name": "Regional DMC / Local Wholesaler",
        "tier": "Regional Partner",
        "cost_multiplier_offset": -0.01,  # Balanced cost
        "reliability_score": 0.90,        # 90% fulfillment SLA
        "allotment_factor": 0.8,          # Lower allotment cap
        "salvage_rate_offset": 0.00,      # Standard refund
        "min_lead_days": 14,
        "cancellation_lead_days": 10,
        "rating": "B+",
        "features": ["Local Ground Support", "Competitive Peak Pricing"],
    },
    {
        "id": "SUP-MARKET",
        "name": "Dynamic Marketplace Aggregator",
        "tier": "Dynamic Secondary",
        "cost_multiplier_offset": 0.07,   # Higher spot cost
        "reliability_score": 0.88,        # Variable fulfillment
        "allotment_factor": 2.0,          # On-demand buffer
        "salvage_rate_offset": 0.20,      # Highest salvage flexibility
        "min_lead_days": 3,               # Last-minute availability
        "cancellation_lead_days": 3,
        "rating": "B",
        "features": ["Last-minute Top-up", "Spot Liquidity", "Higher Cost"],
    },
]


def evaluate_suppliers_for_item(
    item_id: str,
    item_name: str,
    item_type: str,
    destination: str,
    unit_cost_base: float,
    market_price: float,
    allotment_base: float,
    salvage_base: float,
    demand_p50: float,
    lead_days_available: int = 45,
) -> Dict:
    """Evaluate all available suppliers for an item-week position and rank them."""
    options = []
    
    for s in SUPPLIER_PROFILES:
        # Check lead time constraint
        is_feasible = lead_days_available >= s["min_lead_days"]
        
        # Calculate supplier specific unit cost
        cost_mult = 1.0 + s["cost_multiplier_offset"]
        if lead_days_available < 14:
            cost_mult += 0.05  # Late booking surcharge
        supplier_cost = round(unit_cost_base * cost_mult, 0)
        
        # Allotment cap
        allotment = int(round(allotment_base * s["allotment_factor"]))
        
        # Salvage rate (capped between 0.10 and 0.85)
        salvage = round(float(np.clip(salvage_base + s["salvage_rate_offset"], 0.10, 0.85)), 2)
        
        # Gross margin at market price
        gross_margin = market_price - supplier_cost
        gross_margin_pct = round(gross_margin / market_price, 3) if market_price > 0 else 0.0
        
        # Risk-adjusted score (Cost, Reliability, Salvage, Allotment)
        # Higher margin, higher reliability, and higher salvage give higher score
        margin_score = np.clip(gross_margin_pct / 0.30, 0.0, 1.0) * 40.0
        reliability_score = s["reliability_score"] * 30.0
        flexibility_score = (salvage / 0.80) * 20.0
        lead_score = (1.0 if is_feasible else 0.2) * 10.0
        
        composite_score = round(float(margin_score + reliability_score + flexibility_score + lead_score), 1)
        
        options.append({
            "supplier_id": s["id"],
            "supplier_name": s["name"],
            "tier": s["tier"],
            "rating": s["rating"],
            "unit_cost": supplier_cost,
            "cost_diff_vs_base": round(supplier_cost - unit_cost_base, 0),
            "cost_diff_pct": round((supplier_cost / unit_cost_base - 1.0) * 100, 1) if unit_cost_base > 0 else 0.0,
            "allotment_capacity": allotment,
            "reliability_score": s["reliability_score"],
            "salvage_rate": salvage,
            "min_lead_days": s["min_lead_days"],
            "cancellation_lead_days": s["cancellation_lead_days"],
            "is_lead_feasible": is_feasible,
            "gross_margin": gross_margin,
            "gross_margin_pct": gross_margin_pct,
            "composite_score": composite_score,
            "features": s["features"],
        })
    
    # Sort options: feasible first, then by composite score descending
    options.sort(key=lambda x: (1 if x["is_lead_feasible"] else 0, x["composite_score"]), reverse=True)
    best = options[0]
    
    # Generate explainable rationale for supplier recommendation
    runner_up = options[1] if len(options) > 1 else None
    if best["supplier_id"] == "SUP-DIRECT":
        rationale = (
            f"Recommended '{best['supplier_name']}' ({best['rating']}) because it delivers the lowest procurement cost "
            f"(₹{best['unit_cost']:,.0f}, saving {abs(best['cost_diff_pct']):.1f}%) and highest reliability ({best['reliability_score']:.0%}). "
            f"Lead time of {lead_days_available} days satisfies the {best['min_lead_days']}-day cutoff requirement."
        )
    elif best["supplier_id"] == "SUP-BEDBANK":
        rationale = (
            f"Recommended '{best['supplier_name']}' due to superior allotment depth ({best['allotment_capacity']} units) "
            f"and higher cancellation salvage ({best['salvage_rate']:.0%}), protecting downside risk despite a slight price premium."
        )
    else:
        rationale = (
            f"Selected '{best['supplier_name']}' based on balanced SLA reliability ({best['reliability_score']:.0%}) "
            f"and lead-time feasibility for this travel window."
        )
        
    return {
        "item_id": item_id,
        "item_name": item_name,
        "item_type": item_type,
        "destination": destination,
        "market_price": market_price,
        "demand_p50": demand_p50,
        "lead_days_available": lead_days_available,
        "recommended_supplier": best,
        "runner_up_supplier": runner_up,
        "all_suppliers": options,
        "selection_rationale": rationale,
    }


def get_supplier_benchmarks_summary(candidates_df: pd.DataFrame, limit: int = 25) -> List[Dict]:
    """Generates supplier comparison reports across top candidate positions."""
    records = []
    viable = candidates_df[candidates_df.viable].sort_values("opportunity_score", ascending=False).head(limit)
    
    for row in viable.itertuples():
        eval_res = evaluate_suppliers_for_item(
            item_id=str(row.item_id),
            item_name=str(row.name),
            item_type=str(row.item_type),
            destination=str(row.destination),
            unit_cost_base=float(row.unit_cost),
            market_price=float(row.market_price),
            allotment_base=float(row.max_allotment),
            salvage_base=float(row.salvage_rate),
            demand_p50=float(row.demand_p50),
            lead_days_available=int(getattr(row, "buy_lead_days", 45)),
        )
        records.append({
            "cand_id": str(row.cand_id),
            "week": str(row.week),
            **eval_res,
        })
    return records
