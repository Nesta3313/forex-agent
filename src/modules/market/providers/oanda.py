import os
import requests
import time
from typing import List, Optional
from datetime import datetime
from src.core.interfaces import DataProvider
from src.core.models import Candle
from src.core.config import config
from src.core.logger import logging

logger = logging.getLogger(__name__)

class OANDAProvider(DataProvider):
    def __init__(self):
        self.env = config.data.get("oanda", {}).get("environment", "practice")
        self.token = os.getenv("OANDA_API_TOKEN")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        
        if not self.token or not self.account_id:
            raise ValueError("OANDA_API_TOKEN or OANDA_ACCOUNT_ID not found in .env")

        if self.env == "live":
            self.base_url = "https://api-fxtrade.oanda.com"
        else:
            self.base_url = "https://api-fxpractice.oanda.com"
            
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
        
        self.instrument_map = config.data.get("oanda", {}).get("instrument_map", {})

    def _get_oanda_symbol(self, pair: str) -> str:
        return self.instrument_map.get(pair, pair.replace("/", "_"))

    def current_time(self) -> datetime:
        return datetime.utcnow()

    def fetch_spread(self, pair: str) -> float:
        symbol = self._get_oanda_symbol(pair)
        url = f"{self.base_url}/v3/accounts/{self.account_id}/pricing"
        params = {"instruments": symbol}
        
        try:
            resp = self._request_with_retry(url, params=params)
            if resp and "prices" in resp and len(resp["prices"]) > 0:
                price = resp["prices"][0]
                bid = float(price["bids"][0]["price"])
                ask = float(price["asks"][0]["price"])
                return ask - bid
        except Exception as e:
            logger.error(f"Failed to fetch spread: {e}")
        
        return 0.00015 # Fallback 1.5 pips

    def fetch_candles(self, pair: str, timeframe: str, lookback: int) -> List[Candle]:
        symbol = self._get_oanda_symbol(pair)
        url = f"{self.base_url}/v3/instruments/{symbol}/candles"
        
        # OANDA granularity mapping
        granularity = timeframe.upper().replace("4H", "H4")
        
        params = {
            "count": lookback,
            "granularity": granularity,
            "price": "M" # Mid price
        }
        
        resp = self._request_with_retry(url, params=params)
        candles = []
        
        if resp and "candles" in resp:
            for c in resp["candles"]:
                if not c["complete"]:
                    continue
                    
                mid = c["mid"]
                dt = datetime.strptime(c["time"].split(".")[0], "%Y-%m-%dT%H:%M:%S")
                
                candles.append(Candle(
                    timestamp=dt,
                    open=float(mid["o"]),
                    high=float(mid["h"]),
                    low=float(mid["l"]),
                    close=float(mid["c"]),
                    volume=int(c["volume"])
                ))
                
        return candles

    def _request_with_retry(self, url, params=None, retries=3):
        for i in range(retries):
            try:
                r = requests.get(url, headers=self.headers, params=params, timeout=10)
                if r.status_code == 200:
                    return r.json()
                elif r.status_code in [401, 403]:
                    logger.critical(f"OANDA Auth Error: {r.text}")
                    raise PermissionError("Invalid OANDA Credentials")
                elif r.status_code == 429:
                    time.sleep(2 ** i) # Backoff
            except requests.RequestException as e:
                time.sleep(0.5 * (i + 1))
        
        return None
