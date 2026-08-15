"""ArXiv Research Paper Crawler with Atom XML parsing and pagination."""
import xml.etree.ElementTree as ET
import re
from typing import List, Optional, Tuple
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.schemas import ResearchPaper
from src.utils.logger import logger

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

class ArxivCrawler:
    """Crawler for ArXiv REST API (Atom XML format)."""

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()

    def _extract_github_url_from_text(self, text: str) -> Optional[str]:
        """Extract legitimate github.com repository URL from text if present."""
        if not text:
            return None
        match = re.search(r"https?://github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+)", text)
        if match:
            repo_path = match.group(1).rstrip(".,;)]")
            return f"https://github.com/{repo_path}"
        return None

    def parse_atom_xml(self, xml_content: str) -> List[ResearchPaper]:
        """Parse ArXiv Atom XML content into ResearchPaper Pydantic objects."""
        papers: List[ResearchPaper] = []
        try:
            root = ET.fromstring(xml_content)
        except ET.ParseError as exc:
            logger.error(f"Failed to parse ArXiv XML: {exc}", extra={"component": "ArxivCrawler"})
            return papers

        entries = root.findall("atom:entry", ATOM_NS)
        for entry in entries:
            id_elem = entry.find("atom:id", ATOM_NS)
            title_elem = entry.find("atom:title", ATOM_NS)
            published_elem = entry.find("atom:published", ATOM_NS)
            summary_elem = entry.find("atom:summary", ATOM_NS)
            comment_elem = entry.find("arxiv:comment", ATOM_NS)

            if id_elem is None or title_elem is None:
                continue

            paper_url = id_elem.text.strip() if id_elem.text else ""
            title = re.sub(r"\s+", " ", title_elem.text.strip()) if title_elem.text else ""
            pub_date = published_elem.text.strip() if published_elem is not None and published_elem.text else None
            abstract = re.sub(r"\s+", " ", summary_elem.text.strip()) if summary_elem is not None and summary_elem.text else None
            comment = comment_elem.text.strip() if comment_elem is not None and comment_elem.text else ""

            authors = []
            for author_node in entry.findall("atom:author", ATOM_NS):
                name_elem = author_node.find("atom:name", ATOM_NS)
                if name_elem is not None and name_elem.text:
                    authors.append(name_elem.text.strip())

            # Check for GitHub link in abstract or comment
            github_url = self._extract_github_url_from_text(abstract or "") or self._extract_github_url_from_text(comment)

            try:
                paper = ResearchPaper(
                    title=title,
                    authors=authors,
                    paper_url=paper_url,
                    source_url=paper_url,
                    abstract=abstract,
                    publication_date=pub_date,
                    github_repository_url=github_url,
                    github_stars=None,  # Enriched separately via GitHub API
                    source="arxiv"
                )
                papers.append(paper)
            except Exception as e:
                logger.warning(f"Skipping invalid paper record: {e}", extra={"component": "ArxivCrawler"})

        return papers

    async def fetch_papers(
        self,
        categories: List[str] = ["cs.AI", "cs.LG", "cs.CL"],
        limit: int = 1000,
        batch_size: int = 100
    ) -> List[ResearchPaper]:
        """Fetch papers from ArXiv API with pagination."""
        query_str = " OR ".join(f"cat:{cat}" for cat in categories)
        all_papers: List[ResearchPaper] = []
        start = 0

        async with self.crawler:
            while len(all_papers) < limit:
                current_batch = min(batch_size, limit - len(all_papers))
                api_url = (
                    f"http://export.arxiv.org/api/query?"
                    f"search_query={query_str}&start={start}&max_results={current_batch}"
                    f"&sortBy=submittedDate&sortOrder=descending"
                )
                logger.info(
                    f"Fetching ArXiv batch: start={start}, max_results={current_batch}",
                    extra={"component": "ArxivCrawler", "url": api_url}
                )
                resp = await self.crawler.fetch(api_url)

                if not resp.is_success:
                    logger.error(f"ArXiv request failed at start={start}: {resp.error}", extra={"component": "ArxivCrawler"})
                    break

                batch_papers = self.parse_atom_xml(resp.text)
                if not batch_papers:
                    logger.info("No more papers returned from ArXiv", extra={"component": "ArxivCrawler"})
                    break

                all_papers.extend(batch_papers)
                start += len(batch_papers)

        logger.info(f"Total ArXiv papers fetched: {len(all_papers)}", extra={"component": "ArxivCrawler"})
        return all_papers[:limit]
