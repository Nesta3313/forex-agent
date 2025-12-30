import json
from pathlib import Path
from datetime import datetime
from typing import Optional

class StateManager:
    def __init__(self, filepath: str = "logs/state.json"):
        self.filepath = Path(filepath)
        self.state = self._load_state()

    def _load_state(self) -> dict:
        if self.filepath.exists():
            try:
                with open(self.filepath, 'r') as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}

    def _save_state(self):
        try:
            with open(self.filepath, 'w') as f:
                json.dump(self.state, f, indent=2)
        except Exception as e:
            print(f"Failed to save state: {e}")

    def get_last_processed_candle(self) -> Optional[datetime]:
        ts = self.state.get("last_processed_candle")
        if ts:
            return datetime.fromisoformat(ts)
        return None

    def set_last_processed_candle(self, timestamp: datetime):
        self.state["last_processed_candle"] = timestamp.isoformat()
        self._save_state()

state_manager = StateManager()
