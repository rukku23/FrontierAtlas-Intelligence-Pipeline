"""Token-aware intelligent text chunking for preserving semantic sections and avoiding 413 errors."""
import re
from typing import List

class SemanticChunker:
    """Splits long scraped text into token-budgeted chunks preserving semantic boundaries."""

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimate token count (approx 4 characters per token)."""
        if not text:
            return 0
        return len(text) // 4 + 1

    @classmethod
    def chunk_text(
        cls,
        text: str,
        max_context_tokens: int = 3000,
        reserved_output_tokens: int = 1000,
        overlap_tokens: int = 150
    ) -> List[str]:
        """
        Split text into chunks fitting max_context_tokens - reserved_output_tokens,
        preserving paragraph and sentence boundaries.
        """
        if not text or not text.strip():
            return []

        effective_token_budget = max(max_context_tokens - reserved_output_tokens, 500)
        total_tokens = cls.estimate_tokens(text)

        if total_tokens <= effective_token_budget:
            return [text.strip()]

        # Split text by paragraph boundaries (\n\n, \n)
        sections = re.split(r"(\n\s*\n|\n)", text)
        chunks: List[str] = []
        current_chunk_parts: List[str] = []
        current_tokens = 0

        for part in sections:
            part_tokens = cls.estimate_tokens(part)

            if current_tokens + part_tokens > effective_token_budget and current_chunk_parts:
                chunk_str = "".join(current_chunk_parts).strip()
                if chunk_str:
                    chunks.append(chunk_str)

                # Keep overlap from end of current chunk
                overlap_text = chunk_str[-overlap_tokens * 4 :] if len(chunk_str) > overlap_tokens * 4 else ""
                current_chunk_parts = [overlap_text, part] if overlap_text else [part]
                current_tokens = cls.estimate_tokens("".join(current_chunk_parts))
            else:
                current_chunk_parts.append(part)
                current_tokens += part_tokens

        if current_chunk_parts:
            final_str = "".join(current_chunk_parts).strip()
            if final_str:
                chunks.append(final_str)

        return chunks
