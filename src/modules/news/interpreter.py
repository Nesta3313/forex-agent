from typing import Literal, Dict
from src.core.logger import logging

logger = logging.getLogger(__name__)

class NewsInterpreter:
    def __init__(self):
        # Phase 1: No live connection.
        # Defaults to allowing trading.
        pass

    def get_market_state(self) -> Dict:
        """
        Returns the current news-based risk state.
        """
        return {
            "status": "ALLOW_TRADING", # ALLOW_TRADING, CAUTION, STAND_DOWN
            "risk_score": 0.0,
            "next_major_event": None
        }

    def can_trade(self) -> bool:
        state = self.get_market_state()
        return state["status"] == "ALLOW_TRADING"
