import json
import uuid
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
from src.core.config import config
from src.core.logger import logging
from src.backtest.data_loader import OANDADataLoader
from src.backtest.run_backtest import BacktestRunner

logger = logging.getLogger(__name__)

class BatchRunner:
    def __init__(self, batch_id: Optional[str] = None):
        self.batch_id = batch_id or f"batch_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{str(uuid.uuid4())[:8]}"
        self.batch_dir = Path(config.get("backtest", {}).get("output_dir", "logs/backtests")) / self.batch_id
        self.batch_dir.mkdir(parents=True, exist_ok=True)
        self.loader = OANDADataLoader()

    def run_batch(self, ranges: List[Dict[str, str]], overrides: Dict[str, Any]) -> Dict[str, Any]:
        """
        ranges: List of {"start": "...", "end": "..."}
        overrides: Dictionary of backtest config overrides
        """
        logger.info(f"Starting Batch Backtest: {self.batch_id} with {len(ranges)} ranges")
        batch_summary = {
            "batch_id": self.batch_id,
            "timestamp": datetime.utcnow().isoformat(),
            "config": overrides,
            "runs": []
        }

        instrument = overrides.get("instrument", config.get("backtest", {}).get("instrument", "EUR_USD"))
        granularity = overrides.get("granularity", config.get("backtest", {}).get("granularity", "H4"))

        for i, r in enumerate(ranges):
            start_str = r['start']
            end_str = r['end']
            run_id = f"run_{start_str[:10]}_{end_str[:10]}"
            
            logger.info(f"Batch {self.batch_id}: Progress {i+1}/{len(ranges)} - Running {run_id}")
            
            # 1. Fetch Data
            candles = self.loader.fetch_history(instrument, granularity, start_str, end_str)
            if not candles:
                logger.error(f"No data for range {start_str} to {end_str}. Skipping.")
                continue

            # 2. Run Backtest
            runner = BacktestRunner(run_id=run_id, output_parent_dir=self.batch_dir, overrides=overrides)
            runner.run(candles)
            runner._finalize(candles)
            
            # 3. Collect brief metrics for summary
            metrics_path = runner.output_dir / "metrics.json"
            run_metrics = {}
            if metrics_path.exists():
                with open(metrics_path, 'r') as f:
                    run_metrics = json.load(f)

            batch_summary["runs"].append({
                "run_id": run_id,
                "start": start_str,
                "end": end_str,
                "metrics": run_metrics
            })

        # Save summary
        summary_path = self.batch_dir / "batch_summary.json"
        with open(summary_path, 'w') as f:
            json.dump(batch_summary, f, indent=2)

        logger.info(f"Batch {self.batch_id} completed. Summary saved to {summary_path}")
        return batch_summary
