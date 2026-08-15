# FrontierAtlas — AI & Venture Intelligence Pipeline

FrontierAtlas is an asynchronous, fault-tolerant data ingestion pipeline that converts unstructured web content — startup directories, product listings, research-paper repositories, AI news sites, and job boards — into a canonical, schema-validated intelligence graph.

It acquires real AI ecosystem entities across five domain verticals:
1. **Startups**: AI companies, funding stages, founding metadata, categories, website URLs.
2. **Products**: AI apps, tools, models, and verified pricing models (FREE, FREEMIUM, PAID, ENTERPRISE).
3. **Research Papers**: ArXiv papers enriched with live GitHub star counts fetched directly from the GitHub API.
4. **AI News**: 5 monitored AI news sources with strict 24-hour UTC freshness verification.
5. **AI Jobs**: 5 monitored job sources categorized by `RoleFamily` with strict 24-hour freshness verification.

---

## Technical Features

- **Anti-Hallucination Data Integrity**: Every record carries an unbroken provenance `source_url`. Missing fields default to `null`. GitHub stars are fetched directly from GitHub's REST API.
- **Async HTTP Crawler**: Built on `httpx.AsyncClient` with connection pooling, configurable `asyncio.Semaphore` concurrency limits, exponential backoff, jitter, and status code handling (200 success, 429 retry, 404 reject).
- **3-Tier LLM Provider Fallback**: Fallback chain (Gemini 1.5 Flash → Groq Llama 3 → DeepSeek) with 429 rate-limit backoff and prompt injection containment (`<untrusted_web_content>`).
- **Token-Aware 413 Chunking**: `SemanticChunker` pre-flights content, reserving output token budgets and preserving paragraph semantic boundaries.
- **Deterministic Entity Resolution**: RapidFuzz fuzzy matching against ~50 canonical AI entities with alias normalization and a strict 85% confidence threshold.
- **SQLite / SQLAlchemy Storage**: Portable relational ORM schema with unique SHA-256 deduplication keys.
- **Google Sheets Export**: Export to 6 tabs (Startups, Products, Research Papers, Jobs, News, Entity Mapping Log) via batched updates.
- **Comprehensive Test Suite**: 34 passing `pytest` unit and integration tests.

---

## Directory Structure

```
FrontierAtlas/
├── config/
│   └── config.yaml             # Pipeline configuration & source parameters
├── data/
│   ├── raw/                    # Staged raw crawler data
│   ├── processed/              # Processed datasets
│   └── samples/                # Sample data files
├── docs/
│   ├── architecture.md         # Detailed architectural design specification
│   └── final_audit.md          # Verification audit matrix & test report
├── scripts/
│   ├── generate_architecture_pdf.py  # ReportLab script for 3-page PDF
│   ├── test_sources.py         # Data source connectivity tester
│   └── test_wikidata.py        # SPARQL endpoint test script
├── src/
│   ├── crawlers/
│   │   ├── base_crawler.py     # httpx AsyncClient crawler with retries/backoff
│   │   ├── arxiv_crawler.py    # ArXiv Atom XML crawler & parser
│   │   ├── startup_crawler.py  # AI Startups ingestion
│   │   ├── product_crawler.py  # AI Products & HF Spaces ingestion
│   │   ├── news/
│   │   │   └── news_crawler.py # 5 AI news RSS feeds crawler
│   │   └── jobs/
│   │       └── job_crawler.py  # 5 AI job feeds crawler with RoleFamily parsing
│   ├── enrichment/
│   │   └── github_enrichment.py# Direct GitHub API star count enricher
│   ├── entity_resolution/
│   │   ├── entity_resolver.py  # RapidFuzz entity canonicalization engine
│   │   └── deduplicator.py     # Deterministic SHA-256 deduplication engine
│   ├── extraction/
│   │   ├── chunker.py          # Token-aware 413 semantic chunker
│   │   ├── date_normalizer.py  # ISO/RFC/relative UTC date engine
│   │   ├── freshness_engine.py # Strict 24h freshness verification engine
│   │   ├── llm_provider.py     # Base provider with prompt injection defense
│   │   ├── llm_orchestrator.py # 3-tier LLM fallback orchestrator
│   │   └── providers/
│   │       ├── gemini_provider.py
│   │       ├── groq_provider.py
│   │       └── deepseek_provider.py
│   ├── schemas/
│   │   ├── base.py
│   │   ├── enums.py            # PricingType, RoleFamily, RecordType
│   │   └── entities.py         # Pydantic v2 Startup, Product, Paper, Job, News models
│   ├── storage/
│   │   ├── db.py               # SQLAlchemy ORM models & database storage
│   │   └── sheets_sync.py      # 6-tab Google Sheets exporter
│   ├── utils/
│   │   ├── config.py           # Configuration loader
│   │   ├── logger.py           # Structured JSON logger
│   │   └── metrics.py          # Pipeline observability metrics tracker
│   └── main.py                 # CLI & pipeline orchestration entrypoint
├── tests/                      # 34 automated unit & integration tests
├── .env.example                # Example environment configuration
├── .gitignore                  # Git ignore rules
├── architecture.pdf            # Official 3-page Architecture PDF
├── pytest.ini                  # Pytest configuration
├── requirements.txt            # Python dependencies
└── README.md                   # Master project documentation
```

---

## Quick Start Guide

### 1. Environment Setup

```bash
# Clone repository and navigate to project directory
cd "FrontierAtlas Intelligence Pipeline"

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Secrets

Copy `.env.example` to `.env` and fill in optional API keys:

```bash
cp .env.example .env
```

### 3. Run Test Suite

Run the full automated test suite using `pytest`:

```bash
pytest
```

Expected output:
```
============================= 34 passed in 16.73s =============================
```

### 4. Execute the Pipeline

Run the pipeline via CLI:

```bash
python -m src.main --paper-limit 100 --startup-limit 100 --product-limit 100
```

To run without Google Sheets export (local SQLite DB only):

```bash
python -m src.main --no-sheets
```

---

## Architecture PDF

The official 3-page architectural specification is available in [`architecture.pdf`](file:///c:/Projects/FrontierAtlas%20Intelligence%20Pipeline/architecture.pdf). To regenerate it:

```bash
python scripts/generate_architecture_pdf.py
```
