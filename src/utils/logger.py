"""Structured logging configuration for FrontierAtlas."""
import logging
import json
import sys
from datetime import datetime, timezone
from typing import Optional, Any, Dict

class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "component": getattr(record, "component", record.name),
            "message": record.getMessage(),
        }
        
        # Add optional structured context fields if present
        for field in [
            "source", "url", "status_code", "retry_count", "latency_ms",
            "record_id", "error", "llm_provider", "fallback_count",
            "records_discovered", "records_processed", "records_rejected",
            "duplicates", "fresh_records", "stale_records", "entity_matches"
        ]:
            val = getattr(record, field, None)
            if val is not None:
                log_data[field] = val

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)

def setup_logger(name: str = "FrontierAtlas", level: str = "INFO") -> logging.Logger:
    """Setup and return structured logger."""
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        logger.propagate = False
        
    return logger

logger = setup_logger()
