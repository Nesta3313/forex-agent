import streamlit as st
import os
import pandas as pd
import json
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime, timedelta
import time
import hashlib
from src.core.config import config
from src.ui.analytics.shadow_observation import compute_observation_metrics

# Page Config
st.set_page_config(
    page_title="Forex Agent Dashboard",
    page_icon="📈",
    layout="wide",
)

# Constants
LOG_DIR = Path("logs")
AUDIT_LOG_PATH = LOG_DIR / "audit_live.jsonl"
MARKET_DATA_PATH = LOG_DIR / "agent.log" 
EQUITY_LOG_PATH = LOG_DIR / "equity.csv"
POSITIONS_PATH = Path("positions.json")

st.title("🤖 FX Agent (Shadow Mode)")

# Sidebar
st.sidebar.header("System Status")
st.sidebar.info("Mode: SHADOW")
st.sidebar.text(f"Pair: EUR/USD")
st.sidebar.text(f"Timeframe: 4H")

if st.sidebar.button("Refresh Data"):
    st.rerun()

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 Market & Signals", 
    "📝 Audit Log", 
    "🏥 Data Health", 
    "Tape 📼 Backtest", 
    "📅 Event Risk", 
    "🛡️ Portfolio Risk",
    "🕶️ Shadow Observation",
    "📄 Reports"
])

def load_audit_logs():
    data = []
    if AUDIT_LOG_PATH.exists():
        with open(AUDIT_LOG_PATH, "r") as f:
            for line in f:
                try:
                    # The logger outputs: TIMESTAMP [LEVEL] LOG_JSON
                    # But our JsonFormatter outputs PURE JSON if we configured it solely for that handler.
                    # Let's check how we configured it. 
                    # We configured specific "audit_file" handler with JsonFormatter.
                    # It should be pure JSON per line or wrapped.
                    # Our JsonFormatter outputs: {"timestamp":..., "message":..., "props": ...}
                    log_entry = json.loads(line)
                    # New Format: {"event_id":..., "timestamp":..., "event_type":..., "payload":..., "hash":...}
                    if "event_type" in log_entry:
                        flat_entry = {
                            "timestamp": log_entry.get("timestamp"),
                            "event": log_entry.get("event_type"),
                            "details": str(log_entry.get("payload")),
                            "hash": log_entry.get("hash", "")[-8:] + "..."
                        }
                        # Merge payload fields for easier analytics (e.g. data health)
                        payload = log_entry.get("payload", {})
                        if isinstance(payload, dict):
                            flat_entry.update(payload)
                        data.append(flat_entry)
                    # Fallback for old logs
                    elif "props" in log_entry:
                        event_type = log_entry["props"].get("event_type", "UNKNOWN")
                        event_data = log_entry["props"].get("data", {})
                        
                        flat_entry = {
                            "timestamp": log_entry["timestamp"],
                            "event": event_type,
                            "details": str(event_data),
                            "hash": "LEGACY"
                        }
                        if isinstance(event_data, dict):
                            flat_entry.update(event_data)
                        data.append(flat_entry)
                except json.JSONDecodeError:
                    continue
    return pd.DataFrame(data)

def load_positions():
    path = Path("positions.json")
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return []

def load_positions():
    path = Path("positions.json")
    if path.exists():
        with open(path, "r") as f:
            return json.load(f)
    return []

