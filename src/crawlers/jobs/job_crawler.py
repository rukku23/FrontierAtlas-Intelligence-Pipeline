"""Job Crawler for acquiring fresh AI job postings from 5 verified API/RSS sources."""
import json
from typing import List, Optional, Dict, Any
from bs4 import BeautifulSoup
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.extraction.freshness_engine import FreshnessEngine
from src.schemas import Job, RoleFamily
from src.utils.logger import logger

DEFAULT_JOB_SOURCES = [
    {"name": "RemoteOK", "type": "json", "url": "https://remoteok.com/api"},
    {"name": "WeWorkRemotely", "type": "rss", "url": "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss"},
    {"name": "Remotive", "type": "json", "url": "https://remotive.com/api/remote-jobs?category=software-dev"},
    {"name": "Python.org Jobs", "type": "rss", "url": "https://www.python.org/jobs/feed/rss/"},
    {"name": "Jobspresso", "type": "rss", "url": "https://jobspresso.co/category/developer-jobs/feed/"},
]

class JobCrawler:
    """Crawls 5 verified AI job boards and filters for 24h freshness."""

    def __init__(
        self,
        crawler: Optional[BaseAsyncCrawler] = None,
        freshness_engine: Optional[FreshnessEngine] = None,
        sources: Optional[List[Dict[str, str]]] = None
    ):
        self.crawler = crawler or BaseAsyncCrawler()
        self.freshness_engine = freshness_engine or FreshnessEngine(max_age_hours=24.0)
        self.sources = sources or DEFAULT_JOB_SOURCES

    def _infer_role_family(self, title: str, description: str = "") -> RoleFamily:
        """Infer RoleFamily enum from job title and description."""
        text = f"{title} {description}".lower()
        if any(term in text for term in ["machine learning", "ml engineer", "ai engineer", "data scientist", "llm"]):
            return RoleFamily.DATA_AI
        elif any(term in text for term in ["research scientist", "ai researcher", "researcher"]):
            return RoleFamily.RESEARCH
        elif any(term in text for term in ["software engineer", "developer", "backend", "frontend", "fullstack", "devops"]):
            return RoleFamily.ENGINEERING
        elif any(term in text for term in ["product manager", "pm"]):
            return RoleFamily.PRODUCT
        elif any(term in text for term in ["sales", "marketing", "growth"]):
            return RoleFamily.SALES_MARKETING
        return RoleFamily.OTHER

    def parse_json_jobs(self, json_text: str, source_name: str, source_url: str) -> List[Job]:
        """Parse JSON API response from RemoteOK or Remotive into Job Pydantic objects."""
        jobs: List[Job] = []
        try:
            data = json.loads(json_text)
            items = data.get("jobs", data) if isinstance(data, dict) else data
            if not isinstance(items, list):
                return jobs

            for item in items:
                if not isinstance(item, dict):
                    continue
                company = item.get("company")
                position = item.get("position") or item.get("title")
                url = item.get("url") or item.get("apply_url")
                date_raw = item.get("date") or item.get("publication_date")

                if not company or not position or not url:
                    continue

                is_fresh, dt, _ = self.freshness_engine.verify_freshness(str(date_raw) if date_raw else None)
                if is_fresh and dt:
                    job = Job(
                        company_name=company,
                        role_title=position,
                        job_url=url,
                        location=item.get("location") or "Remote",
                        is_remote=True,
                        role_family=self._infer_role_family(position, item.get("description", "")),
                        description=item.get("description"),
                        publication_date=dt.isoformat(),
                        freshness_verified=True,
                        source_name=source_name,
                        source_url=source_url
                    )
                    jobs.append(job)
        except Exception as e:
            logger.error(f"Error parsing JSON jobs for {source_name}: {e}", extra={"component": "JobCrawler"})

        return jobs

    def parse_rss_jobs(self, rss_xml: str, source_name: str, source_url: str) -> List[Job]:
        """Parse RSS feed into Job Pydantic objects."""
        jobs: List[Job] = []
        try:
            try:
                soup = BeautifulSoup(rss_xml, "xml")
            except Exception:
                soup = BeautifulSoup(rss_xml, "html.parser")

            items = soup.find_all(lambda tag: tag.name.lower() in ("item", "entry"))
            for item in items:
                title_elem = item.find(lambda tag: tag.name.lower() == "title")
                link_elem = item.find(lambda tag: tag.name.lower() == "link")
                pub_date_elem = item.find(lambda tag: tag.name.lower() in ("pubdate", "published", "dc:date", "updated"))
                desc_elem = item.find(lambda tag: tag.name.lower() in ("description", "summary", "content"))

                title_text = title_elem.get_text(strip=True) if title_elem else ""
                link = (link_elem.get_text(strip=True) if link_elem else "") or (link_elem.get("href", "") if link_elem else "")
                pub_date = pub_date_elem.get_text(strip=True) if pub_date_elem else ""
                desc = desc_elem.get_text(strip=True) if desc_elem else ""

                if not title_text or not link:
                    continue

                if " at " in title_text:
                    role, company = title_text.split(" at ", 1)
                elif ":" in title_text:
                    company, role = title_text.split(":", 1)
                else:
                    company, role = source_name, title_text

                company = company.strip()
                role = role.strip()

                is_fresh, dt, _ = self.freshness_engine.verify_freshness(pub_date)
                if is_fresh and dt:
                    job = Job(
                        company_name=company,
                        role_title=role,
                        job_url=link,
                        location="Remote",
                        is_remote=True,
                        role_family=self._infer_role_family(role, desc),
                        description=BeautifulSoup(desc, "html.parser").get_text(strip=True) if desc else None,
                        publication_date=dt.isoformat(),
                        freshness_verified=True,
                        source_name=source_name,
                        source_url=source_url
                    )
                    jobs.append(job)
        except Exception as e:
            logger.error(f"Error parsing RSS jobs for {source_name}: {e}", extra={"component": "JobCrawler"})

        return jobs

    async def fetch_fresh_jobs(self) -> List[Job]:
        """Fetch fresh job postings from all 5 sources."""
        all_jobs: List[Job] = []

        async with self.crawler:
            for src in self.sources:
                logger.info(f"Fetching job feed: {src['name']} ({src['url']})", extra={"component": "JobCrawler"})
                resp = await self.crawler.fetch(src["url"])
                if resp.is_success:
                    if src["type"] == "json":
                        items = self.parse_json_jobs(resp.text, src["name"], src["url"])
                    else:
                        items = self.parse_rss_jobs(resp.text, src["name"], src["url"])
                    logger.info(f"Retrieved {len(items)} fresh jobs from {src['name']}", extra={"component": "JobCrawler"})
                    all_jobs.extend(items)
                else:
                    logger.warning(f"Failed to fetch {src['name']}: {resp.status_code}", extra={"component": "JobCrawler"})

        logger.info(f"Total verified fresh jobs: {len(all_jobs)}", extra={"component": "JobCrawler"})
        return all_jobs
