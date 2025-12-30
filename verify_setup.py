import sys
from pathlib import Path
from datetime import datetime

# Add src to path
sys.path.append(str(Path.cwd()))

from src.core.logger import setup_logging, logging
from src.modules.market.data_feed import MarketDataWatcher
from src.modules.decision.engine import DecisionEngine
from src.modules.risk.manager import RiskManager
from src.modules.execution.engine import ExecutionEngine
from src.core.audit import audit_logger

def verify_system():
    setup_logging()
    logger = logging.getLogger("verification")
    logger.info("Starting Refactored Verification...")

    try:
        # 1. Init Modules
        market = MarketDataWatcher()
        decision_eng = DecisionEngine()
        risk = RiskManager()
        # Execution engine now requires provider
        exec_eng = ExecutionEngine(data_provider=market.provider)
        
        logger.info("Modules initialized.")
        logger.info(f"Provider Time: {market.provider.current_time()}")

        # 2. Fetch Data
        df = market.fetch_data()
        if df.empty:
            logger.error("Data fetch returned empty.")
            return
        logger.info(f"Data fetched: {len(df)} rows.")

        # 3. Decision
        decision = decision_eng.analyze(df)
        logger.info(f"Decision: {decision.decision} | {decision.reasoning}")
        
        if decision.approved_trade:
            logger.info(f"Proposal: {decision.approved_trade.model_dump_json(indent=2)}")
            
            # 4. Risk Test (Simulate)
            is_allowed = risk.check_trade(decision.approved_trade)
            logger.info(f"Risk Check: {is_allowed}")
            
            if is_allowed:
                exec_eng.execute_trade(decision.approved_trade)
                logger.info("Trade Executed (Shadow).")
        else:
            logger.info("No trade proposed.")

        # 5. Verify Audit Log Hash Chain
        # We just need to ensure the file exists and is readable
        if audit_logger.filepath.exists():
            logger.info(f"Audit Log Exists: {audit_logger.filepath}")
            logger.info(f"Last Hash: {audit_logger.last_hash}")
        else:
            logger.error("Audit log file missing!")

        logger.info("Verification Complete.")

    except Exception as e:
        logger.error(f"Verification Failed: {e}", exc_info=True)

if __name__ == "__main__":
    verify_system()
