"""Product Crawler for acquiring real AI products/models/tools from public APIs."""
import json
from typing import List, Optional
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.schemas import Product, PricingType
from src.utils.logger import logger

class ProductCrawler:
    """Crawler for AI products and tools using open Hugging Face APIs."""

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()

    async def fetch_products(self, limit: int = 1000) -> List[Product]:
        """Acquire real AI product records from public Hugging Face Spaces and Models APIs."""
        products: List[Product] = []

        async with self.crawler:
            # 1. Fetch HF Spaces (Web AI Applications/Products)
            spaces_url = f"https://huggingface.co/api/spaces?limit={limit}"
            resp_spaces = await self.crawler.fetch(spaces_url)
            if resp_spaces.is_success:
                try:
                    data = json.loads(resp_spaces.text)
                    for item in data:
                        space_id = item.get("id", "")
                        if not space_id:
                            continue
                        
                        parts = space_id.split("/")
                        creator = parts[0] if len(parts) > 1 else None
                        product_name = parts[1] if len(parts) > 1 else space_id
                        
                        source_url = f"https://huggingface.co/spaces/{space_id}"
                        product = Product(
                            name=product_name,
                            canonical_name=None,
                            description=f"AI Web Application / Space by {creator or 'Community'} (SDK: {item.get('sdk', 'unknown')})",
                            product_url=source_url,
                            source_url=source_url,
                            pricing_type=PricingType.FREE,  # Public HF Spaces are open/free
                            pricing_details="Open Access Public Space",
                            company_name=creator,
                            categories=item.get("tags", ["AI App", "Hugging Face Space"])[:5]
                        )
                        products.append(product)
                        if len(products) >= limit:
                            break
                except Exception as e:
                    logger.error(f"Error parsing HF Spaces: {e}", extra={"component": "ProductCrawler"})

            # 2. If additional products needed, fetch HF Models
            if len(products) < limit:
                needed = limit - len(products)
                models_url = f"https://huggingface.co/api/models?limit={needed}"
                resp_models = await self.crawler.fetch(models_url)
                if resp_models.is_success:
                    try:
                        m_data = json.loads(resp_models.text)
                        for item in m_data:
                            model_id = item.get("id", "")
                            if not model_id:
                                continue
                            parts = model_id.split("/")
                            creator = parts[0] if len(parts) > 1 else None
                            name = parts[1] if len(parts) > 1 else model_id
                            source_url = f"https://huggingface.co/{model_id}"

                            product = Product(
                                name=name,
                                canonical_name=None,
                                description=f"AI Model/Product ({item.get('pipeline_tag', 'machine-learning')})",
                                product_url=source_url,
                                source_url=source_url,
                                pricing_type=PricingType.UNKNOWN,  # Do not guess pricing
                                pricing_details=None,
                                company_name=creator,
                                categories=[item.get("pipeline_tag", "ai-model")]
                            )
                            products.append(product)
                            if len(products) >= limit:
                                break
                    except Exception as e:
                        logger.error(f"Error parsing HF Models: {e}", extra={"component": "ProductCrawler"})

        logger.info(f"Total real products fetched: {len(products)}", extra={"component": "ProductCrawler"})
        return products[:limit]
