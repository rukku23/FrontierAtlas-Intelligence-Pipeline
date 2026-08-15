"""Canonical Pydantic v2 schemas for FrontierAtlas entity types."""
from datetime import datetime, timezone
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field, HttpUrl, field_validator
from src.schemas.enums import PricingType, RoleFamily, RecordType

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def generate_id() -> str:
    return str(uuid.uuid4())

class BaseEntity(BaseModel):
    id: str = Field(default_factory=generate_id)
    source_url: str = Field(..., description="Legitimate origin URL for provenance")
    collected_at: str = Field(default_factory=utc_now_iso, description="ISO-8601 UTC timestamp when collected")

    @field_validator("source_url")
    def validate_source_url(cls, v: str) -> str:
        if not v or not v.startswith(("http://", "https://")):
            raise ValueError("source_url must be a valid HTTP/HTTPS URL")
        return v

class Startup(BaseEntity):
    record_type: RecordType = RecordType.STARTUP
    name: str = Field(..., min_length=1, description="Company/Startup name")
    canonical_name: Optional[str] = None
    description: Optional[str] = None
    website_url: Optional[str] = None
    employee_count: Optional[int] = Field(default=None, ge=0, description="Real employee count if known")
    founding_year: Optional[int] = Field(default=None, ge=1800, le=2026)
    headquarters: Optional[str] = None
    categories: List[str] = Field(default_factory=list)
    funding_stage: Optional[str] = None

class Product(BaseEntity):
    record_type: RecordType = RecordType.PRODUCT
    name: str = Field(..., min_length=1, description="Product name")
    canonical_name: Optional[str] = None
    description: Optional[str] = None
    product_url: Optional[str] = None
    pricing_type: Optional[PricingType] = PricingType.UNKNOWN
    pricing_details: Optional[str] = None
    company_name: Optional[str] = None
    categories: List[str] = Field(default_factory=list)

class ResearchPaper(BaseEntity):
    record_type: RecordType = RecordType.RESEARCH_PAPER
    title: str = Field(..., min_length=1, description="Paper title")
    authors: List[str] = Field(default_factory=list)
    paper_url: str = Field(..., description="Paper landing or PDF URL")
    abstract: Optional[str] = None
    publication_date: Optional[str] = None
    github_repository_url: Optional[str] = Field(default=None, description="GitHub URL from legitimate source association")
    github_stars: Optional[int] = Field(default=None, ge=0, description="Verified GitHub star count directly from GitHub API")
    source: str = Field(default="arxiv", description="Source repository name")

    @field_validator("paper_url")
    def validate_paper_url(cls, v: str) -> str:
        if not v or not v.startswith(("http://", "https://")):
            raise ValueError("paper_url must be a valid HTTP/HTTPS URL")
        return v

class Job(BaseEntity):
    record_type: RecordType = RecordType.JOB
    company_name: str = Field(..., min_length=1)
    canonical_company_name: Optional[str] = None
    role_title: str = Field(..., min_length=1)
    job_url: str = Field(...)
    location: Optional[str] = None
    is_remote: Optional[bool] = None
    role_family: Optional[RoleFamily] = RoleFamily.OTHER
    description: Optional[str] = None
    publication_date: str = Field(..., description="Verified publication timestamp")
    freshness_verified: bool = Field(default=False, description="Must be true for acceptance (<= 24h)")
    source_name: str = Field(..., min_length=1)

class News(BaseEntity):
    record_type: RecordType = RecordType.NEWS
    title: str = Field(..., min_length=1)
    article_url: str = Field(...)
    author: Optional[str] = None
    summary: Optional[str] = None
    content: Optional[str] = None
    publication_date: str = Field(..., description="Verified publication timestamp")
    freshness_verified: bool = Field(default=False, description="Must be true for acceptance (<= 24h)")
    source_name: str = Field(..., min_length=1)
