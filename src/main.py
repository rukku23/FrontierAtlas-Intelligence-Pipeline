"""Main entry point for the FrontierAtlas Intelligence Pipeline.

Architecture:
  DISCOVERY (API/RSS) → CONTENT FETCH → LLM EXTRACTION → PYDANTIC VALIDATION → SAVE

The LLM orchestrator is integrated at the extraction stage for fields
that require structuring from unstructured text. Authoritative structured
fields (e.g., ArXiv title, GitHub stars) are mapped directly.
"""
import asyncio
import sys
import argparse
from typing import List, Optional
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.crawlers.arxiv_crawler import ArxivCrawler
from src.crawlers.startup_crawler import StartupCrawler
from src.crawlers.product_crawler import ProductCrawler
from src.crawlers.news.news_crawler import NewsCrawler
from src.crawlers.jobs.job_crawler import JobCrawler
from src.enrichment.github_enrichment import GitHubEnricher
from src.extraction.llm_orchestrator import LLMOrchestrator
from src.extraction.llm_provider import LLMProvider
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.deduplicator import Deduplicator
from src.storage.db import DatabaseStorage
from src.storage.sheets_sync import GoogleSheetsExporter
from src.schemas import Startup, Product, News
from src.utils.metrics import PipelineMetrics
from src.utils.logger import logger
from src.utils.config import get_config


async def _llm_enrich_startup(
    orchestrator: LLMOrchestrator,
    startup: Startup,
    raw_description: Optional[str],
    metrics: PipelineMetrics
) -> Startup:
    """Use LLM to extract structured fields from startup description text.

    Only enriches fields that benefit from LLM structuring.
    Never overwrites authoritative API fields (name, website, team_size, etc.)
    """
    if not raw_description or len(raw_description) < 50:
        return startup

    try:
        result = await orchestrator.extract_structured(raw_description, Startup)
        if result:
            # Only take LLM-extracted fields that enhance the record
            # NEVER overwrite authoritative fields from YC API
            if result.description and not startup.description:
                startup.description = result.description
            if result.categories and len(result.categories) > len(startup.categories or []):
                startup.categories = result.categories
            metrics.llm_fallbacks += 1  # Track LLM usage
    except Exception as e:
        logger.debug(f"LLM enrichment skipped for startup '{startup.name}': {e}",
                     extra={"component": "PipelineMain"})

    return startup


async def _llm_enrich_product(
    orchestrator: LLMOrchestrator,
    product: Product,
    readme_content: Optional[str],
    metrics: PipelineMetrics
) -> Product:
    """Use LLM to extract structured product fields from Space README content.

    Enriches description and categories. Never fabricates pricing.
    """
    if not readme_content or len(readme_content) < 50:
        return product

    try:
        result = await orchestrator.extract_structured(readme_content, Product)
        if result:
            if result.description and (not product.description or len(result.description) > len(product.description)):
                product.description = result.description
            if result.categories:
                product.categories = result.categories
            metrics.llm_fallbacks += 1
    except Exception as e:
        logger.debug(f"LLM enrichment skipped for product '{product.name}': {e}",
                     extra={"component": "PipelineMain"})

    return product


async def _llm_extract_news_content(
    orchestrator: LLMOrchestrator,
    article: News,
    metrics: PipelineMetrics
) -> News:
    """Use LLM to extract structured summary from full article text.

    The article's content field should already contain full text from
    the news crawler's content fetch phase.
    """
    if not article.content or len(article.content) < 200:
        return article

    try:
        result = await orchestrator.extract_structured(article.content, News)
        if result:
            if result.summary and len(result.summary) > 50:
                article.summary = result.summary
            metrics.llm_fallbacks += 1
    except Exception as e:
        logger.debug(f"LLM extraction skipped for news '{article.title[:40]}': {e}",
                     extra={"component": "PipelineMain"})

    return article


