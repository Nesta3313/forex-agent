import json
import hashlib
import os
import portalocker
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import uuid4

class AuditLogger:
    _instances: Dict[str, 'AuditLogger'] = {}

    def __new__(cls, filepath: str = "logs/audit_live.jsonl"):
        path = str(Path(filepath).absolute())
        if path not in cls._instances:
            instance = super(AuditLogger, cls).__new__(cls)
            cls._instances[path] = instance
            instance._initialized = False
        return cls._instances[path]

    def __init__(self, filepath: str = "logs/audit_live.jsonl"):
        if getattr(self, "_initialized", False):
            return
            
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        
        # Initial hash check
        self.last_hash = self._get_last_hash()
        self._initialized = True
        
        # Log opening event
        mode = "LIVE" if "live" in str(self.filepath).lower() else "BACKTEST"
        self.log_event("AUDIT_FILE_OPENED", {
            "mode": mode,
            "path": str(self.filepath),
            "pid": os.getpid()
        })

    def _get_last_hash(self) -> str:
        if not self.filepath.exists():
            return "0" * 64
        
        try:
            with open(self.filepath, 'rb') as f:
                # Seek to end and find last line
                f.seek(0, os.SEEK_END)
                if f.tell() == 0:
                    return "0" * 64
                
                # Simple last line retrieval
                f.seek(max(0, f.tell() - 4096), os.SEEK_SET)
                lines = f.readlines()
                if not lines:
                    return "0" * 64
                
                last_line = json.loads(lines[-1].decode('utf-8'))
                return last_line.get("hash", "0" * 64)
        except Exception:
            return "0" * 64

    def log_event(self, event_type: str, payload: Dict[str, Any]):
        """
        Logs a tamper-evident event with atomic file locking.
        """
        event_id = str(uuid4())
        # Use explicit UTC
        timestamp = datetime.now(timezone.utc).isoformat()
        
        event_data = {
            "event_id": event_id,
            "timestamp": timestamp,
            "event_type": event_type,
            "payload": payload,
            "prev_hash": self.last_hash
        }
        
        canonical_str = json.dumps(event_data, sort_keys=True, separators=(',', ':'))
        current_hash = hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()
        event_data["hash"] = current_hash
        
        # Atomic Write with Locking
        line = json.dumps(event_data) + "\n"
        with portalocker.Lock(self.filepath, mode='a', timeout=5) as f:
            f.write(line)
            f.flush()
            os.fsync(f.fileno())
            
        self.last_hash = current_hash

# Default instance for live mode
audit_logger = AuditLogger("logs/audit_live.jsonl")

def log_audit_event(event_type: str, payload: Dict):
    audit_logger.log_event(event_type, payload)
