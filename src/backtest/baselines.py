import pandas as pd
from typing import List, Dict
from src.core.models import Candle

class BaselineStrategy:
    def __init__(self, initial_balance: float):
        self.initial_balance = initial_balance
        self.equity = initial_balance
        self.equity_history = []
        self.trades = []

    def get_equity_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.equity_history)

    def get_trades_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.trades)

class NoTradeBaseline(BaselineStrategy):
    def run(self, candles: List[Candle]):
        for candle in candles:
            self.equity_history.append({
                "timestamp": candle.timestamp,
                "equity": self.equity
            })

class MACrossoverBaseline(BaselineStrategy):
    def __init__(self, initial_balance: float, fast_period: int = 50, slow_period: int = 200):
        super().__init__(initial_balance)
        self.fast = fast_period
        self.slow = slow_period

    def run(self, candles: List[Candle]):
        df = pd.DataFrame([c.model_dump() for c in candles])
        df['fast_ma'] = df['close'].rolling(window=self.fast).mean()
        df['slow_ma'] = df['close'].rolling(window=self.slow).mean()
        
        position = 0 # 0: none, 1: long, -1: short
        entry_price = 0
        
        for i in range(self.slow, len(df)):
            row = df.iloc[i]
            prev_row = df.iloc[i-1]
            
            # Simple Crossover logic
            # Fast crosses above slow -> BUY
            # Fast crosses below slow -> SELL
            
            if row['fast_ma'] > row['slow_ma'] and prev_row['fast_ma'] <= prev_row['slow_ma']:
                # Buy signal
                if position == -1: # Close short first
                    self._close_trade(row['open'], row['timestamp'], "BUY_TO_COVER")
                if position == 0:
                    self._open_trade(row['open'], row['timestamp'], "BUY")
                    position = 1
                    
            elif row['fast_ma'] < row['slow_ma'] and prev_row['fast_ma'] >= prev_row['slow_ma']:
                # Sell signal
                if position == 1: # Close long
                    self._close_trade(row['open'], row['timestamp'], "SELL")
                if position == 0:
                    self._open_trade(row['open'], row['timestamp'], "SELL_SHORT")
                    position = -1
            
            self.equity_history.append({
                "timestamp": row['timestamp'],
                "equity": self.equity # In reality, equity fluctuates, but we simplify for baseline
            })

    def _open_trade(self, price: float, time: pd.Timestamp, direction: str):
        self.current_trade = {
            "direction": direction,
            "entry_time": time,
            "entry_price": price,
            "size": 0.1
        }

    def _close_trade(self, price: float, time: pd.Timestamp, reason: str):
        if hasattr(self, 'current_trade') and self.current_trade:
            side = self.current_trade['direction']
            if side == "BUY":
                pnl = (price - self.current_trade['entry_price']) * 0.1 * 100000
            else:
                pnl = (self.current_trade['entry_price'] - price) * 0.1 * 100000
            
            self.equity += pnl
            self.trades.append({
                **self.current_trade,
                "exit_time": time,
                "exit_price": price,
                "pnl": pnl,
                "exit_reason": reason
            })
            self.current_trade = None
