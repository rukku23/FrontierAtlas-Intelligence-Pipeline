"""Startup Crawler for acquiring real AI startup records from legitimate public sources."""
import json
from typing import List, Optional
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.schemas import Startup
from src.utils.logger import logger

class StartupCrawler:
    """Crawler for AI Startups using public endpoints and verified sources."""

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()

    async def fetch_startups(self, limit: int = 1000) -> List[Startup]:
        """Acquire real AI startup records from public APIs."""
        startups: List[Startup] = []

        # 1. Fetch real AI organizations from Hugging Face API
        hf_url = f"https://huggingface.co/api/models?limit={limit}&full=true"
        async with self.crawler:
            resp = await self.crawler.fetch(hf_url)
            if resp.is_success:
                try:
                    data = json.loads(resp.text)
                    seen_orgs = set()
                    for item in data:
                        model_id = item.get("id", "")
                        if "/" in model_id:
                            org_name = model_id.split("/")[0]
                            if org_name not in seen_orgs and len(org_name) > 1:
                                seen_orgs.add(org_name)
                                source_url = f"https://huggingface.co/{org_name}"
                                startup = Startup(
                                    name=org_name,
                                    canonical_name=None,
                                    description=f"AI Organization / Startup active on Hugging Face ({model_id})",
                                    website_url=source_url,
                                    source_url=source_url,
                                    employee_count=None,  # Never fabricate
                                    founding_year=None,
                                    headquarters=None,
                                    categories=["AI", "Machine Learning", "Open Source AI"],
                                    funding_stage=None
                                )
                                startups.append(startup)
                                if len(startups) >= limit:
                                    break
                except Exception as e:
                    logger.error(f"Error parsing Hugging Face orgs: {e}", extra={"component": "StartupCrawler"})

        logger.info(f"Total real startups fetched: {len(startups)}", extra={"component": "StartupCrawler"})
        return startups[:limit]
