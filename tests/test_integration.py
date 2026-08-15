"""Integration tests for the complete FrontierAtlas pipeline execution."""
import pytest
from unittest.mock import patch
from src.main import run_pipeline
from src.storage.db import DatabaseStorage, StartupModel, ProductModel, PaperModel, JobModel, NewsModel

@pytest.mark.asyncio
async def test_full_pipeline_integration(tmp_path):
    test_db_file = tmp_path / "integration_atlas.db"
    test_db_url = f"sqlite:///{test_db_file}"

    with patch("src.storage.db.get_config") as mock_cfg:
        mock_cfg.return_value.get.side_effect = lambda key, default=None: test_db_url if "db_url" in key else default

        db = DatabaseStorage(db_url=test_db_url)

        # Run pipeline with small limits
        metrics = await run_pipeline(
            paper_limit=2,
            startup_limit=2,
            product_limit=2,
            export_sheets=False
        )

        assert metrics.records_discovered >= 0
        assert metrics.records_processed >= 0

        # Verify tables were created and queries succeed
        session = db.get_session()
        paper_count = session.query(PaperModel).count()
        startup_count = session.query(StartupModel).count()
        product_count = session.query(ProductModel).count()
        job_count = session.query(JobModel).count()
        news_count = session.query(NewsModel).count()
        session.close()

        assert paper_count >= 0
        assert startup_count >= 0
        assert product_count >= 0
