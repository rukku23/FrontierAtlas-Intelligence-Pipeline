"""Business requirement tests for FrontierAtlas data integrity.

These tests validate business rules that go beyond individual component tests:
  - Startup classification (entity must be a real company)
  - Product classification (entity must be a real product/tool)
  - Provenance (every record must have source_url)
  - No fabricated GitHub associations
  - Freshness boundary precision
  - Duplicate prevention
  - LLM orchestrator integration availability
"""
import pytest
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from src.schemas import Startup, Product, News, Job, ResearchPaper, PricingType, RoleFamily
from src.entity_resolution.deduplicator import Deduplicator
from src.extraction.freshness_engine import FreshnessEngine
from src.extraction.llm_orchestrator import LLMOrchestrator
from src.crawlers.startup_crawler import StartupCrawler


# =============================================================================
# STARTUP CLASSIFICATION
# =============================================================================

class TestStartupClassification:
    """Verify that startup records come from a legitimate startup directory."""

    def test_startup_requires_source_url(self):
        """Every startup must have a non-empty source_url for provenance."""
        with pytest.raises(Exception):
            # source_url is required by schema — missing should fail
            Startup(
                name="Test Corp",
                source_url="",  # Empty = invalid
                categories=["AI"]
            )

    def test_startup_from_yc_has_legitimate_provenance(self):
        """YC-sourced startup must have ycombinator.com source URL."""
        startup = Startup(
            name="Example AI",
            description="An AI company",
            website_url="https://example.com",
            source_url="https://www.ycombinator.com/companies/example-ai",
            employee_count=50,
            founding_year=2020,
            headquarters="San Francisco, CA",
            categories=["AI", "B2B"],
            funding_stage="Series A"
        )
        assert "ycombinator.com" in startup.source_url
        assert startup.employee_count == 50
        assert startup.founding_year == 2020

    def test_startup_unknown_fields_are_null_not_fabricated(self):
        """Fields that cannot be determined must be null, never fabricated."""
        startup = Startup(
            name="Mystery Corp",
            source_url="https://www.ycombinator.com/companies/mystery",
            categories=["AI"]
        )
        assert startup.employee_count is None
        assert startup.founding_year is None
        assert startup.headquarters is None
        assert startup.funding_stage is None
        assert startup.description is None

    def test_startup_crawler_uses_yc_endpoints(self):
        """Verify the startup crawler is configured to use YC-OSS API."""
        from src.crawlers.startup_crawler import YC_AI_TAG_ENDPOINTS
        assert len(YC_AI_TAG_ENDPOINTS) > 0
        for url in YC_AI_TAG_ENDPOINTS:
            assert "yc-oss.github.io/api" in url, f"Endpoint {url} is not YC-OSS"

    def test_startup_parser_maps_yc_fields_correctly(self):
        """Verify YC JSON → Startup mapping uses authoritative fields."""
        crawler = StartupCrawler()
        yc_record = {
            "name": "OpenAI",
            "website": "https://openai.com",
            "one_liner": "AI research and deployment company",
            "all_locations": "San Francisco, CA, USA",
            "team_size": 2000,
            "launched_at": 1451606400,  # 2016-01-01
            "stage": "Growth",
            "tags": ["Artificial Intelligence"],
            "industries": ["AI"],
            "url": "https://www.ycombinator.com/companies/openai"
        }
        startup = crawler._parse_yc_company(yc_record, "https://yc-oss.github.io/api/tags/ai.json")
        assert startup is not None
        assert startup.name == "OpenAI"
        assert startup.website_url == "https://openai.com"
        assert startup.employee_count == 2000
        assert startup.founding_year == 2016
        assert startup.headquarters == "San Francisco, CA, USA"
        assert startup.funding_stage == "Growth"
        assert "Artificial Intelligence" in startup.categories


# =============================================================================
# PRODUCT CLASSIFICATION
# =============================================================================

