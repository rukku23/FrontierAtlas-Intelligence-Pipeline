"""Unit tests for ArXiv Crawler and GitHub Enricher."""
import pytest
import httpx
from src.crawlers.arxiv_crawler import ArxivCrawler
from src.enrichment.github_enrichment import GitHubEnricher
from src.crawlers.base_crawler import BaseAsyncCrawler

SAMPLE_ARXIV_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Awesome AI Model Architecture</title>
    <published>2024-01-01T12:00:00Z</published>
    <summary>We present a new AI model. Code available at https://github.com/example/awesome-ai.</summary>
    <author><name>Jane Doe</name></author>
    <author><name>John Smith</name></author>
    <arxiv:comment>Accepted at NeurIPS 2024</arxiv:comment>
  </entry>
</feed>
"""

def test_arxiv_atom_xml_parser():
    crawler = ArxivCrawler()
    papers = crawler.parse_atom_xml(SAMPLE_ARXIV_XML)
    assert len(papers) == 1
    paper = papers[0]
    assert paper.title == "Awesome AI Model Architecture"
    assert paper.authors == ["Jane Doe", "John Smith"]
    assert paper.paper_url == "http://arxiv.org/abs/2401.00001v1"
    assert paper.github_repository_url == "https://github.com/example/awesome-ai"

@pytest.mark.asyncio
async def test_github_enricher_success():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/repos/example/awesome-ai"
        return httpx.Response(200, json={"stargazers_count": 4200}, request=request)

    transport = httpx.MockTransport(handler)
    base_crawler = BaseAsyncCrawler()
    base_crawler._client = httpx.AsyncClient(transport=transport)
    
    enricher = GitHubEnricher(crawler=base_crawler)
    stars = await enricher.get_star_count("https://github.com/example/awesome-ai")
    assert stars == 4200
    await base_crawler.close()

@pytest.mark.asyncio
async def test_github_enricher_invalid_url():
    enricher = GitHubEnricher()
    stars = await enricher.get_star_count("not_a_github_url")
    assert stars is None
