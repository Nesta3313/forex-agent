import json
import hashlib
import pandas as pd
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

def validate_audit_window(events: List[Dict]) -> Tuple[str, List[str]]:
    """
    Validates hash chaining within a specific window of events.
    Returns: (Status string: "PASS", "PARTIAL", "FAIL", List of errors)
    """
    if not events:
        return "PASS", []

    errors = []
    first_event = events[0]
    is_partial = False
    if first_event.get("prev_hash") != "0" * 64:
        is_partial = True

    prev_hash = first_event.get("hash")
    
    # Check first event
    temp_first = first_event.copy()
    actual_hash = temp_first.pop("hash", None)
    if "dt" in temp_first: temp_first.pop("dt")
    canonical = json.dumps(temp_first, sort_keys=True, separators=(',', ':'))
    if hashlib.sha256(canonical.encode()).hexdigest() != actual_hash:
        return "FAIL", ["Line 0: Data tamper detected."]

    for i in range(1, len(events)):
        curr = events[i]
        
        # Check chaining
        if curr.get("prev_hash") != prev_hash:
            errors.append(f"Event {i}: Chain break. Expected {prev_hash}, got {curr.get('prev_hash')}")
            return "FAIL", errors
        
        # Check data integrity
        temp_curr = curr.copy()
        actual_hash = temp_curr.pop("hash", None)
        if "dt" in temp_curr: temp_curr.pop("dt")
        canonical = json.dumps(temp_curr, sort_keys=True, separators=(',', ':'))
        if hashlib.sha256(canonical.encode()).hexdigest() != actual_hash:
            errors.append(f"Event {i}: Data tamper detected.")
            return "FAIL", errors
        
        prev_hash = actual_hash

    return ("PARTIAL" if is_partial else "PASS"), []

def is_rule_violation(event_type: str, payload: Dict[str, Any], context: Dict[str, Any]) -> Optional[str]:
    """
    Determines if an audit event represents a strict rule violation.
    Returns: Violation code (string) or None.
    """
    if event_type == "TRADE_EXECUTED" and context.get("current_risk_status") == "STAND_DOWN":
        return "EVENT_GATE_LEAK"
        
    if event_type == "RISK_MANAGER_DECISION" and payload.get("status") == "REJECTED":
         reason = payload.get("reason", "").upper()
         if "TOTAL RISK" in reason or "CAP EXCEEDED" in reason:
             return "RISK_CAP_BREACH"
         if "CORRELATION" in reason or "GROUP CAP" in reason:
             return "CORRELATION_CAP_BREACH"
             
    if event_type == "TRADE_EXECUTED" and not payload.get("stop_loss"):
        return "MISSING_STOP_LOSS"
        
    if event_type == "DATA_HEALTH" and payload.get("message") == "Duplicate Candle":
        return "DUPLICATE_CANDLE"

    return None

def detect_event_gate_leaks(window_events: List[Dict]) -> List[Dict]:
    """
    Strict leak detection: EXECUTION_FILL or TRADE_EXECUTED while status was STAND_DOWN.
    """
    leaks = []
    current_status = "ALLOW_TRADING"
    for e in window_events:
        etype = e['event_type']
        p = e['payload']
        if etype == "EVENT_RISK":
            current_status = p.get("status")
        if etype in ["TRADE_EXECUTED", "EXECUTION_FILL"] and current_status == "STAND_DOWN":
            leaks.append(e)
    return leaks

def count_rule_violations(window_events: List[Dict], grace_period_mins: int = 30) -> Tuple[int, List[str]]:
    """
    Counts violations using strict classification and grace period.
    """
    if not window_events:
        return 0, []
    
    violations = 0
    details = []
    current_status = "ALLOW_TRADING"
    first_tick_ts = window_events[0]['dt']
    grace_cutoff = first_tick_ts + timedelta(minutes=grace_period_mins)
    
    for e in window_events:
        etype = e['event_type']
        p = e['payload']
        in_grace = e['dt'] < grace_cutoff
        
        if etype == "EVENT_RISK":
            current_status = p.get("status")
            
        v_type = is_rule_violation(etype, p, {"current_risk_status": current_status})
        if v_type and not in_grace:
            violations += 1
            details.append(v_type)
            
    return violations, details

