from typing import List, Dict, Optional
from src.core.config import config
from src.core.logger import logging
from src.core.audit import log_audit_event

logger = logging.getLogger(__name__)

class PositionManager:
    def __init__(self):
        self.cfg = config.risk.get("management", {})
        self.trailing_cfg = self.cfg.get("trailing_stop", {})
        self.be_cfg = self.cfg.get("break_even", {})

    def evaluate_position(self, pos: Dict, current_price: float) -> Optional[Dict]:
        """
        Evaluates an open position and returns updates if management rules trigger.
        Updates can include 'stop_loss' change.
        """
        updates = {}
        symbol = pos.get('symbol', 'UNKNOWN')
        direction = pos.get('direction')
        entry_price = pos.get('fill_price') or pos.get('entry_price') # Backtest uses entry_price, Live uses fill_price
        current_sl = pos.get('stop_loss') or pos.get('sl') # Backtest uses sl, Live uses stop_loss
        
        # Calculate Pips profit
        multiplier = 100.0 if symbol and "JPY" in symbol else 10000.0
        
        if direction == "BUY":
            profit_pips = (current_price - entry_price) * multiplier
        else:
            profit_pips = (entry_price - current_price) * multiplier

        # 1. Break-Even Logic
        if self.be_cfg.get("enabled"):
            be_activation = self.be_cfg.get("activation_pips", 20)
            # If in profit by activation pips and SL is not already at or better than entry
            if profit_pips >= be_activation:
                if (direction == "BUY" and current_sl < entry_price) or \
                   (direction == "SELL" and current_sl > entry_price):
                    updates['stop_loss'] = entry_price
                    logger.info(f"Break-even triggered for {symbol} {pos.get('id')}")
        
        # 2. Trailing Stop Logic
        if self.trailing_cfg.get("enabled"):
            activation = self.trailing_cfg.get("activation_pips", 30)
            distance = self.trailing_cfg.get("distance_pips", 20)
            
            if profit_pips >= activation:
                new_sl = 0.0
                if direction == "BUY":
                    potential_sl = current_price - (distance / multiplier)
                    if potential_sl > current_sl:
                        new_sl = potential_sl
                else:
                    potential_sl = current_price + (distance / multiplier)
                    if potential_sl < current_sl:
                        new_sl = potential_sl
                
                if new_sl > 0:
                    updates['stop_loss'] = new_sl
                    logger.info(f"Trailing SL updated for {symbol} {pos.get('id')} to {new_sl:.5f}")

        return updates if updates else None
