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

    def _is_rate_limit_error(self, exc: Exception) -> bool:
        """Check if exception represents a 429 Rate Limit error."""
        msg = str(exc).lower()
        return "429" in msg or "rate limit" in msg or "resource_exhausted" in msg or "too many requests" in msg

    async def _execute_with_retry(
        self,
        provider: LLMProvider,
        chunk: str,
        schema_class: Type[T],
        max_retries: int = 2
    ) -> Optional[T]:
        """Execute extraction on single provider with exponential backoff for 429s."""
        attempt = 0
        while attempt <= max_retries:
            try:
                result = await provider.extract(chunk, schema_class)
                if result is not None:
                    return result
                break  # Non-error empty response -> do not retry same provider
            except Exception as exc:
                if self._is_rate_limit_error(exc) and attempt < max_retries:
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

    async def extract_structured(self, raw_text: str, schema_class: Type[T]) -> Optional[T]:
        """
        Main extraction entry point.
        1. Pre-flight chunking (413 protection)
        2. Tiered fallback (Gemini -> Groq -> DeepSeek)
        """
        if not raw_text or not raw_text.strip():
            return None

        # Step 1: Pre-flight semantic chunking
        chunks = SemanticChunker.chunk_text(
            raw_text,
            max_context_tokens=3000,
            reserved_output_tokens=1000
        )
        if not chunks:
            return None

        # Process first/main dense chunk (or iterate over chunks if array mapping)
        target_text = chunks[0]

        # Step 2: Fallback chain execution
        fallback_count = 0
        for provider in self.providers:
            logger.info(
                f"Attempting structured extraction with {provider.name} (fallback_count={fallback_count})",
                extra={"component": "LLMOrchestrator", "llm_provider": provider.name, "fallback_count": fallback_count}
            )

            result = await self._execute_with_retry(provider, target_text, schema_class)
            if result is not None:
                logger.info(
                    f"Extraction successful using {provider.name}",
                    extra={"component": "LLMOrchestrator", "llm_provider": provider.name, "fallback_count": fallback_count}
                )
                return result

            fallback_count += 1

        logger.error("All LLM providers in fallback chain failed or were unavailable", extra={"component": "LLMOrchestrator"})
        return None
