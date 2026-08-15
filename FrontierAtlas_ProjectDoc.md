# FrontierAtlas — AI/Venture Intelligence Ingestion Pipeline
### Engineering Project Documentation v1.0
**Project Type:** AI-Augmented Data Engineering / Web Intelligence System
**Domain:** Web Scraping · LLM-Based Structured Extraction · Entity Resolution · Data Pipelines
**Classification:** Technical Assessment Submission — GraphOne / FrontierAtlas AI Engineer Demo Task

---

> *"Raw web signal is not intelligence. FrontierAtlas exists to turn thousands of noisy, inconsistent, adversarial sources into one canonical, provenance-backed graph of the AI and venture ecosystem."*

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Problem Definition — Technical Depth](#3-problem-definition--technical-depth)
4. [Research & Source Landscape](#4-research--source-landscape)
5. [System Architecture & Approach](#5-system-architecture--approach)
6. [Proposed Solution — FrontierAtlas Pipeline](#6-proposed-solution--frontieratlas-pipeline)
7. [Technology Stack](#7-technology-stack)
8. [Implementation Phases & Task Breakdown](#8-implementation-phases--task-breakdown)
9. [LLM Extraction & Fallback Engine](#9-llm-extraction--fallback-engine)
10. [Entity Resolution & Deduplication Engine](#10-entity-resolution--deduplication-engine)
11. [Freshness & Date Normalization Engine](#11-freshness--date-normalization-engine)
12. [Anti-Bot & Scale Strategy](#12-anti-bot--scale-strategy)
13. [Validation & Self-Correction Loop](#13-validation--self-correction-loop)
14. [Export Pipeline](#14-export-pipeline)
15. [Performance Targets & Expected Outcomes](#15-performance-targets--expected-outcomes)
16. [Risk Analysis & Mitigations](#16-risk-analysis--mitigations)
17. [Future Roadmap](#17-future-roadmap)
18. [Glossary](#18-glossary)

---

## 1. Executive Summary

FrontierAtlas is an asynchronous, fault-tolerant data ingestion pipeline that converts unstructured web content — startup directories, product listings, research-paper repositories, AI news sites, and job boards — into a canonical, schema-validated intelligence graph. It was built to satisfy GraphOne's AI Engineer Demo Task: acquire a minimum of 1,000 unique startups, 1,000 unique products, and 1,000 unique research papers (enriched with live GitHub star counts); continuously monitor 5 AI news sources and 5 AI job boards under a strict 24-hour freshness guarantee; structure all raw content into a defined JSON schema using a three-tier LLM fallback chain (Gemini Flash → Groq Llama 3 → DeepSeek); resolve messy entity names to a canonical form; and deliver the result as a public Google Sheet plus a documented, reproducible GitHub repository.

The central architectural decision is the same one that governs any production scraping-plus-LLM system: **deterministic code owns structure and correctness; the LLM owns language understanding, nothing else.** Crawling, retrying, rate-limiting, chunking, date math, deduplication, and schema enforcement are all handled in plain Python with no model in the loop. The LLM is invoked only to map already-cleaned text into already-defined JSON fields, and its output is never trusted until it passes Pydantic validation and, where possible, cross-checks against an independently-fetched ground truth (e.g., GitHub star counts come from the GitHub API, never from the model).

This document distinguishes, throughout, between three categories of statement:
- **PDF REQUIREMENT** — stated explicitly in the assessment.
- **ENGINEERING RECOMMENDATION** — a design choice made to satisfy a requirement, justified but not mandated by the PDF.
- **ASSUMPTION** — a gap the PDF leaves ambiguous, resolved with a stated, reversible default.

No performance number in this document is claimed until it has been measured from an actual pipeline run. Sections that will eventually contain real benchmarks are marked `[MEASURED AFTER RUN]` and currently contain targets, not results.

---

## 2. Problem Statement

### 2.1 The Core Problem

GraphOne is building an "Intelligence Graph" of the AI and venture ecosystem — a normalized, continuously refreshed dataset spanning startups, founders, products, research, jobs, and news. The raw material for this graph exists nowhere as clean structured data; it is scattered across API-less HTML directories, PDF-heavy research repositories, JS-rendered product listings, Cloudflare-protected news sites, and job boards with inconsistent or missing date metadata. Turning that raw material into something a graph database can consume requires solving, simultaneously, four historically separate engineering problems: **large-scale asynchronous crawling, LLM-based structured extraction under real API constraints (429/413), deterministic entity canonicalization, and time-sensitive freshness verification** — all while guaranteeing that nothing in the final dataset is fabricated.

### 2.2 Who This Serves

| Stakeholder | Need | Failure Cost |
|---|---|---|
| GraphOne Data Intelligence team | A trustworthy, provenance-backed dataset to build the graph on | A single hallucinated record poisons trust in the whole dataset |
| Downstream graph/ML consumers | Canonical entity names, not raw scraped strings | "OpenAI" / "OpenAI, Inc." / "Open AI" fragmenting into 3 nodes breaks graph queries |
| Engineering reviewers (this assessment) | Evidence of production-grade thinking under a 3-day constraint | Over-engineering or fabricated volume both read as poor judgment |

### 2.3 The Three Dimensions of This Problem

Ingestion pipeline correctness fails across three interconnected axes simultaneously, exactly as in any real data-engineering system:

**Dimension 1 — Volume Under Constraint (Scale)**
The assignment asks for ≥1,000 records each of three entity types within a 3-day window, while requiring the *architecture* (not the actual run) to scale to 500,000+. This means the system must be provably horizontally-scalable in design — stateless workers, queue-partitionable stages, idempotent writes — even though the demo run itself stays small. **PDF REQUIREMENT.**

**Dimension 2 — Correctness Under Time Pressure (Freshness)**
News and jobs are only valid if verifiably published within the last 24 hours. Most web sources do not expose a reliable machine-readable timestamp; many use relative phrases ("2 hours ago"), missing `<meta>` tags, or client-rendered dates. A false "fresh" classification is a correctness bug with the same severity as a fabricated field. **PDF REQUIREMENT.**

**Dimension 3 — Semantic Fidelity Under Delegation (LLM Trust)**
Delegating structuring to an LLM introduces a class of failure unique to this problem: the model can produce syntactically valid, schema-conformant JSON that is semantically false (an invented author, a wrong GitHub URL, a guessed employee count). Because the assignment explicitly disqualifies hallucination, every LLM-derived field must be traceable back to a span of the actual source text, and any numeric/factual field with an independent authoritative source (GitHub stars, publish dates) must be fetched from that source directly rather than left to the model. **PDF REQUIREMENT**, reinforced by the explicit disqualification clause.

---

## 3. Problem Definition — Technical Depth

### 3.1 Formal Problem Statement

Given:
- A set of source endpoints **S** = {arxiv, papers-with-code, startup directories, product directories, 5 news sites, 5 job boards}, each with its own access pattern **A(s)** ∈ {REST API, RSS, static HTML, JS-rendered HTML}
- A canonical schema set **Σ** = {Startup, Product, ResearchPaper, Job}, each a strict Pydantic model matching the PDF's field tables exactly
- A canonical entity seed set **K** = {k₁...k₅₀} of known AI startups, used as ground truth for entity resolution
- A freshness constraint **F**: for News and Job records only, `now_UTC − publish_time_UTC ≤ 24h`, else reject
- An LLM tier chain **L** = [Gemini Flash, Groq Llama 3, DeepSeek], invoked in order on failure/429 of the prior tier

Produce:
- A record set **R** ⊂ Σ-typed objects, each carrying `source.url` traceable to a live, fetched page, and `collectedAt` in ISO-8601
- |R_startup| ≥ 1,000, |R_product| ≥ 1,000, |R_paper| ≥ 1,000 (papers additionally carrying verified `github_stars` fetched from the GitHub API, not the LLM)
- R_news and R_job containing only records satisfying **F**
- An entity-mapping log **M** = {(raw_name, canonical_name, method, confidence, source_url)} for every resolved entity
- A public Google Sheet with exactly six tabs (Startups, Products, Research Papers, Jobs, News, Entity Mapping Log) and a GitHub repository containing `src/`, `README.md`, `architecture.pdf`

Subject to:
- No two records in R sharing a deduplication key (canonical entity + source URL, or content hash)
- No LLM call ever receiving a payload that would trigger a 413 (enforced by pre-flight token estimation and chunking)
- Every 429 handled via exponential backoff + jitter before any tier fallback is attempted
- No field in R present unless it is either directly scraped, directly LLM-structured *from* scraped text, or directly fetched from an independent authoritative API

### 3.2 Why This Problem Is Hard

**3.2.1 Heterogeneous Access Patterns at Scale**
Five news sites and five job boards means, realistically, five to ten *different* crawling strategies — RSS where available, HTML parsing with source-specific selectors elsewhere, and Playwright where JavaScript rendering or bot-protection makes static fetching insufficient. A crawler architecture that assumes one access pattern for all sources will not survive contact with the actual sources. **ENGINEERING RECOMMENDATION:** build one `BaseCrawler` with pluggable fetch strategies (`httpx` fetcher, `Playwright` fetcher, `RSS` fetcher) selected per-source in config, not per-source bespoke crawlers duplicating retry/rate-limit logic.

**3.2.2 The 413/429 Duality**
These two HTTP-adjacent failure modes pull in opposite directions. A 413 (or its LLM-context-window equivalent) is solved by sending *less* data per call; a 429 is solved by sending *fewer calls*, not less data per call. A naive "just chunk everything smaller" strategy that ignores rate limits will multiply the number of calls and make 429s worse. The chunking strategy and the backoff strategy must be designed together, with chunk size and concurrency both configurable per-provider, because each LLM tier has different context limits and different rate-limit windows.

**3.2.3 Freshness Without Reliable Signal**
Relative-date parsing ("2 hours ago", "Yesterday") requires knowing the page's fetch time and the target timezone, both of which are easy to get subtly wrong at UTC boundaries (fetching at 00:30 UTC, a source publishing in a UTC+9 timezone, etc.). Where no timestamp exists at all, the PDF explicitly permits an "intelligent heuristic" — but a heuristic that over-trusts unverified freshness is a worse failure than under-including borderline-fresh content, because false freshness claims are functionally equivalent to fabricated data in the eyes of the evaluation criteria.

**3.2.4 Entity Resolution Without Ground Truth Beyond the Seed List**
Only 50 canonical entities are provided as ground truth. Any startup or product mentioned outside that seed list has no authoritative canonical form to resolve against. **ENGINEERING RECOMMENDATION:** entities matching the seed list (exact, alias, or high-confidence fuzzy match) are canonicalized against it; entities outside the seed list are normalized (casing, legal suffixes like "Inc."/"Ltd." stripped, whitespace collapsed) but *not* force-merged against each other without a conservative confidence threshold — false merges are explicitly worse than leaving two records unresolved, since a false merge silently deletes a real distinct entity from the graph.

**3.2.5 Provenance Under LLM Delegation**
The single hardest constraint in this assignment is not any individual technical challenge — it is maintaining unbroken provenance through every transformation. A record must be traceable from the final Sheet row back through entity resolution, schema validation, LLM extraction, cleaning, and all the way to the original fetched HTML byte-for-byte. **ENGINEERING RECOMMENDATION:** every record carries its originating `source.url` and a `raw_content_hash` from the moment it is first fetched, propagated unchanged through every pipeline stage, so any record can be audited independently of the LLM's output.

### 3.3 Existing Approaches & Their Failures

| Approach | Description | Why It Fails This Assignment |
|---|---|---|
| Single-provider LLM extraction | Call one model (e.g., GPT-4o) for everything | No resilience to rate limits; PDF explicitly requires a fallback chain; single point of failure at 25% of the grade |
| Naive fixed-size truncation for long documents | Cut text at N characters | Can sever mid-sentence, destroying exactly the semantically dense content (author lists, dates) the extraction needs; PDF requires chunking that "retains semantically dense content" |
| Regex-only date extraction | Pattern-match dates with regex | Cannot handle relative phrases or JSON-LD/OpenGraph structured dates reliably; produces false negatives that undercount fresh content and false positives that overclaim it |
| Writing directly to Google Sheets per-record | Treat Sheets as the database | Hits Sheets API rate limits fast, has no transactional guarantees, cannot answer "have I seen this URL before" efficiently — makes idempotent re-runs impossible |
| Trusting LLM-reported GitHub stars | Ask the model to state the star count from page text | Stars are dynamic and the model may see stale or absent data in the page snapshot; PDF explicitly implies dynamic-metric tracking, and disqualifies hallucinated data — stars must come from the GitHub API directly |

---

## 4. Research & Source Landscape

*(This section is populated incrementally as each source is verified live — see `06_DATA_SOURCES.md` for the authoritative, continuously updated version. No source below is committed to until confirmed accessible without bypassing auth/paywalls/CAPTCHA.)*

| Category | Candidate sources | Access pattern | Status |
|---|---|---|---|
| Research papers | arxiv.org (official Atom/XML API), paperswithcode.com | REST API / HTML | To verify live before Step 4 |
| GitHub enrichment | api.github.com | REST API, PAT-authenticated | Confirmed stable, well-documented |
| Startups | Public startup directory with listable pages (candidate TBD) | HTML, paginated | To verify live before Step 5 |
| Products | Public AI-tools directory with listable pages (candidate TBD) | HTML, paginated | To verify live before Step 6 |
| News (×5) | Candidate AI news outlets, RSS preferred over HTML where available | RSS / HTML | To verify live before Step 9 |
| Jobs (×5) | Candidate AI-focused job boards, RSS/JSON preferred over HTML | RSS / JSON / HTML | To verify live before Step 10 |

**ASSUMPTION:** `paperswithcode.co` (as printed in the PDF's example URL) is a typo for `paperswithcode.com`; the pipeline targets the real domain and this substitution is documented explicitly in the architecture doc, not silently made.

---

## 5. System Architecture & Approach

```
DATA SOURCES (Arxiv, PwC, startup/product dirs, 5 news, 5 jobs)
        ↓
SOURCE ADAPTERS  (per-source config: fetch strategy, selectors/RSS map, rate limits)
        ↓
ASYNC CRAWLERS   (httpx.AsyncClient | Playwright async, semaphore-bound concurrency,
                  retry + exponential backoff + jitter on 429/5xx/timeout)
        ↓
RAW / STAGING LAYER   (raw HTML/JSON + fetch metadata persisted — the audit trail)
        ↓
CONTENT CLEANING      (boilerplate/nav/ad stripping, main-content extraction)
        ↓
DATE NORMALIZATION → 24H FRESHNESS ENGINE   (news/jobs only; reject on uncertainty)
        ↓
LLM EXTRACTION ENGINE   (chunk → Gemini Flash → [429/err] → Groq Llama 3 → [429/err] → DeepSeek)
        ↓
Pydantic SCHEMA VALIDATION   (reject/quarantine on mismatch, log every failure)
        ↓
ENTITY RESOLUTION   (normalize → exact → alias → fuzzy(RapidFuzz) → confidence gate → canonical)
        ↓
DEDUPLICATION   (canonical entity + source URL / content hash / paper ID / job URL)
        ↓
DATABASE (SQLite via SQLAlchemy; Postgres-portable models)
        ↓
GOOGLE SHEETS EXPORT   (batched writes, 6 tabs, Sheets as a view, not the store of record)
```

**Concurrency:** each crawler runs behind an `asyncio.Semaphore` sized per-source (config-driven), so aggressive sources don't starve polite ones and no single source can trip its own anti-bot defenses through the pipeline's own overeagerness.

**Idempotency:** every write is keyed on a deterministic dedup key computed *before* the write, so re-running the pipeline against a partially-completed prior run never double-inserts.

**Provenance:** the raw/staging layer is the only place a record's identity is first assigned; that identity (source URL + content hash) rides through every subsequent stage unchanged, which is what makes the final audit (`16_FINAL_CHECKLIST.md`) possible.

**Demo architecture vs. production-scale architecture** are explicitly separated: the demo runs single-process with `asyncio.Queue` between logical stages and SQLite as the store; the documented (not implemented) production path swaps `asyncio.Queue` for a real message queue (Redis Streams or SQS), SQLite for Postgres, and adds N horizontally-scaled worker processes per stage — a config and infrastructure change, not a logic rewrite. This separation is itself the answer to the PDF's Phase VI "Scale Strategy" question.

---

## 6. Proposed Solution — FrontierAtlas Pipeline

FrontierAtlas is delivered as a single Python package (`src/`) orchestrated by `main.py`, configured entirely through `config/config.yaml` and `.env` — no source-specific values hardcoded in application logic. The pipeline runs as a sequence of independently-testable stages (crawl → clean → date-normalize → extract → validate → resolve → dedupe → store → export), each of which can be run, tested, and reasoned about in isolation, and each of which is the natural seam for horizontal scaling described above.

The system's defining engineering commitment, restated: **nothing is ever added to the output dataset that the pipeline cannot justify with a live source URL and, where an authoritative independent source exists (GitHub stars), a direct fetch from that source.**

---

## 7. Technology Stack

| Layer | Choice | Rationale |
|---|---|---|
| Language | Python 3.11+ | Ecosystem fit for scraping + LLM orchestration; matches team's stated skillset |
| Async HTTP | `httpx` (async client) | Sync/async parity, HTTP/2, easier learning curve than raw `aiohttp` |
| JS/anti-bot rendering | `Playwright` (async) | Explicitly named as acceptable in the PDF; better anti-detection ergonomics than Selenium |
| HTML parsing | `selectolax` (fast) with `BeautifulSoup` fallback | Speed at scale; BS4 as the readable fallback for tricky markup |
| Schema/validation | `Pydantic v2` | Enforces the PDF's exact field tables; free serialization |
| ORM/storage | `SQLAlchemy` + SQLite (demo), Postgres-portable | Zero-setup for the trial; a connection-string change to scale |
| Entity matching | `RapidFuzz` | Fast, dependency-light fuzzy matching sufficient for company-name canonicalization |
| LLM SDKs | Google Generative AI SDK (Gemini), Groq SDK, DeepSeek (OpenAI-compatible) | Matches the PDF's named fallback chain; all offer usable free/low-cost tiers |
| Sheets export | `gspread` (Google Sheets API) | Required deliverable format; batched writes to respect API limits |
| Config/secrets | `python-dotenv`, `PyYAML` | Keeps secrets out of code and source lists out of logic |
| Logging | Python `logging`, structured JSON formatter | Rigor without a heavyweight dependency |
| Testing | `pytest` | Targeted at the highest-risk logic: dates, chunking, entity resolution, schemas |
| Containerization | Docker + docker-compose (minimal) | Reproducibility credit without consuming majority of the timeline |

**Deliberately excluded for the demo** (documented, not implemented): Kubernetes, Kafka/real message queues, Neo4j or other graph stores, vector databases. Each is addressed as a *justified recommendation* in Section 17 and in `architecture.pdf`, since the PDF asks the design to be scalable and to justify storage choices — not to deploy this infrastructure inside a 3-day trial. Introducing them anyway would be over-engineering relative to the deliverable.

---

## 8. Implementation Phases & Task Breakdown

| # | Phase | Key files | Exit criteria |
|---|---|---|---|
| 0 | Environment setup | `.env`, `requirements.txt` | `python -c "import httpx, pydantic"` succeeds |
| 1 | Project structure + config | `config/config.yaml` | Config loads and validates |
| 2 | Schemas | `src/schemas/*.py` | Pydantic models match PDF tables field-for-field |
| 3 | Base async crawler | `src/crawlers/base_crawler.py` | Retry/backoff/jitter unit-tested against mocked 429/5xx |
| 4 | Research paper pipeline | `src/crawlers/arxiv_crawler.py`, `paperswithcode_crawler.py`, `src/enrichment/github_enrichment.py` | ≥1,000 papers with verified GitHub stars |
| 5 | Startup pipeline | `src/crawlers/startup_crawler.py` | ≥1,000 unique startups |
| 6 | Product pipeline | `src/crawlers/product_crawler.py` | ≥1,000 unique products |
| 7 | Date normalization | `src/extraction/date_normalizer.py` | Passes relative/absolute/timezone-boundary tests |
| 8 | Freshness engine | `src/extraction/freshness_engine.py` | Rejects unverifiable dates by default |
| 9 | News pipeline | `src/crawlers/news_crawlers/*.py` | 5 sources wired, freshness-filtered |
| 10 | Job pipeline | `src/crawlers/job_crawlers/*.py` | 5 sources wired, freshness-filtered |
| 11 | LLM orchestrator | `src/extraction/llm_orchestrator.py` | Fallback chain demonstrated under simulated 429 |
| 12 | Chunking (413 defense) | `src/extraction/chunker.py` | No payload ever exceeds provider context budget |
| 13 | 429 handling | inside `llm_orchestrator.py` | Backoff+jitter logged; fallback triggers correctly |
| 14 | Entity resolution | `src/entity_resolution/*.py` | 50-entity seed list; mapping log populated |
| 15 | Deduplication | `src/storage/db.py` | Constraint-enforced uniqueness; idempotent re-run test |
| 16 | Database | `src/storage/db.py` | SQLite schema matches design in Section 6 |
| 17 | Google Sheets export | `src/storage/sheets_sync.py` | 6 tabs populated via batched writes |
| 18 | Logging | `src/utils/logging_config.py` | Structured logs across all stages |
| 19 | Tests | `tests/*.py` | Highest-risk logic covered; mocked externals |
| 20 | Docker (if time permits) | `Dockerfile`, `docker-compose.yml` | `docker compose up` reproduces a run |
| 21 | Architecture doc | `architecture.pdf` | ≤3 pages, answers all 4 posed questions |
| 22 | README | `README.md` | Setup + honest scope statement |
| 23 | Final audit | `16_FINAL_CHECKLIST.md` | Every PDF requirement has status + evidence |

---

## 9. LLM Extraction & Fallback Engine

```
chunk(text) → estimate_tokens → fits in Tier-1 budget?
   → Gemini Flash
        → success → validate → done
        → 429     → backoff+jitter → retry (bounded) → still failing → Tier 2
        → other error → log → Tier 2
   → Groq Llama 3  (same retry/fallback logic)
   → DeepSeek       (final tier; failure here = record quarantined, not fabricated)
```

The orchestrator is built behind a single `LLMProvider` interface with `GeminiProvider`, `GroqProvider`, `DeepSeekProvider` implementations, so adding or reordering a tier is a config change. Scraped content is treated as **untrusted input**: prompts are structured so that any instruction-like text embedded in a webpage ("ignore previous instructions...") is inert — it is passed only as data inside a clearly delimited content block, never concatenated into the system/instruction portion of the prompt, and the model's output is *always* re-validated against the Pydantic schema regardless of what the page tried to say. This is a direct, practical defense against prompt injection via scraped content.

---

## 10. Entity Resolution & Deduplication Engine

```
raw_name → normalize (casing, whitespace, legal-suffix strip)
        → exact match against 50-entity seed list?
        → alias-table match?
        → RapidFuzz fuzzy match ≥ confidence threshold?
        → YES → canonical entity, log (raw, canonical, method, confidence, source_url)
        → NO  → keep normalized form, mark unresolved, log for review
```

Deduplication runs downstream on the *resolved* entity plus a type-appropriate key: `(canonical_entity, source_url)` for startups/products, `paper_url`/`github_url` for papers, `job_url` for jobs, `news_url` (or content hash where URLs vary by tracking params) for news. Conservative-by-design: an unresolved entity is worse for graph completeness but far safer than a false merge, which silently deletes a real node.

---

## 11. Freshness & Date Normalization Engine

```
extract candidate timestamp (JSON-LD → OpenGraph → <time> tag → visible relative text)
        → parse to timezone-aware datetime
        → convert to UTC
        → age = now_UTC − timestamp_UTC
        → age ≤ 24h?  → accept
        → age > 24h or unparseable → reject, log reason
```

Where no timestamp source exists at all, the pipeline applies the PDF-permitted heuristic (has this URL been seen in a prior crawl run? if not, and other freshness signals are absent, treat cautiously) but **never upgrades an unverifiable date to "confirmed fresh."** This asymmetry — biased toward rejection over false acceptance — is the direct engineering response to the disqualification clause.

---

## 12. Anti-Bot & Scale Strategy

For Cloudflare/Datadome-protected or heavily JS-rendered sources, the priority order is: (1) official API or RSS if one exists — always preferred, since it sidesteps the anti-bot problem entirely; (2) Playwright with realistic headers, pacing, and session persistence for sources that require rendering; (3) if a source remains inaccessible without CAPTCHA-solving or credential/paywall bypass, it is **documented as such, not forced** — the PDF explicitly accepts "demonstrate *or* document" this strategy. Scale beyond the demo run is achieved by adding worker processes and queue partitions, not by increasing per-worker aggressiveness against any single source.

---

## 13. Validation & Self-Correction Loop

Every LLM extraction passes through Pydantic validation before it is eligible for storage. On failure, the record is quarantined with the validation error logged — it is never retried with a "just make it fit" prompt, since that is exactly the path toward fabrication. Numeric/factual fields with an independent source of truth (GitHub stars) are always re-fetched from that source and reconciled against — not accepted from the LLM's reading of page text — as an additional correction layer beyond schema shape.

---

## 14. Export Pipeline

The database (SQLite/SQLAlchemy) remains the source of truth throughout the run. Export to Google Sheets is a final, batched, idempotent step: each of the six tabs (Startups, Products, Research Papers, Jobs, News, Entity Mapping Log) is written via `gspread` batch-update calls, sized to stay well under Sheets API quotas, and can be safely re-run without duplicating rows because the underlying export query is deterministic against the database's dedup keys.

---

## 15. Performance Targets & Expected Outcomes

`[MEASURED AFTER RUN]` — the table below states *targets* derived directly from the PDF; it will be replaced with actual measured numbers once the pipeline has been run end-to-end, and only those measured numbers will ever appear in the README, architecture.pdf, or resume bullets.

| Metric | Target | Source |
|---|---|---|
| Unique startups | ≥ 1,000 | PDF Phase I |
| Unique products | ≥ 1,000 | PDF Phase I |
| Unique research papers w/ GitHub stars | ≥ 1,000 | PDF Phase I |
| News sources monitored | 5, 24h-fresh only | PDF Phase II |
| Job boards monitored | 5, 24h-fresh only | PDF Phase II |
| LLM fallback chain tiers | 3 (Gemini → Groq → DeepSeek) | PDF Phase III |
| Entity seed list size | ~50 | PDF Phase IV |
| Sheet tabs delivered | 6 | PDF Deliverables |

---

## 16. Risk Analysis & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A chosen source turns out to require login/paywall/CAPTCHA bypass | Medium | High | Verify every source live before building its crawler; swap to a documented legitimate alternative rather than bypass |
| LLM tiers rate-limit harder than expected under real load | Medium | Medium | Concurrency caps + backoff tuned conservatively first, loosened only after observing real quota behavior |
| Relative-date parsing misses an edge case at a timezone boundary | Medium | Medium | Explicit unit tests for boundary cases (23:59 vs 00:01 UTC, DST-adjacent dates) |
| Fuzzy entity matching produces a false merge | Low–Medium | High (silently deletes a real entity from the graph) | Conservative confidence threshold; log every match for post-hoc review; prefer unresolved over merged |
| `paperswithcode.co` (as printed) is a genuine, different, untrusted domain | Low | High if unnoticed | Explicitly flagged in this document and in architecture.pdf; only `paperswithcode.com` is used |
| Time runs out before Docker/tests are complete | Medium | Low | Documented cut-order (Section 8 of the roadmap discussion): Docker first, then non-critical tests, before ever cutting schema/provenance/freshness work |

---

## 17. Future Roadmap

Beyond the 3-day demo scope, the natural production path is: swap SQLite → PostgreSQL; swap `asyncio.Queue` → Redis Streams/SQS with N horizontally-scaled workers per stage; introduce a real vector store (e.g., for semantic paper search) or graph database (e.g., Neo4j, to natively represent startup↔product↔paper↔founder relationships) — both justified as *recommendations* here rather than implemented, per the PDF's request to "justify your choice" rather than build it; add a scheduler (cron/Airflow) for continuous rather than one-time ingestion; add a review UI for low-confidence entity-resolution matches.

---

## 18. Glossary

- **413** — HTTP/LLM-context error meaning the payload exceeds the provider's size limit; addressed here via pre-flight chunking.
- **429** — HTTP status for rate-limiting; addressed via exponential backoff with jitter, then provider fallback.
- **Canonical entity** — the single agreed-upon name a set of raw name variants resolve to (e.g., "OpenAI").
- **Chunking** — splitting long text into provider-context-sized pieces without severing semantically important content.
- **Dedup key** — the deterministic field combination used to detect and reject duplicate records.
- **Freshness** — for this project, a binary: published within the last 24 hours, verified against a parsed UTC timestamp.
- **Provenance** — the unbroken chain from a final record back to its original fetched source URL.
- **Schema validation** — Pydantic-enforced conformance to the PDF's exact field tables before a record is eligible for storage.
