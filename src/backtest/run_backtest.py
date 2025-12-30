import os
import sys
import uuid
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Optional

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.core.config import config
from src.core.logger import setup_logging, logging
from src.core.models import Candle, TradeProposal, TradeExecution, SignalOutput, TradeDecision
from src.core.audit import AuditLogger
from src.backtest.data_loader import OANDADataLoader
from src.modules.decision.engine import DecisionEngine
from src.modules.risk.manager import RiskManager

logger = logging.getLogger("backtest")

class BacktestClock:
    def __init__(self, candles: List[Candle]):
        self.candles = candles
        self.current_index = 0

    def now(self) -> datetime:
        return self.candles[self.current_index].timestamp

    def current_candle(self) -> Candle:
        return self.candles[self.current_index]

    def has_next(self) -> bool:
        return self.current_index < len(self.candles) - 1

    def tick(self):
        self.current_index += 1

class BacktestRunner:
    def __init__(self, run_id: str = None, output_parent_dir: Optional[Path] = None, overrides: Optional[Dict] = None):
        self.run_id = run_id or f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
        parent = output_parent_dir or Path(config.get("backtest", {}).get("output_dir", "logs/backtests"))
        self.output_dir = parent / self.run_id
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Setup separate audit logger for this run
        self.audit_file = self.output_dir / "audit.jsonl"
        self.audit_logger = AuditLogger(str(self.audit_file))
        
        # Merge config with overrides
        bt_cfg = config.get("backtest", {}).copy()
        if overrides:
            bt_cfg.update(overrides)

        self.initial_balance = bt_cfg.get("initial_balance", 10000)
        self.equity = self.initial_balance
        self.active_trade: Optional[Dict] = None 
        
        self.trades = []
        self.equity_history = []
        
        # Pipeline components
        self.decision_engine = DecisionEngine()
        self.risk_manager = RiskManager()
        
        from src.modules.risk.position_manager import PositionManager
        self.position_manager = PositionManager()
        
        # Backtest settings
        self.spread_pips = bt_cfg.get("spread_pips", 1.2)
        self.slippage_bps = bt_cfg.get("slippage_bps", 2.0)
        self.entry_mode = bt_cfg.get("entry_mode", "NEXT_OPEN")
        
        self.use_event_filter = bt_cfg.get("use_event_filter", True)
        self.event_risk_engine = None
        if self.use_event_filter:
            from src.modules.events.engine import EventRiskEngine
            self.event_risk_engine = EventRiskEngine(self.audit_logger)
            # Re-init decision engine with event risk
            self.decision_engine = DecisionEngine(self.event_risk_engine)

    def run(self, candles: List[Candle]):
        clock = BacktestClock(candles)
        logger.info(f"Starting backtest {self.run_id} with {len(candles)} candles...")
        
        # Prefetch events if using filter
        if self.event_risk_engine:
            inst = config.get("system", {}).get("currency_pair", "EUR_USD")
            self.event_risk_engine.prefetch(candles[0].timestamp, candles[-1].timestamp, inst)

        # We need at least lookback_candles to start
        lookback = config.get("data", {}).get("lookback_candles", 200)
        
        for i in range(lookback, len(candles)):
            # 1. Prepare data slice for the agent
            data_slice = candles[i-lookback:i]
            current_candle = candles[i]
            
            # 2. Process current candle logic
            self._process_tick(data_slice, current_candle, candles[i+1] if i+1 < len(candles) else None)
            
            # 3. Track equity
            self.equity_history.append({
                "timestamp": current_candle.timestamp,
                "equity": self.equity
            })

    def _process_tick(self, data_slice: List[Candle], current_candle: Candle, next_candle: Optional[Candle]):
        # Convert to DataFrame
        df = pd.DataFrame([c.model_dump() for c in data_slice])
        df.set_index('timestamp', inplace=True)
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
        
        # Calculate Indicators
        self._calculate_indicators_on_df(df)
        
        # 1. Manage Active Trade (Exit checks)
        if self.active_trade:
            # We use the current candle (which just closed) to check for SL/TP hits
            self._manage_exit(current_candle)

        # 2. Decision Logic (Only if no active trade)
        if not self.active_trade:
            inst = config.get("system", {}).get("currency_pair", "EUR_USD")
            
            # Hard Gate: Economic Event Risk
            if self.event_risk_engine:
                assessment = self.event_risk_engine.assess_risk(current_candle.timestamp, inst)
                if assessment.status == "STAND_DOWN":
                    logger.info(f"BACKTEST: STAND_DOWN gate active @ {current_candle.timestamp}")
                    self.audit_logger.log_event("EVENT_STAND_DOWN_BLOCK", {
                        "timestamp": str(current_candle.timestamp),
                        "reason": assessment.reason
                    })
                    return

            decision: TradeDecision = self.decision_engine.analyze(df, instrument=inst, current_time=current_candle.timestamp)
            
            if decision.decision == "TRADE" and decision.approved_trade:
                proposal = decision.approved_trade
                if self.risk_manager.check_trade(proposal):
                    # Enter on NEXT candle open if possible
                    if next_candle:
                        # Defensive check: is the NEXT candle also in stand-down?
                        next_assessment = self.event_risk_engine.assess_risk(next_candle.timestamp, inst)
                        if next_assessment.status == "STAND_DOWN":
                             logger.warning(f"BACKTEST ENTRY BLOCKED: {next_candle.timestamp} is also in STAND_DOWN")
                             self.audit_logger.log_event("EVENT_GATE_LEAK_PREVENTED", {
                                 "candle_time": str(next_candle.timestamp),
                                 "proposal_id": str(proposal.id),
                                 "reason": "Hard gating in Backtest Execution"
                             })
                             return
                        
                        self._execute_entry(proposal, candle=next_candle)
                    else:
                        logger.info("Decision made on last candle, cannot execute entry.")

    def _calculate_indicators_on_df(self, df: pd.DataFrame):
        close = df['Close']
        high = df['High']
        low = df['Low']

        df['SMA_50'] = close.rolling(window=50).mean()
        df['SMA_200'] = close.rolling(window=200).mean()

        previous_close = close.shift(1)
        tr = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
        df['ATR'] = tr.rolling(window=14).mean()

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))

        atr_ma = df['ATR'].rolling(window=50).mean()
        df['Regime'] = "NORMAL"
        if not atr_ma.empty:
             ratio = df['ATR'] / atr_ma
             df.loc[ratio > 1.5, 'Regime'] = 'VOLATILE'

    def _execute_entry(self, proposal: TradeProposal, candle: Candle):
        # Entry logic at the open of the 'next' candle
        spread = self.spread_pips * 0.0001
        slippage = candle.open * (self.slippage_bps / 10000.0)
        
        if proposal.direction == "BUY":
            fill_price = candle.open + (spread / 2) + slippage
        else:
            fill_price = candle.open - (spread / 2) - slippage
            
        self.active_trade = {
            "id": proposal.id,
            "symbol": proposal.symbol,
            "direction": proposal.direction,
            "entry_time": candle.timestamp,
            "entry_price": fill_price,
            "sl": proposal.stop_loss,
            "tp": proposal.take_profit,
            "size": 0.1 # Static for now
        }
        
        self.audit_logger.log_event("BACKTEST_ENTRY", {
            "candle_time": str(candle.timestamp),
            "direction": proposal.direction,
            "fill": fill_price,
            "sl": proposal.stop_loss,
            "tp": proposal.take_profit
        })

    def _manage_exit(self, candle: Candle):
        # 1. Advanced Management (Trailing Stop, Break-even)
        # We use the Close of the current candle to evaluate
        updates = self.position_manager.evaluate_position(self.active_trade, candle.close)
        if updates:
            if 'stop_loss' in updates:
                self.active_trade['sl'] = updates['stop_loss']
                self.audit_logger.log_event("BACKTEST_SL_UPDATE", {
                    "candle_time": str(candle.timestamp),
                    "new_sl": updates['stop_loss']
                })

        # 2. Intra-candle SL/TP resolution
        side = self.active_trade["direction"]
        sl = self.active_trade["sl"]
        tp = self.active_trade["tp"]
        
        exit_price = None
        exit_reason = None
        
        if side == "BUY":
            # Conservative: check SL first
            if candle.low <= sl:
                exit_price = sl
                exit_reason = "STOP_LOSS"
            elif tp and candle.high >= tp:
                exit_price = tp
                exit_reason = "TAKE_PROFIT"
        else: # SELL
            if candle.high >= sl:
                exit_price = sl
                exit_reason = "STOP_LOSS"
            elif tp and candle.low <= tp:
                exit_price = tp
                exit_reason = "TAKE_PROFIT"
                
        if exit_price:
            # Calculate PnL
            if side == "BUY":
                pnl = (exit_price - self.active_trade["entry_price"]) * self.active_trade["size"] * 100000 # Standard lot assumption
            else:
                pnl = (self.active_trade["entry_price"] - exit_price) * self.active_trade["size"] * 100000
                
            self.equity += pnl # Simplified: no commissions listed in requirements but spread/slippage applied at entry
            
            trade_record = {
                **self.active_trade,
                "exit_time": candle.timestamp,
                "exit_price": exit_price,
                "exit_reason": exit_reason,
                "pnl": pnl
            }
            self.trades.append(trade_record)
            
            self.audit_logger.log_event("BACKTEST_EXIT", {
                "candle_time": str(candle.timestamp),
                "reason": exit_reason,
                "pnl": pnl,
                "new_equity": self.equity
            })
            self.active_trade = None

    def _finalize(self, candles: List[Candle]):
        trades_df = pd.DataFrame(self.trades)
        equity_df = pd.DataFrame(self.equity_history)
        
        trades_df.to_csv(self.output_dir / "trades.csv", index=False)
        equity_df.to_csv(self.output_dir / "equity.csv", index=False)
        
        # Calculate Metrics
        from src.backtest.metrics import MetricsEngine, save_metrics
        engine = MetricsEngine(trades_df, equity_df)
        agent_metrics = engine.calculate_all()
        save_metrics(agent_metrics, self.output_dir / "metrics.json")
        
        # Run Baselines
        from src.backtest.baselines import NoTradeBaseline, MACrossoverBaseline
        
        # No Trade
        no_trade = NoTradeBaseline(self.initial_balance)
        no_trade.run(candles)
        no_trade_metrics = MetricsEngine(no_trade.get_trades_df(), no_trade.get_equity_df()).calculate_all()
        save_metrics(no_trade_metrics, self.output_dir / "metrics_baseline_notrade.json")
        no_trade.get_equity_df().to_csv(self.output_dir / "equity_baseline_notrade.csv", index=False)

        # MA Crossover
        ma_cross = MACrossoverBaseline(self.initial_balance)
        ma_cross.run(candles)
        ma_metrics = MetricsEngine(ma_cross.get_trades_df(), ma_cross.get_equity_df()).calculate_all()
        save_metrics(ma_metrics, self.output_dir / "metrics_baseline_ma.json")
        ma_cross.get_equity_df().to_csv(self.output_dir / "equity_baseline_ma.csv", index=False)
        ma_cross.get_trades_df().to_csv(self.output_dir / "trades_baseline_ma.csv", index=False)

        logger.info(f"Backtest complete. Results in {self.output_dir}")

def run_main():
    setup_logging()
    
    loader = OANDADataLoader()
    
    # Load settings from config
    bt_cfg = config.get("backtest", {})
    instrument = bt_cfg.get("instrument", "EUR_USD")
    granularity = bt_cfg.get("granularity", "H4")
    start = bt_cfg.get("start", "2023-01-01T00:00:00Z")
    end = bt_cfg.get("end", "2023-01-31T00:00:00Z")
    
    candles = loader.fetch_history(instrument, granularity, start, end)
    
    if not candles:
        logger.error("No data fetched for backtest.")
        return
        
    runner = BacktestRunner()
    runner.run(candles)
    runner._finalize(candles) # Call finalize after run

if __name__ == "__main__":
    run_main()