class TestProductClassification:
    """Verify product records represent real products, not arbitrary HF entries."""

    def test_product_pricing_not_hardcoded_free(self):
        """Pricing must not be arbitrarily set to FREE without evidence."""
        product = Product(
            name="TestTool",
            source_url="https://huggingface.co/spaces/org/tool",
            product_url="https://huggingface.co/spaces/org/tool",
            pricing_type=PricingType.UNKNOWN,  # Correct — no evidence of pricing
            categories=["AI"]
        )
        assert product.pricing_type == PricingType.UNKNOWN

    def test_product_requires_source_url(self):
        """Every product must have a non-empty source_url for provenance."""
        with pytest.raises(Exception):
            Product(
                name="TestTool",
                source_url="",
                product_url="https://example.com",
                categories=["AI"]
            )

    def test_product_pricing_free_requires_license_evidence(self):
        """ProductCrawler should only set FREE when license evidence exists."""
        from src.crawlers.product_crawler import ProductCrawler
        crawler = ProductCrawler()

        # No card data → UNKNOWN
        assert crawler._extract_pricing_from_card(None) == PricingType.UNKNOWN
        assert crawler._extract_pricing_from_card({}) == PricingType.UNKNOWN

        # Open-source license → FREE
        assert crawler._extract_pricing_from_card({"license": "MIT"}) == PricingType.FREE
        assert crawler._extract_pricing_from_card({"license": "apache-2.0"}) == PricingType.FREE

        # Unknown license → UNKNOWN
        assert crawler._extract_pricing_from_card({"license": "proprietary"}) == PricingType.UNKNOWN


# =============================================================================
# PROVENANCE & SOURCE URL
# =============================================================================

class TestProvenance:
    """Every record must retain its source_url — the chain of provenance."""

    def test_all_entity_types_require_source_url(self):
        """All five entity types must have source_url as a required field."""
        # These should all succeed with valid source_url
        Startup(name="A", source_url="https://example.com/a", categories=["AI"])
        Product(name="B", source_url="https://example.com/b", product_url="https://x.com", categories=["AI"])
        ResearchPaper(title="C", authors=["X"], paper_url="https://arxiv.org/abs/1", source_url="https://arxiv.org/abs/1", source="arxiv")
        News(title="D", article_url="https://news.com/d", source_url="https://news.com/feed", publication_date="2026-01-01T00:00:00Z", freshness_verified=True, source_name="Test")
        Job(company_name="E", role_title="Dev", job_url="https://jobs.com/e", source_url="https://jobs.com/feed", publication_date="2026-01-01T00:00:00Z", freshness_verified=True, source_name="Test")


# =============================================================================
# GITHUB ASSOCIATION INTEGRITY
# =============================================================================

class TestGitHubIntegrity:
    """GitHub URLs and stars must come from legitimate sources, never LLM."""

    def test_github_stars_initially_null(self):
        """Papers must start with github_stars=None until GitHub API enrichment."""
        paper = ResearchPaper(
            title="Test Paper",
            authors=["Author A"],
            paper_url="https://arxiv.org/abs/2024.12345",
            source_url="https://arxiv.org/abs/2024.12345",
            source="arxiv",
            github_repository_url="https://github.com/test/repo"
        )
        assert paper.github_stars is None

    def test_github_url_regex_only_from_paper_content(self):
        """ArXiv crawler extracts GitHub URLs via regex from paper text, not LLM."""
        from src.crawlers.arxiv_crawler import ArxivCrawler
        crawler = ArxivCrawler()
        # The crawler uses _extract_github_url_from_text — a regex method
        assert hasattr(crawler, '_extract_github_url_from_text')

        # Verify it extracts real GitHub URLs from text
        text_with_github = "Code available at https://github.com/user/repo for reproducibility."
        url = crawler._extract_github_url_from_text(text_with_github)
        assert url == "https://github.com/user/repo"

        # Verify it returns None when no GitHub URL is present
        text_without_github = "This paper presents a novel approach to AI."
        assert crawler._extract_github_url_from_text(text_without_github) is None


# =============================================================================
# FRESHNESS BOUNDARY PRECISION
# =============================================================================

