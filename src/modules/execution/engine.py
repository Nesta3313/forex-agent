import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from typing import List, Dict
from src.core.models import TradeProposal, TradeExecution
from src.core.logger import logging
from src.core.audit import log_audit_event
from src.core.interfaces import DataProvider

logger = logging.getLogger(__name__)

class ExecutionEngine:
    def __init__(self, data_provider: DataProvider):
        self.positions_file = Path("positions.json")
        self.provider = data_provider
        self.balance = 10000.0 # Initial Balance
        # Load state if exists (TODO: Full persistence)
        
    def execute_trade(self, proposal: TradeProposal, event_risk: str = "ALLOW_TRADING") -> bool:
        """
        Executes a trade with simulated spread and slippage.
        Belt-and-suspenders: Refuses entry if event_risk is STAND_DOWN.
        """
        # 1. Defensive Gating
        if event_risk == "STAND_DOWN":
            logger.error(f"EXECUTION BLOCKED: STAND_DOWN event detected during execution call for {proposal.symbol}")
            log_audit_event("EVENT_GATE_LEAK_PREVENTED", {
                "proposal_id": str(proposal.id),
                "symbol": proposal.symbol,
                "reason": "Hard gating in ExecutionEngine"
            })
            return False

        # 2. Mandatory Stop Loss Check
        if not proposal.stop_loss or proposal.stop_loss <= 0:
            logger.error(f"EXECUTION BLOCKED: Missing or invalid Stop Loss for {proposal.symbol}")
            log_audit_event("MISSING_STOP_LOSS_BLOCK_EXECUTION", {
                "proposal_id": str(proposal.id),
                "symbol": proposal.symbol
            })
            return False

        # Get Simulation Parameters
        spread = self.provider.fetch_spread(proposal.symbol)
        slippage_bps = 2.0 # 2 basis points slippage assumption
        slippage = proposal.entry_price * (slippage_bps / 10000.0)
        
        if proposal.direction == "BUY":
            fill_price = proposal.entry_price + (spread / 2) + slippage
        else:
            fill_price = proposal.entry_price - (spread / 2) - slippage
            
        # Create Execution Record
        execution = TradeExecution(
            id=uuid4(), # Ensure unique ID for position management
            proposal_id=proposal.id,
            timestamp=datetime.utcnow(),
            symbol=proposal.symbol,
            direction=proposal.direction,
            fill_price=fill_price,
            size=0.1, # TODO: Advanced sizing
            slippage_incurred=slippage,
            risk_pct=proposal.suggested_risk_pct,
            stop_loss=proposal.stop_loss,
            take_profit=proposal.take_profit
        )
        
        logger.info(f"EXECUTED {execution.direction} {execution.symbol} @ {execution.fill_price:.5f} (SL: {execution.stop_loss})")
        
        self._persist_execution(execution)
        log_audit_event("TRADE_EXECUTED", execution.model_dump(mode='json'))
        return True

    def get_open_positions(self) -> List[Dict]:
        """
        Returns all currently active positions.
        """
        if not self.positions_file.exists():
            return []
        try:
            with open(self.positions_file, 'r') as f:
                return json.load(f)
        except:
            return []

    def update_position(self, pos_id: str, updates: Dict) -> bool:
        """
        Updates an existing position (e.g. trailing stop).
        """
        positions = self.get_open_positions()
        found = False
        for p in positions:
            if str(p.get('id')) == str(pos_id):
                p.update(updates)
                found = True
                break
        
        if found:
            with open(self.positions_file, 'w') as f:
                json.dump(positions, f, indent=2)
            return True
        return False

    def close_position(self, pos_id: str, exit_price: float, reason: str) -> bool:
        """
        Closes a position and moves it to history.
        """
        # For Phase 1 simplified: just remove from positions.json and log audit
        positions = self.get_open_positions()
        new_positions = [p for p in positions if str(p.get('id')) != str(pos_id)]
        
        if len(new_positions) < len(positions):
            with open(self.positions_file, 'w') as f:
                json.dump(new_positions, f, indent=2)
            log_audit_event("TRADE_CLOSED", {"id": pos_id, "exit_price": exit_price, "reason": reason})
            return True
        return False

    def _persist_execution(self, execution: TradeExecution):
        data = self.get_open_positions()
        data.append(execution.model_dump(mode='json'))
        with open(self.positions_file, 'w') as f:
            json.dump(data, f, indent=2)
