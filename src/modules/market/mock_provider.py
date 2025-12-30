import numpy as np
import pandas as pd
from typing import List
from datetime import datetime, timedelta
from src.core.interfaces import DataProvider
from src.core.models import Candle
from src.core.logger import logging

logger = logging.getLogger(__name__)

class MockDataProvider(DataProvider):
    def __init__(self):
        self._current_sim_time = datetime.utcnow()
        self._spread = 0.00015 # 1.5 pips fixed for now
    
    def current_time(self) -> datetime:
        return self._current_sim_time
        
    def fetch_spread(self, pair: str) -> float:
        return self._spread

    def fetch_candles(self, pair: str, timeframe: str, lookback: int) -> List[Candle]:
        """
        Generates synthetic OHLCV data ending at current_time.
        """
        # Parse timeframe to frequency (assuming '4h' -> '4H')
        freq = timeframe.upper()
        
        # Date range ending NOW (aligned to freq? Let's assume request comes perfectly aligned for now)
        end_date = self._current_sim_time
        start_date = end_date - (timedelta(hours=4) * lookback) # approx
        
        dates = pd.date_range(end=end_date, periods=lookback, freq=freq)
        
        # Random walk for price
        np.random.seed(42) # Consistent for now, maybe remove seed later for randomness
        returns = np.random.normal(0, 0.001, lookback)
        price_path = 1.10 * np.exp(np.cumsum(returns))
        
        candles = []
        for i, dt in enumerate(dates):
            close = float(price_path[i])
            open_p = float(price_path[i-1]) if i > 0 else close
            high = max(open_p, close) * 1.0005
            low = min(open_p, close) * 0.9995
            vol = float(np.random.randint(1000, 10000))
            
            candles.append(Candle(
                timestamp=dt,
                open=open_p,
                high=high,
                low=low,
                close=close,
                volume=vol
            ))
            
        return candles

