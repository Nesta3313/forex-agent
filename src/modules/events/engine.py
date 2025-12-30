from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from src.core.config import config
from src.core.logger import logging
from src.core.audit import AuditLogger
from src.modules.events.models import EconomicEvent, EventRiskAssessment
from src.modules.events.providers.mock import MockCalendarProvider
from src.modules.events.providers.oanda_labs import OANDALabsProvider

logger = logging.getLogger(__name__)

class EventRiskEngine:
    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self.cfg = config.get("events", {})
        self.enabled = self.cfg.get("enabled", False)
        self.provider_name = self.cfg.get("provider", "mock")
        
        if self.provider_name == "oanda":
            self.provider = OANDALabsProvider()
        else:
            self.provider = MockCalendarProvider()
            
        self.audit_logger = audit_logger
        self.events_cache: List[EconomicEvent] = []
        self.last_fetch: Optional[datetime] = None
        self.force_status: Optional[str] = None # For verification ONLY

    def prefetch(self, start: datetime, end: datetime, instrument: str):
        """
        Prefetch events for a given range and instrument.
        """
        if not self.enabled:
            return
            
        currencies = self.cfg.get("currencies_by_instrument", {}).get(instrument, ["USD", "EUR"])
        self.events_cache = self.provider.get_events(start, end, currencies)
        self.last_fetch = datetime.utcnow()
        
        if self.audit_logger:
            self.audit_logger.log_event("EVENTS_FETCH", {
                "count": len(self.events_cache),
                "range_start": str(start),
                "range_end": str(end),
                "currencies": currencies
            })

    def assess_risk(self, now: datetime, instrument: str) -> EventRiskAssessment:
        if self.force_status:
            return EventRiskAssessment(
                status=self.force_status,
                reason=f"FORCED STATUS ({self.force_status})",
                active_event_window=True
            )

        if not self.enabled:
            return EventRiskAssessment(status="ALLOW_TRADING", reason="Events Filter Disabled")
            
        # Ensure we have events (if none fetched, try a small window)
        if not self.events_cache:
            self.prefetch(now - timedelta(days=1), now + timedelta(days=7), instrument)

        currencies = self.cfg.get("currencies_by_instrument", {}).get(instrument, ["USD", "EUR"])
        stand_down_cfg = self.cfg.get("stand_down", {})
        caution_cfg = self.cfg.get("caution", {})
        
        sd_impacts = stand_down_cfg.get("impact_levels", ["HIGH"])
        sd_pre = stand_down_cfg.get("pre_minutes", 60)
        sd_post = stand_down_cfg.get("post_minutes", 30)
        
        c_impacts = caution_cfg.get("impact_levels", ["MEDIUM"])
        c_pre = caution_cfg.get("pre_minutes", 30)
        c_post = caution_cfg.get("post_minutes", 15)
        
        highest_severity = "ALLOW_TRADING"
        reason = "No upcoming high-impact events"
        matched_event = None
        next_high_time = None
        min_to_event = None
        
        # Sort events by time
        relevant_events = sorted([e for e in self.events_cache if e.currency in currencies], key=lambda x: x.timestamp_utc)
        
        for event in relevant_events:
            event_time = event.timestamp_utc
            diff_mins = (event_time - now).total_seconds() / 60.0
            
            # Check Stand Down (High Impact)
            if event.impact in sd_impacts:
                if -sd_post <= diff_mins <= sd_pre:
                    highest_severity = "STAND_DOWN"
                    reason = f"Event Stand-Down: {event.title} ({event.impact})"
                    matched_event = event
                    # Found the active one, can stop
                    break
                
                if diff_mins > 0 and (next_high_time is None or event_time < next_high_time):
                    next_high_time = event_time
                    min_to_event = int(diff_mins)

            # Check Caution (Medium Impact) - only if not already in stand down
            if highest_severity != "STAND_DOWN" and event.impact in c_impacts:
                if -c_post <= diff_mins <= c_pre:
                    highest_severity = "CAUTION"
                    reason = f"Event Caution: {event.title} ({event.impact})"
                    matched_event = event

        assessment = EventRiskAssessment(
            status=highest_severity,
            reason=reason,
            next_high_event_time=next_high_time,
            minutes_to_event=min_to_event,
            active_event_window=(matched_event is not None),
            matched_event=matched_event
        )
        
        if self.audit_logger:
            import json
            # Use model_dump_json to ensure all types (datetime, etc) are serializable
            safe_payload = json.loads(assessment.model_dump_json())
            self.audit_logger.log_event("EVENT_RISK", safe_payload)
            
        return assessment