with tab1:
    source_name = config.data.get("source", "mock").upper()
    st.subheader(f"Market Overview ({source_name})")
    
    # Check for market data file
    if (LOG_DIR / "market_data.csv").exists():
        try:
            df_market = pd.read_csv(LOG_DIR / "market_data.csv", index_col=0, parse_dates=True)
            
            if not df_market.empty:
                last_row = df_market.iloc[-1]
                
                # Metrics
                col1, col2, col3, col4, col5 = st.columns(5)
                col1.metric("Close", f"{last_row['Close']:.4f}")
                col2.metric("SMA 50", f"{last_row['SMA_50']:.4f}", delta=f"{last_row['Close'] - last_row['SMA_50']:.4f}")
                col3.metric("SMA 200", f"{last_row['SMA_200']:.4f}")
                col4.metric("RSI", f"{last_row['RSI']:.1f}")
                col5.metric("ATR", f"{last_row['ATR']:.4f}")
                
                # Regime Badge
                regime = last_row.get('Regime', 'UNKNOWN')
                if regime == 'VOLATILE':
                    st.error(f"Market Regime: {regime}")
                else:
                    st.success(f"Market Regime: {regime}")

                # Chart
                fig = go.Figure()
                fig.add_trace(go.Candlestick(x=df_market.index,
                                open=df_market['Open'],
                                high=df_market['High'],
                                low=df_market['Low'],
                                close=df_market['Close'],
                                name='Price'))
                
                fig.add_trace(go.Scatter(x=df_market.index, y=df_market['SMA_50'], line=dict(color='orange', width=1), name='SMA 50'))
                fig.add_trace(go.Scatter(x=df_market.index, y=df_market['SMA_200'], line=dict(color='blue', width=1), name='SMA 200'))
                
                fig.update_layout(title="EUR/USD 4H", height=500, xaxis_rangeslider_visible=False)
                st.plotly_chart(fig)
                
            else:
                st.warning("Market data file is empty.")
                
        except Exception as e:
            st.error(f"Error loading market data: {e}")
    else:
        st.info("Waiting for agent to produce market_data.csv...")
    
    # Active Positions
    st.subheader("Active Shadow Positions")
    positions = load_positions()
    if positions:
        st.dataframe(positions)
    else:
        st.write("No active positions.")

with tab2:
    st.subheader("System Activity Log")
    df_audit = load_audit_logs()
    
    if not df_audit.empty:
        # Sort by timestamp desc
        df_audit['timestamp'] = pd.to_datetime(df_audit['timestamp'])
        df_audit = df_audit.sort_values(by='timestamp', ascending=False)
        
        st.dataframe(df_audit)
    else:
        st.info("No audit logs found yet.")

with tab3:
    st.subheader("🏥 Data Health Monitor")
    df_all = load_audit_logs()
    
    if not df_all.empty:
        df_health = df_all[df_all["event"] == "DATA_HEALTH"].copy()
        
        if not df_health.empty:
            # Ensure required columns exist (defensive)
            for col in ["status", "minutes_stale", "latency_ms", "notes"]:
                if col not in df_health.columns:
                    df_health[col] = "N/A" if col == "notes" else 0

            last = df_health.iloc[-1]
            
            # Status Metrics
            c1, c2, c3 = st.columns(3)
            c1.metric("Provider Status", last.get("status", "UNKNOWN"))
            c2.metric("Staleness (min)", f"{float(last.get('minutes_stale', 0)):.1f}")
            c3.metric("Latency (ms)", last.get("latency_ms", 0))
            
            if last.get("status") != "OK":
                st.error(f"Issue Detected: {last.get('notes')}")
            else:
                st.success("Data Feed Healthy")
                
            st.write("Recent Health Events")
            st.dataframe(df_health[["timestamp", "status", "minutes_stale", "notes"]].tail(20))
        else:
            st.info("No Health events logged yet.")
    else:
        st.info("No logs.")

