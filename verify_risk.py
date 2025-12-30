import sys
from pathlib import Path
from datetime import datetime
from uuid import uuid4

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from src.modules.risk.manager import RiskManager
from src.core.models import TradeProposal
from src.core.audit import AuditLogger

def verify_risk():
    print("Starting Phase 6B: Correlated Risk Verification...")
    
    rm = RiskManager()
    
    # 1. Simulate sync with 2 EUR_USD positions (Total risk 2%)
    print("\n[Test 1] Syncing 2 EUR/USD positions...")
    mock_positions = [
        {"symbol": "EUR_USD", "risk_pct": 0.01, "direction": "BUY", "id": str(uuid4())},
        {"symbol": "EUR_USD", "risk_pct": 0.01, "direction": "BUY", "id": str(uuid4())},
    ]
    rm.sync_positions(mock_positions)
    print(f"Current open positions count: {len(rm.current_positions)}")

    # 2. Propose another EUR_USD trade (risk 2% - should trigger correlation cap if > 3%)
    # Wait, max_correlated is 3%. Current group USD_STRENGTH has 2% (EURUSD). 
    # If we add 2% = 4% > 3%. REJECT.
    print("\n[Test 2] Proposing 3rd EUR_USD trade (risk 2%)...")
    p3 = TradeProposal(
        symbol="EUR_USD",
        direction="BUY",
        entry_price=1.10,
        stop_loss=1.09,
        take_profit=1.12,
        confidence=0.8,
        reasoning="Test",
        suggested_risk_pct=0.02
    )
    result = rm.check_trade(p3)
    if not result:
        print("✅ Correctly rejected: Correlated group risk cap hit.")
    else:
        print("❌ FAILED: Should have rejected due to correlated risk cap.")

    # 3. Propose uncorrelated trade (e.g. some pair NOT in USD_STRENGHT/WEAKNESS/YEN)
    # Let's say AUD_NZD (unmapped in config)
    print("\n[Test 3] Proposing uncorrelated trade (AUD_NZD, 1%)...")
    p4 = TradeProposal(
        symbol="AUD_NZD",
        direction="BUY",
        entry_price=1.05,
        stop_loss=1.04,
        take_profit=1.07,
        confidence=0.8,
        reasoning="Test",
        suggested_risk_pct=0.01
    )
    result = rm.check_trade(p4)
    if result:
        print("✅ Correctly approved: Uncorrelated trade.")
    else:
        print("❌ FAILED: Should have approved uncorrelated trade.")

    # 4. Total Risk Cap Check
    # Current risk: 2% (EURUSD) + 1% (Proposed AUDNZD) = 3%.
    # Add AUDNZD to sync positions, then try another big trade.
    mock_positions.append({"symbol": "AUD_NZD", "risk_pct": 0.01, "direction": "BUY", "id": str(uuid4())})
    rm.sync_positions(mock_positions)
    
    print("\n[Test 4] Proposing trade that hits Total Portfolio Risk cap (5%)...")
    p5 = TradeProposal(
        symbol="GBP_JPY",
        direction="BUY",
        entry_price=180.0,
        stop_loss=178.0,
        take_profit=185.0,
        confidence=0.8,
        reasoning="Test",
        suggested_risk_pct=0.03 # 3% (proposed) + 3% (current) = 6% > 5%
    )
    result = rm.check_trade(p5)
    if not result:
        print("✅ Correctly rejected: Total Portfolio Risk cap hit.")
    else:
        print("❌ FAILED: Should have rejected due to total risk cap.")

if __name__ == "__main__":
    verify_risk()
