"""Date Normalization Engine supporting ISO, RFC, relative dates, JSON-LD, OpenGraph, and HTML tags."""
import re
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from bs4 import BeautifulSoup
from src.utils.logger import logger

class DateNormalizer:
    """Parses and normalizes dates into timezone-aware UTC datetimes."""

    @staticmethod
    def parse_relative_date(text: str, reference_time: Optional[datetime] = None) -> Optional[datetime]:
        """Parse relative date strings like '2 hours ago', '30 minutes ago', 'Yesterday', 'Today'."""
        if not text:
            return None

        now = reference_time or datetime.now(timezone.utc)
        clean_text = text.strip().lower()

        if clean_text in ("just now", "moments ago", "right now"):
            return now

        if clean_text == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)

        if clean_text == "yesterday":
            return (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)

        # Match "X minutes ago", "X mins ago", "X hours ago", "X days ago"
        match = re.search(r"(\d+)\s*(sec|second|min|minute|hr|hour|day|d)s?\s*ago", clean_text)
        if match:
            val = int(match.group(1))
            unit = match.group(2)
            if unit.startswith("sec"):
                return now - timedelta(seconds=val)
            elif unit.startswith("min"):
                return now - timedelta(minutes=val)
            elif unit.startswith("hr") or unit.startswith("hour"):
                return now - timedelta(hours=val)
            elif unit.startswith("day") or unit == "d":
                return now - timedelta(days=val)

        return None

    @staticmethod
    def parse_iso_or_rfc(text: str) -> Optional[datetime]:
        """Parse ISO-8601 or RFC-2822 datetime string to UTC datetime."""
        if not text:
            return None

        clean_text = text.strip()

        # Try standard ISO-8601
        for fmt in (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
        ):
            try:
                dt = datetime.strptime(clean_text, fmt)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except ValueError:
                continue

        # Try RFC-2822 (common in RSS feeds, e.g., 'Sat, 15 Aug 2026 10:30:00 GMT')
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(clean_text)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        except Exception:
            pass

        return None

    @classmethod
    def extract_from_html(cls, html_content: str) -> Optional[datetime]:
        """Extract publication date from JSON-LD, OpenGraph, or HTML <time> tags."""
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, "html.parser")

        # 1. Check JSON-LD
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "{}")
                if isinstance(data, dict):
                    date_str = data.get("datePublished") or data.get("dateCreated")
                    if date_str:
                        parsed = cls.parse_iso_or_rfc(str(date_str))
                        if parsed:
                            return parsed
            except Exception:
                continue

        # 2. Check OpenGraph / Meta tags
        for meta_attr, meta_name in [
            ("property", "article:published_time"),
            ("name", "pubdate"),
            ("name", "publish-date"),
            ("name", "date"),
        ]:
            meta = soup.find("meta", attrs={meta_attr: meta_name})
            if meta and meta.get("content"):
                parsed = cls.parse_iso_or_rfc(str(meta["content"]))
                if parsed:
                    return parsed

        # 3. Check HTML <time> tag
        time_tag = soup.find("time")
        if time_tag:
            dt_str = time_tag.get("datetime") or time_tag.get_text(strip=True)
            if dt_str:
                parsed = cls.parse_iso_or_rfc(str(dt_str)) or cls.parse_relative_date(str(dt_str))
                if parsed:
                    return parsed

        return None

    @classmethod
    def normalize(cls, raw_date: str, html_context: Optional[str] = None, reference_time: Optional[datetime] = None) -> Optional[datetime]:
        """Normalize any raw date string or HTML context into a UTC datetime."""
        if not raw_date and not html_context:
            return None

        if raw_date:
            dt = cls.parse_iso_or_rfc(raw_date) or cls.parse_relative_date(raw_date, reference_time)
            if dt:
                return dt

        if html_context:
            dt = cls.extract_from_html(html_context)
            if dt:
                return dt

        return None
