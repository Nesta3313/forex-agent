from typing import Optional
import pandas as pd
from uuid import uuid4
from datetime import datetime

from src.core.models import TradeProposal, TradeDecision, SignalOutput
from src.modules.signals.generators import TrendSignal, MomentumSignal, VolatilitySignal
from src.modules.news.interpreter import NewsInterpreter
from src.core.logger import logging
from src.core.audit import log_audit_event

logger = logging.getLogger(__name__)

class DecisionEngine:
    def __init__(self, event_engine: Optional['EventRiskEngine'] = None):
        self.trend_signal = TrendSignal()
        self.momentum_signal = MomentumSignal()
        self.volatility_signal = VolatilitySignal()
        self.news_interpreter = NewsInterpreter()
        self.event_engine = event_engine

    def analyze(self, df: pd.DataFrame, instrument: str = "EUR_USD", current_time: Optional[datetime] = None) -> TradeDecision:
        if df.empty:
            return TradeDecision(decision="NO_TRADE", reasoning="No Data")

        # 1. Check Economic Calendar Risk
        if self.event_engine:
            now = current_time or datetime.utcnow()
            assessment = self.event_engine.assess_risk(now, instrument)
            if assessment.status == "STAND_DOWN":
                return TradeDecision(decision="STAND_DOWN", reasoning=f"EVENT_STAND_DOWN: {assessment.reason}")

        # 2. Check News (Sentiment/Interpreter)
        if not self.news_interpreter.can_trade():
             return TradeDecision(decision="STAND_DOWN", reasoning="News Event Risk")

        # 3. Generate Signals
        s_trend = self.trend_signal.generate(df)
        s_momentum = self.momentum_signal.generate(df)
        s_vol = self.volatility_signal.generate(df)
        
        # Log signals
        log_audit_event("SIGNALS_GENERATED", {
            "trend": s_trend.model_dump(),
            "momentum": s_momentum.model_dump(),
            "volatility": s_vol.model_dump()
        })

        # 4. Aggregation
        # Risk Filter
        if s_vol.reason == "High Volatility Regime":
             return TradeDecision(decision="NO_TRADE", reasoning=f"Volatility Filter: {s_vol.reason}")

        latest_close = float(df.iloc[-1]['Close'])
        latest_atr = float(df.iloc[-1]['ATR'])

        proposal = None
        decision_str = "NO_TRADE"
        reason = "Signals Mixed"
        
        if s_trend.direction == "BUY":
            # Require Momentum != SELL
            if s_momentum.direction != "SELL":
                sl = latest_close - (2 * latest_atr)
                tp = latest_close + (3 * latest_atr)
                
                proposal = TradeProposal(
                    id=uuid4(),
                    timestamp=datetime.utcnow(),
                    symbol="EURUSD", 
                    direction="BUY",
                    entry_price=latest_close,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=s_trend.confidence,
                    reasoning=f"Trend Buy + Momentum {s_momentum.direction}"
                )
                decision_str = "TRADE"
                reason = "Signals Aligned BUY"

        elif s_trend.direction == "SELL":
            # Require Momentum != BUY
            if s_momentum.direction != "BUY":
                sl = latest_close + (2 * latest_atr)
                tp = latest_close - (3 * latest_atr)
                
                proposal = TradeProposal(
                    id=uuid4(),
                    timestamp=datetime.utcnow(),
                    symbol="EURUSD",
                    direction="SELL", 
                    entry_price=latest_close,
                    stop_loss=sl,
                    take_profit=tp,
                    confidence=s_trend.confidence,
                    reasoning=f"Trend Sell + Momentum {s_momentum.direction}"
                )
                decision_str = "TRADE"
                reason = "Signals Aligned SELL"

        return TradeDecision(decision=decision_str, reasoning=reason, approved_trade=proposal)
