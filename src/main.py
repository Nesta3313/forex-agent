import time
import signal
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from src.core.config import config
from src.core.logger import setup_logging, logging
from src.modules.market.data_feed import MarketDataWatcher
from src.modules.decision.engine import DecisionEngine
from src.modules.risk.manager import RiskManager
from src.modules.execution.engine import ExecutionEngine
from src.core.audit import log_audit_event
from src.modules.market.mock_provider import MockDataProvider

setup_logging()
logger = logging.getLogger("main")

# Global instances (using the new modular setup)
from src.modules.events.engine import EventRiskEngine
from src.modules.risk.position_manager import PositionManager

event_risk_engine = EventRiskEngine()
market_watcher = MarketDataWatcher()
decision_engine = DecisionEngine(event_engine=event_risk_engine)
risk_manager = RiskManager() 
execution_engine = ExecutionEngine(data_provider=market_watcher.provider)
position_manager = PositionManager()

def job_tick():
    """
    Main logic loop running on 4H candle close.
    """
    try:
        logger.info("--- 4H Candle Tick Start ---")
        
        # 1. Fetch Data
        df = market_watcher.fetch_data()
        if df.empty:
            logger.warning("No data received. Skipping tick.")
            return

        # 1.5 Hard Gate: Economic Event Risk
        # We check this BEFORE anything else to avoid signal generation during stand-down
        assessment = event_risk_engine.assess_risk(datetime.utcnow(), config.system.get("currency_pair", "EUR_USD"))
        if assessment.status == "STAND_DOWN":
            logger.warning(f"HARD GATE: Trading blocked by Economic event: {assessment.reason}")
            log_audit_event("EVENT_STAND_DOWN_BLOCK", {
                "reason": assessment.reason,
                "impact": "HIGH"
            })
            return

        current_price = df.iloc[-1]['Close']
        timestamp = df.index[-1]
        
        # 2. Manage Existing Positions
        open_positions = execution_engine.get_open_positions()
        if open_positions:
            logger.info(f"Managing {len(open_positions)} open positions...")
            # For each position, check if SL/TP hit, or if management triggers
            for pos in open_positions:
                symbol = pos['symbol']
                pos_id = pos['id']
                direction = pos['direction']
                sl = pos['stop_loss']
                tp = pos.get('take_profit')

                # Check SL hit
                if (direction == "BUY" and current_price <= sl) or \
                   (direction == "SELL" and current_price >= sl):
                    logger.warning(f"STOP LOSS hit for {symbol} {pos_id} @ {current_price}")
                    execution_engine.close_position(pos_id, current_price, "STOP_LOSS")
                    continue

                # Check TP hit
                if tp and ((direction == "BUY" and current_price >= tp) or \
                          (direction == "SELL" and current_price <= tp)):
                    logger.info(f"TAKE PROFIT hit for {symbol} {pos_id} @ {current_price}")
                    execution_engine.close_position(pos_id, current_price, "TAKE_PROFIT")
                    continue

                # Advanced Management (Trailing Stop, Break-even)
                updates = position_manager.evaluate_position(pos, current_price)
                if updates:
                    execution_engine.update_position(pos_id, updates)
                    logger.info(f"Position {pos_id} updated: {updates}")

        # Sync RiskManager with current state for exposure checks
        risk_manager.sync_positions(execution_engine.get_open_positions())

        # 3. Analyze & Decide (New Entry)
        decision = decision_engine.analyze(df)
        logger.info(f"Decision: {decision.decision} | Reason: {decision.reasoning}")

        # 4. If Trade Proposed -> Risk Check -> Execute
        if decision.decision == "TRADE" and decision.approved_trade:
            proposal = decision.approved_trade
            if risk_manager.check_trade(proposal):
                execution_engine.execute_trade(proposal, event_risk=assessment.status)
            else:
                logger.info("Trade blocked by Risk Manager.")
        
        logger.info("--- Tick End ---")

    except Exception as e:
        logger.error(f"Error in tick job: {e}", exc_info=True)

def main():
    logger.info("Starting Forex Agent (Production Shadow Mode)...")
    
    scheduler = BlockingScheduler()
    
    # TEST MODE: Run every 1 minute
    trigger = CronTrigger(minute='*')
    
    # Production 4H Schedule (Commented out for testing)
    # trigger = CronTrigger(hour='0,4,8,12,16,20', minute='2')
    
    scheduler.add_job(job_tick, trigger)
    logger.info(f"Scheduler started. Next run at: {trigger.get_next_fire_time(None, datetime.now())}")
    
    # Run once immediately for Verification if argument provided
    if "--run-once" in sys.argv:
        logger.info("Running immediate tick for verification...")
        job_tick()
        if "--only-once" in sys.argv:
            return

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Agent stopping...")

if __name__ == "__main__":
    main()
