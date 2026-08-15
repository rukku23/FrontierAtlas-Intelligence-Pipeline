"""Deterministic Deduplication Engine for processing idempotency."""
import hashlib
from typing import Set, List, TypeVar, Any
from src.schemas import Startup, Product, ResearchPaper, Job, News, BaseEntity
from src.utils.logger import logger

T = TypeVar("T", bound=BaseEntity)

class Deduplicator:
    """Computes deterministic deduplication keys and filters duplicate records."""

    def __init__(self):
        self.seen_keys: Set[str] = set()

    @staticmethod
    def compute_key(record: BaseEntity) -> str:
        """Compute unique SHA-256 hash key for any Pydantic entity record."""
        if isinstance(record, Startup):
            raw = f"startup:{record.canonical_name or record.name.lower()}:{record.website_url or record.source_url}"
        elif isinstance(record, Product):
            raw = f"product:{record.canonical_name or record.name.lower()}:{record.product_url or record.source_url}"
        elif isinstance(record, ResearchPaper):
            raw = f"paper:{record.paper_url.strip().lower()}"
        elif isinstance(record, Job):
            raw = f"job:{record.company_name.lower()}:{record.role_title.lower()}:{record.job_url.strip()}"
        elif isinstance(record, News):
            raw = f"news:{record.article_url.strip().lower()}"
        else:
            raw = f"generic:{record.source_url.strip().lower()}"

        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def filter_duplicates(self, records: List[T]) -> List[T]:
        """Filter out duplicate records in-memory while preserving order."""
        unique_records: List[T] = []
        dupes_count = 0

        for r in records:
            key = self.compute_key(r)
            if key not in self.seen_keys:
                self.seen_keys.add(key)
                unique_records.append(r)
            else:
                dupes_count += 1

        if dupes_count > 0:
            logger.info(f"Deduplicated {dupes_count} duplicate records", extra={"component": "Deduplicator", "duplicates": dupes_count})

        return unique_records
