"""Script to test live connectivity to all data sources."""
import asyncio
import json
from src.crawlers.base_crawler import BaseAsyncCrawler

async def main():
    async with BaseAsyncCrawler() as crawler:
        sources = {
            "ArXiv Papers": "http://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=5",
            "HF Spaces (Products)": "https://huggingface.co/api/spaces?limit=5",
            "HF Models (Products)": "https://huggingface.co/api/models?limit=5",
            "HF Orgs (Startups)": "https://huggingface.co/api/organizations",
            "TechCrunch AI News": "https://techcrunch.com/category/artificial-intelligence/feed/",
            "VentureBeat AI News": "https://venturebeat.com/category/ai/feed/",
            "MIT Tech Review News": "https://www.technologyreview.com/feed/",
            "The Verge AI News": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml",
            "Hacker News RSS": "https://news.ycombinator.com/rss",
            "RemoteOK Jobs": "https://remoteok.com/api",
            "WeWorkRemotely Jobs": "https://weworkremotely.com/categories/remote-full-stack-programming-jobs.rss",
            "Remotive Jobs": "https://remotive.com/api/remote-jobs?category=software-dev",
            "Python.org Jobs": "https://www.python.org/jobs/feed/rss/",
        }

        print("=== DATA SOURCE CONNECTIVITY TEST ===")
        for name, url in sources.items():
            resp = await crawler.fetch(url)
            status = "SUCCESS" if resp.is_success else f"FAILED ({resp.status_code})"
            print(f"[{status}] {name} ({resp.latency_ms:.1f}ms) -> {url}")

if __name__ == "__main__":
    asyncio.run(main())
