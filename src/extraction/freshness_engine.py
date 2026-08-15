"""Freshness Verification Engine for News and Job records."""
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from src.extraction.date_normalizer import DateNormalizer
from src.utils.logger import logger

class FreshnessEngine:
    """Verifies that records were published within a strict freshness threshold (e.g. 24h)."""

    def __init__(self, max_age_hours: float = 24.0):
        self.max_age_hours = max_age_hours

    def verify_freshness(
        self,
        raw_date: Optional[str],
        html_context: Optional[str] = None,
        reference_time: Optional[datetime] = None
    ) -> Tuple[bool, Optional[datetime], str]:
        """
        Verify if a date is within max_age_hours.
        Returns: (is_fresh: bool, normalized_utc_datetime: Optional[datetime], reason: str)
        """
        now = reference_time or datetime.now(timezone.utc)

        if not raw_date and not html_context:
            logger.warning("Freshness check failed: No date or HTML context provided", extra={"component": "FreshnessEngine"})
            return False, None, "REJECTED: Missing publication date"

        dt = DateNormalizer.normalize(raw_date or "", html_context=html_context, reference_time=now)
        if dt is None:
            logger.warning(f"Freshness check failed: Unparseable date '{raw_date}'", extra={"component": "FreshnessEngine"})
            return False, None, "REJECTED: Unparseable date format"

        # Calculate age in hours
        age_seconds = (now - dt).total_seconds()
        age_hours = age_seconds / 3600.0

        if age_seconds < -300:
            # Future publication date (> 5 mins in future) -> suspicious/invalid
            logger.warning(f"Freshness check failed: Future publication date '{dt.isoformat()}'", extra={"component": "FreshnessEngine"})
            return False, dt, "REJECTED: Future publication timestamp"

        if age_hours <= self.max_age_hours:
            logger.info(f"Freshness verified: Published {age_hours:.2f}h ago", extra={"component": "FreshnessEngine"})
            return True, dt, f"VERIFIED_FRESH: {age_hours:.2f}h old"
        else:
            logger.info(f"Stale record rejected: Published {age_hours:.2f}h ago (max {self.max_age_hours}h)", extra={"component": "FreshnessEngine"})
            return False, dt, f"REJECTED_STALE: {age_hours:.2f}h old"
