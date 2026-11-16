"""What-If Simulation Engine for TBO Inventory Intelligence.

Simulates macroeconomic and operational shocks:
- Demand shift (+/- %)
- Supplier procurement cost shocks (+/- %)
- Cancellation rate shocks (+/- %)
- Budget adjustments
- Risk aversion changes

Immediately calculates impact across:
- Capital deployed & budget utilization
- Expected profit & ROI
- Worst-case profit (CVaR 10%)
- Tail risk & loss probability
- Strategy profile comparison (Aggressive, Balanced, Conservative)
"""
from typing import Dict, List, Optional
import numpy as np
import pandas as pd
from .optimizer import Optimizer


def run_what_if_simulation(
    optimizer: Optimizer,
    base_budget: float = 75e7,
    demand_shock_pct: float = 0.0,       # e.g. +10% or -20%
    supplier_cost_shock_pct: float = 0.0, # e.g. +5% or -10%
    cancellation_shock_pct: float = 0.0,  # e.g. +15%
    risk_aversion: float = 0.30,
    max_dest_share: float = 0.30,
    item_types: tuple = ("Hotel", "Flight"),
    destinations: Optional[List[str]] = None,
) -> Dict:
    """Runs a complete what-if scenario by applying parameter shocks and re-evaluating."""
    # Build modified optimizer blocks
    d_mult = max(0.2, 1.0 + demand_shock_pct / 100.0)
    c_mult = max(0.5, 1.0 + supplier_cost_shock_pct / 100.0)
    cancel_mult = max(0.2, 1.0 + cancellation_shock_pct / 100.0)
    
    # We create a temporary perturbed candidate set & blocks
    cands_p = optimizer.cands.copy()
    cands_p["unit_cost"] = np.round(cands_p["unit_cost"] * c_mult, 0)
    cands_p["demand_p50"] = np.round(cands_p["demand_p50"] * d_mult, 1)
    cands_p["cancel_rate"] = np.clip(cands_p["cancel_rate"] * cancel_mult, 0.01, 0.60)
    
    # Clone and perturb blocks
    blocks_p = []
    for b in optimizer.blocks:
        bp = {
            "cand_id": b["cand_id"],
            "levels": b["levels"].copy(),
            "block_cost": np.round(b["block_cost"] * c_mult, 0),
            "exp_sold_levels": np.round(b["exp_sold_levels"] * d_mult, 1),
            # Profit levels reflect demand change and cost change
            "profit_levels": (b["profit_levels"] * d_mult - (c_mult - 1.0) * b["block_cost"].sum()).astype(np.float32),
        }
        # recompute block expected deltas
        deltas = np.diff(bp["profit_levels"], axis=1)
        bp["block_exp"] = deltas.mean(axis=0)
        k_tail = max(1, int(0.10 * deltas.shape[0]))
        bp["block_cvar"] = np.sort(deltas, axis=0)[:k_tail].mean(axis=0)
        blocks_p.append(bp)
        
    sim_opt = Optimizer(cands_p, blocks_p)
    
    # Run the user's specific scenario
    scenario_res = sim_opt.solve(
        budget=base_budget,
        lam=risk_aversion,
        max_dest_share=max_dest_share,
        item_types=item_types,
        destinations=destinations,
        time_limit=10,
    )
    
    # Run 3 strategy benchmarks for this scenario:
    # 1. Aggressive (lambda = 0.05)
    agg_res = sim_opt.solve(budget=base_budget, lam=0.05, max_dest_share=max_dest_share,
                            item_types=item_types, destinations=destinations, time_limit=6)
    # 2. Balanced (lambda = 0.30)
    bal_res = sim_opt.solve(budget=base_budget, lam=0.30, max_dest_share=max_dest_share,
                            item_types=item_types, destinations=destinations, time_limit=6)
    # 3. Conservative (lambda = 0.70)
    con_res = sim_opt.solve(budget=base_budget, lam=0.70, max_dest_share=max_dest_share,
                            item_types=item_types, destinations=destinations, time_limit=6)
                            
    def _extract_strat(name, res, l):
        st = res["stats"]
        return {
            "name": name,
            "lambda": l,
            "invested": st["invested"],
            "budget_used_pct": st["budget_used"],
            "expected_profit": st["expected_profit"],
            "worst_10_profit": st["cvar10"],
            "roi": st["roi"],
            "prob_loss": st["prob_loss"],
            "units": st["units"],
        }
        
    strategies = [
        _extract_strat("Aggressive (Profit Maximizer)", agg_res, 0.05),
        _extract_strat("Balanced (Recommended)", bal_res, 0.30),
        _extract_strat("Conservative (Capital Protection)", con_res, 0.70),
    ]
    
    # Financial downside sensitivity assessment
    baseline_stats = optimizer.evaluate(scenario_res["k_sel"])
    profit_diff = scenario_res["stats"]["expected_profit"] - baseline_stats["expected_profit"]
    
    return {
        "inputs": {
            "budget": base_budget,
            "demand_shock_pct": demand_shock_pct,
            "supplier_cost_shock_pct": supplier_cost_shock_pct,
            "cancellation_shock_pct": cancellation_shock_pct,
            "risk_aversion": risk_aversion,
            "max_dest_share": max_dest_share,
        },
        "stats": scenario_res["stats"],
        "strategies": strategies,
        "sensitivity": {
            "profit_impact_vs_nominal": round(profit_diff, 0),
            "profit_impact_pct": round(profit_diff / baseline_stats["expected_profit"] * 100, 1) if baseline_stats["expected_profit"] else 0.0,
            "cvar_impact": round(scenario_res["stats"]["cvar10"] - baseline_stats["cvar10"], 0),
        },
        "scenario_summary": (
            f"Under a {demand_shock_pct:+.0f}% demand shock, {supplier_cost_shock_pct:+.0f}% supplier cost shock, "
            f"and {cancellation_shock_pct:+.0f}% cancellation shock, the optimizer deploys ₹{scenario_res['stats']['invested']/1e7:.1f} Cr "
            f"({scenario_res['stats']['budget_used']:.0%} of budget), yielding expected profit of ₹{scenario_res['stats']['expected_profit']/1e7:.2f} Cr "
            f"(ROI {scenario_res['stats']['roi']:.1%}) with worst-10% profit protected at ₹{scenario_res['stats']['cvar10']/1e7:.2f} Cr."
        ),
    }
