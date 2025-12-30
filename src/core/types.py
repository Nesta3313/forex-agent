from dataclasses import dataclass
from typing import Optional, Literal
from datetime import datetime

class TradeProposal:
    """
    Proposed trade from the Decision Engine. 
    Has not yet been validated by Risk Manager.
    """
    def __init__(self, 
                 symbol: str, 
                 direction: Literal["BUY", "SELL"], 
                 confidence: float, 
                 entry_price: float,
                 stop_loss: float,
                 take_profit: Optional[float],
                 reasoning: str,
                 signal_source: str):
        self.symbol = symbol
        self.direction = direction
        self.confidence = confidence
        self.entry_price = float(entry_price)
        self.stop_loss = float(stop_loss)
        self.take_profit = float(take_profit) if take_profit else None
        self.reasoning = reasoning
        self.signal_source = signal_source
        self.timestamp = datetime.utcnow()

    def __repr__(self):
        return f"<TradeProposal {self.direction} {self.symbol} @ {self.entry_price}>"

@dataclass
class TradeDecision:
    """
    Final decision output.
    """
    decision: Literal["TRADE", "NO_TRADE", "STAND_DOWN"]
    reasoning: str
    approved_trade: Optional[TradeProposal] = None
