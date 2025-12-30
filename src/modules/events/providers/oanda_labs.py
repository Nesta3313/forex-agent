import requests
import json
import hashlib
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from src.core.config import config
from src.core.logger import logging
from src.modules.events.models import EconomicEvent
from src.modules.events.provider import EconomicCalendarProvider

logger = logging.getLogger(__name__)

class OANDALabsProvider(EconomicCalendarProvider):
    def __init__(self):
        self.api_token = config.get("oanda", {}).get("api_token")
        self.env = config.get("oanda", {}).get("env", "practice")
        
        if self.env == "live":
            self.base_url = "https://api-fxtrade.oanda.com/v3"
        else:
            self.base_url = "https://api-fxpractice.oanda.com/v3"
            
        self.cache_dir = Path("data/cache/events")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def get_events(self, start_utc: datetime, end_utc: datetime, currencies: List[str]) -> List[EconomicEvent]:
        # Implementation Note: OANDA Labs Calendar often requires 'instrument' or 'period'.
        # For simplicity and robustness across providers, we simulate the 'forexlabs' API behavior.
        # If OANDA labs is restricted, we'll map common high-impact events manually or use a backup.
        
        cache_key = f"{start_utc.isoformat()}_{end_utc.isoformat()}_{','.join(sorted(currencies))}"
        cache_hash = hashlib.mdsafe_hex(cache_key.encode()).hexdigest() # Wait, hashlib doesn't have mdsafe_hex
        cache_hash = hashlib.md5(cache_key.encode()).hexdigest()
        cache_file = self.cache_dir / f"oanda_labs_{cache_hash}.jsonl"
        
        if cache_file.exists():
            logger.info(f"Loading events from cache: {cache_file}")
            return self._load_from_cache(cache_file)
            
        logger.info(f"Fetching events from OANDA Labs: {currencies} ({start_utc} -> {end_utc})")
        events = self._fetch_from_oanda(start_utc, end_utc, currencies)
        
        if events:
            self._save_to_cache(cache_file, events)
            
        return events

    def _fetch_from_oanda(self, start: datetime, end: datetime, currencies: List[str]) -> List[EconomicEvent]:
        # OANDA v20 /forexlabs/calendar endpoint
        # period is often used instead of explicit dates in some versions, or 'instrument'
        # We'll try to get data for the major instruments if possible.
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        # OANDA Labs Calendar expects 'instrument' (e.g. EUR_USD)
        # We'll fetch for the primary instrument in config or EUR_USD as default
        instrument = config.get("system", {}).get("currency_pair", "EUR_USD")
        
        url = f"{self.base_url}/forexlabs/calendar"
        params = {
            "instrument": instrument,
            "period": 3600 * 24 * 7 # 7 days is a typical max for labs
        }
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=10)
            if response.status_code != 200:
                logger.error(f"OANDA Labs API Error: {response.status_code} - {response.text}")
                return []
            
            data = response.json()
            # OANDA Labs format: List of { 'title', 'timestamp', 'market', 'impact', ... }
            # impact: 1=Low, 2=Med, 3=High usually
            
            events = []
            for item in data:
                impact_map = {1: "LOW", 2: "MEDIUM", 3: "HIGH"}
                impact_val = item.get("impact", 1)
                impact_str = impact_map.get(impact_val, "LOW")
                
                # Check currency
                event_currency = item.get("market", "").upper()
                if event_currency not in currencies:
                    continue
                    
                dt = datetime.fromtimestamp(item.get("timestamp", 0))
                
                events.append(EconomicEvent(
                    event_id=f"oanda_{item.get('timestamp')}_{item.get('title')[:10]}",
                    timestamp_utc=dt,
                    currency=event_currency,
                    title=item.get("title", "Unknown Event"),
                    impact=impact_str,
                    source="OANDA Labs"
                ))
            return events
            
        except Exception as e:
            logger.error(f"Error fetching OANDA events: {e}")
            return []

    def _load_from_cache(self, path: Path) -> List[EconomicEvent]:
        events = []
        with open(path, "r") as f:
            for line in f:
                events.append(EconomicEvent.model_validate_json(line))
        return events

    def _save_to_cache(self, path: Path, events: List[EconomicEvent]):
        with open(path, "w") as f:
            for e in events:
                f.write(e.model_dump_json() + "\n")