def compute_shadow_metrics(audit_log_path: Path, equity_log_path: Path, days: Optional[int] = 28, grace_period_mins: int = 30, start_ts: Optional[datetime] = None, end_ts: Optional[datetime] = None) -> Dict[str, Any]:
    # Use timezone-aware UTC now if end_ts not provided
    now_utc = datetime.now(timezone.utc)
    
    if start_ts:
        cutoff = start_ts
    else:
        cutoff = now_utc - timedelta(days=days or 28)
        
    end_cutoff = end_ts or now_utc
    
    metrics = {
        "violations": 0,
        "violation_details": [],
        "max_dd": 0.0,
        "risk_avg": 0.0,
        "risk_max": 0.0,
        "no_trade_pct": 0.0,
        "sd_entries": 0,
        "blocked_attempts": 0,
        "be_activations": 0,
        "trailing_exits": 0,
        "integrity_status": "PASS",
        "integrity_errors": [],
        "duplicates": 0,
        "last_tick": None,
        "total_ticks": 0,
        "trade_count": 0,
        "equity_data": None,
        "start_ts": cutoff,
        "end_ts": end_cutoff
    }

    if not audit_log_path.exists():
        return metrics

    all_events = []
    with open(audit_log_path, 'r') as f:
        for line in f:
            try:
                e = json.loads(line)
                # Parse as aware if possible
                ts_str = e['timestamp'].replace('Z', '')
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                e['dt'] = dt
                all_events.append(e)
            except: continue

    if not all_events:
        return metrics

    window_events = [e for e in all_events if cutoff <= e['dt'] <= end_cutoff]
    if not window_events:
        return metrics

    # 1. Integrity
    status, errors = validate_audit_window(window_events)
    metrics["integrity_status"] = status
    metrics["integrity_errors"] = errors
    if status == "FAIL":
        metrics["violations"] += 1
        metrics["violation_details"].append("AUDIT_HASH_MISMATCH")

    # 2. Strict Violations
    v_count, v_details = count_rule_violations(window_events, grace_period_mins)
    metrics["violations"] += v_count
    metrics["violation_details"].extend(v_details)
    
    # 3. Decision & Trade Stats
    total_risk = 0.0
    current_status = "ALLOW_TRADING"
    for e in window_events:
        etype = e['event_type']
        p = e['payload']
        if etype == "EVENT_RISK":
            current_status = p.get("status")
            metrics["total_ticks"] += 1
        if etype == "EVENT_STAND_DOWN_BLOCK":
            metrics["blocked_attempts"] += 1
        if etype == "TRADE_EXECUTED":
            metrics["trade_count"] += 1
            risk_val = p.get("risk_pct", 0)
            metrics["risk_max"] = max(metrics["risk_max"], risk_val)
            total_risk += risk_val
            if current_status == "STAND_DOWN":
                metrics["sd_entries"] += 1
        if etype == "TRADE_CLOSED":
            reason = p.get("reason", "").upper()
            if "BREAK_EVEN" in reason or "BE" in reason: metrics["be_activations"] += 1
            elif "TRAILING" in reason: metrics["trailing_exits"] += 1
        if etype == "DATA_HEALTH" and p.get("notes") == "Duplicate Candle":
            metrics["duplicates"] += 1

    if metrics["total_ticks"] > 0:
        metrics["no_trade_pct"] = (metrics["total_ticks"] - metrics["trade_count"]) / metrics["total_ticks"]
    if metrics["trade_count"] > 0:
        metrics["risk_avg"] = total_risk / metrics["trade_count"]
    
    metrics["last_tick"] = window_events[-1]['dt']

    # 4. Equity
    if equity_log_path.exists():
        try:
            df_eq = pd.read_csv(equity_log_path)
            if not df_eq.empty:
                df_eq['timestamp'] = pd.to_datetime(df_eq['timestamp'], utc=True)
                df_eq_obs = df_eq[(df_eq['timestamp'] >= cutoff) & (df_eq['timestamp'] <= end_cutoff)]
                if not df_eq_obs.empty:
                    df_eq_obs['peak'] = df_eq_obs['equity'].cummax()
                    df_eq_obs['dd'] = (df_eq_obs['peak'] - df_eq_obs['equity']) / df_eq_obs['peak']
                    metrics["max_dd"] = df_eq_obs['dd'].max()
                    metrics["equity_data"] = df_eq_obs
        except: pass

    return metrics

# Keep the old name for backward compatibility during transition if needed
def compute_observation_metrics(*args, **kwargs):
    return compute_shadow_metrics(*args, **kwargs)
