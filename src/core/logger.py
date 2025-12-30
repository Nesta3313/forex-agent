import logging
import json
import logging.config
from pathlib import Path
from datetime import datetime
from src.core.config import config

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, "props"):
            log_obj.update(record.props)
        return json.dumps(log_obj)

def setup_logging():
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_level = config.system.get("log_level", "INFO")

    logging_config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "standard": {
                "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            },
            "json": {
                "()": JsonFormatter
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "standard",
            },
            "file": {
                "class": "logging.FileHandler",
                "filename": log_dir / "agent.log",
                "level": log_level,
                "formatter": "standard",
            },
            "audit_file": {
                "class": "logging.FileHandler",
                "filename": log_dir / "audit.json",
                "level": "INFO",
                "formatter": "json",
            }
        },
        "root": {
            "handlers": ["console", "file"],
            "level": log_level,
        },
        "loggers": {
            "audit": {
                "handlers": ["console", "audit_file"],
                "level": "INFO",
                "propagate": False
            }
        }
    }

    logging.config.dictConfig(logging_config)
    logging.info("Logging initialized.")

from src.core.audit import log_audit_event

def log_audit(event_type: str, data: dict):
    """
    Log a structured event to the audit log (Hash-Chained).
    """
    log_audit_event(event_type, data)

