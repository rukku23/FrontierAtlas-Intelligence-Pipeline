# FrontierAtlas System Architecture & Design Specification

## 1. System Overview

FrontierAtlas is an asynchronous, fault-tolerant web intelligence ingestion pipeline designed to continuously ingest, extract, enrich, canonicalize, and export AI ecosystem data across five key domain verticals:

1. **Startups**: AI companies, founding metadata, categories, and website links.
2. **Products**: AI applications, models, tools, and verified pricing models.
3. **Research Papers**: ArXiv publications enriched with live GitHub star counts.
4. **News**: AI news monitored continuously with strict 24-hour freshness guarantees.
5. **Jobs**: AI job postings categorized by role family with 24-hour freshness guarantees.

---

## 2. Technical Decisions & Trade-offs

| Engineering Dimension | Selected Approach | Production Scale Alternative (500,000+ Records) |
|---|---|---|
| **Crawling Engine** | `httpx.AsyncClient` with semaphore concurrency control | Distributed Scrapy / Playwright cluster on Kubernetes |
| **State & Storage** | SQLite + SQLAlchemy ORM | PostgreSQL + PgVector / CockroachDB |
| **Queue & Messaging** | `asyncio.Queue` (in-process) | Redis Streams / Apache Kafka |
| **LLM Tiering** | Gemini Flash → Groq Llama 3 → DeepSeek | Local fine-tuned Small Language Models (vLLM / TGI) |
| **Entity Resolution** | RapidFuzz + Seed List (~50 entities) | Entity Embeddings + Vector Search + Human-in-the-loop UI |
| **Export Layer** | Google Sheets API (`gspread` batched writes) | Snowflake / BigQuery Data Warehouse |

---

## 3. Data Integrity & Anti-Hallucination Framework

### Zero-Fabrication Enforcement
- ** provenance tracking**: Every single entity record retains its original `source_url` and ISO-8601 UTC `collected_at` timestamp.
- **Dynamic Metric Fetching**: GitHub star counts are fetched directly from the GitHub REST API (`https://api.github.com/repos/{owner}/{repo}`). The LLM is never asked to guess star counts or repository URLs.
- **Nullability Policy**: Unknown or missing numeric/text values (e.g. employee counts, founding year, pricing details) are set to `null` rather than estimated.

### Prompt Injection Defense
Scraped content is wrapped inside explicit XML containers (`<untrusted_web_content>...</untrusted_web_content>`). The LLM system prompt instructs the model to treat all text inside these tags strictly as passive data, rendering instruction injection attempts inert.

---

## 4. Scalability Architecture (1K → 500K+)

```
[DATA SOURCES] -> [ASYNC CRAWLERS] -> [CLEANING / FRESHNESS ENGINE]
                                                 ↓
                                      [LLM ORCHESTRATOR]
                                      (413 Chunking + 429 Retry)
                                                 ↓
                                      [ENTITY RESOLUTION & DEDUP]
                                                 ↓
                                      [SQL STORAGE] -> [GOOGLE SHEETS]
```

To scale horizontally:
1. **Decouple Ingestion & Processing**: Move from `asyncio` in-memory processing to Redis Streams or Kafka partitions.
2. **Worker Scaling**: Spin up N stateless worker containers processing specific queue topics independently.
3. **Database Sharding**: Partition PostgreSQL tables on `dedup_key` / entity domain.
