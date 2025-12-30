from datetime import datetime
from typing import Optional
from src.core.audit import log_audit_event

class HealthMonitor:
    def __init__(self):
        pass

    def log_data_health(self, provider: str, status: str, 
                       last_candle_time: str, minutes_stale: float, 
                       latency_ms: int, retries: int, notes: str = ""):
        """
        Logs a DATA_HEALTH event to the audit log.
        """
        payload = {
            "provider": provider,
            "status": status, # OK | WARNING | ERROR
            "last_candle_time": last_candle_time,
            "minutes_stale": minutes_stale,
            "latency_ms": latency_ms,
            "retries_used": retries,
            "notes": notes
        }
        log_audit_event("DATA_HEALTH", payload)

health_monitor = HealthMonitor()
