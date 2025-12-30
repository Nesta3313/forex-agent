import json
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, Any

class MetricsEngine:
    def __init__(self, trades_df: pd.DataFrame, equity_df: pd.DataFrame):
        self.trades = trades_df
        self.equity = equity_df

    def calculate_all(self) -> Dict[str, Any]:
        if self.trades.empty:
            return {
                "total_trades": 0,
                "win_rate": 0.0,
                "net_profit": 0.0,
                "max_drawdown": float(self._calculate_max_drawdown()),
                "profit_factor": 0.0,
                "equity_final": float(self.equity['equity'].iloc[-1]) if not self.equity.empty else 0.0
            }

        wins = self.trades[self.trades['pnl'] > 0]
        losses = self.trades[self.trades['pnl'] <= 0]
        
        total_pnl = self.trades['pnl'].sum()
        win_rate = len(wins) / len(self.trades) if len(self.trades) > 0 else 0
        
        gross_profit = wins['pnl'].sum()
        gross_loss = abs(losses['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss != 0 else float('inf')

        metrics = {
            "total_trades": int(len(self.trades)),
            "win_rate": float(round(win_rate, 4)),
            "net_profit": float(round(total_pnl, 2)),
            "avg_trade": float(round(self.trades['pnl'].mean(), 2)),
            "avg_win": float(round(wins['pnl'].mean(), 2)) if not wins.empty else 0.0,
            "avg_loss": float(round(losses['pnl'].mean(), 2)) if not losses.empty else 0.0,
            "profit_factor": float(round(profit_factor, 2)),
            "max_drawdown": float(round(self._calculate_max_drawdown(), 4)),
            "max_drawdown_pct": float(round(self._calculate_max_drawdown_pct(), 4)),
            "equity_final": float(round(self.equity['equity'].iloc[-1], 2))
        }
        
        return metrics

    def _calculate_max_drawdown(self) -> float:
        equity = self.equity['equity']
        rolling_max = equity.cummax()
        drawdown = rolling_max - equity
        return drawdown.max()

    def _calculate_max_drawdown_pct(self) -> float:
        equity = self.equity['equity']
        rolling_max = equity.cummax()
        drawdown_pct = (rolling_max - equity) / rolling_max
        return drawdown_pct.max()

class MetricsEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super(MetricsEncoder, self).default(obj)

def save_metrics(metrics: Dict[str, Any], output_path: Path):
    with open(output_path, 'w') as f:
        json.dump(metrics, f, indent=2, cls=MetricsEncoder)
