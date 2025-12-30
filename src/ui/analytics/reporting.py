import json
import csv
import pandas as pd
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from src.ui.analytics.shadow_observation import compute_shadow_metrics

REPORT_DIR = Path("logs/reports")
REPORT_DIR.mkdir(parents=True, exist_ok=True)

def generate_shadow_report(start_ts_utc: datetime, end_ts_utc: datetime, audit_log: Path, equity_log: Path, strict: bool = True, include_raw: bool = False) -> Dict[str, Any]:
    """
    Generates a comprehensive shadow observation report object.
    """
    # Ensure timezone aware
    if start_ts_utc.tzinfo is None:
        start_ts_utc = start_ts_utc.replace(tzinfo=timezone.utc)
    if end_ts_utc.tzinfo is None:
        end_ts_utc = end_ts_utc.replace(tzinfo=timezone.utc)
        
    grace_period = 0 if strict else 30
    
    metrics = compute_shadow_metrics(audit_log, equity_log, start_ts=start_ts_utc, end_ts=end_ts_utc, grace_period_mins=grace_period)
    
    # Calculate executive status
    status = "GO"
    if metrics["violations"] > 0 or metrics["integrity_status"] == "FAIL":
        status = "NO-GO"
    elif metrics["integrity_status"] == "PARTIAL":
        status = "REVIEW"
    elif metrics["total_ticks"] < 10: # Min sample size
        status = "INSUFFICIENT_DATA"
        
    report = {
        "header": {
            "title": "Shadow Observation Period Report",
            "status": status,
            "window_start_utc": start_ts_utc.isoformat(),
            "window_end_utc": end_ts_utc.isoformat(),
            "generated_at": datetime.now(timezone.utc).isoformat()
        },
        "metrics": metrics,
    }
    
    return report

def export_report_json(report: Dict[str, Any], path: Path):
    def json_serial(obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, pd.DataFrame):
            return obj.to_dict(orient='records')
        raise TypeError("Type %s not serializable" % type(obj))
        
    with open(path, 'w') as f:
        json.dump(report, f, indent=2, default=json_serial)

def export_report_csv(report: Dict[str, Any], path: Path):
    m = report["metrics"]
    rows = [
        ["Section", "Metric", "Value"],
        ["Header", "Status", report["header"]["status"]],
        ["Header", "Start UTC", report["header"]["window_start_utc"]],
        ["Header", "End UTC", report["header"]["window_end_utc"]],
        ["Safety", "Rule Violations", m["violations"]],
        ["Safety", "Audit Integrity", m["integrity_status"]],
        ["Safety", "Duplicate Candles", m["duplicates"]],
        ["Behavior", "Total Ticks", m["total_ticks"]],
        ["Behavior", "Trade Count", m["trade_count"]],
        ["Behavior", "No Trade %", f"{m['no_trade_pct']:.2%}"],
        ["Behavior", "Blocked Attempts", m["blocked_attempts"]],
        ["Performance", "Max Drawdown %", f"{m['max_dd']:.2%}"],
        ["Performance", "Average Risk", f"{m['risk_avg']:.2%}"],
        ["System", "Last Tick", m["last_tick"].isoformat() if m["last_tick"] else "N/A"]
    ]
    with open(path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)

def export_report_pdf(report: Dict[str, Any], path: Path):
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.pdfgen import canvas
        from reportlab.lib import colors
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    except ImportError:
        print("reportlab not installed, skipping PDF export")
        return

    doc = SimpleDocTemplate(str(path), pagesize=LETTER)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph(report["header"]["title"], styles['Title']))
    elements.append(Spacer(1, 12))

    # Summary Badge
    status = report["header"]["status"]
    status_color = colors.green
    if status == "NO-GO": status_color = colors.red
    elif status == "REVIEW": status_color = colors.orange
    elif status == "INSUFFICIENT_DATA": status_color = colors.grey
    
    status_style = ParagraphStyle('status', parent=styles['Normal'], fontSize=16, textColor=status_color, alignment=1) # alignment 1 is center
    elements.append(Paragraph(f"OVERALL STATUS: {status}", status_style))
    elements.append(Spacer(1, 18))

    # Header Table
    h = report["header"]
    header_data = [
        ["Window Start", h["window_start_utc"]],
        ["Window End", h["window_end_utc"]],
        ["Generated At", h["generated_at"]]
    ]
    t = Table(header_data, colWidths=[120, 300])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (0,-1), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('PADDING', (0,0), (-1,-1), 6)
    ]))
    elements.append(t)
    elements.append(Spacer(1, 24))

    # Metrics Table
    m = report["metrics"]
    metric_data = [
        ["Category", "Metric", "Value"],
        ["Safety", "Rule Violations", m["violations"]],
        ["Safety", "Audit Integrity", m["integrity_status"]],
        ["Safety", "Duplicate Candles", m["duplicates"]],
        ["Behavior", "Total Ticks", m["total_ticks"]],
        ["Behavior", "Trade Count", m["trade_count"]],
        ["Behavior", "No Trade %", f"{m['no_trade_pct']:.2%}"],
        ["Behavior", "Blocked Attempts", m["blocked_attempts"]],
        ["Performance", "Max Drawdown %", f"{m['max_dd']:.2%}"],
        ["Performance", "Average Risk %", f"{m['risk_avg']*100:.2f}%"]
    ]
    mt = Table(metric_data, colWidths=[100, 180, 140])
    mt.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.darkblue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('ALIGN', (2,1), (2,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 6)
    ]))
    elements.append(Paragraph("Key Safety & Performance Metrics", styles['Heading2']))
    elements.append(mt)
    
    # Violation Details
    if m["violation_details"]:
        elements.append(Spacer(1, 12))
        elements.append(Paragraph("Violation Logs (Excerpts)", styles['Heading2']))
        v_data = [["Violation Type"]] + [[v] for v in m["violation_details"][:20]]
        vt = Table(v_data, colWidths=[420])
        vt.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('PADDING', (0,0), (-1,-1), 4)
        ]))
        elements.append(vt)
        if len(m["violation_details"]) > 20:
             elements.append(Paragraph(f"...and {len(m['violation_details'])-20} more. See JSON for details.", styles['Italic']))

    doc.build(elements)
