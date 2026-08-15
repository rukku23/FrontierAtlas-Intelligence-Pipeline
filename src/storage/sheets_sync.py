"""Google Sheets Export Module with 6 tabs and batch writing capability."""
import os
import json
from typing import Optional, List, Dict, Any
from src.storage.db import (
    DatabaseStorage, StartupModel, ProductModel, PaperModel, JobModel, NewsModel, EntityMappingLogModel
)
from src.utils.logger import logger

TAB_HEADERS = {
    "Startups": ["ID", "Name", "Canonical Name", "Description", "Website URL", "Source URL", "Employee Count", "Founding Year", "Headquarters", "Categories", "Funding Stage", "Collected At"],
    "Products": ["ID", "Name", "Canonical Name", "Description", "Product URL", "Source URL", "Pricing Type", "Pricing Details", "Company Name", "Categories", "Collected At"],
    "Research Papers": ["ID", "Title", "Authors", "Paper URL", "Source URL", "Abstract", "Publication Date", "GitHub Repo URL", "GitHub Stars", "Source", "Collected At"],
    "Jobs": ["ID", "Company Name", "Canonical Company", "Role Title", "Job URL", "Source URL", "Location", "Is Remote", "Role Family", "Publication Date", "Freshness Verified", "Source Name", "Collected At"],
    "News": ["ID", "Title", "Article URL", "Source URL", "Author", "Summary", "Publication Date", "Freshness Verified", "Source Name", "Collected At"],
    "Entity Mapping Log": ["ID", "Raw Name", "Canonical Name", "Match Method", "Confidence (%)", "Source URL", "Timestamp"]
}

class GoogleSheetsExporter:
    """Exports SQLite data to Google Sheets with 6 tabs using gspread batch updates."""

    def __init__(self, spreadsheet_id: Optional[str] = None, credentials_path: Optional[str] = None):
        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.client = None

    def initialize_client(self) -> bool:
        """Initialize gspread client if credentials exist."""
        if not self.credentials_path or not os.path.exists(self.credentials_path):
            logger.warning("Google credentials file not found. Google Sheets sync skipped (local DB intact).", extra={"component": "GoogleSheetsExporter"})
            return False

        try:
            import gspread
            self.client = gspread.service_account(filename=self.credentials_path)
            logger.info("Successfully authenticated with Google Sheets API", extra={"component": "GoogleSheetsExporter"})
            return True
        except Exception as e:
            logger.error(f"Failed to authenticate with Google Sheets API: {e}", extra={"component": "GoogleSheetsExporter"})
            return False

    def export_all(self, db: DatabaseStorage) -> Dict[str, int]:
        """Export all 6 tabs from database to Google Sheets."""
        counts = {"Startups": 0, "Products": 0, "Research Papers": 0, "Jobs": 0, "News": 0, "Entity Mapping Log": 0}

        if not self.initialize_client() or not self.spreadsheet_id:
            logger.info("Google Sheets exporter running in dry-run mode (no Google API credentials)", extra={"component": "GoogleSheetsExporter"})
            return counts

        try:
            sh = self.client.open_by_key(self.spreadsheet_id)
            session = db.get_session()

            # 1. Startups
            startups = session.query(StartupModel).all()
            rows_startups = [TAB_HEADERS["Startups"]] + [
                [s.id, s.name, s.canonical_name or "", s.description or "", s.website_url or "", s.source_url, s.employee_count or "", s.founding_year or "", s.headquarters or "", s.categories_json or "[]", s.funding_stage or "", s.collected_at]
                for s in startups
            ]
            self._update_tab(sh, "Startups", rows_startups)
            counts["Startups"] = len(startups)

            # 2. Products
            products = session.query(ProductModel).all()
            rows_products = [TAB_HEADERS["Products"]] + [
                [p.id, p.name, p.canonical_name or "", p.description or "", p.product_url or "", p.source_url, p.pricing_type or "", p.pricing_details or "", p.company_name or "", p.categories_json or "[]", p.collected_at]
                for p in products
            ]
            self._update_tab(sh, "Products", rows_products)
            counts["Products"] = len(products)

            # 3. Research Papers
            papers = session.query(PaperModel).all()
            rows_papers = [TAB_HEADERS["Research Papers"]] + [
                [p.id, p.title, p.authors_json or "[]", p.paper_url, p.source_url, p.abstract or "", p.publication_date or "", p.github_repository_url or "", p.github_stars if p.github_stars is not None else "", p.source, p.collected_at]
                for p in papers
            ]
            self._update_tab(sh, "Research Papers", rows_papers)
            counts["Research Papers"] = len(papers)

            # 4. Jobs
            jobs = session.query(JobModel).all()
            rows_jobs = [TAB_HEADERS["Jobs"]] + [
                [j.id, j.company_name, j.canonical_company_name or "", j.role_title, j.job_url, j.source_url, j.location or "", str(j.is_remote), j.role_family or "", j.publication_date, str(j.freshness_verified), j.source_name, j.collected_at]
                for j in jobs
            ]
            self._update_tab(sh, "Jobs", rows_jobs)
            counts["Jobs"] = len(jobs)

            # 5. News
            news = session.query(NewsModel).all()
            rows_news = [TAB_HEADERS["News"]] + [
                [n.id, n.title, n.article_url, n.source_url, n.author or "", n.summary or "", n.publication_date, str(n.freshness_verified), n.source_name, n.collected_at]
                for n in news
            ]
            self._update_tab(sh, "News", rows_news)
            counts["News"] = len(news)

            # 6. Entity Mapping Log
            mappings = session.query(EntityMappingLogModel).all()
            rows_mappings = [TAB_HEADERS["Entity Mapping Log"]] + [
                [m.id, m.raw_name, m.canonical_name, m.match_method, m.confidence, m.source_url or "", m.timestamp]
                for m in mappings
            ]
            self._update_tab(sh, "Entity Mapping Log", rows_mappings)
            counts["Entity Mapping Log"] = len(mappings)

            session.close()
            logger.info(f"Successfully exported data to Google Sheets: {counts}", extra={"component": "GoogleSheetsExporter"})
        except Exception as e:
            logger.error(f"Error during Google Sheets export: {e}", extra={"component": "GoogleSheetsExporter"})

        return counts

    def _update_tab(self, spreadsheet: Any, tab_name: str, rows: List[List[Any]]):
        """Batch update a specific worksheet tab."""
        try:
            try:
                ws = spreadsheet.worksheet(tab_name)
            except Exception:
                ws = spreadsheet.add_worksheet(title=tab_name, rows="1000", cols="20")

            ws.clear()
            if rows:
                ws.update(rows)
        except Exception as e:
            logger.error(f"Error updating worksheet '{tab_name}': {e}", extra={"component": "GoogleSheetsExporter"})
