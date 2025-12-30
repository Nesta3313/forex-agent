import pandas as pd
from typing import List
from src.core.models import SignalOutput
from src.core.logger import logging

logger = logging.getLogger(__name__)

class TrendSignal:
    def generate(self, df: pd.DataFrame) -> SignalOutput:
        if df.empty or 'SMA_50' not in df.columns or 'SMA_200' not in df.columns:
            return SignalOutput(name="Trend", direction="HOLD", confidence=0.0, reason="Insufficient Data")
            
        last = df.iloc[-1]
        sma_50 = last['SMA_50']
        sma_200 = last['SMA_200']
        close = last['Close']
        
        if sma_50 > sma_200 and close > sma_50:
            return SignalOutput(name="Trend", direction="BUY", confidence=0.8, reason="Price > SMA50 > SMA200")
        elif sma_50 < sma_200 and close < sma_50:
            return SignalOutput(name="Trend", direction="SELL", confidence=0.8, reason="Price < SMA50 < SMA200")
            
        return SignalOutput(name="Trend", direction="HOLD", confidence=0.0, reason="Neutral Trend")

class MomentumSignal:
    def generate(self, df: pd.DataFrame) -> SignalOutput:
        if df.empty or 'RSI' not in df.columns:
            return SignalOutput(name="Momentum", direction="HOLD", confidence=0.0, reason="Insufficient Data")
             
        rsi = df.iloc[-1]['RSI']
        
        if rsi < 30:
            return SignalOutput(name="Momentum", direction="BUY", confidence=0.7, reason="Oversold (RSI < 30)")
        elif rsi > 70:
            return SignalOutput(name="Momentum", direction="SELL", confidence=0.7, reason="Overbought (RSI > 70)")
        
        return SignalOutput(name="Momentum", direction="HOLD", confidence=0.5, reason="RSI Neutral")

class VolatilitySignal:
    def generate(self, df: pd.DataFrame) -> SignalOutput:
        if df.empty or 'Regime' not in df.columns:
            return SignalOutput(name="Volatility", direction="HOLD", confidence=0.0, reason="Insufficient Data")
            
        regime = df.iloc[-1]['Regime']
        if regime == 'VOLATILE':
            return SignalOutput(name="Volatility", direction="HOLD", confidence=0.0, reason="High Volatility Regime")
            
        return SignalOutput(name="Volatility", direction="HOLD", confidence=1.0, reason="Normal Volatility")