async def run_pipeline(
    paper_limit: int = 1000,
    startup_limit: int = 1000,
    product_limit: int = 1000,
    export_sheets: bool = True,
    db_url: Optional[str] = None
) -> PipelineMetrics:
    """Run the complete end-to-end FrontierAtlas intelligence pipeline.

    Architecture per entity type:
      Papers:   ArXiv API → Direct fields → GitHub regex → GitHub API stars → Save
      Startups: YC-OSS API → Direct fields → LLM enrichment (description) → Save
      Products: HF Spaces API → Direct fields → LLM enrichment (README) → Save
      News:     RSS → Freshness filter → Full text fetch → LLM extraction → Save
      Jobs:     RSS/JSON → Freshness filter → Direct fields → Save
    """
    metrics = PipelineMetrics()
    logger.info("Starting FrontierAtlas Intelligence Pipeline...", extra={"component": "PipelineMain"})

    db = DatabaseStorage(db_url=db_url)
    dedup = Deduplicator()
    resolver = EntityResolver()
    base_crawler = BaseAsyncCrawler()
    github_enricher = GitHubEnricher(crawler=base_crawler)

    # Initialize LLM orchestrator (3-tier fallback: Gemini → Groq → DeepSeek)
    orchestrator = LLMOrchestrator()
    llm_available = bool(orchestrator.providers)
    if llm_available:
        logger.info(f"LLM orchestrator initialized with {len(orchestrator.providers)} providers",
                     extra={"component": "PipelineMain"})
    else:
        logger.warning("No LLM API keys configured — running without LLM extraction. "
                       "Set GEMINI_API_KEY, GROQ_API_KEY, or DEEPSEEK_API_KEY for full extraction.",
                       extra={"component": "PipelineMain"})

    async with base_crawler:
        # -------------------------------------------------------------
        # STAGE 1: RESEARCH PAPERS & GITHUB STAR ENRICHMENT
        # Discovery: ArXiv API (structured XML)
        # Extraction: Direct field mapping (authoritative) + GitHub regex
        # GitHub stars: Direct from GitHub API (never LLM)
        # -------------------------------------------------------------
        logger.info("=== STAGE 1: Research Paper Pipeline ===", extra={"component": "PipelineMain"})
        arxiv = ArxivCrawler(crawler=base_crawler)
        raw_papers = await arxiv.fetch_papers(limit=paper_limit)
        metrics.records_discovered += len(raw_papers)

        unique_papers = dedup.filter_duplicates(raw_papers)
        metrics.duplicates += (len(raw_papers) - len(unique_papers))

        # Enrich GitHub stars for papers with legitimate GitHub links
        # (extracted by regex from paper's own abstract/comments, not LLM)
        for paper in unique_papers:
            if paper.github_repository_url:
                stars = await github_enricher.get_star_count(paper.github_repository_url)
                if stars is not None:
                    paper.github_stars = stars
                    metrics.github_stars_enriched += 1

        saved_papers = db.save_papers(unique_papers)
        metrics.records_processed += saved_papers

        # -------------------------------------------------------------
        # STAGE 2: STARTUPS (YC-OSS API) & ENTITY RESOLUTION
        # Discovery: YC-OSS API (real verified startups)
        # Direct fields: name, website, team_size, location, stage
        # LLM enrichment: extract categories from long_description
        # -------------------------------------------------------------
        logger.info("=== STAGE 2: Startup Pipeline (YC-OSS API) ===", extra={"component": "PipelineMain"})
        startup_crawler = StartupCrawler(crawler=base_crawler)
        raw_startups = await startup_crawler.fetch_startups(limit=startup_limit)
        metrics.records_discovered += len(raw_startups)

        # Entity resolution on startups
        for s in raw_startups:
            res = resolver.resolve(s.name, s.source_url)
            s.canonical_name = res.canonical_name
            if res.match_method != "UNRESOLVED":
                metrics.entity_matches += 1

        unique_startups = dedup.filter_duplicates(raw_startups)
        metrics.duplicates += (len(raw_startups) - len(unique_startups))

        # LLM enrichment for startup descriptions (if LLM available)
        if llm_available:
            enriched_count = 0
            for s in unique_startups[:50]:  # Cap LLM calls at 50 for rate limits
                if s.description and len(s.description) > 50:
                    s = await _llm_enrich_startup(orchestrator, s, s.description, metrics)
                    enriched_count += 1
            logger.info(f"LLM-enriched {enriched_count} startup descriptions",
                        extra={"component": "PipelineMain"})

        saved_startups = db.save_startups(unique_startups)
        metrics.records_processed += saved_startups

        # -------------------------------------------------------------
        # STAGE 3: PRODUCTS (HF Spaces) & LLM EXTRACTION
        # Discovery: HF Spaces API (filtered by engagement)
        # Direct fields: name, author, source_url, sdk
        # LLM extraction: README content → description, categories
        # -------------------------------------------------------------
        logger.info("=== STAGE 3: Product Pipeline (HF Spaces) ===", extra={"component": "PipelineMain"})
        product_crawler = ProductCrawler(crawler=base_crawler)
        raw_products = await product_crawler.fetch_products(limit=product_limit)
        metrics.records_discovered += len(raw_products)

        # Entity resolution on product creator companies
        for p in raw_products:
            if p.company_name:
                res = resolver.resolve(p.company_name, p.source_url)
                p.canonical_name = p.name  # Product retains product name
                if res.match_method != "UNRESOLVED":
                    metrics.entity_matches += 1

        unique_products = dedup.filter_duplicates(raw_products)
        metrics.duplicates += (len(raw_products) - len(unique_products))

        # LLM enrichment from Space README content (if LLM available)
        if llm_available:
            enriched_count = 0
            for p in unique_products[:50]:  # Cap at 50 for rate limits
                space_id = p.source_url.replace("https://huggingface.co/spaces/", "")
                readme = await product_crawler.fetch_space_readme(space_id)
                if readme:
                    p = await _llm_enrich_product(orchestrator, p, readme, metrics)
                    enriched_count += 1
            logger.info(f"LLM-enriched {enriched_count} product descriptions from READMEs",
                        extra={"component": "PipelineMain"})

        saved_products = db.save_products(unique_products)
        metrics.records_processed += saved_products

        # -------------------------------------------------------------
        # STAGE 4: NEWS PIPELINE (24H FRESHNESS + FULL TEXT + LLM)
        # Discovery: RSS feeds → freshness filter
        # Content fetch: follows article_url for full text
        # LLM extraction: full text → structured summary
        # -------------------------------------------------------------
        logger.info("=== STAGE 4: News Pipeline (24h Freshness + Full Text) ===", extra={"component": "PipelineMain"})
        news_crawler = NewsCrawler(crawler=base_crawler)
        fresh_news = await news_crawler.fetch_fresh_news()
        metrics.records_discovered += len(fresh_news)
        metrics.fresh_records += len(fresh_news)

        # LLM extraction on full article content (if LLM available)
        if llm_available:
            for article in fresh_news:
                article = await _llm_extract_news_content(orchestrator, article, metrics)

        unique_news = dedup.filter_duplicates(fresh_news)
        metrics.duplicates += (len(fresh_news) - len(unique_news))
        saved_news = db.save_news(unique_news)
        metrics.records_processed += saved_news

        # -------------------------------------------------------------
        # STAGE 5: JOB PIPELINE (24H FRESHNESS FILTERED)
        # Discovery: RSS/JSON APIs → freshness filter
        # Direct fields: company, role, description (from RSS/JSON content)
        # Heuristic: role_family classification from title/description
        # -------------------------------------------------------------
        logger.info("=== STAGE 5: Job Pipeline (24h Freshness) ===", extra={"component": "PipelineMain"})
        job_crawler = JobCrawler(crawler=base_crawler)
        fresh_jobs = await job_crawler.fetch_fresh_jobs()
        metrics.records_discovered += len(fresh_jobs)
        metrics.fresh_records += len(fresh_jobs)

        # Entity resolution on job company names
        for j in fresh_jobs:
            res = resolver.resolve(j.company_name, j.source_url)
            j.canonical_company_name = res.canonical_name
            if res.match_method != "UNRESOLVED":
                metrics.entity_matches += 1

        unique_jobs = dedup.filter_duplicates(fresh_jobs)
        metrics.duplicates += (len(fresh_jobs) - len(unique_jobs))
        saved_jobs = db.save_jobs(unique_jobs)
        metrics.records_processed += saved_jobs

        # -------------------------------------------------------------
        # STAGE 6: ENTITY RESOLUTION AUDIT LOG SAVING
        # -------------------------------------------------------------
        db.save_entity_mappings(resolver.resolution_logs)

    # -------------------------------------------------------------
    # STAGE 7: GOOGLE SHEETS EXPORT
    # -------------------------------------------------------------
    if export_sheets:
        logger.info("=== STAGE 7: Exporting to Google Sheets (6 Tabs) ===", extra={"component": "PipelineMain"})
        sheets_exporter = GoogleSheetsExporter()
        sheets_exporter.export_all(db)

    metrics.log_summary()
    return metrics

def main():
    parser = argparse.ArgumentParser(description="FrontierAtlas Intelligence Pipeline CLI")
    parser.add_argument("--paper-limit", type=int, default=1000, help="Target number of research papers")
    parser.add_argument("--startup-limit", type=int, default=1000, help="Target number of startups")
    parser.add_argument("--product-limit", type=int, default=1000, help="Target number of products")
    parser.add_argument("--no-sheets", action="store_true", help="Disable Google Sheets export")

    args = parser.parse_args()

    asyncio.run(
        run_pipeline(
            paper_limit=args.paper_limit,
            startup_limit=args.startup_limit,
            product_limit=args.product_limit,
            export_sheets=not args.no_sheets
        )
    )

if __name__ == "__main__":
    main()