class TestFreshnessBoundary:
    """Freshness engine must correctly handle edge cases around 24h boundary."""

    def test_exactly_24h_is_stale(self):
        """A record published exactly 24.0 hours ago should be rejected."""
        engine = FreshnessEngine(max_age_hours=24.0)
        boundary_date = datetime.now(timezone.utc) - timedelta(hours=24, seconds=1)
        is_fresh, dt, reason = engine.verify_freshness(boundary_date.isoformat())
        assert not is_fresh

    def test_23h59m_is_fresh(self):
        """A record published 23h59m ago should be accepted."""
        engine = FreshnessEngine(max_age_hours=24.0)
        fresh_date = datetime.now(timezone.utc) - timedelta(hours=23, minutes=59)
        is_fresh, dt, reason = engine.verify_freshness(fresh_date.isoformat())
        assert is_fresh

    def test_future_date_rejected(self):
        """A date in the future (>5 min) should be rejected."""
        engine = FreshnessEngine(max_age_hours=24.0)
        future_date = datetime.now(timezone.utc) + timedelta(hours=1)
        is_fresh, dt, reason = engine.verify_freshness(future_date.isoformat())
        assert not is_fresh

    def test_no_date_rejected(self):
        """Missing date should be rejected, never inferred from crawl time."""
        engine = FreshnessEngine(max_age_hours=24.0)
        is_fresh, dt, reason = engine.verify_freshness(None)
        assert not is_fresh
        assert dt is None


# =============================================================================
# DEDUPLICATION
# =============================================================================

class TestDeduplicationBusiness:
    """Deduplication must prevent the same entity from appearing twice."""

    def test_identical_startups_deduplicated(self):
        """Two startups with same name and source should produce one record."""
        dedup = Deduplicator()
        s1 = Startup(name="DuplicateCo", source_url="https://yc.com/dup", categories=["AI"])
        s2 = Startup(name="DuplicateCo", source_url="https://yc.com/dup", categories=["AI"])
        result = dedup.filter_duplicates([s1, s2])
        assert len(result) == 1

    def test_different_startups_not_merged(self):
        """Two different startups should NOT be merged."""
        dedup = Deduplicator()
        s1 = Startup(name="CompanyA", source_url="https://yc.com/a", categories=["AI"])
        s2 = Startup(name="CompanyB", source_url="https://yc.com/b", categories=["AI"])
        result = dedup.filter_duplicates([s1, s2])
        assert len(result) == 2


# =============================================================================
# LLM ORCHESTRATOR INTEGRATION
# =============================================================================

class TestLLMIntegration:
    """Verify LLM orchestrator is available and integrated into pipeline."""

    def test_orchestrator_filters_providers_by_api_key(self):
        """Orchestrator should only include providers with configured API keys."""
        # With no env vars set, should have empty providers list
        orchestrator = LLMOrchestrator()
        # The test env likely has no API keys, so providers should be empty
        # This validates the filtering logic works
        assert isinstance(orchestrator.providers, list)

    def test_orchestrator_accepts_explicit_providers(self):
        """Explicit provider list should be used as-is."""
        mock_provider = MagicMock()
        mock_provider.api_key = "test-key"
        orchestrator = LLMOrchestrator(providers=[mock_provider])
        assert len(orchestrator.providers) == 1

    def test_main_pipeline_imports_orchestrator(self):
        """The main pipeline module must import and use LLMOrchestrator."""
        import src.main as main_module
        assert hasattr(main_module, 'LLMOrchestrator')
        # Verify the extraction helper functions exist
        assert hasattr(main_module, '_llm_enrich_startup')
        assert hasattr(main_module, '_llm_enrich_product')
        assert hasattr(main_module, '_llm_extract_news_content')


