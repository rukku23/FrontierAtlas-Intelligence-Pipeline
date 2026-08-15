"""Base Async HTTP Crawler for FrontierAtlas with retry, backoff, jitter, and concurrency limits."""
import asyncio
import random
import time
import httpx
from typing import Optional, Dict, Any, Union
from src.utils.logger import logger
from src.utils.config import get_config

class CrawlResponse:
    def __init__(
        self,
        url: str,
        status_code: int,
        content: bytes,
        headers: Dict[str, str],
        latency_ms: float,
        error: Optional[str] = None
    ):
        self.url = url
        self.status_code = status_code
        self.content = content
        self.headers = headers
        self.latency_ms = latency_ms
        self.error = error

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    @property
    def is_success(self) -> bool:
        return self.status_code == 200 and self.error is None

class BaseAsyncCrawler:
    """Async crawler with connection pooling, rate limiting, and exponential backoff + jitter."""

    def __init__(
        self,
        user_agent: Optional[str] = None,
        max_concurrent_requests: Optional[int] = None,
        timeout_seconds: Optional[float] = None,
        max_retries: Optional[int] = None,
        initial_backoff: Optional[float] = None,
        max_backoff: Optional[float] = None,
        backoff_factor: Optional[float] = None,
        jitter: bool = True
    ):
        cfg = get_config()
        self.user_agent = user_agent or cfg.get("crawler.user_agent", "FrontierAtlas-Bot/1.0")
        max_concurrent = max_concurrent_requests or cfg.get("crawler.max_concurrent_requests", 10)
        self.semaphore = asyncio.Semaphore(max_concurrent)
        
        self.timeout_seconds = timeout_seconds or cfg.get("crawler.timeout_seconds", 20.0)
        self.max_retries = max_retries if max_retries is not None else cfg.get("crawler.max_retries", 4)
        self.initial_backoff = initial_backoff or cfg.get("crawler.initial_backoff_seconds", 1.0)
        self.max_backoff = max_backoff or cfg.get("crawler.max_backoff_seconds", 30.0)
        self.backoff_factor = backoff_factor or cfg.get("crawler.backoff_factor", 2.0)
        self.jitter = jitter

        self.headers = {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,application/json;q=0.8,*/*;q=0.7",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def start(self):
        if self._client is None or self._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50)
            timeout = httpx.Timeout(self.timeout_seconds)
            self._client = httpx.AsyncClient(
                headers=self.headers,
                limits=limits,
                timeout=timeout,
                follow_redirects=True
            )

    async def close(self):
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _calculate_backoff(self, attempt: int) -> float:
        backoff = self.initial_backoff * (self.backoff_factor ** attempt)
        backoff = min(backoff, self.max_backoff)
        if self.jitter:
            backoff = backoff * random.uniform(0.5, 1.5)
        return backoff

    async def fetch(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None
    ) -> CrawlResponse:
        """Fetch URL with retries, exponential backoff, jitter, and status handling."""
        if self._client is None or self._client.is_closed:
            await self.start()

        attempt = 0
        req_headers = {**self.headers, **(headers or {})}

        while attempt <= self.max_retries:
            async with self.semaphore:
                start_time = time.perf_counter()
                try:
                    logger.debug(
                        f"Fetching {url}",
                        extra={"url": url, "retry_count": attempt, "component": "BaseAsyncCrawler"}
                    )
                    resp = await self._client.get(url, headers=req_headers, params=params)
                    latency_ms = (time.perf_counter() - start_time) * 1000.0

                    status = resp.status_code

                    # 200 OK
                    if status == 200:
                        logger.info(
                            f"Fetch success for {url} ({latency_ms:.1f}ms)",
                            extra={"url": url, "status_code": status, "latency_ms": latency_ms, "component": "BaseAsyncCrawler"}
                        )
                        return CrawlResponse(
                            url=url,
                            status_code=status,
                            content=resp.content,
                            headers=dict(resp.headers),
                            latency_ms=latency_ms
                        )

                    # 404 Not Found - Reject immediately (no retry)
                    elif status == 404:
                        logger.warning(
                            f"404 Not Found for {url}",
                            extra={"url": url, "status_code": 404, "latency_ms": latency_ms, "component": "BaseAsyncCrawler"}
                        )
                        return CrawlResponse(
                            url=url,
                            status_code=404,
                            content=resp.content,
                            headers=dict(resp.headers),
                            latency_ms=latency_ms,
                            error="404 Not Found"
                        )

                    # 403 Forbidden - Log & return without excessive retry
                    elif status == 403:
                        logger.warning(
                            f"403 Forbidden for {url}",
                            extra={"url": url, "status_code": 403, "latency_ms": latency_ms, "component": "BaseAsyncCrawler"}
                        )
                        return CrawlResponse(
                            url=url,
                            status_code=403,
                            content=resp.content,
                            headers=dict(resp.headers),
                            latency_ms=latency_ms,
                            error="403 Forbidden"
                        )

                    # 429 Too Many Requests or 5xx Server Errors -> Retry with backoff
                    elif status == 429 or status in (500, 502, 503, 504):
                        logger.warning(
                            f"HTTP {status} for {url} on attempt {attempt}/{self.max_retries}",
                            extra={"url": url, "status_code": status, "retry_count": attempt, "component": "BaseAsyncCrawler"}
                        )

                except (httpx.TimeoutException, httpx.RequestError) as exc:
                    latency_ms = (time.perf_counter() - start_time) * 1000.0
                    logger.warning(
                        f"Request error '{type(exc).__name__}' for {url} on attempt {attempt}/{self.max_retries}",
                        extra={"url": url, "error": str(exc), "retry_count": attempt, "component": "BaseAsyncCrawler"}
                    )

            # Check if we should retry
            if attempt < self.max_retries:
                sleep_time = self._calculate_backoff(attempt)
                logger.info(
                    f"Backing off for {sleep_time:.2f}s before retry {attempt + 1}",
                    extra={"url": url, "retry_count": attempt + 1, "component": "BaseAsyncCrawler"}
                )
                await asyncio.sleep(sleep_time)
                attempt += 1
            else:
                break

        logger.error(
            f"Max retries reached for {url}",
            extra={"url": url, "retry_count": attempt, "component": "BaseAsyncCrawler"}
        )
        return CrawlResponse(
            url=url,
            status_code=500,
            content=b"",
            headers={},
            latency_ms=0.0,
            error=f"Failed after {self.max_retries} retries"
        )
