import pandas as pd
from typing import Optional, Dict, List
from datetime import datetime, timedelta
from src.core.config import config
from src.core.logger import logging
from src.core.interfaces import DataProvider
from src.modules.market.mock_provider import MockDataProvider
from src.modules.market.providers.oanda import OANDAProvider
from src.core.models import Candle
from src.core.health import health_monitor
from src.core.state import state_manager

logger = logging.getLogger(__name__)

class MarketDataWatcher:
    def __init__(self):
        self.symbol = config.system.get("currency_pair", "EURUSD")
        self.timeframe = config.system.get("timeframe", "4h")
        self.source = config.data.get("source", "mock")
        
        # Factory Logic
        if self.source == "oanda":
            self.provider: DataProvider = OANDAProvider()
        else:
            self.provider: DataProvider = MockDataProvider()
            
        self.df: Optional[pd.DataFrame] = None

    def fetch_data(self) -> pd.DataFrame:
        start_time = datetime.utcnow()
        try:
            # 1. Fetch Candles
            lookback = config.data.get("lookback_candles", 300)
            candles: List[Candle] = self.provider.fetch_candles(self.symbol, self.timeframe, lookback)
            
            if not candles:
                health_monitor.log_data_health(self.source, "ERROR", "", 0, 0, 0, "No candles returned")
                return pd.DataFrame()

            last_candle = candles[-1]
            
            # 2. Safety Check: Alignment
            # Expected 4H alignment (assuming UTC 0,4,8...)
            is_aligned = last_candle.timestamp.hour % 4 == 0 and last_candle.timestamp.minute == 0
            
            # Calculate Staleness
            now = datetime.utcnow()
            diff_minutes = (now - last_candle.timestamp).total_seconds() / 60
            
            # 3. Duplicate Check
            last_processed = state_manager.get_last_processed_candle()
            if last_processed and last_processed == last_candle.timestamp:
                logger.warning(f"Duplicate candle processed: {last_candle.timestamp}")
                health_monitor.log_data_health(self.source, "WARNING", str(last_candle.timestamp), 
                                             diff_minutes, 0, 0, "Duplicate Candle")
                # We might typically "return empty" to skip processing, but let's decide carefully.
                # If we return empty, the main loop skips. Correct.
                return pd.DataFrame()

            # 4. Log Health
            status = "OK"
            msg = ""
            if not is_aligned: 
                status = "WARNING"
                msg += "Unaligned Candle; "
            if diff_minutes > 250: # 4H candle + 10 mins buffer
                status = "WARNING"
                msg += "Stale Data; "
                
            latency = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            health_monitor.log_data_health(self.source, status, str(last_candle.timestamp), 
                                         diff_minutes, latency, 0, msg)

            if status == "ERROR":
                return pd.DataFrame()

            # 5. Process
            data = [c.model_dump() for c in candles]
            df = pd.DataFrame(data)
            df.set_index('timestamp', inplace=True)
            df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close', 'volume': 'Volume'}, inplace=True)
            
            self.df = df
            self._calculate_indicators()
            self._save_latest_data()
            
            # Update State
            state_manager.set_last_processed_candle(last_candle.timestamp)
            
            return self.df
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}", exc_info=True)
            health_monitor.log_data_health(self.source, "ERROR", "", 0, 0, 0, str(e))
            return pd.DataFrame()

    def _calculate_indicators(self):
        if self.df is None or self.df.empty:
            return

        close = self.df['Close']
        high = self.df['High']
        low = self.df['Low']

        self.df['SMA_50'] = close.rolling(window=50).mean()
        self.df['SMA_200'] = close.rolling(window=200).mean()

        previous_close = close.shift(1)
        tr = pd.concat([high - low, (high - previous_close).abs(), (low - previous_close).abs()], axis=1).max(axis=1)
        self.df['ATR'] = tr.rolling(window=14).mean()

        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        self.df['RSI'] = 100 - (100 / (1 + rs))

        atr_ma = self.df['ATR'].rolling(window=50).mean()
        self.df['Regime'] = "NORMAL"
        if not atr_ma.empty:
             ratio = self.df['ATR'] / atr_ma
             self.df.loc[ratio > 1.5, 'Regime'] = 'VOLATILE'

    def _save_latest_data(self):
        try:
            from pathlib import Path
            p = Path("logs/market_data.csv")
            self.df.to_csv(p)
        except Exception as e:
            logger.error(f"Failed to save CSV: {e}")
