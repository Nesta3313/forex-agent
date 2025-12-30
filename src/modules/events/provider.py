from abc import ABC, abstractmethod
from datetime import datetime
from typing import List
from src.modules.events.models import EconomicEvent

class EconomicCalendarProvider(ABC):
    @abstractmethod
    def get_events(self, start_utc: datetime, end_utc: datetime, currencies: List[str]) -> List[EconomicEvent]:
        """
        Fetch economic events for given currencies and time range.
        """
        pass
