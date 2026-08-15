import asyncio
import json
import urllib.parse
from src.crawlers.base_crawler import BaseAsyncCrawler

async def main():
    async with BaseAsyncCrawler() as crawler:
        query = """
        SELECT DISTINCT ?item ?itemLabel ?website ?description WHERE {
          ?item wdt:P31 wd:Q4830453 .
          OPTIONAL { ?item wdt:P856 ?website . }
          OPTIONAL { ?item schema:description ?description . FILTER(LANG(?description) = "en") }
          SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
        } LIMIT 20
        """
        encoded_query = urllib.parse.quote(query.strip())
        url = f"https://query.wikidata.org/sparql?query={encoded_query}&format=json"
        resp = await crawler.fetch(url, headers={"User-Agent": "FrontierAtlas/1.0"})
        print("Wikidata status:", resp.status_code)
        if resp.is_success:
            data = json.loads(resp.text)
            bindings = data["results"]["bindings"]
            print("Wikidata items fetched:", len(bindings))
            for b in bindings[:3]:
                print("-", b["itemLabel"]["value"], b.get("website", {}).get("value", "No website"))

if __name__ == "__main__":
    asyncio.run(main())
