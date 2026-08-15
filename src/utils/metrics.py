"""Metrics tracker for pipeline observability."""
from typing import Dict, Any
from src.utils.logger import logger

class PipelineMetrics:
    """Tracks and reports ingestion metrics across all pipeline stages."""

    def __init__(self):
        self.records_discovered = 0
        self.records_processed = 0
        self.records_rejected = 0
        self.duplicates = 0
        self.fresh_records = 0
        self.stale_records = 0
        self.entity_matches = 0
        self.github_stars_enriched = 0
        self.llm_fallbacks = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "records_discovered": self.records_discovered,
            "records_processed": self.records_processed,
            "records_rejected": self.records_rejected,
            "duplicates": self.duplicates,
            "fresh_records": self.fresh_records,
            "stale_records": self.stale_records,
            "entity_matches": self.entity_matches,
            "github_stars_enriched": self.github_stars_enriched,
            "llm_fallbacks": self.llm_fallbacks,
        }

    def summary(self) -> str:
        d = self.to_dict()
        return (
            "=== PIPELINE RUN METRICS SUMMARY ===\n"
            f"  Discovered Records:    {d['records_discovered']}\n"
            f"  Processed & Saved:     {d['records_processed']}\n"
            f"  Rejected Records:      {d['records_rejected']}\n"
            f"  Duplicates Filtered:   {d['duplicates']}\n"
            f"  Fresh (<=24h) Records: {d['fresh_records']}\n"
            f"  Stale Records:         {d['stale_records']}\n"
            f"  Entity Match Hits:     {d['entity_matches']}\n"
            f"  GitHub Stars Enriched: {d['github_stars_enriched']}\n"
            f"===================================="
        )

    def log_summary(self):
        logger.info(self.summary(), extra={"component": "PipelineMetrics", **self.to_dict()})
