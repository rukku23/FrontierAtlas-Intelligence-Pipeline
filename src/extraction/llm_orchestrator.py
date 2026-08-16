"""LLM Orchestrator managing token chunking, 429 rate-limit backoff, and 3-tier provider fallback."""
import asyncio
import random
from typing import Type, List, Optional, TypeVar
from pydantic import BaseModel
from src.extraction.llm_provider import LLMProvider
from src.extraction.providers.gemini_provider import GeminiProvider
from src.extraction.providers.groq_provider import GroqProvider
from src.extraction.providers.deepseek_provider import DeepSeekProvider
from src.extraction.chunker import SemanticChunker
from src.utils.logger import logger

T = TypeVar("T", bound=BaseModel)

class LLMOrchestrator:
    """Orchestrates 3-tier LLM fallback (Gemini -> Groq -> DeepSeek) with 413 chunking and 429 handling."""

    def __init__(self, providers: Optional[List[LLMProvider]] = None):
        if providers is not None:
            self.providers = providers
        else:
            # Only include providers that have API keys configured
            candidates = [GeminiProvider(), GroqProvider(), DeepSeekProvider()]
            self.providers = [p for p in candidates if p.api_key]
        
        self.quota_exhausted_providers: set = set()
        self.quota_exhausted: bool = False

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        """Check if exception represents a 429 Rate Limit error."""
        msg = str(exc).lower()
        return "429" in msg or "rate limit" in msg or "resource_exhausted" in msg or "too many requests" in msg or "quota" in msg

    def _is_quota_exhaustion_error(self, exc: Exception) -> bool:
        """Check if 429 error represents hard quota exhaustion (e.g. daily/tier limit)."""
        msg = str(exc).lower()
        return "resource_exhausted" in msg or "quota exceeded" in msg or "plan and billing" in msg

    async def _execute_with_retry(
        self,
        provider: LLMProvider,
        chunk: str,
        schema_class: Type[T],
        metrics: Optional[Any] = None,
        max_retries: int = 2
    ) -> Optional[T]:
        """Execute extraction on single provider with exponential backoff for 429s."""
        if provider.name in self.quota_exhausted_providers:
            logger.debug(
                f"Skipping {provider.name} — provider quota previously exhausted",
                extra={"component": "LLMOrchestrator", "llm_provider": provider.name}
            )
            return None

        attempt = 0
        while attempt <= max_retries:
            try:
                result = await provider.extract(chunk, schema_class)
                if result is not None:
                    return result
                break  # Non-error empty response -> do not retry same provider
            except Exception as exc:
                if self._is_rate_limit_error(exc):
                    if metrics and hasattr(metrics, "gemini_429s") and provider.name == "GeminiProvider":
                        metrics.gemini_429s += 1

                    if self._is_quota_exhaustion_error(exc) or attempt >= max_retries:
                        self.quota_exhausted_providers.add(provider.name)
                        if len(self.quota_exhausted_providers) >= len(self.providers):
                            self.quota_exhausted = True
                        logger.warning(
                            f"Hard quota/rate limit reached on {provider.name}. Fast-failing remaining calls to preserve deterministic pipeline.",
                            extra={"component": "LLMOrchestrator", "llm_provider": provider.name, "error": str(exc)}
                        )
                        break

                    backoff = (2.0 ** attempt) * random.uniform(0.8, 1.5)
                    logger.warning(
                        f"429 Rate Limit hit on {provider.name}, backing off for {backoff:.2f}s (attempt {attempt + 1})",
                        extra={"component": "LLMOrchestrator", "llm_provider": provider.name, "retry_count": attempt + 1}
                    )
                    await asyncio.sleep(backoff)
                    attempt += 1
                else:
                    logger.warning(
                        f"Provider {provider.name} failed with error: {exc}",
                        extra={"component": "LLMOrchestrator", "llm_provider": provider.name, "error": str(exc)}
                    )
                    break  # Fallthrough to next provider in tier chain

        return None

    async def extract_structured(self, raw_text: str, schema_class: Type[T], metrics: Optional[Any] = None) -> Optional[T]:
        """
        Main extraction entry point.
        1. Fast-fail if all provider quotas are exhausted
        2. Pre-flight chunking (413 protection)
        3. Tiered fallback (Gemini -> Groq -> DeepSeek)
        """
        if not raw_text or not raw_text.strip():
            return None

        if self.quota_exhausted:
            logger.debug("LLM orchestrator quota exhausted — fast-failing extraction.", extra={"component": "LLMOrchestrator"})
            return None

        # Step 1: Pre-flight semantic chunking
        chunks = SemanticChunker.chunk_text(
            raw_text,
            max_context_tokens=3000,
            reserved_output_tokens=1000
        )
        if not chunks:
            return None

        target_text = chunks[0]

        # Step 2: Fallback chain execution
        fallback_count = 0
        for provider in self.providers:
            if provider.name in self.quota_exhausted_providers:
                continue

            logger.info(
                f"Attempting structured extraction with {provider.name} (fallback_count={fallback_count})",
                extra={"component": "LLMOrchestrator", "llm_provider": provider.name, "fallback_count": fallback_count}
            )

            result = await self._execute_with_retry(provider, target_text, schema_class, metrics=metrics)
            if result is not None:
                logger.info(
                    f"Extraction successful using {provider.name}",
                    extra={"component": "LLMOrchestrator", "llm_provider": provider.name, "fallback_count": fallback_count}
                )
                if fallback_count > 0 and metrics and hasattr(metrics, "llm_fallbacks"):
                    metrics.llm_fallbacks += 1
                return result

            fallback_count += 1

        if len(self.quota_exhausted_providers) >= len(self.providers):
            self.quota_exhausted = True

        logger.warning("LLM extraction unavailable or skipped due to provider failure/quota limit", extra={"component": "LLMOrchestrator"})
        return None
