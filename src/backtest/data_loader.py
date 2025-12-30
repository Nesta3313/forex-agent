import os
import json
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Optional
from src.core.config import config
from src.core.models import Candle
from src.core.logger import logging

logger = logging.getLogger(__name__)

class OANDADataLoader:
    def __init__(self):
        self.token = os.getenv("OANDA_API_TOKEN")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        self.env = os.getenv("OANDA_ENV", "practice")
        
        if self.env == "live":
            self.base_url = "https://api-fxtrade.oanda.com"
        else:
            self.base_url = "https://api-fxpractice.oanda.com"
            
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        self.cache_dir = Path(config.get("backtest", {}).get("cache_dir", "data/cache"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_history(self, instrument: str, granularity: str, start: str, end: str) -> List[Candle]:
        """
        Fetch historical candles from OANDA or local cache.
        """
        # Create a unique cache filename
        safe_start = start.replace(":", "-")
        safe_end = end.replace(":", "-")
        cache_file = self.cache_dir / f"oanda_{instrument}_{granularity}_{safe_start}_{safe_end}.jsonl"
        
        if cache_file.exists():
            logger.info(f"Loading candles from cache: {cache_file}")
            return self._load_from_cache(cache_file)
            
        logger.info(f"Fetching candles from OANDA: {instrument} {granularity} ({start} -> {end})")
        candles = self._fetch_from_oanda(instrument, granularity, start, end)
        
        if candles:
            self._save_to_cache(cache_file, candles)
            
        return candles

    def _fetch_from_oanda(self, instrument: str, granularity: str, start: str, end: str) -> List[Candle]:
        url = f"{self.base_url}/v3/instruments/{instrument}/candles"
        
        all_candles = []
        current_from = start
        
        while True:
            params = {
                "from": current_from,
                "to": end,
                "granularity": granularity,
                "price": "M"
            }
            
            try:
                r = requests.get(url, headers=self.headers, params=params, timeout=20)
                if r.status_code != 200:
                    logger.error(f"OANDA API Error: {r.status_code} - {r.text}")
                    break
                    
                data = r.json()
                batch = data.get("candles", [])
                
                if not batch:
                    break
                    
                for c in batch:
                    if not c["complete"]:
                        continue
                    
                    mid = c["mid"]
                    dt = datetime.strptime(c["time"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                    
                    all_candles.append(Candle(
                        timestamp=dt,
                        open=float(mid["o"]),
                        high=float(mid["h"]),
                        low=float(mid["l"]),
                        close=float(mid["c"]),
                        volume=int(c["volume"])
                    ))
                
                # Check if we reached the end
                last_time = batch[-1]["time"]
                if len(batch) < 500:
                    break
                    
                # Increment from time to avoid overlap (OANDA 'from' is exclusive usually, but let's be sure)
                current_from = last_time
                
            except Exception as e:
                logger.error(f"Failed to fetch historical batch: {e}")
                break
                
        return all_candles

    def _save_to_cache(self, path: Path, candles: List[Candle]):
        with open(path, 'w') as f:
            for c in candles:
                f.write(c.model_dump_json() + "\n")
        logger.info(f"Saved {len(candles)} candles to cache.")

    def _load_from_cache(self, path: Path) -> List[Candle]:
        candles = []
        with open(path, 'r') as f:
            for line in f:
                candles.append(Candle.model_validate_json(line))
        return candles
