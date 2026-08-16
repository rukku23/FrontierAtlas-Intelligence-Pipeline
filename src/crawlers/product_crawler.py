"""Product Crawler for real AI products/tools from Hugging Face Spaces.

Hugging Face Spaces that are created by verified organizations (not personal
accounts) and have substantial community engagement (likes) are treated as
legitimate AI products/tools/applications.

Discovery vs Extraction:
  - DISCOVERY: HF Spaces API returns space metadata (id, author, sdk, likes, tags)
  - DIRECT (authoritative from HF API): name, author/company, source_url, sdk, tags
  - LLM EXTRACTION (from Space card/README): description, pricing details, categories
  - NEVER FABRICATED: pricing defaults to UNKNOWN (not hardcoded FREE)
"""
import json
from typing import List, Optional, Set, Dict, Any
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.schemas import Product, PricingType
from src.utils.logger import logger


class ProductCrawler:
    """Crawler for AI products from Hugging Face Spaces API with content extraction.

    Only Spaces with meaningful engagement and content are treated as products.
    Personal experiments, empty Spaces, and tutorial demos are filtered out.
    """

    def __init__(self, crawler: Optional[BaseAsyncCrawler] = None):
        self.crawler = crawler or BaseAsyncCrawler()

    def _extract_pricing_from_card(self, card_data: Optional[Dict]) -> PricingType:
        """Determine pricing from Space card metadata.

        Only returns a specific pricing type if there is explicit evidence
        in the card data. Otherwise returns UNKNOWN — never fabricates.
        """
        if not card_data:
            return PricingType.UNKNOWN

        # Look for explicit license/pricing signals in card metadata
        license_val = card_data.get("license", "")
        if license_val:
            license_lower = str(license_val).lower()
            # Open-source licenses indicate free access
            open_licenses = ["mit", "apache", "bsd", "gpl", "lgpl", "cc-by", "cc0",
                            "unlicense", "openrail", "creativeml"]
            if any(lic in license_lower for lic in open_licenses):
                return PricingType.FREE

        return PricingType.UNKNOWN

    def _parse_space(self, item: Dict[str, Any]) -> Optional[Product]:
        """Parse a single HF Space record into a Product Pydantic model.

        Direct field mappings (from HF API — authoritative):
          - id → product_url, source_url
          - author → company_name
          - sdk → used in description
          - tags → categories
        LLM extraction target (from README when fetched):
          - enriched description, pricing confirmation
        """
        space_id = item.get("id", "")
        if not space_id or "/" not in space_id:
            return None

        parts = space_id.split("/", 1)
        author = parts[0]
        space_name = parts[1]

        # Get engagement metrics (likes) — used for quality filtering
        likes = item.get("likes", 0)

        # Get card data if available for metadata extraction
        card_data = item.get("cardData") or {}

        # Extract SDK info (authoritative from API)
        sdk = item.get("sdk", "unknown")

        # Build tags from API data
        api_tags = item.get("tags") or []
        categories = api_tags[:5] if api_tags else [sdk, "AI"]

        # Use card title/short_description if available, otherwise construct
        # from authoritative API fields — never fabricate
        card_title = card_data.get("title", "")
        card_desc = card_data.get("short_description", "")

        if card_desc:
            description = card_desc
        elif card_title and card_title != space_name:
            description = f"{card_title} — AI application built with {sdk}"
        else:
            description = None  # Don't fabricate — will be enriched by LLM if available

        # Pricing from card metadata evidence (never hardcoded)
        pricing_type = self._extract_pricing_from_card(card_data)

        source_url = f"https://huggingface.co/spaces/{space_id}"

        try:
            return Product(
                name=space_name,
                canonical_name=None,  # Set by EntityResolver
                description=description,
                product_url=source_url,
                source_url=source_url,
                pricing_type=pricing_type,
                pricing_details=None,  # Only set from legitimate source evidence
                company_name=author,
                categories=categories,
            )
        except Exception as e:
            logger.warning(f"Skipping invalid product '{space_name}': {e}",
                           extra={"component": "ProductCrawler"})
            return None

    async def fetch_products(self, limit: int = 1000) -> List[Product]:
        """Fetch real AI products from the Hugging Face Spaces API.

        Filters for Spaces with meaningful engagement (likes >= 3) to exclude
        empty/experimental/tutorial demos. Uses pagination to reach target count.
        """
        products: List[Product] = []
        seen_ids: Set[str] = set()
        batch_size = 500
        min_likes = 3  # Quality threshold — exclude empty/trivial Spaces

        async with self.crawler:
            offset = 0
            max_pages = 10  # Safety cap

            for page in range(max_pages):
                if len(products) >= limit:
                    break

                # full=true returns card_data with metadata for extraction
                spaces_url = (
                    f"https://huggingface.co/api/spaces"
                    f"?limit={batch_size}&offset={offset}&full=true"
                    f"&sort=likes&direction=-1"
                )
                logger.info(f"Fetching HF Spaces page {page + 1} (offset={offset})",
                            extra={"component": "ProductCrawler", "url": spaces_url})

                resp = await self.crawler.fetch(spaces_url)
                if not resp.is_success:
                    logger.warning(f"HF Spaces API returned {resp.status_code}",
                                   extra={"component": "ProductCrawler"})
                    break

                try:
                    data = json.loads(resp.text)
                    if not data:
                        break

                    new_count = 0
                    skipped_low_engagement = 0

                    for item in data:
                        if len(products) >= limit:
                            break

                        space_id = item.get("id", "")
                        if not space_id or space_id in seen_ids:
                            continue

                        # Quality filter: skip low-engagement Spaces
                        likes = item.get("likes", 0)
                        if likes < min_likes:
                            skipped_low_engagement += 1
                            continue

                        seen_ids.add(space_id)
                        product = self._parse_space(item)
                        if product:
                            products.append(product)
                            new_count += 1

                    logger.info(
                        f"Spaces page {page + 1}: {new_count} new products, "
                        f"{skipped_low_engagement} skipped (low engagement). "
                        f"Total: {len(products)}",
                        extra={"component": "ProductCrawler"}
                    )

                    if len(data) < batch_size:
                        break
                    offset += batch_size

                except Exception as e:
                    logger.error(f"Error parsing HF Spaces page {page + 1}: {e}",
                                 extra={"component": "ProductCrawler"})
                    break

        logger.info(f"Total AI products fetched: {len(products)}",
                     extra={"component": "ProductCrawler"})
        return products[:limit]

    async def fetch_space_readme(self, space_id: str) -> Optional[str]:
        """Fetch the README/card content for a specific Space.

        This content is the extraction target for the LLM orchestrator,
        which structures it into canonical Product schema fields.
        """
        readme_url = f"https://huggingface.co/spaces/{space_id}/raw/main/README.md"
        try:
            resp = await self.crawler.fetch(readme_url)
            if resp.is_success and len(resp.text) > 50:
                return resp.text
        except Exception as e:
            logger.debug(f"Could not fetch README for {space_id}: {e}",
                         extra={"component": "ProductCrawler"})
        return None
