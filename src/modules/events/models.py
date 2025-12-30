from datetime import datetime
from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class EconomicEvent(BaseModel):
    event_id: str
    timestamp_utc: datetime
    currency: str
    title: str
    impact: Literal["LOW", "MEDIUM", "HIGH"]
    source: str = "OANDA"
    tags: List[str] = []
    actual: Optional[float] = None
    forecast: Optional[float] = None
    previous: Optional[float] = None

class EventRiskAssessment(BaseModel):
    status: Literal["ALLOW_TRADING", "CAUTION", "STAND_DOWN"]
    reason: str
    next_high_event_time: Optional[datetime] = None
    minutes_to_event: Optional[int] = None
    active_event_window: bool = False
    matched_event: Optional[EconomicEvent] = None