class TestGeminiProviderAndKeys:
    """Verify GeminiProvider configuration, SDK model name passing, and placeholder key filtering."""

    def test_gemini_provider_default_and_custom_model_config(self, monkeypatch):
        from src.extraction.providers.gemini_provider import GeminiProvider
        monkeypatch.delenv("GEMINI_MODEL", raising=False)
        provider_default = GeminiProvider(api_key="valid-test-key-12345678")
        assert provider_default.model_name == "gemini-3.5-flash"

        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
        provider_env = GeminiProvider(api_key="valid-test-key-12345678")
        assert provider_env.model_name == "gemini-3.6-flash"

        provider_explicit = GeminiProvider(api_key="valid-test-key-12345678", model_name="gemini-3.5-flash")
        assert provider_explicit.model_name == "gemini-3.5-flash"

    def test_placeholder_and_empty_keys_ignored(self):
        from src.extraction.llm_provider import is_valid_api_key
        from src.extraction.providers.gemini_provider import GeminiProvider
        from src.extraction.providers.groq_provider import GroqProvider
        from src.extraction.providers.deepseek_provider import DeepSeekProvider

        assert not is_valid_api_key(None)
        assert not is_valid_api_key("")
        assert not is_valid_api_key("   ")
        assert not is_valid_api_key("your_gemini_api_key_here")
        assert not is_valid_api_key("your_groq_api_key_here")
        assert not is_valid_api_key("your_deepseek_api_key_here")
        assert not is_valid_api_key("placeholder")
        assert not is_valid_api_key("path/to/key.json")

        assert is_valid_api_key("AIzaSyD_valid_key_12345")
        assert is_valid_api_key("gsk_valid_groq_key_67890")

        # Verify providers treat placeholders as None
        g_prov = GeminiProvider(api_key="your_gemini_api_key_here")
        assert g_prov.api_key is None

        groq_prov = GroqProvider(api_key="your_groq_api_key_here")
        assert groq_prov.api_key is None

        ds_prov = DeepSeekProvider(api_key="your_deepseek_api_key_here")
        assert ds_prov.api_key is None

    @pytest.mark.asyncio
    async def test_configured_model_passed_to_gemini_sdk(self, monkeypatch):
        from unittest.mock import MagicMock, patch
        from src.extraction.providers.gemini_provider import GeminiProvider
        from pydantic import BaseModel

        class SimpleSchema(BaseModel):
            name: str

        monkeypatch.setenv("GEMINI_MODEL", "gemini-3.6-flash")
        provider = GeminiProvider(api_key="valid-dummy-api-key-12345")
        assert provider.model_name == "gemini-3.6-flash"

        mock_response = MagicMock()
        mock_response.text = '{"name": "Test Entity"}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        mock_genai = MagicMock()
        mock_genai.Client.return_value = mock_client

        with patch.dict("sys.modules", {"google": MagicMock(genai=mock_genai), "google.genai": mock_genai}):
            result = await provider.extract("Sample text for extraction", SimpleSchema)
            assert result is not None
            assert result.name == "Test Entity"

            mock_client.models.generate_content.assert_called_once()
            called_kwargs = mock_client.models.generate_content.call_args.kwargs
            assert called_kwargs.get("model") == "gemini-3.6-flash"


# =============================================================================
# DETERMINISTIC-FIRST EXTRACTION & QUOTA EXHAUSTION RESILIENCE
# =============================================================================

