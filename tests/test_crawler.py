"""Unit tests for BaseAsyncCrawler with mocked httpx transport."""
import pytest
import httpx
from src.crawlers.base_crawler import BaseAsyncCrawler

@pytest.mark.asyncio
async def test_crawler_200_ok():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="OK", request=request)

    transport = httpx.MockTransport(handler)
    crawler = BaseAsyncCrawler(max_retries=1, initial_backoff=0.01)
    crawler._client = httpx.AsyncClient(transport=transport)

    resp = await crawler.fetch("https://example.com/test")
    assert resp.is_success
    assert resp.status_code == 200
    assert resp.text == "OK"
    await crawler.close()

@pytest.mark.asyncio
async def test_crawler_404_no_retry():
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(404, text="Not Found", request=request)

    transport = httpx.MockTransport(handler)
    crawler = BaseAsyncCrawler(max_retries=3, initial_backoff=0.01)
    crawler._client = httpx.AsyncClient(transport=transport)

    resp = await crawler.fetch("https://example.com/notfound")
    assert resp.status_code == 404
    assert calls == 1  # 404 should not retry
    await crawler.close()

@pytest.mark.asyncio
async def test_crawler_429_retry_then_success():
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, text="Rate Limited", request=request)
        return httpx.Response(200, text="Success after retry", request=request)

    transport = httpx.MockTransport(handler)
    crawler = BaseAsyncCrawler(max_retries=2, initial_backoff=0.01, jitter=False)
    crawler._client = httpx.AsyncClient(transport=transport)

    resp = await crawler.fetch("https://example.com/ratelimit")
    assert resp.is_success
    assert resp.status_code == 200
    assert calls == 2
    await crawler.close()

@pytest.mark.asyncio
async def test_crawler_500_max_retries_exceeded():
    calls = 0
    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500, text="Server Error", request=request)

    transport = httpx.MockTransport(handler)
    crawler = BaseAsyncCrawler(max_retries=2, initial_backoff=0.01, jitter=False)
    crawler._client = httpx.AsyncClient(transport=transport)

    resp = await crawler.fetch("https://example.com/error")
    assert not resp.is_success
    assert calls == 3  # 1 initial + 2 retries
    await crawler.close()
