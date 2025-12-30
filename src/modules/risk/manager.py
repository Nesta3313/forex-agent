from typing import Dict, Optional, List
from src.core.config import config
from src.core.models import TradeProposal, RiskDecision
from src.core.logger import logging
from src.core.audit import log_audit_event
from src.modules.risk.correlation import CorrelationMatrix

logger = logging.getLogger(__name__)

class RiskManager:
    def __init__(self):
        self.max_risk_per_trade = config.risk.get("max_risk_per_trade", 0.01)
        self.max_positions = config.risk.get("max_open_positions", 3)
        self.daily_loss_cap = config.risk.get("daily_loss_cap", 0.02)
        
        portfolio_cfg = config.risk.get("portfolio", {})
        self.max_total_risk = portfolio_cfg.get("max_total_risk_pct", 0.05)
        self.max_correlated_risk = portfolio_cfg.get("max_correlated_risk_pct", 0.03)
        
        self.correlation_matrix = CorrelationMatrix()
        
        # In-memory tracking (Should be synced with actual trade state)
        self.current_positions: List[Dict] = [] # List of {symbol, risk_pct, direction, id}
        self.daily_pnl = 0.0
        self.account_balance = config.execution.get("paper_balance", 10000.0)

    def sync_positions(self, open_positions: List[Dict]):
        """
        Updates internal tracking with actual open positions.
        Each position should have 'symbol' and 'risk_pct'.
        """
        self.current_positions = open_positions
        logger.debug(f"RiskManager synced. Open positions: {len(self.current_positions)}")

    def check_trade(self, proposal: TradeProposal) -> bool:
        """
        Validates trade against portfolio-wide rules.
        """
        logger.info(f"Risk Check for: {proposal.symbol} {proposal.direction}")

        # 1. hard validation
        if not proposal.stop_loss or proposal.stop_loss <= 0:
             self._log_rejection(proposal, "MISSING_STOP_LOSS")
             return False

        if proposal.entry_price <= 0:
             self._log_rejection(proposal, "Invalid entry price")
             return False

        # 2. Max Count
        if len(self.current_positions) >= self.max_positions:
            self._log_rejection(proposal, f"Max positions reached ({self.max_positions})")
            return False

        # 3. Daily Loss Cap
        if self.daily_pnl <= -(self.account_balance * self.daily_loss_cap):
            self._log_rejection(proposal, "Daily loss cap hit")
            return False

        # 4. Total Portfolio Risk-at-Risk
        current_total_risk = sum(p.get("risk_pct", 0.01) for p in self.current_positions)
        proposed_risk = proposal.suggested_risk_pct or self.max_risk_per_trade
        
        if (current_total_risk + proposed_risk) > self.max_total_risk:
            self._log_rejection(proposal, f"Portfolio risk cap exceeded ({current_total_risk+proposed_risk:.1%})")
            return False

        # 5. Correlated Group Risk
        groups = self.correlation_matrix.get_groups_for_pair(proposal.symbol)
        for group in groups:
            # Sum risk for all open positions in this same group
            group_members = [m.replace("/", "_") for m in self.correlation_matrix.groups.get(group, [])]
            group_risk = sum(p.get("risk_pct", 0.01) for p in self.current_positions if p['symbol'].replace("/", "_") in group_members)
            
            if (group_risk + proposed_risk) > self.max_correlated_risk:
                self._log_rejection(proposal, f"Correlated group cap hit: {group} ({group_risk+proposed_risk:.1%})")
                return False

        logger.info(f"Risk Approved for {proposal.symbol}")
        log_audit_event("RISK_APPROVED", {"proposal_id": str(proposal.id), "symbol": proposal.symbol})
        return True

    def calculate_position_size(self, proposal: TradeProposal) -> float:
        """
        Standardized sizing logic.
        """
        risk_pct = proposal.suggested_risk_pct or self.max_risk_per_trade
        risk_amount = self.account_balance * risk_pct
        risk_distance = abs(proposal.entry_price - proposal.stop_loss)
        
        if risk_distance == 0: return 0.0
        return risk_amount / risk_distance

    def _log_rejection(self, proposal: TradeProposal, reason: str):
        logger.warning(f"Risk Rejected: {proposal.symbol} | Reason: {reason}")
        log_audit_event("RISK_REJECTED", {"reason": reason, "proposal_id": str(proposal.id), "symbol": proposal.symbol})
