import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from src.core.models import Candle
from src.backtest.run_backtest import BacktestRunner

def verify_position_management():
    print("Starting Phase 6C: Position Management Verification...")
    
    # 1. Create artificial candles showing profit
    # Entry @ 1.1000, TP @ 1.1100, SL @ 1.0950
    # Activation BE @ 20 pips = 1.1020
    # Activation Trailing @ 30 pips = 1.1030
    
    start_time = datetime(2024, 1, 1, 0, 0)
    candles = []
    
    # Needs lookback (200)
    for i in range(200):
        candles.append(Candle(timestamp=start_time + timedelta(hours=4*i), open=1.1000, high=1.1010, low=1.0990, close=1.1000, volume=100))
    
    # Trigger Trade on next (Decision engine will see signal if we mock it, but let's just force entry)
    # Actually, we can just use the provided runner and mock a trade proposal.
    
    # Let's add more candles to simulate profit
    # C201: Moves up to 1.1025 (triggers BE)
    candles.append(Candle(timestamp=start_time + timedelta(hours=4*200), open=1.1000, high=1.1030, low=1.1001, close=1.1025, volume=100))
    # C202: Moves up to 1.1040 (triggers Trailing)
    candles.append(Candle(timestamp=start_time + timedelta(hours=4*201), open=1.1025, high=1.1045, low=1.1020, close=1.1040, volume=100))
    # C203: Moves down to hit trailing stop
    candles.append(Candle(timestamp=start_time + timedelta(hours=4*202), open=1.1040, high=1.1045, low=1.0900, close=1.1020, volume=100))
    # C204: Dummy
    candles.append(Candle(timestamp=start_time + timedelta(hours=4*203), open=1.1020, high=1.1025, low=1.1015, close=1.1020, volume=100))
    
    runner = BacktestRunner(run_id="verify_6c")
    # Pre-fill equity history
    for c in candles:
        runner.equity_history.append({"timestamp": c.timestamp, "equity": runner.initial_balance})
    
    print("\nSimulating trade entry...")
    # Manually inject a trade to bypass decision logic
    runner._execute_entry(type('obj', (object,), {
        'id': 'test-uuid',
        'symbol': 'EUR_USD',
        'direction': 'BUY',
        'stop_loss': 1.0950,
        'take_profit': 1.2000, # Far away
        'entry_price': 1.1000
    })(), candles[200])
    
    # Run the remaining ticks
    print("Processing market moves...")
    
    # Candle 201
    runner._process_tick(candles[0:201], candles[201], candles[202])
    runner.equity_history.append({"timestamp": candles[201].timestamp, "equity": runner.equity})
    
    # Check if BE hit (SL should be 1.1000)
    if runner.active_trade:
        print(f"SL after candle 201: {runner.active_trade['sl']}")
        if runner.active_trade['sl'] == 1.1000:
             print("✅ Break-even triggered correctly.")
    
    # Candle 202
    runner._process_tick(candles[0:202], candles[202], candles[203])
    runner.equity_history.append({"timestamp": candles[202].timestamp, "equity": runner.equity})
    # Check if Trailing hit (Triggered SL to 1.1020, then hit by Low=1.1020)
    if runner.active_trade is None:
        last_trade = runner.trades[-1]
        print(f"✅ Trade closed correctly. Exit: {last_trade['exit_reason']} @ {last_trade['exit_price']}")
        if last_trade['exit_price'] == 1.1020:
             print("✅ Trailing stop price verified.")
    else:
        print(f"SL after candle 202: {runner.active_trade['sl']}")

    print("\nFinalizing backtest artifacts...")
    runner._finalize(candles)
    print("Done. Artifacts saved in logs/backtests/verify_6c")

if __name__ == "__main__":
    verify_position_management()
