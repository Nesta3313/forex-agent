from typing import List, Dict, Set
from src.core.config import config

class CorrelationMatrix:
    def __init__(self):
        self.cfg = config.risk.get("portfolio", {})
        self.groups = self.cfg.get("correlation_groups", {})
        self.default_corr = self.cfg.get("default_correlation", 0.5)

    def get_groups_for_pair(self, pair: str) -> List[str]:
        """
        Returns a list of group names the pair belongs to.
        Supports both OANDA (EUR_USD) and internal (EUR/USD) formats by normalizing.
        """
        norm_pair = pair.replace("/", "_")
        matched_groups = []
        for group_name, members in self.groups.items():
            if norm_pair in [m.replace("/", "_") for m in members]:
                matched_groups.append(group_name)
        return matched_groups

    def get_correlated_pairs(self, pair: str) -> Set[str]:
        """
        Returns all pairs that share at least one correlation group with the given pair.
        """
        norm_pair = pair.replace("/", "_")
        groups = self.get_groups_for_pair(norm_pair)
        correlated = set()
        for group in groups:
            for member in self.groups[group]:
                correlated.add(member.replace("/", "_"))
        
        if norm_pair in correlated:
            correlated.remove(norm_pair)
        return correlated

    def is_correlated(self, pair1: str, pair2: str) -> bool:
        """
        Returns true if the two pairs share a correlation group.
        """
        p1 = pair1.replace("/", "_")
        p2 = pair2.replace("/", "_")
        g1 = set(self.get_groups_for_pair(p1))
        g2 = set(self.get_groups_for_pair(p2))
        return not g1.isdisjoint(g2)
