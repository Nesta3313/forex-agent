import json
import pandas as pd
import hashlib
from pathlib import Path
from datetime import datetime, timedelta

def verify_audit_hash_chain(file_path):
    if not Path(file_path).exists():
        return False, "File not found"
    
    valid = True
    errors = []
    prev_hash = "0" * 64
    
    with open(file_path, 'r') as f:
        for i, line in enumerate(f):
            try:
                data = json.loads(line)
                # Check prev_hash
                if data.get("prev_hash") != prev_hash:
                    valid = False
                    errors.append(f"Line {i}: Hash chain break. Expected {prev_hash}, got {data.get('prev_hash')}")
                
                # Verify current hash
                # Remove 'hash' itself from data to re-calculate
                hash_to_verify = data.pop("hash")
                canonical_str = json.dumps(data, sort_keys=True, separators=(',', ':'))
                recalculated = hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()
                
                if recalculated != hash_to_verify:
                    valid = False
                    errors.append(f"Line {i}: Data tamper detected. Hash mismatch.")
                
                prev_hash = hash_to_verify
            except Exception as e:
                valid = False
                errors.append(f"Line {i}: JSON Error: {e}")
    
    return valid, errors

def get_observation_metrics(days=28):
    audit_path = Path("logs/audit.jsonl")
    equity_path = Path("logs/equity.csv") # May not exist
    
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    metrics = {
        "rule_violations_count": 0,
        "max_drawdown_pct": 0.0,
        "avg_total_risk_pct": 0.0,
        "max_total_risk_pct": 0.0,
        "no_trade_ratio": 0.0,
        "event_stand_down_entries": 0,
        "event_blocked_trade_attempts": 0,
        "avg_loss_vs_planned": 0.0,
        "be_activations": 0,
        "trailing_exits": 0,
        "hash_chain_valid": True,
        "duplicates": 0,
        "last_tick": None
    }
    
    if not audit_path.exists():
        return metrics

    events = []
    with open(audit_path, 'r') as f:
        for line in f:
            try:
                events.append(json.loads(line))
            except:
                continue

    # 1. Audit Integrity
    valid, _ = verify_audit_hash_chain(audit_path)
    metrics["hash_chain_valid"] = valid

    # Filter by time
    df_events = pd.DataFrame(events)
    if df_events.empty:
        return metrics
        
    df_events['timestamp'] = pd.to_datetime(df_events['timestamp'])
    df_obs = df_events[df_events['timestamp'] >= cutoff]
    
    if df_obs.empty:
        return metrics

    metrics["last_tick"] = df_obs['timestamp'].max()

    # 2. Rule Violations & Event Gates
    # Track event risk state
    current_risk_status = "ALLOW_TRADING"
    decisions = []
    
    processed_candles = set()
    
    for _, row in df_obs.iterrows():
        etype = row['event_type']
        payload = row['payload']
        
        if etype == "EVENT_RISK":
            current_risk_status = payload.get("status")
            if current_risk_status == "STAND_DOWN":
                metrics["event_blocked_trade_attempts"] += 1 # Placeholder, will refine
        
        if etype == "TRADE_EXECUTED":
            # Check Stand Down
            if current_risk_status == "STAND_DOWN":
                metrics["rule_violations_count"] += 1
                metrics["event_stand_down_entries"] += 1
            
            # Check Stop Loss
            if not payload.get("stop_loss"):
                metrics["rule_violations_count"] += 1
                
            # Risk Cap Breachs (assuming 5% hard cap)
            # This would need context of ALL open trades at that moment
            # For now, just check individual risk_pct if it's crazy
            if payload.get("risk_pct", 0) > 0.05:
                metrics["rule_violations_count"] += 1

        if etype == "SIGNALS_GENERATED":
            # Duplicate candle check
            candle_ts = payload.get("timestamp") or row['timestamp'] # Fallback
            if candle_ts in processed_candles:
                metrics["duplicates"] += 1
                metrics["rule_violations_count"] += 1
            processed_candles.add(candle_ts)
            
            # Decisions
            # Logic here depends on how decisions are logged
            pass

    # 3. Decision Quality
    # In live mode, SIGNALS_GENERATED or a separate DECISION event
    decisions = df_obs[df_obs['event_type'] == 'SIGNALS_GENERATED'] # Approximation
    # We might need to look at logs/agent.log for NO_TRADE if not in audit
    # But user said only use audit.jsonl/positions.json/equity.csv
    
    # 4. Drawdown
    if equity_path.exists():
        df_equity = pd.read_csv(equity_path)
        if not df_equity.empty:
            df_equity['equity_peak'] = df_equity['equity'].cummax()
            df_equity['drawdown'] = (df_equity['equity_peak'] - df_equity['equity']) / df_equity['equity_peak']
            metrics["max_drawdown_pct"] = df_equity['drawdown'].max()
    
    return metrics

if __name__ == "__main__":
    m = get_observation_metrics()
    print(json.dumps(m, indent=2, default=str))
