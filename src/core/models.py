from pydantic import BaseModel, Field
from typing import List, Optional, Literal, Dict
from datetime import datetime
from uuid import UUID, uuid4

class Candle(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float

class MarketSnapshot(BaseModel):
    timestamp: datetime
    pair: str
    timeframe: str
    close_price: float
    spread: float
    indicators: Dict[str, float]
    # Optionally include the raw candle if needed, but snapshots usually summarize state

class SignalOutput(BaseModel):
    name: str # e.g. "Trend", "Momentum"
    direction: Literal["BUY", "SELL", "HOLD"]
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str

class TradeProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    symbol: str
    direction: Literal["BUY", "SELL"]
    entry_price: float
    stop_loss: float
    take_profit: Optional[float]
    confidence: float
    reasoning: str
    # New fields for risk sizing (to be filled by Risk Manager or suggested by Strategy)
    suggested_risk_pct: float = 0.01

class RiskDecision(BaseModel):
    accepted: bool
    reason: str
    adjusted_size: float = 0.0 # Units
    proposal_id: UUID

class TradeExecution(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    timestamp: datetime
    symbol: str
    direction: Literal["BUY", "SELL"]
    fill_price: float
    size: float
    commission: float = 0.0
    slippage_incurred: float = 0.0
    risk_pct: float = 0.01 
    stop_loss: float
    take_profit: Optional[float] = None

from typing import Optional
class TradeDecision(BaseModel):
    decision: Literal["TRADE", "NO_TRADE", "STAND_DOWN"]
    reasoning: str
    approved_trade: Optional[TradeProposal] = None
