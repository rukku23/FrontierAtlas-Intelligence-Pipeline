"""Main entry point for the FrontierAtlas Intelligence Pipeline."""
import asyncio
import sys
import argparse
from typing import List
from src.crawlers.base_crawler import BaseAsyncCrawler
from src.crawlers.arxiv_crawler import ArxivCrawler
from src.crawlers.startup_crawler import StartupCrawler
from src.crawlers.product_crawler import ProductCrawler
from src.crawlers.news.news_crawler import NewsCrawler
from src.crawlers.jobs.job_crawler import JobCrawler
from src.enrichment.github_enrichment import GitHubEnricher
from src.entity_resolution.entity_resolver import EntityResolver
from src.entity_resolution.deduplicator import Deduplicator
from src.storage.db import DatabaseStorage
from src.storage.sheets_sync import GoogleSheetsExporter
from src.utils.metrics import PipelineMetrics
from src.utils.logger import logger
from src.utils.config import get_config

async def run_pipeline(
    paper_limit: int = 1000,
    startup_limit: int = 1000,
    product_limit: int = 1000,
    export_sheets: bool = True
) -> PipelineMetrics:
    """Run the complete end-to-end FrontierAtlas intelligence pipeline."""
    metrics = PipelineMetrics()
    logger.info("Starting FrontierAtlas Intelligence Pipeline...", extra={"component": "PipelineMain"})

    db = DatabaseStorage()
    dedup = Deduplicator()
    resolver = EntityResolver()
    base_crawler = BaseAsyncCrawler()
    github_enricher = GitHubEnricher(crawler=base_crawler)

    async with base_crawler:
        # -------------------------------------------------------------
        # STAGE 1: RESEARCH PAPERS & GITHUB STAR ENRICHMENT
        # -------------------------------------------------------------
        logger.info("=== STAGE 1: Research Paper Pipeline ===", extra={"component": "PipelineMain"})
        arxiv = ArxivCrawler(crawler=base_crawler)
        raw_papers = await arxiv.fetch_papers(limit=paper_limit)
        metrics.records_discovered += len(raw_papers)

        unique_papers = dedup.filter_duplicates(raw_papers)
        metrics.duplicates += (len(raw_papers) - len(unique_papers))

        # Enrich GitHub stars for papers with legitimate GitHub links
        for paper in unique_papers:
            if paper.github_repository_url:
                stars = await github_enricher.get_star_count(paper.github_repository_url)
                if stars is not None:
                    paper.github_stars = stars
                    metrics.github_stars_enriched += 1

        saved_papers = db.save_papers(unique_papers)
        metrics.records_processed += saved_papers

        # -------------------------------------------------------------
        # STAGE 2: STARTUPS & ENTITY RESOLUTION
        # -------------------------------------------------------------
        logger.info("=== STAGE 2: Startup Pipeline ===", extra={"component": "PipelineMain"})
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
        saved_startups = db.save_startups(unique_startups)
        metrics.records_processed += saved_startups

        # -------------------------------------------------------------
        # STAGE 3: PRODUCTS PIPELINE
        # -------------------------------------------------------------
        logger.info("=== STAGE 3: Product Pipeline ===", extra={"component": "PipelineMain"})
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
        saved_products = db.save_products(unique_products)
        metrics.records_processed += saved_products

        # -------------------------------------------------------------
        # STAGE 4: NEWS PIPELINE (24H FRESHNESS FILTERED)
        # -------------------------------------------------------------
        logger.info("=== STAGE 4: News Pipeline (24h Freshness) ===", extra={"component": "PipelineMain"})
        news_crawler = NewsCrawler(crawler=base_crawler)
        fresh_news = await news_crawler.fetch_fresh_news()
        metrics.records_discovered += len(fresh_news)
        metrics.fresh_records += len(fresh_news)

        unique_news = dedup.filter_duplicates(fresh_news)
        metrics.duplicates += (len(fresh_news) - len(unique_news))
        saved_news = db.save_news(unique_news)
        metrics.records_processed += saved_news

        # -------------------------------------------------------------
        # STAGE 5: JOB PIPELINE (24H FRESHNESS FILTERED)
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
