"""Unit tests for DatabaseStorage and GoogleSheetsExporter."""
import pytest
import os
from src.storage.db import DatabaseStorage
from src.storage.sheets_sync import GoogleSheetsExporter, TAB_HEADERS
from src.schemas import Startup, Product, ResearchPaper, Job, News, PricingType, RoleFamily
from src.entity_resolution.entity_resolver import EntityResolutionResult

@pytest.fixture
def temp_db(tmp_path):
    db_file = tmp_path / "test_atlas.db"
    db_url = f"sqlite:///{db_file}"
    return DatabaseStorage(db_url=db_url)

def test_db_save_and_retrieve_startups(temp_db):
    s1 = Startup(
        name="Anthropic",
        website_url="https://anthropic.com",
        source_url="https://example.com/startups/anthropic",
        employee_count=500
    )
    # Save once
    saved_first = temp_db.save_startups([s1])
    assert saved_first == 1

    # Save duplicate -> should not double insert (idempotency)
    saved_second = temp_db.save_startups([s1])
    assert saved_second == 0

def test_db_save_all_entities(temp_db):
    startup = Startup(name="OpenAI", source_url="https://example.com/s1")
    product = Product(name="GPT-4o", source_url="https://example.com/p1", pricing_type=PricingType.FREEMIUM)
    paper = ResearchPaper(title="Attention Is All You Need", paper_url="https://arxiv.org/abs/1706.03762", source_url="https://arxiv.org/abs/1706.03762")
    job = Job(company_name="Meta", role_title="AI Engineer", job_url="https://example.com/j1", source_url="https://example.com/j1", source_name="Test", publication_date="2026-08-15T10:00:00Z", freshness_verified=True)
    news = News(title="Breakthrough", article_url="https://example.com/n1", source_url="https://example.com/n1", source_name="Test", publication_date="2026-08-15T10:00:00Z", freshness_verified=True)

    assert temp_db.save_startups([startup]) == 1
    assert temp_db.save_products([product]) == 1
    assert temp_db.save_papers([paper]) == 1
    assert temp_db.save_jobs([job]) == 1
    assert temp_db.save_news([news]) == 1

def test_google_sheets_exporter_dry_run(temp_db):
    exporter = GoogleSheetsExporter()
    counts = exporter.export_all(temp_db)
    assert isinstance(counts, dict)
    assert len(counts) == 6
    assert "Startups" in counts
    assert "Entity Mapping Log" in counts
    assert TAB_HEADERS["Startups"][0] == "ID"