with tab4:
    st.subheader("📼 Backtest Results")
    
    # --- New: Batch Controls ---
    with st.expander("🚀 Run Multi-Year Backtest", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            inst = st.selectbox("Instrument", ["EUR_USD", "GBP_USD", "USD_JPY"], index=0)
            gran = st.selectbox("Granularity", ["H4", "H1", "D"], index=0)
            balance = st.number_input("Initial Balance", value=10000)
        with c2:
            entry_mode = st.selectbox("Entry Mode", ["NEXT_OPEN", "CLOSE"], index=0)
            spread_pips = st.number_input("Spread (Pips)", value=1.2, step=0.1)
            slippage_bps = st.number_input("Slippage (BPS)", value=2.0, step=0.5)
            
        st.write("**Select Year Ranges**")
        start_year = st.number_input("Start Year", value=2018, min_value=2010, max_value=2024)
        end_year = st.number_input("End Year", value=2024, min_value=2010, max_value=2024)
        
        ranges = []
        for y in range(start_year, end_year):
            ranges.append({"start": f"{y}-01-01T00:00:00Z", "end": f"{y}-12-31T23:59:59Z"})
            
        if st.button("Run Multi-Year Batch"):
            from src.backtest.batch_runner import BatchRunner
            batch_runner = BatchRunner()
            
            overrides = {
                "instrument": inst,
                "granularity": gran,
                "initial_balance": balance,
                "entry_mode": entry_mode,
                "spread_pips": spread_pips,
                "slippage_bps": slippage_bps
            }
            
            status_text = st.empty()
            status_text.info(f"Starting Batch {batch_runner.batch_id}...")
            
            # Use the BatchRunner to run the batch
            # Note: This is synchronous, so UI will hang until done.
            batch_runner.run_batch(ranges, overrides)
            
            status_text.success(f"Batch {batch_runner.batch_id} Complete!")
            st.rerun()

    st.divider()
    project_root = Path(__file__).resolve().parent.parent.parent
    bt_dir = project_root / "logs" / "backtests"
    
    if bt_dir.exists():
        # Look for batch folders too
        # Logic to distinguish batches vs single runs
        all_items = sorted([d for d in bt_dir.iterdir() if d.is_dir()], key=os.path.getmtime, reverse=True)
        item_names = [d.name for d in all_items]
        
        if item_names:
            selected_item = st.selectbox("Select Backtest Run or Batch", item_names)
            run_path = bt_dir / selected_item
            
            # Check if it's a batch
            if (run_path / "batch_summary.json").exists():
                with open(run_path / "batch_summary.json", "r") as f:
                    batch = json.load(f)
                
                st.info(f"Batch ID: {batch['batch_id']}")
                
                # Comparison Table
                st.write("### 📊 Batch Comparison")
                comp_data = []
                for run in batch["runs"]:
                    m = run["metrics"]
                    comp_data.append({
                        "Year": run["start"][:4],
                        "Trades": m.get("total_trades", 0),
                        "Win Rate %": f"{m.get('win_rate', 0)*100:.1f}%",
                        "Profit Factor": m.get("profit_factor", 0),
                        "Net PnL": m.get("net_profit", 0),
                        "Return %": f"{(m.get('net_profit', 0)/batch['config'].get('initial_balance', 10000))*100:.2f}%",
                        "Max DD %": f"{m.get('max_drawdown_pct', 0)*100:.1f}%"
                    })
                st.table(comp_data)
                
                # Comparison Charts
                st.write("### 📈 Batch Performance")
                df_comp = pd.DataFrame(comp_data)
                # Convert string percentages back to float for plotting
                df_comp["Net PnL"] = df_comp["Net PnL"].astype(float)
                
                st.bar_chart(df_comp.set_index("Year")["Net PnL"])
                
                # Overlay chart (Equity)
                fig_batch = go.Figure()
                for run in batch["runs"]:
                    run_run_path = run_path / run["run_id"]
                    if (run_run_path / "equity.csv").exists():
                        df_req_eq = pd.read_csv(run_run_path / "equity.csv")
                        # Normalize equity for overlay? No, let's just show absolute
                        fig_batch.add_trace(go.Scatter(x=df_req_eq['timestamp'], y=df_req_eq['equity'], name=f"Agent {run['start'][:4]}"))
                
                fig_batch.update_layout(title="Batch Equity Curves", height=500)
                st.plotly_chart(fig_batch)
                
            # Else single run logic (as before)
            elif (run_path / "metrics.json").exists():
                with open(run_path / "metrics.json", "r") as f:
                    metrics = json.load(f)
                
                # Metrics Display
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Win Rate", f"{metrics['win_rate']*100:.1f}%")
                m2.metric("Net PnL", f"${metrics['net_profit']:.2f}")
                m3.metric("Profit Factor", metrics['profit_factor'])
                m4.metric("Max Drawdown", f"{metrics['max_drawdown_pct']*100:.1f}%")
                
                # Charts
                if (run_path / "equity.csv").exists():
                    df_eq = pd.read_csv(run_path / "equity.csv")
                    fig_eq = go.Figure()
                    fig_eq.add_trace(go.Scatter(x=df_eq['timestamp'], y=df_eq['equity'], name="Agent Equity"))
                    
                    # Optionally add baselines if they exist
                    if (run_path / "equity_baseline_ma.csv").exists():
                        df_ma = pd.read_csv(run_path / "equity_baseline_ma.csv")
                        fig_eq.add_trace(go.Scatter(x=df_ma['timestamp'], y=df_ma['equity'], name="MA Crossover Baseline", line=dict(dash='dot')))
                    
                    fig_eq.update_layout(title="Equity Curve", height=400)
                    st.plotly_chart(fig_eq)
                
                # Trades Table
                if (run_path / "trades.csv").exists():
                    st.write("Recent Trades")
                    df_tr = pd.read_csv(run_path / "trades.csv")
                    st.dataframe(df_tr.tail(50))
                
            else:
                st.warning("Selected run is missing metrics.json")
        else:
            st.info("No backtest runs found. Run python3 src/backtest/run_backtest.py first.")
    else:
        st.info("Backtest directory not found.")
        
with tab5:
    st.subheader("📅 Economic Event Risk")
    
    from src.modules.events.engine import EventRiskEngine
    events_engine = EventRiskEngine()
    
    # Live Status Assessment
    instrument = config.get("system", {}).get("currency_pair", "EUR_USD")
    now = datetime.utcnow()
    assessment = events_engine.assess_risk(now, instrument)
    
    # 1. Metrics Header
    c1, c2, c3 = st.columns(3)
    with c1:
        color = "green" if assessment.status == "ALLOW_TRADING" else "orange" if assessment.status == "CAUTION" else "red"
        st.markdown(f"**Current Status:** :{color}[{assessment.status}]")
    with c2:
        if assessment.next_high_event_time:
            st.write(f"**Next High Event In:** {assessment.minutes_to_event} mins")
        else:
            st.write("**Next High Event In:** N/A")
    with c3:
        st.write(f"**Reason:** {assessment.reason}")
        
    st.divider()
    
    # 2. Upcoming Events Table
    st.write("### 🏷️ Upcoming Major Events (Next 7 Days)")
    # We need to prefetch or just use the engine's cache
    events_engine.prefetch(now, now + timedelta(days=7), instrument)
    
    if events_engine.events_cache:
        event_data = []
        # Sort by time
        sorted_events = sorted(events_engine.events_cache, key=lambda x: x.timestamp_utc)
        for e in sorted_events:
            event_data.append({
                "Time (UTC)": e.timestamp_utc.strftime("%Y-%m-%d %H:%M"),
                "Currency": e.currency,
                "Title": e.title,
                "Impact": e.impact
            })
        st.table(event_data[:15]) # Show next 15
    else:
        st.info("No upcoming events found.")

    st.divider()
    
    # 3. Recent Risk Logs (from Audit)
    st.write("### 📜 Recent Event Risk Logs")
    audit_path = Path("logs/audit.jsonl")
    if audit_path.exists():
        with open(audit_path, "r") as f:
            log_lines = f.readlines()
        
        risk_events = []
        for line in reversed(log_lines):
            try:
                data = json.loads(line)
                if data.get("event_type") == "EVENT_RISK":
                    p = data.get("payload", {})
                    risk_events.append({
                        "Time": data.get("timestamp"),
                        "Status": p.get("status"),
                        "Reason": p.get("reason"),
                        "Matched Event": p.get("matched_event", {}).get("title") if p.get("matched_event") else "None"
                    })
                if len(risk_events) >= 10:
                    break
            except:
                continue
        
        if risk_events:
            st.table(risk_events)
        else:
            st.write("No risk logs found in audit file.")
    else:
        st.info("Audit log not found yet.")

with tab6:
    st.subheader("🛡️ Portfolio Exposure Management")
    
    from src.modules.risk.correlation import CorrelationMatrix
    corr_matrix = CorrelationMatrix()
    
    positions = load_positions()
    
    if not positions:
        st.info("No active positions to analyze.")
    else:
        # 1. Aggregate Stats
        total_risk = sum(p.get('risk_pct', 0.01) for p in positions)
        
        c1, c2 = st.columns(2)
        with c1:
            max_total = config.risk.get("portfolio", {}).get("max_total_risk_pct", 0.05)
            st.metric("Total Account Risk", f"{total_risk:.2%}", delta=f"Cap: {max_total:.0%}", delta_color="inverse")
            st.progress(min(total_risk / max_total, 1.0) if max_total > 0 else 0)
            
        with c2:
            st.metric("Open Positions", len(positions), delta=f"Cap: {config.risk.get('max_open_positions', 3)}", delta_color="inverse")

        st.divider()
        
        # 2. Correlated Groups
        st.write("### ⛓️ Correlated Group Exposure")
        
        groups_found = {}
        for p in positions:
            symbol = p.get('symbol', 'UNKNOWN')
            p_groups = corr_matrix.get_groups_for_pair(symbol)
            risk = p.get('risk_pct', 0.01)
            
            for g in p_groups:
                groups_found[g] = groups_found.get(g, 0.0) + risk
        
        if groups_found:
            max_corr = config.risk.get("portfolio", {}).get("max_correlated_risk_pct", 0.03)
            group_data = []
            for g, r in groups_found.items():
                group_data.append({
                    "Group": g,
                    "Total Risk": f"{r:.2%}",
                    "Status": "✅ OK" if r <= max_corr else "⚠️ OVER LIMIT"
                })
            st.table(group_data)
        else:
            st.write("No correlation group overlaps detected.")

        st.divider()
        
        # 3. Detailed Position Risk
        st.write("### 🔍 Risk Breakdown by Position")
        df_risk = pd.DataFrame(positions)
        if 'risk_pct' in df_risk.columns:
            df_risk['risk_pct'] = df_risk['risk_pct'].apply(lambda x: f"{x:.2%}")
        st.dataframe(df_risk)

with tab7:
    st.subheader("🕶️ Shadow Observation Analytics")
    
    # 1. Window & Controls
    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        window_days = st.select_slider("Observation Window (Days)", options=[14, 21, 28], value=28)
    with col_ctrl2:
        grace_period = st.number_input("Startup Grace Period (Mins)", value=30, min_value=0, max_value=240)
    
    with st.spinner("Analyzing logs..."):
        metrics = compute_observation_metrics(AUDIT_LOG_PATH, EQUITY_LOG_PATH, window_days, grace_period)
    
    # 2. Overall Status Logic
    is_fail = (metrics["violations"] > 0 or 
               metrics["sd_entries"] > 0 or 
               metrics["integrity_status"] == "FAIL" or 
               metrics["max_dd"] > 0.07)
    
    is_go = (metrics["violations"] == 0 and 
             metrics["max_dd"] <= 0.05 and 
             metrics["sd_entries"] == 0 and 
             metrics["integrity_status"] in ["PASS", "PARTIAL"])

    if is_fail:
        st.error("🔴 NO-GO – Fix Required Before Paper Trading")
    elif is_go:
        st.success("🟢 GO – System Behaving as Designed")
    else:
        st.warning("🟡 REVIEW – Investigate Before Progressing")

    # 3. Executive Summary Table
    sum_col1, sum_col2 = st.columns([1, 1])
    with sum_col1:
        st.write("### Executive Summary")
        
        # Integrity Label with Icon
        i_status = metrics["integrity_status"]
        i_icon = "✅" if i_status in ["PASS", "PARTIAL"] else "❌"
        i_label = f"{i_icon} {i_status}"
        
        summary_data = [
            {"Metric": "Rule Violations", "Status": "🟢 PASS" if metrics["violations"] == 0 else "🔴 FAIL", "Value": str(metrics["violations"])},
            {"Metric": "Max Drawdown", "Status": "🟢 PASS" if metrics["max_dd"] <= 0.05 else ("🟡 OK" if metrics["max_dd"] <= 0.07 else "🔴 FAIL"), "Value": f"{metrics['max_dd']:.2%}"},
            {"Metric": "Event Gate Integrity", "Status": "🟢 PASS" if metrics["sd_entries"] == 0 else "🔴 FAIL", "Value": "No Leaks" if metrics["sd_entries"] == 0 else f"{metrics['sd_entries']} LEAKS"},
            {"Metric": "Audit Integrity", "Status": i_label, "Value": "Valid" if i_status != "FAIL" else " Tampered/Broken"},
            {"Metric": "NO_TRADE Ratio", "Status": "🟢 PASS" if 0.6 <= metrics["no_trade_pct"] <= 0.9 else "🟡 REVIEW", "Value": f"{metrics['no_trade_pct']:.1%}"},
        ]
        st.table(pd.DataFrame(summary_data))

    # 4. Risk & Drawdown
    st.divider()
    st.write("### 📉 Risk & Drawdown")
    c1, c2, c3 = st.columns(3)
    c1.metric("Max Drawdown", f"{metrics['max_dd']:.2%}")
    c2.metric("Avg Risk-at-Risk", f"{metrics['risk_avg']:.2%}")
    c3.metric("Max Risk-at-Risk", f"{metrics['risk_max']:.2%}")
    
    if metrics["equity_data"] is not None:
        try:
            df_eq = metrics["equity_data"]
            fig_dd = go.Figure()
            fig_dd.add_trace(go.Scatter(x=df_eq['timestamp'], y=df_eq['equity'], name="Equity Curve", line=dict(color='green')))
            fig_dd.update_layout(height=300, margin=dict(l=0,r=0,t=0,b=0))
            st.plotly_chart(fig_dd, use_container_width=True)
        except: pass
    else:
        st.info("Equity curve log not available for this period.")

    # 5. Decision & Trade Behavior
    st.divider()
    st.write("### 🧠 Decision & Interaction")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.write("Decision Ratios")
        if metrics["total_ticks"] > 0:
            labels = ['TRADE', 'NO_TRADE']
            values = [metrics["trade_count"], metrics["total_ticks"] - metrics["trade_count"]]
            fig_pie = go.Figure(data=[go.Pie(labels=labels, values=values, hole=.3)])
            fig_pie.update_layout(height=300)
            st.plotly_chart(fig_pie)
        else:
            st.write("Insufficient decision data.")

    with cc2:
        st.write("Event Gate Performance")
        st.metric("Blocked Trade Attempts", metrics["blocked_attempts"])
        st.metric("Event Stand-Down Entries (FAIL)", metrics["sd_entries"])
        
    st.divider()
    st.write("### 🛠️ Position Management Behavior")
    bc1, bc2, bc3 = st.columns(3)
    bc1.metric("BE Activations", metrics["be_activations"])
    bc2.metric("Trailing Stop Exits", metrics["trailing_exits"])
    # bc3.metric("Avg Loss vs Planned", f"{metrics['loss_vs_planned']:.1%}")

    # 6. System Stability
    st.divider()
    st.write("### 🏥 System Stability")
    sc1, sc2 = st.columns(2)
    with sc1:
        st.write(f"**Audit Hash Chain:** {metrics['integrity_status']}")
        st.write(f"**Duplicate Candles:** {metrics['duplicates']}")
    with sc2:
        st.write(f"**Last Tick Processed:** {metrics['last_tick']}")
        st.write(f"**Total Observations (Ticks):** {metrics['total_ticks']}")

with tab8:
    st.subheader("📄 Shadow Observation Reporting")
    st.write("Generate a formal safety and performance report for any UTC time range.")
    
    # 1. Selection
    c1, c2 = st.columns(2)
    with c1:
        start_date = st.date_input("Start Date (UTC)", value=datetime.utcnow() - timedelta(days=7))
        start_time = st.time_input("Start Time (UTC)", value=datetime.min.time())
    with c2:
        end_date = st.date_input("End Date (UTC)", value=datetime.utcnow())
        end_time = st.time_input("End Time (UTC)", value=datetime.now().time())
        
    # Combine and ensure UTC
    from datetime import timezone as tz_utc
    start_ts = datetime.combine(start_date, start_time).replace(tzinfo=tz_utc.utc)
    end_ts = datetime.combine(end_date, end_time).replace(tzinfo=tz_utc.utc)
    
    st.divider()
    
    # 2. Options
    c3, c4 = st.columns(2)
    with c3:
        strict_report = st.toggle("Strict Scoring (Grace Period OFF)", value=True, key="report_strict")
        include_raw = st.toggle("Include Raw Audit Excerpts", value=False, key="report_raw")
    with c4:
        st.info("Reports are saved to `logs/reports/`. All timestamps in reports are processed in UTC.")

    # 3. Actions
    if st.button("🚀 Generate Report Bundle"):
        from src.ui.analytics.reporting import (
            generate_shadow_report, export_report_json, 
            export_report_csv, export_report_pdf, REPORT_DIR
        )
        
        with st.spinner("Analyzing audit logs and generating bundle..."):
            report_obj = generate_shadow_report(start_ts, end_ts, AUDIT_LOG_PATH, EQUITY_LOG_PATH, strict=strict_report, include_raw=include_raw)
            
            # Deterministic filenames based on dates
            ts_str = datetime.now().strftime("%H%M%S")
            base_name = f"shadow_report_{start_date}_to_{end_date}_{ts_str}"
            json_path = REPORT_DIR / f"{base_name}.json"
            csv_path = REPORT_DIR / f"{base_name}.csv"
            pdf_path = REPORT_DIR / f"{base_name}.pdf"
            
            export_report_json(report_obj, json_path)
            export_report_csv(report_obj, csv_path)
            export_report_pdf(report_obj, pdf_path)
            
            st.success(f"Report bundle generated successfully.")
            
            # Show Preview
            st.write("### 🔍 Report Summary")
            h = report_obj["header"]
            m = report_obj["metrics"]
            
            p1, p2, p3, p4 = st.columns(4)
            p1.metric("Status", h["status"])
            p2.metric("Violations", m["violations"])
            p3.metric("Integrity", m["integrity_status"])
            p4.metric("Ticks", m["total_ticks"])
            
            # Download Buttons
            st.write("### 📥 Download")
            d1, d2, d3 = st.columns(3)
            with open(json_path, 'rb') as f_json:
                d1.download_button("JSON Report", f_json, file_name=json_path.name)
            with open(csv_path, 'rb') as f_csv:
                d2.download_button("CSV Report", f_csv, file_name=csv_path.name)
            if pdf_path.exists():
                with open(pdf_path, 'rb') as f_pdf:
                    d3.download_button("PDF Report", f_pdf, file_name=pdf_path.name)

    # 4. Saved Reports List
    st.divider()
    st.write("### 📂 Recently Generated Reports")
    from src.ui.analytics.reporting import REPORT_DIR
    if REPORT_DIR.exists():
        files = sorted(REPORT_DIR.glob("shadow_report_*"), key=os.path.getmtime, reverse=True)
        if files:
            for f in files[:10]:
                col_f, col_d = st.columns([4, 1])
                col_f.text(f"📄 {f.name}")
                with open(f, 'rb') as rb:
                    col_d.download_button("⬇️", rb, file_name=f.name, key=str(f))
        else:
            st.info("No reports generated yet.")
    else:
        st.info("Report directory not created yet.")
