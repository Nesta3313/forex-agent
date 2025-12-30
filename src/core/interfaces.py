from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from src.core.models import Candle

class DataProvider(ABC):
    @abstractmethod
    def fetch_candles(self, pair: str, timeframe: str, lookback: int) -> List[Candle]:
        """
        Fetches historical candles.
        """
        pass

    @abstractmethod
    def fetch_spread(self, pair: str) -> float:
        """
        Returns current spread for the pair.
        """
        pass
    
    @abstractmethod
    def current_time(self) -> datetime:
        """
        Returns the current provider time (simulated or real).
        """
        pass
