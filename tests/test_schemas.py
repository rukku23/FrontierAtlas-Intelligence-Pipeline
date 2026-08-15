"""Unit tests for Pydantic schemas."""
import pytest
from pydantic import ValidationError
from src.schemas import Startup, Product, ResearchPaper, Job, News, PricingType, RoleFamily, RecordType

def test_startup_schema_valid():
    startup = Startup(
        name="Anthropic",
        source_url="https://example.com/startups/anthropic",
        description="AI Safety and Research Company",
        founding_year=2021,
        employee_count=500
    )
    assert startup.name == "Anthropic"
    assert startup.record_type == RecordType.STARTUP
    assert startup.source_url == "https://example.com/startups/anthropic"
    assert startup.id is not None
    assert startup.collected_at is not None

def test_startup_schema_invalid_url():
    with pytest.raises(ValidationError):
        Startup(name="Invalid", source_url="not_a_url")

def test_product_schema_valid():
    product = Product(
        name="Claude 3.5 Sonnet",
        source_url="https://example.com/products/claude",
        pricing_type=PricingType.FREEMIUM,
        company_name="Anthropic"
    )
    assert product.name == "Claude 3.5 Sonnet"
    assert product.pricing_type == PricingType.FREEMIUM

def test_research_paper_schema_valid():
    paper = ResearchPaper(
        title="Attention Is All You Need",
        authors=["Ashish Vaswani", "Noam Shazeer"],
        paper_url="https://arxiv.org/abs/1706.03762",
        source_url="https://arxiv.org/abs/1706.03762",
        github_repository_url="https://github.com/tensorflow/tensor2tensor",
        github_stars=12500,
        source="arxiv"
    )
    assert paper.title == "Attention Is All You Need"
    assert paper.github_stars == 12500

def test_job_schema_valid():
    job = Job(
        company_name="OpenAI",
        role_title="Member of Technical Staff",
        job_url="https://example.com/jobs/123",
        source_url="https://example.com/jobs",
        source_name="Example Job Board",
        publication_date="2026-08-15T10:00:00Z",
        freshness_verified=True,
        role_family=RoleFamily.ENGINEERING
    )
    assert job.company_name == "OpenAI"
    assert job.freshness_verified is True

def test_news_schema_valid():
    news = News(
        title="New Model Released",
        article_url="https://example.com/news/new-model",
        source_url="https://example.com/news",
        source_name="AI News Daily",
        publication_date="2026-08-15T11:00:00Z",
        freshness_verified=True
    )
    assert news.title == "New Model Released"
    assert news.freshness_verified is True
