"""Unit tests for News and Job crawlers."""
import pytest
from datetime import datetime, timezone, timedelta
from src.crawlers.news.news_crawler import NewsCrawler
from src.crawlers.jobs.job_crawler import JobCrawler
from src.extraction.freshness_engine import FreshnessEngine
from src.schemas import RoleFamily

def test_news_crawler_rss_freshness_filter():
    now_utc = datetime.now(timezone.utc)
    fresh_date = (now_utc - timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
    stale_date = "Wed, 15 Jan 2020 10:00:00 GMT"

    sample_rss = f"""<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0">
      <channel>
        <title>AI News Feed</title>
        <item>
          <title>Breakthrough in LLM Reasoning</title>
          <link>https://example.com/news/breakthrough</link>
          <pubDate>{fresh_date}</pubDate>
          <description>Scientists release new open weights model.</description>
        </item>
        <item>
          <title>Old News from 2020</title>
          <link>https://example.com/news/old</link>
          <pubDate>{stale_date}</pubDate>
          <description>Very old news item.</description>
        </item>
      </channel>
    </rss>
    """

    crawler = NewsCrawler()
    articles = crawler.parse_rss_feed(sample_rss, "Test Feed", "https://example.com/rss")
    
    assert len(articles) == 1
    assert articles[0].title == "Breakthrough in LLM Reasoning"
    assert articles[0].freshness_verified is True

def test_job_crawler_role_family_and_freshness():
    now_utc = datetime.now(timezone.utc)
    fresh_iso = (now_utc - timedelta(hours=2)).isoformat()

    sample_json = f"""[
      {{
        "company": "Anthropic",
        "position": "AI Alignment Researcher",
        "url": "https://example.com/jobs/researcher",
        "date": "{fresh_iso}",
        "description": "Conduct research on model safety and alignment."
      }},
      {{
        "company": "Stale Corp",
        "position": "Software Engineer",
        "url": "https://example.com/jobs/stale",
        "date": "2020-01-01T10:00:00Z",
        "description": "Old job post."
      }}
    ]"""

    crawler = JobCrawler()
    jobs = crawler.parse_json_jobs(sample_json, "Test Job Board", "https://example.com/api")
    assert len(jobs) == 1
    job = jobs[0]
    assert job.company_name == "Anthropic"
    assert job.role_title == "AI Alignment Researcher"
    assert job.role_family == RoleFamily.RESEARCH
    assert job.freshness_verified is True
