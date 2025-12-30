from datetime import datetime, timedelta
from typing import List
from src.modules.events.models import EconomicEvent
from src.modules.events.provider import EconomicCalendarProvider

class MockCalendarProvider(EconomicCalendarProvider):
    def get_events(self, start_utc: datetime, end_utc: datetime, currencies: List[str]) -> List[EconomicEvent]:
        # Return a set of typical high-impact events for testing
        events = []
        
        # Example: NFP on first Friday of every month (roughly)
        # But let's just generate some events around the provided range for consistency
        
        current = start_utc
        while current < end_utc:
            # Add a High Impact USD event every Wednesday at 13:30 (e.g., CPI/NFP context)
            if current.weekday() == 2: # Wednesday
                events.append(EconomicEvent(
                    event_id=f"usd_cpi_{current.strftime('%Y%m%d')}",
                    timestamp_utc=current.replace(hour=13, minute=30, second=0, microsecond=0),
                    currency="USD",
                    title="Consumer Price Index (CPI) m/m",
                    impact="HIGH",
                    source="Mock",
                    tags=["CPI", "INFLATION"]
                ))
            
            # Add a Medium Impact EUR event every Tuesday at 09:00
            if current.weekday() == 1: # Tuesday
                events.append(EconomicEvent(
                    event_id=f"eur_gdp_{current.strftime('%Y%m%d')}",
                    timestamp_utc=current.replace(hour=9, minute=0, second=0, microsecond=0),
                    currency="EUR",
                    title="GDP Flash Estimate q/q",
                    impact="MEDIUM",
                    source="Mock",
                    tags=["GDP", "GROWTH"]
                ))
                
            current += timedelta(days=1)
            
        return [e for e in events if e.timestamp_utc >= start_utc and e.timestamp_utc <= end_utc]
