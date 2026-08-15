"""SQLAlchemy Database ORM and Storage Manager for SQLite / PostgreSQL portability."""
import json
import os
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from sqlalchemy import (
    create_engine, Column, String, Integer, Float, Boolean, Text, DateTime, Index
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from src.schemas import Startup, Product, ResearchPaper, Job, News
from src.entity_resolution.entity_resolver import EntityResolutionResult
from src.entity_resolution.deduplicator import Deduplicator
from src.utils.logger import logger
from src.utils.config import get_config

Base = declarative_base()

class StartupModel(Base):
    __tablename__ = "startups"

    id = Column(String(64), primary_key=True)
    dedup_key = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False, index=True)
    canonical_name = Column(String(255), index=True)
    description = Column(Text)
    website_url = Column(String(512))
    source_url = Column(String(512), nullable=False)
    employee_count = Column(Integer)
    founding_year = Column(Integer)
    headquarters = Column(String(255))
    categories_json = Column(Text)
    funding_stage = Column(String(100))
    collected_at = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class ProductModel(Base):
    __tablename__ = "products"

    id = Column(String(64), primary_key=True)
    dedup_key = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(255), nullable=False, index=True)
    canonical_name = Column(String(255), index=True)
    description = Column(Text)
    product_url = Column(String(512))
    source_url = Column(String(512), nullable=False)
    pricing_type = Column(String(50))
    pricing_details = Column(Text)
    company_name = Column(String(255))
    categories_json = Column(Text)
    collected_at = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class PaperModel(Base):
    __tablename__ = "research_papers"

    id = Column(String(64), primary_key=True)
    dedup_key = Column(String(64), unique=True, index=True, nullable=False)
    title = Column(String(512), nullable=False, index=True)
    authors_json = Column(Text)
    paper_url = Column(String(512), nullable=False)
    source_url = Column(String(512), nullable=False)
    abstract = Column(Text)
    publication_date = Column(String(64))
    github_repository_url = Column(String(512))
    github_stars = Column(Integer)
    source = Column(String(100), default="arxiv")
    collected_at = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String(64), primary_key=True)
    dedup_key = Column(String(64), unique=True, index=True, nullable=False)
    company_name = Column(String(255), nullable=False, index=True)
    canonical_company_name = Column(String(255))
    role_title = Column(String(255), nullable=False)
    job_url = Column(String(512), nullable=False)
    source_url = Column(String(512), nullable=False)
    location = Column(String(255))
    is_remote = Column(Boolean, default=True)
    role_family = Column(String(100))
    description = Column(Text)
    publication_date = Column(String(64), nullable=False)
    freshness_verified = Column(Boolean, default=True)
    source_name = Column(String(100), nullable=False)
    collected_at = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class NewsModel(Base):
    __tablename__ = "news"

    id = Column(String(64), primary_key=True)
    dedup_key = Column(String(64), unique=True, index=True, nullable=False)
    title = Column(String(512), nullable=False, index=True)
    article_url = Column(String(512), nullable=False)
    source_url = Column(String(512), nullable=False)
    author = Column(String(255))
    summary = Column(Text)
    content = Column(Text)
    publication_date = Column(String(64), nullable=False)
    freshness_verified = Column(Boolean, default=True)
    source_name = Column(String(100), nullable=False)
    collected_at = Column(String(64), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

class EntityMappingLogModel(Base):
    __tablename__ = "entity_mapping_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    raw_name = Column(String(255), nullable=False, index=True)
    canonical_name = Column(String(255), nullable=False, index=True)
    match_method = Column(String(50), nullable=False)
    confidence = Column(Float, nullable=False)
    source_url = Column(String(512))
    timestamp = Column(String(64), nullable=False)

class CrawlAttemptModel(Base):
    __tablename__ = "crawl_attempts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    url = Column(String(512), nullable=False, index=True)
    status_code = Column(Integer)
    retry_count = Column(Integer, default=0)
    latency_ms = Column(Float)
    error = Column(Text)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class DatabaseStorage:
    """Storage manager interacting with SQLite/SQLAlchemy database."""

    def __init__(self, db_url: Optional[str] = None):
        cfg = get_config()
        self.db_url = db_url or os.getenv("DATABASE_URL") or cfg.get("pipeline.db_url", "sqlite:///data/frontier_atlas.db")
        
        # Ensure database parent directory exists for SQLite
        if self.db_url.startswith("sqlite:///"):
            db_path = self.db_url.replace("sqlite:///", "")
            os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)

        self.engine = create_engine(self.db_url, echo=False, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        self.init_db()

    def init_db(self):
        """Create all tables if they do not exist."""
        Base.metadata.create_all(bind=self.engine)
        logger.info(f"Initialized database schema at {self.db_url}", extra={"component": "DatabaseStorage"})

    def get_session(self) -> Session:
        return self.SessionLocal()

    def save_startups(self, startups: List[Startup]) -> int:
        session = self.get_session()
        saved_count = 0
        try:
            for s in startups:
                dedup_key = Deduplicator.compute_key(s)
                if not session.query(StartupModel).filter_by(dedup_key=dedup_key).first():
                    model = StartupModel(
                        id=s.id,
                        dedup_key=dedup_key,
                        name=s.name,
                        canonical_name=s.canonical_name,
                        description=s.description,
                        website_url=s.website_url,
                        source_url=s.source_url,
                        employee_count=s.employee_count,
                        founding_year=s.founding_year,
                        headquarters=s.headquarters,
                        categories_json=json.dumps(s.categories),
                        funding_stage=s.funding_stage,
                        collected_at=s.collected_at
                    )
                    session.add(model)
                    saved_count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving startups: {e}", extra={"component": "DatabaseStorage"})
        finally:
            session.close()
        return saved_count

    def save_products(self, products: List[Product]) -> int:
        session = self.get_session()
        saved_count = 0
        try:
            for p in products:
                dedup_key = Deduplicator.compute_key(p)
                if not session.query(ProductModel).filter_by(dedup_key=dedup_key).first():
                    model = ProductModel(
                        id=p.id,
                        dedup_key=dedup_key,
                        name=p.name,
                        canonical_name=p.canonical_name,
                        description=p.description,
                        product_url=p.product_url,
                        source_url=p.source_url,
                        pricing_type=p.pricing_type.value if p.pricing_type else None,
                        pricing_details=p.pricing_details,
                        company_name=p.company_name,
                        categories_json=json.dumps(p.categories),
                        collected_at=p.collected_at
                    )
                    session.add(model)
                    saved_count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving products: {e}", extra={"component": "DatabaseStorage"})
        finally:
            session.close()
        return saved_count

    def save_papers(self, papers: List[ResearchPaper]) -> int:
        session = self.get_session()
        saved_count = 0
        try:
            for p in papers:
                dedup_key = Deduplicator.compute_key(p)
                if not session.query(PaperModel).filter_by(dedup_key=dedup_key).first():
                    model = PaperModel(
                        id=p.id,
                        dedup_key=dedup_key,
                        title=p.title,
                        authors_json=json.dumps(p.authors),
                        paper_url=p.paper_url,
                        source_url=p.source_url,
                        abstract=p.abstract,
                        publication_date=p.publication_date,
                        github_repository_url=p.github_repository_url,
                        github_stars=p.github_stars,
                        source=p.source,
                        collected_at=p.collected_at
                    )
                    session.add(model)
                    saved_count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving papers: {e}", extra={"component": "DatabaseStorage"})
        finally:
            session.close()
        return saved_count

    def save_jobs(self, jobs: List[Job]) -> int:
        session = self.get_session()
        saved_count = 0
        try:
            for j in jobs:
                dedup_key = Deduplicator.compute_key(j)
                if not session.query(JobModel).filter_by(dedup_key=dedup_key).first():
                    model = JobModel(
                        id=j.id,
                        dedup_key=dedup_key,
                        company_name=j.company_name,
                        canonical_company_name=j.canonical_company_name,
                        role_title=j.role_title,
                        job_url=j.job_url,
                        source_url=j.source_url,
                        location=j.location,
                        is_remote=j.is_remote,
                        role_family=j.role_family.value if j.role_family else None,
                        description=j.description,
                        publication_date=j.publication_date,
                        freshness_verified=j.freshness_verified,
                        source_name=j.source_name,
                        collected_at=j.collected_at
                    )
                    session.add(model)
                    saved_count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving jobs: {e}", extra={"component": "DatabaseStorage"})
        finally:
            session.close()
        return saved_count

    def save_news(self, news_items: List[News]) -> int:
        session = self.get_session()
        saved_count = 0
        try:
            for n in news_items:
                dedup_key = Deduplicator.compute_key(n)
                if not session.query(NewsModel).filter_by(dedup_key=dedup_key).first():
                    model = NewsModel(
                        id=n.id,
                        dedup_key=dedup_key,
                        title=n.title,
                        article_url=n.article_url,
                        source_url=n.source_url,
                        author=n.author,
                        summary=n.summary,
                        content=n.content,
                        publication_date=n.publication_date,
                        freshness_verified=n.freshness_verified,
                        source_name=n.source_name,
                        collected_at=n.collected_at
                    )
                    session.add(model)
                    saved_count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving news: {e}", extra={"component": "DatabaseStorage"})
        finally:
            session.close()
        return saved_count

    def save_entity_mappings(self, logs: List[EntityResolutionResult]) -> int:
        session = self.get_session()
        saved_count = 0
        try:
            for log in logs:
                model = EntityMappingLogModel(
                    raw_name=log.raw_name,
                    canonical_name=log.canonical_name,
                    match_method=log.match_method,
                    confidence=log.confidence,
                    source_url=log.source_url,
                    timestamp=log.timestamp
                )
                session.add(model)
                saved_count += 1
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving entity mapping logs: {e}", extra={"component": "DatabaseStorage"})
        finally:
            session.close()
        return saved_count