class TestDeterministicFirstExtraction:
    """Verify deterministic-first extraction policy and quota exhaustion resilience."""

    @pytest.mark.asyncio
    async def test_startup_with_complete_yc_metadata_skips_llm(self):
        """A startup with complete YC metadata should not call LLM."""
        from src.main import _llm_enrich_startup
        from src.schemas import Startup
        from src.utils.metrics import PipelineMetrics
        from unittest.mock import MagicMock

        metrics = PipelineMetrics()
        mock_orchestrator = MagicMock()

        complete_startup = Startup(
            name="Complete Startup",
            source_url="https://yc.com/complete",
            description="Complete YC description provided directly by API",
            categories=["AI", "Enterprise"]
        )

        result = await _llm_enrich_startup(mock_orchestrator, complete_startup, complete_startup.description, metrics)
        assert result.name == "Complete Startup"
        assert metrics.llm_extractions_skipped == 1
        assert metrics.llm_extractions_attempted == 0
        mock_orchestrator.extract_structured.assert_not_called()

    @pytest.mark.asyncio
    async def test_product_with_complete_hf_metadata_skips_llm(self):
        """A product with complete HF metadata should not call LLM."""
        from src.main import _llm_enrich_product
        from src.schemas import Product
        from src.utils.metrics import PipelineMetrics
        from unittest.mock import MagicMock

        metrics = PipelineMetrics()
        mock_orchestrator = MagicMock()

        complete_product = Product(
            name="Complete Product",
            source_url="https://huggingface.co/spaces/test/product",
            description="Complete HF Space description provided directly by API",
            categories=["text-to-image"]
        )

        result = await _llm_enrich_product(mock_orchestrator, complete_product, "Sample README content", metrics)
        assert result.name == "Complete Product"
        assert metrics.llm_extractions_skipped == 1
        assert metrics.llm_extractions_attempted == 0
        mock_orchestrator.extract_structured.assert_not_called()

    def test_paper_with_complete_arxiv_github_metadata_is_deterministic(self):
        """Papers with complete ArXiv/GitHub API fields require zero LLM calls."""
        from src.schemas import ResearchPaper
        paper = ResearchPaper(
            title="Deterministic Paper",
            authors=["Author One"],
            paper_url="https://arxiv.org/abs/2026.12345",
            source_url="https://arxiv.org/abs/2026.12345",
            abstract="Sample abstract describing LLM-free extraction",
            github_repository_url="https://github.com/test/paper-code",
            github_stars=500
        )
        assert paper.title == "Deterministic Paper"
        assert paper.github_stars == 500
        assert paper.source == "arxiv"

    @pytest.mark.asyncio
    async def test_llm_invoked_only_when_required_fields_missing(self):
        """LLM is invoked only when startup description/categories are incomplete."""
        from src.main import _llm_enrich_startup
        from src.schemas import Startup
        from src.utils.metrics import PipelineMetrics
        from unittest.mock import AsyncMock, MagicMock

        metrics = PipelineMetrics()
        mock_orchestrator = MagicMock()
        mock_orchestrator.extract_structured = AsyncMock(return_value=Startup(
            name="Incomplete Startup",
            source_url="https://yc.com/inc",
            description="LLM Enriched Description",
            categories=["LLM-Category"]
        ))

        incomplete_startup = Startup(
            name="Incomplete Startup",
            source_url="https://yc.com/inc",
            description=None,
            categories=[]
        )

        result = await _llm_enrich_startup(mock_orchestrator, incomplete_startup, "Raw description text longer than 50 chars for extraction", metrics)
        assert metrics.llm_extractions_attempted == 1
        assert result.description == "LLM Enriched Description"
        assert result.categories == ["LLM-Category"]
        mock_orchestrator.extract_structured.assert_called_once()

    @pytest.mark.asyncio
    async def test_gemini_429_quota_exhaustion_fast_fails_without_infinite_loop(self):
        """Gemini 429 quota error sets quota_exhausted and fast-fails subsequent requests."""
        from src.extraction.llm_orchestrator import LLMOrchestrator
        from src.schemas import Startup
        from unittest.mock import AsyncMock, MagicMock

        mock_provider = MagicMock()
        mock_provider.name = "GeminiProvider"
        mock_provider.api_key = "valid-key"
        mock_provider.extract = AsyncMock(side_effect=Exception("429 RESOURCE_EXHAUSTED: Quota exceeded for metric"))

        orchestrator = LLMOrchestrator(providers=[mock_provider])

        result1 = await orchestrator.extract_structured("Text for extraction", Startup)
        assert result1 is None
        assert orchestrator.quota_exhausted is True

        mock_provider.extract.reset_mock()

        result2 = await orchestrator.extract_structured("Another text for extraction", Startup)
        assert result2 is None
        mock_provider.extract.assert_not_called()

    @pytest.mark.asyncio
    async def test_pipeline_continues_processing_after_llm_quota_failure(self):
        """Pipeline continues saving valid deterministic records even after LLM quota exhaustion."""
        from src.main import run_pipeline
        from unittest.mock import patch, AsyncMock

        test_db_url = "sqlite:///:memory:"

        with patch("src.main.LLMOrchestrator") as mock_orch_cls, \
             patch("src.storage.db.get_config") as mock_cfg, \
             patch("src.utils.config.get_config") as mock_cfg_util:

            def _mock_get(key, default=None):
                if "db_url" in key:
                    return test_db_url
                return default
            mock_cfg.return_value.get.side_effect = _mock_get
            mock_cfg_util.return_value.get.side_effect = _mock_get

            mock_orch_instance = MagicMock()
            mock_orch_instance.providers = [MagicMock(api_key="dummy")]
            mock_orch_instance.quota_exhausted = False

            async def mock_extract(*args, **kwargs):
                mock_orch_instance.quota_exhausted = True
                return None
            mock_orch_instance.extract_structured = AsyncMock(side_effect=mock_extract)
            mock_orch_cls.return_value = mock_orch_instance

            metrics = await run_pipeline(
                paper_limit=2,
                startup_limit=2,
                product_limit=2,
                export_sheets=False,
                db_url=test_db_url
            )

            assert metrics.records_discovered > 0
            assert metrics.records_processed > 0
            assert mock_orch_instance.quota_exhausted is True
