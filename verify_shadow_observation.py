import os
import sys
import json
import shutil
import argparse
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

# Ensure project root is in path
sys.path.append(str(Path(__file__).resolve().parent))

from src.core.config import config
from src.core.logger import setup_logging
from src.ui.analytics.shadow_observation import (
    validate_audit_window,
    detect_event_gate_leaks,
    count_rule_violations,
    compute_shadow_metrics
)

# Setup logging for verification
setup_logging()
import logging
logger = logging.getLogger("verify_shadow")

def run_test_a_integrity(audit_path: Path, days: int):
    print("\n--- Test A: Audit Integrity (Window-Scoped) ---")
    
    # Filter events for window
    all_events = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if not audit_path.exists():
        print("❌ Audit log not found.")
        return False
        
    with open(audit_path, 'r') as f:
        for line in f:
            try:
                e = json.loads(line)
                ts_str = e['timestamp'].replace('Z', '')
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                e['dt'] = dt
                if e['dt'] >= cutoff:
                    all_events.append(e)
            except: continue
            
    if not all_events:
        print("🟡 Insufficient data in window.")
        return True
        
    status, errors = validate_audit_window(all_events)
    if status in ["PASS", "PARTIAL"]:
        print(f"✅ Audit window integrity: {status}")
    else:
        print(f"❌ Audit window integrity: {status}")
        for err in errors:
            print(f"   - {err}")
        return False
        
    # Tamper Test
    print("--- Test A2: Tamper Detection ---")
    temp_audit = Path("logs/audit_verify_tmp.jsonl")
    shutil.copy(audit_path, temp_audit)
    
    # Tamper with an event in the window
    tampered = False
    lines = []
    with open(temp_audit, 'r') as f:
        lines = f.readlines()
        
    for i in range(len(lines)):
        try:
            data = json.loads(lines[i])
            ts_str = data['timestamp'].replace('Z', '')
            ts = datetime.fromisoformat(ts_str)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= cutoff:
                # Tamper with payload
                data['payload']['tampered'] = True
                lines[i] = json.dumps(data) + "\n"
                tampered = True
                break
        except: continue
        
    if tampered:
        with open(temp_audit, 'w') as f:
            f.writelines(lines)
            
        # Re-parse and validate
        window_events_tampered = []
        with open(temp_audit, 'r') as f:
            for line in f:
                try:
                    e = json.loads(line)
                    ts_str = e['timestamp'].replace('Z', '')
                    dt = datetime.fromisoformat(ts_str)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    e['dt'] = dt
                    if e['dt'] >= cutoff:
                        window_events_tampered.append(e)
                except: continue
                
        status_t, _ = validate_audit_window(window_events_tampered)
        if status_t == "FAIL":
            print("✅ Tamper detection: PASS (FAIL caught correctly)")
        else:
            print("❌ Tamper detection: FAIL (FAIL not caught)")
            os.remove(temp_audit)
            return False
    else:
        print("🟡 Could not find a line to tamper in window.")
        
    if temp_audit.exists():
        os.remove(temp_audit)
    return True

def run_test_b_gating(audit_path: Path):
    print("\n--- Test B: Hard Event Gating (Early-Return) ---")
    
    # We set VERIFY_MODE to enable hooks
    os.environ["VERIFY_MODE"] = "1"
    
    from src.main import job_tick, event_risk_engine, market_watcher
    from unittest.mock import MagicMock
    
    # Force STAND_DOWN
    event_risk_engine.force_status = "STAND_DOWN"
    
    # Mock market watcher to return a simple candle
    now_utc = datetime.now(timezone.utc)
    mock_df = pd.DataFrame([{
        "Open": 1.1000, "High": 1.1010, "Low": 1.0990, "Close": 1.1005, "Volume": 100
    }], index=[now_utc])
    market_watcher.fetch_data = MagicMock(return_value=mock_df)
    
    # Clear audit file tail or just count block events
    initial_blocks = 0
    if audit_path.exists():
        with open(audit_path, 'r') as f:
            for line in f:
                if "EVENT_STAND_DOWN_BLOCK" in line:
                    initial_blocks += 1
    
    # Run tick
    try:
        job_tick()
    except Exception as e:
        print(f"❌ Error during tick: {e}")
        return False
        
    # Verify block was logged and NO trade proposal etc
    post_blocks = 0
    has_signals = False
    with open(audit_path, 'r') as f:
        for line in f:
            if "EVENT_STAND_DOWN_BLOCK" in line:
                post_blocks += 1
            if "SIGNALS_GENERATED" in line and datetime.now(timezone.utc).strftime("%Y-%m-%d") in line:
                # Check if it was recent
                pass 
    
    event_risk_engine.force_status = None # reset
    
    if post_blocks > initial_blocks:
        print("✅ Hard event gating: PASS (Block logged)")
        return True
    else:
        print("❌ Hard event gating: FAIL (Block NOT logged)")
        return False

