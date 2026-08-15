"""Unit tests for DateNormalizer and FreshnessEngine."""
import pytest
from datetime import datetime, timezone, timedelta
from src.extraction.date_normalizer import DateNormalizer
from src.extraction.freshness_engine import FreshnessEngine

def test_date_normalizer_iso():
    dt = DateNormalizer.normalize("2026-08-15T10:00:00Z")
    assert dt is not None
    assert dt.tzinfo == timezone.utc
    assert dt.year == 2026
    assert dt.month == 8
    assert dt.day == 15

def test_date_normalizer_rfc():
    dt = DateNormalizer.normalize("Sat, 15 Aug 2026 10:00:00 GMT")
    assert dt is not None
    assert dt.year == 2026
    assert dt.hour == 10

def test_date_normalizer_relative():
    ref = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    
    dt_2h = DateNormalizer.parse_relative_date("2 hours ago", reference_time=ref)
    assert dt_2h == datetime(2026, 8, 15, 10, 0, 0, tzinfo=timezone.utc)

    dt_30m = DateNormalizer.parse_relative_date("30 mins ago", reference_time=ref)
    assert dt_30m == datetime(2026, 8, 15, 11, 30, 0, tzinfo=timezone.utc)

    dt_yest = DateNormalizer.parse_relative_date("yesterday", reference_time=ref)
    assert dt_yest == datetime(2026, 8, 14, 0, 0, 0, tzinfo=timezone.utc)

def test_date_normalizer_html_json_ld():
    html = """
    <html>
      <head>
        <script type="application/ld+json">
          {"@context": "https://schema.org", "datePublished": "2026-08-15T08:15:00Z"}
        </script>
      </head>
    </html>
    """
    dt = DateNormalizer.extract_from_html(html)
    assert dt is not None
    assert dt.hour == 8
    assert dt.minute == 15

def test_freshness_engine_verified_fresh():
    ref = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    engine = FreshnessEngine(max_age_hours=24.0)

    # 2 hours ago -> Fresh
    is_fresh, dt, reason = engine.verify_freshness("2026-08-15T10:00:00Z", reference_time=ref)
    assert is_fresh is True
    assert "VERIFIED_FRESH" in reason

def test_freshness_engine_rejected_stale():
    ref = datetime(2026, 8, 15, 12, 0, 0, tzinfo=timezone.utc)
    engine = FreshnessEngine(max_age_hours=24.0)

    # 30 hours ago -> Stale
    is_fresh, dt, reason = engine.verify_freshness("2026-08-14T06:00:00Z", reference_time=ref)
    assert is_fresh is False
    assert "REJECTED_STALE" in reason

def test_freshness_engine_missing_date_rejected():
    engine = FreshnessEngine(max_age_hours=24.0)
    is_fresh, dt, reason = engine.verify_freshness(None)
    assert is_fresh is False
    assert "REJECTED" in reason
