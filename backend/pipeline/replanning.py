"""Automated Inventory Replanning & Audit Engine for TBO Inventory Intelligence.

Monitors operational trigger events:
- Material demand shifts
- Supplier rate updates
- Inventory availability / allotment changes
- Budget reallocation
- Cancellation surge alerts

Computes Plan Deltas:
- Positions to expand (BUY MORE)
- Positions to trim (REDUCE)
- New positions to enter (NEW ENTRY)
- Positions to liquidate / drop (EXIT)

Provides Approval Workflow:
- Automatic Approval Mode (within configurable threshold, e.g. <5% capital change)
- Manual Approval Workflow with State Machine:
  [PROPOSED] -> [PENDING_APPROVAL] -> [APPROVED / REJECTED]
- Comprehensive Audit Log
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
from .config import ART_DIR
from .database import (
    init_db,
    db_save_replan,
    db_get_replan_history,
    db_update_replan_status,
)

# Persistent file path fallback
_STATE_FILE = ART_DIR / "replan_state.json"

# Initialize database schema
try:
    init_db()
except Exception as e:
    print(f"Database init warning: {e}")


def _load_state():
    # 1. Try loading from Database
    try:
        db_history = db_get_replan_history()
        if db_history:
            # Active plan from state file if available
            active = None
            if _STATE_FILE.exists():
                try:
                    data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
                    active = data.get("active_plan")
                except Exception:
                    pass
            return db_history, active
    except Exception as e:
        print(f"Warning: Failed to query database replan history: {e}")

    # 2. Fallback to file system
    if _STATE_FILE.exists():
        try:
            data = json.loads(_STATE_FILE.read_text(encoding="utf-8"))
            h = data.get("history", [])
            # Seed into DB
            for item in h:
                try:
                    db_save_replan(item)
                except Exception:
                    pass
            return h, data.get("active_plan", None)
        except Exception:
            return [], None
    return [], None


def _save_state(history: List[Dict], active_plan: Optional[List[Dict]]):
    # 1. Save to Database
    for item in history[:10]:
        try:
            db_save_replan(item, current_plan=active_plan)
        except Exception as e:
            pass

    # 2. Save to file system fallback
    try:
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        _STATE_FILE.write_text(
            json.dumps({"history": history, "active_plan": active_plan}, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception as e:
        print(f"Warning: Failed to persist replan state to disk: {e}")


# Initialize from disk if available
_REPLAN_HISTORY, _CURRENT_ACTIVE_PLAN = _load_state()


def calculate_plan_delta(old_plan: List[Dict], new_plan: List[Dict]) -> Dict:
    """Compares previous active plan against new optimized plan and computes position-level deltas."""
    old_map = {r["cand_id"]: r for r in (old_plan or [])}
    new_map = {r["cand_id"]: r for r in (new_plan or [])}
    
    all_keys = set(old_map.keys()) | set(new_map.keys())
    
    changes = []
    total_units_delta = 0
    total_invest_delta = 0.0
    total_profit_delta = 0.0
    
    for k in all_keys:
        old_r = old_map.get(k)
        new_r = new_map.get(k)
        
        old_units = old_r["units"] if old_r else 0
        new_units = new_r["units"] if new_r else 0
        units_delta = new_units - old_units
        
        old_inv = old_r["investment"] if old_r else 0.0
        new_inv = new_r["investment"] if new_r else 0.0
        inv_delta = new_inv - old_inv
        
        old_p = old_r["expected_profit"] if old_r else 0.0
        new_p = new_r["expected_profit"] if new_r else 0.0
        p_delta = new_p - old_p
        
        if units_delta == 0 and inv_delta == 0:
            continue
            
        if old_r is None:
            action = "NEW_ENTRY"
            tag_tone = "green"
        elif new_r is None:
            action = "EXIT_POSITION"
            tag_tone = "red"
        elif units_delta > 0:
            action = "INCREASE"
            tag_tone = "teal"
        else:
            action = "DECREASE"
            tag_tone = "amber"
            
        ref = new_r or old_r
        changes.append({
            "cand_id": k,
            "name": ref["name"],
            "destination": ref["destination"],
            "week": ref["week"],
            "item_type": ref["item_type"],
            "action": action,
            "tag_tone": tag_tone,
            "old_units": old_units,
            "new_units": new_units,
            "units_delta": units_delta,
            "old_investment": old_inv,
            "new_investment": new_inv,
            "investment_delta": inv_delta,
            "expected_profit_delta": p_delta,
        })
        
        total_units_delta += units_delta
        total_invest_delta += inv_delta
        total_profit_delta += p_delta

    # Sort changes by absolute capital impact
    changes.sort(key=lambda x: abs(x["investment_delta"]), reverse=True)
    
    return {
        "changes": changes,
        "total_positions_affected": len(changes),
        "total_units_delta": total_units_delta,
        "total_investment_delta": round(total_invest_delta, 0),
        "total_profit_delta": round(total_profit_delta, 0),
        "net_direction": "EXPANDING" if total_invest_delta > 0 else "CONSOLIDATING" if total_invest_delta < 0 else "BALANCED",
    }


def record_replan_execution(
    trigger_reason: str,
    settings: Dict,
    plan_result: Dict,
    auto_approve: bool = False,
    auto_threshold_pct: float = 5.0,
) -> Dict:
    """Records a replan calculation into the audit system and determines approval state."""
    global _CURRENT_ACTIVE_PLAN, _REPLAN_HISTORY
    
    timestamp = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
    replan_id = f"RPL-{int(time.time() * 1000) % 1000000}"
    
    delta = calculate_plan_delta(_CURRENT_ACTIVE_PLAN, plan_result["plan"])
    
    # Check if delta qualifies for auto-approval
    old_capital = sum(r["investment"] for r in (_CURRENT_ACTIVE_PLAN or []))
    capital_change_pct = abs(delta["total_investment_delta"] / old_capital * 100) if old_capital > 0 else 100.0
    
    if auto_approve and (capital_change_pct <= auto_threshold_pct or _CURRENT_ACTIVE_PLAN is None):
        status = "APPROVED_AUTOMATIC"
        _CURRENT_ACTIVE_PLAN = plan_result["plan"]
        notes = f"Auto-approved: Capital variance {capital_change_pct:.1f}% within {auto_threshold_pct}% threshold."
    else:
        status = "PENDING_APPROVAL"
        notes = f"Requires procurement manager sign-off: Capital variance {capital_change_pct:.1f}% exceeds auto-threshold."
        
    entry = {
        "replan_id": replan_id,
        "timestamp": timestamp,
        "trigger_reason": trigger_reason,
        "status": status,
        "notes": notes,
        "budget": settings.get("budget", 75e7),
        "risk_aversion": settings.get("risk_aversion", 0.3),
        "stats": plan_result["stats"],
        "delta": delta,
    }
    
    _REPLAN_HISTORY.insert(0, entry)
    if len(_REPLAN_HISTORY) > 50:
        _REPLAN_HISTORY.pop()
    _save_state(_REPLAN_HISTORY, _CURRENT_ACTIVE_PLAN)
    return entry


def approve_or_reject_replan(replan_id: str, action: str, approver: str = "Procurement_Lead") -> Dict:
    """Transition replan status to APPROVED or REJECTED."""
    global _CURRENT_ACTIVE_PLAN, _REPLAN_HISTORY
    
    for entry in _REPLAN_HISTORY:
        if entry["replan_id"] == replan_id:
            if action.upper() == "APPROVE":
                entry["status"] = "APPROVED"
                entry["approver"] = approver
                entry["approved_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                _save_state(_REPLAN_HISTORY, _CURRENT_ACTIVE_PLAN)
                return {"success": True, "replan_id": replan_id, "status": "APPROVED"}
            elif action.upper() == "REJECT":
                entry["status"] = "REJECTED"
                entry["approver"] = approver
                entry["rejected_at"] = pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
                _save_state(_REPLAN_HISTORY, _CURRENT_ACTIVE_PLAN)
                return {"success": True, "replan_id": replan_id, "status": "REJECTED"}
            else:
                return {"success": False, "error": f"Invalid action {action}"}
                
    return {"success": False, "error": f"Replan ID {replan_id} not found"}


def get_replan_history() -> List[Dict]:
    """Returns the full audit history of replan executions."""
    return _REPLAN_HISTORY
