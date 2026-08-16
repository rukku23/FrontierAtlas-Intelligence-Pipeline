"""Startup Crawler for acquiring real AI startup/organization records from legitimate public sources."""
import json
from typing import List, Optional, Set
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.schemas import Startup
from src.utils.logger import logger


class StartupCrawler:
    """Crawler for AI Startups using multiple public endpoints with pagination."""

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()

    async def fetch_startups(self, limit: int = 1000) -> List[Startup]:
        """Acquire real AI startup records from multiple public Hugging Face APIs with pagination."""
        startups: List[Startup] = []
        seen_orgs: Set[str] = set()

        async with self.crawler:
            # ---------------------------------------------------------------
            # SOURCE 1: Hugging Face Organizations from Models API (paginated)
            # ---------------------------------------------------------------
            # Fetch models in batches and extract unique organization prefixes
            batch_size = 1000
            offset = 0
            max_pages = 10  # Safety cap: 10 pages × 1000 models = 10,000 models scanned

            for page in range(max_pages):
                if len(startups) >= limit:
                    break

                hf_url = (
                    f"https://huggingface.co/api/models"
                    f"?limit={batch_size}&offset={offset}&full=false&sort=downloads&direction=-1"
                )
                logger.info(
                    f"Fetching HF models page {page + 1} (offset={offset})",
                    extra={"component": "StartupCrawler", "url": hf_url}
                )
                resp = await self.crawler.fetch(hf_url)
                if not resp.is_success:
                    logger.warning(f"HF models API returned {resp.status_code} at offset={offset}", extra={"component": "StartupCrawler"})
                    break

                try:
                    data = json.loads(resp.text)
                    if not data:
                        logger.info("No more models from HF API", extra={"component": "StartupCrawler"})
                        break

                    new_orgs_this_page = 0
                    for item in data:
                        model_id = item.get("id", "")
                        if "/" in model_id:
                            org_name = model_id.split("/")[0]
                            if org_name not in seen_orgs and len(org_name) > 1:
                                seen_orgs.add(org_name)
                                new_orgs_this_page += 1
                                source_url = f"https://huggingface.co/{org_name}"
                                startup = Startup(
                                    name=org_name,
                                    canonical_name=None,
                                    description=f"AI Organization active on Hugging Face",
                                    website_url=source_url,
                                    source_url=source_url,
                                    employee_count=None,  # Never fabricate
                                    founding_year=None,
                                    headquarters=None,
                                    categories=["AI", "Machine Learning"],
                                    funding_stage=None
                                )
                                startups.append(startup)
                                if len(startups) >= limit:
                                    break

                    logger.info(
                        f"Page {page + 1}: found {new_orgs_this_page} new orgs (total: {len(startups)})",
                        extra={"component": "StartupCrawler"}
                    )

                    if len(data) < batch_size:
                        break  # Last page

                    offset += batch_size

                except Exception as e:
                    logger.error(f"Error parsing HF models page {page + 1}: {e}", extra={"component": "StartupCrawler"})
                    break

            # ---------------------------------------------------------------
            # SOURCE 2: Hugging Face Organizations from Datasets API (paginated)
            # ---------------------------------------------------------------
            # Datasets have different creators than models — broadens org coverage
            if len(startups) < limit:
                ds_offset = 0
                ds_max_pages = 5

                for page in range(ds_max_pages):
                    if len(startups) >= limit:
                        break

                    ds_url = (
                        f"https://huggingface.co/api/datasets"
                        f"?limit={batch_size}&offset={ds_offset}&full=false&sort=downloads&direction=-1"
                    )
                    logger.info(
                        f"Fetching HF datasets page {page + 1} (offset={ds_offset})",
                        extra={"component": "StartupCrawler", "url": ds_url}
                    )
                    resp = await self.crawler.fetch(ds_url)
                    if not resp.is_success:
                        break

                    try:
                        data = json.loads(resp.text)
                        if not data:
                            break

                        for item in data:
                            ds_id = item.get("id", "")
                            if "/" in ds_id:
                                org_name = ds_id.split("/")[0]
                                if org_name not in seen_orgs and len(org_name) > 1:
                                    seen_orgs.add(org_name)
                                    source_url = f"https://huggingface.co/{org_name}"
                                    startup = Startup(
                                        name=org_name,
                                        canonical_name=None,
                                        description=f"AI Organization active on Hugging Face",
                                        website_url=source_url,
                                        source_url=source_url,
                                        employee_count=None,
                                        founding_year=None,
                                        headquarters=None,
                                        categories=["AI", "Machine Learning", "Datasets"],
                                        funding_stage=None
                                    )
                                    startups.append(startup)
                                    if len(startups) >= limit:
                                        break

                        if len(data) < batch_size:
                            break
                        ds_offset += batch_size

                    except Exception as e:
                        logger.error(f"Error parsing HF datasets page {page + 1}: {e}", extra={"component": "StartupCrawler"})
                        break

            # ---------------------------------------------------------------
            # SOURCE 3: Hugging Face Organizations from Spaces API (paginated)
            # ---------------------------------------------------------------
            if len(startups) < limit:
                sp_offset = 0
                sp_max_pages = 5

                for page in range(sp_max_pages):
                    if len(startups) >= limit:
                        break

                    sp_url = (
                        f"https://huggingface.co/api/spaces"
                        f"?limit={batch_size}&offset={sp_offset}&full=false&sort=likes&direction=-1"
                    )
                    logger.info(
                        f"Fetching HF spaces page {page + 1} for orgs (offset={sp_offset})",
                        extra={"component": "StartupCrawler", "url": sp_url}
                    )
                    resp = await self.crawler.fetch(sp_url)
                    if not resp.is_success:
                        break

                    try:
                        data = json.loads(resp.text)
                        if not data:
                            break

                        for item in data:
                            space_id = item.get("id", "")
                            if "/" in space_id:
                                org_name = space_id.split("/")[0]
                                if org_name not in seen_orgs and len(org_name) > 1:
                                    seen_orgs.add(org_name)
                                    source_url = f"https://huggingface.co/{org_name}"
                                    startup = Startup(
                                        name=org_name,
                                        canonical_name=None,
                                        description=f"AI Organization active on Hugging Face",
                                        website_url=source_url,
                                        source_url=source_url,
                                        employee_count=None,
                                        founding_year=None,
                                        headquarters=None,
                                        categories=["AI", "Machine Learning", "Applications"],
                                        funding_stage=None
                                    )
                                    startups.append(startup)
                                    if len(startups) >= limit:
                                        break

                        if len(data) < batch_size:
                            break
                        sp_offset += batch_size

                    except Exception as e:
                        logger.error(f"Error parsing HF spaces page {page + 1}: {e}", extra={"component": "StartupCrawler"})
                        break

        logger.info(
            f"Total real startups fetched: {len(startups)} (from {len(seen_orgs)} unique orgs across Models, Datasets, Spaces APIs)",
            extra={"component": "StartupCrawler"}
        )
        return startups[:limit]
