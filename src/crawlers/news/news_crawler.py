"""News Crawler for acquiring fresh AI news articles from 5 verified RSS/API sources."""
import xml.etree.ElementTree as ET
from typing import List, Optional, Dict
from bs4 import BeautifulSoup
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.extraction.freshness_engine import FreshnessEngine
from src.schemas import News
from src.utils.logger import logger

DEFAULT_NEWS_SOURCES = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "VentureBeat AI", "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "MIT Tech Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "AI News", "url": "https://www.artificialintelligence-news.com/feed/"},
    {"name": "Wired AI", "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
]

class NewsCrawler:
    """Crawls 5 verified AI news RSS feeds and filters for 24h freshness."""

    def __init__(
        self,
        crawler: Optional[BaseAsyncCrawler] = None,
        freshness_engine: Optional[FreshnessEngine] = None,
        sources: Optional[List[Dict[str, str]]] = None
    ):
        self.crawler = crawler or BaseAsyncCrawler()
        self.freshness_engine = freshness_engine or FreshnessEngine(max_age_hours=24.0)
        self.sources = sources or DEFAULT_NEWS_SOURCES

    def parse_rss_feed(self, rss_xml: str, source_name: str, source_url: str) -> List[News]:
        """Parse RSS/Atom XML feed into 24h freshness-verified News Pydantic models."""
        news_items: List[News] = []
        try:
            soup = BeautifulSoup(rss_xml, "xml")
        except Exception:
            soup = BeautifulSoup(rss_xml, "html.parser")

        items = soup.find_all("item") or soup.find_all("entry")
        for item in items:
            title_tag = item.find(lambda tag: tag.name.lower() == "title")
            link_tag = item.find(lambda tag: tag.name.lower() == "link")
            pub_date_tag = item.find(lambda tag: tag.name.lower() in ("pubdate", "published", "dc:date", "updated"))
            author_tag = item.find(lambda tag: tag.name.lower() in ("dc:creator", "author", "creator"))
            desc_tag = item.find(lambda tag: tag.name.lower() in ("description", "summary", "content"))

            if not title_tag or not link_tag:
                continue

            title = title_tag.get_text(strip=True)
            # Handle RSS link tag which can be <link>url</link> or <link href="url"/>
            link = link_tag.get_text(strip=True) or link_tag.get("href", "")
            if not link:
                continue

            pub_date_raw = pub_date_tag.get_text(strip=True) if pub_date_tag else None
            author = author_tag.get_text(strip=True) if author_tag else None
            summary = desc_tag.get_text(strip=True) if desc_tag else None
            if summary:
                # Strip HTML tags from summary text
                summary = BeautifulSoup(summary, "html.parser").get_text(strip=True)

            # Verify 24h freshness
            is_fresh, normalized_dt, reason = self.freshness_engine.verify_freshness(pub_date_raw)
            if is_fresh and normalized_dt:
                try:
                    article = News(
                        title=title,
                        article_url=link,
                        author=author,
                        summary=summary,
                        content=summary,
                        publication_date=normalized_dt.isoformat(),
                        freshness_verified=True,
                        source_name=source_name,
                        source_url=source_url
                    )
                    news_items.append(article)
                except Exception as e:
                    logger.warning(f"Skipping invalid News item: {e}", extra={"component": "NewsCrawler"})

        return news_items

    async def fetch_fresh_news(self) -> List[News]:
        """Fetch fresh news articles from all 5 sources."""
        all_news: List[News] = []

        async with self.crawler:
            for src in self.sources:
                logger.info(f"Fetching news feed: {src['name']} ({src['url']})", extra={"component": "NewsCrawler"})
                resp = await self.crawler.fetch(src["url"])
                if resp.is_success:
                    items = self.parse_rss_feed(resp.text, src["name"], src["url"])
                    logger.info(f"Retrieved {len(items)} fresh articles from {src['name']}", extra={"component": "NewsCrawler"})
                    all_news.extend(items)
                else:
                    logger.warning(f"Failed to fetch {src['name']}: {resp.status_code}", extra={"component": "NewsCrawler"})

        logger.info(f"Total verified fresh news articles: {len(all_news)}", extra={"component": "NewsCrawler"})
        return all_news
