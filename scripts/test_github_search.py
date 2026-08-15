import asyncio
import json
import os
from src.crawlers.base_crawler import BaseAsyncCrawler

async def main():
    async with BaseAsyncCrawler(user_agent="FrontierAtlas-IngestionBot/1.0") as crawler:
        headers = {"Accept": "application/vnd.github.v3+json"}
        token = os.getenv("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"token {token}"
            
        url = "https://api.github.com/search/repositories?q=topic:artificial-intelligence+OR+topic:llm&per_page=100"
        resp = await crawler.fetch(url, headers=headers)
        print("GitHub Search status:", resp.status_code)
        if resp.is_success:
            data = json.loads(resp.text)
            items = data.get("items", [])
            print("Total GitHub repo items found:", data.get("total_count"), f"(fetched {len(items)})")
            if items:
                print("Sample:", items[0]["name"], items[0]["html_url"], items[0].get("description"))

if __name__ == "__main__":
    asyncio.run(main())
