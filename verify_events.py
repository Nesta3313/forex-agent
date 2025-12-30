import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.append(str(Path(__file__).resolve().parent))

from src.core.config import config
from src.core.logger import setup_logging, logging
from src.modules.events.engine import EventRiskEngine
from src.core.audit import AuditLogger

def verify():
    setup_logging()
    logger = logging.getLogger("verify_events")
    logger.info("Starting Event Risk Verification...")
    
    audit_logger = AuditLogger("logs/audit.jsonl")
    engine = EventRiskEngine(audit_logger=audit_logger)
    
    now = datetime.utcnow()
    instrument = "EUR_USD"
    
    # 1. Test Prefetch
    logger.info("Testing event prefetch (7 days)...")
    engine.prefetch(now, now + timedelta(days=7), instrument)
    logger.info(f"Fetched {len(engine.events_cache)} events.")
    
    # 2. Print next 5 HIGH events
    high_events = [e for e in engine.events_cache if e.impact == "HIGH"]
    logger.info(f"Upcoming HIGH impact events ({len(high_events)} total):")
    for e in sorted(high_events, key=lambda x: x.timestamp_utc)[:5]:
        logger.info(f"  - {e.timestamp_utc} | {e.currency} | {e.title}")
        
    # 3. Assess Risk NOW
    logger.info(f"Assessing risk for NOW ({now}):")
    assessment = engine.assess_risk(now, instrument)
    logger.info(f"  Status: {assessment.status}")
    logger.info(f"  Reason: {assessment.reason}")
    
    # 4. Test Stand-Down Window (Simulate being exactly 30 mins before a high event)
    if high_events:
        target_event = high_events[0]
        test_time = target_event.timestamp_utc - timedelta(minutes=30)
        logger.info(f"Assessing risk for simulated time (30m before high event): {test_time}")
        assessment_sim = engine.assess_risk(test_time, instrument)
        logger.info(f"  Status: {assessment_sim.status}")
        logger.info(f"  Reason: {assessment_sim.reason}")
        
        if assessment_sim.status == "STAND_DOWN":
            logger.info("✅ STAND_DOWN correctly triggered.")
        else:
            logger.error("❌ STAND_DOWN failed to trigger.")
            
    logger.info("Verification Complete. Check dashboard and audit.jsonl.")

if __name__ == "__main__":
    verify()
