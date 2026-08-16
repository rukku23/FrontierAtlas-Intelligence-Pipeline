"""Integration tests for the complete FrontierAtlas pipeline execution."""
import pytest
from unittest.mock import patch
from src.main import run_pipeline
from src.storage.db import DatabaseStorage, StartupModel, ProductModel, PaperModel, JobModel, NewsModel

@pytest.mark.asyncio
async def test_full_pipeline_integration(tmp_path):
    test_db_file = tmp_path / "integration_atlas.db"
    test_db_url = f"sqlite:///{test_db_file}"

    with patch("src.storage.db.get_config") as mock_cfg, \
         patch("src.utils.config.get_config") as mock_cfg_util:
        def _mock_get(key, default=None):
            if "db_url" in key:
                return test_db_url
            return default
        mock_cfg.return_value.get.side_effect = _mock_get
        mock_cfg_util.return_value.get.side_effect = _mock_get

        db = DatabaseStorage(db_url=test_db_url)

        # Run pipeline with small limits
        metrics = await run_pipeline(
            paper_limit=2,
            startup_limit=2,
            product_limit=2,
            export_sheets=False,
            db_url=test_db_url
        )

        # Metrics must show actual discovery (not vacuously >= 0)
        assert metrics.records_discovered > 0, "Pipeline must discover at least 1 record"
        assert metrics.records_processed > 0, "Pipeline must process at least 1 record"

        # Verify tables were created and queries succeed
        session = db.get_session()
        paper_count = session.query(PaperModel).count()
        startup_count = session.query(StartupModel).count()
        product_count = session.query(ProductModel).count()
        job_count = session.query(JobModel).count()
        news_count = session.query(NewsModel).count()
        total = paper_count + startup_count + product_count + job_count + news_count
        session.close()

        # At least some records must have been persisted to the database
        assert total > 0, f"Database must contain records (papers={paper_count}, startups={startup_count}, products={product_count}, jobs={job_count}, news={news_count})"