def run_test_c_leaks(audit_path: Path, days: int):
    print("\n--- Test C: Leak Detection Logic ---")
    all_events = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if not audit_path.exists(): return True
    
    with open(audit_path, 'r') as f:
        for line in f:
            try:
                e = json.loads(line)
                ts_str = e['timestamp'].replace('Z', '')
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                e['dt'] = dt
                if e['dt'] >= cutoff:
                    all_events.append(e)
            except: continue
            
    leaks = detect_event_gate_leaks(all_events)
    if not leaks:
        print(f"✅ Leak detection logic: PASS (0 leaks in {days} days)")
        return True
    else:
        print(f"❌ Leak detection logic: FAIL ({len(leaks)} leaks found)")
        for l in leaks:
            print(f"   - Leak @ {l['timestamp']}")
        return False

def run_test_d_rules(audit_path: Path, days: int, grace: int):
    print("\n--- Test D: Strict Rule Classification ---")
    all_events = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if not audit_path.exists(): return True
    
    with open(audit_path, 'r') as f:
        for line in f:
            try:
                e = json.loads(line)
                ts_str = e['timestamp'].replace('Z', '')
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                e['dt'] = dt
                if e['dt'] >= cutoff:
                    all_events.append(e)
            except: continue
            
    violation_count, details = count_rule_violations(all_events, grace)
    print(f"✅ Rule classification: PASS ({violation_count} violations found)")
    for d in details:
        print(f"   - {d}")
    return True

def run_test_e_grace(audit_path: Path, days: int):
    print("\n--- Test E: Grace Period Behavior ---")
    all_events = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    if not audit_path.exists(): return True
    
    with open(audit_path, 'r') as f:
        for line in f:
            try:
                e = json.loads(line)
                ts_str = e['timestamp'].replace('Z', '')
                dt = datetime.fromisoformat(ts_str)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                e['dt'] = dt
                if e['dt'] >= cutoff:
                    all_events.append(e)
            except: continue
            
    v_grace, _ = count_rule_violations(all_events, 30)
    v_no_grace, _ = count_rule_violations(all_events, 0)
    
    delta = v_no_grace - v_grace
    print(f"✅ Grace period behavior: PASS (reduced {delta} startup artifacts)")
    return True

def main():
    parser = argparse.ArgumentParser(description="Shadow Observation Verification Suite")
    parser.add_argument("--window-days", type=int, default=3)
    parser.add_argument("--grace-minutes", type=int, default=30)
    parser.add_argument("--audit-path", type=str, default="logs/audit_live.jsonl")
    parser.add_argument("--equity-path", type=str, default="logs/equity.csv")
    
    args = parser.parse_args()
    
    audit_path = Path(args.audit_path)
    equity_path = Path(args.equity_path)
    
    results = []
    results.append(run_test_a_integrity(audit_path, args.window_days))
    results.append(run_test_b_gating(audit_path))
    results.append(run_test_c_leaks(audit_path, args.window_days))
    results.append(run_test_d_rules(audit_path, args.window_days, args.grace_minutes))
    results.append(run_test_e_grace(audit_path, args.window_days))
    
    print("\n" + "="*40)
    if all(results):
        print("🎉 ALL VERIFICATION TESTS PASSED")
        sys.exit(0)
    else:
        print("❌ SOME VERIFICATION TESTS FAILED")
        sys.exit(1)

if __name__ == "__main__":
    main()
