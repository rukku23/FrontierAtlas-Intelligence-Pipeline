"""Product Crawler for acquiring real AI products/models/tools from public APIs with pagination."""
import json
from typing import List, Optional, Set
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.schemas import Product, PricingType
from src.utils.logger import logger


class ProductCrawler:
    """Crawler for AI products and tools using paginated Hugging Face APIs."""

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()

    async def fetch_products(self, limit: int = 1000) -> List[Product]:
        """Acquire real AI product records from paginated Hugging Face Spaces and Models APIs."""
        products: List[Product] = []
        seen_ids: Set[str] = set()
        batch_size = 1000

        async with self.crawler:
            # ---------------------------------------------------------------
            # SOURCE 1: Hugging Face Spaces (AI Web Applications / Products)
            # ---------------------------------------------------------------
            offset = 0
            max_pages = 5

            for page in range(max_pages):
                if len(products) >= limit:
                    break

                spaces_url = (
                    f"https://huggingface.co/api/spaces"
                    f"?limit={batch_size}&offset={offset}&full=false&sort=likes&direction=-1"
                )
                logger.info(
                    f"Fetching HF Spaces page {page + 1} (offset={offset})",
                    extra={"component": "ProductCrawler", "url": spaces_url}
                )
                resp = await self.crawler.fetch(spaces_url)
                if not resp.is_success:
                    logger.warning(f"HF Spaces API returned {resp.status_code}", extra={"component": "ProductCrawler"})
                    break

                try:
                    data = json.loads(resp.text)
                    if not data:
                        break

                    for item in data:
                        space_id = item.get("id", "")
                        if not space_id or space_id in seen_ids:
                            continue
                        seen_ids.add(space_id)

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

                    logger.info(
                        f"Spaces page {page + 1}: total products so far {len(products)}",
                        extra={"component": "ProductCrawler"}
                    )

                    if len(data) < batch_size:
                        break
                    offset += batch_size

                except Exception as e:
                    logger.error(f"Error parsing HF Spaces page {page + 1}: {e}", extra={"component": "ProductCrawler"})
                    break

            # ---------------------------------------------------------------
            # SOURCE 2: Hugging Face Models (if additional products needed)
            # ---------------------------------------------------------------
            if len(products) < limit:
                m_offset = 0
                m_max_pages = 5

                for page in range(m_max_pages):
                    if len(products) >= limit:
                        break

                    needed = limit - len(products)
                    fetch_size = min(batch_size, needed + 200)  # Fetch extra for dedup headroom

                    models_url = (
                        f"https://huggingface.co/api/models"
                        f"?limit={fetch_size}&offset={m_offset}&full=false&sort=downloads&direction=-1"
                    )
                    logger.info(
                        f"Fetching HF Models page {page + 1} for products (offset={m_offset})",
                        extra={"component": "ProductCrawler", "url": models_url}
                    )
                    resp = await self.crawler.fetch(models_url)
                    if not resp.is_success:
                        break

                    try:
                        data = json.loads(resp.text)
                        if not data:
                            break

                        for item in data:
                            model_id = item.get("id", "")
                            if not model_id or model_id in seen_ids:
                                continue
                            seen_ids.add(model_id)

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

                        if len(data) < fetch_size:
                            break
                        m_offset += fetch_size

                    except Exception as e:
                        logger.error(f"Error parsing HF Models page {page + 1}: {e}", extra={"component": "ProductCrawler"})
                        break

        logger.info(f"Total real products fetched: {len(products)}", extra={"component": "ProductCrawler"})
        return products[:limit]
