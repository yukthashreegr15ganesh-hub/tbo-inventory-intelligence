"""Plain-English and structured explanations of a recommendation for TBO Inventory Intelligence.

Produces comprehensive, deterministic operational explanations addressing:
- Why the inventory position was selected
- Why the specific quantity was chosen (Newsvendor critical ratio + scenario stress analysis)
- Expected demand and price expectations
- Capital investment and expected profit
- Identified risks (cancellation, sold-outs, price sensitivity)
- Why alternative strategies were rejected (waiting, over-buying)
"""
import json
import os
import urllib.request


def _inr(x):
    x = float(x)
    if abs(x) >= 1e7:
        return f"₹{x / 1e7:.2f} Cr"
    if abs(x) >= 1e5:
        return f"₹{x / 1e5:.1f} L"
    return f"₹{x:,.0f}"


def structured_explanation(r: dict) -> dict:
    drivers = ", ".join(f"{d['driver'].lower()} ({'+' if d['effect'] >= 0 else ''}{d['effect']:.0f}%)"
                        for d in r.get("drivers", [])[:3])
    ev = f" overlaps with {', '.join(r['events'])}" if r.get("events") else "normal calendar window"
    so = r.get("sold_out_risk", 0)
    cr = r.get("cancel_rate", 0)
    units = r.get("units", 0)
    unit_cost = r.get("unit_cost", 0)
    cost_if_wait = r.get("cost_if_wait", unit_cost)
    saving = max(0.0, (cost_if_wait - unit_cost) * units)

    dest = r.get("destination", "this destination")
    name = r.get("name", "this inventory")
    # 1. Selection Reason
    selection_reason = (
        f"Selected {name} for high risk-adjusted margin and demand certainty in {dest}. "
        f"Historically, supply in this travel week experiences a {so:.0%} sold-out rate, making early pre-buy "
        f"crucial to secure inventory that wholesalers would otherwise lose to market exhaustion."
    )

    # 2. Quantity Rationale
    quantity_rationale = (
        f"Recommended {units} {r.get('unit', 'unit')}s based on the Newsvendor critical ratio balancing "
        f"unsold allotment salvage risk against stockout opportunity cost. Forecast demand is {r.get('demand_p50', 0):.0f} "
        f"(P10: {r.get('demand_p10', 0):.0f}, P90: {r.get('demand_p90', 0):.0f}), resulting in an expected sell-through of {r.get('sell_through', 0):.0%}."
    )

    # 3. Financial Outlook
    financial_outlook = (
        f"Requires {_inr(r.get('investment', 0))} capital at {_inr(unit_cost)}/{r.get('unit', 'unit')}. "
        f"Generates an expected profit of {_inr(r.get('expected_profit', 0))}. Securing this before {r.get('buy_by', 'deadline')} "
        f"locks in procurement savings of {_inr(saving)} compared to spot market rates."
    )

    # 4. Risk Analysis
    risk_analysis = (
        f"Cancellation risk is estimated at {cr:.1%}. In the worst 5% of simulated demand scenarios, "
        f"profit remains protected at {_inr(r.get('worst5_profit', 0))}. Drivers include {drivers} ({ev})."
    )

    # 5. Rejected Alternatives
    rejected_alternatives = (
        f"Alternative 1 (Higher Quantity): Rejected because additional units beyond {units} have diminished marginal profit "
        f"and exceed downside tail risk limits. Alternative 2 (Spot/Last-Minute Buying): Rejected because supplier rates inflate "
        f"to {_inr(cost_if_wait)}/{r.get('unit', 'unit')}, eroding profit margins by {_inr(saving)}."
    )

    full_text = f"{selection_reason} {quantity_rationale} {financial_outlook} {risk_analysis} {rejected_alternatives}"

    return {
        "full_text": full_text,
        "selection_reason": selection_reason,
        "quantity_rationale": quantity_rationale,
        "financial_outlook": financial_outlook,
        "risk_analysis": risk_analysis,
        "rejected_alternatives": rejected_alternatives,
    }


def template_explanation(r: dict) -> str:
    return structured_explanation(r)["full_text"]


def llm_explanation(r: dict) -> str | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    facts = {k: r[k] for k in ["name", "destination", "item_type", "week", "units", "unit", "unit_cost", "investment",
                               "buy_by", "cost_if_wait", "sell_price", "market_price", "demand_p10", "demand_p50",
                               "demand_p90", "expected_profit", "worst5_profit", "sell_through", "sold_out_risk",
                               "cancel_rate", "events", "drivers"] if k in r}
    prompt = ("You are an inventory analyst at TBO.com, a B2B travel distributor. In at most 90 words, explain to a "
              "procurement manager why the system recommends this pre-buy, and name the single biggest risk. "
              "Use INR (crore/lakh). Facts (JSON):\n" + json.dumps(facts, default=str))
    body = json.dumps({"model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5"), "max_tokens": 300,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        return "".join(b.get("text", "") for b in data.get("content", []))
    except Exception as e:
        return f"(LLM explanation unavailable: {e})"
