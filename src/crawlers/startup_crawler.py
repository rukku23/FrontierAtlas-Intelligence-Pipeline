"""Startup Crawler using YC-OSS API for verified, real AI startup records.

Source: https://yc-oss.github.io/api/ — open-source mirror of Y Combinator's
official startup directory. Every entity is an explicitly verified startup/company
that went through the YC accelerator program.

Discovery vs Extraction:
  - DIRECT (authoritative from YC API): name, website, one_liner, all_locations,
    team_size, batch, stage, industry, tags, url
  - LLM EXTRACTION (from long_description text): enriched description, categories
"""
import json
from typing import List, Optional, Set, Dict, Any
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.schemas import Startup
from src.utils.logger import logger

# YC-OSS tags that map to AI/ML startups — combine for >1000 unique companies
YC_AI_TAG_ENDPOINTS = [
    "https://yc-oss.github.io/api/tags/artificial-intelligence.json",   # 968
    "https://yc-oss.github.io/api/tags/ai-assistant.json",              # 161
    "https://yc-oss.github.io/api/tags/machine-learning.json",          # ~150
    "https://yc-oss.github.io/api/tags/generative-ai.json",             # ~100
    "https://yc-oss.github.io/api/tags/natural-language-processing.json",# ~60
    "https://yc-oss.github.io/api/tags/computer-vision.json",           # ~50
    "https://yc-oss.github.io/api/tags/ai-powered-drug-discovery.json", # 37
    "https://yc-oss.github.io/api/tags/ai-enhanced-learning.json",      # 46
    "https://yc-oss.github.io/api/tags/aiops.json",                     # 58
]


class StartupCrawler:
    """Crawler for real AI startups from the YC-OSS open-source API.

    Every record is a verified Y Combinator startup — legitimate company
    identity is established by YC's own vetting and directory.
    """

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()

    def _parse_yc_company(self, item: Dict[str, Any], source_tag_url: str) -> Optional[Startup]:
        """Parse a single YC company JSON record into a Startup Pydantic model.

        Direct field mappings (authoritative from YC API — no LLM):
          - name, website, all_locations, team_size, batch, industry, tags, url
        Fields that remain null if not present in source (never fabricated):
          - employee_count, founding_year, headquarters, funding_stage
        """
        name = item.get("name")
        if not name:
            return None

        # Provenance: the canonical YC directory URL for this company
        yc_url = item.get("url", "")
        website = item.get("website", "")

        # Map YC fields directly to Startup schema
        # team_size → employee_count (direct authoritative mapping)
        team_size = item.get("team_size")
        employee_count = team_size if isinstance(team_size, int) and team_size > 0 else None

        # launched_at → founding_year (Unix timestamp → year)
        launched_at = item.get("launched_at")
        founding_year = None
        if launched_at and isinstance(launched_at, (int, float)):
            from datetime import datetime, timezone
            try:
                founding_year = datetime.fromtimestamp(launched_at, tz=timezone.utc).year
            except (ValueError, OSError):
                founding_year = None

        # all_locations → headquarters (direct mapping)
        headquarters = item.get("all_locations") or None

        # stage → funding_stage
        stage = item.get("stage") or None

        # Combine tags + industry into categories
        tags = item.get("tags") or []
        industries = item.get("industries") or []
        categories = list(set(tags + industries))[:10]  # Cap at 10

        # one_liner + long_description → description
        # These are authoritative from YC's own directory, not LLM-generated
        one_liner = item.get("one_liner", "")
        long_desc = item.get("long_description", "")
        description = one_liner or (long_desc[:500] if long_desc else None)

        try:
            return Startup(
                name=name,
                canonical_name=None,  # Set by EntityResolver in main pipeline
                description=description,
                website_url=website or None,
                source_url=yc_url or source_tag_url,  # Provenance
                employee_count=employee_count,
                founding_year=founding_year,
                headquarters=headquarters,
                categories=categories if categories else ["AI"],
                funding_stage=stage,
            )
        except Exception as e:
            logger.warning(f"Skipping invalid startup '{name}': {e}",
                           extra={"component": "StartupCrawler"})
            return None

    async def fetch_startups(self, limit: int = 1000) -> List[Startup]:
        """Fetch real AI startups from YC-OSS API tag endpoints.

        Iterates over AI-related YC tag endpoints, deduplicating by company name
        to produce a list of verified, unique AI startups.
        """
        startups: List[Startup] = []
        seen_names: Set[str] = set()

        async with self.crawler:
            for tag_url in YC_AI_TAG_ENDPOINTS:
                if len(startups) >= limit:
                    break

                logger.info(f"Fetching YC tag endpoint: {tag_url}",
                            extra={"component": "StartupCrawler", "url": tag_url})

                resp = await self.crawler.fetch(tag_url)
                if not resp.is_success:
                    logger.warning(f"YC API returned {resp.status_code} for {tag_url}",
                                   extra={"component": "StartupCrawler", "status_code": resp.status_code})
                    continue

                try:
                    data = json.loads(resp.text)
                    if not isinstance(data, list):
                        logger.warning(f"Unexpected YC API response type for {tag_url}",
                                       extra={"component": "StartupCrawler"})
                        continue

                    new_count = 0
                    for item in data:
                        if len(startups) >= limit:
                            break

                        name = item.get("name", "").strip()
                        name_lower = name.lower()
                        if not name or name_lower in seen_names:
                            continue

                        startup = self._parse_yc_company(item, tag_url)
                        if startup:
                            seen_names.add(name_lower)
                            startups.append(startup)
                            new_count += 1

                    logger.info(f"Parsed {new_count} new startups from {tag_url} (total: {len(startups)})",
                                extra={"component": "StartupCrawler"})

                except Exception as e:
                    logger.error(f"Error parsing YC response from {tag_url}: {e}",
                                 extra={"component": "StartupCrawler"})

        logger.info(f"Total verified AI startups fetched: {len(startups)} "
                     f"(from {len(seen_names)} unique companies across YC-OSS API)",
                     extra={"component": "StartupCrawler"})
        return startups[:limit]
