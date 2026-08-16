"""News Crawler for acquiring fresh AI news articles from 5 verified RSS/API sources.

Discovery vs Extraction:
  - DISCOVERY: RSS feeds provide article URLs, titles, publication dates
  - DIRECT (from RSS): title, article_url, publication_date, author
  - CONTENT FETCH: follows article_url to retrieve full article text
  - LLM EXTRACTION: structures full article text into summary/content fields
"""
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
    """Crawls 5 verified AI news RSS feeds, filters for 24h freshness,
    and fetches full article content from source URLs."""

    def __init__(
        self,
        crawler: Optional[BaseAsyncCrawler] = None,
        freshness_engine: Optional[FreshnessEngine] = None,
        sources: Optional[List[Dict[str, str]]] = None
    ):
        self.crawler = crawler or BaseAsyncCrawler()
        self.freshness_engine = freshness_engine or FreshnessEngine(max_age_hours=24.0)
        self.sources = sources or DEFAULT_NEWS_SOURCES

    def _extract_article_text(self, html: str) -> str:
        """Extract main article text from HTML, stripping navigation/ads/boilerplate.

        Uses a heuristic approach: extracts text from <article>, <main>, or
        the largest <div> with paragraph content.
        """
        soup = BeautifulSoup(html, "html.parser")

        # Remove script, style, nav, header, footer, aside elements
        for tag in soup.find_all(["script", "style", "nav", "header", "footer",
                                   "aside", "form", "iframe", "noscript"]):
            tag.decompose()

        # Priority 1: <article> tag
        article = soup.find("article")
        if article:
            paragraphs = article.find_all("p")
            text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
            if len(text) > 200:
                return text[:5000]  # Cap at 5000 chars

        # Priority 2: <main> tag
        main = soup.find("main")
        if main:
            paragraphs = main.find_all("p")
            text = "\n\n".join(p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 20)
            if len(text) > 200:
                return text[:5000]

        # Priority 3: all <p> tags with substantial content
        all_paragraphs = soup.find_all("p")
        substantial = [p.get_text(strip=True) for p in all_paragraphs if len(p.get_text(strip=True)) > 40]
        if substantial:
            return "\n\n".join(substantial)[:5000]

        return ""

    def parse_rss_feed(self, rss_xml: str, source_name: str, source_url: str) -> List[News]:
        """Parse RSS/Atom XML feed into 24h freshness-verified News Pydantic models.

        At this stage, content is the RSS summary only. Full article text
        is fetched separately via fetch_article_content().
        """
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
            rss_summary = desc_tag.get_text(strip=True) if desc_tag else None
            if rss_summary:
                # Strip HTML tags from summary text
                rss_summary = BeautifulSoup(rss_summary, "html.parser").get_text(strip=True)

            # Verify 24h freshness
            is_fresh, normalized_dt, reason = self.freshness_engine.verify_freshness(pub_date_raw)
            if is_fresh and normalized_dt:
                try:
                    article = News(
                        title=title,
                        article_url=link,
                        author=author,
                        summary=rss_summary,  # RSS summary — may be short
                        content=rss_summary,   # Placeholder until full text fetched
                        publication_date=normalized_dt.isoformat(),
                        freshness_verified=True,
                        source_name=source_name,
                        source_url=source_url
                    )
                    news_items.append(article)
                except Exception as e:
                    logger.warning(f"Skipping invalid News item: {e}", extra={"component": "NewsCrawler"})

        return news_items

    async def fetch_article_content(self, article_url: str) -> Optional[str]:
        """Fetch full article content by following the article URL.

        Returns extracted article text, or None if fetch fails.
        This text becomes the LLM extraction target for structured content.
        """
        try:
            resp = await self.crawler.fetch(article_url)
            if resp.is_success:
                text = self._extract_article_text(resp.text)
                if text and len(text) > 100:
                    return text
        except Exception as e:
            logger.debug(f"Could not fetch article content from {article_url}: {e}",
                         extra={"component": "NewsCrawler"})
        return None

    async def fetch_fresh_news(self) -> List[News]:
        """Fetch fresh news articles from all 5 sources and enrich with full content."""
        all_news: List[News] = []

        async with self.crawler:
            # Phase 1: Discover fresh articles via RSS
            for src in self.sources:
                logger.info(f"Fetching news feed: {src['name']} ({src['url']})", extra={"component": "NewsCrawler"})
                resp = await self.crawler.fetch(src["url"])
                if resp.is_success:
                    items = self.parse_rss_feed(resp.text, src["name"], src["url"])
                    logger.info(f"Retrieved {len(items)} fresh articles from {src['name']}", extra={"component": "NewsCrawler"})
                    all_news.extend(items)
                else:
                    logger.warning(f"Failed to fetch {src['name']}: {resp.status_code}", extra={"component": "NewsCrawler"})

            # Phase 2: Fetch full article content for each fresh article
            enriched_count = 0
            for article in all_news:
                full_text = await self.fetch_article_content(article.article_url)
                if full_text:
                    article.content = full_text
                    enriched_count += 1
                # If fetch fails, content retains RSS summary

            logger.info(f"Total verified fresh news articles: {len(all_news)} "
                        f"({enriched_count} enriched with full article text)",
                        extra={"component": "NewsCrawler"})

        return all_news
