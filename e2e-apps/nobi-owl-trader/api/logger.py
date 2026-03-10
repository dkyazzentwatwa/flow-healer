import time
import json
import logging
from typing import Optional, Any
from api.models import LogEntry, LogRepository

# Standard Python logger for console output
logger = logging.getLogger("nobibot")
logger.setLevel(logging.INFO)

# Create console handler
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

class NobiLogger:
    """
    Centralized logging for NobiBot that writes to both:
    1. Console (via standard logging)
    2. SQLite database (for frontend observability)
    """
    def __init__(self):
        self.repo = LogRepository()

    def _log(self, level: str, message: str, rule_id: Optional[str] = None, symbol: Optional[str] = None, details: Any = None):
        # 1. Console Log
        if level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        else:
            logger.info(message)

        # 2. Database Log
        timestamp = int(time.time() * 1000)
        details_str = json.dumps(details) if details else None
        
        entry = LogEntry(
            id=None,
            timestamp=timestamp,
            level=level,
            message=message,
            rule_id=rule_id,
            symbol=symbol,
            details=details_str
        )
        try:
            self.repo.create(entry)
        except Exception as e:
            # Fallback if DB logging fails
            logger.error(f"Failed to write log to database: {e}")

    def info(self, message: str, rule_id: Optional[str] = None, symbol: Optional[str] = None, details: Any = None):
        self._log("INFO", message, rule_id, symbol, details)

    def error(self, message: str, rule_id: Optional[str] = None, symbol: Optional[str] = None, details: Any = None):
        self._log("ERROR", message, rule_id, symbol, details)

    def warning(self, message: str, rule_id: Optional[str] = None, symbol: Optional[str] = None, details: Any = None):
        self._log("WARNING", message, rule_id, symbol, details)

    def trade(self, message: str, rule_id: Optional[str] = None, symbol: Optional[str] = None, details: Any = None):
        self._log("TRADE", message, rule_id, symbol, details)

# Singleton instance
nobi_logger = NobiLogger()
