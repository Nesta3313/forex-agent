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

    def _get_last_hash(self, f_handle: Optional[Any] = None) -> str:
        # If no handle, open and read
        if f_handle is None:
            if not self.filepath.exists():
                return "0" * 64
            with open(self.filepath, 'rb') as f:
                return self._read_tail_hash(f)
        else:
            return self._read_tail_hash(f_handle)

    def _read_tail_hash(self, f: Any) -> str:
        try:
            f.seek(0, os.SEEK_END)
            if f.tell() == 0:
                return "0" * 64
            
            # Read last 4KB
            f.seek(max(0, f.tell() - 4096), os.SEEK_SET)
            lines = f.readlines()
            if not lines:
                return "0" * 64
            
            # Find the actual last JSON line (handle possible empty lines at EOF)
            for line in reversed(lines):
                line = line.strip()
                if not line: continue
                try:
                    last_event = json.loads(line.decode('utf-8'))
                    return last_event.get("hash", "0" * 64)
                except: continue
            return "0" * 64
        except Exception:
            return "0" * 64

    def log_event(self, event_type: str, payload: Dict[str, Any]):
        """
        Logs a tamper-evident event with atomic file locking and dynamic chaining.
        """
        event_id = str(uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # We must lock the file BEFORE calculating the hash to ensure we chain correctly
        # to whatever is currently at the tail.
        with portalocker.Lock(self.filepath, mode='a+b', timeout=5) as f:
            # 1. Get the actual current tail hash while holding the lock
            current_tail_hash = self._get_last_hash(f)
            
            # 2. Prepare event data with the fresh tail hash
            event_data = {
                "event_id": event_id,
                "timestamp": timestamp,
                "event_type": event_type,
                "payload": payload,
                "prev_hash": current_tail_hash
            }
            
            # 3. Calculate hash
            canonical_str = json.dumps(event_data, sort_keys=True, separators=(',', ':'))
            current_hash = hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()
            event_data["hash"] = current_hash
            
            # 4. Append
            line = json.dumps(event_data) + "\n"
            # Since mode is 'a+b', seek to end just in case (though append mode usually handles it)
            f.seek(0, os.SEEK_END)
            f.write(line.encode('utf-8'))
            f.flush()
            os.fsync(f.fileno())
            
            # Update cache for local use (though it will be re-read next time anyway)
            self.last_hash = current_hash

# Default instance for live mode
audit_logger = AuditLogger("logs/audit_live.jsonl")

def log_audit_event(event_type: str, payload: Dict):
    audit_logger.log_event(event_type, payload)
